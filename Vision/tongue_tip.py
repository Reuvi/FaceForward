"""Experimental free-edge midpoint from a color mask; no anatomical guarantee.

All geometry here is in mouth-aligned crop pixels. Distance waves remain within
one connected mask. The selected front arc, not the region centroid, supplies the
point. No previous point is used to fabricate a missing edge.
"""

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class TipEstimate:
    point: object = None
    attachment: object = None
    edge: object = None
    quality: float = 0.0
    reason: str = "Tip unavailable"
    extension: float = 0.0


def estimate_tip(mask, inner_mouth, mouth_pixels, config):
    selected = (mask > 0).astype(np.uint8)
    height, width = selected.shape
    if (
        selected[:2].any()
        or selected[-2:].any()
        or selected[:, :2].any()
        or selected[:, -2:].any()
    ):
        return TipEstimate(
            reason="Tongue touches crop edge; move farther from the camera or recenter"
        )
    yy, xx = np.indices(selected.shape)
    center = np.array([(width - 1) / 2, (height - 1) / 2])
    root_zone = (xx - center[0]) ** 2 + (yy - center[1]) ** 2 <= (
        0.18 * mouth_pixels
    ) ** 2
    seed = selected & (inner_mouth > 0) & root_zone
    if np.count_nonzero(seed) < max(8, 0.002 * mouth_pixels**2):
        return TipEstimate(
            reason="Candidate is not connected to the central mouth; tip attachment unknown"
        )
    sy, sx = np.nonzero(seed)
    base = np.array([sx.mean(), sy.mean()])
    # Eight-neighbor geodesic distance (pixels/steps). Reject maze-like masks
    # rather than letting a pathological color region stall the capture worker.
    reached = seed.astype(np.uint8)
    distances = np.full(selected.shape, -1, np.int16)
    distances[reached > 0] = 0
    kernel = np.ones((3, 3), np.uint8)
    step = 0
    while step < 2 * max(height, width):
        grown = cv2.dilate(reached, kernel) & selected
        new = (grown > 0) & (reached == 0)
        if not new.any():
            break
        step += 1
        distances[new] = step
        reached = grown
    if np.any(selected & (reached == 0)):
        return TipEstimate(
            reason="Disconnected or excessively winding color region; tip unavailable"
        )
    extension = step / mouth_pixels
    result = TipEstimate(attachment=tuple(base), extension=extension)
    if extension < config.tongue_tip_min_extension:
        result.reason = "No distinct free end; show a little more of the tongue"
        return result
    # A rounded or forked mask can have several equally distant fronts.
    cap = (
        (distances >= step - max(2, round(0.04 * mouth_pixels))) & (selected > 0)
    ).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(cap)
    groups = sorted(
        range(1, count), key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True
    )
    if not groups or (
        len(groups) > 1
        and stats[groups[1], cv2.CC_STAT_AREA]
        > 0.2 * stats[groups[0], cv2.CC_STAT_AREA]
    ):
        result.reason = "Several possible tongue ends; tip is ambiguous"
        return result
    cy, cx = np.nonzero(labels == groups[0])
    front = np.array([cx.mean(), cy.mean()])
    direction = front - base
    distance = np.linalg.norm(direction)
    if distance < config.tongue_tip_min_extension * mouth_pixels:
        result.reason = "Front direction is ambiguous; extend the visible tongue"
        return result
    direction /= distance
    across = np.array([-direction[1], direction[0]])
    distal = np.column_stack((cx, cy))
    if np.ptp((distal - base) @ across) > 0.9 * distance:
        result.reason = "Front edge is too broad to identify a unique tip"
        return result
    # Estimate the last short section's direction, so a curved tongue's end
    # need not point along the straight line from mouth center to tip.
    near_front = (xx - front[0]) ** 2 + (yy - front[1]) ** 2 <= (
        0.4 * mouth_pixels
    ) ** 2
    reach = min(0.18 * mouth_pixels, step)
    proximal = (
        (distances >= step - reach)
        & (distances <= step - 0.45 * reach)
        & near_front
        & (selected > 0)
    )
    py, px = np.nonzero(proximal)
    if len(px) < 5:
        result.reason = "Insufficient tongue body behind the front edge"
        return result
    direction = front - np.array([px.mean(), py.mean()])
    if np.linalg.norm(direction) < 0.04 * mouth_pixels:
        result.reason = "Local front direction is ambiguous"
        return result
    direction /= np.linalg.norm(direction)
    across = np.array([-direction[1], direction[0]])
    contours, _ = cv2.findContours(selected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(float)
    ci = contour.astype(int)
    local = contour[
        (np.linalg.norm(contour - front, axis=1) <= 0.3 * mouth_pixels)
        & (distances[ci[:, 1], ci[:, 0]] >= step - 0.15 * mouth_pixels)
    ]
    if len(local) < 7:
        result.reason = "Too little distal outline to identify the front edge"
        return result
    along = (local - front) @ direction
    edge = local[along >= along.max() - 0.07 * mouth_pixels]
    if len(edge) < 7:
        result.reason = "Too little visible front boundary to fit a tip"
        return result
    transverse = (edge - front) @ across
    longitudinal = (edge - front) @ direction
    if np.ptp(transverse) < 0.08 * mouth_pixels:
        result.reason = "Front edge is too small or pointed to measure reliably"
        return result
    # Smooth a short rounded/flat front edge. Its middle, rather than the
    # furthest single pixel or the body center, is the reported tip.
    fit = np.polynomial.polynomial.polyfit(transverse, longitudinal, 2)
    fitted = np.polynomial.polynomial.polyval(transverse, fit)
    error = float(np.sqrt(np.mean((fitted - longitudinal) ** 2))) / mouth_pixels
    if error > config.tongue_tip_fit_error or fit[2] > 0.01:
        result.reason = "Front boundary is irregular or concave; tip uncertain"
        return result
    middle = float((transverse.min() + transverse.max()) / 2)
    point = (
        front
        + across * middle
        + direction * np.polynomial.polynomial.polyval(middle, fit)
    )
    # A fitted point must still be supported by actual color-boundary pixels.
    boundary_distance = np.linalg.norm(edge - point, axis=1)
    if boundary_distance.min() > 0.035 * mouth_pixels:
        result.reason = "Fitted tip lacks a visible color boundary"
        return result
    # Anchor the smoothed middle to observed boundary evidence. A curve fit can
    # otherwise overshoot a flat or pixelated end and put the marker in air.
    point = edge[int(boundary_distance.argmin())]
    result.point = tuple(float(v) for v in point)
    result.edge = edge
    result.quality = float(
        min(
            1,
            extension / (2 * config.tongue_tip_min_extension),
            max(0.1, 1 - error / config.tongue_tip_fit_error),
        )
    )
    result.reason = "Visible front-edge midpoint (experimental)"
    return result
