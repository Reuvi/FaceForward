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

    def guide(self,recheck=False):
        self.session.detector_command('start_movement_guide','pupil',recheck)
        for _ in range(200):
            g=self.core.movement_guide
            if not g.active:break
            state=g.state(self.now)
            if state['waiting']:self.session.detector_command('present_movement_step',state['index'],state['phase'],self.core.generation)
            self.feed(**self.runtime.demo_input())
        self.assertTrue(g.passed,g.report)
        self.assertTrue(self.core.pupil_ready)

    def test_calibration_normalization_unknown_and_pointer_adapter(self):
        self.assertFalse(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.guide()
        for x,y in ((.5,.5),(0,.5),(1,.5),(.5,0),(.5,1),(.25,.75)):
            frame=self.feed(pupil_x=x,pupil_y=y)
            values=frame['faces'][0]['signals']
            self.assertAlmostEqual(values['gaze_x']['value'],x)
            self.assertAlmostEqual(values['gaze_y']['value'],y)
            sample=decode(frame,MouseConfig(pointer_source='gaze'),'single-user')
            self.assertAlmostEqual(sample.pointer[0],x)
            self.assertAlmostEqual(sample.pointer[1],y)
            self.assertEqual(self.runtime.snapshot()['trace'][-1]['gaze_x'],values['gaze_x']['value'])
        for kwargs in ({'left_closed':True},{'right_closed':True},{'head':1.}):
            values=self.feed(**kwargs)['faces'][0]['signals']
            self.assertFalse(values['gaze_x']['valid'])
        self.feed(blank=True)
        self.assertIsNotNone(self.core.pupil_range)
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.assertEqual(self.core.head.center,0)

    def test_profile_roundtrip_recheck_and_atomic_validation(self):
        self.guide();self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        data=self.core.export_calibration();self.assertEqual(data['version'],6)
        self.core.disconnect();self.core.load_calibration(data)
        self.assertFalse(self.core.pupil_ready)
        self.assertFalse(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        bad=deepcopy(data);bad['pupil']['pose'][0]=float('nan')
        saved=self.core.pupil_range
        with self.assertRaises(ValueError):self.core.load_calibration(bad)
        self.assertEqual(saved,self.core.pupil_range)
        self.guide(recheck=True)
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.core.reset_pupil();self.assertIsNone(self.core.pupil_range);self.assertIsNotNone(self.core.head)

    def test_neural_reset_identity_and_unavailable_cannot_pass_absence(self):
        self.core.tongue_model=SegmentedTongueModel('/not/installed.onnx')
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        model=self.core.tongue_model
        data=self.core.export_calibration();self.assertEqual(data['version'],6)
        bad=deepcopy(data);bad['tongue']['sha256']='0'*64
        with self.assertRaises(ValueError):self.core.load_calibration(bad)
        self.core.reset_tongue();self.assertIs(self.core.tongue_model,model)
        self.session.detector_command('start_movement_guide','tongue')
        self.core.present_movement_step(0,'prepare')
        for _ in range(15):self.feed()
        self.assertFalse(self.core.movement_guide.passed)
        self.assertIn('too few',self.core.movement_guide.report)
        self.assertIsNotNone(self.core.head)

    def test_source_selection_stops_preview_and_saves(self):
        self.guide()
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
            self.assertFalse(self.core.pupil_ready)

    def test_color_profile_migrates_without_reusing_range_or_losing_head(self):
        import numpy as np
        from Vision.tongue import TongueModel
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.tongue_model=TongueModel(np.array([[40,160,140]],dtype=np.float32),
                                          np.array([[20,100,100]],dtype=np.float32),6,4,{})
        self.core.tongue_range={k:AxisCalibration(-.2,0,.2,endpoint_tolerance=.05) for k in ("x","y")}
        legacy=self.core.export_calibration();self.assertEqual(legacy["version"],5)
        model=SegmentedTongueModel()
        self.core.tongue_model=model
        self.core.load_calibration(legacy)
        self.assertIs(self.core.tongue_model,model)
        self.assertIsNone(self.core.tongue_range)
        self.assertEqual(self.core.head.center,0)
        self.assertIn("Color tongue range removed",self.core.notice)

    def test_long_unknown_pupil_trace_keeps_display_seed_only(self):
        self.guide();frame=self.feed(pupil_x=1)
        known=frame["sequence"]
        for _ in range(10):
            self.now+=1000;self.feed(blank=True)
        state=self.runtime.snapshot()
        self.assertTrue(any(row["sequence"]==known and row["gaze_x"]==1 for row in state["trace"]))
        self.assertIsNone(state["trace"][-1]["gaze_x"])
        self.assertIsNone(state["pupil"]["xy"])

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_native_pupil_popup_capture_cancel_and_neural_setup(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy)
        root.geometry('1230x910')
        with patch('Vision.movement_view.CalibrationSounds'):
            container=tk.Frame(root);container.pack(fill="both",expand=True)
            ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.pupil_tab);root.update();ui.tick()
            ui.pupil_panel.start.invoke();ui.tick();root.update();ui.tick()
            self.assertIsNotNone(ui.pupil_panel.window)
            self.assertIsNone(self.core.movement_guide.start_ms)
            ui.pupil_panel.window.event_generate('<space>');root.update()
            self.assertIsNotNone(self.core.movement_guide.start_ms)
            self.session.detector_command('cancel');ui.tick();root.update()
            self.assertIsNone(ui.pupil_panel.window)
            self.core.tongue_model=SegmentedTongueModel()
            ui.calibration_tabs.select(ui.tongue_tab);ui.tick();root.update()
            self.assertTrue(ui.tongue_setup.neural.winfo_ismapped())
            self.assertFalse(ui.tongue_setup.background.winfo_ismapped())
            self.assertTrue(ui.mouth.winfo_ismapped())
