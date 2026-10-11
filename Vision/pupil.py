"""Eye-relative iris direction, not screen gaze. No additional ML inference."""
import math
from dataclasses import dataclass, field
from .geometry import eye_ratios, midpoint, sub
from .landmarks import EYES
from .signals import finite_number

MEASUREMENT = "mediapipe_iris_direction_v2"
HALF_RANGES = (.2, .1)  # Eye widths, independent of changing lid opening.


def settings(value=None):
    if value is None:
        return dict(measurement=MEASUREMENT, x_sensitivity=1., y_sensitivity=1.)
    if (not isinstance(value, dict)
            or set(value) != {"measurement", "x_sensitivity", "y_sensitivity"}
            or value["measurement"] != MEASUREMENT):
        raise ValueError("Unsupported direct pupil settings")
    for key in ("x_sensitivity", "y_sensitivity"):
        if not finite_number(value[key]) or not .25 <= value[key] <= 4:
            raise ValueError(f"{key} must be a finite number from 0.25 to 4")
    return dict(value)


def normalize(xy, options):
    """Fixed geometric scale, no training, temporal extrema or pose reference."""
    if xy is None or len(xy) != 2 or not all(finite_number(v) for v in xy):
        return None
    return tuple(max(0., min(1., .5+v*options[key]/(2*span)))
                 for v, span, key in zip(xy, HALF_RANGES, ("x_sensitivity", "y_sensitivity")))


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
    return (math.degrees(math.atan2(rotation[0][2], rotation[2][2])),
            math.degrees(math.atan2(-rotation[1][2], math.hypot(rotation[0][2], rotation[2][2]))),
            math.degrees(math.atan2(rotation[1][0], rotation[1][1])))


def measure(observation, features):
    result = PupilReading(pose=pose_angles(observation.rotation))
    points = observation.points
    if len(points) < 478:
        result.reason = "Iris landmarks unavailable"
        return result
    down = sub(midpoint(points[61], points[291]), midpoint(points[33], points[263]))
    qualities = []
    for side, (corners, pairs, ring) in EYES.items():
        f = features[side]
        blink = observation.expressions.get("eyeBlink"+side.title(), 0)
        opened = f.value is not None and f.value >= .16
        entry = {"xy": None, "valid": False, "reason": "Open eye clearly to measure its iris"}
        result.eyes[side] = entry
        if not f.quality or not opened or blink >= .4:
            continue
        center = tuple(sum(points[i][axis] for i in ring)/4 for axis in (0, 1))
        width = math.dist(points[corners[0]], points[corners[1]])
        radius = sum(math.dist(center, points[i]) for i in ring)/4/max(width, 1e-6)
        if not .025 <= radius <= .25:
            entry["reason"] = "Iris shape too small or distorted"
            continue
        try:
            ratios = eye_ratios(*(points[i] for i in corners),
                                [(points[a], points[b]) for a, b in pairs], center, down)
        except ValueError:
            continue
        xy = (ratios.horizontal-.5, ratios.vertical)
        if not (-.45 <= xy[0] <= .45 and -.3 <= xy[1] <= .3):
            entry["reason"] = "Iris outside supported eye geometry"
            continue
        entry.update(xy=xy, valid=True, reason="Visible open-eye iris")
        qualities.append(f.quality)
    if not all(v["valid"] for v in result.eyes.values()):
        result.reason = "Both pupils need clear, open eyes; closure pauses this joystick"
        return result
    left, right = [result.eyes[s]["xy"] for s in ("left", "right")]
    if max(abs(a-b) for a, b in zip(left, right)) > .18:
        result.reason = "Pupil directions disagree; face the camera and check lighting"
        return result
    result.xy = tuple((a+b)/2 for a, b in zip(left, right))
    result.quality = min(qualities)
    result.reason = "Raw pupil direction available"
    return result
