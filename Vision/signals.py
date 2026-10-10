"""SignalFrame v1 construction and validation; no Processing dependency."""

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from uuid import uuid4


# The calibrated app's single operator slot; not a biometric identity.
SINGLE_SUBJECT = "single-user"

SIGNALS = (
    "gaze_x", "gaze_y", "tongue_x", "tongue_y",
    "left_eye_open", "right_eye_open", "head_x", "head_y",
)


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def unit_number(value):
    return finite_number(value) and 0 <= value <= 1


def invalid():
    return {"value": None, "confidence": 0.0, "valid": False}


def measurement(value, confidence):
    """Invalid detector results fail closed, including NaN and boolean values."""
    if not unit_number(value) or not unit_number(confidence) or confidence == 0:
        return invalid()
    return {"value": float(value), "confidence": float(confidence), "valid": True}


def make_face(subject_id, measurements=None):
    """Include all eight signals; missing measurements are never neutralized."""
    measurements = {} if measurements is None else measurements
    if set(measurements) - set(SIGNALS):
        raise ValueError("unknown signal name")
    result = {
        "subject_id": subject_id,
        "signals": {name: deepcopy(measurements.get(name, invalid())) for name in SIGNALS},
    }
    _validate_face(result)
    return result


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _validate_face(face):
    if not isinstance(face, dict):
        raise ValueError("face must be an object")
    _text(face.get("subject_id"), "subject_id")
    signals = face.get("signals")
    if not isinstance(signals, dict) or not set(SIGNALS) <= signals.keys():
        raise ValueError("all eight signals are required")
    for name in SIGNALS:
        item = signals[name]
        if not isinstance(item, dict) or not {"value", "confidence", "valid"} <= item.keys():
            raise ValueError(f"incomplete measurement: {name}")
        if type(item["valid"]) is not bool or not unit_number(item["confidence"]):
            raise ValueError(f"invalid validity/confidence: {name}")
        if item["valid"]:
            if not unit_number(item["value"]):
                raise ValueError(f"invalid measurement value: {name}")
        elif item["value"] is not None or item["confidence"] != 0:
            raise ValueError(f"unavailable measurement must be null/0/false: {name}")


def validate_frame(frame):
    """Accept v1 including additive fields and intermediate eye openness."""
    if not isinstance(frame, dict):
        raise ValueError("SignalFrame must be an object")
    if type(frame.get("schema_version")) is not int or frame["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    _text(frame.get("session_id"), "session_id")
    seq, timestamp = frame.get("sequence"), frame.get("timestamp_ms")
    if type(seq) is not int or seq < 0:
        raise ValueError("sequence must be a nonnegative integer")
    if not finite_number(timestamp) or timestamp < 0:
        raise ValueError("timestamp_ms must be finite and nonnegative")
    faces = frame.get("faces")
    if not isinstance(faces, list) or len(faces) > 2:
        raise ValueError("faces must be an array with at most two faces")
    for face in faces:
        _validate_face(face)
    ids = [face["subject_id"] for face in faces]
    if len(ids) != len(set(ids)):
        raise ValueError("subject IDs must be unique within a frame")
    return frame


def monotonic_ms():
    return monotonic() * 1000.0


@dataclass(frozen=True)
class Envelope:
    session_id: str
    sequence: int
    timestamp_ms: float

    def frame(self, faces):
        return validate_frame({
            "schema_version": 1, "session_id": self.session_id,
            "sequence": self.sequence, "timestamp_ms": self.timestamp_ms,
            "faces": deepcopy(list(faces)),
        })


class CaptureSession:
    """Stamp at capture, before inference. App may inject its common ms clock."""

    def __init__(self, clock=monotonic_ms):
        self.clock = clock
        self.restart()

    def restart(self):
        self.session_id = str(uuid4())
        self.sequence = -1
        self.last_timestamp = None

    def stamp(self, *, skipped=0):
        if type(skipped) is not int or skipped < 0:
            raise ValueError("skipped must be a nonnegative integer")
        now = self.clock()
        if not finite_number(now) or now < 0:
            raise ValueError("capture clock must return finite, nonnegative milliseconds")
        if self.last_timestamp is not None and now < self.last_timestamp:
            raise ValueError("capture clock moved backwards")
        self.sequence += 1 + skipped
        self.last_timestamp = now
        return Envelope(self.session_id, self.sequence, now)
