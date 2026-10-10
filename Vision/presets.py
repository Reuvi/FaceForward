"""Versioned detector parameter serialization; no identity or capture data."""

from dataclasses import asdict

import numpy as np

from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig
from .signals import finite_number
from .tongue import TongueModel

ALGORITHM = "lid-gap-head-y-lab-color-v1"


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name} has missing or unknown fields")


def decode_preset(data):
    """Validate completely before the workbench changes any active state."""
    _keys(data, ("version", "algorithm", "settings", "eyes", "head", "tongue"), "Detector preset")
    if type(data["version"]) is not int or data["version"] != 1 or data["algorithm"] != ALGORITHM:
        raise ValueError("Unsupported detector preset version or algorithm")
    config = DetectionConfig.from_dict(data["settings"])
    if not isinstance(data["eyes"], dict) or set(data["eyes"]) - {"left", "right"}:
        raise ValueError("Unknown eye preset")
    eyes = {}
    for side, values in data["eyes"].items():
        _keys(values, ("closed", "opened", "threshold"), side + " eye")
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
    return config, eyes, head, tongue


def encode_preset(core):
    result = {"version": 1, "algorithm": ALGORITHM, "settings": core.config.to_dict(),
              "eyes": {side: {name: getattr(fit, name) for name in ("closed", "opened", "threshold")}
                       for side, fit in core.eyes.items()},
              "head": asdict(core.head) if core.head else None, "tongue": None}
    if core.tongue_model:
        model = core.tongue_model
        result["tongue"] = {"positive": model.positive.tolist(), "negative": model.negative.tolist(),
                            "radius": model.radius, "margin": model.margin}
    decode_preset(result)
    return result
