#include "control.hpp"
#include <algorithm>
#include <cmath>

namespace fid {
namespace {
bool valid_axis(const fid_axis_config &a) {
    return std::isfinite(a.neutral) && a.neutral > 0 && a.neutral < 1 &&
           std::isfinite(a.dead_zone) && a.dead_zone >= 0 &&
           a.dead_zone < std::min(a.neutral, 1 - a.neutral) &&
           std::isfinite(a.max_speed) && a.max_speed >= 0 && a.max_speed <= 100000 &&
           a.inverted <= 1;
}
std::array<double, 4> levels(const fid_frame &f) {
    return {f.left_click, f.right_click, f.delete_key, f.insert_key};
}
int32_t take_integer(double &fraction, double delta) {
    fraction += delta;
    auto whole = static_cast<int32_t>(std::trunc(fraction));
    fraction -= whole;
    return whole;
}
} // namespace

bool valid_config(const fid_config &c) {
    if (c.abi_version != FID_ABI_VERSION || c.backend > FID_NATIVE ||
        c.tick_hz < 10 || c.tick_hz > 1000 || c.stale_timeout_ms < 1 ||
        c.stale_timeout_ms > 60000 ||
        c.stale_timeout_ms < (1000u + c.tick_hz - 1) / c.tick_hz ||
        !valid_axis(c.pointer_x) || !valid_axis(c.pointer_y) || !valid_axis(c.scroll))
        return false;
    for (const auto &b : c.buttons) {
        if (!std::isfinite(b.activation_threshold) || !std::isfinite(b.release_threshold) ||
            b.release_threshold <= 0 || b.activation_threshold >= 1 ||
            b.release_threshold >= b.activation_threshold || b.dwell_ms > 60000)
            return false;
    }
    return true;
}

bool valid_frame(const fid_frame &f) {
    const double values[] = {f.pointer_x, f.pointer_y, f.scroll, f.left_click,
                             f.right_click, f.delete_key, f.insert_key};
    for (double v : values)
        if (!std::isfinite(v) || v < 0 || v > 1) return false;
    return true;
}

double axis_velocity(double value, const fid_axis_config &a) {
    const double low = a.neutral - a.dead_zone;
    const double high = a.neutral + a.dead_zone;
    double speed = 0;
    if (value > high)
        speed = (value - high) / (1 - high);
    else if (value < low)
        speed = (value - low) / low;
    return speed * a.max_speed * (a.inverted ? -1 : 1);
}

void Control::enable(Time now) {
    enabled_ = true;
    awaiting_neutral_ = true;
    timed_out_ = false;
    have_frame_ = false;
    enabled_at_ = last_tick_ = now;
    buttons_ = {};
    fractions_ = {};
}

void Control::pause() {
    enabled_ = false;
    awaiting_neutral_ = false;
    have_frame_ = false;
    buttons_ = {};
    fractions_ = {};
}

void Control::submit(const fid_frame &frame, Time now) {
    // A late producer must not erase an expired watchdog while the worker is
    // delayed. Expiry latches paused even if a fresh frame arrives first.
    const Time freshest = have_frame_ ? received_at_ : enabled_at_;
    if (enabled_ && now - freshest >= config_.stale_timeout_ms / 1000.0) {
        pause();
        timed_out_ = true;
    }
    frame_ = frame;
    received_at_ = now;
    have_frame_ = true;
}

std::vector<fid_event> Control::tick(Time now) {
    std::vector<fid_event> events;
    if (!enabled_) return events;
    const double dt = std::clamp(now - last_tick_, 0.0, 0.1);
    last_tick_ = now;
    const Time freshest = have_frame_ ? received_at_ : enabled_at_;
    if (now - freshest >= config_.stale_timeout_ms / 1000.0) {
        pause();
        timed_out_ = true;
        return events;
    }
    if (!have_frame_) return events;
    const auto values = levels(frame_);
    if (awaiting_neutral_) {
        for (size_t i = 0; i < values.size(); ++i)
            if (values[i] >= config_.buttons[i].release_threshold) return events;
        awaiting_neutral_ = false;
        // Arming emits no motion, preventing a jump on the first fresh frame.
        return events;
    }
    const auto stamp = static_cast<uint64_t>(std::max(0.0, now) * 1000000);
    auto add = [&](uint32_t type, int32_t x = 0, int32_t y = 0) {
        events.push_back({type, x, y, stamp});
    };
    const std::array<double, 3> axis_values{frame_.pointer_x, frame_.pointer_y, frame_.scroll};
    const std::array<fid_axis_config, 3> axes{config_.pointer_x, config_.pointer_y, config_.scroll};
    std::array<int32_t, 3> movement{};
    for (size_t i = 0; i < axes.size(); ++i) {
        const double velocity = axis_velocity(axis_values[i], axes[i]);
        // Clear leftovers at neutral or on reversal; do not drift or delay reversal.
        if (velocity == 0 || velocity * fractions_[i] < 0) fractions_[i] = 0;
        movement[i] = take_integer(fractions_[i], velocity * dt);
    }
    if (movement[0] || movement[1]) add(FID_EVENT_MOVE, movement[0], movement[1]);
    if (movement[2]) add(FID_EVENT_SCROLL, 0, movement[2]);

    const uint32_t types[] = {FID_EVENT_LEFT_CLICK, FID_EVENT_RIGHT_CLICK,
                              FID_EVENT_DELETE, FID_EVENT_INSERT};
    for (size_t i = 0; i < values.size(); ++i) {
        auto &state = buttons_[i];
        const auto &cfg = config_.buttons[i];
        if (values[i] < cfg.release_threshold) {
            state = {};
        } else if (!state.latched) {
            if (values[i] > cfg.activation_threshold) {
                if (!state.dwelling) {
                    state.dwelling = true;
                    state.since = now;
                }
                if (now - state.since + 1e-9 >= cfg.dwell_ms / 1000.0) {
                    add(types[i]);
                    state.latched = true;
                    state.dwelling = false;
                }
            } else {
                state.dwelling = false;
            }
        }
    }
    return events;
}
} // namespace fid
