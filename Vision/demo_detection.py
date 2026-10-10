"""Synthetic pixels + landmarks for workbench testing; never a face ML result."""

import math

import cv2
import numpy as np

from .landmarks import EYES, Observation
from .tongue import INNER_LIP
from .tracking import Box


def demo_image(*, left_closed=False, right_closed=False, head=0.5,
               tongue=False, tongue_x=0.5, tongue_y=0.5, left_ratio=None, right_ratio=None):
    """Anatomical right is image-left. Head value shifts Y and supplies a fake pitch."""
    offset = (head - 0.5) * 80
    bgr = np.full((480, 640, 3), (65, 65, 65), dtype=np.uint8)
    cv2.ellipse(bgr, (320, int(240 + offset)), (155, 195), 0, 0, 360, (145, 175, 200), -1)
    # Fine skin texture makes focus gates meaningful in generated image tests.
    yy, xx = np.indices((480, 640))
    texture = (((xx + yy) % 4) - 2).astype(np.int16) * 3
    bgr = np.clip(bgr.astype(np.int16) + texture[:, :, None], 0, 255).astype(np.uint8)
    points = [(320., 240. + offset)] * 478
    for side, (corners, pairs, iris) in EYES.items():
        cx, cy, width = (385 if side == "left" else 255), 200 + offset, 60
        closed = left_closed if side == "left" else right_closed
        ratio = left_ratio if side == "left" else right_ratio
        gap = width * ratio if ratio is not None else (2.5 if closed else 15)
        points[corners[0]], points[corners[1]] = (cx + width/2, cy), (cx - width/2, cy)
        for index, (a, b) in enumerate(pairs):
            x = cx + (index - 1) * 12
            points[a], points[b] = (x, cy-gap/2), (x, cy+gap/2)
        for i in iris:
            points[i] = (cx, cy)
        cv2.ellipse(bgr, (cx, int(cy)), (30, max(1, int(gap/2))), 0, 0, 360, (45, 45, 45), -1)
        if not closed:
            cv2.circle(bgr, (cx, int(cy)), 5, (160, 90, 50), -1)
    points[168] = (320., 225. + offset)
    cy = 326 + offset
    for index, landmark in enumerate(INNER_LIP):
        # Ordered lower arc followed by upper arc; actual anatomical corners below.
        angle = math.pi - index * 2 * math.pi / len(INNER_LIP)
        points[landmark] = (320 + 60*math.cos(angle), cy + 30*math.sin(angle))
    points[13], points[14] = (320., cy-30), (320., cy+30)
    points[291], points[61] = (380., cy), (260., cy)
    polygon = np.round([points[i] for i in INNER_LIP]).astype(np.int32)
    cv2.ellipse(bgr, (320, int(cy)), (65, 35), 0, 0, 360, (90, 85, 155), -1)
    cv2.fillPoly(bgr, [polygon], (35, 30, 40))
    cv2.rectangle(bgr, (290, int(cy-22)), (350, int(cy-14)), (195, 210, 220), -1)
    if tongue:
        x, y = int(380-120*tongue_x), int(cy-30+60*tongue_y)
        cv2.ellipse(bgr, (x, y), (15, 11), 0, 0, 360, (115, 100, 215), -1)
    angle = math.radians((head - 0.5)*40)
    rotation = ((1., 0., 0.), (0., math.cos(angle), -math.sin(angle)), (0., math.sin(angle), math.cos(angle)))
    observation = Observation(Box(165/640, (45+offset)/480, 310/640, 390/480), tuple(points), rotation=rotation)
    # Explicit synthetic coefficients for the native experiment fixture.
    for side in ('left','right'):
        ratio = left_ratio if side == 'left' else right_ratio
        closed = (left_closed if side == 'left' else right_closed) if ratio is None else ratio < .08
        for name, value in (('eyeBlink',.95 if closed else .08),('eyeSquint',.65 if closed else .05),
                            ('cheekSquint',.45 if closed else .04),('browDown',.3 if closed else .03),
                            ('mouthSmile',.05),('eyeWide',.1)):
            observation.expressions[name+side.title()] = value
    observation.expressions.update(browInnerUp=.05,jawOpen=.3)
    return bgr, [observation]
