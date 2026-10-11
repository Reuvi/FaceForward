#include "backend.hpp"
#include "control.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>

namespace {
using Clock = std::chrono::steady_clock;
double now_seconds() {
    return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();
}
class DryRun final : public fid::Backend {
public:
    fid_result ready() const override { return FID_OK; }
    fid_result emit(const fid_event &) override { return FID_OK; }
    fid_result release() override { return FID_OK; }
    bool supports_target_pointer() const override { return true; }
    fid_result pointer_position(double &x, double &y) const override {
        x = x_ / (width_ - 1); y = y_ / (height_ - 1); return FID_OK;
    }
    fid_result move_toward(double tx, double ty, double speed, double dt,
                           bool &reached, int32_t &dx, int32_t &dy) override {
        const double before_x = x_, before_y = y_;
        const double target_x = tx * (width_ - 1), target_y = ty * (height_ - 1);
        const double vx = target_x - x_, vy = target_y - y_;
        const double distance = std::hypot(vx, vy);
        const double step = std::min(distance, speed * dt);
        if (distance > 0 && step > 0) { x_ += vx / distance * step; y_ += vy / distance * step; }
        reached = distance < 0.5 || (speed > 0 && distance <= speed * dt);
        if (reached) { x_ = target_x; y_ = target_y; }
        dx = static_cast<int32_t>(std::lround(x_ - before_x));
        dy = static_cast<int32_t>(std::lround(y_ - before_y));
        return FID_OK;
    }
private:
    static constexpr double width_ = 1920, height_ = 1080;
    double x_ = (width_ - 1) / 2, y_ = (height_ - 1) / 2;
};
} // namespace

struct fid_driver {
    fid_driver(const fid_config &config, std::unique_ptr<fid::Backend> output)
        : control(config), backend(std::move(output)), config(config),
          period(std::chrono::duration_cast<Clock::duration>(
              std::chrono::duration<double>(1.0 / config.tick_hz))) {
        status.backend = config.backend;
        status.capabilities = backend->capabilities();
    }
    ~fid_driver() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            stopping = true;
            control.pause();
        }
        wake.notify_all();
        if (worker.joinable()) worker.join();
        backend->release();
    }
    void record(const fid_event &event) {
        ++status.emitted_events;
        if (journal.size() == 1024) {
            journal.pop_front();
            ++status.dropped_log_events;
        }
        journal.push_back(event);
    }
    fid_result release_output(uint32_t keys_to_log) {
        const auto result = backend->release();
        if (result != FID_OK) status.last_error = result;
        const auto stamp = static_cast<uint64_t>(std::max(0.0, now_seconds()) * 1000000);
        for (uint32_t bit = 1; bit <= FID_KEY_LEFT_SHIFT; bit <<= 1)
            if (bit != FID_KEY_LEFT_SHIFT && (keys_to_log & bit))
                record({FID_EVENT_KEY_UP, static_cast<int32_t>(bit), 0, stamp});
        if (keys_to_log & FID_KEY_LEFT_SHIFT)
            record({FID_EVENT_KEY_UP, FID_KEY_LEFT_SHIFT, 0, stamp});
        return result;
    }
    void start() { worker = std::thread([this] { run(); }); }
    void process_tick(double now) {
        try {
            const bool was_enabled = control.enabled();
            const uint32_t held_before_tick = control.held_key_mask();
            auto events = control.tick(now);
            bool absolute_target_moved = false;
            status.pointer_velocity_x = status.pointer_velocity_y = 0;
            status.target_reached = 0;
            if (control.enabled() && !control.awaiting_neutral() &&
                control.frame().pointer_mode == FID_POINTER_TARGET &&
                control.frame().target_speed > 0) {
                const auto &frame = control.frame();
                bool reached = false;
                int32_t dx = 0, dy = 0;
                const double dt = control.tick_seconds();
                const auto moved = backend->move_toward(frame.target_x, frame.target_y,
                    frame.target_speed * config.target_max_speed, dt, reached, dx, dy);
                if (moved != FID_OK) {
                    status.last_error = moved;
                    control.pause();
                    events.clear();
                } else {
                    status.target_reached = reached;
                    if (dt > 0) {
                        status.pointer_velocity_x = dx / dt;
                        status.pointer_velocity_y = dy / dt;
                    }
                    if (dx || dy) {
                        absolute_target_moved = true;
                        events.push_back({FID_EVENT_MOVE, dx, dy,
                            static_cast<uint64_t>(std::max(0.0, now_seconds()) * 1000000)});
                    }
                }
            }
            if (was_enabled && !control.enabled()) {
                release_output(held_before_tick);
            }
            for (const auto &event : events) {
                // Target mode already performed this step through the
                // backend's absolute-position path; do not inject REL too.
                const auto result = absolute_target_moved && event.type == FID_EVENT_MOVE
                    ? FID_OK : backend->emit(event);
                if (result != FID_OK) {
                    status.last_error = result;
                    const auto held = control.held_key_mask();
                    control.pause();
                    release_output(held);
                    break;
                }
                record(event);
            }
        } catch (...) {
            status.last_error = FID_INTERNAL_ERROR;
            const auto held = control.held_key_mask();
            control.pause();
            release_output(held);
        }
    }
    void run() {
        std::unique_lock<std::mutex> lock(mutex);
        auto deadline = Clock::now() + period;
        while (!stopping) {
            wake.wait_until(lock, deadline, [this] { return stopping; });
            if (stopping) break;
            process_tick(now_seconds());
            deadline += period;
            // Skip missed ticks rather than replaying a backlog.
            if (deadline <= Clock::now()) deadline = Clock::now() + period;
        }
    }

    std::mutex mutex;
    std::condition_variable wake;
    fid::Control control;
    std::unique_ptr<fid::Backend> backend;
    fid_config config;
    Clock::duration period;
    fid_status status{};
    std::deque<fid_event> journal;
    std::thread worker;
    bool stopping = false;
};

extern "C" {
uint32_t fid_abi_version(void) { return FID_ABI_VERSION; }
void fid_default_config(fid_config *config) {
    if (!config) return;
    *config = {};
    config->abi_version = FID_ABI_VERSION;
    config->backend = FID_DRY_RUN;
    config->tick_hz = 60;
    config->stale_timeout_ms = 250;
    config->pointer_x = {0.5, 0.05, 600, 0};
    config->pointer_y = {0.5, 0.05, 600, 0};
    config->scroll = {0.5, 0.05, 12, 0};
    config->target_max_speed = 600;
    for (auto &button : config->buttons) button = {0.7, 0.3, 150};
}

void fid_neutral_frame(fid_frame *frame) {
    if (frame) *frame = {0.5, 0.5, 0.5, 0, 0, 0, 0,
                         FID_POINTER_VELOCITY, 0.5, 0.5, 0, 0};
}

fid_result fid_create(const fid_config *config, fid_driver **out_driver) {
    if (!out_driver) return FID_INVALID_ARGUMENT;
    *out_driver = nullptr;
    if (!config || !fid::valid_config(*config)) return FID_INVALID_ARGUMENT;
    try {
        std::unique_ptr<fid::Backend> backend;
        if (config->backend == FID_DRY_RUN) backend = std::make_unique<DryRun>();
        else {
#ifdef FID_HAS_NATIVE
            fid_result result = FID_OK;
            backend = fid::make_native_backend(result);
            if (!backend) return result;
#else
            return FID_UNSUPPORTED;
#endif
        }
        auto driver = std::make_unique<fid_driver>(*config, std::move(backend));
        driver->start();
        *out_driver = driver.release();
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

static fid_result submit_frame(fid_driver *driver, const fid_frame *frame, bool processed) {
    if (!driver) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        if (!frame || !fid::valid_frame(*frame)) {
            if (processed) {
                const auto held = driver->control.held_key_mask();
                driver->control.pause();
                driver->release_output(held);
                driver->status.last_error = FID_INVALID_ARGUMENT;
            }
            ++driver->status.rejected_frames;
            return FID_INVALID_ARGUMENT;
        }
        if (frame->pointer_mode == FID_POINTER_TARGET &&
            !driver->backend->supports_target_pointer()) return FID_UNSUPPORTED;
        const bool was_enabled = driver->control.enabled();
        const auto held_before_submit = driver->control.held_key_mask();
        driver->control.submit(*frame, now_seconds());
        if (was_enabled && !driver->control.enabled()) {
            driver->release_output(held_before_submit);
        }
        ++driver->status.accepted_frames;
        if (processed) {
            driver->process_tick(now_seconds());
            return static_cast<fid_result>(driver->status.last_error);
        }
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

fid_result fid_submit(fid_driver *driver, const fid_frame *frame) {
    return submit_frame(driver, frame, false);
}

fid_result fid_submit_processed(fid_driver *driver, const fid_frame *frame) {
    return submit_frame(driver, frame, true);
}

fid_result fid_enable(fid_driver *driver) {
    if (!driver) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        if (driver->control.enabled()) return FID_OK;
        const auto result = driver->backend->ready();
        if (result != FID_OK) {
            driver->status.last_error = result;
            return result;
        }
        driver->control.enable(now_seconds());
        driver->status.last_error = FID_OK;
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

fid_result fid_pause(fid_driver *driver) {
    if (!driver) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        const auto held = driver->control.held_key_mask();
        driver->control.pause();
        const auto result = driver->release_output(held);
        if (result != FID_OK) driver->status.last_error = result;
        return result;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

fid_result fid_get_status(fid_driver *driver, fid_status *status) {
    if (!driver || !status) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        *status = driver->status;
        status->enabled = driver->control.enabled();
        status->awaiting_neutral = driver->control.awaiting_neutral();
        status->timed_out = driver->control.timed_out();
        status->held_key_mask = driver->control.held_key_mask();
        const auto &frame = driver->control.frame();
        status->pointer_mode = frame.pointer_mode;
        status->target_x = frame.target_x;
        status->target_y = frame.target_y;
        status->target_speed = frame.target_speed;
        status->pointer_position_valid = driver->backend->pointer_position(
            status->pointer_position_x, status->pointer_position_y) == FID_OK;
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

fid_result fid_drain_events(fid_driver *driver, fid_event *events,
                            size_t capacity, size_t *out_count) {
    if (out_count) *out_count = 0;
    if (!driver || !out_count || (!events && capacity)) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        while (*out_count < capacity && !driver->journal.empty()) {
            events[(*out_count)++] = driver->journal.front();
            driver->journal.pop_front();
        }
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
}

void fid_destroy(fid_driver *driver) {
    try { delete driver; } catch (...) { /* Destruction must not cross the C ABI. */ }
}

const char *fid_result_string(fid_result result) {
    switch (result) {
        case FID_OK: return "ok";
        case FID_INVALID_ARGUMENT: return "invalid argument";
        case FID_UNSUPPORTED: return "backend unsupported in this build";
        case FID_PERMISSION_DENIED: return "input permission denied";
        case FID_BACKEND_UNAVAILABLE: return "native input backend unavailable";
        case FID_IO_ERROR: return "OS event write failed";
        case FID_INTERNAL_ERROR: return "internal error";
    }
    return "unknown error";
}
} // extern C
