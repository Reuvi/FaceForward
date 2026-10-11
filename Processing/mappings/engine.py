"""Gaming signal mapping on the existing freshness/eye/pointer engine."""

from dataclasses import replace
import math
import uuid

from Processing.mouse.engine import AxisFilter, MouseProcessor
from .config import DIRECTIONS, KEYS, Mapping


class HeadGate:
    """Independent capture-timed head axis with neutral rearming and hysteresis."""

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.raw = self.filtered = self.timestamp = None
        self.base_value = self.base_time = None
        self.ready = False
        self.direction = self.candidate = 0
        self.since = None

    @property
    def neutral(self):
        return self.raw is None or (abs(2*self.raw-1) <= self.config.release+1e-12 and
                                    abs(self.filtered) <= self.config.release+1e-12)

    def sample(self, value, timestamp, armed):
        if value is None:
            self.reset()
            return
        signed = 2*value-1
        if timestamp != self.timestamp:
            self.base_time, self.base_value = self.timestamp, self.filtered
        if self.base_time is None or self.config.smoothing_ms == 0:
            self.filtered = signed
        else:
            alpha = -math.expm1(-(timestamp-self.base_time)/self.config.smoothing_ms)
            self.filtered = self.base_value + alpha*(signed-self.base_value)
        self.raw, self.timestamp = value, timestamp
        if not armed:
            self.ready = False
            self.direction = self.candidate = 0
            self.since = None
            return
        if not self.ready:
            self.ready = self.neutral
            return
        if self.direction and self.direction*self.filtered <= self.config.release+1e-12:
            self.direction = 0
        if self.direction:
            return
        direction = 1 if self.filtered >= self.config.activation-1e-12 else -1 if self.filtered <= -self.config.activation+1e-12 else 0
        if direction != self.candidate:
            self.candidate, self.since = direction, timestamp if direction else None
        if direction and timestamp-self.since >= self.config.confirmation_ms:
            self.direction = direction
            self.candidate, self.since = 0, None

    def status(self, direction):
        if self.raw is None:
            return "unknown; released"
        if not self.ready:
            return "waiting for neutral"
        if self.direction == direction:
            return "held"
        if self.candidate == direction:
            return "confirming movement"
        return "below threshold; released"


class GamingProcessor(MouseProcessor):
    def __init__(self, mapping=None, subject_id="mock-person"):
        self.mapping = mapping or Mapping()
        self.head_x = HeadGate(self.mapping.head_x)
        self.head_y = HeadGate(self.mapping.head_y)
        self.output_session_id = str(uuid.uuid4())
        super().__init__(self.mapping.response, subject_id)
        self.pointer = AxisFilter(self.config.pointer, 2, gain=self.mapping.pointer_gain)

    def decode_sample(self, frame):
        sample = super().decode_sample(frame)
        if frame.get("format") != "raw_mouse_v1" and not sample.appearance_intent:
            sample = replace(sample, left_closed=False, right_closed=False,
                             left_known=False, right_known=False)
        return sample

    def arm(self):
        super().arm()
        self.head_x.reset()
        self.head_y.reset()

    def disarm(self, reason="Preview stopped"):
        super().disarm(reason)
        self.head_x.reset()
        self.head_y.reset()

    def accept(self, frame, received_ms):
        result = super().accept(frame, received_ms)
        if result["accepted"]:
            self.head_x.sample(self.sample.head_x, self.sample.timestamp_ms, self.armed)
            self.head_y.sample(self.sample.scroll, self.sample.timestamp_ms, self.armed)
        return result

    def can_enable(self):
        usable = self.pointer.valid or self.head_x.ready or self.head_y.ready or self.left.ready or self.right.ready
        return (usable and self.pointer.neutral() and self.head_x.neutral and self.head_y.neutral
                and not self.left.down and not self.right.down)

    def tick(self, now_ms):
        snap = super().tick(now_ms)
        keys = dict.fromkeys(KEYS, 0)
        directions = (self.head_y.direction == 1, self.head_y.direction == -1,
                      self.head_x.direction == -1, self.head_x.direction == 1)
        if snap["enabled"]:
            for key, active in zip(self.mapping.bindings, directions):
                if key != "none" and active:
                    keys[key] = 1
        diag = snap["diagnostics"]
        snap.update(keys=keys, scroll_y=.5, mapping_id=self.mapping.id,
                    mapping_name=self.mapping.name, mapping_revision=self.mapping.revision,
                    output_session_id=self.output_session_id)
        diag.update(scroll_target=0, scroll_boost=0, interpolated_scroll=None,
                    head_x=self.head_diagnostic(self.head_x), head_y=self.head_diagnostic(self.head_y))
        snap["known"] = {"left_click": diag["left_closed"] is not None,
                         "right_click": diag["right_closed"] is not None,
                         "head_x": self.head_x.raw is not None,
                         "head_y": self.head_y.raw is not None,
                         "pointer": diag["raw_pointer"] is not None}
        snap["instructions"] = self.instructions(snap)
        return snap

    @staticmethod
    def head_diagnostic(gate):
        return {"raw": gate.raw, "filtered": (gate.filtered+1)/2 if gate.filtered is not None else None,
                "ready": gate.ready, "neutral": gate.neutral, "direction": gate.direction, "candidate": gate.candidate}

    def instructions(self, snap):
        rows = []
        diag = snap["diagnostics"]
        for side in ("left", "right"):
            gate = getattr(self, side)
            raw = diag[side+"_closed"]
            status = "unknown; released" if raw is None else "waiting for reopen" if not gate.ready else "active" if snap[side+"_click"] else "released"
            rows.append({"id": "eye_"+side, "input": side.title()+" eye action", "raw": None if raw is None else int(raw),
                         "filtered": None if raw is None else int(raw), "threshold": "Calibrated action",
                         "instruction": side.title()+" mouse: "+status})
        for name, gate, direction, key in zip(DIRECTIONS, (self.head_y,self.head_y,self.head_x,self.head_x),
                                              (1,-1,-1,1), self.mapping.bindings):
            on = (.5+direction*gate.config.activation/2)
            off = (.5+direction*gate.config.release/2)
            status = gate.status(direction)
            if not snap["armed"]:
                status = "preview stopped"
            elif not snap["enabled"] and gate.raw is not None:
                status = "waiting for neutral; released"
            elif key == "none":
                status = "unassigned; released"
            rows.append({"id": name, "input": "Head "+name, "raw": gate.raw,
                         "filtered": (gate.filtered+1)/2 if gate.filtered is not None else None,
                         "threshold": f"On {on:.3f} / off {off:.3f}",
                         "instruction": key.replace("left_shift", "Shift").upper()+": "+status})
        for index, axis in enumerate(("x", "y")):
            point = diag["raw_pointer"]
            filtered = diag["interpolated_pointer"]
            signed = 2*snap["pointer_"+axis]-1
            direction = ("right" if signed > 0 else "left") if axis == "x" else ("down" if signed > 0 else "up")
            instruction = "unknown; stopped" if point is None else "stopped" if abs(signed) < .0001 else f"{direction} {abs(signed):.0%}"
            rows.append({"id": "pupil_"+axis, "input": "Pupils "+axis.upper(),
                         "raw": point[index] if point is not None else None,
                         "filtered": filtered[index] if filtered is not None else None,
                         "threshold": f"Radius {self.config.pointer.deadzone+self.config.pointer.hysteresis:.2f} / {self.config.pointer.deadzone:.2f}",
                         "instruction": "Pointer: "+instruction})
        return rows
