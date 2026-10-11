"""Generated color regions test the proxy; these are not live tongue accuracy tests."""

import importlib.util
import unittest
from dataclasses import replace

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    import cv2
    import numpy as np
    from Vision.features import DetectionConfig
    from Vision.lip_boundary import LipBoundaryModel
    from Vision.tongue import MouthCrop, mouth_crop
    from Vision.demo_detection import demo_image


def color_crop(
    direction=None, *, tissue=(100, 90, 200), skin=(120, 160, 190), extras=()
):
    image = np.full((160, 160, 3), skin, np.uint8)
    outer = np.zeros((160, 160), np.uint8)
    inner = np.zeros_like(outer)
    cv2.ellipse(outer, (80, 80), (48, 23), 0, 0, 360, 255, -1)
    cv2.ellipse(inner, (80, 80), (39, 12), 0, 0, 360, 255, -1)
    image[outer > 0] = tissue
    image[inner > 0] = (25, 15, 20)
    for name in (() if direction is None else (direction,)) + extras:
        tip = {"up": (80, 38), "down": (80, 123), "left": (15, 80), "right": (145, 80)}[
            name
        ]
        cv2.line(image, (80, 80), tip, tissue, 15)
        cv2.circle(image, tip, 8, tissue, -1)
    return MouthCrop(
        image,
        np.full_like(outer, 255),
        np.float32([[1, 0, 0], [0, 1, 0]]),
        0.24,
        100,
        inner,
        outer,
    )


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class LipBoundaryTests(unittest.TestCase):
    def detect(self, crop):
        model = LipBoundaryModel()
        result = model.detect(crop, DetectionConfig())
        self.assertGreaterEqual(model.report["inference_ms"], 0)
        return result

    def test_four_directions_front_midpoint_on_boundary_not_centroid(self):
        for direction, axis, sign in (
            ("up", 1, -1),
            ("down", 1, 1),
            ("left", 0, -1),
            ("right", 0, 1),
        ):
            with self.subTest(direction=direction):
                crop = color_crop(direction)
                result = self.detect(crop)
                self.assertIsNotNone(result.xy, result.reason)
                self.assertGreater(result.xy[axis] * sign, 0.35)
                self.assertLess(abs(result.xy[1 - axis]), 0.03)
                self.assertGreater(result.quality, 0.5)
                self.assertNotEqual(result.xy, result.centroid)
                point = np.array(crop.crop_point(result.xy))
                self.assertLess(
                    np.min(np.linalg.norm(result.edge - point, axis=1)), 1e-4
                )
                self.assertFalse(np.any((result.mask > 0) & (crop.outer_mask > 0)))

    def test_absent_and_disconnected_color_are_not_candidates(self):
        crop = color_crop()
        for noise in (False, True):
            if noise:
                cv2.circle(crop.bgr, (80, 20), 8, (100, 90, 200), -1)
            result = self.detect(crop)
            self.assertIsNone(result.xy)
            self.assertFalse(result.candidate_present, result.reason)

    def test_skin_teeth_and_dark_exterior_are_rejected(self):
        for color in ((120, 160, 190), (240, 240, 240), (5, 5, 5)):
            crop = color_crop()
            cv2.rectangle(crop.bgr, (69, 90), (91, 125), color, -1)
            result = self.detect(crop)
            self.assertIsNone(result.xy, result.reason)
            self.assertFalse(result.candidate_present)

    def test_ambiguous_and_clipped_regions_remain_unavailable(self):
        ambiguous = self.detect(color_crop("up", extras=("down",)))
        self.assertIsNone(ambiguous.xy)
        self.assertTrue(ambiguous.candidate_present)
        self.assertIn("ambiguous", ambiguous.reason)
        crop = color_crop("down")
        cv2.rectangle(crop.bgr, (72, 100), (88, 159), (100, 90, 200), -1)
        clipped = self.detect(crop)
        self.assertIsNone(clipped.xy)
        self.assertTrue(clipped.candidate_present)
        self.assertIn("crop edge", clipped.reason)

    def test_missing_boundary_and_flat_color_are_not_valid_absence_evidence(self):
        model = LipBoundaryModel()
        for crop in (
            replace(color_crop(), outer_mask=None),
            color_crop(tissue=(120, 160, 190)),
        ):
            result = model.detect(crop, DetectionConfig())
            self.assertIsNone(result.xy)
            self.assertIsNotNone(model.report["error"])

    def test_crop_allows_closed_inner_lips_and_rejects_bad_outer_geometry(self):
        image, observations = demo_image(tongue=False)
        obs = observations[0]
        from Vision.tongue import INNER_LIP

        points = list(obs.points)
        for index in INNER_LIP:
            points[index] = (points[index][0], 340.0)
        obs.points = tuple(points)
        crop, reason = mouth_crop(image, obs, DetectionConfig(), lip_boundary=True)
        self.assertIsNotNone(crop, reason)
        self.assertIsNone(mouth_crop(image, obs, DetectionConfig())[0])
        points[17] = points[0]
        obs.points = tuple(points)
        self.assertIsNone(
            mouth_crop(image, obs, DetectionConfig(), lip_boundary=True)[0]
        )

    def test_large_instant_jump_is_invalid_but_next_supported_sample_recovers(self):
        model = LipBoundaryModel()
        config = DetectionConfig()
        self.assertIsNotNone(
            model.detect(color_crop("left"), config, timestamp_ms=1000).xy
        )
        result = model.detect(color_crop("right"), config, timestamp_ms=1001)
        self.assertIsNone(result.xy)
        self.assertIn("jumped", result.reason)
        self.assertIsNotNone(
            model.detect(color_crop("right"), config, timestamp_ms=1030).xy
        )

    def test_color_positions_can_train_then_pass_fresh_joystick_checks(self):
        from Vision.movement_guide import MovementGuide

        guide = MovementGuide(
            "tongue",
            DetectionConfig(
                settle_ms=0, collect_ms=300, min_samples=5, movement_rest_ms=0
            ),
        )
        readings = {}
        for name, point in dict(
            center=(80, 122),
            left=(35, 122),
            right=(125, 122),
            up=(80, 110),
            down=(80, 138),
        ).items():
            crop = color_crop()
            cv2.line(crop.bgr, (80, 80), point, (100, 90, 200), 15)
            cv2.circle(crop.bgr, point, 8, (100, 90, 200), -1)
            result = self.detect(crop)
            self.assertIsNotNone(result.xy, (name, result.reason))
            readings[name] = result.xy
        now = 1000
        for _ in range(250):
            if not guide.active:
                break
            state = guide.state(now)
            if state["waiting"]:
                guide.present(state["index"], now, state["phase"])
            guide.feed(now, readings.get(state["name"]), True)
            now += 25
        self.assertTrue(guide.passed, guide.report)
        for name, target in (
            ("center", (0.5, 0.5)),
            ("left", (0, 0.5)),
            ("right", (1, 0.5)),
            ("up", (0.5, 0)),
            ("down", (0.5, 1)),
        ):
            for value, want in zip(guide.normalized(readings[name]), target):
                self.assertAlmostEqual(value, want, delta=0.2)
