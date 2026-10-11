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
    from Processing.mouse.config import MouseConfig
    from Processing.mouse.signals import decode


@unittest.skipUnless(AVAILABLE,'pixel dependencies required')
class JoystickIntegration(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.sequence=0
        self.session=MouseSession(clock=lambda:self.now);self.addCleanup(self.session.close)
        self.session.mode='detector-demo';self.runtime=self.session.ensure_detector_runtime();self.core=self.runtime.workbench
        self.core.configure(dict(settle_ms=0,collect_ms=300,movement_rest_ms=0,min_samples=5))
        from tests.vision.pupil_fixture import pupil_fixture
        self.core.pupil_model = pupil_fixture()
        self.feed()

    def feed(self,blank=False,**controls):
        self.now+=25;self.sequence+=1
        b,o=demo_image(**controls)
        return self.session.deliver_detection(CapturedImage(Envelope('pupils',self.sequence,self.now),b),[] if blank else o,preview=False)

    def test_personal_normalization_unknown_and_pointer_adapter(self):
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        for x,y,expected_y in ((.5,.5,.5),(0,.5,.5),(1,.5,.5),(.5,0,0),(.5,.825,1),(.25,.6625,.75)):
            frame=self.feed(pupil_x=x,pupil_y=y)
            values=frame['faces'][0]['signals']
            self.assertAlmostEqual(values['gaze_x']['value'],x)
            self.assertAlmostEqual(values['gaze_y']['value'],expected_y)
            sample=decode(frame,MouseConfig(pointer_source='gaze'),'single-user')
            self.assertAlmostEqual(sample.pointer[0],x)
            self.assertAlmostEqual(sample.pointer[1],expected_y)
            self.assertEqual(self.runtime.snapshot()['trace'][-1]['gaze_x'],values['gaze_x']['value'])
            self.assertEqual(frame['gaze_measurement'],'head_compensated_iris_direction_v1')
        for kwargs in ({'left_closed':True},{'right_closed':True}):
            values=self.feed(**kwargs)['faces'][0]['signals']
            self.assertFalse(values['gaze_x']['valid'])
        self.feed(blank=True)
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.assertEqual(self.core.head.center,0)
        self.assertFalse(self.session.lab.processor.armed)

    def test_matrix_every_capture_matches_continuous_position_and_processing_adapter(self):
        from Processing.mouse.signals import one_hot_matrix
        # Cover every cell, including all boundaries and the exact center.
        for row in range(11):
            for column in range(11):
                y=row/10
                demo_y=y if y <= .5 else .5+(y-.5)*.65
                frame=self.feed(pupil_x=column/10,pupil_y=demo_y)
                grid=frame['pupil_matrix']
                self.assertTrue(grid['valid'])
                self.assertEqual((grid['row'],grid['column']),(row,column))
                self.assertEqual(grid['size'],11)
                self.assertEqual(grid['subject_id'],'single-user')
                self.assertEqual(grid['format'],'pupil_matrix_v1')
                for key in ('sequence','session_id','timestamp_ms'):
                    self.assertEqual(grid[key],frame[key])
                self.assertEqual(len(grid['values']),11)
                self.assertTrue(all(len(r)==11 for r in grid['values']))
                self.assertEqual(sum(sum(r) for r in grid['values']),1)
                self.assertEqual(one_hot_matrix(grid['values']),(column/10,row/10))
                trace=self.runtime.snapshot()['trace'][-1]
                self.assertEqual((trace['pupil_matrix_row'],trace['pupil_matrix_column']),(row,column))
        self.assertEqual(self.session.state(include_detector=True)['detector']['trace'],self.runtime.snapshot()['trace'])
        # Fractional directions remain continuous in the existing mouse adapter.
        frame=self.feed(pupil_x=.273,pupil_y=.25)
        sample=decode(frame,MouseConfig(pointer_source='gaze'),'single-user')
        self.assertAlmostEqual(sample.pointer[0],.273)
        self.assertNotEqual(sample.pointer,one_hot_matrix(frame['pupil_matrix']['values']))

    def test_matrix_unknown_loss_stop_load_and_csv_keep_validity_consistent(self):
        import csv
        self.feed(pupil_x=.8)
        for kwargs in ({'blank':True},{'left_closed':True},{'right_closed':True}):
            frame=self.feed(**kwargs);grid=frame['pupil_matrix']
            self.assertFalse(grid['valid']);self.assertIsNone(grid['values'])
            self.assertIsNone(grid['row']);self.assertIsNone(grid['column'])
            self.assertEqual(grid['confidence'],0)
        self.feed();self.core.disconnect()
        self.assertIsNone(self.core.frame['pupil_matrix']['values'])
        self.feed();data=self.core.export_calibration();self.core.load_calibration(data)
        self.assertIsNone(self.core.frame['pupil_matrix']['values'])
        self.feed(pupil_y=.825)
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/pupils.csv';self.runtime.export_trace(path)
            with open(path) as handle:row=list(csv.DictReader(handle))[-1]
            self.assertEqual(row['pupil_matrix_row'],'10')
            self.assertEqual(row['pupil_matrix_valid'],'True')
            self.assertEqual(row['pupil_matrix_size'],'11')
            self.assertNotIn('pupil_x_sensitivity',row)
        self.now+=self.core.config.stale_ms+1
        self.assertIsNone(self.runtime.snapshot()['frame']['pupil_matrix']['values'])

    def test_completed_profile_roundtrip_and_atomic_validation(self):
        data=self.core.export_calibration();self.assertEqual(data['version'],12)
        self.assertEqual(data['eyes'],{});self.assertIsNone(data['head'])
        self.core.disconnect();self.core.load_calibration(data)
        values=self.feed(pupil_x=.75,pupil_y=1)['faces'][0]['signals']
        self.assertAlmostEqual(values['gaze_x']['value'],.75)
        self.assertEqual(values['gaze_y']['value'],1)
        for pupil in (None,dict(data['pupil'],x_sensitivity=float('nan')),dict(data['pupil'],extra=1),
                      dict(data['pupil'],measurement='wrong')):
            bad=deepcopy(data);bad['pupil']=pupil
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(data,self.core.export_calibration())

    def test_legacy_pupil_fits_are_validated_then_discarded(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        original=self.core.export_calibration()
        for version,algorithm in ((6,'tongue-segmentation-pupil-joystick-v6'),(7,'independent-head-axes-v7')):
            old=deepcopy(original);old.update(version=version,algorithm=algorithm,tongue=None,tongue_range=None,tongue_measurement="color_tip_mouth_width_v1")
            if version==6:old.pop('head_x')
            old['pupil']={'range':{axis:dict(low=-.05,center=.05,high=.15,endpoint_tolerance=.05) for axis in ('x','y')},'pose':[30,25,20]}
            self.core.load_calibration(old)
            self.assertIn('old pupil settings discarded',self.core.notice)
            values=self.feed()['faces'][0]['signals']
            self.assertIsNone(values['gaze_x']['value'])
            self.assertIsNone(values['gaze_y']['value'])
            self.assertIsNotNone(self.core.pupil.xy)
            self.assertEqual(self.core.head.center,0)
            saved=self.core.export_calibration()
            bad=deepcopy(old);bad['pupil']['pose'][0]=float('nan')
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),saved)

    def test_no_eye_fit_dependency_but_head_pose_is_required(self):
        from Vision.calibration import EyeCalibration
        # A poor eye-closure fit must not turn a visible iris into a pupil failure.
        self.core.eyes['left']=EyeCalibration(.24,.5,.7)
        self.core.eyes['right']=EyeCalibration(.24,.5,.7)
        values=self.feed(head=1)['faces'][0]['signals']
        self.assertTrue(values['gaze_x']['valid'])
        b,o=demo_image(pupil_x=.75);o[0].rotation=None
        self.now+=25;self.sequence+=1
        frame=self.session.deliver_detection(CapturedImage(Envelope('pupils',self.sequence,self.now),b),o,preview=False)
        self.assertIsNone(frame['faces'][0]['signals']['gaze_x']['value'])
        self.assertIn('Head pose unavailable',self.core.reasons['pupil'])
        self.core.disconnect()
        self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])
        self.session.detector_command('start_pupil_guide')
        self.assertIsNotNone(self.core.pupil_guide)
        self.assertFalse(self.session.lab.processor.armed)

    def test_guided_personal_eye_geometry_improves_narrow_pupil_availability(self):
        from Vision.calibration import EyeCalibration
        raw=self.feed(left_ratio=.12,right_ratio=.12,pupil_x=.75)
        self.assertFalse(raw['faces'][0]['signals']['gaze_x']['valid'])
        fit=EyeCalibration.fit_guided([.04]*12,[[.12]*12,[.25]*12],min_separation=.015)
        self.core.eyes={side:fit for side in ('left','right')}
        frame=self.feed(left_ratio=.12,right_ratio=.12,pupil_x=.75)
        self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_x']['value'],.75)
        self.assertTrue(frame['pupil_matrix']['valid'])
        self.assertEqual(self.core.pupil.eyes['left']['aperture_source'],'personal open geometry')
        frame=self.feed(left_closed=True)
        self.assertFalse(frame['pupil_matrix']['valid'])
        self.assertIsNone(frame['faces'][0]['signals']['gaze_x']['value'])

    def test_legacy_sensitivity_is_validated_then_discarded_without_losing_fits(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x=AxisCalibration(-15,0,20,endpoint_tolerance=.05)
        data=self.core.export_calibration()
        for version,algorithm in ((8,'direct-mediapipe-pupils-v8'),(9,'lip-boundary-head-reliability-v9')):
            old=deepcopy(data);old.update(version=version,algorithm=algorithm,tongue=None,tongue_range=None,tongue_measurement="color_tip_mouth_width_v1")
            old['pupil']=dict(measurement='mediapipe_iris_direction_v2',x_sensitivity=4,y_sensitivity=.25)
            self.core.load_calibration(old)
            values=self.feed(pupil_x=.75,pupil_y=.825)['faces'][0]['signals']
            self.assertIsNone(values['gaze_x']['value'])
            self.assertIsNone(values['gaze_y']['value'])
            self.assertEqual(self.core.head.low,-12);self.assertEqual(self.core.head_x.high,20)
            self.assertIn('old pupil settings discarded',self.core.notice)
            self.assertIsNone(self.core.export_calibration()['pupil']['calibration'])
            saved=self.core.export_calibration()
            for value in (float('nan'),0,5,True):
                bad=deepcopy(old);bad['pupil']['x_sensitivity']=value
                with self.assertRaises(ValueError):self.core.load_calibration(bad)
                self.assertEqual(self.core.export_calibration(),saved)
        with self.assertRaisesRegex(ValueError,'Unsupported'):
            self.session.detector_command('set_pupil_sensitivity',2,2)
        self.assertFalse(hasattr(self.core,'set_pupil_sensitivity'))


    def test_pupil_source_saves_with_transfer_settings(self):
        config=self.session.lab.state()["config"];config["pointer"]["smoothing_ms"]=135
        self.session.lab.settings({"config":config})
        self.assertEqual(self.session.lab.state()["config"]["pointer"]["smoothing_ms"],135)
        self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
        self.assertFalse(self.session.lab.processor.armed)
        with tempfile.TemporaryDirectory() as folder:
            path=folder+'/profile.json';self.session.save_profile(path)
            self.session.load_profile(path)
            self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
            self.assertTrue(self.feed()['faces'][0]['signals']['gaze_x']['valid'])


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
    def test_native_pupil_controls_and_matrix(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy)
        callback_errors=[]
        root.report_callback_exception=lambda *error:callback_errors.append(error)
        root.geometry('1230x910')
        with patch('Vision.movement_view.CalibrationSounds'), patch('Vision.pupil_view.CalibrationSounds'):
            container=tk.Frame(root);container.pack(fill="both",expand=True)
            ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
            self.addCleanup(ui.close_panels)
            ui.calibration_tabs.select(ui.pupil_tab);root.update();ui.tick()
            self.assertTrue(hasattr(ui.pupil_panel,'start'))
            self.assertFalse(hasattr(ui.pupil_panel,'window'))
            self.assertIn('Personal pupil calibration',ui.pupil_panel.message.get())
            self.assertIsNone(self.core.movement_guide)
            self.feed(pupil_x=.75);ui.tick();root.update()
            self.assertIn('Normalized X/Y: (0.750, 0.500)',ui.pupil_details.get())
            self.assertFalse(hasattr(ui.pupil_panel,'apply_button'))
            self.assertFalse(hasattr(ui.pupil_panel,'inputs'))
            canvas=ui.pupil_panel.canvas
            self.assertEqual(len(canvas.find_withtag('matrix-grid')),24)
            self.assertEqual(len(canvas.find_withtag('pupil-cell')),1)
            cell=canvas.coords(canvas.find_withtag('pupil-cell')[0])
            self.assertAlmostEqual(cell[2]-cell[0],cell[3]-cell[1])
            self.assertEqual(self.core.frame['pupil_matrix']['column'],8)
            self.feed(blank=True);ui.tick();root.update()
            from LabUI.traces import darker
            item=canvas.find_withtag('pupil-cell')[0]
            self.assertEqual(canvas.itemcget(item,'fill'),darker('#6ed7fe'))
            self.assertIsNone(self.core.frame['pupil_matrix']['values'])
            ui.movement_scope_mode.set('Normalized positions');ui.tick();root.update()
            labels={ui.scope.itemcget(item,'text') for item in ui.scope.find_all() if ui.scope.type(item)=='text'}
            self.assertIn('Pupil X',labels)
            ui.visible=lambda:False;ui.tick();root.update()
            ui.visible=lambda:True;ui.tick();root.update()
            self.assertFalse(callback_errors)
            self.assertEqual([ui.calibration_tabs.tab(tab, 'text') for tab in ui.calibration_tabs.tabs()],
                             ['1 Eyes', '2 Head Y', '3 Head X', '4 Pupils', 'Settings'])
            self.assertFalse(hasattr(ui, 'tongue_setup'))
