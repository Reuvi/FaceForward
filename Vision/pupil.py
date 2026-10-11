"""Eye-relative iris direction, not screen gaze. No additional ML inference."""

import math
from dataclasses import dataclass, field
from .geometry import eye_ratios, midpoint, sub
from .landmarks import EYES
from .signals import finite_number

MEASUREMENT = "mediapipe_iris_direction_v3"
X_HALF_RANGE, UP_RANGE, DOWN_RANGE = 0.2, 0.1, 0.065
MATRIX_SIZE = 11


def normalize(xy):
    """Fixed scale for direct iris direction; no personal fit or head-pose gate."""
    if xy is None or len(xy) != 2 or not all(finite_number(v) for v in xy):
        return None
    x, y = xy
    return (
        max(0.0, min(1.0, 0.5 + x / (2 * X_HALF_RANGE))),
        max(0.0, min(1.0, 0.5 + y / (2 * (UP_RANGE if y <= 0 else DOWN_RANGE)))),
    )


def matrix_cell(xy):
    if (
        xy is None
        or len(xy) != 2
        or not all(finite_number(v) and 0 <= v <= 1 for v in xy)
    ):
        return None
    return tuple(int(math.floor(v * (MATRIX_SIZE - 1) + 0.5)) for v in (xy[1], xy[0]))


def matrix_sample(frame, subject):
    """Additive one-hot sample; invalid evidence never becomes a center cell."""
    signals = next(
        (f["signals"] for f in frame["faces"] if f["subject_id"] == subject), {}
    )
    axes = [signals.get(k, {}) for k in ("gaze_x", "gaze_y")]
    confidence = min((a.get("confidence", 0) for a in axes), default=0)
    cell = (
        matrix_cell(tuple(a.get("value") for a in axes))
        if all(a.get("valid") for a in axes)
        else None
    )
    values = None
    if cell is not None and finite_number(confidence) and 0 < confidence <= 1:
        values = [[0] * MATRIX_SIZE for _ in range(MATRIX_SIZE)]
        values[cell[0]][cell[1]] = 1
    else:
        cell, confidence = None, 0.0
    return dict(
        format="pupil_matrix_v1",
        size=MATRIX_SIZE,
        **{key: frame[key] for key in ("session_id", "sequence", "timestamp_ms")},
        subject_id=subject,
        valid=cell is not None,
        confidence=confidence,
        row=cell[0] if cell else None,
        column=cell[1] if cell else None,
        values=values,
    )


@dataclass
class PupilReading:
    xy: object = None
    quality: float = 0
    reason: str = "Pupils unavailable"
    eyes: dict = field(default_factory=dict)
    pose: object = None


def pose_angles(rotation):
    if rotation is None:
        return None
    return (
        math.degrees(math.atan2(rotation[0][2], rotation[2][2])),
        math.degrees(
            math.atan2(-rotation[1][2], math.hypot(rotation[0][2], rotation[2][2]))
        ),
        math.degrees(math.atan2(rotation[1][0], rotation[1][1])),
    )


def measure(observation, features, eye_calibrations=None):
    result = PupilReading(pose=pose_angles(observation.rotation))
    points = observation.points
    if len(points) < 478:
        result.reason = "Iris landmarks unavailable"
        return result
    down = sub(midpoint(points[61], points[291]), midpoint(points[33], points[263]))
    qualities = []
    for side, (corners, pairs, ring) in EYES.items():
        f = features[side]
        blink = observation.expressions.get("eyeBlink" + side.title(), 0)
        look_down = observation.expressions.get("eyeLookDown" + side.title())
        look_up = observation.expressions.get("eyeLookUp" + side.title())
        calibration = (eye_calibrations or {}).get(side)
        # Only completed guided geometry has separated open/closed regions.
        # Use positive same-eye evidence; never require an eye fit for pupils.
        personal_open = bool(calibration is not None and calibration.open_limit is not None
                             and finite_number(f.value) and f.value >= calibration.open_limit
                             and f.value > calibration.closed_limit)
        entry = {
            "xy": None,
            "valid": False,
            "reason": "Open eye clearly to measure its iris",
            "lid_gap": f.value,
            "blink": blink,
            "look_down": look_down,
            "look_up": look_up,
            "down_supported": False,
            "aperture_source": "personal open geometry" if personal_open else "generic geometry",
        }
        result.eyes[side] = entry
        if (
            not f.quality
            or f.value is None
            or f.value < (0.04 if personal_open else 0.10)
            or not finite_number(blink)
            or not 0 <= blink < (0.8 if personal_open else 0.4)
        ):
            continue
        center = tuple(sum(points[i][axis] for i in ring) / 4 for axis in (0, 1))
        width = math.dist(points[corners[0]], points[corners[1]])
        radius = sum(math.dist(center, points[i]) for i in ring) / 4 / max(width, 1e-6)
        if not 0.025 <= radius <= 0.25:
            entry["reason"] = "Iris shape too small or distorted"
            continue
        try:
            ratios = eye_ratios(
                *(points[i] for i in corners),
                [(points[a], points[b]) for a, b in pairs],
                center,
                down,
            )
        except ValueError:
            continue
        xy = (ratios.horizontal - 0.5, ratios.vertical)
        if not (-0.45 <= xy[0] <= 0.45 and -0.3 <= xy[1] <= 0.3):
            entry["reason"] = "Iris outside supported eye geometry"
            continue
        down_supported = (
            "eyeBlink" + side.title() in observation.expressions
            and xy[1] > 0.015
            and finite_number(look_down)
            and finite_number(look_up)
            and 0.2 <= look_down <= 1
            and 0 <= look_up <= 1
            and look_down - look_up >= 0.1
        )
        entry["down_supported"] = down_supported
        if f.value < 0.16 and not down_supported and not personal_open:
            entry["reason"] = "Narrow eye without supported downward iris direction"
            continue
        entry.update(
            xy=xy,
            valid=True,
            reason="Personally calibrated open-eye iris" if personal_open else
                   "Supported down-looking iris" if f.value < 0.16 else "Visible open-eye iris",
        )
        qualities.append(f.quality)
    if not all(v["valid"] for v in result.eyes.values()):
        result.reason = (
            "Both pupils need clear, open eyes; closure pauses this joystick"
        )
        return result
    left, right = [result.eyes[s]["xy"] for s in ("left", "right")]
    if max(abs(a - b) for a, b in zip(left, right)) > 0.18:
        result.reason = "Pupil directions disagree; face the camera and check lighting"
        return result
    result.xy = tuple((a + b) / 2 for a, b in zip(left, right))
    result.quality = min(qualities)
    result.reason = "Raw pupil direction available"
    return result
