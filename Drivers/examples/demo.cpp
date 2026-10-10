#include "face_input_driver.h"
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>

namespace {
volatile std::sig_atomic_t interrupted = 0;
void interrupt(int) { interrupted = 1; }
using Driver = std::unique_ptr<fid_driver, decltype(&fid_destroy)>;
bool check(fid_result result) {
    if (result == FID_OK) return true;
    std::cerr << fid_result_string(result) << '\n';
    return false;
}
void print_events(fid_driver *driver) {
    fid_event events[128];
    size_t count = 0;
    if (!check(fid_drain_events(driver, events, 128, &count))) return;
    const char *names[] = {"unknown", "move", "scroll", "left_click", "right_click", "delete", "insert"};
    for (size_t i = 0; i < count; ++i)
        std::cout << events[i].monotonic_us << ' ' << names[events[i].type]
                  << ' ' << events[i].x << ' ' << events[i].y << '\n';
}
bool send_for(fid_driver *driver, const fid_frame &frame, int milliseconds, int hz) {
    using Clock = std::chrono::steady_clock;
    const auto end = Clock::now() + std::chrono::milliseconds(milliseconds);
    const auto step = std::chrono::microseconds(1000000 / hz);
    auto next = Clock::now();
    while (!interrupted && Clock::now() < end) {
        if (!check(fid_submit(driver, &frame))) return false;
        print_events(driver);
        fid_status status{};
        if (!check(fid_get_status(driver, &status))) return false;
        if (!status.enabled) {
            std::cerr << "Output stopped: timeout=" << status.timed_out
                      << ", error=" << fid_result_string(static_cast<fid_result>(status.last_error)) << '\n';
            return false;
        }
        next += step;
        if (next < Clock::now()) next = Clock::now() + step;
        std::this_thread::sleep_until(next);
    }
    return !interrupted;
}
} // namespace

int main(int argc, char **argv) {
    bool native = false, probe = false, from_stdin = false;
    int hz = 60;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--native") native = true;
        else if (arg == "--probe") probe = true;
        else if (arg == "--stdin") from_stdin = true;
        else if (arg == "--rate" && i + 1 < argc) {
            const std::string rate = argv[++i];
            if (rate != "30" && rate != "60") {
                std::cerr << "Producer rate must be 30 or 60 Hz\n"; return 2;
            }
            hz = std::stoi(rate);
        } else {
            std::cerr << "Usage: driver_demo [--native] [--probe] [--stdin] [--rate 30|60]\n";
            return arg == "--help" ? 0 : 2;
        }
    }
    fid_config config{};
    fid_default_config(&config);
    config.backend = native ? FID_NATIVE : FID_DRY_RUN;
    fid_driver *raw = nullptr;
    if (!check(fid_create(&config, &raw))) {
        if (native) std::cerr << "See readme.MD in the Drivers directory for OS permission/device setup.\n";
        return 1;
    }
    Driver driver(raw, fid_destroy);
    fid_status status{};
    if (!check(fid_get_status(driver.get(), &status))) return 1;
    std::cout << (native ? "native" : "dry-run") << " capabilities=" << status.capabilities
              << " paused=" << !status.enabled << '\n';
    if (probe) return 0;
    std::signal(SIGINT, interrupt);
    std::signal(SIGTERM, interrupt);
    if (native && !from_stdin) {
        std::cerr << "Live demo moves/clicks the pointer and sends Delete/Insert to the focused app.\n"
                     "Focus a disposable text document; starting in 3 seconds. Ctrl-C stops.\n";
        for (int i = 0; i < 30 && !interrupted; ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if (interrupted) return 130;
    if (!check(fid_enable(driver.get()))) return 1;
    bool ok = true;
    if (from_stdin) {
        // Current frames, not one-shot commands. Stream continuously at 30–60 Hz.
        std::string line;
        while (!interrupted && std::getline(std::cin, line)) {
            std::istringstream input(line);
            fid_frame frame{};
            std::string extra;
            if (!(input >> frame.pointer_x >> frame.pointer_y >> frame.scroll >> frame.left_click
                        >> frame.right_click >> frame.delete_key >> frame.insert_key) || input >> extra) {
                std::cerr << "Expected exactly seven numeric fields\n";
                ok = false; break;
            }
            if (!check(fid_submit(driver.get(), &frame))) { ok = false; break; }
            print_events(driver.get());
            if (!check(fid_get_status(driver.get(), &status))) { ok = false; break; }
            if (!status.enabled) {
                std::cerr << "Output paused/timed out; restart and stream fresh neutral frames first.\n";
                ok = false; break;
            }
        }
    } else {
        fid_frame frame{};
        fid_neutral_frame(&frame);
        ok = send_for(driver.get(), frame, 200, hz);
        frame.pointer_x = 0.65;
        if (ok) ok = send_for(driver.get(), frame, 800, hz);
        fid_neutral_frame(&frame);
        frame.scroll = 0.85;
        if (ok) ok = send_for(driver.get(), frame, 800, hz);
        for (int button = 0; button < 4 && ok; ++button) {
            fid_neutral_frame(&frame);
            ok = send_for(driver.get(), frame, 200, hz);
            double *buttons[] = {&frame.left_click, &frame.right_click, &frame.delete_key, &frame.insert_key};
            *buttons[button] = 1;
            if (ok) ok = send_for(driver.get(), frame, 350, hz);
        }
        fid_neutral_frame(&frame);
        if (ok) ok = send_for(driver.get(), frame, 200, hz);
    }
    if (!check(fid_pause(driver.get()))) ok = false;
    print_events(driver.get());
    if (!check(fid_get_status(driver.get(), &status))) ok = false;
    std::cout << "accepted=" << status.accepted_frames << " rejected=" << status.rejected_frames
              << " emitted=" << status.emitted_events << " dropped_log=" << status.dropped_log_events << '\n';
    return interrupted ? 130 : (ok ? 0 : 1);
}
