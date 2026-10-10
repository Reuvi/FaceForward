"""Pixels → calibrated measurements → real Processing, without camera or OS input."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
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
    from Vision.signals import SINGLE_SUBJECT, Envelope
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
        self.session.detector_command("configure", {"settle_ms":0,"collect_ms":400,"eye_rest_ms":100,"movement_rest_ms":0,"min_samples":8})
        self.feed()
        self.assertEqual(self.core.selected, SINGLE_SUBJECT)
        self.assertEqual(self.lab.runtime["subject_id"], SINGLE_SUBJECT)

    def feed(self, blank=False, box=None, session_id="test", missing_eye=None, **controls):
        self.now += 25
        self.sequence += 1
        image, observations = demo_image(**controls)
        if missing_eye:
            observations[0].expressions.pop("eyeSquint"+missing_eye.title())
        if box is not None:
            observations[0].box = replace(observations[0].box, **box)
        self.session.deliver_detection(CapturedImage(Envelope(session_id,self.sequence,self.now),image),
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
        self.guided_eyes()
        for target,head in (("up",.2),("neutral",.5),("down",.8)):
            self.collect("head_"+target,head=head)
        self.collect("tongue_absent")
        self.feed(tongue=True)
        self.session.detector_command("freeze_mouth")
        self.session.detector_command("mark_tongue",.5,.5)
        self.session.detector_command("fit_tongue")
        self.collect("validate_absent")
        self.collect("validate_visible",tongue=True)
        self.guided_movement("tongue")

    def test_v4_migration_keeps_eyes_winks_head_but_discards_centroid_tongue(self):
        self.calibrate()
        original = deepcopy(self.core.export_calibration())
        legacy = deepcopy(original)
        legacy.update(version=4, algorithm="personal-head-tongue-ranges-v4")
        legacy.pop("tongue_measurement")
        legacy["tongue_range"] = {
            axis: dict(low=.2, center=.5, high=.8, endpoint_tolerance=.05)
            for axis in ("x", "y")
        }
        for key in tuple(legacy["settings"]):
            if key.startswith("tongue_tip_"): legacy["settings"].pop(key)
        invalid = deepcopy(legacy)
        invalid["tongue_range"]["x"]["low"] = -.2
        with self.assertRaises(ValueError): self.core.load_calibration(invalid)
        self.assertEqual(self.core.export_calibration(), original)
        self.core.load_calibration(legacy)
        migrated = self.core.export_calibration()
        for key in ("eyes", "winks", "head"):
            self.assertEqual(migrated[key], original[key])
        self.assertEqual(migrated["version"], 5)
        self.assertIsNone(migrated["tongue"])
        self.assertIsNone(migrated["tongue_range"])
        self.assertIn("repeat appearance and tip range", self.core.notice)

    def guided_movement(self,kind):
        self.session.detector_command("start_movement_guide",kind)
        while self.core.movement_guide.active:
            guide=self.core.movement_guide;state=guide.state(self.now)
            if state["waiting"]:self.session.detector_command("present_movement_step",guide.index,state["phase"])
            self.feed(**self.session.detector_runtime.demo_input())
            self.assertFalse(self.lab.processor.armed)
        self.assertTrue(self.core.movement_guide.passed,self.core.notice)

    def guided_eyes(self):
        for command in ("start_eye_guide", "start_wink_guide"):
            self.session.detector_command(command)
            self.finish_eye_guide()

    def finish_eye_guide(self, **overrides):
        while self.core.eye_guide.active:
            guide=self.core.eye_guide
            state=guide.state(self.now)
            if state['waiting']:
                self.session.detector_command("present_eye_step",guide.index,state['phase'])
            controls=dict(self.session.detector_runtime.demo_input(), **overrides)
            self.feed(**controls)
            self.assertFalse(self.lab.processor.armed)
            self.assertEqual(self.lab.processor.eye_sample['sequence'],self.sequence)

    def test_restarting_eye_calibration_clears_processing_history(self):
        self.guided_eyes()
        self.feed(left_closed=True)
        self.assertEqual(self.lab.processor.eye_sample['left']['value'],1.)
        self.session.detector_command("start_eye_guide")
        self.assertIsNone(self.lab.processor.eye_sample)
        self.feed(left_closed=True)
        for sample in (self.lab.processor.eye_sample,):
            self.assertEqual(sample['left'],{'value':0.,'known':False})

    def test_failed_blink_training_retries_without_changing_other_calibration(self):
        self.calibrate()
        eyes = dict(self.core.eyes)
        head, tongue = self.core.head, self.core.tongue_model
        tongue_range = deepcopy(self.core.tongue_range)
        self.lab.action({"action":"arm"}); self.hold()
        self.assertEqual(self.feed(left_closed=True)["left_click"], 1)
        self.session.detector_command("start_wink_guide")
        self.assertFalse(self.lab.processor.armed)
        self.assertIsNone(self.lab.processor.eye_sample)
        self.assertFalse(self.core.winks)
        # Incorrect blink capture: never actually close either eye.
        self.finish_eye_guide(left_closed=False, right_closed=False, natural_blink=False)
        self.assertFalse(self.core.winks)
        self.assertIn("Too few train blinks", self.core.notice)
        self.assertEqual(self.core.eyes, eyes)
        self.assertIs(self.core.head, head)
        self.assertIs(self.core.tongue_model, tongue)
        self.assertEqual(self.core.tongue_range, tongue_range)
        self.session.detector_command("start_wink_guide")
        self.assertEqual(self.core.eye_guide.state(self.now)["total"], 14)
        self.finish_eye_guide()
        self.assertEqual(set(self.core.winks), {"left", "right"}, self.core.notice)
        self.assertEqual(self.core.eyes, eyes)

    def test_geometry_can_be_saved_loaded_and_survives_wink_cancel_and_loss(self):
        with self.assertRaises(ValueError): self.session.detector_command("start_wink_guide")
        self.session.detector_command("start_eye_guide")
        self.finish_eye_guide()
        self.assertEqual(self.core.eye_guide.state(self.now)["total"], 7)
        self.assertFalse(self.core.winks)
        eyes = dict(self.core.eyes)
        self.assertEqual(set(eyes), {"left", "right"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"eye-geometry.json"
            self.session.save_profile(path)
            self.session.detector_command("reset_calibration")
            self.session.load_profile(path)
        self.assertEqual(self.core.eyes, eyes)
        for end in ("cancel", "loss"):
            self.feed()
            self.session.detector_command("start_wink_guide")
            old_generation = self.core.generation
            self.session.detector_command("start_wink_guide")
            self.session.detector_command("present_eye_step", 0, "prepare", old_generation)
            self.assertIsNone(self.core.eye_guide.start_ms)
            if end == "cancel": self.session.detector_command("cancel")
            else: self.feed(blank=True)
            self.assertEqual(self.core.eyes, eyes)
            self.assertIsNone(self.core.eye_guide)
            self.assertFalse(self.core.winks)

    def test_incomplete_geometry_cannot_seed_wink_training(self):
        self.session.detector_command("start_eye_guide")
        while self.core.eye_guide.step[0] != "reopen":
            guide = self.core.eye_guide
            state = guide.state(self.now)
            if state["waiting"]: self.session.detector_command("present_eye_step", guide.index, state["phase"])
            self.feed(**self.session.detector_runtime.demo_input())
        self.assertTrue(self.core.eye_guide.fits)  # Provisional, before fresh reopen check.
        self.assertFalse(self.core.eyes)
        with self.assertRaises(ValueError): self.session.detector_command("start_wink_guide")
        self.session.detector_command("cancel")
        with self.assertRaises(ValueError): self.session.detector_command("start_wink_guide")

    def test_large_box_jump_loss_and_recovery_keep_fits_and_held_unknown_sample(self):
        self.guided_eyes()
        detector = self.core.export_calibration()
        generation = self.core.generation
        # This move/scale change would previously retire the geometric tracker ID.
        self.feed(box={"x":.01, "y":.01, "width":.1, "height":.1})
        self.assertEqual(self.core.selected, SINGLE_SUBJECT)
        self.assertEqual(self.core.export_calibration(), detector)
        self.lab.action({"action":"arm"}); self.hold()
        self.assertEqual(self.hold(left_closed=True)["left_click"], 1)
        self.feed(blank=True)
        self.assertFalse(self.lab.processor.armed)
        self.assertEqual(self.lab.state()["message"]["buttons"], {"left":0,"right":0})
        for sample in (self.lab.processor.eye_sample,):
            self.assertEqual(sample["sequence"], self.sequence)
            self.assertEqual(sample["left"], {"value":1., "known":False})
        self.feed(left_closed=True)
        self.assertTrue(self.core.frame["faces"][0]["signals"]["left_eye_open"]["valid"])
        self.assertEqual(self.core.export_calibration(), detector)
        self.assertEqual(self.core.generation, generation)
        self.assertFalse(self.lab.processor.armed)
        self.lab.action({"action":"arm"})
        self.assertEqual(self.hold(left_closed=True)["left_click"], 0)
        self.hold()
        self.assertEqual(self.hold(left_closed=True)["left_click"], 1)

    def test_same_source_restart_keeps_fits_source_switch_resets(self):
        self.calibrate()
        detector = self.core.export_calibration()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"saved.json"
            self.session.save_profile(path)
            self.session.stop()
            self.session.save_profile(path)  # Completed calibration can be saved while stopped.
            with patch("App.mouse_runtime.threading.Thread") as thread:
                thread.return_value.is_alive.return_value = False
                self.session.start("detector-demo", preview=False)
                self.feed(session_id="restarted")
                self.assertTrue(self.session.state()["profile_bound"])
                self.assertEqual(self.core.export_calibration(), detector)
                self.assertEqual(self.core.validation, {})
                self.assertIsNotNone(self.core.tongue_model)
                self.assertFalse(self.lab.processor.armed)
                self.session.stop()
                self.session.start("demo", preview=False)
                self.assertFalse(self.core.eyes)
                self.assertFalse(self.session.state()["profile_bound"])

    def test_load_saved_calibration_before_first_capture(self):
        self.guided_eyes()
        detector = self.core.export_calibration()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"saved.json"
            self.session.save_profile(path)
            fresh = MouseSession(clock=lambda:self.now)
            self.addCleanup(fresh.close)
            fresh.mode = "detector-demo"
            fresh.load_profile(path)
            self.assertIsNone(fresh.frame)
            self.assertEqual(fresh.detector_runtime.workbench.export_calibration(), detector)
            self.assertFalse(fresh.lab.processor.armed)
            self.assertTrue(fresh.state()["profile_bound"])
            image, observations = demo_image()
            fresh.deliver_detection(CapturedImage(Envelope("fresh",0,self.now),image),observations,preview=False)
            self.assertEqual(fresh.detector_runtime.workbench.selected,SINGLE_SUBJECT)
            self.assertTrue(fresh.frame["faces"][0]["signals"]["left_eye_open"]["valid"])
            fresh.detector_command("reset_calibration")
            self.assertFalse(fresh.detector_runtime.workbench.eyes)
            self.assertFalse(fresh.state()["profile_bound"])

    def test_guided_pixels_independence_unknown_and_profile_roundtrip(self):
        self.guided_eyes()
        self.assertEqual(set(self.core.eyes),{"left","right"})
        self.assertEqual(set(self.core.winks),{"left","right"})
        self.feed(left_ratio=.14,right_closed=True)
        signals=self.session.frame["faces"][0]["signals"]
        self.assertEqual(signals["left_eye_open"]["value"],1)
        self.assertEqual(signals["right_eye_open"]["value"],0)
        self.feed(left_ratio=.5)
        self.assertEqual(self.core.frame["faces"][0]["signals"]["left_eye_open"]["value"],1)
        self.lab.action({"action":"arm"});self.hold()
        # Identical eyelid closure geometry: supporting features distinguish the
        # natural blink from a wink, with no duration delay in either direction.
        result=self.hold(count=50,natural_blink=True)
        self.assertEqual((result["left_click"],result["right_click"]),(0,0))
        self.feed()
        self.assertEqual(self.feed(left_closed=True)["left_click"],1)
        self.assertEqual(self.feed()["left_click"],0)
        result=self.hold(left_closed=True,right_closed=True)
        self.assertEqual((result["left_click"],result["right_click"]),(1,1))
        result=self.feed(left_ratio=.09,right_closed=True,missing_eye="left")
        self.assertEqual((result["left_click"],result["right_click"]),(0,1))
        self.assertIsNone(self.core.trace[-1]["left_closed_bit"])
        for sample in (self.lab.state()['eye_sample'],):
            self.assertEqual(sample['sequence'],self.session.frame['sequence'])
            self.assertEqual(sample['left'],{'value':1.,'known':False})
            self.assertEqual(sample['right'],{'value':1.,'known':True})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"eyes.json"
            self.session.save_profile(path)
            detector=read_profile(path)["detector"]
            corrupted=read_profile(path)
            corrupted["detector"]["winks"]["left"]["weights"]=[]
            broken=Path(directory)/"broken.json"
            write_profile(broken,corrupted)
            with self.assertRaises(ValueError):self.session.load_profile(broken)
            self.assertEqual(self.core.export_calibration(),detector)
            self.assertEqual(detector["version"],5)
            self.assertEqual(read_profile(path)["format"],"face_mouse_profile_v3")
            self.assertEqual(detector['settings']['eye_rest_ms'],100)
            self.session.load_profile(path)
            self.assertFalse(self.lab.processor.armed)
            self.feed(left_ratio=.09,missing_eye="left")
            self.assertFalse(self.core.frame["faces"][0]["signals"]["left_eye_open"]["valid"])
            for sample in (self.lab.state()['eye_sample'],):
                self.assertEqual(sample['left'],{'value':0.,'known':False})
            # Old profiles remain readable; they retain the original single threshold.
            detector["version"]=1;detector["algorithm"]="lid-gap-head-y-lab-color-v1"
            detector.pop("winks")
            detector.pop("tongue_range")
            detector.pop("tongue_measurement")
            for fit in detector["eyes"].values():
                del fit["closed_limit"];del fit["open_limit"]
            _,eyes,_,_=decode_preset(detector)
            self.assertIsNone(eyes["left"].closed_limit)
            detector['settings'].pop('eye_rest_ms')
            restored,_,_,_=decode_preset(detector)
            self.assertEqual(restored.eye_rest_ms,3000)
            for version in (1,2):
                legacy=read_profile(path)
                legacy["format"]=f"face_mouse_profile_v{version}"
                legacy["detector"]=deepcopy(detector) if version==1 else deepcopy(read_profile(path)["detector"])
                if version==2:
                    from Processing.research.settings import settings
                    legacy["detector"].update(version=2,algorithm="guided-lid-gap-head-y-lab-color-v2")
                    legacy["detector"].pop("winks")
                    legacy["detector"].pop("tongue_range")
                    legacy["detector"].pop("tongue_measurement")
                    legacy["research"]={"settings":settings(),"fits":{},"pose_bounds":{},"models":{},"gaze":None}
                old_path=Path(directory)/f"legacy{version}.json"
                write_profile(old_path,legacy)
                self.session.load_profile(old_path)
                self.assertEqual(self.core.winks,{})
                self.lab.action({"action":"arm"});self.feed()
                self.assertEqual(self.feed(left_closed=True)["left_click"],0)
                self.assertEqual(self.core.frame["faces"][0]["signals"]["left_eye_open"]["value"],0)
                self.assertFalse(self.core.frame["eye_intent"]["left"]["known"])

    def test_rest_duration_setting_validates_before_clearing_a_fit(self):
        self.collect('left_open')
        self.collect('left_closed',left_closed=True)
        previous=dict(self.core.eyes)
        for value in ('bad','-1','31','nan'):
            with self.assertRaises(ValueError):self.session.detector_command('start_eye_guide',value)
            self.assertEqual(self.core.eyes,previous)
        self.session.detector_command('start_eye_guide','2.5')
        self.assertEqual(self.core.config.eye_rest_ms,2500)
        self.assertEqual(self.core.eye_guide.config.eye_rest_ms,2500)

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
        result=self.hold(tongue=True,tongue_x=.65,head=.78)
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
            self.assertTrue(self.session.state()["profile_bound"])
            self.session.load_profile(path)  # Loading works while the face is absent.
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
            self.session.load_profile(path)  # Stale camera data is not required for loading.
            self.assertIsNone(self.core.selected)
            self.assertIn("left", self.core.eyes)
            self.assertFalse(self.lab.processor.armed)

    def test_stop_preserves_calibration_and_releases_output(self):
        self.calibrate();self.lab.action({"action":"arm"});self.hold(tongue=True)
        self.assertEqual(self.hold(left_closed=True,tongue=True)["left_click"],1)
        self.session.stop()
        self.assertIsNone(self.core.selected)
        self.assertEqual(set(self.core.eyes), {"left", "right"})
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.assertEqual(self.lab.state()["message"]["buttons"],{"left":0,"right":0})

    def test_stale_profile_read_disarms_and_keeps_profile(self):
        self.guided_eyes()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"left.json";self.session.save_profile(path)
            self.lab.action({"action":"arm"});self.hold()
            self.assertEqual(self.hold(left_closed=True)["left_click"],1)
            self.now+=300
            state=self.session.state()
            self.assertTrue(state["profile_bound"])
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
