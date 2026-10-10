"""Adapters for provisional one-hot inputs and the repository's SignalFrame v1."""

from dataclasses import dataclass
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def unit(value):
    return finite(value) and 0 <= value <= 1


def one_hot_vector(values):
    # Accept [0,1,0], [[0,1,0]], or [[0],[1],[0]].
    if not isinstance(values, list) or not values:
        return None
    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    elif all(isinstance(row, list) and len(row) == 1 for row in values):
        values = [row[0] for row in values]
    if not 2 <= len(values) <= 256:
        return None
    if not all(finite(v) and v in (0, 1) for v in values) or sum(values) != 1:
        return None
    return values.index(1) / (len(values) - 1)


def one_hot_matrix(values):
    if not isinstance(values, list) or not 2 <= len(values) <= 256:
        return None
    if not isinstance(values[0], list) or not 2 <= len(values[0]) <= 256:
        return None
    width = len(values[0])
    if not all(isinstance(row, list) and len(row) == width for row in values):
        return None
    points = []
    for y, row in enumerate(values):
        for x, value in enumerate(row):
            if not finite(value) or value not in (0, 1):
                return None
            if value == 1:
                points.append((x / (width - 1), y / (len(values) - 1)))
    return points[0] if len(points) == 1 else None


class SubjectMissing(ValueError):
    """A valid capture with no observation for the requested person."""


@dataclass(frozen=True)
class Sample:
    session_id: str
    sequence: int
    timestamp_ms: float
    subject_id: str
    left_closed: object
    right_closed: object
    pointer: object
    scroll: object
    left_known: bool = True
    right_known: bool = True
    appearance_intent: bool = False
    left_reopened: bool = False
    right_reopened: bool = False

    def __post_init__(self):
        for side in ("left", "right"):
            if getattr(self, side + "_closed") is None:
                object.__setattr__(self, side + "_closed", False)
                object.__setattr__(self, side + "_known", False)


def decode(frame, config, subject_id):
    if not isinstance(frame, dict):
        raise ValueError("Frame must be an object")
    session = frame.get("session_id")
    sequence = frame.get("sequence")
    timestamp = frame.get("timestamp_ms")
    if not isinstance(session, str) or not session or len(session) > 128:
        raise ValueError("session_id must be a nonempty string of at most 128 characters")
    if type(sequence) is not int or sequence < 0:
        raise ValueError("sequence must be a nonnegative integer")
    if not finite(timestamp) or timestamp < 0:
        raise ValueError("timestamp_ms must be a finite monotonic time")

    if frame.get("format") == "raw_mouse_v1":
        if frame.get("subject_id") != subject_id:
            raise SubjectMissing("Selected subject is missing")
        def eye(name):
            value = frame.get(name)
            return value == config.closed_value if finite(value) and value in (0, 1) else None
        return Sample(session, sequence, timestamp, subject_id, eye("left_eye"), eye("right_eye"),
                      one_hot_matrix(frame.get(config.pointer_source)),
                      one_hot_vector(frame.get("head_vertical")))

    if type(frame.get("schema_version")) is not int or frame["schema_version"] != 1:
        raise ValueError("Expected raw_mouse_v1 or SignalFrame schema_version 1")
    faces = frame.get("faces")
    if not isinstance(faces, list) or len(faces) > 2:
        raise ValueError("faces must contain zero to two observations")
    if not all(isinstance(face, dict) for face in faces):
        raise ValueError("Invalid face observation")
    selected = [face for face in faces if face.get("subject_id") == subject_id]
    if not selected:
        raise SubjectMissing("Selected subject is missing")
    if len(selected) != 1:
        raise ValueError("Selected subject is ambiguous")
    signals = selected[0].get("signals")
    if not isinstance(signals, dict):
        raise ValueError("signals must be an object")

    def measurement(name):
        item = signals.get(name)
        if not isinstance(item, dict) or item.get("valid") is not True:
            return None
        value, confidence = item.get("value"), item.get("confidence")
        return value if unit(value) and unit(confidence) and confidence >= config.min_confidence else None

    def eye(name):
        value = measurement(name)
        # SignalFrame's *_eye_open convention is fixed, independent of raw polarity.
        return value == 0 if value in (0, 1) else None

    x, y = measurement(config.pointer_source + "_x"), measurement(config.pointer_source + "_y")
    if "eye_intent" in frame:
        intent=frame["eye_intent"]
        if (not isinstance(intent,dict) or set(intent)!={"format","session_id","sequence","timestamp_ms","subject_id","left","right"}
                or intent.get("format")!="eye_intent_v1" or type(intent.get("sequence")) is not int
                or not finite(intent.get("timestamp_ms"))
                or any(intent.get(k)!=frame[k] for k in ("session_id","sequence","timestamp_ms"))
                or intent.get("subject_id")!=subject_id):
            raise ValueError("Wink sample does not match the current capture/subject")
        bits=[]
        for side in ("left","right"):
            item=intent.get(side)
            if not isinstance(item,dict) or set(item)!={"value","known","state"} or type(item["known"]) is not bool:
                raise ValueError("Invalid wink sample")
            valid = (item["known"] and finite(item["value"]) and item["value"] in (0,1)
                     and item["state"] in (("wink",) if item["value"] else ("open","blink")))
            unknown = not item["known"] and item["value"] is None and item["state"]=="unknown"
            if not (valid or unknown):raise ValueError("Inconsistent wink sample")
            bits.append(bool(item["value"]) if valid else None)
        return Sample(session,sequence,timestamp,subject_id,*bits,
                      (x,y) if x is not None and y is not None else None,measurement("head_y"),
                      appearance_intent=True,left_reopened=measurement("left_eye_open")==1,
                      right_reopened=measurement("right_eye_open")==1)
    return Sample(session, sequence, timestamp, subject_id, eye("left_eye_open"), eye("right_eye_open"),
                  (x, y) if x is not None and y is not None else None, measurement("head_y"))
