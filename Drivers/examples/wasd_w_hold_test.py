#!/usr/bin/env python3
"""Send W-down for 180 consecutive frames through the Driver C ABI v3.

Dry-run is the default. Pass --native to send W to the focused desktop app;
focus Roblox during the five-second countdown. The script then sends an
all-released frame and pauses the driver.
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
EVENT_KEY_DOWN = 7
EVENT_KEY_UP = 8


def parse_args() -> argparse.Namespace:
    suffix = "dylib" if platform.system() == "Darwin" else "so"
    default_library = Path(__file__).resolve().parents[1] / "build" / f"libface_input_driver.{suffix}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=default_library,
                        help="ABI v3 library (default: Drivers/build)")
    parser.add_argument("--native", action="store_true",
                        help="send live W key events to the focused desktop app")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="seconds to focus Roblox before sending input (default: 5)")
    parser.add_argument("--frames", type=int, default=180,
                        help="number of consecutive W-down frames (default: 180)")
    parser.add_argument("--rate", type=int, choices=(30, 60), default=60,
                        help="frame submission rate; 180 frames at 60 Hz lasts about 3s (default)")
    args = parser.parse_args()
    if args.delay < 0 or args.delay > 60:
        parser.error("--delay must be between 0 and 60 seconds")
    if args.frames < 1 or args.frames > 600:
        parser.error("--frames must be between 1 and 600")
    return args


def check_result(lib, code: int) -> None:
    if code:
        raise driver_api.DriverError(driver_api.error_message(lib, code))


def wait_for_focus(delay: float) -> None:
    print(f"Focus the Roblox game window now. W will be sent in {delay:g} seconds.", flush=True)
    finish = time.monotonic() + delay
    while time.monotonic() < finish:
        remaining = int(finish - time.monotonic() + 0.999)
        print(f"  {remaining}...", flush=True)
        time.sleep(min(1.0, max(0.0, finish - time.monotonic())))


def submit(lib, handle, frame) -> None:
    check_result(lib, lib.fid_submit(handle, ct.byref(frame)))


def drain_key_events(lib, handle, totals: dict[str, int]) -> None:
    events = (driver_api.Event * 64)()
    count = ct.c_size_t()
    check_result(lib, lib.fid_drain_events(handle, events, len(events), ct.byref(count)))
    for event in events[:count.value]:
        if event.type == EVENT_KEY_DOWN and event.x == KEY_W:
            totals["down"] += 1
        elif event.type == EVENT_KEY_UP and event.x == KEY_W:
            totals["up"] += 1


def run(lib, handle, args) -> dict[str, int]:
    wait_for_focus(args.delay)
    check_result(lib, lib.fid_enable(handle))

    neutral = driver_api.Frame()
    lib.fid_neutral_frame(ct.byref(neutral))
    # Arm with a freshly submitted all-neutral frame before key output begins.
    submit(lib, handle, neutral)
    deadline = time.monotonic() + 1.0
    status = driver_api.Status()
    while time.monotonic() < deadline:
        check_result(lib, lib.fid_get_status(handle, ct.byref(status)))
        if not status.awaiting_neutral:
            break
        time.sleep(0.005)
    if status.awaiting_neutral:
        raise driver_api.DriverError("Driver did not arm on the neutral frame")

    held = driver_api.Frame()
    lib.fid_neutral_frame(ct.byref(held))
    held.keys_down = KEY_W
    totals = {"down": 0, "up": 0}
    print(f"Sending W-down for {args.frames} frames at {args.rate} Hz...", flush=True)
    next_frame = time.monotonic()
    for _ in range(args.frames):
        submit(lib, handle, held)
        check_result(lib, lib.fid_get_status(handle, ct.byref(status)))
        if not status.enabled:
            raise driver_api.DriverError("Driver paused during W hold")
        drain_key_events(lib, handle, totals)
        next_frame += 1.0 / args.rate
        now = time.monotonic()
        if next_frame < now:
            next_frame = now
        time.sleep(max(0.0, next_frame - now))

    # Clear W explicitly, keep refreshing neutral while the worker emits key-up.
    print(f"{args.frames}-frame hold submitted; releasing W...", flush=True)
    release_deadline = time.monotonic() + 0.5
    while time.monotonic() < release_deadline:
        submit(lib, handle, neutral)
        check_result(lib, lib.fid_get_status(handle, ct.byref(status)))
        drain_key_events(lib, handle, totals)
        if status.held_key_mask == 0 and totals["down"] and totals["up"]:
            break
        time.sleep(1.0 / args.rate)
    if totals["down"] != 1 or totals["up"] != 1:
        raise driver_api.DriverError(
            f"Expected one W-down and one W-up transition; got down={totals['down']}, up={totals['up']}"
        )
    return totals


def main() -> int:
    args = parse_args()
    mode = "LIVE OS INPUT" if args.native else "DRY-RUN (no OS input)"
    print(f"Mode: {mode}. W is held for {args.frames} frames; Ctrl-C stops and releases it.", flush=True)
    lib = driver_api.load_driver(args.library)
    config = driver_api.Config()
    lib.fid_default_config(ct.byref(config))
    if config.abi_version != 3:
        raise driver_api.DriverError(f"Expected Driver ABI v3, found v{config.abi_version}; rebuild the library")
    config.backend = int(args.native)
    handle = ct.c_void_p()
    check_result(lib, lib.fid_create(ct.byref(config), ct.byref(handle)))
    try:
        totals = run(lib, handle, args)
        print(f"Driver emitted W-down={totals['down']} and W-up={totals['up']}. Output is released.", flush=True)
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
