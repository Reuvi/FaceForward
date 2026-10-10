"""Eye-only per-capture values. Unknown holds prior input plus an explicit flag.

Raw observations remain separate; this fallback must not teach calibration or
complete a release gesture. Other facial signals intentionally have no default here.
"""

from math import isfinite


def eye_value(value, previous=0.0):
    known = type(value) in (bool, int, float) and isfinite(value) and 0 <= value <= 1
    return {"value": float(value) if known else previous, "known": known}


def eye_sample(frame, subject_id, left=None, right=None, *, previous=None):
    session, sequence, timestamp = (
        frame.get(k) for k in ("session_id", "sequence", "timestamp_ms")
    )
    if (
        not isinstance(session, str)
        or not session
        or type(sequence) is not int
        or sequence < 0
        or type(timestamp) not in (int, float)
        or not isfinite(timestamp)
        or timestamp < 0
    ):
        raise ValueError("Eye samples require a valid capture envelope")
    if previous and (
        previous["session_id"] != session or previous["subject_id"] != subject_id
    ):
        previous = None
    return dict(
        format="eye_sample_v1",
        session_id=session,
        sequence=sequence,
        timestamp_ms=timestamp,
        subject_id=subject_id,
        left=eye_value(left, previous["left"]["value"] if previous else 0.0),
        right=eye_value(right, previous["right"]["value"] if previous else 0.0),
    )


def is_fresh_sample(sample, previous, now, stale_ms):
    if not 0 <= now - sample["timestamp_ms"] <= stale_ms:
        return False
    return (
        previous is None
        or sample["session_id"] != previous["session_id"]
        or sample["sequence"] > previous["sequence"]
        and sample["timestamp_ms"] >= previous["timestamp_ms"]
    )


def trace_fields(sample):
    """Use a stable CSV schema, leaving values empty before the first capture."""
    return {
        key: value
        for side in ("left", "right")
        for key, value in (
            (side + "_input", sample[side]["value"] if sample else None),
            (side + "_input_known", sample[side]["known"] if sample else False),
        )
    }
