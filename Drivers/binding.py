"""Public ctypes ABI v3 binding shared by App and the standalone console."""

import ctypes as ct
import platform
from pathlib import Path


class Axis(ct.Structure):
    _fields_ = [("neutral", ct.c_double), ("dead_zone", ct.c_double),
                ("max_speed", ct.c_double), ("inverted", ct.c_uint32)]


class Button(ct.Structure):
    _fields_ = [("activation_threshold", ct.c_double), ("release_threshold", ct.c_double),
                ("dwell_ms", ct.c_uint32)]


class Config(ct.Structure):
    _fields_ = [("abi_version", ct.c_uint32), ("backend", ct.c_uint32),
                ("tick_hz", ct.c_uint32), ("stale_timeout_ms", ct.c_uint32),
                ("pointer_x", Axis), ("pointer_y", Axis), ("scroll", Axis), ("buttons", Button * 4),
                ("target_max_speed", ct.c_double)]


class Frame(ct.Structure):
    _fields_ = [(name, ct.c_double) for name in
                ("pointer_x", "pointer_y", "scroll", "left_click", "right_click", "delete_key", "insert_key")]
    _fields_ += [("pointer_mode", ct.c_uint32), ("target_x", ct.c_double),
                 ("target_y", ct.c_double), ("target_speed", ct.c_double),
                 ("keys_down", ct.c_uint32)]


class Status(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in
                ("enabled", "awaiting_neutral", "timed_out", "last_error", "capabilities", "backend")] + [
                (name, ct.c_uint64) for name in
                ("accepted_frames", "rejected_frames", "emitted_events", "dropped_log_events")] + [
                (name, ct.c_uint32) for name in
                ("pointer_mode", "pointer_position_valid", "target_reached", "reserved")] + [
                (name, ct.c_double) for name in
                ("pointer_position_x", "pointer_position_y", "target_x", "target_y", "target_speed",
                 "pointer_velocity_x", "pointer_velocity_y")] + [
                ("held_key_mask", ct.c_uint32)]


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
    try:
        lib.fid_abi_version.restype = ct.c_uint32
        lib.fid_abi_version.argtypes = []
        if lib.fid_abi_version() != 3:
            raise DriverError("Expected driver ABI v3; rebuild Drivers for this checkout")
    except AttributeError as error:
        raise DriverError("Rebuild Drivers: missing ABI handshake/processed submission support") from error
    signatures = {
        "fid_submit_processed": ([ct.c_void_p, ct.POINTER(Frame)], ct.c_int),
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
    # Additive presentation support: old ABI v3 libraries keep old mappings usable.
    for name, args in {
        "fid_set_presentation": [ct.c_void_p, ct.c_uint32, ct.c_uint32],
        "fid_type_character": [ct.c_void_p, ct.c_uint32],
    }.items():
        if hasattr(lib, name):
            function = getattr(lib, name)
            function.argtypes, function.restype = args, ct.c_int
    return lib


class DriverError(ValueError):
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
        if system == "Linux":
            return (f"{detail}. Build live Linux output with FID_NATIVE_BACKEND=ON. "
                    "Linux target movement also requires X11 and XRandR primary-display geometry; "
                    "pure Wayland sessions are unsupported for target mode. Use `velocity X Y` for "
                    "relative motion, or test targets in dry-run.")
        return (f"{detail}. For live output, build the native backend on Linux or macOS.\n"
                "From Drivers/: cmake -S . -B build -DFID_NATIVE_BACKEND=ON\n"
                "Then: cmake --build build -j 4")
    return f"{detail}. Output remains paused after a failed trial; check status and testing/README.md."
