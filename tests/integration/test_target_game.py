"""Native game UI and App entry wiring using practice/injected input, no OS driver."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Processing.mouse.controller import Lab
from Processing.target_game.view import TargetGame


@unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
class TargetGameWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.now=1000.
        self.lab=Lab(clock=lambda:self.now)
        self.folder=tempfile.TemporaryDirectory()
        self.root=tk.Tk();self.root.withdraw();self.errors=[]
        self.root.report_callback_exception=lambda *error:self.errors.append(error)
        self.game=TargetGame(self.root,self.lab,lambda:dict(mode='demo',error=None),
                             root=Path(self.folder.name)/'runs',default_path=Path(self.folder.name)/'default.json')
        self.root.update()
        self.game.window.after_cancel(self.game.timer);self.game.timer=None
        self.addCleanup(self.close)

    def close(self):
        self.game.close();self.lab.close()
        for timer in self.root.tk.splitlist(self.root.tk.call('after','info')):self.root.after_cancel(timer)
        self.root.destroy();self.folder.cleanup();self.assertEqual(self.errors,[])

    def test_practice_button_uses_actual_game_and_does_not_arm(self):
        self.game.practice_button.invoke();self.root.update()
        self.assertEqual(self.game.experiment.mode,'practice')
        geometry=self.game.geometry()
        for i in range(9):
            self.now+=50
            self.game.experiment.poll(self.now,geometry['width']/2,geometry['height']/2,geometry)
        self.game.draw();self.root.update()
        self.assertEqual(self.game.experiment.round.phase,'target')
        self.assertFalse(self.lab.processor.armed)
        self.assertGreater(len(self.game.canvas.find_all()),3)
        labels=[self.game.canvas.itemcget(item,'text') for item in self.game.canvas.find_all()
                if self.game.canvas.type(item)=='text']
        self.assertTrue(any('PRACTICE' in label for label in labels))
        self.assertEqual(self.game.enter(),'break')  # Enter must not stop an active trial.
        self.assertEqual(self.game.experiment.round.phase,'target')
        self.game.stop()
        self.assertTrue(self.game.experiment.closed)
        self.assertIsNone(self.game.experiment.round)
        self.assertEqual(str(self.game.resume_button['state']),'disabled')
        self.assertEqual(str(self.game.start_button['state']),'normal')
        self.assertTrue((self.game.experiment.recorder.path/'partial-round.json').is_file())
        self.assertFalse((Path(self.folder.name)/'default.json').exists())

    def test_live_start_requires_camera_head_mapping_and_native_output(self):
        self.game.start_button.invoke();self.root.update()
        self.assertIn('Camera',self.game.status.get())
        self.assertFalse(self.game.experiment.waiting)
        self.assertFalse(self.lab.processor.armed)

    def test_recenter_recovery_button_is_connected_and_does_not_run_in_practice(self):
        with patch.object(self.game.experiment,'recenter') as recenter:
            self.game.recenter_button.invoke()
            recenter.assert_called_once_with(self.game.geometry())
        self.game.start(practice=True);self.game.draw()
        self.assertEqual(str(self.game.recenter_button['state']),'disabled')

    def test_failed_continue_is_logged_and_saved_data_is_preserved(self):
        import json
        self.game.start(practice=True);geometry=self.game.geometry()
        self.now+=50;self.game.experiment.poll(self.now,0,0,geometry)
        path=self.game.experiment.recorder.path/'cursor.jsonl'
        def fail():raise ValueError('Synthetic blocked continuation')
        self.game.guarded(fail)
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(rows[-1]['event'],'ui_error')
        self.assertIn('blocked continuation',rows[-1]['reason'])
        self.assertFalse(self.lab.processor.armed)

    def test_status_and_saved_footer_do_not_resize_active_course(self):
        initial=self.game.geometry()
        self.game.status.set('A long measured recommendation with evidence. '*30)
        self.game.footer.set('Saved locally · 20261011T000000Z-12345678 · cursor trace and per-target reports')
        self.root.update()
        self.assertEqual(self.game.geometry(),initial)
        self.assertGreaterEqual(initial['width'],640);self.assertGreaterEqual(initial['height'],400)
        self.assertLess(self.game.canvas.winfo_rooty()+self.game.canvas.winfo_height(),
                        self.game.window.winfo_rooty()+self.game.window.winfo_height())
        self.game.window.geometry('900x650');self.root.update()
        self.assertGreaterEqual(self.game.geometry()['height'],400)

    def test_new_session_and_close_cancel_pending_start_and_callbacks(self):
        self.game.practice_button.invoke();self.game.new_session()
        self.assertIsNone(self.game.experiment.mode)
        self.assertFalse(self.game.experiment.waiting)
        self.game.close();self.assertTrue(self.game.closed)
        self.assertIsNone(self.game.timer)
        self.assertFalse(self.lab.processor.armed)

    def test_focus_loss_and_geometry_change_pause_instead_of_scoring(self):
        self.game.start(practice=True);geometry=self.game.geometry()
        self.now+=50;self.game.experiment.poll(self.now,0,0,geometry)
        with patch.object(self.game.window,'focus_displayof',return_value=None):
            self.now+=50;self.game.tick()
        self.assertEqual(self.game.experiment.round.phase,'paused')
        self.assertIn('focus',self.game.experiment.round.reason)
        self.assertFalse(self.lab.processor.armed)
