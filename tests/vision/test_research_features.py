"""Asymmetric eye normalization and quality gates for the selected capture."""

import importlib.util
import math
from types import SimpleNamespace
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("cv2"), "Vision pixel dependencies required"
)
class FeatureTests(unittest.TestCase):
    def make(self, **controls):
        from Vision.demo_detection import demo_image
        from Vision.features import analyze_features, DetectionConfig
        from Vision.calibration import EyeCalibration

        image, observations = demo_image(**controls)
        obs = observations[0]
        core = SimpleNamespace(
            frame={"session_id": "s", "sequence": 3, "timestamp_ms": 1200},
            selected="face",
            observations={"face": obs},
            features=analyze_features(image, obs, DetectionConfig()),
            eyes={
                "left": EyeCalibration(0.04, 0.25, 0.5),
                "right": EyeCalibration(0.02, 0.16, 0.5),
            },
            generation=2,
        )
        return core, obs

    def test_asymmetric_normalization_and_closed_iris_are_independent(self):
        from Vision.research_features import feature_frame

        core, obs = self.make(left_ratio=0.04, right_ratio=0.16)
        frame = feature_frame(core)
        v = frame["values"]
        self.assertAlmostEqual(v["left_closure"], 1)
        self.assertAlmostEqual(v["right_closure"], 0)
        self.assertIsNone(v["left_iris_x"])
        self.assertIsNotNone(v["right_iris_x"])
        self.assertEqual(frame["sequence"], 3)
        self.assertEqual(frame["generation"], 2)

    def test_no_expression_is_unknown_not_zero_and_eye_quality_is_separate(self):
        from Vision.research_features import feature_frame

        core, obs = self.make()
        obs.expressions = {}
        self.assertIsNone(feature_frame(core)["values"]["eyeBlinkLeft"])
        core.features["left"] = SimpleNamespace(value=0.25, quality=0)
        v = feature_frame(core)["values"]
        self.assertIsNone(v["left_closure"])
        self.assertIsNotNone(v["right_closure"])
        core.features["face"] = SimpleNamespace(value=1, quality=0)
        v = feature_frame(core)["values"]
        self.assertIsNone(v["yaw"])
        self.assertIsNone(v["right_closure"])

    def test_yaw_pitch_roll_rotation_order_and_sign(self):
        import numpy as np
        from Vision.research_features import feature_frame

        core, obs = self.make()
        yaw, pitch, roll = 0.2, -0.15, 0.1
        c, s = math.cos, math.sin
        rx = np.array([[1, 0, 0], [0, c(pitch), -s(pitch)], [0, s(pitch), c(pitch)]])
        ry = np.array([[c(yaw), 0, s(yaw)], [0, 1, 0], [-s(yaw), 0, c(yaw)]])
        rz = np.array([[c(roll), -s(roll), 0], [s(roll), c(roll), 0], [0, 0, 1]])
        obs.rotation = rz @ ry @ rx
        values = feature_frame(core)["values"]
        for key, expected in [("yaw", yaw), ("pitch", pitch), ("roll", roll)]:
            self.assertAlmostEqual(values[key], expected)
        core.selected = "other"
        self.assertIsNone(feature_frame(core))
