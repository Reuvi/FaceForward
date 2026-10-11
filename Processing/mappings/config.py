"""Versioned gaming mappings, separate from detector/face profiles."""

from dataclasses import asdict, dataclass, field, replace
import json
import os
from pathlib import Path
import re
import tempfile

from Processing.mouse.config import MouseConfig, number

GAMING_ID = "gaming-keyboard-mouse-1"
MOUSE_TEST_ID = "mouse-test"
KEYS = ("w", "a", "s", "d", "space", "left_shift")
DIRECTIONS = ("down", "up", "left", "right")
DEFAULT_BINDINGS = ("w", "space", "left_shift", "s")


@dataclass(frozen=True)
class HeadMotionConfig:
    enabled: bool = False
    speed_gain: float = .75
    return_brake: float = .65

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Head motion response must be boolean")
        number(self.speed_gain, "head motion speed gain", 0, 2)
        number(self.return_brake, "head return braking", 0, 1)


@dataclass(frozen=True)
class HeadConfig:
    activation: float = .30
    release: float = .18
    smoothing_ms: float = 40
    confirmation_ms: float = 50

    def __post_init__(self):
        number(self.activation, "head activation", .01, 1)
        number(self.release, "head release", 0, .99)
        if self.release >= self.activation:
            raise ValueError("Head release must be below activation")
        number(self.smoothing_ms, "head smoothing_ms", 0, 500)
        number(self.confirmation_ms, "head confirmation_ms", 0, 1000)


def gaming_response():
    config = MouseConfig(pointer_source="gaze")
    return replace(config, pointer=replace(config.pointer, boost_gain=0))


@dataclass(frozen=True)
class Mapping:
    id: str = GAMING_ID
    name: str = "gaming keyboard mouse mapping 1"
    revision: int = 1
    response: MouseConfig = field(default_factory=gaming_response)
    pointer_gain: float = 2
    head_x: HeadConfig = field(default_factory=HeadConfig)
    head_y: HeadConfig = field(default_factory=HeadConfig)
    bindings: tuple = DEFAULT_BINDINGS
    input_mode: str = "gaming"
    adaptive_pointer: bool = True
    pointer_mode: str = "target"
    target_jitter: float = .002
    pointer_down_gain: float = 4
    target_smoothing_ms: float = 20
    target_interpolation_ms: float = 0
    head_motion: HeadMotionConfig = field(default_factory=HeadMotionConfig)

    def __post_init__(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.id) or self.id == "mouse":
            raise ValueError("Mapping ID must be 1–64 lowercase letters/digits/hyphens, starting with a letter")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100 or any(ord(c) < 32 for c in self.name):
            raise ValueError("Mapping name must be readable text of 1–100 characters")
        if type(self.revision) is not int or not 1 <= self.revision <= 1000000:
            raise ValueError("Mapping revision must be a positive integer")
        if not isinstance(self.response, MouseConfig) or self.response.pointer_source != "gaze":
            raise ValueError("Gaming mappings use pupil/gaze input")
        number(self.pointer_gain, "pointer gain", .1, 4)
        if not isinstance(self.head_x, HeadConfig) or not isinstance(self.head_y, HeadConfig):
            raise ValueError("Both head axes need independent settings")
        if type(self.bindings) is not tuple or len(self.bindings) != 4 or any(v not in KEYS + ("none",) for v in self.bindings):
            raise ValueError("Head bindings must use supported keys or none")
        if self.input_mode not in ("gaming", "head-mouse"):
            raise ValueError("Unknown mapping input mode")
        if self.input_mode == "head-mouse" and self.bindings != ("none",) * 4:
            raise ValueError("Head mouse mappings cannot assign keyboard actions")
        if type(self.adaptive_pointer) is not bool:
            raise ValueError("Adaptive pointer must be boolean")
        if self.pointer_mode not in ("velocity", "target"):
            raise ValueError("Pointer mode must be velocity or target")
        if self.input_mode == "head-mouse" and self.pointer_mode != "velocity":
            raise ValueError("Mouse test uses head velocity")
        number(self.target_jitter, "target jitter", 0, .1)
        number(self.pointer_down_gain, "downward pointer gain", 1, 8)
        number(self.target_smoothing_ms, "target smoothing_ms", 0, 1000)
        number(self.target_interpolation_ms, "target interpolation_ms", 0, 250)
        if self.target_interpolation_ms >= self.response.stale_ms:
            raise ValueError("Target interpolation must be smaller than stale_ms")
        if not isinstance(self.head_motion, HeadMotionConfig):
            raise ValueError("Head motion needs independent settings")
        if self.head_motion.enabled and self.input_mode != "head-mouse":
            raise ValueError("Head motion response applies only to head mouse mappings")

    def to_dict(self):
        return {"format": "input_mapping_v5", "id": self.id, "name": self.name,
                "revision": self.revision, "response": self.response.to_dict(),
                "pointer_gain": self.pointer_gain, "head_x": asdict(self.head_x),
                "head_y": asdict(self.head_y), "bindings": dict(zip(DIRECTIONS, self.bindings)),
                "input_mode": self.input_mode, "adaptive_pointer": self.adaptive_pointer,
                "pointer_mode": self.pointer_mode, "target_jitter": self.target_jitter,
                "pointer_down_gain": self.pointer_down_gain,
                "target_smoothing_ms": self.target_smoothing_ms,
                "target_interpolation_ms": self.target_interpolation_ms,
                "head_motion": asdict(self.head_motion)}

    @classmethod
    def from_dict(cls, data):
        fields = {"format", "id", "name", "revision", "response", "pointer_gain", "head_x", "head_y", "bindings"}
        if not isinstance(data, dict):
            raise ValueError("Expected an input_mapping_v1/v2/v3/v4/v5 file")
        version = data.get("format")
        if version in ("input_mapping_v2", "input_mapping_v3", "input_mapping_v4", "input_mapping_v5"):
            fields |= {"input_mode", "adaptive_pointer"}
        if version in ("input_mapping_v3", "input_mapping_v4", "input_mapping_v5"):
            fields |= {"pointer_mode", "target_jitter"}
        if version in ("input_mapping_v4", "input_mapping_v5"):
            fields |= {"pointer_down_gain", "target_smoothing_ms", "target_interpolation_ms"}
        if version == "input_mapping_v5":
            fields.add("head_motion")
        if set(data) != fields or version not in ("input_mapping_v1", "input_mapping_v2", "input_mapping_v3", "input_mapping_v4", "input_mapping_v5"):
            raise ValueError("Expected an input_mapping_v1/v2/v3/v4/v5 file")
        if version == "input_mapping_v5" and (not isinstance(data["head_motion"], dict) or
                set(data["head_motion"]) != {"enabled", "speed_gain", "return_brake"}):
            raise ValueError("Malformed head motion settings")
        if not isinstance(data["bindings"], dict) or set(data["bindings"]) != set(DIRECTIONS):
            raise ValueError("Mapping needs down/up/left/right bindings")
        try:
            response = MouseConfig.from_dict(data["response"])
            return cls(data["id"], data["name"], data["revision"], response,
                       data["pointer_gain"], HeadConfig(**data["head_x"]), HeadConfig(**data["head_y"]),
                       tuple(data["bindings"][k] for k in DIRECTIONS),
                       data.get("input_mode", "gaming"), data.get("adaptive_pointer", True),
                       data.get("pointer_mode", "velocity"), data.get("target_jitter", .01),
                       data.get("pointer_down_gain", 1),
                       data.get("target_smoothing_ms", response.pointer.smoothing_ms),
                       data.get("target_interpolation_ms", response.interpolation_ms),
                       HeadMotionConfig(**data.get("head_motion", {})))
        except TypeError as exc:
            raise ValueError("Malformed mapping settings") from exc


def mouse_test_mapping():
    response = gaming_response()
    response = replace(response, interpolation_ms=0, pointer=replace(response.pointer,
                       deadzone=.10, hysteresis=.02, smoothing_ms=20,
                       exponent=1.2, acceleration=10, deceleration=14))
    return Mapping(id=MOUSE_TEST_ID, name="Mouse test", input_mode="head-mouse", pointer_mode="velocity",
                   bindings=("none",) * 4, pointer_gain=1, pointer_down_gain=3, response=response,
                   head_motion=HeadMotionConfig(enabled=True))


def read_mapping(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Mapping file exceeds 64 KiB")
    try:
        return Mapping.from_dict(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Mapping file is not valid JSON") from exc


def write_mapping(path, mapping):
    data = Mapping.from_dict(mapping.to_dict()).to_dict()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".mapping-", delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
