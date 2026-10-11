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
    pointer_gain: float = 1
    head_x: HeadConfig = field(default_factory=HeadConfig)
    head_y: HeadConfig = field(default_factory=HeadConfig)
    bindings: tuple = DEFAULT_BINDINGS
    input_mode: str = "gaming"
    adaptive_pointer: bool = True

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

    def to_dict(self):
        return {"format": "input_mapping_v2", "id": self.id, "name": self.name,
                "revision": self.revision, "response": self.response.to_dict(),
                "pointer_gain": self.pointer_gain, "head_x": asdict(self.head_x),
                "head_y": asdict(self.head_y), "bindings": dict(zip(DIRECTIONS, self.bindings)),
                "input_mode": self.input_mode, "adaptive_pointer": self.adaptive_pointer}

    @classmethod
    def from_dict(cls, data):
        fields = {"format", "id", "name", "revision", "response", "pointer_gain", "head_x", "head_y", "bindings"}
        if not isinstance(data, dict):
            raise ValueError("Expected an input_mapping_v1 or input_mapping_v2 file")
        version = data.get("format")
        if version == "input_mapping_v2":
            fields |= {"input_mode", "adaptive_pointer"}
        if set(data) != fields or version not in ("input_mapping_v1", "input_mapping_v2"):
            raise ValueError("Expected an input_mapping_v1 or input_mapping_v2 file")
        if not isinstance(data["bindings"], dict) or set(data["bindings"]) != set(DIRECTIONS):
            raise ValueError("Mapping needs down/up/left/right bindings")
        try:
            return cls(data["id"], data["name"], data["revision"], MouseConfig.from_dict(data["response"]),
                       data["pointer_gain"], HeadConfig(**data["head_x"]), HeadConfig(**data["head_y"]),
                       tuple(data["bindings"][k] for k in DIRECTIONS),
                       data.get("input_mode", "gaming"), data.get("adaptive_pointer", True))
        except TypeError as exc:
            raise ValueError("Malformed mapping settings") from exc


def mouse_test_mapping():
    return Mapping(id=MOUSE_TEST_ID, name="Mouse test", input_mode="head-mouse",
                   bindings=("none",) * 4,
                   response=replace(gaming_response(), interpolation_ms=0))


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
