"""Read-only v1–v10 validation. Retired tongue state is never activated."""

from dataclasses import replace

import numpy as np

from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig
from .signals import finite_number
from .tongue import TongueModel, TONGUE_MEASUREMENT

LEGACY_ALGORITHM = "lid-gap-head-y-lab-color-v1"
ALGORITHM = "guided-lid-gap-head-y-lab-color-v2"
WINK_ALGORITHM = "frame-wink-eye-head-tongue-v3"
MOVEMENT_ALGORITHM = "personal-head-tongue-ranges-v4"
TIP_ALGORITHM = "color-tongue-tip-v5"
JOYSTICK_ALGORITHM = "tongue-segmentation-pupil-joystick-v6"
HEAD_AXES_ALGORITHM = "independent-head-axes-v7"
DIRECT_PUPIL_ALGORITHM = "direct-mediapipe-pupils-v8"
LIP_BOUNDARY_ALGORITHM = "lip-boundary-head-reliability-v9"
PUPIL_MATRIX_ALGORITHM = "fixed-pupil-matrix-v10"


def decode_winks(data):
    from .wink_model import validate_models
    return validate_models(data["winks"]) if data.get("version") in (3,4,5,6,7,8,9,10) else {}


def decode_tongue_range(data, config):
    from .movement_guide import validate_range
    return validate_range(data["tongue_range"],config) if data.get("version") in (5,6,7,8,9,10) else None


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name} has missing or unknown fields")


def decode_preset(data):
    """Validate completely before the workbench changes any active state."""
    fields=("version", "algorithm", "settings", "eyes", "head", "tongue")
    if isinstance(data,dict) and data.get("version") in (3,4,5,6,7,8,9,10):fields+=("winks",)
    if isinstance(data,dict) and data.get("version") in (4,5,6,7,8,9,10):fields+=("tongue_range",)
    if isinstance(data,dict) and data.get("version") in (5,6,7,8,9,10):fields+=("tongue_measurement",)
    if isinstance(data,dict) and data.get("version") in (6,7,8,9,10): fields+=("pupil",)
    if isinstance(data,dict) and data.get("version") in (7,8,9,10): fields+=("head_x",)
    _keys(data, fields, "Detector preset")
    if (type(data["version"]) is not int
            or (data["version"], data["algorithm"]) not in ((1, LEGACY_ALGORITHM), (2, ALGORITHM), (3,WINK_ALGORITHM), (4,MOVEMENT_ALGORITHM), (5,TIP_ALGORITHM), (6,JOYSTICK_ALGORITHM), (7,HEAD_AXES_ALGORITHM), (8,DIRECT_PUPIL_ALGORITHM), (9,LIP_BOUNDARY_ALGORITHM), (10,PUPIL_MATRIX_ALGORITHM))):
        raise ValueError("Unsupported detector preset version or algorithm")
    settings = data["settings"]
    if isinstance(settings, dict):
        # Before pitch-only calibration, omitted mode meant image position.
        settings = dict(settings)
        settings.setdefault("head_mode", "position")
    config = DetectionConfig.from_dict(settings)
    from .tongue_segment import MEASUREMENT, MODEL_SHA256, SegmentedTongueModel
    from .lip_boundary import MEASUREMENT as LIP_MEASUREMENT, ALGORITHM as LIP_ALGORITHM, LipBoundaryModel
    allowed_measurements = (TONGUE_MEASUREMENT, MEASUREMENT) if data["version"] in (6,7,8,9,10) else (TONGUE_MEASUREMENT,)
    if data["version"] in (9,10): allowed_measurements += (LIP_MEASUREMENT,)
    if data["version"] in (5,6,7,8,9,10) and data["tongue_measurement"] not in allowed_measurements:
        raise ValueError("Unsupported tongue measurement coordinate space")
    if not isinstance(data["eyes"], dict) or set(data["eyes"]) - {"left", "right"}:
        raise ValueError("Unknown eye preset")
    eyes = {}
    for side, values in data["eyes"].items():
        fields = ("closed", "opened", "threshold") + (("closed_limit", "open_limit") if data["version"] >= 2 else ())
        _keys(values, fields, side + " eye")
        fit = EyeCalibration(**values)
        if fit.opened > .65 or fit.opened - fit.closed < config.eye_separation:
            raise ValueError("Eye preset range is invalid")
        eyes[side] = fit
    head = None
    if data["head"] is not None:
        _keys(data["head"], ("low", "center", "high", "endpoint_tolerance"), "Head fit")
        head = AxisCalibration(**data["head"])
        low, high, separation = (0, 1, config.head_position_separation) if config.head_mode == "position" else (-90, 90, config.head_pitch_separation)
        if (not all(low <= v <= high for v in (head.low, head.center, head.high))
                or min(abs(head.center-head.low), abs(head.high-head.center)) < separation
                or head.endpoint_tolerance != config.endpoint_tolerance):
            raise ValueError("Head preset range does not match settings")
    horizontal = decode_head_x(data, config)
    tongue = None
    pupil, _ = decode_pupil(data, config)
    decode_pupil_settings(data)
    neural = data.get("tongue_measurement") == MEASUREMENT
    if data.get("tongue_measurement") == LIP_MEASUREMENT:
        if data["tongue"] != {"backend":"lip-boundary", "algorithm":LIP_ALGORITHM}:
            raise ValueError("Unsupported lip-boundary detector identity")
        tongue = LipBoundaryModel()
    elif neural:
        _keys(data["tongue"], ("backend", "sha256"), "Tongue neural model")
        if data["tongue"] != {"backend": "yolov8n-seg", "sha256": MODEL_SHA256}:
            raise ValueError("Unsupported tongue model identity")
        tongue = SegmentedTongueModel()
    elif data["tongue"] is not None:
        values = data["tongue"]
        _keys(values, ("positive", "negative", "radius", "margin"), "Tongue fit")
        centers = []
        for key, limit in (("positive", 3), ("negative", 8)):
            raw = values[key]
            if (not isinstance(raw, list) or not 1 <= len(raw) <= limit
                    or any(not isinstance(row, list) or len(row) != 3
                           or any(not finite_number(v) for v in row) for row in raw)):
                raise ValueError("Invalid tongue color prototypes")
            array = np.asarray(raw, dtype=np.float32)
            if np.any(array < 0) or np.any(array > [89.25, 255, 255]):
                raise ValueError("Tongue color prototype is out of range")
            centers.append(array)
        if (not finite_number(values["radius"]) or not 6 <= values["radius"] <= 30
                or not finite_number(values["margin"]) or values["margin"] != config.tongue_margin):
            raise ValueError("Invalid tongue radius or margin")
        tongue = TongueModel(*centers, values["radius"], values["margin"], {"restored": True})
    if data["version"] < 8 and not eyes and head is None and horizontal is None and tongue is None and pupil is None:
        raise ValueError("Profile needs at least one fitted detector")
    winks=decode_winks(data)
    if set(winks)-set(eyes):raise ValueError("Wink model requires matching eye geometry")
    if data["version"] == 4:
        from .movement_guide import validate_range
        old_range = validate_range(data["tongue_range"],config,bounds=(0,1))
        if old_range is not None and tongue is None:
            raise ValueError("Legacy tongue range requires its appearance model")
    if decode_tongue_range(data,config) is not None and tongue is None:
        raise ValueError("Tongue movement range requires an appearance model")
    if config.head_mode == "position":
        config, head = replace(config, head_mode="pitch"), None
    # Expanded negatives and front-edge coordinates cannot reuse an inner-mouth fit.
    return config, eyes, head, tongue if data["version"] in (5,6,7,8,9,10) else None


def decode_head_x(data, config):
    if data.get("version") not in (7,8,9,10):
        return None
    if config.head_mode != "pitch":
        raise ValueError("Head-axis presets require pitch-mode vertical calibration")
    if data["head_x"] is None:
        return None
    _keys(data["head_x"], ("low", "center", "high", "endpoint_tolerance"), "Head X fit")
    fit = AxisCalibration(**data["head_x"])
    if (not all(-90 <= value <= 90 for value in (fit.low, fit.center, fit.high))
            or min(abs(fit.center-fit.low), abs(fit.high-fit.center)) < config.head_yaw_separation
            or fit.endpoint_tolerance != config.endpoint_tolerance):
        raise ValueError("Head X preset range does not match settings")
    return fit


def decode_pupil(data, config):
    if data.get("version") not in (6,7) or data.get("pupil") is None:
        return None, None
    from .movement_guide import validate_range
    values = data["pupil"]
    _keys(values, ("range", "pose"), "Pupil calibration")
    fit = validate_range(values["range"], config, bounds=(-.5,.5), separation=.015, label="Pupil")
    pose = values["pose"]
    if fit is None or not isinstance(pose, list) or len(pose) != 3 or any(not finite_number(v) or abs(v)>180 for v in pose):
        raise ValueError("Invalid pupil range or head-pose reference")
    return fit, tuple(pose)


def decode_pupil_settings(data):
    from .pupil import MEASUREMENT
    values = data.get("pupil")
    if data.get("version") in (8,9):
        _keys(values, ("measurement", "x_sensitivity", "y_sensitivity"), "Legacy pupil settings")
        if values["measurement"] != "mediapipe_iris_direction_v2":
            raise ValueError("Unsupported legacy pupil measurement")
        if any(not finite_number(values[k]) or not .25 <= values[k] <= 4
               for k in ("x_sensitivity", "y_sensitivity")):
            raise ValueError("Invalid legacy pupil sensitivity")
    elif data.get("version") == 10:
        _keys(values, ("measurement",), "Fixed pupil identity")
        if values["measurement"] != MEASUREMENT:
            raise ValueError("Unsupported fixed pupil measurement")
    # Old valid settings are deliberately discarded, never applied.
