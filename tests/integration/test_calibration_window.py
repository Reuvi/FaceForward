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
        # Synthetic key events need an active native window on macOS. The lab
        # may be in the background when the suite was launched from a terminal.
        old.focus_force()
        self.root.update()
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
    def close_ui(self, ui):
        if ui.closed:
            return
        # Each test owns a separate Tk interpreter. Dispose scheduled redraws
        # before destroying it so they cannot fire while the next test runs.
        for callback in ui.root.tk.call("after", "info"):
            ui.root.after_cancel(callback)
        ui.close()

    def test_separate_wink_button_and_visible_rest_countdown_keep_eye_geometry(self):
        import tkinter as tk
        from App.desktop import IntegratedDesktop
        from App.mouse_runtime import MouseSession
        from Vision.calibration import EyeCalibration
        from Vision.capture import CapturedImage
        from Vision.demo_detection import demo_image
        from Vision.signals import Envelope
        now = [1000.]
        session = MouseSession(clock=lambda: now[0]); session.mode = "detector-demo"
        root = tk.Tk()
        options = SimpleNamespace(source="detector-demo", replay=None, model=None,
                                  fps=30, camera_id=0, no_preview=True, subject=None)
        with patch.object(session, "start"), patch("Vision.eye_view.CalibrationSounds"):
            ui = IntegratedDesktop(root, session, options)
            self.addCleanup(self.close_ui, ui)
            root.geometry("1420x850")
            session.detector_command("configure", dict(settle_ms=0, collect_ms=300,
                                                         eye_rest_ms=3000, min_samples=5))
            core = session.detector_runtime.workbench
            sequence = 0
            def feed():
                nonlocal sequence
                sequence += 1; now[0] += 25
                image, observations = demo_image(**session.detector_runtime.demo_input())
                session.deliver_detection(CapturedImage(Envelope("split-eye",sequence,now[0]),image), observations, preview=False)
                view.tick(); root.update()
            ui.notebook.select(ui.calibration_page); ui.open_calibration(); root.update()
            view = ui.calibration_ui
            feed()
            panel = view.eye_panel
            self.assertEqual(str(panel.wink_start["state"]), "disabled")
            # A completed or loaded geometry fit makes the second stage available.
            core.eyes = {side: EyeCalibration(.04,.25,.5) for side in ("left", "right")}
            eyes = dict(core.eyes)
            feed()
            self.assertEqual(str(panel.wink_start["state"]), "normal")
            self.assertTrue(panel.wink_start.winfo_ismapped())
            panel.wink_start.invoke(); view.tick(); root.update()
            while True:
                feed()
                state = core.eye_guide.state(now[0])
                if state["resting"] and not state["waiting"]: break
                self.assertLess(sequence, 200)
            self.assertEqual(state["kind"], "winks")
            self.assertEqual(state["total"], 14)
            popup = panel.fullscreen.canvas
            def label(tag):
                return popup.itemcget(popup.find_withtag(tag)[0], "text")
            self.assertIn("3s", label("rest-countdown"))
            self.assertIn("smile, talk", label("rest-instruction"))
            for _ in range(44): feed()
            self.assertIn("2s", label("rest-countdown"))
            self.assertEqual(core.eye_guide.state(now[0])["samples"], {"left":0,"right":0})
            countdown = popup.bbox("rest-countdown")
            instruction = popup.bbox("rest-instruction")
            self.assertLess(countdown[3], instruction[1])
            self.assertGreaterEqual(instruction[0], 0)
            self.assertLessEqual(instruction[2], popup.winfo_width())
            panel.cancel(); view.tick(); root.update()
            self.assertIsNone(panel.fullscreen)
            self.assertEqual(core.eyes, eyes)
            self.assertEqual(str(panel.wink_start["state"]), "normal")
            self.assertIn("retained", panel.instruction.get())
            self.assertFalse(session.lab.processor.armed)

    def test_head_guide_shared_raw_graphs_and_cancel_on_tab_change(self):
        import tkinter as tk
        from App.desktop import IntegratedDesktop
        from App.mouse_runtime import MouseSession
        from Vision.capture import CapturedImage
        from Vision.demo_detection import demo_image
        from Vision.signals import Envelope
        now=[1000.]
        session=MouseSession(clock=lambda:now[0]);session.mode="detector-demo"
        root=tk.Tk()
        options=SimpleNamespace(source="detector-demo",replay=None,model=None,fps=30,camera_id=0,no_preview=True,subject=None)
        with patch.object(session,"start"),patch("Vision.movement_view.CalibrationSounds"):
            ui=IntegratedDesktop(root,session,options)
            self.addCleanup(self.close_ui, ui)
            root.geometry("1420x850")
            session.detector_command("configure",dict(settle_ms=0,collect_ms=300,movement_rest_ms=0,min_samples=5))
            sequence=0
            def feed(**controls):
                nonlocal sequence
                sequence+=1;now[0]+=25
                image,observations=demo_image(**dict(session.detector_runtime.demo_input(), **controls))
                session.deliver_detection(CapturedImage(Envelope("tk-movement",sequence,now[0]),image),observations,preview=False)
            feed();ui.refresh_vision();root.update()
            self.assertGreaterEqual(ui.raw_canvas.winfo_height(),160)
            self.assertIn("Raw capture #1",ui.raw_capture.get())
            ui.notebook.select(ui.calibration_page);ui.open_calibration();root.update()
            view=ui.calibration_ui;view.calibration_tabs.select(view.head_tab);root.update()
            self.assertFalse(any(child.winfo_class() == "TCombobox" for child in view.head_tab.winfo_children()))
            self.assertNotIn('"head_mode"', view.settings.get("1.0", "end"))
            self.assertNotIn('"head_position_separation"', view.settings.get("1.0", "end"))
            self.assertEqual(view.head_panel.start["text"], "Start head pitch guide")
            view.head_panel.start.invoke()
            view.tick();root.update()
            core=session.detector_runtime.workbench
            while core.movement_guide.active:
                feed();view.tick();root.update()
                self.assertLess(sequence,300)
            self.assertTrue(core.movement_guide.passed,core.notice)
            self.assertIsNotNone(core.head)
            self.assertEqual(core.config.head_mode, "pitch")
            for position, expected in ((.2, 0), (.5, .5), (.8, 1)):
                feed(head=position);view.tick();root.update()
                text = {view.eye_scope.itemcget(item, "text") for item in view.eye_scope.find_all()
                        if view.eye_scope.type(item) == "text"}
                self.assertTrue({"-12°", "0°", "12°"}.issubset(text))
                for color in ("#b18bff", "#75e3a8"):
                    dot = next(item for item in view.eye_scope.find_all()
                               if view.eye_scope.type(item) == "oval" and view.eye_scope.itemcget(item, "fill") == color)
                    coordinates = view.eye_scope.coords(dot)
                    self.assertAlmostEqual((coordinates[1]+coordinates[3])/2,
                                           50 + expected * (max(160, view.eye_scope.winfo_height())-82))
            self.assertIn("Up -12.0° = 0", view.head_details.get())
            for mode in view.movement_scope_picker["values"]:
                view.movement_scope_mode.set(mode);view.tick();root.update()
                self.assertTrue(view.scope.find_all())
            view.head_panel.start.invoke();view.tick();root.update()
            ui.notebook.select(ui.vision_page);view.tick();root.update()
            self.assertIsNone(core.movement_guide)
            self.assertFalse(session.lab.processor.armed)
            ui.refresh_vision()
            self.assertIn(f"Raw capture #{sequence}",ui.raw_capture.get())
            self.assertEqual(session.state(include_detector=True)["detector"]["trace"],session.detector_state()["trace"])

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
        self.addCleanup(self.close_ui, ui)
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
