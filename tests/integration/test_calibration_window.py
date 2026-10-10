"""Opt-in native Tk checks: RUN_TK_TESTS=1, with a desktop/display available."""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("RUN_TK_TESTS") == "1", "Explicit desktop Tk test required")
class FullscreenCalibrationTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        from Vision.eye_view import EyeGuidePanel
        from Vision.guided_eyes import GuidedEyes
        self.Guide = GuidedEyes
        self.root = tk.Tk()
        self.root.geometry("600x580+30+30")
        self.addCleanup(self.root.destroy)
        parent = ttk.Frame(self.root);parent.pack(fill="both", expand=True)
        self.sounds = patch("Vision.eye_view.CalibrationSounds").start()
        self.addCleanup(patch.stopall)
        self.now = 1000
        self.generation = 0
        self.guide = None
        self.panel = EyeGuidePanel(parent, self.root, self.call)
        self.addCleanup(self.panel.close)
        self.root.update()
        self.geometry = self.root.geometry()

    def call(self, command, *args):
        if command == "start_eye_guide":
            self.generation += 1
            self.guide = self.Guide(SimpleNamespace(settle_ms=0, collect_ms=400,
                eye_rest_ms=float(args[0])*1000 if args else 3000, min_samples=8, eye_separation=.015))
        elif command == "present_eye_step":
            self.guide.present(args[0], self.now, args[1] if len(args)>1 else None)
        elif command == "cancel":
            self.guide = None

    def refresh(self):
        self.panel.update({"eye_guide": self.guide.state(self.now) if self.guide else None,
                           "eyes": {}, "generation": self.generation})
        self.root.update()

    def start(self):
        self.panel.start.invoke()
        self.refresh()
        self.refresh()  # first mapping must paint before sampling starts
        self.assertTrue(self.panel.fullscreen.ready)
        self.assertIsNotNone(self.guide.start_ms)

    def test_fullscreen_sequence_returns_to_unchanged_lab_with_independent_fits(self):
        self.start()
        window = self.panel.fullscreen.window
        self.assertEqual(window.winfo_width(), self.root.winfo_screenwidth())
        self.assertEqual(window.winfo_height(), self.root.winfo_screenheight())
        targets = []
        while self.guide.active:
            if self.guide.resting:
                self.assertIn('Rest',self.panel.title.get())
                self.assertIn('no samples',self.panel.progress.get())
                self.now=self.guide.rest_end_ms
                self.guide.feed(self.now,{})
                self.refresh()
                continue
            targets.append(self.guide.step[2])
            ratio = .04 if self.guide.step[0] == "closed" else .2
            self.now = self.guide.start_ms
            self.refresh()  # Capture cue fires once on the phase transition.
            self.refresh()
            for _ in range(16):
                self.guide.feed(self.now, {s: SimpleNamespace(value=ratio, quality=1) for s in ("left", "right")})
                self.now += 25
            self.guide.feed(self.now, {})
            self.refresh()
        self.assertIsNone(self.panel.fullscreen)
        self.assertEqual(set(self.guide.fits), {"left", "right"})
        self.assertEqual(len(set(targets)), 6)
        self.assertEqual(self.root.geometry(), self.geometry)
        self.assertIsNone(self.root.grab_current())
        self.sounds.return_value.play.assert_any_call("reopen")
        self.sounds.return_value.play.assert_any_call("success")
        cues=[call.args[0] for call in self.sounds.return_value.play.call_args_list]
        self.assertEqual(cues.count('rest'),5)
        self.assertEqual(cues.count('rest_reopen'),1)
        self.assertEqual(cues.count('capture'),7)
        self.assertEqual(str(self.panel.rest_input['state']),'normal')

    def test_cancel_during_rest_clears_popup_and_restart_timing(self):
        self.panel.rest_seconds.set('2.5')
        self.start()
        self.assertEqual(self.guide.config.eye_rest_ms,2500)
        self.assertEqual(str(self.panel.rest_input['state']),'disabled')
        self.now=self.guide.start_ms+400
        self.guide.feed(self.now,{})
        self.refresh()
        self.assertTrue(self.guide.resting)
        old_event=self.panel.event
        self.panel.fullscreen.cancel_button.invoke()
        self.call('start_eye_guide')
        self.panel.present(old_event)
        self.assertIsNone(self.guide.start_ms)
        self.assertIsNone(self.guide.rest_end_ms)
        self.assertIsNone(self.panel.fullscreen)

    def test_escape_cancels_and_restart_has_no_old_timer(self):
        self.start()
        old = self.panel.fullscreen.window
        old.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(self.guide)
        self.assertIsNone(self.panel.fullscreen)
        self.assertIsNone(self.root.grab_current())
        self.start()
        self.assertEqual(self.guide.index, 0)
        self.assertEqual(self.guide.groups, {"left": [], "right": []})
        self.panel.fullscreen.cancel_button.invoke()
        self.assertIsNone(self.panel.fullscreen)

    def test_source_loss_dismisses_popup_and_pending_acknowledgment(self):
        self.start()
        self.guide = None  # source/selection loss clears the runtime guide
        self.refresh()
        self.assertIsNone(self.panel.fullscreen)
        self.assertIsNone(self.panel.pending_present)
        self.assertIsNone(self.root.grab_current())

    def test_cancel_before_presentation_cannot_start_a_later_guide(self):
        self.panel.start.invoke()
        self.panel.update({"eye_guide": self.guide.state(self.now), "eyes": {}, "generation": self.generation})
        self.panel.cancel()
        self.call("start_eye_guide")
        self.root.update()
        self.assertIsNone(self.guide.start_ms)
        self.assertIsNone(self.panel.pending_present)

    def test_processing_canvas_draws_unknown_hold_in_its_channel_color(self):
        from LabUI.traces import darker
        from Processing.mouse.desktop import Scope, BLUE
        scope=Scope(self.root,"Display test",("raw",))
        scope.pack(fill="both",expand=True)
        self.root.update()
        scope.draw([{"t":0,"raw":.2},{"t":1,"raw":.2},{"t":2,"raw":None},{"t":3,"raw":.8}])
        dark=[item for item in scope.canvas.find_withtag("gap-run")
              if scope.canvas.itemcget(item,"fill")==darker(BLUE)]
        self.assertEqual(len(dark),1)
        points=scope.canvas.coords(dark[0])
        self.assertEqual(len(set(points[1::2])),1)
        scope.draw([])
        self.assertFalse(scope.canvas.find_withtag("gap-run"))


@unittest.skipUnless(os.environ.get("RUN_TK_TESTS") == "1", "Explicit desktop Tk test required")
class SingleUserWindowTests(unittest.TestCase):
    def test_live_selection_hidden_replay_selection_available_and_profile_load_stopped(self):
        import tkinter as tk
        import tempfile
        from pathlib import Path
        from App.desktop import IntegratedDesktop
        from App.mouse_runtime import MouseSession
        from Vision.calibration import EyeCalibration
        root = tk.Tk()
        session = MouseSession()
        session.mode = "detector-demo"
        options = SimpleNamespace(source="detector-demo", replay=None, model=None,
                                  fps=30, camera_id=0, no_preview=True, subject=None)
        self.addCleanup(lambda: None if session.closed else session.close())
        with patch.object(session, "start"):
            ui = IntegratedDesktop(root, session, options)
        self.addCleanup(lambda: None if ui.closed else ui.close())
        root.update()
        self.assertNotIn("Detection research",[ui.notebook.tab(t,"text") for t in ui.notebook.tabs()])
        self.assertNotIn("config.left_eye.dwell_ms",ui.setting_vars)
        self.assertNotIn("config.right_eye.release_ms",ui.setting_vars)
        self.assertEqual(ui.replay_selection.winfo_manager(), "")
        session.mode = "replay"
        ui.refresh_vision(); root.update()
        self.assertEqual(ui.replay_selection.winfo_manager(), "pack")
        session.mode = "detector-demo"
        ui.refresh_vision(); root.update()
        self.assertEqual(ui.replay_selection.winfo_manager(), "")
        core = session.ensure_detector_runtime().workbench
        core.eyes["left"] = EyeCalibration(.04, .25, .5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"eyes.json"
            session.save_profile(path)
            session.detector_command("reset_calibration")
            self.assertFalse(core.eyes)
            with patch("App.desktop.filedialog.askopenfilename", return_value=str(path)):
                ui.load_profile()
            root.update()
            self.assertIn("left", core.eyes)
            self.assertIsNotNone(ui.calibration_ui)
            self.assertFalse(session.lab.processor.armed)
            ui.refresh_vision()
            self.assertIn("saved calibration active", ui.profile_text.get())
            from Vision.capture import CapturedImage
            from Vision.demo_detection import demo_image
            from Vision.signals import Envelope
            image,observations=demo_image()
            for sequence in range(3):
                session.deliver_detection(CapturedImage(Envelope("scope-test",sequence,session.clock()),image),observations,preview=False)
            ui.notebook.select(ui.calibration_page);root.update()
            for mode in ui.calibration_ui.eye_scope_picker["values"]:
                ui.calibration_ui.eye_scope_mode.set(mode)
                ui.calibration_ui.tick();root.update()
                self.assertTrue(ui.calibration_ui.scope.find_all())
