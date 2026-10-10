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
            self.guide = self.Guide(SimpleNamespace(settle_ms=0, collect_ms=400, min_samples=8, eye_separation=.015))
        elif command == "present_eye_step":
            self.guide.present(args[0], self.now)
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
            targets.append(self.guide.step[2])
            ratio = .04 if self.guide.step[0] == "closed" else .2
            self.now = self.guide.start_ms
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
