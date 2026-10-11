"""Personal iris endpoints and a small, capture-time head-drift regression."""
from copy import deepcopy

import numpy as np

from .pupil import MEASUREMENT
from .signals import finite_number

SPACE = "head_compensated_iris_direction_v1"
POSE_MARGIN = 3.0
ROLL_MARGIN = 12.0
MIN_RANGE = .015
CHECK_NAMES = ("diagonal", "left", "right", "up", "down")
POSE_NAMES = ("center", "head_left", "head_right", "head_up", "head_down")


def _array(value, shape, bound, label):
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"Pupil {label} must be an array")
    def numeric(v):
        return all(numeric(item) for item in v) if isinstance(v, (tuple, list)) else finite_number(v)
    if not numeric(value):
        raise ValueError(f"Invalid pupil {label}")
    try:
        array = np.asarray(value)
        if array.shape != shape or array.dtype.kind not in "fiu":
            raise ValueError()
        array = array.astype(float)
        if not np.isfinite(array).all() or (np.abs(array) > bound).any():
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid pupil {label}") from exc
    return array


def validate_model(model):
    if model is None:
        return None
    keys = {"space", "measurement", "reference_pose", "pose_bounds", "slopes", "center", "low", "high", "checks"}
    if not isinstance(model, dict) or set(model) != keys:
        raise ValueError("Pupil calibration has missing or unknown fields")
    if model["space"] != SPACE or model["measurement"] != MEASUREMENT:
        raise ValueError("Incompatible pupil coordinate space")
    ref = _array(model["reference_pose"], (3,), 90, "reference pose")
    bounds = _array(model["pose_bounds"], (2, 2), 90, "pose bounds")
    _array(model["slopes"], (2, 2), .03, "head slopes")
    center = _array(model["center"], (2,), .5, "center")
    low = _array(model["low"], (2,), .5, "minimums")
    high = _array(model["high"], (2,), .5, "maximums")
    if (np.minimum(center-low, high-center) < MIN_RANGE).any():
        raise ValueError("Pupil directional ranges are too small or reversed")
    if ((ref[:2]-bounds[:, 0] < (4, 3)).any()
            or (bounds[:, 1]-ref[:2] < (4, 3)).any()):
        raise ValueError("Pupil head-angle coverage needs both directions")
    checks = model["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECK_NAMES):
        raise ValueError("Pupil calibration requires fresh checks")
    for check in checks.values():
        if (not isinstance(check, dict) or set(check) != {"samples", "matched_fraction"}
                or type(check["samples"]) is not int or check["samples"] < 1
                or not finite_number(check["matched_fraction"])
                or not .9 <= check["matched_fraction"] <= 1):
            raise ValueError("Invalid pupil validation result")
    return deepcopy(model)


def compensate(model, xy, pose):
    """Return corrected eye-width units, or an explicit invalid reason. O(1)."""
    if (not isinstance(xy, (tuple, list)) or len(xy) != 2
            or not all(finite_number(v) for v in xy)):
        return None, "Pupils unavailable; keep both eyes visible"
    if model is None:
        return None, "Run pupil calibration to define your directions and head compensation"
    if (not isinstance(pose, (tuple, list)) or len(pose) != 3
            or not all(finite_number(v) for v in pose)):
        return None, "Head pose unavailable; pupil compensation needs the same-frame angles"
    reference = model["reference_pose"]
    for index, (low, high) in enumerate(model["pose_bounds"]):
        if not low-POSE_MARGIN <= pose[index] <= high+POSE_MARGIN:
            return None, "Head angle outside pupil calibration; return toward your trained head positions"
    if abs(pose[2]-reference[2]) > ROLL_MARGIN:
        return None, "Head tilted sideways beyond pupil calibration; straighten gently"
    delta = (pose[0]-reference[0], pose[1]-reference[1])
    corrected = tuple(v-s[0]*delta[0]-s[1]*delta[1] for v, s in zip(xy, model["slopes"]))
    return corrected, "Personal pupil direction · head-angle compensated"


def normalize(model, xy, pose):
    corrected, reason = compensate(model, xy, pose)
    if corrected is None:
        return None, None, reason
    result = []
    for value, low, center, high in zip(corrected, model["low"], model["center"], model["high"]):
        span = high-center if value >= center else center-low
        result.append(max(0., min(1., .5+.5*(value-center)/span)))
    return tuple(result), corrected, reason


def fit_pose(groups):
    """Equal weight per held pose; screen target stays centered for every group."""
    medians = np.array([np.median(groups[name], axis=0) for name in POSE_NAMES])
    reference = medians[0, 2:]
    pose = medians[:, 2:4]
    coverage = np.array([pose.min(axis=0), pose.max(axis=0)]).T
    if (np.minimum(reference[:2]-coverage[:, 0], coverage[:, 1]-reference[:2]) < (4, 3)).any():
        raise ValueError("Head turns too small: repeat the head poses about 10–15° each way")
    if np.max(np.abs(medians[:, 4]-reference[2])) > 10:
        raise ValueError("Keep head level while turning; avoid sideways tilt")
    design = np.column_stack((np.ones(len(pose)), pose-reference[:2]))
    if np.linalg.cond(design) > 40:
        raise ValueError("Head yaw and pitch need separate, repeatable movements")
    coefficients = np.linalg.lstsq(design, medians[:, :2], rcond=None)[0]
    residual = np.max(np.abs(design @ coefficients-medians[:, :2]))
    if residual > .02 or np.max(np.abs(coefficients[1:])) > .03:
        raise ValueError("Center gaze changed too much during head turns; keep looking at the fixed dot")
    return dict(space=SPACE, measurement=MEASUREMENT, reference_pose=reference.tolist(),
                pose_bounds=coverage.tolist(), slopes=coefficients[1:].T.tolist(),
                center=coefficients[0].tolist(), low=None, high=None, checks={})


def fit_endpoints(model, groups):
    result = deepcopy(model)
    limits = {}
    for name in ("left", "right", "up", "down"):
        corrected = [compensate(model, v[:2], v[2:])[0] for v in groups[name]]
        if any(v is None for v in corrected):
            raise ValueError("Head moved outside the learned range during eye directions")
        limits[name] = np.median(corrected, axis=0)
    result["low"] = [float(limits["left"][0]), float(limits["up"][1])]
    result["high"] = [float(limits["right"][0]), float(limits["down"][1])]
    if min(*(c-lo for c, lo in zip(result["center"], result["low"])),
           *(hi-c for hi, c in zip(result["high"], result["center"]))) < MIN_RANGE:
        raise ValueError("Eye directions are too similar or reversed; restart and use comfortable distinct limits")
    return result
