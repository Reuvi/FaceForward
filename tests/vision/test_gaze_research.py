"""Known synthetic eye/pose relationship; does not validate human gaze accuracy."""

import importlib.util
import unittest
from copy import deepcopy
from Vision.gaze_research import BASE, fit_gaze, predict, validate_model, evaluate


def episodes():
    result = []
    for role in ("train", "validation"):
        for pose, yaw, pitch in (
            ("neutral", 0, 0),
            ("left", -0.3, 0),
            ("right", 0.3, 0),
            ("up", 0, -0.25),
            ("down", 0, 0.25),
        ):
            for x in (0.15, 0.5, 0.85):
                for y in (0.15, 0.5, 0.85):
                    values = dict(
                        zip(
                            BASE,
                            (
                                x - 0.7 * yaw,
                                y - 0.65 * pitch,
                                x - 0.7 * yaw,
                                y - 0.65 * pitch,
                                yaw,
                                pitch,
                                0,
                                0.5,
                                0.5,
                                -0.8,
                            ),
                        )
                    )
                    result.append(
                        dict(role=role, pose=pose, target=[x, y], values=values)
                    )
    return result


@unittest.skipUnless(importlib.util.find_spec("numpy"), "numpy required")
class GazeTests(unittest.TestCase):
    def test_pose_compensation_beats_eyes_and_predicts_fixed_target_across_head_turns(
        self,
    ):
        data = episodes()
        model, report = fit_gaze(data, [1440, 900])
        validate_model(model)
        self.assertTrue(model["report"]["beats_eyes"])
        self.assertLess(model["report"]["p95_px"], 5)
        for e in data:
            output = predict(model, e["values"])
            self.assertIsNotNone(output)
            for a, b in zip(output, e["target"]):
                self.assertAlmostEqual(a, b, delta=0.004)
        scores = evaluate(model, data)
        self.assertEqual(scores["targets"], 9)
        self.assertEqual(scores["poses"], 5)

    def test_missing_closed_eye_and_unseen_pose_are_unknown(self):
        model, _ = fit_gaze(episodes(), [1440, 900])
        values = deepcopy(episodes()[0]["values"])
        values["yaw"] = 2
        self.assertIsNone(predict(model, values))
        values["left_iris_x"] = None
        self.assertIsNone(predict(model, values))

    def test_invalid_models_and_insufficient_target_coverage_rejected(self):
        model, _ = fit_gaze(episodes(), [1440, 900])
        for key, value in (
            ("scale", None),
            ("weights", [[0, 0]]),
            ("viewport", [0, 900]),
            ("low", [float("nan")] * len(model["low"])),
        ):
            bad = deepcopy(model)
            bad[key] = value
            with self.assertRaises(ValueError):
                validate_model(bad)
        with self.assertRaises(ValueError):
            fit_gaze(episodes()[:10], [1440, 900])

    def test_errors_are_measured_before_clipping(self):
        model, _ = fit_gaze(episodes(), [1440, 900])
        model["weights"][0][0] = 2
        self.assertGreater(evaluate(model, episodes())["median_px"], 1500)
