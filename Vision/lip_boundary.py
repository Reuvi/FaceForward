"""Experimental color extension beyond tracked outer lips, not tongue recognition.

No trained network or saved skin baseline. Each crop supplies local skin/lip
chroma references. Only the visible exterior front boundary supplies the point.
"""

from time import perf_counter
import cv2
import numpy as np
from .tongue import TongueModel, TongueResult

MEASUREMENT = "lip_color_extension_mouth_width_v1"
ALGORITHM = "lip-color-extension-v1"


class LipBoundaryModel(TongueModel):
    measurement = MEASUREMENT
    backend = "lip-boundary"
    path = "builtin:lip-color-extension-v1"
    load_error = None

    def __init__(self):
        self.report = dict(
            backend="Lip-boundary color extension · local CPU",
            inference_ms=None,
            confidence=None,
            error=None,
        )
        self.reset_tracking()

    def detect(self, crop, config, *, timestamp_ms=None):
        started = perf_counter()
        self.report.update(error=None, confidence=None)
        result = super().detect(crop, config, timestamp_ms=timestamp_ms)
        self.report.update(
            inference_ms=(perf_counter() - started) * 1000, confidence=result.quality
        )
        return result

    def unavailable(self, reason):
        self.report["error"] = reason
        return TongueResult(reason=reason)

    def _detect(self, crop, config):
        if crop.outer_mask is None or np.count_nonzero(crop.outer_mask) < 200:
            return self.unavailable("Outer lip outline unavailable")
        lab = cv2.cvtColor(crop.bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        chroma = lab[..., 1:]
        outer = (crop.outer_mask > 0).astype(np.uint8)
        m = crop.mouth_pixels
        yy, xx = np.indices(outer.shape)
        cx, cy = (np.array(outer.shape[::-1]) - 1) / 2
        skin_zone = (
            (abs(xx - cx) > 0.55 * m)
            & (abs(xx - cx) < 0.72 * m)
            & (abs(yy - cy) < 0.25 * m)
            & (outer == 0)
        )
        tissue_zone = (cv2.erode(outer, np.ones((3, 3), np.uint8)) > 0) & (
            cv2.dilate(crop.inner_mask, np.ones((3, 3), np.uint8)) == 0
        )
        if np.count_nonzero(skin_zone) < 100 or np.count_nonzero(tissue_zone) < 40:
            return self.unavailable("Not enough visible skin/lip color reference")
        skin = np.median(chroma[skin_zone], axis=0)
        tissue = np.median(chroma[tissue_zone], axis=0)
        axis = tissue - skin
        contrast = float(np.linalg.norm(axis))
        self.report["lip_skin_contrast"] = contrast
        if contrast < 6:
            return self.unavailable(
                "Lip/skin color contrast too low; adjust lighting or camera position"
            )
        delta = chroma - skin
        skin_distance = np.linalg.norm(delta, axis=2)
        tissue_distance = np.linalg.norm(chroma - tissue, axis=2)
        noise = float(np.median(np.linalg.norm(chroma[skin_zone] - skin, axis=1)))
        similar_hue = np.sum(delta * axis, axis=2) > 0.35 * contrast * np.maximum(
            1, skin_distance
        )
        colored = (
            (skin_distance > max(8, 2.5 * noise))
            & similar_hue
            & (tissue_distance < skin_distance)
            & (lab[..., 0] > 25)
        )
        border = max(2, round(0.02 * m))
        expanded = cv2.dilate(outer, np.ones((2 * border + 1,) * 2, np.uint8))
        mask = (colored & (expanded == 0)).astype(np.uint8) * 255
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask[expanded > 0] = 0
        distance = cv2.distanceTransform((outer == 0).astype(np.uint8), cv2.DIST_L2, 5)
        rim = (distance > 0) & (distance <= 0.08 * m)
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        candidates = [
            i
            for i in range(1, count)
            if stats[i, cv2.CC_STAT_AREA] >= 0.004 * m * m
            and np.count_nonzero((labels == i) & rim) >= 5
        ]
        candidates.sort(key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)
        if not candidates:
            return TongueResult(
                reason="No color extension connected to the lip boundary",
                mask=np.zeros_like(mask),
            )
        best = candidates[0]
        selected = (labels == best).astype(np.uint8)
        area = stats[best, cv2.CC_STAT_AREA]
        result = TongueResult(
            mask=selected * 255,
            candidate_present=True,
            area_fraction=float(area / mask.size),
            centroid=crop.raw_point(centers[best]),
        )
        if (
            len(candidates) > 1
            and stats[candidates[1], cv2.CC_STAT_AREA] > config.tongue_ambiguity * area
        ):
            result.reason = "Multiple color extensions; direction is ambiguous"
            return result
        if (
            selected[:2].any()
            or selected[-2:].any()
            or selected[:, :2].any()
            or selected[:, -2:].any()
        ):
            result.reason = (
                "Color extension touches crop edge; recenter or move farther away"
            )
            return result
        extension = float(distance[selected > 0].max())
        result.extension = extension / m
        if extension < 0.055 * m:
            result.reason = (
                "Color change too close to the lip; show a clearer extension"
            )
            return result
        cap = ((selected > 0) & (distance >= extension - max(2, 0.035 * m))).astype(
            np.uint8
        )
        groups, _, sizes, _ = cv2.connectedComponentsWithStats(cap)
        cap_areas = sorted(sizes[1:, cv2.CC_STAT_AREA], reverse=True)
        if groups > 2 and cap_areas[1] > 0.3 * cap_areas[0]:
            result.reason = "Several outer fronts; color direction is ambiguous"
            return result
        contours, _ = cv2.findContours(
            selected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
        edge = contour[distance[contour[:, 1], contour[:, 0]] >= extension - 0.05 * m]
        if len(edge) < 5:
            result.reason = "Too little visible outer boundary"
            return result
        by, bx = np.nonzero((selected > 0) & rim)
        attachment = np.array([np.mean(bx), np.mean(by)])
        direction = edge.mean(axis=0) - attachment
        length = np.linalg.norm(direction)
        if length < 0.04 * m:
            result.reason = "Extension direction is too short"
            return result
        direction /= length
        tangent = np.array([-direction[1], direction[0]])
        transverse = edge @ tangent
        middle = (transverse.min() + transverse.max()) / 2
        depth = distance[edge[:, 1], edge[:, 0]]
        point = edge[
            np.argmin((transverse - middle) ** 2 + 0.15 * (depth - extension) ** 2)
        ]
        result.xy = crop.raw_point(point)
        result.attachment = crop.raw_point(attachment)
        result.edge = edge
        result.quality = float(
            min(1, contrast / 20, extension / (0.12 * m), area / (0.008 * m * m))
        )
        result.reason = "Visible color extension beyond lip boundary (experimental)"
        return result
