"""Mouse-only signal processing; no camera or OS input dependencies."""

from .config import MouseConfig
from .engine import MouseProcessor

__all__ = ["MouseConfig", "MouseProcessor"]
