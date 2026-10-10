"""Synthetic and streaming NDJSON replay sources using the shared clock."""

from copy import deepcopy
import json
import math
from time import sleep
from uuid import uuid4

from .signals import Envelope, finite_number, make_face, measurement, monotonic_ms, validate_frame


def read_ndjson(path):
    with open(path, encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                yield validate_frame(json.loads(line))
            except (ValueError, TypeError) as error:
                raise ValueError(f"{path}:{number}: {error}") from error


def replay(records, *, clock=monotonic_ms, sleeper=sleep):
    """Rebase capture times without erasing gaps or hiding a slow consumer.

    A source-session change creates a fresh output session. Timestamps are due
    times on the injected clock, not inference/completion times. Late records
    remain late so downstream staleness checks still work.
    """
    last_clock = None

    def now():
        nonlocal last_clock
        value = clock()
        if not finite_number(value) or value < 0:
            raise ValueError("replay clock must return finite, nonnegative milliseconds")
        if last_clock is not None and value < last_clock:
            raise ValueError("replay clock moved backwards")
        last_clock = value
        return value

    source_session = None
    source_start = output_start = previous_time = previous_sequence = None
    output_session = None
    for original in records:
        validate_frame(original)
        changed = original["session_id"] != source_session
        if changed:
            source_session = original["session_id"]
            output_session = str(uuid4())
            source_start = original["timestamp_ms"]
            output_start = now()
            # Reuse the envelope validator for the injected clock.
            Envelope(output_session, 0, output_start).frame([])
        else:
            if original["sequence"] <= previous_sequence:
                raise ValueError("replay sequences must strictly increase within a session")
            if original["timestamp_ms"] < previous_time:
                raise ValueError("replay capture times must not move backwards")
        due = output_start + (original["timestamp_ms"] - source_start)
        if not finite_number(due):
            raise ValueError("rebased replay time overflowed")
        while True:
            remaining = due - now()
            if remaining <= 0:
                break
            sleeper(remaining / 1000.0)
        result = deepcopy(original)
        result["session_id"] = output_session
        result["timestamp_ms"] = due
        previous_time = original["timestamp_ms"]
        previous_sequence = original["sequence"]
        yield validate_frame(result)


def synthetic_records(*, count=120, fps=30.0):
    """An explicitly synthetic repeating no-face/wink/two-face/loss scenario."""
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be finite and positive")
    for index in range(count):
        phase = index % 120
        faces = []
        if 10 <= phase < 100:
            values = {
                "gaze_x": measurement(0.5 + 0.2 * math.sin(index / 10), 1),
                "gaze_y": measurement(0.5, 1),
                "left_eye_open": measurement(0 if 30 <= phase < 35 else 1, 1),
                "right_eye_open": measurement(1, 1),
                "head_x": measurement(0.5, 1),
                "head_y": measurement(0.5, 1),
            }
            if 30 <= phase < 35:
                # This fixture has not validated a single-eye gaze mode.
                values.pop("gaze_x")
                values.pop("gaze_y")
            faces.append(make_face(f"synthetic-person-{index // 120}", values))
        if 60 <= phase < 110:
            faces.append(make_face(f"synthetic-bystander-{index // 120}"))
        yield Envelope("synthetic-recording", index, index * 1000.0 / fps).frame(faces)
