"""Current calibrated detector and synthetic source → gaming Processing preview."""

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from App.mouse_runtime import MouseSession
from Processing.mappings.config import GAMING_ID
from Processing.mappings.demo import gaming_demo_frame
from Vision.mouse_demo import mouse_demo_records

PIXELS = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))


class GamingHarness(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.session = MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.lab = self.session.lab
        self.lab.select_mapping(GAMING_ID)


class GamingPipeline(GamingHarness):
    def test_synthetic_full_mapping_and_source_stop(self):
        self.lab.action({"action":"arm"})
        observed = set()
        for original in mouse_demo_records(count=490):
            self.now = 1000+original["timestamp_ms"]
            original["timestamp_ms"] = self.now
            result = self.session.deliver(gaming_demo_frame(original,30))
            self.assertTrue(result["accepted"])
            self.lab.step(self.now)
            command = self.lab.state()["message"]
            observed.update(k for k,v in command["keys"].items() if v)
            observed.update(k for k,v in command["buttons"].items() if v)
            if command["pointer"]["x"] != .5 or command["pointer"]["y"] != .5:observed.add("pointer")
            self.assertEqual(command["source"]["timestamp_ms"],self.now)
            self.assertEqual(command["scroll_y"],.5)
        self.assertEqual(observed,{"w","s","space","left_shift","left_click","right_click","pointer"})
        self.session.stop()
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.assertFalse(any(self.lab.state()["message"]["keys"].values()))

    def test_malformed_frame_stops_keyboard_and_preserves_selected_mapping(self):
        self.lab.action({"action":"arm"})
        base = next(mouse_demo_records(count=1))
        for index in range(15):
            self.now += 20
            raw = deepcopy(base);raw.update(sequence=index,timestamp_ms=self.now)
            frame = gaming_demo_frame(raw,30)
            frame["faces"][0]["signals"]["head_y"]["value"] = .5 if index==0 else .8
            self.session.deliver(frame)
        self.assertEqual(self.lab.state()["message"]["keys"]["w"],1)
        with self.assertRaises(ValueError):self.session.deliver({"schema_version":0})
        self.assertEqual(self.lab.mapping_id,GAMING_ID)
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.assertEqual(self.lab.state()["message"]["keys"]["w"],0)


@unittest.skipUnless(PIXELS,"Vision image dependencies required")
class CalibratedGamingPipeline(GamingHarness):
    def setUp(self):
        super().setUp()
        from Vision.calibration import AxisCalibration
        from tests.vision.pupil_fixture import pupil_fixture
        self.session.mode = "detector-demo"
        self.core = self.session.ensure_detector_runtime().workbench
        self.core.head = AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x = AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.pupil_model = pupil_fixture()
        self.capture_sequence = 0

    def capture(self, blank=False, **controls):
        from Vision.capture import CapturedImage
        from Vision.demo_detection import demo_image
        from Vision.signals import Envelope
        self.now += 25
        self.capture_sequence += 1
        pixels, faces = demo_image(**controls)
        return self.session.deliver_detection(CapturedImage(Envelope("gaming-pixels",self.capture_sequence,self.now),pixels),
                                              [] if blank else faces, preview=False)

    def test_current_pupil_fit_and_head_axes_reach_processing_without_quantizing(self):
        self.capture()
        self.lab.action({"action":"arm"})
        self.capture()
        for _ in range(16):frame = self.capture(head=.65,head_x=.35,pupil_x=.723,pupil_y=.5)
        values = frame["faces"][0]["signals"]
        self.assertEqual(frame["gaze_measurement"],"head_compensated_iris_direction_v1")
        self.assertAlmostEqual(self.lab.processor.sample.pointer[0],values["gaze_x"]["value"])
        self.assertNotEqual(self.lab.processor.sample.pointer[0],frame["pupil_matrix"]["column"]/10)
        command = self.lab.state()["message"]
        self.assertEqual(command["keys"]["w"],1)
        self.assertEqual(command["keys"]["left_shift"],1)
        self.assertGreater(command["pointer"]["x"],.5)
        self.assertEqual(command["source"]["timestamp_ms"],frame["timestamp_ms"])
        saved = deepcopy(self.core.export_calibration())
        self.capture(blank=True)
        self.assertFalse(self.lab.state()["message"]["enabled"])
        self.assertEqual(self.core.export_calibration(),saved)
        self.capture()
        self.assertFalse(self.lab.state()["message"]["enabled"])

    def test_face_profile_load_keeps_mapping_and_detector_v12_but_disarms(self):
        self.capture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"face.json"
            self.session.save_profile(path)
            self.lab.action({"action":"arm"}); self.capture()
            self.session.load_profile(path)
            self.assertEqual(self.lab.mapping_id,GAMING_ID)
            self.assertFalse(self.lab.processor.armed)
            self.assertEqual(self.core.export_calibration()["version"],12)
            self.assertIsNotNone(self.core.pupil_model)

    @unittest.skipUnless(os.environ.get("RUN_TK_TESTS")=="1","native Tk check")
    def test_native_mapping_rows_settings_and_stop_on_switch(self):
        import tkinter as tk
        from App.desktop import IntegratedDesktop
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *error:errors.append(error)
        options = SimpleNamespace(source="detector-demo",fps=30,camera_id=0,model="unused",replay=None,no_preview=True)
        with patch.object(IntegratedDesktop,"start_source"):
            ui = IntegratedDesktop(root,self.session,options)
        try:
            self.capture()
            self.lab.action({"action":"arm"});self.capture()
            ui.notebook.select(ui.mapping_page)
            ui.refresh();root.update()
            panel = ui.mapping_page
            self.assertEqual(len(panel.table.get_children()),8)
            self.assertIn("Head down",panel.table.item("down","values"))
            self.assertFalse(panel.mock.winfo_manager())
            panel.fields[("head_x","activation")].set("0.4")
            panel.apply()
            self.assertEqual(self.lab.processor.mapping.head_x.activation,.4)
            self.assertFalse(self.lab.processor.armed)
            ui.refresh();root.update()
            self.lab.select_mapping("mouse");ui.refresh();root.update()
            self.assertEqual(panel.table.get_children(),())
            self.assertEqual(errors,[])
        finally:
            ui.closed = True
            if ui.calibration_ui:ui.calibration_ui.close_panels()
            for timer in root.tk.splitlist(root.tk.call("after","info")):root.after_cancel(timer)
            root.destroy()
