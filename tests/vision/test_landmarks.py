from types import SimpleNamespace
import unittest

from Vision.capture import CapturedImage
from Vision.landmarks import EYES, MediaPipeDetector, observation_from_landmarks
from Vision.overlay import display_point
from Vision.signals import Envelope


def synthetic_landmarks():
    points = [SimpleNamespace(x=0.5, y=0.4) for _ in range(478)]
    def set_point(index, x, y):
        points[index] = SimpleNamespace(x=x / 640, y=y / 480)
    set_point(168, 320, 180)
    set_point(61, 270, 310)
    set_point(291, 370, 310)
    for side, center, gap in (("left", 390, 8), ("right", 250, 0)):
        corners, pairs, iris = EYES[side]
        set_point(corners[0], center + 20, 200)
        set_point(corners[1], center - 20, 200)
        for i, (a, b) in enumerate(pairs):
            set_point(a, center + (i - 1) * 8, 200 - gap / 2)
            set_point(b, center + (i - 1) * 8, 200 + gap / 2)
        for i in iris:
            set_point(i, center - 4, 202)
    return points


class LandmarkTests(unittest.TestCase):
    def test_anatomical_eyes_remain_independent_and_use_pixel_aspect_ratio(self):
        observation = observation_from_landmarks(synthetic_landmarks(), 640, 480)
        self.assertAlmostEqual(observation.eyes["left"].openness, 0.2)
        self.assertAlmostEqual(observation.eyes["right"].openness, 0)
        self.assertAlmostEqual(observation.eyes["left"].horizontal, 0.6)
        self.assertAlmostEqual(observation.eyes["left"].vertical, 0.05)
        self.assertEqual(observation.head_reference.right, (-1, 0))
        self.assertEqual(observation.head_reference.down, (0, 1))

    def test_preview_mirroring_does_not_change_measurements(self):
        observation = observation_from_landmarks(synthetic_landmarks(), 640, 480)
        p = observation.points[EYES["left"][0][0]]
        self.assertEqual(display_point(p, 640, mirrored=False), (410, 200))
        self.assertEqual(display_point(p, 640, mirrored=True), (229, 200))
        self.assertAlmostEqual(observation.eyes["left"].openness, 0.2)

    def test_missing_iris_and_occluded_eye_stay_unavailable(self):
        points = synthetic_landmarks()
        self.assertEqual(observation_from_landmarks(points[:468], 640, 480).eyes, {})
        points[474].x = -1
        observation = observation_from_landmarks(points, 640, 480)
        self.assertNotIn("left", observation.eyes)
        self.assertIn("right", observation.eyes)

    def test_bad_face_geometry_raises_instead_of_fabricating_no_faces(self):
        points = synthetic_landmarks()
        points[0].x = float("nan")
        with self.assertRaises(ValueError):
            observation_from_landmarks(points, 640, 480)

    def test_detector_preserves_capture_time_and_converts_bgr_before_inference(self):
        # Exercise the adapter without importing third-party modules or a model.
        detector = MediaPipeDetector(__file__)
        calls = []
        fake_image = SimpleNamespace(shape=(480, 640, 3))
        def convert(image, conversion):
            self.assertIs(image, fake_image)
            self.assertEqual(conversion, "BGR2RGB")
            calls.append("converted")
            return "rgb pixels"
        def infer(image, timestamp):
            calls.append(timestamp)
            self.assertEqual(image, ("SRGB", "rgb pixels"))
            return SimpleNamespace(face_landmarks=[synthetic_landmarks()])
        detector.cv2 = SimpleNamespace(cvtColor=convert, COLOR_BGR2RGB="BGR2RGB")
        detector.mp = SimpleNamespace(Image=lambda **kw: (kw["image_format"], kw["data"]),
                                      ImageFormat=SimpleNamespace(SRGB="SRGB"))
        detector.landmarker = SimpleNamespace(detect_for_video=infer)
        first = CapturedImage(Envelope("s", 0, 1000.2), fake_image)
        second = CapturedImage(Envelope("s", 1, 1000.8), fake_image)
        self.assertEqual(len(detector.detect(first)), 1)
        detector.detect(second)
        self.assertEqual(calls, ["converted", 1000, "converted", 1001])
        self.assertEqual(first.envelope.timestamp_ms, 1000.2)
        self.assertEqual(second.envelope.timestamp_ms, 1000.8)
        with self.assertRaises(ValueError):
            detector.detect(first)


if __name__ == "__main__":
    unittest.main()
