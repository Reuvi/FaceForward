"""Independent head axes through native calibration, saved profiles and shared trace."""
from copy import deepcopy
import importlib.util
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.calibration import EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope


@unittest.skipUnless(AVAILABLE, "Vision pixel dependencies required")
class HorizontalHeadTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.; self.sequence=0
        self.session=MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.session.mode="detector-demo"
        self.runtime=self.session.ensure_detector_runtime(); self.core=self.runtime.workbench
        self.session.detector_command("configure", dict(settle_ms=0, collect_ms=300, min_samples=5, movement_rest_ms=0))
        self.feed()

    def feed(self, *, blank=False, no_pose=False, **controls):
        self.now+=25; self.sequence+=1
        bgr, obs=demo_image(**controls)
        if no_pose: obs[0].rotation=None
        return self.session.deliver_detection(CapturedImage(Envelope("heads",self.sequence,self.now),bgr),
                                              [] if blank else obs, preview=False)

    def guide(self, kind, *, positions=None):
        self.session.detector_command("start_movement_guide",kind)
        for _ in range(120):
            guide=self.core.movement_guide
            if not guide.active: break
            state=guide.state(self.now)
            if state["waiting"]:
                self.session.detector_command("present_movement_step",state["index"],state["phase"],self.core.generation)
            controls=self.runtime.demo_input()
            if positions:
                controls["head_x"]=positions[state["name"]]
            self.feed(**controls)
            self.assertFalse(self.session.lab.processor.armed)
        self.assertFalse(guide.active)
        return guide

    def test_full_range_asymmetry_and_reversed_raw_sign_preserve_pitch(self):
        self.assertTrue(self.guide("head").passed)
        pitch=self.core.head
        self.core.eyes["left"]=EyeCalibration(.04,.25,.5)
        eye=self.core.eyes["left"]
        for positions in (dict(left=.2,neutral=.55,right=.8), dict(left=.85,neutral=.6,right=.2)):
            self.assertTrue(self.guide("head_x",positions=positions).passed, self.core.notice)
            self.assertEqual(self.core.head,pitch); self.assertEqual(self.core.eyes["left"],eye)
            for pose,want in ((positions["left"],0),(positions["neutral"],.5),(positions["right"],1),
                              ((positions["left"]+positions["neutral"])/2,.25),
                              ((positions["neutral"]+positions["right"])/2,.75)):
                values=self.feed(head_x=pose,head=.65)["faces"][0]["signals"]
                self.assertAlmostEqual(values["head_x"]["value"],want)
                self.assertAlmostEqual(values["head_y"]["value"],.75)
                self.assertTrue(values["head_x"]["valid"])
        # Retrying pitch does not discard a completed yaw fit.
        yaw=self.core.head_x
        self.assertTrue(self.guide("head").passed)
        self.assertEqual(self.core.head_x,yaw)

    def test_yaw_unknown_invalid_and_loss_preserve_fit_and_do_not_change_mouse_mapping(self):
        self.assertFalse(self.feed()["faces"][0]["signals"]["head_x"]["valid"])
        self.assertTrue(self.guide("head").passed)
        self.assertTrue(self.guide("head_x").passed)
        saved=self.core.head_x
        for controls in (dict(no_pose=True),):
            values=self.feed(**controls)["faces"][0]["signals"]
            self.assertFalse(values["head_x"]["valid"])
            self.assertIsNone(values["head_x"]["value"])
        self.feed(blank=True)
        self.assertEqual(self.core.head_x,saved)
        values=self.feed(head_x=.8)["faces"][0]["signals"]
        self.assertEqual(values["head_x"]["value"],1)
        self.assertEqual(values["head_y"]["value"],.5)
        self.assertEqual(self.session.lab.processor.sample.scroll,.5)
        self.assertIsNone(self.session.lab.processor.sample.pointer)

    def test_shared_raw_views_csv_and_normalized_samples(self):
        self.assertTrue(self.guide("head_x").passed)
        frame=self.feed(head_x=.65)
        setup=self.session.state(include_detector=True)["detector"]
        calibration=self.session.detector_state()
        self.assertEqual(setup["trace"],calibration["trace"])
        row=calibration["trace"][-1]
        self.assertEqual(row["sequence"],frame["sequence"])
        self.assertEqual(row["timestamp_ms"],frame["timestamp_ms"])
        self.assertAlmostEqual(row["head_x_raw"],6)
        self.assertAlmostEqual(row["head_x"],.75)
        self.assertEqual(row["head_x_raw_units"],"degrees")
        with tempfile.TemporaryDirectory() as folder:
            import csv
            path=folder+"/head.csv";self.runtime.export_trace(path)
            with open(path) as handle: last=list(csv.DictReader(handle))[-1]
            self.assertAlmostEqual(float(last["head_x_raw"]),6)
        self.feed(no_pose=True)
        self.assertIsNone(self.core.trace[-1]["head_x_raw"])
        self.assertFalse(self.core.trace[-1]["head_x_valid"])

    def test_endpoint_saturation_in_both_sign_conventions_does_not_hide_raw_loss(self):
        for poses in (dict(left=.2, neutral=.5, right=.8), dict(left=.8, neutral=.5, right=.2)):
            self.assertTrue(self.guide("head_x", positions=poses).passed)
            for raw, want in ((0, int(poses["left"] > .5)), (1, int(poses["right"] > .5))):
                values = self.feed(head_x=raw)["faces"][0]["signals"]
                self.assertEqual(values["head_x"]["value"], want)
                self.assertTrue(values["head_x"]["valid"])
                self.assertTrue(self.core.trace[-1]["head_x_saturated"])
                self.assertIn("tracking remains valid", self.core.reasons["head_x"])
            values = self.feed(head_x=1, no_pose=True)["faces"][0]["signals"]
            self.assertFalse(values["head_x"]["valid"])
            self.assertFalse(self.core.trace[-1]["head_x_saturated"])

    def test_retry_failed_head_pose_keeps_successful_groups_and_completed_fit(self):
        self.assertTrue(self.guide("head_x").passed)
        saved = self.core.head_x
        self.session.detector_command("start_movement_guide", "head_x")
        guide = self.core.movement_guide
        for _ in range(80):
            if not guide.active: break
            state = guide.state(self.now)
            if state["waiting"]:
                self.session.detector_command("present_movement_step", state["index"], state["phase"], self.core.generation)
            self.feed(no_pose=state["name"] == "left", **self.runtime.demo_input())
        self.assertFalse(guide.active)
        self.assertFalse(guide.passed)
        self.assertEqual(self.core.head_x, saved)
        neutral = deepcopy(guide.groups["neutral"])
        self.session.detector_command("retry_tongue_step")
        for _ in range(100):
            if not guide.active: break
            state = guide.state(self.now)
            if state["waiting"]:
                self.session.detector_command("present_movement_step", state["index"], state["phase"], self.core.generation)
            self.feed(**self.runtime.demo_input())
        self.assertTrue(guide.passed, guide.report)
        self.assertEqual(guide.groups["neutral"], neutral)

    def test_cancel_failure_and_loss_preserve_fit_but_explicit_reset_clears_horizontal(self):
        self.assertTrue(self.guide("head").passed); pitch=self.core.head
        self.assertTrue(self.guide("head_x").passed); saved=self.core.head_x
        self.session.detector_command("start_movement_guide","head_x")
        self.session.detector_command("cancel")
        self.assertEqual(self.core.head_x,saved);self.assertEqual(self.core.head,pitch)
        result=self.guide("head_x",positions=dict(left=.5,neutral=.5,right=.5))
        self.assertFalse(result.passed);self.assertEqual(self.core.head_x,saved)
        self.assertEqual(self.core.head,pitch)
        self.assertTrue(self.guide("head_x").passed)
        self.session.detector_command("start_movement_guide","head_x")
        self.session.detector_command("reset_head_x")
        self.assertIsNone(self.core.movement_guide)
        self.assertIsNone(self.core.head_x);self.assertEqual(self.core.head,pitch)
        self.assertFalse(self.core.frame["faces"][0]["signals"]["head_x"]["valid"])

    def test_saved_yaw_only_profile_can_load_stopped_and_rejects_bad_fit_atomically(self):
        self.assertTrue(self.guide("head_x").passed); saved=self.core.head_x
        data=self.core.export_calibration()
        self.assertEqual(data["version"],10); self.assertIsNone(data["head"])
        with tempfile.TemporaryDirectory() as folder:
            path=folder+"/profile.json";self.session.save_profile(path)
            self.session.stop();self.core.reset_calibration()
            self.session.load_profile(path)
        self.assertEqual(self.core.head_x,saved);self.assertIsNone(self.core.selected)
        self.assertFalse(self.session.lab.processor.armed)
        self.assertAlmostEqual(self.feed(head_x=.65)["faces"][0]["signals"]["head_x"]["value"],.75)
        original=self.core.export_calibration()
        variants=[dict(data["head_x"],low=float("nan")),dict(data["head_x"],high=100),
                  dict(data["head_x"],center=-11),dict(data["head_x"],endpoint_tolerance=.01),
                  dict(data["head_x"],extra=1)]
        for fit in variants:
            bad=deepcopy(data);bad["head_x"]=fit
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),original)
        bad=deepcopy(data);bad["settings"]["head_mode"]="position"
        with self.assertRaises(ValueError):self.core.load_calibration(bad)

    def test_v1_through_v6_preserve_vertical_and_require_new_horizontal_calibration(self):
        self.assertTrue(self.guide("head").passed); pitch=self.core.head
        self.assertTrue(self.guide("head_x").passed); original=self.core.export_calibration()
        algorithms=("lid-gap-head-y-lab-color-v1","guided-lid-gap-head-y-lab-color-v2",
                    "frame-wink-eye-head-tongue-v3","personal-head-tongue-ranges-v4",
                    "color-tongue-tip-v5","tongue-segmentation-pupil-joystick-v6")
        for version,algorithm in enumerate(algorithms,1):
            old=deepcopy(original);old.update(version=version,algorithm=algorithm)
            old["pupil"] = None
            old.pop("head_x");old["settings"].pop("head_yaw_separation")
            for key,min_version in (("pupil",6),("tongue_measurement",5),("tongue_range",4),("winks",3)):
                if version<min_version:old.pop(key)
            self.core.load_calibration(original)
            self.core.load_calibration(old)
            self.assertEqual(self.core.head,pitch)
            self.assertIsNone(self.core.head_x)
            self.assertEqual(self.core.config.head_yaw_separation,3)
            values=self.feed()["faces"][0]["signals"]
            self.assertTrue(values["head_y"]["valid"]);self.assertFalse(values["head_x"]["valid"])

    @unittest.skipUnless(os.environ.get("RUN_TK_TESTS")=="1","Explicit native Tk test")
    def test_native_head_x_tab_guide_bar_and_tab_cancel(self):
        import tkinter as tk
        from Vision.lab import DetectionLab
        root=tk.Tk();root.geometry("1230x910")
        self.addCleanup(root.destroy)
        callback_errors=[]
        root.report_callback_exception=lambda *error:callback_errors.append(error)
        self.assertTrue(self.guide("head").passed);pitch=self.core.head
        with patch("Vision.movement_view.CalibrationSounds"),patch("Vision.eye_view.CalibrationSounds"):
            ui=DetectionLab(root,SimpleNamespace(demo=False,camera=False),runtime=self.runtime)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.head_x_tab);root.update()
            self.assertEqual(ui.head_x_panel.start["text"],"Start head yaw guide")
            ui.head_x_panel.start.invoke();ui.tick();root.update()
            for _ in range(130):
                if not self.core.movement_guide.active:break
                self.feed(**self.runtime.demo_input());ui.tick();root.update()
            self.assertTrue(self.core.movement_guide.passed,self.core.notice)
            for position,want in ((.2,0),(.5,.5),(.8,1)):
                self.feed(head_x=position);ui.tick();root.update()
                dot=next(item for item in ui.eye_scope.find_all()
                         if ui.eye_scope.type(item)=="oval" and ui.eye_scope.itemcget(item,"fill")=="#75e3a8")
                xy=ui.eye_scope.coords(dot);w=max(360,ui.eye_scope.winfo_width())
                self.assertAlmostEqual((xy[0]+xy[2])/2,30+w/2+want*(w/2-60))
            self.assertIn("Left -12.0° = 0",ui.head_x_details.get())
            self.assertIn("Right 12.0° = 1",ui.head_x_details.get())
            ui.movement_scope_mode.set("Normalized positions");ui.tick();root.update()
            labels=[ui.scope.itemcget(i,"text") for i in ui.scope.find_all() if ui.scope.type(i)=="text"]
            self.assertIn("Head X",labels)
            ui.head_x_panel.start.invoke();ui.tick();root.update()
            ui.calibration_tabs.select(ui.head_tab);ui.tick();root.update()
            self.assertIsNone(self.core.movement_guide)
            self.assertEqual(self.core.head,pitch)
            self.assertEqual(callback_errors,[])
