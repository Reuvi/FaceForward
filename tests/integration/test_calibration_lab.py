"""Pixels → calibrated measurements → real Processing, without camera or OS input."""

from copy import deepcopy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from App.mouse_runtime import MouseSession
from Processing.mouse.controller import Lab
from Processing.mouse.profiles import read_profile, write_profile

AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))
if AVAILABLE:
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope
    from Vision.presets import decode_preset


@unittest.skipUnless(AVAILABLE, "Install Vision requirements for combined pixel tests")
class UnifiedCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.sequence = 0
        self.lab = Lab(clock=lambda:self.now)
        self.session = MouseSession(self.lab, clock=lambda:self.now)
        self.session.mode = "detector-demo"
        self.addCleanup(self.session.close)
        self.core = self.session.ensure_detector_runtime().workbench
        self.session.detector_command("configure", {"settle_ms":0,"collect_ms":400,"min_samples":8})
        self.feed()
        self.session.select_subject(self.session.frame["faces"][0]["subject_id"])

    def feed(self, blank=False, **controls):
        self.now += 25
        self.sequence += 1
        image, observations = demo_image(**controls)
        self.session.deliver_detection(CapturedImage(Envelope("test",self.sequence,self.now),image),
                                       [] if blank else observations, preview=False)
        self.lab.step(self.now)
        return self.lab.state()["snapshot"]

    def hold(self, count=24, **controls):
        for _ in range(count):result=self.feed(**controls)
        return result

    def collect(self, target, **controls):
        self.session.detector_command("collect",target)
        while self.core.job is not None:self.feed(**controls)

    def calibrate(self):
        for side in ("left","right"):
            self.collect(side+"_open")
            self.collect(side+"_closed",**{side+"_closed":True})
        for target,head in (("up",.2),("neutral",.5),("down",.8)):
            self.collect("head_"+target,head=head)
        self.collect("tongue_absent")
        self.feed(tongue=True)
        self.session.detector_command("freeze_mouth")
        self.session.detector_command("mark_tongue",.5,.5)
        self.session.detector_command("fit_tongue")
        self.collect("validate_absent")
        self.collect("validate_visible",tongue=True)

    def guided_eyes(self):
        self.session.detector_command("start_eye_guide")
        while self.core.eye_guide.active:
            guide=self.core.eye_guide
            self.session.detector_command("present_eye_step",guide.index)
            index=guide.index
            while guide.active and guide.index==index:
                controls=self.session.detector_runtime.demo_input()
                self.feed(**controls)
                self.assertFalse(self.lab.processor.armed)

    def test_guided_pixels_independence_unknown_and_profile_roundtrip(self):
        self.guided_eyes()
        self.assertEqual(set(self.core.eyes),{"left","right"})
        self.assertEqual(set(self.session.research.processor.fits),{"eyeBlinkLeft","eyeBlinkRight"})
        self.feed(left_ratio=.14,right_closed=True)
        signals=self.session.frame["faces"][0]["signals"]
        self.assertEqual(signals["left_eye_open"]["value"],1)
        self.assertEqual(signals["right_eye_open"]["value"],0)
        self.feed(left_ratio=.5)
        self.assertEqual(self.core.frame["faces"][0]["signals"]["left_eye_open"]["value"],1)
        self.lab.action({"action":"arm"});self.hold()
        result=self.hold(left_closed=True,right_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(1,1))
        result=self.feed(left_ratio=.09,right_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(0,1))
        self.assertIsNone(self.core.trace[-1]["left_closed_bit"])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"eyes.json"
            self.session.save_profile(path)
            detector=read_profile(path)["detector"]
            self.assertEqual(detector["version"],2)
            self.session.load_profile(path)
            self.assertFalse(self.lab.processor.armed)
            self.feed(left_ratio=.09)
            self.assertFalse(self.core.frame["faces"][0]["signals"]["left_eye_open"]["valid"])
            # Old profiles remain readable; they retain the original single threshold.
            detector["version"]=1;detector["algorithm"]="lid-gap-head-y-lab-color-v1"
            for fit in detector["eyes"].values():
                del fit["closed_limit"];del fit["open_limit"]
            _,eyes,_,_=decode_preset(detector)
            self.assertIsNone(eyes["left"].closed_limit)

    def test_guided_restart_cancel_loss_and_mixed_jobs(self):
        self.calibrate()
        old_head=self.core.head
        self.lab.action({"action":"arm"});self.hold()
        self.session.detector_command("start_eye_guide")
        self.assertFalse(self.lab.processor.armed)
        self.assertFalse(self.core.eyes)
        self.assertEqual(self.core.head,old_head)
        with self.assertRaises(ValueError):self.core.collect("head_up")
        with self.assertRaises(ValueError):self.core.export_calibration()
        with self.assertRaises(ValueError):self.core.reset_tongue()
        self.lab.action({"action":"arm"});self.feed()
        self.assertFalse(self.lab.processor.armed)
        self.session.detector_command("present_eye_step",0)
        self.hold(count=5)
        self.session.detector_command("start_eye_guide")
        self.assertEqual(self.core.eye_guide.groups,{"left":[],"right":[]})
        self.assertIsNone(self.core.eye_guide.start_ms)
        self.session.detector_command("cancel")
        self.assertFalse(self.core.calibrating)
        self.assertFalse(self.core.eyes)
        self.session.detector_command("start_eye_guide")
        self.feed(blank=True)
        self.assertIsNone(self.core.eye_guide)
        self.assertIsNone(self.core.selected)

    def test_calibration_feeds_all_four_mouse_outputs(self):
        self.calibrate()
        self.assertFalse(self.lab.processor.armed)
        self.lab.action({"action":"arm"})
        self.hold(tongue=True)
        result=self.hold(tongue=True,left_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(1,0))
        result=self.hold(tongue=True,right_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(0,1))
        result=self.hold(tongue=True,left_closed=True,right_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(1,1))
        result=self.hold(tongue=True,tongue_x=.72,head=.78)
        self.assertGreater(result["pointer_x"],.51)
        self.assertGreater(result["scroll_y"],.51)
        self.assertEqual(self.lab.state()["raw"]["sequence"],self.core.frame["sequence"])
        self.assertFalse(self.session.frame["diagnostic_only"])
        self.assertTrue(self.core.frame["diagnostic_only"])
        self.assertIsNone(self.session.detector_runtime.worker)  # No second producer.

    def test_calibration_changes_disarm_immediately_and_during_capture(self):
        self.calibrate()
        self.lab.action({"action":"arm"});self.hold(tongue=True)
        self.assertEqual(self.hold(left_closed=True,tongue=True)["left_click"],1)
        self.session.detector_command("collect","right_open")
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.lab.action({"action":"arm"})
        self.feed(left_closed=True,tongue=True)
        self.assertFalse(self.lab.processor.armed)
        self.session.detector_command("cancel")
        self.assertFalse(self.lab.processor.armed)

    def test_combined_profile_roundtrip_rebinds_but_requires_tongue_recheck(self):
        self.calibrate()
        config=self.lab.processor.config.to_dict()
        config["left_eye"]["dwell_ms"]=500
        self.lab.settings({"config":config,"runtime":{"pointer_speed":1000}})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"face.json"
            self.session.save_profile(path)
            saved=read_profile(path)
            self.assertNotIn("validation",saved["detector"])
            self.assertNotIn("session_id",saved)
            self.assertNotIn("samples",saved["detector"])
            self.feed(blank=True)
            self.assertFalse(self.session.state()["profile_bound"])
            with self.assertRaises(ValueError):self.session.load_profile(path)
            self.feed()
            self.session.select_subject(self.session.frame["faces"][0]["subject_id"])
            self.session.load_profile(path)
            self.assertTrue(self.session.state()["profile_bound"])
            self.assertFalse(self.lab.processor.armed)
            self.feed(tongue=True)
            signals=self.session.frame["faces"][0]["signals"]
            self.assertTrue(signals["left_eye_open"]["valid"])
            self.assertTrue(signals["head_y"]["valid"])
            self.assertFalse(signals["tongue_x"]["valid"])
            self.assertEqual(self.lab.processor.config.left_eye.dwell_ms,500)
            self.assertEqual(self.lab.state()["runtime"]["pointer_speed"],1000)
            self.collect("validate_absent")
            self.collect("validate_visible",tongue=True)
            self.feed(tongue=True)
            self.assertTrue(self.session.frame["faces"][0]["signals"]["tongue_x"]["valid"])
            self.assertTrue(self.session.state()["profile_bound"])
            self.assertFalse(self.lab.processor.armed)

    def test_profile_malformed_or_wrong_source_is_atomic(self):
        self.calibrate()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"face.json";self.session.save_profile(path)
            baseline=self.core.export_calibration()
            saved=read_profile(path)
            saved["detector"]["eyes"]["left"]["opened"]=float("nan")
            with self.assertRaises(ValueError):decode_preset(saved["detector"])
            saved=read_profile(path);saved["detector"]["algorithm"]="wrong"
            write_profile(path,saved)
            with self.assertRaises(ValueError):self.session.load_profile(path)
            self.assertEqual(self.core.export_calibration(),baseline)
            saved["detector"]=baseline;saved["source_kind"]="camera";write_profile(path,saved)
            with self.assertRaises(ValueError):self.session.load_profile(path)
            self.assertEqual(self.core.export_calibration(),baseline)

    def test_each_eye_partial_profile_and_stale_load(self):
        self.collect("left_open");self.collect("left_closed",left_closed=True)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"left.json";self.session.save_profile(path)
            self.session.load_profile(path);self.feed(left_closed=True)
            signals=self.session.frame["faces"][0]["signals"]
            self.assertTrue(signals["left_eye_open"]["valid"])
            self.assertFalse(signals["right_eye_open"]["valid"])
            self.now+=300
            with self.assertRaises(ValueError):self.session.load_profile(path)
            self.assertIsNone(self.core.selected)

    def test_stop_clears_current_binding_and_output(self):
        self.calibrate();self.lab.action({"action":"arm"});self.hold(tongue=True)
        self.assertEqual(self.hold(left_closed=True,tongue=True)["left_click"],1)
        self.session.stop()
        self.assertIsNone(self.core.selected)
        self.assertFalse(self.core.eyes)
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.assertEqual(self.lab.state()["message"]["buttons"],{"left":0,"right":0})

    def test_stale_profile_read_disarms_and_marks_binding_detached(self):
        self.collect("left_open");self.collect("left_closed",left_closed=True)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"left.json";self.session.save_profile(path)
            self.lab.action({"action":"arm"});self.hold()
            self.assertEqual(self.hold(left_closed=True)["left_click"],1)
            self.now+=300
            state=self.session.state()
            self.assertFalse(state["profile_bound"])
            self.assertFalse(self.lab.processor.armed)
            self.assertFalse(state["frame"]["faces"][0]["signals"]["left_eye_open"]["valid"])

    def test_bad_detector_sections_reject_before_mutating_live_calibration(self):
        self.calibrate()
        baseline=self.core.export_calibration()
        mutations=(lambda d:d.update(version=True),
                   lambda d:d["eyes"]["left"].update(threshold=1),
                   lambda d:d["eyes"].update(center=d["eyes"]["left"]),
                   lambda d:d["head"].update(center=50),
                   lambda d:d["head"].update(endpoint_tolerance=.09),
                   lambda d:d["tongue"].update(positive=[[0,0,999]]),
                   lambda d:d["tongue"].update(radius=100),
                   lambda d:d["tongue"].update(margin=-1))
        for mutate in mutations:
            bad=deepcopy(baseline);mutate(bad)
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),baseline)


@unittest.skipUnless(AVAILABLE, "Install Vision requirements for combined pixel tests")
class DetectorWorkerTests(unittest.TestCase):
    def test_one_producer_eof_and_restart_clear_calibration(self):
        import threading
        from unittest.mock import patch
        session=MouseSession();self.addCleanup(session.close)
        session.lab.start()
        entered,release=threading.Event(),threading.Event()
        real=demo_image
        def blocked_demo(**controls):
            entered.set()
            if not release.wait(2):raise RuntimeError("test worker timed out")
            return real(**controls)
        with patch("Vision.demo_detection.demo_image",blocked_demo):
            session.start("detector-demo",count=2,fps=120,preview=False)
            self.assertTrue(entered.wait(1))
            try:
                with self.assertRaises(ValueError):session.start("camera",model="unused")
                self.assertIsNone(session.detector_runtime.worker)
            finally:release.set()
            session.thread.join(2)
        self.assertFalse(session.thread.is_alive())
        self.assertIsNone(session.error)
        self.assertEqual(session.received,2)
        first=session.frame["session_id"]
        self.assertIsNone(session.detector_runtime.workbench.selected)
        session.start("detector-demo",count=2,fps=120,preview=False)
        session.thread.join(2)
        self.assertFalse(session.thread.is_alive())
        self.assertIsNone(session.error)
        self.assertNotEqual(first,session.frame["session_id"])
        self.assertFalse(session.lab.state()["message"]["enabled"])
