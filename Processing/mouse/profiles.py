"""Atomic local unified-profile storage. Detector validation belongs to Vision/App."""

import json
import os
from pathlib import Path
import tempfile

from .config import MouseConfig, number

FORMAT = "face_mouse_profile_v1"
MAX_BYTES = 262144


def validate_profile(data):
    fields = {"format", "source_kind", "detector", "processing", "preview"}
    if not isinstance(data, dict) or set(data) != fields or data["format"] != FORMAT:
        raise ValueError("Expected a face_mouse_profile_v1 with detector and processing sections")
    if data["source_kind"] not in ("camera", "synthetic"):
        raise ValueError("Unknown profile source kind")
    if not isinstance(data["detector"], dict):
        raise ValueError("Detector preset must be an object")
    MouseConfig.from_dict(data["processing"])
    if not isinstance(data["preview"], dict) or set(data["preview"]) != {"pointer_speed", "scroll_speed"}:
        raise ValueError("Profile preview must contain pointer_speed and scroll_speed")
    number(data["preview"]["pointer_speed"], "pointer_speed", 50, 2500)
    number(data["preview"]["scroll_speed"], "scroll_speed", 20, 1500)
    return data


def read_profile(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Profile exceeds 256 KiB")
    try:
        return validate_profile(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Profile is not valid JSON") from exc


def write_profile(path, data):
    validate_profile(data)
    encoded = json.dumps(data, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    if len(encoded) > MAX_BYTES:
        raise ValueError("Profile exceeds 256 KiB")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".profile-", delete=False) as handle:
            temporary = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
