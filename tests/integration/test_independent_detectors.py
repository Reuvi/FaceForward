"""Shared fast samples, delayed tongue evidence, calibration and native snapshots."""
import importlib.util
import time
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    import numpy as np
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.features import DetectionConfig
    from Vision.signals import Envelope
    from Vision.tongue import TongueResult
    from Vision.tongue_async import AsyncTongue
    from Vision.tongue_segment import SegmentedTongueModel
    from Vision.tongue_worker import TongueReply


class ManualWorker:
    """No completion until the test explicitly supplies captured evidence."""
    def __init__(self):
        self.pending = self.reply = None
        self.replaced = self.completed = 0

    def submit(self, job):
        self.replaced += self.pending is not None
        self.pending = job

    def invalidate(self):
        self.pending = self.reply = None

    def take(self):
        reply, self.reply = self.reply, None
        return reply

    def finish(self, result=None, *, job=None, error=None):
        self.reply = TongueReply(job or self.pending, result or TongueResult(),
                                 dict(error=error, inference_ms=150, confidence=.9))
        self.completed += 1

    def state(self):
        return dict(error=None, hz=5, submitted=1, completed=self.completed,
                    replaced=self.replaced, pending=int(self.pending is not None))

    def close(self):
        self.invalidate()


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class IndependentDetectors(unittest.TestCase):
    def setUp(self):
        self.now = 1000.; self.sequence = 0
        self.session = MouseSession(clock=lambda: self.now)
        self.addCleanup(self.session.close)
        self.session.mode = "detector-demo"
        self.runtime = self.session.ensure_detector_runtime()
        self.core = self.runtime.workbench
        self.core.config = DetectionConfig(settle_ms=0, collect_ms=300, min_samples=5, movement_rest_ms=100)
        self.worker = ManualWorker()
        self.core.async_tongue = AsyncTongue(self.worker)
        self.core.tongue_model = SegmentedTongueModel("/unused.onnx")
        self.core.head = AxisCalibration(-12, 0, 12, endpoint_tolerance=.05)
        self.core.eyes = {side: EyeCalibration(.04, .25, .5) for side in ("left", "right")}
        self.feed()

    def feed(self, *, blank=False, session="camera", step=25, **controls):
        self.now += step; self.sequence += 1
        bgr, observations = demo_image(tongue=True, **controls)
        return self.session.deliver_detection(
            CapturedImage(Envelope(session, self.sequence, self.now), bgr),
            [] if blank else observations, preview=False)

    def ready_tongue(self):
        self.core.tongue_range = {key: AxisCalibration(-.2, 0, .2) for key in ("x", "y")}
        self.core.validation = {key: {"passed": True} for key in ("validate_visible", "validate_absent")}

    def test_all_fast_features_and_every_frame_continue_without_tongue_completion(self):
        with patch.object(self.core.tongue_model, "detect", side_effect=AssertionError("inference on camera thread")):
            for index in range(24):
                frame = self.feed(head=.3 if index % 2 else .7, left_closed=index % 3 == 1,
                                  right_closed=index % 3 == 2, pupil_x=.3 if index % 2 else .7)
                self.assertEqual(frame["sequence"], self.sequence)
                self.assertEqual(frame["eye_intent"]["timestamp_ms"], self.now)
                self.assertTrue(frame["faces"][0]["signals"]["head_y"]["valid"])
                self.assertTrue(frame["faces"][0]["signals"]["left_eye_open"]["valid"])
                self.assertTrue(frame["faces"][0]["signals"]["right_eye_open"]["valid"])
                self.assertFalse(frame["faces"][0]["signals"]["tongue_x"]["valid"])
        self.assertEqual(len(self.core.trace), 25)
        self.assertGreater(self.worker.replaced, 20)
        self.assertGreater(len({row["head_raw"] for row in self.core.trace}), 1)
        self.assertGreater(len({row["left_raw"] for row in self.core.trace}), 1)
        self.assertGreater(len({row["right_raw"] for row in self.core.trace}), 1)
        self.assertGreater(len({row["pupil_raw_x"] for row in self.core.trace if row["pupil_raw_x"] is not None}), 1)
        self.assertEqual(self.runtime.snapshot()["trace"][-1]["sequence"], self.sequence)

    def test_original_timestamp_held_graph_and_expiry_with_matching_crop_overlay(self):
        self.ready_tongue()
        job = self.worker.pending
        job.crop.bgr[:] = (10, 20, 30)
        result = TongueResult(xy=(.1, 0), quality=.9, mask=np.zeros((160, 160), np.uint8))
        self.worker.finish(result)
        frame = self.feed(head=.8)
        self.assertEqual(frame["tongue_sample"]["sequence"], job.sequence)
        self.assertEqual(frame["tongue_sample"]["timestamp_ms"], job.timestamp_ms)
        self.assertTrue(frame["faces"][0]["signals"]["tongue_x"]["valid"])
        self.assertTrue(self.core.trace[-1]["tongue_new"])
        self.assertTrue(np.array_equal(self.runtime.snapshot()["mouth"][0, 0], [10, 20, 30]))
        self.assertFalse(np.array_equal(self.core.crop.bgr[0, 0], [10, 20, 30]))
        frame = self.feed()
        self.assertTrue(frame["faces"][0]["signals"]["tongue_x"]["valid"])
        self.assertFalse(self.core.trace[-1]["tongue_new"])
        self.assertIsNone(self.core.trace[-1]["tongue_tip_x"])
        self.assertEqual(frame["tongue_sample"]["timestamp_ms"], job.timestamp_ms)
        for _ in range(10):
            frame = self.feed()
        self.assertFalse(frame["faces"][0]["signals"]["tongue_x"]["valid"])
        self.assertTrue(frame["faces"][0]["signals"]["head_y"]["valid"])
        self.assertIn("stale", self.core.tongue.reason)

    def test_late_replies_after_reset_loss_load_restart_and_old_generation_are_discarded(self):
        for action in ("reset", "loss", "load", "restart", "generation"):
            with self.subTest(action=action):
                self.feed()
                old_job = self.worker.pending
                if action == "reset":
                    self.core.reset_tongue()
                elif action == "loss":
                    self.feed(blank=True)
                elif action == "load":
                    self.core.load_calibration(self.core.export_calibration())
                elif action == "restart":
                    self.feed(session="new")
                else:
                    self.core.start_eye_guide(0)
                self.worker.finish(TongueResult(xy=(.1, 0), quality=1), job=old_job)
                frame = self.feed(session="new" if action == "restart" else "camera")
                self.assertIsNone(frame["tongue_sample"]["sequence"])
                self.assertIsNone(self.core.tongue.xy)
                self.core.cancel()

    def test_calibration_counts_unique_captures_and_never_trains_on_held_values(self):
        self.core.start_movement_guide("tongue")
        self.core.present_movement_step(0, "prepare")
        self.feed()
        self.worker.finish()  # One actual absent result.
        self.feed()
        guide = self.core.movement_guide
        self.assertEqual(len(guide.values), 1)
        for _ in range(24):
            self.feed()
        self.assertFalse(guide.active)
        self.assertFalse(guide.passed)
        self.assertIn("too few", guide.report)
        self.assertEqual(len(guide.values), 1)

    def test_capture_window_delivery_grace_and_rest_exclusion(self):
        self.core.start_movement_guide("tongue")
        guide = self.core.movement_guide
        self.core.present_movement_step(0, "prepare")
        self.feed()
        for _ in range(4):
            self.worker.finish(); self.feed()
        while self.now < guide.start_ms + 275:
            self.feed()
        last_job = self.worker.pending
        self.feed(step=75)  # Deliver the last in-window result after capture ends.
        self.worker.finish(job=last_job); self.feed()
        self.assertEqual(len(guide.values), 5)
        deadline = guide.start_ms + 550
        while self.now < deadline:
            self.feed()
        self.assertTrue(guide.active)
        self.assertTrue(guide.absence["passed"])
        self.assertEqual(guide.absence["samples"], 5)
        self.assertTrue(guide.resting)
        self.core.present_movement_step(guide.index, "rest")
        for _ in range(5):
            self.worker.finish(TongueResult(xy=(.1, 0), quality=1)); self.feed()
        self.assertEqual(guide.values, [])
        self.assertIsNone(guide.start_ms)

    def test_old_out_of_order_and_future_reply_cannot_replace_newer_evidence(self):
        old = self.worker.pending
        self.feed(); current = self.worker.pending
        self.worker.finish(TongueResult(xy=(.1, 0), quality=1))
        self.feed()
        self.worker.finish(TongueResult(xy=(-.1, 0), quality=1), job=old)
        frame = self.feed()
        self.assertEqual(frame["tongue_sample"]["sequence"], current.sequence)
        self.assertEqual(self.core.tongue.xy, (.1, 0))
        from dataclasses import replace
        future = replace(current, timestamp_ms=self.now+200)
        self.worker.finish(TongueResult(xy=(-.1, 0), quality=1), job=future)
        self.feed()
        self.assertEqual(self.core.tongue.xy, (.1, 0))

    def test_hung_tongue_cannot_hang_guide_or_other_calibration(self):
        self.core.start_movement_guide("tongue")
        self.core.present_movement_step(0, "prepare")
        start = time.perf_counter()
        for _ in range(25):
            self.feed()
        self.assertLess(time.perf_counter()-start, 2)
        self.assertFalse(self.core.movement_guide.active)
        self.assertIn("too few", self.core.movement_guide.report)
        self.core.start_movement_guide("head")
        self.core.present_movement_step(0, "prepare")
        for _ in range(13):
            self.feed()
        self.assertEqual(self.core.movement_guide.index, 1)
