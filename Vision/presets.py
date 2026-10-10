"""Versioned detector parameter serialization; no identity or capture data."""

from dataclasses import asdict, replace

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


def decode_winks(data):
    from .wink_model import validate_models
    return validate_models(data["winks"]) if data.get("version") in (3,4,5) else {}


def decode_tongue_range(data, config):
    from .movement_guide import validate_range
    return validate_range(data["tongue_range"],config) if data.get("version")==5 else None


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name} has missing or unknown fields")


def decode_preset(data):
    """Validate completely before the workbench changes any active state."""
    fields=("version", "algorithm", "settings", "eyes", "head", "tongue")
    if isinstance(data,dict) and data.get("version") in (3,4,5):fields+=("winks",)
    if isinstance(data,dict) and data.get("version") in (4,5):fields+=("tongue_range",)
    if isinstance(data,dict) and data.get("version")==5:fields+=("tongue_measurement",)
    _keys(data, fields, "Detector preset")
    if (type(data["version"]) is not int
            or (data["version"], data["algorithm"]) not in ((1, LEGACY_ALGORITHM), (2, ALGORITHM), (3,WINK_ALGORITHM), (4,MOVEMENT_ALGORITHM), (5,TIP_ALGORITHM))):
        raise ValueError("Unsupported detector preset version or algorithm")
    settings = data["settings"]
    if isinstance(settings, dict):
        # Before pitch-only calibration, omitted mode meant image position.
        settings = dict(settings)
        settings.setdefault("head_mode", "position")
    config = DetectionConfig.from_dict(settings)
    if data["version"]==5 and data["tongue_measurement"]!=TONGUE_MEASUREMENT:
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
    tongue = None
    if data["tongue"] is not None:
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
    if not eyes and head is None and tongue is None:
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
    return config, eyes, head, tongue if data["version"]==5 else None


def encode_preset(core):
    result = {"version": 5, "algorithm": TIP_ALGORITHM, "tongue_measurement": TONGUE_MEASUREMENT, "settings": core.config.to_dict(),
              "winks": core.winks,
              "tongue_range": {key:asdict(fit) for key,fit in core.tongue_range.items()} if core.tongue_range else None,
              "eyes": {side: {name: getattr(fit, name) for name in ("closed", "opened", "threshold", "closed_limit", "open_limit")}
                       for side, fit in core.eyes.items()},
              "head": asdict(core.head) if core.head else None, "tongue": None}
    if core.tongue_model:
        model = core.tongue_model
        result["tongue"] = {"positive": model.positive.tolist(), "negative": model.negative.tolist(),
                            "radius": model.radius, "margin": model.margin}
    decode_preset(result)
    return result
