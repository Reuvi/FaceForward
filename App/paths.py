"""Local assets are relative to the checkout, not the launcher's working directory."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "Vision" / ".local" / "face_landmarker.task"
PROFILE_DIRECTORY = ROOT / "local-profiles"

# The speech bundle must live outside cloud-synced Desktop directories so macOS
# signing is not invalidated by File Provider FinderInfo metadata. Per-checkout.
import hashlib
DICTATION_BUNDLE = (Path.home()/"Library/Caches/FaceController"/
                    hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]/"FaceControllerDictation.app")
