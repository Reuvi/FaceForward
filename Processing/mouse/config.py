"""Validated, JSON-serializable settings. All time settings are milliseconds."""

from dataclasses import asdict, dataclass, field
import math


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


@dataclass(frozen=True)
class AxisConfig:
    deadzone: float = 0.16
    hysteresis: float = 0.03
    exponent: float = 1.6
    smoothing_ms: float = 90.0
    acceleration: float = 5.0
    deceleration: float = 8.0
    jump_threshold: float = 0.25
    boost_gain: float = 0.04
    boost_max: float = 0.5
    boost_decay_ms: float = 350.0
    center_x: float = 0.5
    center_y: float = 0.5
    invert_x: bool = False
    invert_y: bool = False

    def __post_init__(self):
        bounds = {
            "deadzone": (0, 0.8), "hysteresis": (0, 0.15), "exponent": (0.2, 5),
            "smoothing_ms": (0, 1000), "acceleration": (0.1, 100),
            "deceleration": (0.1, 100), "jump_threshold": (0, 2),
            "boost_gain": (0, 1), "boost_max": (0, 3), "boost_decay_ms": (1, 2000),
            "center_x": (0.05, 0.95), "center_y": (0.05, 0.95),
        }
        for name, (low, high) in bounds.items():
            number(getattr(self, name), name, low, high)
        for name in ("invert_x", "invert_y"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")


@dataclass(frozen=True)
class EyeConfig:
    dwell_ms: float = 320.0
    release_ms: float = 60.0

    def __post_init__(self):
        number(self.dwell_ms, "dwell_ms", 50, 3000)
        number(self.release_ms, "release_ms", 0, 500)


@dataclass(frozen=True)
class MouseConfig:
    mode: str = "mouse"
    closed_value: int = 1
    left_eye: EyeConfig = field(default_factory=EyeConfig)
    right_eye: EyeConfig = field(default_factory=EyeConfig)
    pointer_source: str = "tongue"
    interpolation_ms: float = 50.0
    stale_ms: float = 250.0
    min_confidence: float = 0.5
    pointer: AxisConfig = field(default_factory=AxisConfig)
    scroll: AxisConfig = field(default_factory=lambda: AxisConfig(deadzone=0.22, exponent=1.8))

    def __post_init__(self):
        if self.mode != "mouse":
            raise ValueError("Only mouse mode is implemented")
        if type(self.closed_value) is not int or self.closed_value not in (0, 1):
            raise ValueError("closed_value must be 0 or 1")
        if self.pointer_source not in ("tongue", "gaze"):
            raise ValueError("pointer_source must be tongue or gaze")
        for name, low, high in (
            ("interpolation_ms", 0, 250), ("stale_ms", 80, 2000),
            ("min_confidence", 0, 1),
        ):
            number(getattr(self, name), name, low, high)
        if self.interpolation_ms >= self.stale_ms:
            raise ValueError("interpolation_ms must be smaller than stale_ms")
        if not isinstance(self.pointer, AxisConfig) or not isinstance(self.scroll, AxisConfig):
            raise ValueError("pointer and scroll must be AxisConfig settings")
        if not isinstance(self.left_eye, EyeConfig) or not isinstance(self.right_eye, EyeConfig):
            raise ValueError("left_eye and right_eye must be EyeConfig settings")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Settings must be a JSON object")
        values = dict(data)
        try:
            for name in ("pointer", "scroll"):
                if name in values:
                    if not isinstance(values[name], dict):
                        raise ValueError(f"{name} must be an object")
                    values[name] = AxisConfig(**values[name])
            for name in ("left_eye", "right_eye"):
                if name in values:
                    if not isinstance(values[name], dict):
                        raise ValueError(f"{name} must be an object")
                    values[name] = EyeConfig(**values[name])
            return cls(**values)
        except TypeError as exc:
            raise ValueError(f"Unknown or malformed setting: {exc}") from exc
