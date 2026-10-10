from types import SimpleNamespace
import unittest

from Vision.capture import CaptureError, CapturedImage, OpenCVCamera
from Vision.calibration import AxisCalibration, EyeCalibration
from Vision.geometry import EyeRatios
from Vision.landmarks import Observation
from Vision.pipeline import EyeBinding, VisionPipeline
from Vision.signals import Envelope, invalid
from Vision.tracking import Box, SubjectTracker
from test_streams import Clock


class TrackingTests(unittest.TestCase):
    def envelope(self, seq, time=None, session="s"):
        return Envelope(session, seq, seq * 30 if time is None else time)

    def test_detection_order_does_not_define_identity(self):
        tracker = SubjectTracker()
        a, b = Box(0.1, 0.1, 0.1, 0.2), Box(0.7, 0.1, 0.1, 0.2)
        ids = tracker.update(self.envelope(0), [a, b])
        changed = tracker.update(self.envelope(1), [Box(0.69, 0.1, 0.1, 0.2),
                                                    Box(0.11, 0.1, 0.1, 0.2)])
        self.assertEqual(changed, list(reversed(ids)))

    def test_loss_never_assigns_missing_subject_to_bystander(self):
        tracker = SubjectTracker()
        a, b = Box(0.1, 0.1, 0.1, 0.2), Box(0.7, 0.1, 0.1, 0.2)
        ids = tracker.update(self.envelope(0), [a, b])
        self.assertEqual(tracker.update(self.envelope(1), [b]), [ids[1]])
        after = tracker.update(self.envelope(2), [a, b])
        self.assertNotEqual(after[0], ids[0])
        self.assertEqual(after[1], ids[1])
        tracker.update(self.envelope(3), [])
        self.assertNotIn(tracker.update(self.envelope(4), [a])[0], ids)

    def test_crossing_and_ambiguous_candidates_end_tracks(self):
        tracker = SubjectTracker()
        old = tracker.update(self.envelope(0), [Box(0.2, 0.1, 0.2, 0.3),
                                               Box(0.5, 0.1, 0.2, 0.3)])
        crossing = [Box(0.34, 0.1, 0.2, 0.3), Box(0.36, 0.1, 0.2, 0.3)]
        new = tracker.update(self.envelope(1), crossing)
        self.assertFalse(set(old) & set(new))
        after = tracker.update(self.envelope(2), crossing)
        self.assertFalse(set(after) & set(new))

    def test_gap_and_large_size_change_end_track(self):
        for timestamp, changed in ((300, Box(0.1, 0.1, 0.1, 0.2)),
                                   (30, Box(0.1, 0.1, 0.3, 0.6))):
            tracker = SubjectTracker()
            old = tracker.update(self.envelope(0), [Box(0.1, 0.1, 0.1, 0.2)])
            self.assertNotEqual(tracker.update(self.envelope(1, timestamp), [changed]), old)

    def test_duplicate_backwards_and_over_limit_rejected(self):
        tracker = SubjectTracker()
        tracker.update(self.envelope(1), [])
        for envelope, boxes in ((self.envelope(1), []), (self.envelope(2, 20), []),
                                (self.envelope(2), [Box(0, 0, 0.1, 0.1)] * 3)):
            with self.assertRaises(ValueError):
                tracker.update(envelope, boxes)


class FakeCapture:
    def __init__(self, opened=True, fail_read=False):
        self.opened, self.fail_read = opened, fail_read
        self.releases = 0
        self.settings = []

    def isOpened(self):
        return self.opened

    def set(self, key, value):
        self.settings.append((key, value))
        return False  # The backend ignores requests; code must tolerate that.

    def read(self):
        return (False, None) if self.fail_read else (True, SimpleNamespace(size=1))

    def release(self):
        self.releases += 1


def fake_cv(capture):
    return SimpleNamespace(VideoCapture=lambda _: capture, CAP_PROP_FRAME_WIDTH=1,
                           CAP_PROP_FRAME_HEIGHT=2, CAP_PROP_FPS=3, CAP_PROP_BUFFERSIZE=4)


class CaptureTests(unittest.TestCase):
    def test_read_stamps_before_inference_and_paces_without_assuming_actual_fps(self):
        clock, capture = Clock(), FakeCapture()
        with OpenCVCamera(clock=clock, sleeper=clock.sleep, fps=20, cv2_module=fake_cv(capture)) as source:
            first = source.read()
            clock.now += 80  # Inference was slower than requested period.
            second = source.read()
            self.assertEqual(second.envelope.timestamp_ms - first.envelope.timestamp_ms, 80)
            self.assertEqual(clock.sleeps, [])
            third = source.read()
            self.assertEqual(third.envelope.timestamp_ms - second.envelope.timestamp_ms, 50)
            self.assertEqual(first.envelope.timestamp_ms, 1000)
        self.assertEqual(capture.releases, 1)

    def test_failed_open_and_read_release_and_emit_nothing(self):
        for capture in (FakeCapture(opened=False), FakeCapture(fail_read=True)):
            with self.subTest(opened=capture.opened), self.assertRaises(CaptureError):
                with OpenCVCamera(cv2_module=fake_cv(capture)) as source:
                    source.read()
            self.assertEqual(capture.releases, 1)

    def test_reopen_changes_session(self):
        capture = FakeCapture()
        source = OpenCVCamera(cv2_module=fake_cv(capture))
        with source:
            first = source.read().envelope
        with source:
            second = source.read().envelope
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(second.sequence, 0)

    def test_hardware_is_not_opened_by_construction(self):
        source = OpenCVCamera(cv2_module=SimpleNamespace())
        with self.assertRaises(CaptureError):
            source.read()


class PipelineTests(unittest.TestCase):
    def observation(self, *, closed=False, x=0.1):
        return Observation(Box(x, 0.1, 0.1, 0.2), (), eyes={
            "left": EyeRatios(0.5, 0, 0.02 if closed else 0.22),
            "right": EyeRatios(0.5, 0, 0.22),
        })

    def capture(self, sequence, session="session"):
        return CapturedImage(Envelope(session, sequence, sequence * 30), None)

    def binding(self, subject, quality=None):
        eye = EyeCalibration(0.02, 0.22, 0.5, AxisCalibration(0.2, 0.5, 0.8),
                             AxisCalibration(-0.1, 0, 0.1))
        return EyeBinding("session", subject, eye, eye,
                          quality or (lambda _: {"left": 0.8, "right": 0.7}), 0.15)

    def test_default_invalid_then_explicit_binding_enables_only_calibrated_signals(self):
        pipeline = VisionPipeline()
        initial = pipeline.process(self.capture(0), [self.observation()])
        self.assertTrue(all(item == invalid() for item in initial["faces"][0]["signals"].values()))
        pipeline.bind(self.binding(initial["faces"][0]["subject_id"]))
        output = pipeline.process(self.capture(1), [self.observation(closed=True)])
        self.assertEqual(output["timestamp_ms"], 30)
        signals = output["faces"][0]["signals"]
        self.assertEqual(signals["left_eye_open"]["value"], 0)
        self.assertEqual(signals["right_eye_open"]["value"], 1)
        self.assertEqual(signals["gaze_x"], invalid())
        self.assertEqual(signals["tongue_x"], invalid())
        self.assertEqual(signals["head_y"], invalid())

    def test_loss_clears_binding_even_while_bystander_remains(self):
        pipeline = VisionPipeline()
        first = pipeline.process(self.capture(0), [self.observation(), self.observation(x=0.7)])
        pipeline.bind(self.binding(first["faces"][0]["subject_id"]))
        lost = pipeline.process(self.capture(1), [self.observation(x=0.7)])
        self.assertIsNone(pipeline.binding)
        self.assertEqual(lost["faces"][0]["subject_id"], first["faces"][1]["subject_id"])
        returned = pipeline.process(self.capture(2), [self.observation()])
        self.assertTrue(all(item == invalid() for item in returned["faces"][0]["signals"].values()))

    def test_restart_never_inherits_calibration_even_with_same_id(self):
        pipeline = VisionPipeline()
        first = pipeline.process(self.capture(0), [self.observation()])
        pipeline.bind(self.binding(first["faces"][0]["subject_id"]))
        pipeline.process(self.capture(0, "new-session"), [self.observation()])
        self.assertIsNone(pipeline.binding)

    def test_broken_quality_assessor_clears_binding_and_stops(self):
        pipeline = VisionPipeline()
        first = pipeline.process(self.capture(0), [self.observation()])
        def broken(_):
            raise RuntimeError("quality unavailable")
        pipeline.bind(self.binding(first["faces"][0]["subject_id"], broken))
        with self.assertRaisesRegex(RuntimeError, "quality unavailable"):
            pipeline.process(self.capture(1), [self.observation()])
        self.assertIsNone(pipeline.binding)


if __name__ == "__main__":
    unittest.main()
