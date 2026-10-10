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

    config.stale_timeout_ms = 100;
    fid_driver *second = nullptr;
    require(fid_create(&config, &second) == FID_OK, "create timeout driver");
    Driver timeout_driver(second, fid_destroy);
    require(fid_enable(second) == FID_OK, "enable timeout driver");
    require(wait_for(second, [](const fid_status &s) { return s.timed_out && !s.enabled; }), "worker watchdog without frames");
    fid_neutral_frame(&frame); require(fid_submit(second, &frame) == FID_OK, "submit after timeout");
    require(!status_of(second).enabled, "submit cannot resume output");
    fid_destroy(nullptr);
    std::cout << "C API lifecycle, worker, journal, and watchdog checks passed\n";
}
