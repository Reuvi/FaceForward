from math import cos, sin
import unittest

from Vision.calibration import AxisCalibration, EyeCalibration, calibrated_eye, combine_gaze
from Vision.geometry import EyeRatios, eye_ratios, tongue_ratios
from Vision.signals import invalid


class GeometryTests(unittest.TestCase):
    def transform(self, p, angle, scale, offset):
        x, y = p
        return (offset[0] + scale * (x * cos(angle) - y * sin(angle)),
                offset[1] + scale * (x * sin(angle) + y * cos(angle)))

    def test_eye_ratios_invariant_to_translation_roll_and_scale(self):
        for angle, scale, offset in ((0, 1, (0, 0)), (0.6, 3, (42, -9)), (-1.1, 0.4, (-12, 80))):
            transform = lambda p: self.transform(p, angle, scale, offset)
            down = self.transform((0, 1), angle, scale, (0, 0))
            result = eye_ratios(transform((10, 0)), transform((-10, 0)),
                                [(transform((x, -2)), transform((x, 2))) for x in (-3, 0, 3)],
                                transform((-4, 1)), down)
            self.assertAlmostEqual(result.horizontal, 0.7)
            self.assertAlmostEqual(result.vertical, 0.05)
            self.assertAlmostEqual(result.openness, 0.2)

    def test_vertical_gaze_does_not_divide_by_lid_opening(self):
        readings = [eye_ratios((10, 0), (-10, 0), [((0, -gap), (0, gap))], (0, 1), (0, 1))
                    for gap in (0, 0.1, 1, 3)]
        self.assertEqual([result.vertical for result in readings], [0.05] * 4)
        self.assertEqual(readings[0].openness, 0)

    def test_tongue_continuous_and_invariant_to_head_image_motion(self):
        for angle, scale, offset in ((0, 1, (0, 0)), (0.8, 2.5, (18, 24)), (-0.3, 0.7, (-40, -20))):
            transform = lambda p: self.transform(p, angle, scale, offset)
            result = tongue_ratios(
                transform((10, 0)), transform((-10, 0)), transform((0, -5)),
                transform((0, 5)), transform((2.6, 1.4)),
                self.transform((0, 1), angle, scale, (0, 0)),
            )
            self.assertAlmostEqual(result[0], 0.37)
            self.assertAlmostEqual(result[1], 0.64)

    def test_bad_references_and_outside_tongue_are_rejected(self):
        with self.assertRaises(ValueError):
            eye_ratios((0, 0), (0, 0), [((0, 0), (0, 1))], (0, 0), (0, 1))
        for centroid, bottom in (((11, 0), (0, 5)), ((0, 6), (0, 5)),
                                 ((0, 0), (0, -5)), ((float("nan"), 0), (0, 5))):
            with self.subTest(centroid=centroid, bottom=bottom), self.assertRaises(ValueError):
                tongue_ratios((10, 0), (-10, 0), (0, -5), bottom, centroid, (0, 1))


class CalibrationTests(unittest.TestCase):
    def test_axis_endpoints_center_both_directions_and_invalid_values(self):
        for values in ((-2, 1, 5), (4, 2, -6)):
            calibration = AxisCalibration(*values)
            for raw, expected in zip(values, (0, 0.5, 1)):
                self.assertEqual(calibration.normalize(raw), expected)
            self.assertEqual(calibration.normalize((values[0] + values[1]) / 2), 0.25)
            for invalid_raw in (float("nan"), float("inf"), -100, 100, None, True):
                self.assertIsNone(calibration.normalize(invalid_raw))

    def test_axis_tolerance_is_explicit_and_bounded(self):
        self.assertIsNone(AxisCalibration(0, 0.5, 1).normalize(1.01))
        self.assertEqual(AxisCalibration(0, 0.5, 1, 0.02).normalize(1.01), 1)
        with self.assertRaises(ValueError):
            AxisCalibration(0, 0.5, 1, 0.5)

    def test_fit_rejects_overlapping_missing_and_unstable_targets(self):
        result = AxisCalibration.fit([0] * 10 + [100], [1] * 10, [2] * 10, min_separation=0.1)
        self.assertEqual(result.center, 1)
        for low, center, high in (([0] * 4, [1] * 5, [2] * 5),
                                  ([0] * 5, [0] * 5, [2] * 5),
                                  ([0, 0, 0, 100, 100], [1] * 5, [2] * 5)):
            with self.assertRaises(ValueError):
                AxisCalibration.fit(low, center, high, min_separation=0.1)

    def eye(self):
        return EyeCalibration.fit([0.02] * 6, [0.22] * 6, min_separation=0.05,
                                  gaze_x=AxisCalibration(0.2, 0.5, 0.8),
                                  gaze_y=AxisCalibration(-0.1, 0, 0.1))

    def test_binary_eye_threshold_and_no_dwell(self):
        eye = EyeCalibration(0.02, 0.22, 0.5)
        boundary = eye.closed + eye.threshold * (eye.opened - eye.closed)
        for raw, expected in ((0.02, 0), (boundary - 1e-9, 0), (boundary, 1), (0.22, 1)):
            result = eye.classify(raw, 0.8)
            self.assertEqual(result["value"], expected)
            self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(eye.classify(0, 0.8)["value"], 0)
        self.assertEqual(eye.classify(0.22, None), invalid())

    def test_eye_fit_rejects_overlapping_classes(self):
        with self.assertRaises(ValueError):
            EyeCalibration.fit([0.1] * 6, [0.11] * 6, min_separation=0.05)

    def test_unilateral_closure_and_validated_single_eye_mode(self):
        left = calibrated_eye(EyeRatios(0.5, 0, 0.02), self.eye(), 0.8)
        right = calibrated_eye(EyeRatios(0.5, 0, 0.22), self.eye(), 0.7)
        self.assertEqual(left["open"]["value"], 0)
        self.assertEqual(right["open"]["value"], 1)
        self.assertEqual(left["gaze_x"], invalid())
        self.assertEqual(combine_gaze(left, right, disagreement_tolerance=0.1)["gaze_x"], invalid())
        single = combine_gaze(left, right, disagreement_tolerance=0.1, allow_single_eye=True)
        self.assertEqual(single["gaze_x"]["value"], 0.5)

    def test_gaze_disagreement_is_per_axis_and_missing_calibration_invalid(self):
        left = calibrated_eye(EyeRatios(0.2, 0, 0.22), self.eye(), 0.8)
        right = calibrated_eye(EyeRatios(0.8, 0, 0.22), self.eye(), 0.7)
        combined = combine_gaze(left, right, disagreement_tolerance=0.2)
        self.assertEqual(combined["gaze_x"], invalid())
        self.assertEqual(combined["gaze_y"]["value"], 0.5)
        self.assertTrue(all(x == invalid() for x in calibrated_eye(None, None, 1).values()))


if __name__ == "__main__":
    unittest.main()
