"""Local assets are relative to the checkout, not the launcher's working directory."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "Vision" / ".local" / "face_landmarker.task"
PROFILE_DIRECTORY = ROOT / "local-profiles"
