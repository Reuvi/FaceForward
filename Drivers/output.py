"""Validated Processing commands → the existing mouse/keyboard C driver."""

from collections import Counter, deque
import ctypes as ct
import math
from pathlib import Path
import platform
import time

from .binding import Config, DriverError, Event, Frame, Status, error_message, load_driver

KEYS = ("w", "a", "s", "d", "space", "left_shift")


def default_library():
    name = "libface_input_driver.dylib" if platform.system() == "Darwin" else "libface_input_driver.so"
    return Path(__file__).parent / "build" / name


def number(value, name, low=0, high=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise DriverError(f"Invalid {name}")
    return value


def identity(value, name):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise DriverError(f"Invalid {name}")
    return value


def sequence(value, name):
    if type(value) is not int or value < 0:
        raise DriverError(f"Invalid {name}")
    return value


class DriverOutput:
    """Call from one serialized owner (App's Lab lock); no Python worker/queue."""

    def __init__(self, mode="dry-run", library=None, *, clock=lambda: time.monotonic()*1000):
        if mode not in ("dry-run", "native"):
            raise DriverError("Output must be dry-run or native")
        self.mode, self.clock = mode, clock
        self.lib = load_driver(library or default_library())
        self.handle = ct.c_void_p()
        self.active = False
        self.presentation_active = False
        self.last_output = self.last_source = self.mapping = None
        self.events = deque(maxlen=32)
        self.counts = Counter()
        self.error = None
        self.speeds = (900, 12)
        self._create()

    def check(self, code):
        if code:
            raise DriverError(error_message(self.lib, code))

    def _create(self):
        config = Config()
        self.lib.fid_default_config(ct.byref(config))
        config.backend = int(self.mode == "native")
        config.tick_hz = 100
        config.stale_timeout_ms = 250
        for axis in (config.pointer_x, config.pointer_y, config.scroll):
            axis.neutral, axis.dead_zone, axis.inverted = .5, 0, 0
        config.pointer_x.max_speed = config.pointer_y.max_speed = self.speeds[0]
        config.target_max_speed = self.speeds[0]
        config.scroll.max_speed = self.speeds[1]
        for button in config.buttons:
            button.dwell_ms = 0
        self.check(self.lib.fid_create(ct.byref(config), ct.byref(self.handle)))

    def status(self):
        status = Status()
        if self.handle:
            self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
        return status

    def collect(self):
        if not self.handle:
            return
        events, count = (Event*128)(), ct.c_size_t()
        while True:
            self.check(self.lib.fid_drain_events(self.handle, events, 128, ct.byref(count)))
            for event in events[:count.value]:
                self.counts[event.type] += 1
                self.events.append({"type": event.type, "x": None if event.type == 12 else event.x, "y": event.y})
            if count.value < 128:
                break

    def snapshot(self):
        status = self.status()
        return {"mode": self.mode, "enabled": bool(status.enabled),
                "awaiting_neutral": bool(status.awaiting_neutral),
                "presentation_supported": bool(status.capabilities & 256),
                "text_supported": bool(status.capabilities & 512),
                "timed_out": bool(status.timed_out), "held_keys": status.held_key_mask,
                "error": self.error, "events": list(self.events),
                "pointer_mode": "target" if status.pointer_mode == 1 else "velocity",
                "pointer_position": [status.pointer_position_x, status.pointer_position_y] if status.pointer_position_valid else None,
                "target": [status.target_x, status.target_y],
                "target_reached": bool(status.enabled and status.pointer_mode == 1 and status.target_speed > 0 and status.target_reached),
                "event_counts": dict(self.counts), "accepted_frames": status.accepted_frames}

    def pause(self):
        self.active = False
        self.presentation_active = False
        self.last_output = self.last_source = self.mapping = None
        if self.handle:
            self.check(self.lib.fid_pause(self.handle))
            self.collect()

    def close(self):
        try:
            self.pause()
        finally:
            if self.handle:
                self.lib.fid_destroy(self.handle)
                self.handle = ct.c_void_p()

    def _decode(self, message, now):
        if not isinstance(message, dict) or type(message.get("enabled")) is not bool:
            raise DriverError("Expected a complete Processing command")
        output_seq = sequence(message.get("sequence"), "output sequence")
        stamp = number(message.get("timestamp_ms"), "output timestamp", 0, 1e16)
        if not 0 <= now-stamp <= 250:
            raise DriverError("Output timestamp is stale or in the future")
        fmt = message.get("format")
        gaming = fmt == "device_control_v1"
        if not gaming and fmt != "mouse_preview_v0":
            raise DriverError("Unsupported Processing command format")
        origin = identity(message.get("output_session_id"), "output session") if gaming else "mouse"
        buttons = message.get("buttons")
        names = ("left_click", "right_click") if gaming else ("left", "right")
        if not isinstance(buttons, dict) or set(buttons) != set(names):
            raise DriverError("Expected complete left/right button state")
        for name in names:
            if type(buttons[name]) is not int or buttons[name] not in (0, 1):
                raise DriverError("Buttons must be discrete 0/1")
        keys = message.get("keys") if gaming else dict.fromkeys(KEYS, 0)
        if not isinstance(keys, dict) or set(keys) != set(KEYS) or any(type(v) is not int or v not in (0, 1) for v in keys.values()):
            raise DriverError("Expected complete six-key state")
        pointer = message.get("pointer") if gaming else message.get("velocity")
        if not isinstance(pointer, dict) or (gaming and pointer.get("mode") not in ("velocity", "target")):
            raise DriverError("Expected pointer velocity or target")
        target = gaming and pointer["mode"] == "target"
        if target and set(pointer) != {"mode", "x", "y", "speed"}:
            raise DriverError("Expected complete target coordinates and speed")
        x, y = (number(pointer.get(axis), "pointer "+axis) for axis in ("x", "y"))
        speed = number(pointer["speed"], "target speed") if target else 0
        scroll = number(message.get("scroll_y") if gaming else pointer.get("scroll"), "scroll")
        frame = Frame(x, y, scroll, buttons[names[0]], buttons[names[1]], 0, 0, 0, .5, .5, 0,
                      sum(1 << i for i, key in enumerate(KEYS) if keys[key]))
        if target:
            frame.pointer_x = frame.pointer_y = .5
            frame.pointer_mode = 1
            frame.target_x, frame.target_y, frame.target_speed = x, y, speed
        mapping = (identity(message.get("mapping_id"), "mapping"), sequence(message.get("mapping_revision"), "mapping revision"), pointer["mode"]) if gaming else ("mouse", 0, "velocity")
        if gaming:
            known = message.get("known")
            fields = {"left_click", "right_click", "head_x", "head_y", "pointer"}
            if (not isinstance(known, dict) or set(known) not in (fields, fields | {"keys"})
                    or any(type(known[k]) is not bool for k in fields)):
                raise DriverError("Expected complete channel validity")
            if "keys" in known:
                key_known = known["keys"]
                if (not isinstance(key_known, dict) or set(key_known) != set(KEYS)
                        or any(type(v) is not bool for v in key_known.values())):
                    raise DriverError("Expected complete key validity")
                if any(keys[k] and not key_known[k] for k in KEYS):
                    raise DriverError("Unknown button input cannot hold a key")
            elif not known["head_x"] and not known["head_y"] and frame.keys_down:
                raise DriverError("Unknown head axes cannot hold keys")
            if any(not known[name] and buttons[name] for name in names):
                raise DriverError("Unknown button input cannot click")
            if not known["pointer"] and (x != .5 or y != .5 or speed != 0):
                raise DriverError("Unknown pointer input cannot move the pointer")
        presentation = message.get("presentation")
        if presentation is not None:
            presentation_fields = {"enter", "drag_left", "eyes_known"}
            if (not gaming or not isinstance(presentation, dict) or
                    set(presentation) not in (presentation_fields, presentation_fields | {"left_known", "right_known"}) or
                    any(type(v) is not bool for v in presentation.values())):
                raise DriverError("Expected complete presentation state")
            if target:
                raise DriverError("Presentation requires relative pointer movement")
            enter, drag = presentation["enter"], presentation["drag_left"]
            left_known = presentation.get("left_known", presentation["eyes_known"])
            right_known = presentation.get("right_known", presentation["eyes_known"])
            if ((enter and not right_known) or (drag and not left_known) or (enter and drag) or
                    ((enter or drag) and (any(buttons.values()) or frame.keys_down))):
                raise DriverError("Invalid or unknown presentation gesture")
            if not hasattr(self.lib, "fid_set_presentation") or not (self.status().capabilities & 256):
                raise DriverError("Rebuild Drivers for presentation Enter and dragging support")
        else:
            enter = drag = False
            if self.presentation_active and message["enabled"]:
                raise DriverError("Presentation mode changed without stopping")
        neutral = (not enter and not drag and not frame.keys_down and not any(buttons.values()) and scroll == .5
                   and (target or (x, y) == (.5, .5)))
        if not message["enabled"]:
            if not neutral or (target and (speed != 0 or (x, y) != (.5, .5))):
                raise DriverError("Disabled command must release every output")
            return frame, None, None, None
        source = message.get("source")
        if not isinstance(source, dict):
            raise DriverError("Missing source provenance")
        source_id = (identity(source.get("session_id"), "source session"), identity(source.get("subject_id"), "subject"))
        source_seq = sequence(source.get("sequence"), "capture sequence")
        captured = number(source.get("timestamp_ms"), "capture timestamp", 0, 1e16)
        if not 0 <= now-captured <= 250 or captured > stamp:
            raise DriverError("Capture timestamp is stale or in the future")
        output = (origin, output_seq, stamp)
        capture = (source_id, source_seq, captured)
        if self.last_output and (origin != self.last_output[0] or output_seq <= self.last_output[1] or stamp < self.last_output[2]):
            raise DriverError("Output session changed or command arrived out of order")
        if self.last_source and (source_id != self.last_source[0] or source_seq < self.last_source[1] or captured < self.last_source[2]
                                 or (source_seq == self.last_source[1] and captured != self.last_source[2])):
            raise DriverError("Source changed or capture arrived out of order")
        if self.mapping is not None and mapping != self.mapping:
            raise DriverError("Mapping changed without releasing output")
        if not self.active and not neutral:
            raise DriverError("Driver needs a fresh neutral command before output")
        return frame, output, capture, mapping

    def submit(self, message, runtime):
        try:
            if not self.handle:
                raise DriverError("Driver is closed")
            now = self.clock()
            frame, output, capture, mapping = self._decode(message, now)
            speeds = (number(runtime["pointer_speed"], "pointer speed", 50, 2500),
                      number(runtime["scroll_speed"], "scroll speed", 20, 1500)/40)
            if not message["enabled"]:
                self.pause()
                if speeds != self.speeds:
                    self.lib.fid_destroy(self.handle)
                    self.handle = ct.c_void_p()
                    self.speeds = speeds
                    self._create()
                return
            status = self.status()
            if self.active and (not status.enabled or status.last_error or status.timed_out):
                raise DriverError("Driver stopped or timed out; press Start again" if not status.last_error else error_message(self.lib, status.last_error))
            if speeds != self.speeds:
                raise DriverError("Driver speeds changed without stopping")
            if not self.active:
                self.check(self.lib.fid_enable(self.handle))
            self.check(self.lib.fid_submit_processed(self.handle, ct.byref(frame)))
            status = self.status()
            if not status.enabled or status.awaiting_neutral or status.last_error:
                raise DriverError("Driver could not accept the fresh command; press Start again")
            presentation = message.get("presentation")
            if presentation is not None:
                self.check(self.lib.fid_set_presentation(self.handle, int(presentation["enter"]),
                                                        int(presentation["drag_left"])))
            self.presentation_active = presentation is not None
            self.active = True
            self.last_output, self.last_source, self.mapping = output, capture, mapping
            self.error = None
            self.collect()
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.error = str(exc)
            try:
                self.pause()
            finally:
                raise DriverError(self.error) from exc

    def _require_fresh_presentation(self, action):
        if (not self.active or not self.presentation_active or self.last_source is None or
                not 0 <= self.clock()-self.last_source[2] <= 250 or self.last_output is None or
                not 0 <= self.clock()-self.last_output[2] <= 250):
            raise DriverError(f"{action} output requires fresh enabled presentation input")

    def press_return(self):
        """One Return press/release after explicit dictation completion."""
        try:
            self._require_fresh_presentation("Return")
            if not hasattr(self.lib, "fid_set_presentation"):
                raise DriverError("Rebuild Drivers for Return output support")
            self.check(self.lib.fid_set_presentation(self.handle, 1, 0))
            self.check(self.lib.fid_set_presentation(self.handle, 0, 0))
            self.collect()
        except (ValueError, TypeError, OSError) as exc:
            self.error = str(exc)
            self.pause()
            raise DriverError(self.error) from exc

    def type_character(self, character):
        """One Unicode scalar, gated by the most recently accepted fresh command."""
        try:
            if (not isinstance(character, str) or len(character) != 1 or not character.isprintable()
                    or 0xd800 <= ord(character) <= 0xdfff):
                raise DriverError("Text output requires one printable Unicode scalar")
            self._require_fresh_presentation("Text")
            if not hasattr(self.lib, "fid_type_character"):
                raise DriverError("Rebuild Drivers for text output support")
            self.check(self.lib.fid_type_character(self.handle, ord(character)))
            self.collect()
        except (ValueError, TypeError, OSError) as exc:
            self.error = str(exc)
            self.pause()
            raise DriverError(self.error) from exc
