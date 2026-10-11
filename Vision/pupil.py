"""Eye-relative iris direction, not screen gaze. No additional ML inference."""
import math
from dataclasses import dataclass, field
from .geometry import eye_ratios, midpoint, sub
from .landmarks import EYES

MEASUREMENT = "personal_pupil_joystick_v1"


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


def measure(observation, features, calibrations):
    result = PupilReading(pose=pose_angles(observation.rotation))
    points = observation.points
    if len(points) < 478:
        result.reason = "Iris landmarks unavailable"
        return result
    down = sub(midpoint(points[61], points[291]), midpoint(points[33], points[263]))
    qualities = []
    for side, (corners, pairs, ring) in EYES.items():
        f = features[side]
        fit = calibrations.get(side)
        blink = observation.expressions.get("eyeBlink"+side.title(), 0)
        opened = (fit.classify(f.value, f.quality).get("value") == 1 if fit and f.value is not None
                  else f.value is not None and f.value >= .16)
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


def pose_supported(current, reference):
    return (current is not None and reference is not None
            and all(abs(a-b) <= limit for a, b, limit in zip(current, reference, (18, 18, 25))))
