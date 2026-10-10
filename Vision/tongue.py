"""Session-calibrated mouth appearance segmentation, not a pretrained tongue net.

Manual positive patches and tongue-absent mouth images teach competing Lab-color
prototypes. Held-out camera exercises are required before normalized output is
marked valid by the workbench. All image data is memory-only.
"""

from dataclasses import dataclass
import math

import cv2
import numpy as np

from .geometry import reference, sub
from .tongue_tip import estimate_tip


INNER_LIP = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324,
             308, 415, 310, 311, 312, 13, 82, 81, 80, 191)
CROP_WIDTH, CROP_HEIGHT = 160, 160
CROP_SPAN = 1.6
TONGUE_MEASUREMENT = "color_tip_mouth_width_v1"


@dataclass
class MouthCrop:
    bgr: object
    mask: object
    to_image: object
    opening_ratio: float
    width_px: float
    inner_mask: object

    @property
    def mouth_pixels(self):
        return (CROP_WIDTH - 1) / CROP_SPAN

    def raw_point(self, pixel):
        return tuple((float(v)/(CROP_WIDTH-1)-.5)*CROP_SPAN for v in pixel)

    def crop_point(self, raw):
        return tuple((float(v)/CROP_SPAN+.5)*(CROP_WIDTH-1) for v in raw)

    def image_point(self, xy):
        point = self.to_image @ np.array([*self.crop_point(xy), 1.0])
        return tuple(float(v) for v in point)


def mouth_crop(bgr, observation, config):
    points = observation.points
    if len(points) < 468:
        return None, "Mouth landmarks unavailable"
    left, right, upper, lower = (points[i] for i in (291, 61, 13, 14))
    try:
        frame = reference(left, right, sub(lower, upper))
    except ValueError:
        return None, "Mouth reference is degenerate"
    down, across = np.array(frame.down), np.array(frame.right)
    mouth_height = float(np.dot(np.array(lower) - upper, down))
    ratio = mouth_height / frame.width
    if frame.width < config.min_mouth_px or mouth_height < 5 or ratio < config.min_mouth_opening:
        return None, "Open mouth more, or move closer"
    if ratio > 1.2:
        return None, "Implausible mouth geometry"
    height, width = bgr.shape[:2]
    if not all(0 <= points[i][0] < width and 0 <= points[i][1] < height for i in INNER_LIP):
        return None, "Mouth is outside the image"
    origin = np.array(frame.origin) - (across+down)*frame.width*CROP_SPAN/2
    span = frame.width*CROP_SPAN
    corners = [origin, origin+across*span, origin+down*span, origin+(across+down)*span]
    if not all(0 <= point[0] < width and 0 <= point[1] < height for point in corners):
        return None, "Expanded mouth crop is outside image; recenter or move farther away"
    source = np.float32(corners[:3])
    dest = np.float32([[0, 0], [CROP_WIDTH - 1, 0], [0, CROP_HEIGHT - 1]])
    transform = cv2.getAffineTransform(source, dest)
    crop = cv2.warpAffine(bgr, transform, (CROP_WIDTH, CROP_HEIGHT))
    polygon = np.array([transform @ np.array([*points[i], 1.0]) for i in INNER_LIP], dtype=np.int32)
    inner = np.zeros((CROP_HEIGHT, CROP_WIDTH), dtype=np.uint8)
    cv2.fillPoly(inner, [polygon], 255)
    inner = cv2.erode(inner, np.ones((3, 3), np.uint8), iterations=1)
    if np.count_nonzero(inner) < 200:
        return None, "Insufficient visible inner mouth"
    mask = np.full_like(inner, 255)
    return MouthCrop(crop, mask, cv2.invertAffineTransform(transform), ratio, frame.width, inner), "Expanded mouth region available"


def color_features(bgr):
    values = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    values[..., 0] *= 0.35  # Preserve some luminance evidence; emphasize chroma.
    return values


def sample_colors(crop, *, xy=None):
    mask = crop.mask > 0
    if xy is not None:
        x, y = xy
        if not (math.isfinite(x) and math.isfinite(y) and .04 <= x <= .96 and .04 <= y <= .96):
            raise ValueError("Choose a point inside the mouth image")
        cx, cy = round(x * (CROP_WIDTH - 1)), round(y * (CROP_HEIGHT - 1))
        patch = np.zeros_like(mask)
        patch[max(0, cy - 5):min(CROP_HEIGHT, cy + 6), max(0, cx - 5):min(CROP_WIDTH, cx + 6)] = True
        mask = mask & patch
        if np.count_nonzero(mask) < 80:
            raise ValueError("Choose a tongue patch away from the lip border")
    pixels = color_features(crop.bgr)[mask]
    return pixels[::max(1, len(pixels) // 800)].copy()


def _centers(values, count):
    """Small deterministic k-means; no global RNG state, bounded training cost."""
    values = np.asarray(values, dtype=np.float32)
    centers = [values[0]]
    for _ in range(1, count):
        distances = ((values[:, None] - np.array(centers)[None]) ** 2).sum(axis=2).min(axis=1)
        if distances.max() < 1:
            break
        centers.append(values[int(distances.argmax())])
    centers = np.array(centers)
    for _ in range(12):
        labels = ((values[:, None] - centers[None]) ** 2).sum(axis=2).argmin(axis=1)
        updated = np.array([values[labels == i].mean(axis=0) if np.any(labels == i) else center
                            for i, center in enumerate(centers)])
        if np.max(np.abs(updated - centers)) < 0.05:
            break
        centers = updated
    return centers


def _distance(values, centers):
    return np.sqrt(((values[..., None, :] - centers) ** 2).sum(axis=-1).min(axis=-1))


@dataclass
class TongueResult:
    xy: object = None
    quality: float = 0
    reason: str = "Tongue model uncalibrated"
    mask: object = None
    area_fraction: float = 0
    candidate_present: bool = False
    centroid: object = None
    attachment: object = None
    edge: object = None
    extension: float = 0


class TongueModel:
    def __init__(self, positive, negative, radius, margin, report):
        self.positive, self.negative = positive, negative
        self.radius, self.margin, self.report = radius, margin, report
        self.reset_tracking()

    def reset_tracking(self):
        self.last_tip = self.last_timestamp = None

    @classmethod
    def fit(cls, positives, negatives, margin=4):
        positive, negative = np.asarray(positives, dtype=np.float32), np.asarray(negatives, dtype=np.float32)
        for values in (positive, negative):
            if values.ndim != 2 or values.shape[1] != 3 or len(values) < 100 or not np.isfinite(values).all():
                raise ValueError("Collect at least 100 finite positive and negative color samples")
        # Spatial pixel holdout is a fit diagnostic, not independent real-world validation.
        p_train, p_test = positive[np.arange(len(positive)) % 5 != 0], positive[::5]
        n_train, n_test = negative[np.arange(len(negative)) % 5 != 0], negative[::5]
        p, n = _centers(p_train, 3), _centers(n_train, 8)
        radius = float(min(30, max(6, np.quantile(_distance(p_train, p), 0.98) * 1.5)))
        model = cls(p, n, radius, margin, {})
        recall = float(model.classify(p_test)[0].mean())
        false_positive = float(model.classify(n_test)[0].mean())
        if recall < 0.75 or false_positive > 0.02:
            raise ValueError(f"Tongue/background colors overlap (pixel recall {recall:.0%}, false positives {false_positive:.0%}); recollect")
        model.report = {"pixel_recall": recall, "pixel_false_positive": false_positive, "radius": radius}
        return model

    def classify(self, values):
        positive, negative = _distance(values, self.positive), _distance(values, self.negative)
        contrast = negative - positive
        return (positive <= self.radius) & (contrast >= self.margin), contrast

    def detect(self, crop, config, *, timestamp_ms=None):
        result = self._detect(crop, config)
        if result.xy is None:
            self.reset_tracking()
            return result
        if timestamp_ms is not None and self.last_timestamp is not None:
            dt = (timestamp_ms-self.last_timestamp)/1000
            if 0 < dt <= config.stale_ms/1000 and math.dist(result.xy,self.last_tip) > .12+config.tongue_tip_max_speed*dt:
                result.xy, result.quality = None, 0
                result.reason = "Tip jumped too far; waiting for a fresh supported edge"
                self.reset_tracking()
                return result
        self.last_tip, self.last_timestamp = result.xy, timestamp_ms
        return result

    def _detect(self, crop, config):
        predicted, contrast = self.classify(color_features(crop.bgr))
        mask = ((predicted & (crop.mask > 0)) * 255).astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel) & crop.mask
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        available = max(1, np.count_nonzero(crop.mask))
        candidates = sorted(range(1, count), key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)
        if not candidates or stats[candidates[0], cv2.CC_STAT_AREA] / available < config.tongue_min_area:
            return TongueResult(reason="No sufficiently large tongue candidate", mask=mask)
        best = candidates[0]
        fraction = float(stats[best, cv2.CC_STAT_AREA] / available)
        if fraction > config.tongue_max_area:
            return TongueResult(reason="Candidate occupies too much of the mouth", mask=mask, area_fraction=fraction, candidate_present=True)
        if len(candidates) > 1 and stats[candidates[1], cv2.CC_STAT_AREA] > config.tongue_ambiguity * stats[best, cv2.CC_STAT_AREA]:
            return TongueResult(reason="Multiple ambiguous tongue candidates", mask=mask, area_fraction=fraction, candidate_present=True)
        selected = labels == best
        quality = float(min(1, np.median(contrast[selected]) / (3 * self.margin), fraction / (2 * config.tongue_min_area)))
        estimate = estimate_tip((selected*255).astype(np.uint8), crop.inner_mask, crop.mouth_pixels, config)
        return TongueResult(xy=crop.raw_point(estimate.point) if estimate.point else None,
                            quality=min(quality,estimate.quality), reason=estimate.reason,
                            mask=(selected*255).astype(np.uint8), area_fraction=fraction,
                            candidate_present=True, centroid=crop.raw_point(centers[best]),
                            attachment=crop.raw_point(estimate.attachment) if estimate.attachment else None,
                            edge=estimate.edge, extension=estimate.extension)
