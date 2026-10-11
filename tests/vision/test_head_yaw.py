"""Yaw uses the existing pose matrix, not face translation or another model."""
import importlib.util
import math
import unittest

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    import numpy as np
    from Vision.demo_detection import demo_image
    from Vision.features import DetectionConfig, analyze_features, pitch_degrees, yaw_degrees
    from Vision.movement_guide import MovementGuide


def rotation(yaw, pitch=0, roll=0):
    y, p, r = map(math.radians, (yaw, pitch, roll))
    ry = np.array(((math.cos(y),0,math.sin(y)),(0,1,0),(-math.sin(y),0,math.cos(y))))
    rx = np.array(((1,0,0),(0,math.cos(p),-math.sin(p)),(0,math.sin(p),math.cos(p))))
    rz = np.array(((math.cos(r),-math.sin(r),0),(math.sin(r),math.cos(r),0),(0,0,1)))
    return ry @ rx @ rz


@unittest.skipUnless(AVAILABLE, "Vision pixel dependencies required")
class HeadYawTests(unittest.TestCase):
    def test_combined_pose_keeps_yaw_and_pitch_independent(self):
        for yaw in (-40, -10, 0, 25, 50):
            for pitch in (-30, 0, 30):
                for roll in (-20, 0, 20):
                    r = rotation(yaw, pitch, roll)
                    self.assertAlmostEqual(yaw_degrees(r), yaw)
                    self.assertAlmostEqual(pitch_degrees(r), pitch)

    def test_missing_degenerate_rear_facing_and_nonfinite_yaw_are_unavailable(self):
        for r in (None, np.zeros((3,3)), rotation(0,90), rotation(110), np.full((3,3),float("nan"))):
            self.assertIsNone(yaw_degrees(r))

    def test_raw_yaw_ignores_image_translation_and_uses_face_quality(self):
        bgr, observations = demo_image(head=.8, head_x=.7)
        features = analyze_features(bgr, observations[0], DetectionConfig())
        self.assertAlmostEqual(features["head_x"].value, 8)
        self.assertAlmostEqual(features["head"].value, 12)
        observations[0].rotation = rotation(0, 0)
        self.assertEqual(analyze_features(bgr, observations[0], DetectionConfig())["head_x"].value, 0)
        self.assertEqual(analyze_features(np.zeros_like(bgr), observations[0], DetectionConfig())["head_x"].quality, 0)
        observations[0].rotation = None
        missing = analyze_features(bgr, observations[0], DetectionConfig())["head_x"]
        self.assertIsNone(missing.value); self.assertEqual(missing.quality, 0)

    def test_guide_ignores_preparation_rest_and_duplicate_samples(self):
        config = DetectionConfig(settle_ms=100, collect_ms=300, min_samples=5, movement_rest_ms=100)
        guide = MovementGuide("head_x", config)
        guide.feed(0, (0,), True); self.assertEqual(guide.values, [])
        guide.present(0, 0, "prepare")
        guide.feed(99, (0,), True); self.assertEqual(guide.values, [])
        for timestamp in range(100, 400, 25):
            guide.feed(timestamp, (0,), True)
            guide.feed(timestamp, (99,), True)
        self.assertEqual(len(guide.values), 12)
        guide.feed(400, (0,), True)
        self.assertTrue(guide.resting)
        guide.present(1, 400, "rest")
        for timestamp in (425, 450, 475, 500, 525):
            guide.feed(timestamp, (99,), True)
        self.assertEqual(guide.values, [])

    def test_yaw_range_setting_rejects_invalid_values(self):
        for value in (0, 31, float("nan"), True):
            with self.assertRaises(ValueError):
                DetectionConfig(head_yaw_separation=value)
