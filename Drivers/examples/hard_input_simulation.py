#!/usr/bin/env python3
"""Run a configurable sequence of held-key and relative-mouse input trials.

Dry-run is the default. Add --native to send the sequence to the focused app.
"""

from __future__ import annotations

import argparse
import ctypes as ct
import platform
import sys
import time
from pathlib import Path

import python_ctypes as driver_api


KEY_W = 1 << 0
KEY_SPACE = 1 << 4
EVENT_MOVE = 1
EVENT_KEY_DOWN = 7
EVENT_KEY_UP = 8


def parse_args() -> argparse.Namespace:
    suffix = "dylib" if platform.system() == "Darwin" else "so"
    default_library = Path(__file__).resolve().parents[1] / "build" / f"libface_input_driver.{suffix}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=default_library,
                        help="ABI v3 library (default: Drivers/build)")
    parser.add_argument("--native", action="store_true",
                        help="send live input to the focused desktop app")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="seconds to focus the target app before input (default: 5)")
    parser.add_argument("--rate", type=int, choices=(30, 60), default=60,
                        help="frame submission rate (default: 60 Hz)")
    parser.add_argument("--w-frames", type=int, default=180,
                        help="consecutive W-down frames (default: 180, about 3 seconds at 60 Hz)")
    parser.add_argument("--spin-seconds", type=float, default=1.0,
                        help="duration of each mouse-velocity direction (default: 1)")
    parser.add_argument("--space-tap-seconds", type=float, default=0.2,
                        help="Space tap duration (default: 0.2)")
    parser.add_argument("--space-hold-seconds", type=float, default=3.0,
                        help="Space hold duration after the tap (default: 3)")
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error("--delay must be between 0 and 60 seconds")
    if not 1 <= args.w_frames <= 3600:
        parser.error("--w-frames must be between 1 and 3600")
    for name in ("spin_seconds", "space_tap_seconds", "space_hold_seconds"):
        if not 0 < getattr(args, name) <= 60:
            parser.error(f"--{name.replace('_', '-')} must be greater than 0 and at most 60 seconds")
    return args


def check_result(lib, code: int) -> None:
    if code:
        raise driver_api.DriverError(driver_api.error_message(lib, code))


def wait_for_focus(delay: float) -> None:
    print(f"Focus the target app now. Input starts in {delay:g} seconds.", flush=True)
    finish = time.monotonic() + delay
    while time.monotonic() < finish:
        remaining = int(finish - time.monotonic() + 0.999)
        print(f"  {remaining}...", flush=True)
        time.sleep(min(1.0, max(0.0, finish - time.monotonic())))


def submit(lib, handle, frame) -> None:
    check_result(lib, lib.fid_submit(handle, ct.byref(frame)))


def neutral_frame(lib):
    frame = driver_api.Frame()
    lib.fid_neutral_frame(ct.byref(frame))
    return frame


def collect_events(lib, handle, totals: dict[str, int]) -> None:
    events = (driver_api.Event * 64)()
    count = ct.c_size_t()
    check_result(lib, lib.fid_drain_events(handle, events, len(events), ct.byref(count)))
    for event in events[:count.value]:
        if event.type == EVENT_MOVE:
            totals["dx"] += event.x
            totals["dy"] += event.y
        elif event.type == EVENT_KEY_DOWN:
            if event.x == KEY_W:
                totals["w_down"] += 1
            elif event.x == KEY_SPACE:
                totals["space_down"] += 1
        elif event.type == EVENT_KEY_UP:
            if event.x == KEY_W:
                totals["w_up"] += 1
            elif event.x == KEY_SPACE:
                totals["space_up"] += 1


def run_frames(lib, handle, frame, count: int, rate: int,
               totals: dict[str, int], label: str) -> None:
    print(f"{label} ({count} frames at {rate} Hz)...", flush=True)
    interval = 1.0 / rate
    next_frame = time.monotonic()
    status = driver_api.Status()
    for _ in range(count):
        submit(lib, handle, frame)
        check_result(lib, lib.fid_get_status(handle, ct.byref(status)))
        if not status.enabled:
            raise driver_api.DriverError("Driver paused during the input sequence")
        collect_events(lib, handle, totals)
        next_frame += interval
        now = time.monotonic()
        if next_frame < now:
            next_frame = now
        time.sleep(max(0.0, next_frame - now))


def run_segment(lib, handle, frame, seconds: float, args, totals, label: str) -> None:
    count = max(1, round(seconds * args.rate))
    before_dx, before_dy = totals["dx"], totals["dy"]
    run_frames(lib, handle, frame, count, args.rate, totals, label)
    if frame.pointer_x != 0.5 or frame.pointer_y != 0.5:
        print(f"  observed relative movement: dx={totals['dx'] - before_dx}, "
              f"dy={totals['dy'] - before_dy} units", flush=True)


def release(lib, handle, neutral, args, totals) -> None:
    # Refresh neutral state long enough for the worker to emit key-up transitions.
    run_frames(lib, handle, neutral, max(4, round(0.1 * args.rate)),
               args.rate, totals, "Release / neutral")


def run(lib, handle, args) -> dict[str, int]:
    wait_for_focus(args.delay)
    check_result(lib, lib.fid_enable(handle))
    neutral = neutral_frame(lib)
    totals = {"dx": 0, "dy": 0, "w_down": 0, "w_up": 0,
              "space_down": 0, "space_up": 0}

    # Arm the driver on a neutral frame before any active input is sent.
    submit(lib, handle, neutral)
    status = driver_api.Status()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        check_result(lib, lib.fid_get_status(handle, ct.byref(status)))
        if not status.awaiting_neutral:
            break
        time.sleep(0.005)
    if status.awaiting_neutral:
        raise driver_api.DriverError("Driver did not arm on the neutral frame")

    held_w = neutral_frame(lib)
    held_w.keys_down = KEY_W
    run_frames(lib, handle, held_w, args.w_frames, args.rate, totals, "Hold W")
    release(lib, handle, neutral, args, totals)

    mouse_right = neutral_frame(lib)
    mouse_right.pointer_x = 0.9
    run_segment(lib, handle, mouse_right, args.spin_seconds, args, totals,
                "Move mouse right (velocity 0.9, 0.5)")
    release(lib, handle, neutral, args, totals)

    mouse_left = neutral_frame(lib)
    mouse_left.pointer_x = 0.1
    run_segment(lib, handle, mouse_left, args.spin_seconds, args, totals,
                "Move mouse left (velocity 0.1, 0.5)")
    release(lib, handle, neutral, args, totals)

    space = neutral_frame(lib)
    space.keys_down = KEY_SPACE
    run_segment(lib, handle, space, args.space_tap_seconds, args, totals,
                "Tap Space")
    release(lib, handle, neutral, args, totals)

    run_segment(lib, handle, space, args.space_hold_seconds, args, totals,
                "Hold Space")
    release(lib, handle, neutral, args, totals)

    if (totals["w_down"], totals["w_up"]) != (1, 1):
        raise driver_api.DriverError(
            f"Expected one W down/up transition; got {totals['w_down']}/{totals['w_up']}")
    if (totals["space_down"], totals["space_up"]) != (2, 2):
        raise driver_api.DriverError(
            "Expected two Space down/up pairs (tap and hold); "
            f"got down={totals['space_down']} up={totals['space_up']}")
    return totals


def main() -> int:
    args = parse_args()
    mode = "LIVE OS INPUT" if args.native else "DRY-RUN (no OS input)"
    print(f"Mode: {mode}; rate: {args.rate} Hz. Ctrl-C pauses and releases output.", flush=True)
    lib = driver_api.load_driver(args.library)
    config = driver_api.Config()
    lib.fid_default_config(ct.byref(config))
    if config.abi_version != 3:
        raise driver_api.DriverError(
            f"Expected Driver ABI v3, found v{config.abi_version}; rebuild the library")
    config.backend = int(args.native)
    handle = ct.c_void_p()
    check_result(lib, lib.fid_create(ct.byref(config), ct.byref(handle)))
    try:
        totals = run(lib, handle, args)
        print("Sequence complete; output released.", flush=True)
        print(f"Events: W down/up={totals['w_down']}/{totals['w_up']}; "
              f"Space down/up={totals['space_down']}/{totals['space_up']}; "
              f"relative mouse dx/dy={totals['dx']}/{totals['dy']} units", flush=True)
        return 0
    finally:
        lib.fid_pause(handle)
        lib.fid_destroy(handle)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted; output paused and held keys released.", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except driver_api.DriverError as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
