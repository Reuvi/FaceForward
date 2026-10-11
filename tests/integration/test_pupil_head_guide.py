"""Pixels → guided personal pupil fit → shared trace/profile/mouse adapter."""
from copy import deepcopy
import os
import tempfile
import unittest
from unittest.mock import patch

import importlib.util
AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope



@unittest.skipUnless(AVAILABLE, "Vision dependencies required")
class PupilHeadGuideTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.sequence=0
        self.session=MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.session.mode='detector-demo'
        self.runtime=self.session.ensure_detector_runtime();self.core=self.runtime.workbench
        self.core.configure(dict(settle_ms=25,collect_ms=300,movement_rest_ms=50,min_samples=5))
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.eyes={'left':EyeCalibration(.04,.25,.5)}
        self.feed()

    def feed(self,blank=False,**controls):
        self.now+=25;self.sequence+=1
        image,faces=demo_image(**controls)
        frame=self.session.deliver_detection(CapturedImage(Envelope('pupil-guide',self.sequence,self.now),image),[] if blank else faces,preview=False)
        self.assertEqual(frame['pupil_matrix']['sequence'],self.sequence)
        return frame

    def guide(self, fail_index=None):
        self.session.detector_command('start_pupil_guide')
        attempts=0
        while self.core.pupil_guide.active:
            guide=self.core.pupil_guide;state=guide.state(self.now)
            if state['waiting']:
                self.session.detector_command('present_pupil_step',guide.index,state['phase'],self.core.generation)
            controls=self.runtime.demo_input()
            if fail_index==guide.index:controls.update(left_closed=True)
            self.feed(**controls)
            self.assertFalse(self.session.lab.processor.armed)
            attempts+=1
            self.assertLess(attempts,400)
        return self.core.pupil_guide

    def test_raw_before_calibration_and_complete_guide_preserves_other_channels(self):
        before=(self.core.eyes.copy(),self.core.head,self.core.head_x)
        self.assertIsNotNone(self.core.pupil.xy)
        self.assertIsNone(self.core.frame['pupil_matrix']['values'])
        guide=self.guide()
        self.assertTrue(guide.passed,guide.report)
        self.assertEqual(before,(self.core.eyes,self.core.head,self.core.head_x))
        model=self.core.pupil_model
        self.assertAlmostEqual(model['slopes'][0][0],.002,places=5)
        self.assertAlmostEqual(model['slopes'][1][1],.001,places=5)
        for yaw,pitch in ((0,0),(8,-5),(-5,6),(6,6)):
            frame=self.feed(head_x=.5+yaw/40,head=.5+pitch/40,
                            pupil_x=.5+(yaw*.002+pitch*.0004)/.4,
                            pupil_y=.5+(pitch*.001+yaw*.0002)/.2)
            values=frame['faces'][0]['signals']
            self.assertAlmostEqual(values['gaze_x']['value'],.5,places=5)
            self.assertAlmostEqual(values['gaze_y']['value'],.5,places=5)
            self.assertTrue(values['head_x']['valid']);self.assertTrue(values['head_y']['valid'])
            self.assertEqual((frame['pupil_matrix']['row'],frame['pupil_matrix']['column']),(5,5))
            trace=self.runtime.snapshot()['trace'][-1]
            self.assertAlmostEqual(trace['pupil_compensated_x'],0,places=5)
            self.assertAlmostEqual(trace['pupil_compensated_y'],0,places=5)
            self.assertEqual(trace['sequence'],frame['sequence'])
            self.assertEqual(self.session.state(include_detector=True)['detector']['trace'],self.runtime.snapshot()['trace'])
        for x,y in ((0,.5),(1,.5),(.5,0),(.5,1)):
            frame=self.feed(pupil_x=x,pupil_y=y)
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_x']['value'],x)
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_y']['value'],y)

    def test_retry_only_failed_step_then_cancel_and_loss_retain_fit(self):
        self.assertTrue(self.guide().passed)
        original=deepcopy(self.core.pupil_model)
        guide=self.guide(fail_index=6)
        self.assertFalse(guide.passed);self.assertEqual(guide.index,6)
        self.assertEqual(self.core.pupil_model,original)
        groups=deepcopy(guide.groups)
        self.session.detector_command('retry_pupil_step')
        self.assertEqual(guide.groups,groups)
        self.assertTrue(guide.active)
        self.session.detector_command('cancel')
        self.assertIsNone(self.core.pupil_guide)
        self.assertEqual(self.core.pupil_model,original)
        self.feed(blank=True);self.feed()
        self.assertEqual(self.core.pupil_model,original)
        self.assertTrue(self.core.frame['pupil_matrix']['valid'])
        self.session.detector_command('start_pupil_guide')
        self.feed(blank=True)
        self.assertIsNone(self.core.pupil_guide)
        self.assertEqual(self.core.pupil_model,original)

    def test_reset_pupils_keeps_eyes_and_head_and_blocks_mixed_guides(self):
        self.assertTrue(self.guide().passed)
        before=(self.core.eyes.copy(),self.core.head,self.core.head_x)
        self.session.detector_command('start_pupil_guide')
        with self.assertRaises(ValueError):self.core.start_eye_guide()
        with self.assertRaises(ValueError):self.core.reset_head_x()
        self.assertTrue(self.core.pupil_guide.active)
        self.session.detector_command('reset_pupils')
        self.assertIsNone(self.core.pupil_model)
        self.assertIsNone(self.core.frame['pupil_matrix']['values'])
        self.assertEqual(before,(self.core.eyes,self.core.head,self.core.head_x))
        self.feed();self.session.detector_command('start_movement_guide','head_x')
        with self.assertRaises(ValueError):self.core.start_pupil_guide()
        self.assertTrue(self.core.movement_guide.active)

    def test_profile_roundtrip_and_malformed_pupil_state_is_atomic(self):
        self.assertTrue(self.guide().passed)
        original=self.core.export_calibration()
        self.assertEqual(original['version'],12)
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/profile.json';self.session.save_profile(path)
            self.core.disconnect();self.session.load_profile(path)
            self.assertEqual(self.core.export_calibration(),original)
            self.assertFalse(self.session.lab.processor.armed)
            self.feed();self.assertTrue(self.core.frame['pupil_matrix']['valid'])
        for update in ({'slopes':[[float('nan'),0],[0,0]]},{'checks':{}},{'reference_pose':[0,0,True]}):
            bad=deepcopy(original);bad['pupil']['calibration'].update(update)
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),original)

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_native_guide_prompt_ack_rest_countdown_and_tab_cancel(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy)
        errors=[];root.report_callback_exception=lambda *error:errors.append(error)
        root.geometry('1230x910')
        with patch('Vision.pupil_view.CalibrationSounds'),patch('Vision.eye_view.CalibrationSounds'),patch('Vision.movement_view.CalibrationSounds'):
            container=tk.Frame(root);container.pack(fill='both',expand=True)
            ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.pupil_tab);root.update();ui.tick()
            ui.pupil_panel.start.invoke();self.assertIsNone(self.core.pupil_guide.start_ms)
            ui.tick();root.update();ui.tick();root.update()
            self.assertIsNotNone(self.core.pupil_guide.start_ms)
            self.assertTrue(ui.pupil_panel.fullscreen.ready)
            self.assertEqual(ui.pupil_panel.fullscreen.window.grab_current(),ui.pupil_panel.fullscreen.window)
            for _ in range(13):self.feed(**self.runtime.demo_input())
            ui.tick();root.update();ui.tick();root.update()
            canvas=ui.pupil_panel.fullscreen.canvas
            self.assertTrue(canvas.find_withtag('rest-countdown'))
            self.assertTrue(canvas.find_withtag('rest-instruction'))
            self.assertIn('CENTER',canvas.itemcget(canvas.find_withtag('rest-instruction')[0],'text'))
            ui.calibration_tabs.select(ui.head_x_tab);ui.tick();root.update()
            self.assertIsNone(self.core.pupil_guide)
            self.assertIsNone(ui.pupil_panel.fullscreen)
            self.assertIsNone(root.grab_current())
            self.assertFalse(errors)
