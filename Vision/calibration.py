"""In-memory detection calibration; profile persistence belongs to Processing."""

from dataclasses import dataclass
from statistics import median

from .signals import finite_number, invalid, measurement, unit_number


def _samples(values):
    values = list(values)
    if len(values) < 5 or not all(finite_number(value) for value in values):
        raise ValueError("provide at least five finite observations per target")
    center = median(values)
    mad = median(abs(value - center) for value in values)
    # Exact repeated samples are common in synthetic calibration.
    radius = max(3 * 1.4826 * mad, 1e-9)
    kept = [value for value in values if abs(value - center) <= radius]
    if len(kept) < 5 or len(kept) < 0.8 * len(values):
        raise ValueError("calibration samples are too unstable")
    return kept


@dataclass(frozen=True)
class AxisCalibration:
    low: float
    center: float
    high: float
    endpoint_tolerance: float = 0.0

    def __post_init__(self):
        if not all(finite_number(v) for v in (self.low, self.center, self.high)):
            raise ValueError("calibration must be finite")
        if not (self.low < self.center < self.high or self.low > self.center > self.high):
            raise ValueError("center must be strictly between distinct endpoints")
        if min(abs(self.center - self.low), abs(self.high - self.center)) < 1e-6:
            raise ValueError("calibration range is too small")
        if not unit_number(self.endpoint_tolerance) or self.endpoint_tolerance > 0.1:
            raise ValueError("endpoint tolerance must be in [0, 0.1]")

    @classmethod
    def fit(cls, low, center, high, *, min_separation):
        if not finite_number(min_separation) or min_separation <= 0:
            raise ValueError("min_separation must be positive")
        groups = [_samples(values) for values in (low, center, high)]
        result = cls(*(median(group) for group in groups))
        direction = 1 if result.high > result.low else -1
        ordered = [[direction * value for value in group] for group in groups]
        if any(min(b) - max(a) < min_separation for a, b in zip(ordered, ordered[1:])):
            raise ValueError("calibration targets overlap or have insufficient range")
        return result

    def normalize(self, raw):
        if not finite_number(raw):
            return None
        direction = 1 if self.high > self.low else -1
        if direction * (raw - self.center) < 0:
            value = 0.5 * (raw - self.low) / (self.center - self.low)
        else:
            value = 0.5 + 0.5 * (raw - self.center) / (self.high - self.center)
        if value < -self.endpoint_tolerance or value > 1 + self.endpoint_tolerance:
            return None
        return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class EyeCalibration:
    closed: float
    opened: float
    threshold: float
    gaze_x: AxisCalibration | None = None
    gaze_y: AxisCalibration | None = None

    def __post_init__(self):
        if not all(finite_number(v) for v in (self.closed, self.opened)):
            raise ValueError("eye calibration must be finite")
        if self.closed < 0 or self.opened - self.closed < 1e-6:
            raise ValueError("open ratio must exceed closed ratio")
        if not unit_number(self.threshold) or self.threshold in (0, 1):
            raise ValueError("open threshold must be between 0 and 1")

    @classmethod
    def fit(cls, closed, opened, *, min_separation, gaze_x=None, gaze_y=None):
        if not finite_number(min_separation) or min_separation <= 0:
            raise ValueError("min_separation must be positive")
        closed, opened = _samples(closed), _samples(opened)
        if min(opened) - max(closed) < min_separation:
            raise ValueError("open/closed samples overlap or are insufficiently separated")
        low, high = median(closed), median(opened)
        boundary = (max(closed) + min(opened)) / 2
        return cls(low, high, (boundary - low) / (high - low), gaze_x, gaze_y)

    def classify(self, ratio, quality):
        if not finite_number(ratio) or ratio < 0:
            return invalid()
        score = max(0.0, min(1.0, (ratio - self.closed) / (self.opened - self.closed)))
        return measurement(1 if score >= self.threshold else 0, quality)


def calibrated_eye(ratios, calibration, quality):
    """Quality must come from validated observation gates, not task thresholds."""
    result = {"open": invalid(), "gaze_x": invalid(), "gaze_y": invalid()}
    if ratios is None or calibration is None:
        return result
    result["open"] = calibration.classify(ratios.openness, quality)
    if not result["open"]["valid"] or result["open"]["value"] != 1:
        return result
    for name, raw in (("gaze_x", ratios.horizontal), ("gaze_y", ratios.vertical)):
        axis = getattr(calibration, name)
        if axis is not None:
            result[name] = measurement(axis.normalize(raw), quality)
    return result


def combine_gaze(left, right, *, disagreement_tolerance, allow_single_eye=False):
    if not unit_number(disagreement_tolerance):
        raise ValueError("gaze disagreement tolerance must be in [0, 1]")
    result = {}
    for name in ("gaze_x", "gaze_y"):
        candidates = [eye[name] for eye in (left, right)
                      if eye[name]["valid"] and eye[name]["confidence"] > 0]
        if len(candidates) == 2:
            a, b = candidates
            if abs(a["value"] - b["value"]) > disagreement_tolerance:
                result[name] = invalid()
            else:
                total = a["confidence"] + b["confidence"]
                result[name] = measurement(
                    sum(item["value"] * item["confidence"] for item in candidates) / total,
                    min(a["confidence"], b["confidence"]),
                )
        elif len(candidates) == 1 and allow_single_eye:
            result[name] = dict(candidates[0])
        else:
            result[name] = invalid()
    return result
