"""Vision fixtures → Processing → actual C driver in dry-run mode."""

import os
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from App.mouse_runtime import MouseSession
from Drivers.output import default_library
from Processing.mappings.config import GAMING_ID
from Processing.mappings.demo import gaming_demo_frame
from Vision.mouse_demo import mouse_demo_records

LIBRARY = Path(os.environ.get("FID_LIBRARY", default_library()))


@unittest.skipUnless(LIBRARY.is_file(), "Build Drivers or set FID_LIBRARY")
class DriverConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.session = MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.lab = self.session.lab
        self.lab.select_mapping(GAMING_ID)
        self.session.configure_output("dry-run",LIBRARY)
        self.lab.action({"action":"arm"})
        self.sequence = 0
        self.deliver()

    def deliver(self, **values):
        self.now += 20
        self.sequence += 1
        base = next(mouse_demo_records(count=1))
        base.update(sequence=self.sequence,timestamp_ms=self.now)
        frame = gaming_demo_frame(base,30)
        for key,value in values.items():
            frame["faces"][0]["signals"][key].update(value=value,valid=value is not None,
                                                    confidence=1 if value is not None else 0)
        if "left_eye_open" in values:
            closed = values["left_eye_open"] == 0
            frame["eye_intent"]["left"].update(value=int(closed),state="wink" if closed else "open")
        self.session.deliver(frame)
        return self.lab.state()["output"]

    def test_real_driver_receives_eye_pulse_between_processing_ticks(self):
        self.deliver(left_eye_open=0)
        output = self.deliver(left_eye_open=1)
        self.assertEqual(output["event_counts"].get(3),1)
        self.assertTrue(output["enabled"])
        self.session.stop()
        self.assertFalse(self.lab.state()["output"]["enabled"])

    def test_head_mouse_reaches_driver_without_any_eye_key_or_scroll_event(self):
        self.lab.select_mapping("mouse-test")
        self.lab.action({"action":"arm"})
        output = self.deliver(gaze_x=1,gaze_y=0,left_eye_open=0)
        self.assertTrue(output["enabled"])
        self.assertIsNone(output["error"])
        for _ in range(20):
            output = self.deliver(head_x=.8,head_y=.2,gaze_x=0,gaze_y=1,left_eye_open=0)
        snap = self.lab.state()["snapshot"]
        self.assertGreater(snap["pointer_x"],.5)
        self.assertLess(snap["pointer_y"],.5)
        self.assertGreater(output["event_counts"].get(1,0),0)
        self.assertEqual(output["held_keys"],0)
        self.assertTrue(all(e["type"] == 1 for e in self.lab.output.events))
        self.lab.select_mapping(GAMING_ID)
        self.assertFalse(self.lab.state()["output"]["enabled"])

    def test_switch_to_head_mouse_releases_gaming_keys_and_ignores_unavailable_pupils(self):
        for _ in range(12):self.deliver(head_y=.8)
        self.assertNotEqual(self.lab.state()["output"]["held_keys"],0)
        self.lab.select_mapping("mouse-test")
        self.assertEqual(self.lab.state()["output"]["held_keys"],0)
        self.lab.action({"action":"arm"})
        self.assertTrue(self.deliver(gaze_x=None,gaze_y=None)["enabled"])
        for _ in range(12):self.deliver(head_x=.8)
        output=self.deliver(head_x=None)
        self.assertIsNone(output["error"])
        snap=self.lab.state()["snapshot"]
        self.assertEqual((snap["pointer_x"],snap["pointer_y"]),(.5,.5))

    def test_small_downward_head_input_produces_compiled_movement_without_other_actions(self):
        self.lab.select_mapping('mouse-test')
        self.lab.action({'action':'arm'});self.deliver(gaze_x=None,gaze_y=None)
        start=len(self.lab.output.events)
        for _ in range(25):
            time.sleep(.01);self.deliver(head_y=.53,gaze_x=None,gaze_y=None)
        output=self.lab.output.snapshot()
        self.assertIsNone(output['error'])
        # Dry-run integrates target positions only; velocity is verified through
        # the same movement events that the native backend sends to the OS.
        events=list(self.lab.output.events)[start:]
        self.assertGreater(sum(event['y'] for event in events),0)
        self.assertTrue(all(event['type']==1 and event['x']==0 and event['y']>0 for event in events))
        self.deliver(head_y=None)
        self.assertEqual(self.lab.state()['message']['pointer'],dict(mode='velocity',x=.5,y=.5))

    def test_centering_after_start_discards_pre_enable_interpolation(self):
        settings=self.lab.state()['mapping'];settings['pointer_mode']='velocity'
        self.lab.update_mapping(settings)
        for mapping in (GAMING_ID, "mouse"):
            with self.subTest(mapping=mapping):
                self.lab.select_mapping(mapping)
                self.lab.action({"action":"arm"})
                for _ in range(3):
                    self.assertFalse(self.deliver(gaze_x=.8)["enabled"])
                output = self.deliver(gaze_x=.5)
                self.assertIsNone(output["error"])
                self.assertTrue(output["enabled"])
                snap = self.lab.state()["snapshot"]
                self.assertEqual((snap["pointer_x"], snap["pointer_y"]), (.5,.5))
                for _ in range(6):
                    self.deliver(gaze_x=.8)
                self.assertGreater(self.lab.state()["snapshot"]["pointer_x"], .5)
                self.assertIsNone(self.lab.state()["output"]["error"])

    def test_wink_during_startup_waits_for_release_before_first_command(self):
        settings=self.lab.state()['mapping'];settings['pointer_mode']='velocity'
        self.lab.update_mapping(settings)
        self.lab.action({"action":"arm"})
        self.deliver(gaze_x=.8)  # Actual reopening readies the eye.
        self.deliver(gaze_x=.8,left_eye_open=0)
        output = self.deliver(gaze_x=.5,left_eye_open=0)
        self.assertFalse(output["enabled"])
        self.assertIsNone(output["error"])
        output = self.deliver()
        self.assertTrue(output["enabled"])
        self.assertIsNone(output["error"])
        self.assertEqual(output["event_counts"].get(3,0),0)
        self.assertEqual(self.deliver(left_eye_open=0)["event_counts"].get(3),1)

    def test_target_start_requires_release_but_not_centered_pupils(self):
        self.lab.action({'action':'arm'})
        self.assertFalse(self.deliver(gaze_x=.8,left_eye_open=0)['enabled'])
        self.assertFalse(self.deliver(gaze_x=.8,left_eye_open=0)['enabled'])
        output=self.deliver(gaze_x=.8,left_eye_open=1)
        self.assertTrue(output['enabled'])
        self.assertEqual(output['event_counts'].get(3,0),0)
        self.assertEqual(self.lab.state()['message']['pointer']['x'],1)
        self.assertEqual(self.deliver(gaze_x=.8,left_eye_open=0)['event_counts'].get(3),1)

    def test_key_combo_loss_mapping_change_and_profile_settings_release(self):
        for change in ("source_stop","settings","mapping"):
            self.lab.select_mapping(GAMING_ID)
            self.lab.action({"action":"arm"});self.deliver()
            for _ in range(12):output=self.deliver(head_x=.2,head_y=.8)
            self.assertEqual(output["held_keys"],33)
            if change=="source_stop":self.session.stop()
            elif change=="settings":self.lab.settings({"config":self.lab.processor.config.to_dict()})
            else:self.lab.select_mapping("mouse")
            self.assertFalse(self.lab.state()["output"]["enabled"])
            self.assertEqual(self.lab.output.status().held_key_mask,0)

    def test_invalid_source_disarms_and_future_captures_cannot_resume(self):
        self.deliver(left_eye_open=0)
        with self.assertRaises(ValueError):self.session.deliver({"schema_version":0})
        self.assertFalse(self.lab.state()["output"]["enabled"])
        self.deliver();self.deliver(left_eye_open=0)
        self.assertFalse(self.lab.state()["output"]["enabled"])
        self.assertEqual(self.lab.state()["output"]["event_counts"][3],1)

    def test_driver_failure_disarms_processing_clock_and_requires_rearm(self):
        driver = self.lab.output
        with patch.object(driver,"submit",side_effect=ValueError("test backend failure")):
            self.lab.step(self.now)
        self.assertFalse(self.lab.processor.armed)
        self.assertIn("test backend failure",self.lab.state()["output"]["error"])
        self.deliver()
        self.assertFalse(driver.status().enabled)
        self.lab.action({"action":"arm"});self.deliver()
        self.assertTrue(driver.status().enabled)

    def test_native_rejects_synthetic_source_before_library_or_os_use(self):
        with patch("Drivers.output.DriverOutput") as create:
            with self.assertRaisesRegex(ValueError,"Camera"):
                self.session.configure_output("native",LIBRARY)
            create.assert_not_called()

    def test_close_releases_and_destroys_output(self):
        for _ in range(12):self.deliver(head_y=.8)
        driver = self.lab.output
        self.assertEqual(driver.status().held_key_mask,1)
        self.session.close()
        self.assertFalse(driver.handle)
        self.assertTrue(any(e["type"]==8 and e["x"]==1 for e in driver.events))
        with self.assertRaisesRegex(ValueError,"closed"):
            self.session.configure_output("dry-run",LIBRARY)

    def test_switch_away_from_camera_disconnects_native_mode(self):
        # Model a native-mode session with an already-created dry-run handle;
        # no native backend or camera is opened by this lifecycle check.
        driver = self.lab.output
        driver.mode = "native"
        self.session.mode = "camera"
        self.lab.step(self.now)
        self.assertEqual(self.lab.state()["output"]["mode"],"native")
        self.session.start("demo",count=1)
        self.assertIsNone(self.lab.output)
        self.assertFalse(driver.handle)
        self.assertEqual(self.lab.state()["output"]["mode"],"preview")

    @unittest.skipUnless(os.environ.get("RUN_TK_TESTS")=="1","native Tk check")
    def test_native_ui_exposes_output_selection_and_actual_driver_mode(self):
        import tkinter as tk
        from App.desktop import IntegratedDesktop
        root = tk.Tk()
        options = SimpleNamespace(source="demo",fps=30,camera_id=0,model="unused",replay=None,
                                  no_preview=True,subject=None,driver_library=LIBRARY,output="dry-run")
        with patch.object(IntegratedDesktop,"start_source"):
            ui = IntegratedDesktop(root,self.session,options)
        try:
            self.assertEqual(ui.output_var.get(),"Driver dry run")
            ui.output_var.set("Driver dry run");ui.connect_output()
            ui.refresh();ui.refresh_vision();root.update()
            self.assertEqual(self.lab.state()["output"]["mode"],"dry-run")
            self.assertEqual(ui.start_button.cget("text"),"Start dry run")
            self.assertIn("DRIVER DRY RUN",ui.mapping_page.notice.get())
            ui.output_var.set("Preview");ui.connect_output();ui.refresh();root.update()
            self.assertEqual(ui.start_button.cget("text"),"Start preview")
            self.assertIsNone(self.lab.output)
        finally:
            ui.closed=True
            for timer in root.tk.splitlist(root.tk.call("after","info")):root.after_cancel(timer)
            root.destroy()
