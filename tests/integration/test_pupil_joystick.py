"""One capture through calibration, persistence and the existing mouse adapter."""
from copy import deepcopy
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

AVAILABLE=all(importlib.util.find_spec(k) for k in ('cv2','numpy'))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope
    from Vision.calibration import AxisCalibration
    from Vision.tongue_segment import SegmentedTongueModel
    from Processing.mouse.config import MouseConfig
    from Processing.mouse.signals import decode


@unittest.skipUnless(AVAILABLE,'pixel dependencies required')
class JoystickIntegration(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.sequence=0
        self.session=MouseSession(clock=lambda:self.now);self.addCleanup(self.session.close)
        self.session.mode='detector-demo';self.runtime=self.session.ensure_detector_runtime();self.core=self.runtime.workbench
        self.core.configure(dict(settle_ms=0,collect_ms=300,movement_rest_ms=0,min_samples=5))
        self.feed()

    def feed(self,blank=False,**controls):
        self.now+=25;self.sequence+=1
        b,o=demo_image(**controls)
        return self.session.deliver_detection(CapturedImage(Envelope('pupils',self.sequence,self.now),b),[] if blank else o,preview=False)

    def test_direct_normalization_unknown_and_pointer_adapter(self):
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        for x,y in ((.5,.5),(0,.5),(1,.5),(.5,0),(.5,1),(.25,.75)):
            frame=self.feed(pupil_x=x,pupil_y=y)
            values=frame['faces'][0]['signals']
            self.assertAlmostEqual(values['gaze_x']['value'],x)
            self.assertAlmostEqual(values['gaze_y']['value'],y)
            sample=decode(frame,MouseConfig(pointer_source='gaze'),'single-user')
            self.assertAlmostEqual(sample.pointer[0],x)
            self.assertAlmostEqual(sample.pointer[1],y)
            self.assertEqual(self.runtime.snapshot()['trace'][-1]['gaze_x'],values['gaze_x']['value'])
            self.assertEqual(frame['gaze_measurement'],'mediapipe_iris_direction_v2')
        for kwargs in ({'left_closed':True},{'right_closed':True}):
            values=self.feed(**kwargs)['faces'][0]['signals']
            self.assertFalse(values['gaze_x']['valid'])
        self.feed(blank=True)
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.assertEqual(self.core.head.center,0)
        self.assertFalse(self.session.lab.processor.armed)

    def test_profile_roundtrip_without_training_and_atomic_validation(self):
        self.session.detector_command('set_pupil_sensitivity',2,.5)
        data=self.core.export_calibration();self.assertEqual(data['version'],9)
        self.assertEqual(data['eyes'],{});self.assertIsNone(data['head'])
        self.core.disconnect();self.core.load_calibration(data)
        values=self.feed(pupil_x=.75,pupil_y=1)['faces'][0]['signals']
        self.assertAlmostEqual(values['gaze_x']['value'],1)
        self.assertEqual(values['gaze_y']['value'],.75)
        for pupil in (None,dict(data['pupil'],x_sensitivity=float('nan')),dict(data['pupil'],extra=1),
                      dict(data['pupil'],measurement='wrong')):
            bad=deepcopy(data);bad['pupil']=pupil
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(data,self.core.export_calibration())

    def test_legacy_pupil_fits_are_validated_then_discarded(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        original=self.core.export_calibration()
        for version,algorithm in ((6,'tongue-segmentation-pupil-joystick-v6'),(7,'independent-head-axes-v7')):
            old=deepcopy(original);old.update(version=version,algorithm=algorithm)
            if version==6:old.pop('head_x')
            old['pupil']={'range':{axis:dict(low=-.05,center=.05,high=.15,endpoint_tolerance=.05) for axis in ('x','y')},'pose':[30,25,20]}
            self.core.load_calibration(old)
            self.assertIn('Old pupil fit removed',self.core.notice)
            values=self.feed()['faces'][0]['signals']
            self.assertEqual(values['gaze_x']['value'],.5)
            self.assertEqual(values['gaze_y']['value'],.5)
            self.assertEqual(self.core.head.center,0)
            saved=self.core.export_calibration()
            bad=deepcopy(old);bad['pupil']['pose'][0]=float('nan')
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),saved)

    def test_no_eye_fit_pose_or_recheck_dependency(self):
        from Vision.calibration import EyeCalibration
        # A poor eye-closure fit must not turn a visible iris into a pupil failure.
        self.core.eyes['left']=EyeCalibration(.24,.5,.7)
        self.core.eyes['right']=EyeCalibration(.24,.5,.7)
        values=self.feed(head=1)['faces'][0]['signals']
        self.assertTrue(values['gaze_x']['valid'])
        b,o=demo_image(pupil_x=.75);o[0].rotation=None
        self.now+=25;self.sequence+=1
        frame=self.session.deliver_detection(CapturedImage(Envelope('pupils',self.sequence,self.now),b),o,preview=False)
        self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_x']['value'],.75)
        self.core.disconnect()
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        with self.assertRaisesRegex(ValueError,'no calibration'):
            self.session.detector_command('start_movement_guide','pupil')
        self.assertIsNone(self.core.movement_guide)

    def test_sensitivity_preserves_fits_and_invalidates_old_normalized_sample(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x=AxisCalibration(-15,0,20,endpoint_tolerance=.05)
        self.feed(pupil_x=.75)
        self.session.lab.processor.armed=True
        self.session.detector_command('set_pupil_sensitivity',2,.5)
        self.assertFalse(self.session.lab.processor.armed)
        self.assertFalse(self.core.frame['faces'][0]['signals']['gaze_x']['valid'])
        self.assertEqual(self.core.head.low,-12);self.assertEqual(self.core.head_x.high,20)
        with self.assertRaises(ValueError):self.session.detector_command('set_pupil_sensitivity',0,1)
        self.assertEqual(self.core.pupil_settings['x_sensitivity'],2)
        values=self.feed(pupil_x=.75)['faces'][0]['signals']
        self.assertAlmostEqual(values['gaze_x']['value'],1)
        self.session.detector_command('set_pupil_sensitivity',1,1)
        self.assertAlmostEqual(self.feed(pupil_x=.75)['faces'][0]['signals']['gaze_x']['value'],.75)

    def test_neural_reset_identity_and_unavailable_cannot_pass_absence(self):
        self.core.tongue_model=SegmentedTongueModel('/not/installed.onnx')
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        model=self.core.tongue_model
        data=self.core.export_calibration();self.assertEqual(data['version'],9)
        bad=deepcopy(data);bad['tongue']['sha256']='0'*64
        with self.assertRaises(ValueError):self.core.load_calibration(bad)
        self.core.reset_tongue();self.assertIs(self.core.tongue_model,model)
        self.session.detector_command('start_movement_guide','tongue')
        self.core.present_movement_step(0,'prepare')
        # Async inference admits at most stale_ms delivery grace after capture.
        for _ in range(25):self.feed()
        self.assertFalse(self.core.movement_guide.passed)
        self.assertIn('too few',self.core.movement_guide.report)
        self.assertIsNotNone(self.core.head)

    def test_source_selection_stops_preview_and_saves(self):
        config=self.session.lab.state()["config"];config["pointer"]["smoothing_ms"]=135
        self.session.lab.settings({"config":config})
        self.session.set_pointer_source('gaze')
        self.assertEqual(self.session.lab.state()["config"]["pointer"]["smoothing_ms"],135)
        self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
        self.assertFalse(self.session.lab.processor.armed)
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/profile.json';self.session.save_profile(path)
            self.session.set_pointer_source('tongue');self.session.load_profile(path)
            self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
            self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])

    def test_color_profile_migrates_without_reusing_range_or_losing_head(self):
        import numpy as np
        from Vision.tongue import TongueModel
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.tongue_model=TongueModel(np.array([[40,160,140]],dtype=np.float32),
                                          np.array([[20,100,100]],dtype=np.float32),6,4,{})
        self.core.tongue_range={k:AxisCalibration(-.2,0,.2,endpoint_tolerance=.05) for k in ("x","y")}
        legacy=self.core.export_calibration()
        legacy.update(version=5,algorithm="color-tongue-tip-v5")
        legacy.pop("head_x");legacy.pop("pupil")
        legacy["settings"].pop("head_yaw_separation")
        model=SegmentedTongueModel()
        self.core.tongue_model=model
        self.core.load_calibration(legacy)
        self.assertIs(self.core.tongue_model,model)
        self.assertIsNone(self.core.tongue_range)
        self.assertEqual(self.core.head.center,0)
        self.assertIn("Incompatible tongue range removed",self.core.notice)

    def test_long_unknown_pupil_trace_keeps_display_seed_only(self):
        frame=self.feed(pupil_x=1)
        known=frame["sequence"]
        for _ in range(10):
            self.now+=1000;self.feed(blank=True)
        state=self.runtime.snapshot()
        self.assertTrue(any(row["sequence"]==known and row["gaze_x"] is not None and abs(row["gaze_x"]-1)<1e-9 for row in state["trace"]))
        self.assertIsNone(state["trace"][-1]["gaze_x"])
        self.assertIsNone(state["pupil"]["xy"])

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_native_direct_pupil_controls_and_neural_setup(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy)
        callback_errors=[]
        root.report_callback_exception=lambda *error:callback_errors.append(error)
        root.geometry('1230x910')
        with patch('Vision.movement_view.CalibrationSounds'):
            container=tk.Frame(root);container.pack(fill="both",expand=True)
            ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.pupil_tab);root.update();ui.tick()
            self.assertFalse(hasattr(ui.pupil_panel,'start'))
            self.assertFalse(hasattr(ui.pupil_panel,'window'))
            self.assertIn('no calibration',ui.pupil_panel.message.get())
            self.assertIsNone(self.core.movement_guide)
            ui.pupil_panel.values[0].set('2');ui.pupil_panel.apply_button.invoke()
            self.feed(pupil_x=.75);ui.tick();root.update()
            self.assertEqual(self.core.pupil_settings['x_sensitivity'],2)
            self.assertIn('Normalized X/Y: (1.000, 0.500)',ui.pupil_details.get())
            ui.pupil_panel.reset_button.invoke();ui.tick();root.update()
            self.assertEqual(self.core.pupil_settings['x_sensitivity'],1)
            ui.movement_scope_mode.set('Normalized positions');ui.tick();root.update()
            labels={ui.scope.itemcget(item,'text') for item in ui.scope.find_all() if ui.scope.type(item)=='text'}
            self.assertIn('Pupil X',labels)
            ui.visible=lambda:False;ui.tick();root.update()
            ui.visible=lambda:True;ui.tick();root.update()
            self.assertFalse(callback_errors)
            self.core.tongue_model=SegmentedTongueModel()
            ui.calibration_tabs.select(ui.tongue_tab);ui.tick();root.update()
            self.assertTrue(ui.tongue_setup.neural.winfo_ismapped())
            self.assertFalse(ui.tongue_setup.background.winfo_ismapped())
            self.assertTrue(ui.mouth.winfo_ismapped())
