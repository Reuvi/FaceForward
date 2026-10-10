#include "backend.hpp"
#include "control.hpp"
#include <chrono>
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
};
} // namespace

struct fid_driver {
    fid_driver(const fid_config &config, std::unique_ptr<fid::Backend> output)
        : control(config), backend(std::move(output)),
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
    void start() { worker = std::thread([this] { run(); }); }
    void run() {
        std::unique_lock<std::mutex> lock(mutex);
        auto deadline = Clock::now() + period;
        while (!stopping) {
            wake.wait_until(lock, deadline, [this] { return stopping; });
            if (stopping) break;
            try {
                const bool was_enabled = control.enabled();
                auto events = control.tick(now_seconds());
                if (was_enabled && !control.enabled()) {
                    const auto result = backend->release();
                    if (result != FID_OK) status.last_error = result;
                }
                for (const auto &event : events) {
                    const auto result = backend->emit(event);
                    if (result != FID_OK) {
                        status.last_error = result;
                        control.pause();
                        backend->release();
                        break;
                    }
                    ++status.emitted_events;
                    if (journal.size() == 1024) {
                        journal.pop_front();
                        ++status.dropped_log_events;
                    }
                    journal.push_back(event);
                }
            } catch (...) {
                status.last_error = FID_INTERNAL_ERROR;
                control.pause();
                backend->release();
            }
            deadline += period;
            // Skip missed ticks rather than replaying a backlog.
            if (deadline <= Clock::now()) deadline = Clock::now() + period;
        }
    }

    std::mutex mutex;
    std::condition_variable wake;
    fid::Control control;
    std::unique_ptr<fid::Backend> backend;
    Clock::duration period;
    fid_status status{};
    std::deque<fid_event> journal;
    std::thread worker;
    bool stopping = false;
};

extern "C" {
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
    for (auto &button : config->buttons) button = {0.7, 0.3, 150};
}

void fid_neutral_frame(fid_frame *frame) {
    if (frame) *frame = {0.5, 0.5, 0.5, 0, 0, 0, 0};
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

fid_result fid_submit(fid_driver *driver, const fid_frame *frame) {
    if (!driver || !frame) return FID_INVALID_ARGUMENT;
    try {
        std::lock_guard<std::mutex> lock(driver->mutex);
        if (!fid::valid_frame(*frame)) {
            ++driver->status.rejected_frames;
            return FID_INVALID_ARGUMENT;
        }
        driver->control.submit(*frame, now_seconds());
        ++driver->status.accepted_frames;
        return FID_OK;
    } catch (...) { return FID_INTERNAL_ERROR; }
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
        driver->control.pause();
        const auto result = driver->backend->release();
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
