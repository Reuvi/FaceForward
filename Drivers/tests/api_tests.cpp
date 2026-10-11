#include "face_input_driver.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <memory>
#include <thread>

namespace {
void require(bool condition, const char *message) {
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
using Driver = std::unique_ptr<fid_driver, decltype(&fid_destroy)>;
fid_status status_of(fid_driver *driver) {
    fid_status status{};
    require(fid_get_status(driver, &status) == FID_OK, "status query");
    return status;
}
bool wait_for(fid_driver *driver, bool (*predicate)(const fid_status &), int ms = 1000) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
    while (std::chrono::steady_clock::now() < deadline) {
        if (predicate(status_of(driver))) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return false;
}
bool wait_for_target(fid_driver *driver, double x, double y, int ms = 1500) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
    while (std::chrono::steady_clock::now() < deadline) {
        const auto status = status_of(driver);
        if (status.target_reached && status.pointer_position_valid &&
            std::abs(status.pointer_position_x - x) < 0.002 &&
            std::abs(status.pointer_position_y - y) < 0.002) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    return false;
}
} // namespace

int main() {
    fid_config config{}; fid_default_config(&config);
    require(config.backend == FID_DRY_RUN && config.tick_hz == 60, "safe default backend");
    fid_driver *raw = nullptr;
    require(fid_create(nullptr, &raw) == FID_INVALID_ARGUMENT && !raw, "null config rejected");
    auto invalid = config; invalid.abi_version = 99;
    require(fid_create(&invalid, &raw) == FID_INVALID_ARGUMENT && !raw, "invalid config rejected");
    config.stale_timeout_ms = 1000; // Allow slow CI scheduling during integration checks.
    config.buttons[0].dwell_ms = 0;
    require(fid_create(&config, &raw) == FID_OK && raw, "create dry-run driver");
    Driver driver(raw, fid_destroy);
    require(!status_of(raw).enabled, "created paused");
    fid_frame frame{}; fid_neutral_frame(&frame);
    frame.pointer_x = std::numeric_limits<double>::quiet_NaN();
    require(fid_submit(raw, &frame) == FID_INVALID_ARGUMENT, "API rejects NaN");
    require(status_of(raw).rejected_frames == 1, "invalid frame counted");
    require(fid_enable(raw) == FID_OK, "enable succeeds");
    fid_neutral_frame(&frame);
    require(fid_submit(raw, &frame) == FID_OK, "submit neutral");
    require(wait_for(raw, [](const fid_status &s) { return !s.awaiting_neutral; }), "worker arms");
    frame.left_click = 1;
    require(fid_submit(raw, &frame) == FID_OK, "submit button");
    require(wait_for(raw, [](const fid_status &s) { return s.emitted_events == 1; }), "worker emits click");
    require(fid_pause(raw) == FID_OK, "pause succeeds");
    fid_event events[8]{}; size_t count = 0;
    require(fid_drain_events(raw, events, 8, &count) == FID_OK, "drain journal");
    require(count == 1 && events[0].type == FID_EVENT_LEFT_CLICK, "journal contains complete action");
    require(fid_drain_events(raw, events, 8, &count) == FID_OK && count == 0, "drain destructive");
    require(fid_drain_events(raw, nullptr, 1, &count) == FID_INVALID_ARGUMENT, "null buffer rejected");
    require(fid_submit(nullptr, &frame) == FID_INVALID_ARGUMENT, "null handle rejected");

    require(fid_enable(raw) == FID_OK, "enable for held-key test");
    fid_neutral_frame(&frame);
    require(fid_submit(raw, &frame) == FID_OK, "held-key test arms on neutral frame");
    require(wait_for(raw, [](const fid_status &s) { return !s.awaiting_neutral; }), "held-key test arms");
    frame.keys_down = FID_KEY_W | FID_KEY_LEFT_SHIFT;
    require(fid_submit(raw, &frame) == FID_OK, "submit held W+Shift state");
    require(wait_for(raw, [](const fid_status &s) {
        return s.held_key_mask == (FID_KEY_W | FID_KEY_LEFT_SHIFT) && s.emitted_events >= 3;
    }), "key-down transitions update status");
    frame.keys_down = FID_KEY_LEFT_SHIFT;
    require(fid_submit(raw, &frame) == FID_OK, "submit W release state");
    require(wait_for(raw, [](const fid_status &s) { return s.held_key_mask == FID_KEY_LEFT_SHIFT; }),
            "cleared key bit releases independently");
    require(fid_pause(raw) == FID_OK, "pause releases remaining held key");
    require(status_of(raw).held_key_mask == 0, "pause status reports no held keys");
    require(fid_drain_events(raw, events, 8, &count) == FID_OK, "drain key journal");
    bool saw_w_down = false, saw_w_up = false, saw_shift_up = false;
    for (size_t i = 0; i < count; ++i) {
        saw_w_down |= events[i].type == FID_EVENT_KEY_DOWN && events[i].x == FID_KEY_W;
        saw_w_up |= events[i].type == FID_EVENT_KEY_UP && events[i].x == FID_KEY_W;
        saw_shift_up |= events[i].type == FID_EVENT_KEY_UP && events[i].x == FID_KEY_LEFT_SHIFT;
    }
    require(saw_w_down && saw_w_up && saw_shift_up, "journal includes key down, clear, and pause release");

    require(fid_enable(raw) == FID_OK, "enable for relative velocity test");
    fid_neutral_frame(&frame);
    require(fid_submit(raw, &frame) == FID_OK, "relative velocity test submits neutral");
    require(wait_for(raw, [](const fid_status &s) { return !s.awaiting_neutral; }),
            "relative velocity test arms");
    const auto movement_before = status_of(raw).emitted_events;
    frame.pointer_x = 0.65;
    require(fid_submit(raw, &frame) == FID_OK, "submit positive relative velocity");
    const auto movement_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (status_of(raw).emitted_events <= movement_before &&
           std::chrono::steady_clock::now() < movement_deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    require(status_of(raw).emitted_events > movement_before,
            "velocity produces movement event");
    require(fid_pause(raw) == FID_OK, "pause after relative velocity test");
    require(fid_drain_events(raw, events, 8, &count) == FID_OK,
            "drain relative velocity event");
    bool saw_positive_relative_move = false;
    for (size_t i = 0; i < count; ++i)
        saw_positive_relative_move |= events[i].type == FID_EVENT_MOVE &&
                                      events[i].x > 0 && events[i].y == 0;
    require(saw_positive_relative_move,
            "velocity mode reports positive incremental X movement, not a target position");

    fid_neutral_frame(&frame);
    frame.pointer_mode = FID_POINTER_TARGET;
    frame.target_x = 0.52; frame.target_y = 0.5; frame.target_speed = 0.1;
    require(fid_enable(raw) == FID_OK, "re-enable for target mode");
    require(fid_submit(raw, &frame) == FID_OK, "target frame accepted by dry-run backend");
    const auto slow_start = std::chrono::steady_clock::now();
    require(wait_for_target(raw, 0.52, 0.5), "slow target mode reaches endpoint");
    const auto slow_time = std::chrono::steady_clock::now() - slow_start;
    auto target_status = status_of(raw);
    require(target_status.pointer_mode == FID_POINTER_TARGET && target_status.pointer_position_valid,
            "target telemetry reports mode and position");
    require(std::abs(target_status.pointer_position_x - 0.52) < 0.002 &&
            std::abs(target_status.pointer_position_y - 0.5) < 0.002, "target is not overshot");
    frame.target_x = 0.5; frame.target_speed = 1;
    require(fid_submit(raw, &frame) == FID_OK && wait_for_target(raw, 0.5, 0.5),
            "target can return to its starting point");
    frame.target_x = 0.52; frame.target_speed = 0.6;
    const auto fast_start = std::chrono::steady_clock::now();
    require(fid_submit(raw, &frame) == FID_OK && wait_for_target(raw, 0.52, 0.5),
            "faster target reaches the same endpoint");
    const auto fast_time = std::chrono::steady_clock::now() - fast_start;
    require(slow_time > fast_time * 2, "higher normalized speed reaches the same target faster");
    require(fid_pause(raw) == FID_OK, "pause after target trial");

    config.stale_timeout_ms = 100;
    fid_driver *second = nullptr;
    require(fid_create(&config, &second) == FID_OK, "create timeout driver");
    Driver timeout_driver(second, fid_destroy);
    require(fid_enable(second) == FID_OK, "enable timeout driver");
    require(wait_for(second, [](const fid_status &s) { return s.timed_out && !s.enabled; }), "worker watchdog without frames");
    require(fid_enable(second) == FID_OK, "re-enable for held-key watchdog test");
    fid_neutral_frame(&frame);
    require(fid_submit(second, &frame) == FID_OK, "submit neutral for watchdog arming");
    require(wait_for(second, [](const fid_status &s) { return !s.awaiting_neutral; }), "watchdog test arms");
    frame.keys_down = FID_KEY_D;
    require(fid_submit(second, &frame) == FID_OK, "submit held key before watchdog");
    require(wait_for(second, [](const fid_status &s) { return s.held_key_mask == FID_KEY_D; }),
            "watchdog test key becomes held");
    require(wait_for(second, [](const fid_status &s) {
        return s.timed_out && !s.enabled && s.held_key_mask == 0;
    }, 1000), "watchdog releases held key");
    require(fid_drain_events(second, events, 8, &count) == FID_OK, "drain watchdog transitions");
    bool saw_watchdog_key_up = false;
    for (size_t i = 0; i < count; ++i)
        saw_watchdog_key_up |= events[i].type == FID_EVENT_KEY_UP && events[i].x == FID_KEY_D;
    require(saw_watchdog_key_up, "watchdog key-up is observable in journal");
    fid_neutral_frame(&frame); require(fid_submit(second, &frame) == FID_OK, "submit after timeout");
    require(!status_of(second).enabled, "submit cannot resume output");
    fid_destroy(nullptr);
    std::cout << "C API lifecycle, worker, journal, and watchdog checks passed\n";
}
