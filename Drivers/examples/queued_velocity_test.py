#!/usr/bin/env python3
"""Queue timed velocity phases through the Driver C ABI v3.

Dry-run is the default. Pass --native to move the real pointer. This test never
clicks or types; Ctrl-C pauses and closes the Driver.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import platform
import sys
import time
from pathlib import Path

import python_ctypes as driver_api


@dataclass(frozen=True)
class MotionStep:
    name: str
    x: float
    y: float
    seconds: float


def parse_args() -> argparse.Namespace:
    suffix = "dylib" if platform.system() == "Darwin" else "so"
    default_library = Path(__file__).resolve().parents[1] / "build" / f"libface_input_driver.{suffix}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=default_library,
                        help="ABI v3 library (default: Drivers/build)")
    parser.add_argument("--native", action="store_true",
                        help="allow real pointer movement; otherwise use dry-run")
    parser.add_argument("--setup-delay", type=int, default=10,
                        help="wait before loading/enabling the library (default: 10s)")
    parser.add_argument("--rate", type=int, choices=(30, 60), default=60,
                        help="velocity frame update rate (default: 60 Hz)")
    parser.add_argument("--corner-seconds", type=float, default=5.0,
                        help="drive to top-left display edge (default: 5s)")
    parser.add_argument("--down-seconds", type=float, default=1.2,
                        help="move down toward middle (default: 1.2s)")
    parser.add_argument("--right-seconds", type=float, default=2.2,
                        help="move right toward middle (default: 2.2s)")
    parser.add_argument("--up-seconds", type=float, default=0.2,
                        help="upward pulse before reversal (default: 0.2s)")
    parser.add_argument("--down-reversal-seconds", type=float, default=0.6,
                        help="downward duration immediately after up (default: 0.6s)")
    args = parser.parse_args()
    if args.setup_delay < 0:
        parser.error("--setup-delay cannot be negative")
    for name in ("corner_seconds", "down_seconds", "right_seconds", "up_seconds",
                 "down_reversal_seconds"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


def make_scenario(args: argparse.Namespace):
    return deque((
        MotionStep("drive to top-left edge", 0.3, 0.3, args.corner_seconds),
        MotionStep("move down toward middle", 0.5, 0.95, args.down_seconds),
        MotionStep("move right toward middle", 0.95, 0.5, args.right_seconds),
        MotionStep("quick move up", 0.5, 0.05, args.up_seconds),
        MotionStep("immediate reversal: move down", 0.5, 0.95, args.down_reversal_seconds),
    ))


def make_frame(lib, x: float = 0.5, y: float = 0.5):
    frame = driver_api.Frame()
    lib.fid_neutral_frame(driver_api.ct.byref(frame))
    frame.pointer_x = x
    frame.pointer_y = y
    return frame


def submit_for(lib, handle, seconds: float, rate: int, *, x: float = 0.5,
               y: float = 0.5) -> None:
    frame = make_frame(lib, x, y)
    deadline = time.monotonic() + seconds
    next_tick = time.monotonic()
    while time.monotonic() < deadline:
        code = lib.fid_submit(handle, driver_api.ct.byref(frame))
        if code:
            raise driver_api.DriverError(driver_api.error_message(lib, code))
        status = driver_api.Status()
        code = lib.fid_get_status(handle, driver_api.ct.byref(status))
        if code:
            raise driver_api.DriverError(driver_api.error_message(lib, code))
        if not status.enabled:
            why = "input watchdog timed out" if status.timed_out else "driver paused"
            detail = driver_api.error_message(lib, status.last_error) if status.last_error else why
            raise driver_api.DriverError(f"Output stopped: {detail}")
        next_tick += 1 / rate
        now = time.monotonic()
        if next_tick < now:
            # Skip missed updates instead of replaying a stale FIFO backlog.
            next_tick = now + 1 / rate
        time.sleep(max(0, next_tick - now))


def wait_for_setup(seconds: int) -> None:
    print(f"Starting in {seconds}s. Focus the empty browser page and get ready.", flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        remaining = int(deadline - time.monotonic() + 0.999)
        print(f"  {remaining}...", flush=True)
        time.sleep(min(1.0, max(0, deadline - time.monotonic())))


def run(lib, handle, args) -> None:
    print("Arming with neutral input...", flush=True)
    code = lib.fid_enable(handle)
    if code:
        raise driver_api.DriverError(driver_api.error_message(lib, code))
    submit_for(lib, handle, 0.2, args.rate)
    status = driver_api.Status()
    code = lib.fid_get_status(handle, driver_api.ct.byref(status))
    if code:
        raise driver_api.DriverError(driver_api.error_message(lib, code))
    if status.awaiting_neutral:
        raise driver_api.DriverError("Driver did not arm after neutral input")

    for step in make_scenario(args):
        print(f"{step.name}: velocity=({step.x:.2f}, {step.y:.2f}) for {step.seconds:.2f}s",
              flush=True)
        submit_for(lib, handle, step.seconds, args.rate, x=step.x, y=step.y)
    print("Returning to neutral and pausing output...", flush=True)
    submit_for(lib, handle, 0.1, args.rate)


def main() -> int:
    args = parse_args()
    mode = "LIVE POINTER OUTPUT" if args.native else "DRY RUN (no pointer movement)"
    print(f"Mode: {mode}. Ctrl-C stops the run.", flush=True)
    wait_for_setup(args.setup_delay)

    # Deliberately load/create the Driver only after the setup delay.
    lib = driver_api.load_driver(args.library)
    config = driver_api.Config()
    lib.fid_default_config(driver_api.ct.byref(config))
    if config.abi_version != 3:
        raise driver_api.DriverError(f"Expected Driver ABI v3, found v{config.abi_version}")
    config.backend = int(args.native)
    handle = driver_api.ct.c_void_p()
    code = lib.fid_create(driver_api.ct.byref(config), driver_api.ct.byref(handle))
    if code:
        raise driver_api.DriverError(driver_api.error_message(lib, code))
    try:
        run(lib, handle, args)
        return 0
    finally:
        # Pause before destroy even if an exception or Ctrl-C interrupts a phase.
        lib.fid_pause(handle)
        lib.fid_destroy(handle)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted; Driver output paused and closed.", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except driver_api.DriverError as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
