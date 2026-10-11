"""Head Y pose corrections through App, persistence, and native controls."""
from copy import deepcopy
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

AVAILABLE=all(importlib.util.find_spec(name) for name in ('cv2','numpy'))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope
    from tests.vision.pupil_fixture import pupil_fixture


@unittest.skipUnless(AVAILABLE,'Vision image dependencies required')
class HeadYRetryTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.sequence=0
        self.session=MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close);self.session.mode='detector-demo'
        self.runtime=self.session.ensure_detector_runtime();self.core=self.runtime.workbench
        self.core.configure(dict(settle_ms=25,collect_ms=300,movement_rest_ms=50,min_samples=5))
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x=AxisCalibration(-15,0,15,endpoint_tolerance=.05)
        self.core.eyes={'left':EyeCalibration(.04,.25,.5)}
        self.core.pupil_model=pupil_fixture()
        self.feed()

    def feed(self,blank=False,**controls):
        self.now+=25;self.sequence+=1
        image,faces=demo_image(**controls)
        return self.session.deliver_detection(CapturedImage(Envelope('head-retry',self.sequence,self.now),image),[] if blank else faces,preview=False)

    def finish(self, positions=None, *, old_fit=None, fail=None):
        positions=positions or dict(neutral=.5,up=.2,down=.8)
        steps=[]
        for _ in range(160):
            guide=self.core.movement_guide
            if not guide.active:break
            state=guide.state(self.now)
            if state['waiting']:
                self.session.detector_command('present_movement_step',guide.index,state['phase'],self.core.generation)
            step=(state['role'],state['name'])
            if not steps or step!=steps[-1]:steps.append(step)
            value=.5 if step==fail else positions[state['name']]
            self.feed(head=value)
            self.assertFalse(self.session.lab.processor.armed)
            if old_fit and not guide.passed:self.assertEqual(self.core.head,old_fit)
        self.assertFalse(guide.active)
        return steps

    def test_loaded_fit_retake_one_pose_preserves_channels_and_requires_fresh_checks(self):
        before=self.core.export_calibration()
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/profile.json';self.session.save_profile(path)
            self.session.load_profile(path);self.feed()
            self.assertIsNone(self.core.movement_guide)
            old=self.core.head
            self.session.lab.processor.armed=True
            self.session.detector_command('redo_head_y_step','train','up')
            self.assertFalse(self.session.lab.processor.armed)
            self.assertEqual(self.core.head,old)
            self.assertEqual(self.core.movement_guide.groups,{})
            steps=self.finish(dict(neutral=.5,up=.1,down=.8),old_fit=old)
            self.assertEqual(steps,[('train','up'),('check','neutral'),('check','up'),('check','down')])
            self.assertTrue(self.core.movement_guide.passed,self.core.notice)
            self.assertAlmostEqual(self.core.head.low,-16)
            self.assertEqual(self.core.head.center,old.center);self.assertEqual(self.core.head.high,old.high)
            self.assertEqual(set(self.core.movement_guide.groups),{'up'})
            after=self.core.export_calibration()
            for key in before:
                if key!='head':self.assertEqual(after[key],before[key])
            self.session.save_profile(path);self.session.load_profile(path);self.feed(head=.3)
            self.assertAlmostEqual(self.core.frame['faces'][0]['signals']['head_y']['value'],.25)
            self.assertEqual(self.core.export_calibration(),after)
            self.assertEqual(self.runtime.snapshot()['trace'],self.session.state(include_detector=True)['detector']['trace'])

    def test_full_restart_failure_cancel_and_loss_keep_previous_fit(self):
        old=self.core.head
        self.session.detector_command('start_movement_guide','head')
        self.assertEqual(self.core.head,old)
        self.finish(fail=('train','down'),old_fit=old)
        self.assertFalse(self.core.movement_guide.passed)
        previous=deepcopy(self.core.movement_guide.groups['neutral'])
        self.session.detector_command('retry_movement_step')
        self.assertEqual(self.core.movement_guide.groups['neutral'],previous)
        self.assertEqual(self.finish(old_fit=old),[('train','down'),('check','neutral'),('check','up'),('check','down')])
        self.assertTrue(self.core.movement_guide.passed)
        old=self.core.head  # The freshly completed fit is now the one to retain.
        for stop in ('cancel','loss'):
            self.session.detector_command('redo_head_y_step','train','neutral')
            if stop=='cancel':self.session.detector_command('cancel')
            else:self.feed(blank=True)
            self.assertEqual(self.core.head,old)
            self.feed();self.assertTrue(self.core.frame['faces'][0]['signals']['head_y']['valid'])

    def test_check_only_failure_retries_alone_and_never_retrains(self):
        old=self.core.head
        self.session.detector_command('redo_head_y_step','check','down')
        self.finish(fail=('check','down'),old_fit=old)
        self.assertFalse(self.core.movement_guide.passed)
        self.session.detector_command('retry_movement_step')
        self.assertEqual(self.finish(old_fit=old),[('check','down')])
        self.assertEqual(self.core.head,old)
        self.assertEqual(self.core.movement_guide.groups,{})

    def test_active_retry_generation_and_other_calibration_exclusion(self):
        self.session.detector_command('start_movement_guide','head')
        generation=self.core.generation
        self.session.detector_command('present_movement_step',0,'prepare',generation)
        self.feed();self.assertTrue(self.core.movement_guide.values)
        self.session.detector_command('retry_movement_step')
        self.assertGreater(self.core.generation,generation)
        self.assertEqual(self.core.movement_guide.values,[])
        self.session.detector_command('present_movement_step',0,'prepare',generation)
        self.assertIsNone(self.core.movement_guide.start_ms)
        self.session.detector_command('cancel')
        for command,args in (('start_movement_guide',('head_x',)),('start_eye_guide',()),('start_pupil_guide',())):
            self.session.detector_command(command,*args)
            guide=self.core.movement_guide or self.core.eye_guide or self.core.pupil_guide
            with self.assertRaises(ValueError):self.session.detector_command('redo_head_y_step','train','up')
            self.assertTrue(guide.active)
            self.session.detector_command('cancel')

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_native_specific_pose_selection_and_active_retry(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy);root.geometry('1230x910')
        errors=[];root.report_callback_exception=lambda *error:errors.append(error)
        with patch('Vision.movement_view.CalibrationSounds'),patch('Vision.eye_view.CalibrationSounds'),patch('Vision.pupil_view.CalibrationSounds'):
            container=tk.Frame(root);container.pack(fill='both',expand=True)
            ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.head_tab);root.update();ui.tick();root.update()
            panel=ui.head_panel
            self.assertEqual(len(panel.step_picker['values']),6)
            self.assertIn('Up: saved',panel.retained.get())
            panel.step_choice.set('Capture up');panel.redo.invoke()
            self.assertEqual(self.core.movement_guide.steps[0][:2],('train','up'))
            ui.tick();root.update();ui.tick();root.update()
            old=self.core.generation
            self.assertEqual(str(panel.retry['state']),'normal')
            panel.retry.invoke();self.assertGreater(self.core.generation,old)
            self.assertIsNone(self.core.movement_guide.start_ms)
            ui.tick();root.update();ui.tick();root.update()
            self.assertIsNotNone(self.core.movement_guide.start_ms)
            ui.calibration_tabs.select(ui.head_x_tab);ui.tick();root.update()
            self.assertIsNone(self.core.movement_guide)
            self.assertIsNotNone(self.core.head)
            self.assertFalse(errors)
