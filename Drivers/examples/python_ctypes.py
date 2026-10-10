#!/usr/bin/env python3
"""Minimal C ABI integration. Defaults to dry-run; --native enables OS input."""
import argparse
import ctypes as ct
import math
import platform
import shlex
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
import time


class Axis(ct.Structure):
    _fields_ = [("neutral", ct.c_double), ("dead_zone", ct.c_double),
                ("max_speed", ct.c_double), ("inverted", ct.c_uint32)]


class Button(ct.Structure):
    _fields_ = [("activation_threshold", ct.c_double), ("release_threshold", ct.c_double),
                ("dwell_ms", ct.c_uint32)]


class Config(ct.Structure):
    _fields_ = [("abi_version", ct.c_uint32), ("backend", ct.c_uint32),
                ("tick_hz", ct.c_uint32), ("stale_timeout_ms", ct.c_uint32),
                ("pointer_x", Axis), ("pointer_y", Axis), ("scroll", Axis), ("buttons", Button * 4)]


class Frame(ct.Structure):
    _fields_ = [(name, ct.c_double) for name in
                ("pointer_x", "pointer_y", "scroll", "left_click", "right_click", "delete_key", "insert_key")]


class Status(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in
                ("enabled", "awaiting_neutral", "timed_out", "last_error", "capabilities", "backend")] + [
                (name, ct.c_uint64) for name in
                ("accepted_frames", "rejected_frames", "emitted_events", "dropped_log_events")]


class Event(ct.Structure):
    _fields_ = [("type", ct.c_uint32), ("x", ct.c_int32), ("y", ct.c_int32), ("monotonic_us", ct.c_uint64)]


def load_driver(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise DriverError(
            f"Shared library not found: {path}\n"
            "From Drivers/, build it with:\n"
            "  cmake -S . -B build\n  cmake --build build -j 4\n"
            "For another build directory, pass --library /absolute/path/to/library."
        )
    try:
        lib = ct.CDLL(str(path))
    except OSError as error:
        raise DriverError(
            f"Could not load {path}: {error}\n"
            "Rebuild on this OS with the same architecture as Python. See testing/README.md."
        ) from error
    signatures = {
        "fid_default_config": ([ct.POINTER(Config)], None),
        "fid_neutral_frame": ([ct.POINTER(Frame)], None),
        "fid_create": ([ct.POINTER(Config), ct.POINTER(ct.c_void_p)], ct.c_int),
        "fid_submit": ([ct.c_void_p, ct.POINTER(Frame)], ct.c_int),
        "fid_enable": ([ct.c_void_p], ct.c_int),
        "fid_pause": ([ct.c_void_p], ct.c_int),
        "fid_get_status": ([ct.c_void_p, ct.POINTER(Status)], ct.c_int),
        "fid_drain_events": ([ct.c_void_p, ct.POINTER(Event), ct.c_size_t, ct.POINTER(ct.c_size_t)], ct.c_int),
        "fid_destroy": ([ct.c_void_p], None),
        "fid_result_string": ([ct.c_int], ct.c_char_p),
    }
    for name, (args, result) in signatures.items():
        try:
            function = getattr(lib, name)
        except AttributeError as error:
            raise DriverError(
                f"The library is missing {name}. Rebuild this driver or correct --library."
            ) from error
        function.argtypes, function.restype = args, result
    return lib


class DriverError(RuntimeError):
    """An expected setup/output failure suitable for a teammate-facing message."""


def error_message(lib, code, system=None):
    system = system or platform.system()
    detail = lib.fid_result_string(code).decode()
    if not code:
        return "no driver error"
    if code == 3 and system == "Linux":
        return (f"{detail}. Your account needs read/write access to /dev/uinput.\n"
                "Check: ls -l /dev/uinput and getfacl /dev/uinput.\n"
                "See testing/README.md for account-specific permissions; run the tester without sudo.")
    if code == 3 and system == "Darwin":
        return (f"{detail}. Enable Accessibility access in System Settings > Privacy & Security\n"
                "> Accessibility for the Python host (and launcher if required), then relaunch.\n"
                "See testing/README.md for macOS setup.")
    if code == 4 and system == "Linux":
        return (f"{detail}. The host must expose /dev/uinput.\n"
                "An administrator can load it with sudo modprobe uinput; containers need host device access.\n"
                "Use dry-run without --native until the device is available.")
    if code == 2:
        return (f"{detail}. For live output, build the native backend on Linux or macOS.\n"
                "From Drivers/: cmake -S . -B build -DFID_NATIVE_BACKEND=ON\n"
                "Then: cmake --build build -j 4")
    return f"{detail}. Output remains paused after a failed trial; check status and testing/README.md."


HELP = """Commands (axis values are normalized between 0 and 1):
  move X Y        Example: move 0.65 0.5 (right); 0.5 0.5 is neutral
  scroll VALUE    Example: scroll 0.8 (down); scroll 0.2 (up)
  click left      One left click; click right for a right click
  key delete      One forward Delete; key insert for Insert (limited on macOS)
  status          Mode, trial state, output state, counters, and capabilities
  stop            Cancel the current trial/focus delay and pause output
  help            Show these commands
  quit            Stop output and exit (Ctrl-C also exits)
Advanced: frame X Y SCROLL LEFT RIGHT DELETE INSERT, or seven bare numbers.
Each trial runs for the configured duration, then pauses; trials are not queued."""


@dataclass
class Command:
    name: str
    label: str = ""
    frame: object = None


def parse_command(line):
    try:
        parts = shlex.split(line, comments=True)
    except ValueError as error:
        raise ValueError("Unclosed quote. Type help for examples.") from error
    if not parts:
        return Command("empty")
    name = parts[0].lower()
    if name in ("q", "exit"):
        name = "quit"
    if name in ("help", "status", "stop", "quit"):
        if len(parts) != 1:
            raise ValueError(f"Usage: {name}")
        return Command(name)

    def number(value):
        try:
            value = float(value)
        except ValueError as error:
            raise ValueError("Axis/frame values must be numbers between 0 and 1.") from error
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Axis/frame values must be finite and between 0 and 1.")
        return value

    frame = Frame(0.5, 0.5, 0.5, 0, 0, 0, 0)
    if name == "move":
        if len(parts) != 3:
            raise ValueError("Usage: move X Y (example: move 0.65 0.5)")
        frame.pointer_x, frame.pointer_y = map(number, parts[1:])
        label = f"Move (X={frame.pointer_x:g}, Y={frame.pointer_y:g})"
    elif name == "scroll":
        if len(parts) != 2:
            raise ValueError("Usage: scroll VALUE (example: scroll 0.8)")
        frame.scroll = number(parts[1])
        label = f"Scroll (value={frame.scroll:g})"
    elif name == "click":
        if len(parts) != 2 or parts[1].lower() not in ("left", "right"):
            raise ValueError("Usage: click left or click right")
        side = parts[1].lower()
        setattr(frame, f"{side}_click", 1)
        label = f"{side.capitalize()} click"
    elif name == "key":
        if len(parts) != 2 or parts[1].lower() not in ("delete", "insert"):
            raise ValueError("Usage: key delete or key insert")
        key = parts[1].lower()
        setattr(frame, f"{key}_key", 1)
        label = "Forward Delete" if key == "delete" else "Insert"
    else:
        values = parts[1:] if name == "frame" else parts
        if name != "frame" and len(parts) != 7:
            raise ValueError("Unknown command. Type help for commands and examples.")
        if len(values) != 7:
            raise ValueError("Usage: frame X Y SCROLL LEFT RIGHT DELETE INSERT (seven numbers)")
        frame = Frame(*map(number, values))
        label = "Custom frame"
    return Command("trial", label, frame)


def capability_names(bits):
    names = [label for bit, label in ((1, "pointer"), (2, "scroll"), (4, "left click"),
             (8, "right click"), (16, "forward Delete"), (32, "Insert")) if bits & bit]
    if bits & 64:
        names = ["Insert (limited: Help/Insert-position key)" if n == "Insert" else n for n in names]
    return ", ".join(names) or "none"


def summarize(totals):
    results = []
    for axis, positive, negative in (("dx", "right", "left"), ("dy", "down", "up")):
        value = totals[axis]
        if value:
            results.append(f"pointer {positive if value > 0 else negative}: {abs(value)} units")
    if totals["scroll"]:
        value = totals["scroll"]
        results.append(f"scroll {'down' if value > 0 else 'up'}: {abs(value)} detents")
    for kind, label in ((3, "left click"), (4, "right click"), (5, "forward Delete"), (6, "Insert")):
        if totals["counts"].get(kind):
            results.append(f"{label}: {totals['counts'][kind]}")
    return "; ".join(results) or "no actions emitted (neutral/dead-zone input)"


class TestSession:
    """Background finite trials. Stop/join before destroying the C handle."""
    def __init__(self, lib, handle, check, args, output=print):
        self.lib, self.handle, self.check, self.args = lib, handle, check, args
        self.output = output
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread = None
        self.phase = "paused"
        self.last_error = "none"
        self.last_totals = None

    def status_text(self):
        with self.lock:
            status = Status()
            self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
            mode = "LIVE OS INPUT" if self.args.native else "DRY-RUN (no OS input)"
            error = self.lib.fid_result_string(status.last_error).decode()
            return (f"Mode: {mode} | Trial: {self.phase} | Output: {'enabled' if status.enabled else 'paused'}\n"
                    f"Capabilities: {capability_names(status.capabilities)}\n"
                    f"Accepted frames: {status.accepted_frames} | Rejected frames: {status.rejected_frames} | "
                    f"Emitted actions: {status.emitted_events}\n"
                    f"Awaiting neutral: {'yes' if status.awaiting_neutral else 'no'} | "
                    f"Timed out: {'yes' if status.timed_out else 'no'} | Driver error: {error}\n"
                    f"Last trial error: {self.last_error}")

    def start(self, command):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.output("A trial is already running. Use stop before starting another.")
                return False
            self.cancel = threading.Event()
            self.last_error = "none"
            self.last_totals = None
            self.phase = "focus delay" if self.args.native and self.args.delay else "arming"
            self.output(f"Trial: {command.label}. Duration: {self.args.duration:g} seconds.")
            if self.args.native and self.args.delay:
                self.output(f"Focus your target app; starting in {self.args.delay:g} seconds. stop cancels.")
            self.thread = threading.Thread(target=self._run, args=(command,), name="manual-input-trial")
            self.thread.start()
            return True

    def _collect(self, totals):
        events, count = (Event * 128)(), ct.c_size_t()
        self.check(self.lib.fid_drain_events(self.handle, events, 128, ct.byref(count)))
        for event in events[:count.value]:
            totals["counts"][event.type] = totals["counts"].get(event.type, 0) + 1
            if event.type == 1:
                totals["dx"] += event.x
                totals["dy"] += event.y
            elif event.type == 2:
                totals["scroll"] += event.y

    def _send(self, frame, seconds, totals):
        finish = time.monotonic() + seconds
        next_frame = time.monotonic()
        while time.monotonic() < finish:
            with self.lock:
                if self.cancel.is_set():
                    return False
                self.check(self.lib.fid_submit(self.handle, ct.byref(frame)))
                status = Status()
                self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
                if not status.enabled:
                    reason = "input watchdog timed out" if status.timed_out else "driver paused"
                    detail = error_message(self.lib, status.last_error) if status.last_error else reason
                    raise DriverError(f"Output stopped: {detail}")
                self._collect(totals)
            next_frame += 1 / self.args.rate
            current = time.monotonic()
            if next_frame < current:
                next_frame = current + 1 / self.args.rate
            if self.cancel.wait(max(0, next_frame - current)):
                return False
        return True

    def _run(self, command):
        totals = {"counts": {}, "dx": 0, "dy": 0, "scroll": 0}
        error = None
        try:
            if self.args.native and self.cancel.wait(self.args.delay):
                return
            with self.lock:
                if self.cancel.is_set():
                    return
                self.check(self.lib.fid_enable(self.handle))
                self.phase = "arming"
            neutral = Frame()
            self.lib.fid_neutral_frame(ct.byref(neutral))
            if not self._send(neutral, 0.2, totals):
                return
            with self.lock:
                if self.cancel.is_set():
                    return
                status = Status()
                self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
                if status.awaiting_neutral:
                    raise DriverError("Worker has not armed; try again when the host is less busy.")
                self.phase = "running"
            if not self._send(command.frame, self.args.duration, totals):
                return
            with self.lock:
                self.phase = "settling"
            self._send(neutral, 0.1, totals)
        except DriverError as caught:
            error = str(caught)
        except Exception as caught:
            error = f"Tester failed: {caught}"
        finally:
            with self.lock:
                code = self.lib.fid_pause(self.handle)
                if code:
                    error = (error + "\n" if error else "") + error_message(self.lib, code)
                # Drain any final successful action before reporting, without
                # letting a diagnostic failure prevent cleanup.
                try:
                    self._collect(totals)
                except DriverError as caught:
                    error = (error + "\n" if error else "") + str(caught)
                self.phase = "paused"
                self.last_totals = totals
                self.last_error = error or "none"
                if error:
                    self.output(f"\nTrial failed: {error}\nOutput paused. Use status for details.")
                elif not self.cancel.is_set():
                    self.output(f"\nFinished: {command.label} — {summarize(totals)}. Output paused.")

    def stop(self, quiet=False):
        with self.lock:
            self.cancel.set()
            code = self.lib.fid_pause(self.handle)
            thread = self.thread
        # Never destroy a handle while the producer can still call the C ABI.
        if thread:
            thread.join()
        self.check(code)
        if not quiet:
            self.output("Stopped. Output paused; no trial is queued.")


def interactive(lib, handle, check, args):
    def show_message(text):
        print(text, flush=True)
        if threading.current_thread() is not threading.main_thread() and sys.stdin.isatty():
            print("test> ", end="", flush=True)

    session = TestSession(lib, handle, check, args, output=show_message)
    print(session.status_text())
    print("Try move 0.65 0.5, scroll 0.8, click left, or key delete. Type help for all commands.")
    print("Each trial pauses automatically. stop cancels a trial; quit or Ctrl-C exits.")
    try:
        while True:
            try:
                command = parse_command(input("test> "))
            except EOFError:
                return
            except ValueError as error:
                print(f"Input error: {error}")
                continue
            if command.name == "empty":
                continue
            if command.name == "quit":
                return
            if command.name == "help":
                print(HELP)
            elif command.name == "status":
                print(session.status_text())
            elif command.name == "stop":
                session.stop()
            else:
                session.start(command)
    finally:
        session.stop(quiet=True)


def main():
    suffix = "dylib" if platform.system() == "Darwin" else "so"
    default = Path(__file__).resolve().parents[1] / "build" / f"libface_input_driver.{suffix}"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=default)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--rate", type=int, choices=(30, 60), default=60)
    parser.add_argument("--interactive", action="store_true", help="Named commands for finite manual trials")
    parser.add_argument("--probe", action="store_true", help="Check backend setup while paused; emit no actions")
    parser.add_argument("--duration", type=float, default=1.0, help="Interactive trial duration in seconds (0.2–10)")
    parser.add_argument("--delay", type=float, default=3.0, help="Native interactive delay to focus a target app (0–30 seconds)")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 0.2 <= args.duration <= 10:
        parser.error("--duration must be between 0.2 and 10 seconds")
    if not math.isfinite(args.delay) or not 0 <= args.delay <= 30:
        parser.error("--delay must be between 0 and 30 seconds")
    if args.interactive and args.probe:
        parser.error("Choose either --interactive or --probe")
    lib = load_driver(args.library)

    def check(code):
        if code:
            raise DriverError(error_message(lib, code))

    config = Config()
    lib.fid_default_config(ct.byref(config))
    config.backend = int(args.native)
    handle = ct.c_void_p()
    check(lib.fid_create(ct.byref(config), ct.byref(handle)))
    try:
        if args.probe:
            print(TestSession(lib, handle, check, args).status_text())
            return
        if args.interactive:
            interactive(lib, handle, check, args)
            return
        if args.native:
            print("Native pointer movement starts in 3 seconds. Ctrl-C stops.")
            time.sleep(3)
        check(lib.fid_enable(handle))
        frame, status = Frame(), Status()
        events, count = (Event * 128)(), ct.c_size_t()
        start = time.monotonic()
        next_frame = start
        # Replace frame construction below with your processing output.
        while time.monotonic() - start < 2:
            elapsed = time.monotonic() - start
            lib.fid_neutral_frame(ct.byref(frame))
            if 0.2 < elapsed < 1.2:
                frame.pointer_x = 0.65
            check(lib.fid_submit(handle, ct.byref(frame)))
            check(lib.fid_get_status(handle, ct.byref(status)))
            if not status.enabled:
                raise DriverError(f"Output stopped: timeout={status.timed_out}; " + error_message(lib, status.last_error))
            check(lib.fid_drain_events(handle, events, 128, ct.byref(count)))
            for event in events[:count.value]:
                print(event.monotonic_us, event.type, event.x, event.y)
            next_frame += 1 / args.rate
            current = time.monotonic()
            if next_frame < current:
                next_frame = current + 1 / args.rate
            time.sleep(max(0, next_frame - current))
        check(lib.fid_pause(handle))
        check(lib.fid_get_status(handle, ct.byref(status)))
        print(f"accepted={status.accepted_frames}, emitted={status.emitted_events}")
    finally:
        lib.fid_destroy(handle)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Output paused and driver closed.")
    except DriverError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
