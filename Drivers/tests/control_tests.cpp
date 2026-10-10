#include "control.hpp"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>

namespace {
int checks = 0;
void require(bool condition, const char *message) {
    ++checks;
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
fid_config defaults() {
    fid_config c{};
    c.abi_version = FID_ABI_VERSION;
    c.backend = FID_DRY_RUN;
    c.tick_hz = 60;
    c.stale_timeout_ms = 250;
    c.pointer_x = c.pointer_y = {0.5, 0.05, 600, 0};
    c.scroll = {0.5, 0.05, 12, 0};
    for (auto &b : c.buttons) b = {0.7, 0.3, 150};
    return c;
}
fid_frame neutral() { return {0.5, 0.5, 0.5, 0, 0, 0, 0}; }
void arm(fid::Control &control, double now = 0) {
    control.enable(now);
    control.submit(neutral(), now);
    require(control.tick(now).empty(), "arming emits no events");
    require(!control.awaiting_neutral(), "neutral buttons arm output");
}
int count(const std::vector<fid_event> &events, uint32_t type) {
    int result = 0;
    for (const auto &event : events) result += event.type == type;
    return result;
}

void validation_and_axes() {
    auto c = defaults();
    require(fid::valid_config(c), "default config valid");
    require(fid::valid_frame(neutral()), "neutral frame valid");
    auto f = neutral();
    f.left_click = std::numeric_limits<double>::quiet_NaN();
    require(!fid::valid_frame(f), "NaN rejected");
    f.left_click = std::numeric_limits<double>::infinity();
    require(!fid::valid_frame(f), "infinity rejected");
    f.left_click = -0.01;
    require(!fid::valid_frame(f), "negative rejected");
    f.left_click = 1.01;
    require(!fid::valid_frame(f), "greater than one rejected");
    c.pointer_x.neutral = 0;
    require(!fid::valid_config(c), "invalid neutral rejected");
    c = defaults(); c.pointer_x.dead_zone = 0.5;
    require(!fid::valid_config(c), "dead zone cannot reach endpoint");
    c = defaults(); c.buttons[0].release_threshold = 0.8;
    require(!fid::valid_config(c), "inverted thresholds rejected");
    c = defaults(); c.tick_hz = 9;
    require(!fid::valid_config(c), "worker rate below supported range rejected");
    c = defaults(); c.stale_timeout_ms = 1;
    require(!fid::valid_config(c), "timeout shorter than tick rejected");
    c = defaults(); c.abi_version = 2;
    require(!fid::valid_config(c), "ABI mismatch rejected");
    c = defaults(); c.backend = 10;
    require(!fid::valid_config(c), "invalid backend rejected");
    const auto a = defaults().pointer_x;
    require(fid::axis_velocity(0.5, a) == 0, "center neutral");
    require(fid::axis_velocity(0.45, a) == 0, "dead-zone left edge exactly neutral");
    require(fid::axis_velocity(0.55, a) == 0, "dead-zone right edge exactly neutral");
    require(fid::axis_velocity(0, a) == -600, "left endpoint");
    require(fid::axis_velocity(1, a) == 600, "right endpoint");
    require(std::abs(fid::axis_velocity(0.65, a) - 600 * 2.0 / 9) < 1e-9, "linear partial speed");
    auto changed = a; changed.neutral = 0.4; changed.inverted = 1;
    require(fid::axis_velocity(0.4, changed) == 0, "neutral configurable");
    require(fid::axis_velocity(1, changed) == -600, "inversion configurable");
}

void buttons_and_hysteresis() {
    fid::Control core(defaults()); arm(core);
    auto frame = neutral(); frame.left_click = 1;
    core.submit(frame, 0.01);
    require(core.tick(0.01).empty(), "dwell starts without action");
    core.submit(frame, 0.15);
    require(core.tick(0.15).empty(), "early dwell does not fire");
    core.submit(frame, 0.16);
    require(count(core.tick(0.16), FID_EVENT_LEFT_CLICK) == 1, "dwell fires once");
    core.submit(frame, 0.30);
    require(core.tick(0.30).empty(), "sustained button does not repeat");
    frame.left_click = 0.5; core.submit(frame, 0.31); core.tick(0.31);
    frame.left_click = 1; core.submit(frame, 0.32);
    require(core.tick(0.32).empty(), "hysteresis band does not rearm");
    frame.left_click = 0; core.submit(frame, 0.33); core.tick(0.33);
    frame.left_click = 1; core.submit(frame, 0.34); core.tick(0.34);
    core.submit(frame, 0.49);
    require(count(core.tick(0.49), FID_EVENT_LEFT_CLICK) == 1, "release allows next click");
    frame.left_click = 0; core.submit(frame, 0.50); core.tick(0.50);
    frame.left_click = 1; core.submit(frame, 0.51); core.tick(0.51);
    frame.left_click = 0.7; core.submit(frame, 0.60); core.tick(0.60);
    frame.left_click = 1; core.submit(frame, 0.61); core.tick(0.61);
    core.submit(frame, 0.70);
    require(core.tick(0.70).empty(), "threshold interruption restarts dwell");
    core.submit(frame, 0.76);
    require(count(core.tick(0.76), FID_EVENT_LEFT_CLICK) == 1, "restarted dwell completes");

    auto c = defaults();
    for (auto &b : c.buttons) b.dwell_ms = 0;
    fid::Control all(c); arm(all);
    frame = neutral(); frame.left_click = frame.right_click = frame.delete_key = frame.insert_key = 1;
    all.submit(frame, 0.01);
    auto events = all.tick(0.01);
    require(events.size() == 4, "four independent actions");
    require(count(events, FID_EVENT_RIGHT_CLICK) == 1, "right click emitted");
    require(count(events, FID_EVENT_DELETE) == 1, "Delete emitted");
    require(count(events, FID_EVENT_INSERT) == 1, "Insert emitted");
}

void lifecycle() {
    fid::Control core(defaults());
    auto frame = neutral(); frame.pointer_x = 1; frame.left_click = 1;
    core.submit(frame, 0);
    require(core.tick(0.01).empty(), "startup paused");
    core.enable(0.02);
    require(core.tick(0.03).empty(), "enable discards old frames");
    core.submit(frame, 0.04);
    require(core.tick(0.04).empty() && core.awaiting_neutral(), "held buttons block arming");
    core.submit(neutral(), 0.05);
    require(core.tick(0.05).empty(), "fresh neutral arms without events");
    require(core.tick(0.30).empty() && !core.enabled() && core.timed_out(), "stale input stops output");
    core.submit(frame, 0.31);
    require(core.tick(0.31).empty(), "fresh input does not automatically resume");
    core.enable(0.32);
    require(!core.timed_out(), "explicit enabling clears timeout");
    core.submit(frame, 0.33);
    require(core.tick(0.33).empty(), "resume requires neutral buttons again");
    core.submit(neutral(), 0.34); core.tick(0.34);
    frame.left_click = 0; core.submit(frame, 0.35);
    require(count(core.tick(0.35), FID_EVENT_MOVE) == 1, "movement resumes after arming");
    core.pause();
    require(core.tick(0.36).empty(), "pause stops movement immediately");

    fid::Control no_frame(defaults()); no_frame.enable(0);
    require(no_frame.tick(0.25).empty() && no_frame.timed_out(), "no frames also time out");

    fid::Control late(defaults()); arm(late);
    late.submit(frame, 0.26);
    require(late.timed_out() && !late.enabled(), "late frame cannot erase expired watchdog before worker tick");
    require(late.tick(0.27).empty(), "late submission remains paused");
}

int simulated_motion(int producer_hz) {
    fid::Control core(defaults()); arm(core);
    auto frame = neutral(); frame.pointer_x = 0.73;
    core.submit(frame, 0);
    int sum = 0;
    const int interval = 60 / producer_hz;
    for (int tick = 1; tick <= 120; ++tick) {
        double now = tick / 60.0;
        if (tick % interval == 0) core.submit(frame, now);
        for (const auto &event : core.tick(now)) if (event.type == FID_EVENT_MOVE) sum += event.x;
    }
    return sum;
}

void motion_and_scroll() {
    require(std::abs(simulated_motion(30) - simulated_motion(60)) <= 1, "30/60 Hz producers preserve speed");
    require(std::abs(simulated_motion(60) - 480) <= 1, "elapsed time determines distance");
    fid::Control core(defaults()); arm(core);
    auto frame = neutral(); frame.pointer_x = 0; frame.pointer_y = 1; frame.scroll = 1;
    core.submit(frame, 0.1);
    auto events = core.tick(0.1);
    require(events.size() == 2, "move and scroll emitted");
    require(events[0].x == -60 && events[0].y == 60, "both pointer directions");
    require(events[1].type == FID_EVENT_SCROLL && events[1].y == 1, "positive scroll means down");
    frame.scroll = 0; frame.pointer_x = frame.pointer_y = 0.5;
    core.submit(frame, 0.2);
    events = core.tick(0.2);
    require(events.size() == 1 && events[0].y == -1, "negative scroll means up");
    core.submit(neutral(), 0.21);
    require(core.tick(0.21).empty(), "neutral stops movement including fractional leftovers");

    auto c = defaults(); c.stale_timeout_ms = 1000;
    fid::Control stalled(c); arm(stalled);
    frame = neutral(); frame.pointer_x = 1;
    stalled.submit(frame, 0.5);
    events = stalled.tick(0.5);
    require(events.size() == 1 && events[0].x == 60, "stall caps integration to 100 ms");
    c = defaults(); c.pointer_x.max_speed = 30;
    fid::Control fractional(c); arm(fractional);
    frame = neutral(); frame.pointer_x = 1;
    int total = 0;
    for (int i = 1; i <= 60; ++i) {
        const double now = i / 60.0;
        fractional.submit(frame, now);
        for (const auto &e : fractional.tick(now)) total += e.x;
    }
    require(std::abs(total - 30) <= 1, "sub-unit motion accumulates");
}
} // namespace

int main() {
    validation_and_axes();
    buttons_and_hysteresis();
    lifecycle();
    motion_and_scroll();
    std::cout << checks << " control checks passed\n";
}
