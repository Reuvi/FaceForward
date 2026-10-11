"""Whole Vision → Processing checks with no camera, Tk, or OS input."""

from copy import deepcopy
from dataclasses import replace
import unittest
import importlib.util
from unittest.mock import patch

from App.mouse_runtime import MouseSession
from Processing.mouse.controller import Lab
from Vision.calibration import EyeCalibration
from Vision.capture import CapturedImage
from Vision.geometry import EyeRatios
from Vision.landmarks import Observation
from Vision.mouse_demo import SUBJECT, mouse_demo_records
from Vision.pipeline import EyeBinding, VisionPipeline
from Vision.signals import Envelope, measurement
from Vision.sources import replay
from Vision.tracking import Box


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.lab = Lab(clock=self.clock)
        self.session = MouseSession(self.lab, clock=self.clock)
        self.addCleanup(self.session.close)
        self.outputs = []

    def tick(self):
        self.lab.step(self.clock())
        self.outputs.append(deepcopy(self.lab.state()["snapshot"]))

    def sleep(self, seconds):
        due = self.clock() + seconds * 1000
        while self.clock() < due:
            self.clock.value = min(due, self.clock() + 10)
            self.tick()

    def play(self, records):
        for frame in replay(records, clock=self.clock, sleeper=self.sleep):
            self.session.deliver(frame)
            self.tick()

    def test_vision_demo_drives_all_four_mouse_behaviors(self):
        self.lab.action({"action": "arm"})
        self.play(mouse_demo_records(count=490))
        left = sum(b["left_click"] and not a["left_click"] for a, b in zip(self.outputs, self.outputs[1:]))
        right = sum(b["right_click"] and not a["right_click"] for a, b in zip(self.outputs, self.outputs[1:]))
        self.assertEqual((left, right), (2, 2))  # Individual wink + both, no short blink.
        for key in ("pointer_x", "pointer_y", "scroll_y"):
            self.assertLess(min(o[key] for o in self.outputs), 0.4)
            self.assertGreater(max(o[key] for o in self.outputs), 0.6)
        self.assertTrue(all(o["subject_id"] == SUBJECT for o in self.outputs))
        self.assertEqual(self.session.accepted, 490)
        self.assertEqual(self.lab.state()["raw"]["schema_version"], 1)
        # Continuous Vision values are not quantized through the one-hot adapter.
        self.assertTrue(any(o["diagnostics"]["raw_pointer"] and
                            o["diagnostics"]["raw_pointer"][0] not in (0.5, 0.75, 1)
                            for o in self.outputs))

    def test_bound_vision_eye_classifier_reaches_independent_clicks(self):
        pipeline = VisionPipeline()
        base = Observation(Box(0.1, 0.1, 0.3, 0.4), (), eyes={
            "left": EyeRatios(0.5, 0, 0.22), "right": EyeRatios(0.5, 0, 0.22)})
        calibration = EyeCalibration(0.02, 0.22, 0.5)
        # Fixture assessor only; this does not assert live-camera quality.
        pipeline.bind(EyeBinding("pipeline-test", "subject-0", calibration, calibration,
                                 lambda obs: {"left": 1, "right": 1}, 0.1))
        self.lab.settings({"runtime": {"subject_id": "subject-0"}})
        self.lab.action({"action": "arm"})
        for index in range(41):
            self.clock.value = 1000 + index * 20
            observation = replace(base, eyes={
                "left": EyeRatios(0.5, 0, 0.02 if index >= 10 else 0.22),
                "right": EyeRatios(0.5, 0, 0.22)})
            frame = pipeline.process(CapturedImage(Envelope("pipeline-test", index, self.clock()), None), [observation])
            self.session.deliver(frame)
            self.tick()
        self.assertEqual(self.outputs[-1]["left_click"], 1)
        self.assertEqual(self.outputs[-1]["right_click"], 0)
        self.assertEqual(self.outputs[-1]["pointer_x"], 0.5)  # Unsupported pupil input stays invalid.

    def test_subject_loss_is_visible_and_never_transfers_to_bystander(self):
        self.lab.action({"action": "arm"})
        self.play(mouse_demo_records(count=85))
        frame = deepcopy(self.session.frame)
        frame["sequence"] += 1; frame["timestamp_ms"] = self.clock.value = self.clock() + 20
        frame["faces"][0]["subject_id"] = "bystander"
        result = self.session.deliver(frame)
        self.tick()
        self.assertFalse(result["accepted"])
        self.assertFalse(self.outputs[-1]["enabled"])
        self.assertEqual(self.outputs[-1]["left_click"], 0)
        self.assertIsNone(self.outputs[-1]["diagnostics"]["raw_pointer"])
        self.assertIsNone(self.outputs[-1]["diagnostics"]["left_closed"])
        self.assertEqual(self.lab.state()["raw"]["faces"][0]["subject_id"], "bystander")
        self.assertEqual(self.lab.state()["runtime"]["subject_id"], SUBJECT)
        self.session.select_subject("bystander")
        self.assertFalse(self.lab.processor.armed)

    def test_newer_sequence_same_timestamp_is_accepted_without_dwell_progress(self):
        self.lab.action({"action": "arm"})
        frame = next(mouse_demo_records(count=1))
        frame["timestamp_ms"] = self.clock()
        self.assertTrue(self.session.deliver(frame)["accepted"])
        self.tick()
        frame = deepcopy(frame); frame["sequence"] += 1
        frame["faces"][0]["signals"]["gaze_x"] = measurement(0.7, 1)
        self.assertTrue(self.session.deliver(frame)["accepted"])
        self.tick()
        self.assertEqual(len(self.lab.processor.pointer.history), 1)
        self.assertEqual(self.outputs[-1]["source_sequence"], 1)
        self.assertEqual(self.outputs[-1]["left_click"], 0)
        self.assertFalse(self.session.deliver(frame)["accepted"])

    def test_dropouts_and_explicit_stop_release_all_output(self):
        self.lab.action({"action": "arm"})
        self.play(mouse_demo_records(count=80))
        self.assertEqual(self.outputs[-1]["left_click"], 1)
        self.sleep(0.3)
        self.assertFalse(self.outputs[-1]["enabled"])
        self.assertEqual(self.outputs[-1]["left_click"], 0)
        self.session.stop()
        self.assertEqual(self.lab.state()["message"]["velocity"], {"x": 0.5, "y": 0.5, "scroll": 0.5})
        self.assertFalse(self.lab.state()["message"]["enabled"])

    def test_malformed_vision_input_disarms_and_mock_source_cannot_override(self):
        self.lab.action({"action": "arm"})
        self.play(mouse_demo_records(count=3))
        with self.assertRaises(ValueError):
            self.session.deliver({"schema_version": 99})
        self.assertFalse(self.lab.state()["message"]["enabled"])
        with self.assertRaises(ValueError):
            self.lab.settings({"runtime": {"source": "mock"}})

    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ("cv2", "numpy")), "Install Vision requirements for camera adapter")
    def test_camera_adapter_exposes_pupil_motion_without_calibration(self):
        clock = self.clock
        from Vision.demo_detection import demo_image
        image, observations = demo_image()
        observation = observations[0]
        observation.eyes["left"] = EyeRatios(0.42, -0.02, 0.24)

        class Camera:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return CapturedImage(Envelope("camera-stub", 0, clock()), image)

        class Detector(Camera):
            def detect(self, captured): return [observation]

        with patch("Vision.capture.OpenCVCamera", Camera), patch("Vision.landmarks.MediaPipeDetector", Detector):
            self.session._camera(0, "stub-model", 30, False, 1)
        state = self.session.state()
        self.assertEqual(state["observations"]["single-user"]["eyes"]["left"]["openness"], 0.24)
        values = state["frame"]["faces"][0]["signals"]
        self.assertTrue(values["gaze_x"]["valid"])
        self.assertTrue(values["gaze_y"]["valid"])
        self.assertFalse(values["head_y"]["valid"])
        self.assertFalse(values["left_eye_open"]["valid"])
        self.assertIsNotNone(self.session.detector_runtime.workbench.trace[-1]["pupil_raw_x"])
        self.assertIsNone(self.session.detector_runtime.workbench.pupil_model)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.session = MouseSession()
        self.addCleanup(self.session.close)
        self.session.lab.start()

    def test_eof_and_error_disarm_and_a_new_run_gets_a_new_session(self):
        self.session.start("demo", count=3, fps=120)
        self.session.thread.join(2)
        self.assertFalse(self.session.thread.is_alive())
        first = self.session.frame["session_id"]
        self.assertEqual(self.session.status, "Vision source ended")
        self.assertFalse(self.session.lab.state()["message"]["enabled"])
        self.session.start("demo", count=3, fps=120)
        self.session.thread.join(2)
        self.assertNotEqual(self.session.frame["session_id"], first)
        self.session.start("replay", path="/nonexistent-mouse-mvp-fixture.ndjson")
        self.session.thread.join(2)
        self.assertIsNotNone(self.session.error)
        self.assertFalse(self.session.lab.state()["message"]["enabled"])

    def test_one_producer_and_stop_interrupts_long_replay_wait(self):
        records = list(mouse_demo_records(count=2))
        records[1]["timestamp_ms"] = 100000
        with patch("App.mouse_runtime.read_ndjson", return_value=iter(records)):
            self.session.start("replay", path="fixture.ndjson")
            with self.assertRaises(ValueError):
                self.session.start("demo")
            self.session.stop()
            self.session.thread.join(1)
        self.assertFalse(self.session.thread.is_alive())
        self.assertFalse(self.session.lab.state()["message"]["enabled"])
        with self.assertRaises(RuntimeError):
            self.session.lab.start()


if __name__ == "__main__":
    unittest.main()
