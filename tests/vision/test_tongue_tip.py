"""Known synthetic front boundaries, rejection cases, and mouth-width geometry."""

import importlib.util
import unittest

AVAILABLE = all(importlib.util.find_spec(name) for name in ("cv2", "numpy"))
if AVAILABLE:
    import cv2
    import numpy as np
    from Vision.features import DetectionConfig
    from Vision.tongue_tip import estimate_tip
    from Vision.tongue import TongueModel, mouth_crop, sample_colors
    from Vision.demo_detection import demo_image


@unittest.skipUnless(AVAILABLE, "Vision pixel dependencies required")
class TongueTipTests(unittest.TestCase):
    def setUp(self):
        self.config = DetectionConfig()
        self.inner = np.zeros((160, 160), np.uint8)
        cv2.ellipse(self.inner, (80, 80), (50, 25), 0, 0, 360, 255, -1)

    def capsule(self, end, *, radius=10):
        mask = np.zeros_like(self.inner)
        root = np.array([80.0, 80.0])
        end = np.array(end, dtype=float)
        direction = (end - root) / np.linalg.norm(end - root)
        back = end - direction * radius
        cv2.line(
            mask,
            tuple(root.astype(int)),
            tuple(np.round(back).astype(int)),
            255,
            2 * radius,
        )
        cv2.circle(mask, tuple(np.round(back).astype(int)), radius, 255, -1)
        return mask

    def estimate(self, mask):
        return estimate_tip(mask, self.inner, 100, self.config)

    def test_boundary_midpoint_in_all_directions_is_not_region_center(self):
        for end in ((80, 135), (25, 80), (135, 80), (80, 25), (120, 120), (40, 40)):
            with self.subTest(end=end):
                mask = self.capsule(end)
                tip = self.estimate(mask)
                self.assertIsNotNone(tip.point, tip.reason)
                self.assertLess(np.linalg.norm(np.array(tip.point) - end), 3)
                ys, xs = np.nonzero(mask)
                self.assertGreater(
                    np.linalg.norm(np.array(tip.point) - [xs.mean(), ys.mean()]), 15
                )
                self.assertGreater(len(tip.edge), 6)

    def test_curved_tongue_uses_local_front_direction(self):
        mask = np.zeros_like(self.inner)
        points = [(80, 80), (90, 95), (95, 110), (80, 130), (60, 130)]
        cv2.polylines(mask, [np.array(points)], False, 255, 20)
        for point in points:
            cv2.circle(mask, point, 10, 255, -1)
        result = self.estimate(mask)
        self.assertIsNotNone(result.point, result.reason)
        self.assertLess(np.linalg.norm(np.array(result.point) - [50, 130]), 4)

    def test_flat_front_uses_boundary_middle_not_a_corner_or_fit_overshoot(self):
        mask = np.zeros_like(self.inner)
        cv2.rectangle(mask, (68, 75), (92, 135), 255, -1)
        result = self.estimate(mask)
        self.assertIsNotNone(result.point, result.reason)
        np.testing.assert_allclose(result.point, (80, 135))
        self.assertEqual(np.linalg.norm(result.edge - result.point, axis=1).min(), 0)

    def test_small_round_hidden_clipped_and_detached_shapes_are_unknown(self):
        masks = []
        circle = np.zeros_like(self.inner)
        cv2.circle(circle, (80, 80), 14, 255, -1)
        masks.append(circle)
        circle = np.zeros_like(self.inner)
        cv2.circle(circle, (120, 130), 15, 255, -1)
        masks.append(circle)
        masks.append(self.capsule((80, 165)))
        masks.append(np.zeros_like(self.inner))
        for mask in masks:
            self.assertIsNone(self.estimate(mask).point)

    def test_competing_fronts_and_disconnected_shapes_are_rejected(self):
        fork = self.capsule((35, 125)) | self.capsule((125, 125))
        result = self.estimate(fork)
        self.assertIsNone(result.point)
        self.assertIn("ambiguous", result.reason)
        split = self.capsule((80, 130))
        cv2.circle(split, (20, 20), 8, 255, -1)
        self.assertIsNone(self.estimate(split).point)

    def crop(self, **controls):
        image, obs = demo_image(**controls)
        crop, reason = mouth_crop(image, obs[0], self.config)
        self.assertIsNotNone(crop, reason)
        return crop

    def model(self):
        return TongueModel.fit(
            sample_colors(self.crop(tongue=True), xy=(0.5, 0.5)),
            sample_colors(self.crop()),
        )

    def test_protruding_tip_and_raw_y_do_not_scale_with_mouth_opening(self):
        model = self.model()
        image, obs = demo_image(tongue=True)
        original = mouth_crop(image, obs[0], self.config)[0]
        first = model.detect(original, self.config)
        self.assertGreater(first.xy[1], original.opening_ratio / 2)
        points = list(obs[0].points)
        points[13] = (320, 310)
        points[14] = (320, 342)
        obs[0].points = tuple(points)
        changed = mouth_crop(image, obs[0], self.config)[0]
        second = model.detect(changed, self.config)
        self.assertIsNotNone(second.xy, second.reason)
        np.testing.assert_allclose(first.xy, second.xy, atol=0.015)
        self.assertLess(
            np.linalg.norm(np.array(original.image_point(first.xy)) - [320, 380]), 3
        )

    def test_bad_tip_still_counts_as_a_color_candidate(self):
        model = self.model()
        crop = self.crop()
        cv2.circle(crop.bgr, (80, 80), 18, (115, 100, 215), -1)
        result = model.detect(crop, self.config)
        self.assertTrue(result.candidate_present)
        self.assertIsNone(result.xy)

    def test_unexpected_jump_is_unknown_then_reacquires_new_evidence(self):
        model = self.model()
        first = model.detect(
            self.crop(tongue=True, tongue_x=0.3), self.config, timestamp_ms=1000
        )
        self.assertIsNotNone(first.xy)
        right = self.crop(tongue=True, tongue_x=0.7)
        bad = model.detect(right, self.config, timestamp_ms=1033)
        self.assertTrue(bad.candidate_present)
        self.assertIsNone(bad.xy)
        self.assertIn("jumped", bad.reason)
        self.assertIsNone(model.last_tip)
        current = model.detect(right, self.config, timestamp_ms=1066)
        self.assertIsNotNone(current.xy)
        model.detect(self.crop(), self.config, timestamp_ms=1099)
        self.assertIsNone(model.last_tip)
