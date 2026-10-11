"""Image evidence and explicit units for the detector-only workbench.

Scores are transparent heuristic quality scores, not calibrated probabilities.
OpenCV/numpy are lazy imports so the existing stdlib-only Vision APIs still work.
"""

from dataclasses import asdict, dataclass, field
import math
from statistics import median

from .landmarks import EYES


@dataclass(frozen=True)
class DetectionConfig:
    settle_ms: float = 1000
    collect_ms: float = 1800
    eye_rest_ms: float = 3000
    movement_rest_ms: float = 1500
    min_samples: int = 12
    stale_ms: float = 250
    min_face_px: float = 80
    min_eye_px: float = 12
    min_focus: float = 12
    min_brightness: float = 20
    max_brightness: float = 235
    max_clipped_fraction: float = 0.5
    eye_separation: float = 0.015
    endpoint_tolerance: float = 0.05
    head_mode: str = "pitch"
    head_position_separation: float = 0.02
    head_pitch_separation: float = 3
    head_yaw_separation: float = 3
    tongue_position_separation: float = 0.04
    position_check_tolerance: float = 0.2
    min_mouth_px: float = 28
    min_mouth_opening: float = 0.07
    tongue_tip_min_extension: float = 0.10
    tongue_tip_fit_error: float = 0.025
    tongue_tip_max_speed: float = 6
    tongue_margin: float = 4
    tongue_min_area: float = 0.025
    tongue_max_area: float = 0.8
    tongue_ambiguity: float = 0.35

    def __post_init__(self):
        bounds = {
            "settle_ms": (0, 5000), "collect_ms": (300, 10000),
            "eye_rest_ms": (0, 30000),
            "movement_rest_ms": (0, 30000),
            "stale_ms": (80, 2000), "min_face_px": (20, 500),
            "min_eye_px": (4, 100), "min_focus": (1, 1000),
            "min_brightness": (0, 120), "max_brightness": (130, 255),
            "max_clipped_fraction": (0.05, 0.9), "eye_separation": (0.001, 0.2),
            "endpoint_tolerance": (0, 0.1), "head_position_separation": (0.005, 0.2),
            "head_pitch_separation": (1, 30), "head_yaw_separation": (1, 30), "min_mouth_px": (12, 200),
            "tongue_position_separation": (0.01, 0.3), "position_check_tolerance": (0.05, 0.35),
            "min_mouth_opening": (0.02, 0.5), "tongue_margin": (1, 30),
            "tongue_min_area": (0.005, 0.3), "tongue_max_area": (0.4, 0.95),
            "tongue_ambiguity": (0.1, 0.9),
            "tongue_tip_min_extension": (0.08, 0.4),
            "tongue_tip_fit_error": (0.005, 0.08),
            "tongue_tip_max_speed": (1, 30),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be a finite number in [{low}, {high}]")
        if type(self.min_samples) is not int or not 5 <= self.min_samples <= 200:
            raise ValueError("min_samples must be an integer in [5, 200]")
        if self.head_mode not in ("position", "pitch"):
            raise ValueError("head_mode must be position or pitch")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Detection settings must be an object")
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError(f"Unknown detection setting: {exc}") from exc


@dataclass
class Feature:
    value: object = None
    quality: float = 0
    reason: str = "Unavailable"
    metrics: dict = field(default_factory=dict)


def rotation_from_matrix(matrix):
    """Remove uniform scale from MediaPipe's canonical-to-camera transform."""
    import numpy as np
    try:
        value = np.asarray(matrix, dtype=float)
        if value.shape != (4, 4) or not np.isfinite(value).all():
            return None
        u, scales, vt = np.linalg.svd(value[:3, :3])
        if scales.min() < 1e-6 or scales.max() / scales.min() > 1.2:
            return None
        rotation = u @ vt
        if np.linalg.det(rotation) < 0.99:
            return None
        return tuple(tuple(float(v) for v in row) for row in rotation)
    except (TypeError, ValueError, np.linalg.LinAlgError):
        return None


def pitch_degrees(rotation):
    """Camera-frame pitch proxy in degrees; calibration establishes up/down sign."""
    if rotation is None:
        return None
    return math.degrees(math.atan2(-rotation[1][2], math.hypot(rotation[0][2], rotation[2][2])))


def yaw_degrees(rotation):
    """Horizontal face-forward direction; calibration establishes left/right sign."""
    if rotation is None:
        return None
    x, z = rotation[0][2], rotation[2][2]
    if not math.isfinite(x) or not math.isfinite(z) or math.hypot(x, z) < 1e-6:
        return None
    angle = math.degrees(math.atan2(x, z))
    return angle if abs(angle) <= 90 else None


def image_quality(bgr, bounds, config):
    import cv2
    import numpy as np
    height, width = bgr.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in bounds)
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height or x1 - x0 < 4 or y1 - y0 < 4:
        return Feature(reason="Region is outside the image or too small")
    gray = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    focus = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    clipped = float(np.mean((gray < 5) | (gray > 250)))
    metrics = {"brightness": brightness, "focus": focus, "clipped_fraction": clipped}
    if not config.min_brightness <= brightness <= config.max_brightness:
        return Feature(reason="Region is too dark or bright", metrics=metrics)
    if clipped > config.max_clipped_fraction:
        return Feature(reason="Too many clipped pixels", metrics=metrics)
    if focus < config.min_focus:
        return Feature(reason="Region lacks sharp detail", metrics=metrics)
    # Passing the gates is necessary. Support above them determines the score.
    score = min(1.0, focus / (4 * config.min_focus), (1 - clipped) / 0.8)
    return Feature(quality=float(score), reason="Image gates passed", metrics=metrics)


def analyze_features(bgr, observation, config):
    """Independent lid measurements do not require visible iris landmarks."""
    height, width = bgr.shape[:2]
    points = observation.points
    result = {}
    box = observation.box
    face = image_quality(bgr, (box.x * width, box.y * height,
                              (box.x + box.width) * width, (box.y + box.height) * height), config)
    if box.width * width < config.min_face_px:
        face = Feature(reason="Face is too small")
    for side, (corners, pairs, _) in EYES.items():
        feature = Feature(reason="Eyelid landmarks unavailable")
        if len(points) > max((*corners, *(i for pair in pairs for i in pair))):
            left, right = (points[i] for i in corners)
            eye_width = math.dist(left, right)
            lids = [points[i] for pair in pairs for i in pair]
            visible = all(0 <= x < width and 0 <= y < height for x, y in [left, right, *lids])
            if visible and eye_width >= config.min_eye_px:
                value = median(math.dist(points[a], points[b]) for a, b in pairs) / eye_width
                cx, cy = (left[0] + right[0]) / 2, (left[1] + right[1]) / 2
                feature = image_quality(bgr, (cx - eye_width * 0.7, cy - eye_width * 0.45,
                                             cx + eye_width * 0.7, cy + eye_width * 0.45), config)
                feature.value = value
                feature.metrics["width_px"] = eye_width
                if not 0 <= value <= 0.65:
                    feature.quality, feature.reason = 0, "Implausible eyelid geometry"
                if face.quality == 0:
                    feature.quality, feature.reason = 0, face.reason
            else:
                feature.reason = "Eye is too small or outside the image"
        result[side] = feature
    head = Feature(quality=face.quality, reason=face.reason, metrics=dict(face.metrics))
    if config.head_mode == "position":
        if len(points) > 168 and 0 <= points[168][1] < height:
            head.value = points[168][1] / height
        else:
            head.quality, head.reason = 0, "Nose bridge unavailable"
    else:
        head.value = pitch_degrees(observation.rotation)
        if head.value is None:
            head.quality, head.reason = 0, "Head transformation unavailable"
    result["head"] = head
    yaw = Feature(value=yaw_degrees(observation.rotation), quality=face.quality,
                  reason=face.reason, metrics=dict(face.metrics))
    if yaw.value is None:
        yaw.quality, yaw.reason = 0, "Head yaw transformation unavailable or unsupported"
    result["head_x"] = yaw
    result["face"] = face
    return result
