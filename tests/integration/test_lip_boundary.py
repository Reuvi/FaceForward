"""Built-in tongue backend through the same capture/profile/native App path."""

from copy import deepcopy
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    import numpy as np
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.lip_boundary import LipBoundaryModel
    from Vision.signals import Envelope
    from Vision.tongue_async import AsyncTongue
    from Vision.tongue_segment import SegmentedTongueModel
    from test_independent_detectors import ManualWorker


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class BoundaryIntegration(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.seq = 0
        self.session = MouseSession(clock=lambda: self.now)
        self.addCleanup(self.session.close)
        self.session.mode = "detector-demo"
        self.runtime = self.session.ensure_detector_runtime()
        self.core = self.runtime.workbench
        self.worker = ManualWorker()
        self.core.async_tongue = AsyncTongue(self.worker)
        self.core.head = AxisCalibration(-12, 0, 12, endpoint_tolerance=0.05)
        self.core.head_x = AxisCalibration(-12, 0, 12, endpoint_tolerance=0.05)
        self.core.eyes = {"left": EyeCalibration(0.04, 0.25, 0.5)}
        self.core.tongue_model = LipBoundaryModel()
        self.feed()

    def feed(self, blank=False, **controls):
        self.now += 25
        self.seq += 1
        image, obs = demo_image(tongue=True, **controls)
        return self.session.deliver_detection(
            CapturedImage(Envelope("boundary", self.seq, self.now), image),
            [] if blank else obs,
            preview=False,
        )

    def test_fast_features_keep_sampling_when_color_worker_has_no_reply(self):
        with patch.object(
            self.core.tongue_model,
            "detect",
            side_effect=AssertionError("must run off camera thread"),
        ):
            for i in range(30):
                frame = self.feed(head_x=0.3 if i % 2 else 0.7, left_closed=i % 3 == 0)
                signals = frame["faces"][0]["signals"]
                self.assertTrue(signals["head_x"]["valid"])
                self.assertTrue(signals["head_y"]["valid"])
                self.assertTrue(signals["left_eye_open"]["valid"])
                self.assertFalse(signals["tongue_x"]["valid"])
                self.assertEqual(frame["sequence"], self.seq)
                self.assertEqual(frame["eye_intent"]["timestamp_ms"], self.now)
        self.assertEqual(self.worker.pending.backend, "lip-boundary")
        self.assertGreater(self.worker.replaced, 25)
        self.assertEqual(len(self.core.trace), 31)

    def test_overlay_uses_completed_capture_and_raw_tabs_share_same_trace(self):
        job = self.worker.pending
        result = LipBoundaryModel().detect(job.crop, job.config)
        self.assertIsNotNone(result.xy, result.reason)
        self.worker.finish(result)
        self.feed(tongue_x=0.8)
        self.assertIs(self.core.async_tongue.crop, job.crop)
        state = self.runtime.snapshot()
        self.assertEqual(state["candidate"], result.xy)
        self.assertEqual(state["trace"][-1]["tongue_sequence"], job.sequence)
        self.assertEqual(state["trace"][-1]["tongue_timestamp_ms"], job.timestamp_ms)
        self.assertTrue(np.any(np.all(state["mouth"] == (255, 200, 0), axis=2)))
        self.assertEqual(
            state["trace"],
            self.session.state(include_detector=True)["detector"]["trace"],
        )
        self.feed(blank=True)
        self.worker.finish(result, job=job)
        self.feed()
        self.assertIsNone(self.core.tongue.xy)  # old epoch cannot reappear after loss

    def test_backend_switch_and_reset_preserve_other_fits(self):
        old = (
            self.core.head,
            self.core.head_x,
            dict(self.core.eyes),
        )
        self.core.tongue_model = SegmentedTongueModel("/unused.onnx")
        self.core.tongue_range = {k: AxisCalibration(-0.2, 0, 0.2) for k in ("x", "y")}
        self.session.lab.processor.armed = True
        self.session.detector_command("use_lip_boundary")
        self.assertFalse(self.session.lab.processor.armed)
        self.assertIsInstance(self.core.tongue_model, LipBoundaryModel)
        self.assertIsNone(self.core.tongue_range)
        self.session.detector_command("reset_tongue")
        self.assertIsInstance(self.core.tongue_model, LipBoundaryModel)
        self.assertEqual(
            (
                self.core.head,
                self.core.head_x,
                self.core.eyes,
            ),
            old,
        )

    def test_profile_identity_roundtrip_and_old_neural_migration_are_atomic(self):
        self.core.tongue_range = {
            k: AxisCalibration(-0.2, 0, 0.2, endpoint_tolerance=0.05)
            for k in ("x", "y")
        }
        data = self.core.export_calibration()
        self.assertEqual(data["version"], 10)
        self.core.load_calibration(data)
        self.assertEqual(self.core.export_calibration(), data)
        self.assertEqual(self.core.validation, {})
        for identity in (
            None,
            dict(data["tongue"], algorithm="unsupported"),
            dict(data["tongue"], extra=True),
        ):
            bad = deepcopy(data)
            bad["tongue"] = identity
            with self.assertRaises(ValueError):
                self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(), data)
        self.core.tongue_model = SegmentedTongueModel()
        neural = self.core.export_calibration()
        self.core.load_calibration(neural)
        self.assertIsInstance(
            self.core.tongue_model, SegmentedTongueModel
        )  # v9 explicit choice survives
        legacy_nine=deepcopy(neural)
        legacy_nine.update(version=9,algorithm="lip-boundary-head-reliability-v9")
        legacy_nine["pupil"]=dict(measurement="mediapipe_iris_direction_v2",x_sensitivity=2,y_sensitivity=.5)
        self.core.load_calibration(legacy_nine)
        self.assertIsInstance(self.core.tongue_model,SegmentedTongueModel)
        self.assertIsNotNone(self.core.tongue_range)
        for version, algorithm in (
            (8, "direct-mediapipe-pupils-v8"),
            (7, "independent-head-axes-v7"),
            (6, "tongue-segmentation-pupil-joystick-v6"),
        ):
            old = deepcopy(neural)
            old.update(version=version, algorithm=algorithm)
            old["pupil"] = dict(measurement="mediapipe_iris_direction_v2", x_sensitivity=1., y_sensitivity=1.)
            if version < 8:
                old["pupil"] = None
            if version < 7:
                old.pop("head_x")
            self.core.load_calibration(old)
            self.assertIsInstance(self.core.tongue_model, LipBoundaryModel)
            self.assertIsNone(self.core.tongue_range)
            self.assertEqual(self.core.head.center, 0)
            self.assertIn("Old neural tongue range removed", self.core.notice)

    @unittest.skipUnless(os.environ.get("RUN_TK_TESTS") == "1", "native Tk check")
    def test_native_instructions_and_backend_controls(self):
        import tkinter as tk
        from Vision.lab import DetectionLab

        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.geometry("1230x910")
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        with (
            patch("Vision.movement_view.CalibrationSounds"),
            patch("Vision.eye_view.CalibrationSounds"),
        ):
            ui = DetectionLab(
                root, SimpleNamespace(demo=False, camera=False), runtime=self.runtime
            )
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.tongue_tab)
            ui.tick()
            root.update()
            self.assertIn("Lip-boundary", ui.tongue_setup.backend_title.get())
            self.assertIn("Blue outline", ui.tongue_setup.backend_help.get())
            self.assertFalse(ui.tongue_setup.legacy_top.winfo_ismapped())
            self.assertEqual(str(ui.tongue_setup.use_boundary["state"]), "disabled")
            self.assertTrue(ui.head_x_panel.retry.winfo_exists())
            self.assertEqual(errors, [])
