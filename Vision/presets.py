"""Current eyes/head/pupil presets, with read-only legacy migration."""

from dataclasses import asdict

from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig
from .pupil import MEASUREMENT

ALGORITHM = "eyes-head-pupils-v11"


def decode_winks(data):
    from .wink_model import validate_models
    return validate_models(data["winks"]) if data.get("version", 0) >= 3 else {}


def _keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{name} has missing or unknown fields")


def decode_preset(data):
    """Validate before changing active state; never restore retired detectors."""
    if isinstance(data, dict) and type(data.get("version")) is int and 1 <= data["version"] <= 10:
        from .legacy_presets import decode_preset as decode_legacy
        config, eyes, head, _ = decode_legacy(data)
        config = DetectionConfig.from_dict(config.active_dict())
        return config, eyes, head, None
    _keys(data, ("version", "algorithm", "settings", "eyes", "winks", "head", "head_x", "pupil"), "Detector preset")
    if type(data["version"]) is not int or data["version"] != 11 or data["algorithm"] != ALGORITHM:
        raise ValueError("Unsupported detector preset version or algorithm")
    settings = data["settings"]
    _keys(settings, DetectionConfig().active_dict(), "Detector settings")
    config = DetectionConfig.from_dict(settings)
    if config.head_mode != "pitch":
        raise ValueError("Current head calibration requires pitch mode")
    _keys(data["pupil"], ("measurement",), "Fixed pupil identity")
    if data["pupil"]["measurement"] != MEASUREMENT:
        raise ValueError("Unsupported fixed pupil measurement")
    if not isinstance(data["eyes"], dict) or set(data["eyes"]) - {"left", "right"}:
        raise ValueError("Unknown eye preset")
    eyes = {}
    for side, values in data["eyes"].items():
        _keys(values, ("closed", "opened", "threshold", "closed_limit", "open_limit"), side + " eye")
        fit = EyeCalibration(**values)
        if fit.opened > .65 or fit.opened - fit.closed < config.eye_separation:
            raise ValueError("Eye preset range is invalid")
        eyes[side] = fit
    winks = decode_winks(data)
    if set(winks) - set(eyes):
        raise ValueError("Wink model requires matching eye geometry")
    head = None
    if data["head"] is not None:
        _keys(data["head"], ("low", "center", "high", "endpoint_tolerance"), "Head fit")
        head = AxisCalibration(**data["head"])
        if (not all(-90 <= value <= 90 for value in (head.low, head.center, head.high))
                or min(abs(head.center-head.low), abs(head.high-head.center)) < config.head_pitch_separation
                or head.endpoint_tolerance != config.endpoint_tolerance):
            raise ValueError("Head preset range does not match settings")
    decode_head_x(data, config)
    return config, eyes, head, None


def decode_head_x(data, config):
    if data.get("version") not in (7,8,9,10,11):
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


def encode_preset(core):
    result = {
        "version": 11, "algorithm": ALGORITHM, "settings": core.config.active_dict(),
        "eyes": {side: {name: getattr(fit, name) for name in ("closed", "opened", "threshold", "closed_limit", "open_limit")}
                 for side, fit in core.eyes.items()},
        "winks": core.winks,
        "head": asdict(core.head) if core.head else None,
        "head_x": asdict(core.head_x) if core.head_x else None,
        "pupil": {"measurement": MEASUREMENT},
    }
    decode_preset(result)
    return result
