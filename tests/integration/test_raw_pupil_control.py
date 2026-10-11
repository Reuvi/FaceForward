"""Raw pupils replace the retired live pupil guide; old fits remain inert."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

AVAILABLE=all(importlib.util.find_spec(k) for k in ('numpy','cv2'))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope
    from tests.vision.pupil_fixture import pupil_fixture


@unittest.skipUnless(AVAILABLE,'Vision dependencies required')
class RawPupilControlTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.sequence=0
        self.session=MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.session.mode='detector-demo'
        self.runtime=self.session.ensure_detector_runtime()
        self.core=self.runtime.workbench
        self.feed()

    def feed(self, blank=False, missing_pose=False, **controls):
        self.now+=25;self.sequence+=1
        image,faces=demo_image(**controls)
        if missing_pose:faces[0].rotation=None
        return self.session.deliver_detection(CapturedImage(Envelope('raw-pupil',self.sequence,self.now),image),
                                              [] if blank else faces,preview=False)

    def test_no_calibration_and_no_head_pose_needed_on_first_capture(self):
        self.assertEqual(self.core.eyes,{})
        self.assertIsNone(self.core.head)
        self.assertIsNone(self.core.pupil_model)
        for x,y,expected_y in ((0,.5,.5),(1,.5,.5),(.5,0,0),(.5,.825,1),(.25,.6625,.75)):
            frame=self.feed(pupil_x=x,pupil_y=y,missing_pose=True)
            self.assertEqual(frame['gaze_measurement'],'mediapipe_iris_direction_v3')
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_x']['value'],x)
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_y']['value'],expected_y)
            self.assertTrue(frame['pupil_matrix']['valid'])
            self.assertIsNone(self.runtime.snapshot()['trace'][-1]['pupil_compensated_x'])

    def test_loaded_head_correction_and_bounds_cannot_affect_raw_output(self):
        fit=pupil_fixture();fit['slopes']=[[.01,.01],[-.01,.01]]
        fit['center']=[.04,-.01];fit['low']=[-.1,-.08];fit['high']=[.2,.09]
        fit['pose_bounds']=[[-5,5],[-4,4]]
        self.core.pupil_model=fit
        for head_x,head in ((.5,.5),(0,1),(1,0)):
            frame=self.feed(head_x=head_x,head=head,pupil_x=.75,pupil_y=.25)
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_x']['value'],.75)
            self.assertAlmostEqual(frame['faces'][0]['signals']['gaze_y']['value'],.25)
            self.assertIn('no calibration',self.core.reasons['pupil'])

    def test_v12_profile_migration_preserves_other_fits_and_inert_pupil_fit(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x=AxisCalibration(-15,0,15,endpoint_tolerance=.05)
        self.core.eyes={'left':EyeCalibration(.04,.25,.5)}
        self.core.pupil_model=pupil_fixture()
        original=self.core.export_calibration()
        self.assertEqual(original['version'],13)
        old=deepcopy(original);old.update(version=12,algorithm='head-compensated-pupils-v12')
        self.core.load_calibration(old)
        self.assertEqual(self.core.export_calibration(),original)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json';self.session.save_profile(path)
            self.session.lab.processor.armed=True
            self.session.load_profile(path)
            self.assertEqual(self.core.export_calibration(),original)
            self.assertFalse(self.session.lab.processor.armed)
        for update in ({'slopes':[[float('nan'),0],[0,0]]},{'checks':{}},{'reference_pose':[0,0,True]}):
            bad=deepcopy(old);bad['pupil']['calibration'].update(update)
            with self.assertRaises(ValueError):self.core.load_calibration(bad)
            self.assertEqual(self.core.export_calibration(),original)

    def test_guide_commands_retired_and_closure_loss_stale_still_stop(self):
        before=self.core.export_calibration()
        for name in ('start_pupil_guide','present_pupil_step','retry_pupil_step','reset_pupils'):
            with self.assertRaises(ValueError):self.session.detector_command(name)
        with self.assertRaises(ValueError):self.session.detector_command('start_movement_guide','pupil')
        self.assertEqual(self.core.export_calibration(),before)
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.session.lab.action({'action':'arm'});self.feed()
        self.assertTrue(self.session.lab.processor.enabled)
        for _ in range(12):self.feed(pupil_x=.8)
        self.assertGreater(self.session.lab.state()['snapshot']['pointer_x'],.5)
        self.feed(left_closed=True)
        snap=self.session.lab.state()['snapshot']
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.feed(blank=True);self.feed()
        self.assertFalse(self.session.lab.processor.armed)
        self.session.lab.action({'action':'arm'});self.feed()
        self.now+=300;self.session.lab.step(self.now)
        self.assertFalse(self.session.lab.processor.armed)

    def test_uncalibrated_raw_pupils_reach_compiled_driver_without_head_pose(self):
        from Drivers.output import default_library
        library=Path(os.environ.get('FID_LIBRARY',default_library()))
        if not library.is_file():self.skipTest('Build Drivers or set FID_LIBRARY')
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.session.configure_output('dry-run',library)
        self.session.lab.action({'action':'arm'});self.feed(missing_pose=True)
        self.assertTrue(self.session.lab.state()['output']['enabled'])
        for _ in range(20):self.feed(missing_pose=True,pupil_x=.8,pupil_y=.25)
        state=self.session.lab.state()
        self.assertIsNone(state['output']['error'])
        self.assertGreater(state['snapshot']['pointer_x'],.5)
        self.assertLess(state['snapshot']['pointer_y'],.5)
        self.assertGreater(state['output']['event_counts'].get(1,0),0)
        self.assertTrue(all(event['type']==1 for event in self.session.lab.output.events))
        self.feed(left_closed=True,missing_pose=True)
        snap=self.session.lab.state()['snapshot']
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.session.lab.action({'action':'stop'})
        self.assertFalse(self.session.lab.state()['output']['enabled'])

    def test_raw_eye_fixation_reaches_screen_destination_and_does_not_drift(self):
        from Drivers.output import default_library
        library=Path(os.environ.get('FID_LIBRARY',default_library()))
        if not library.is_file():self.skipTest('Build Drivers or set FID_LIBRARY')
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.session.configure_output('dry-run',library)
        self.session.lab.action({'action':'arm'})
        self.feed(missing_pose=True,pupil_x=.65,pupil_y=.375)
        pointer=self.session.lab.state()['message']['pointer']
        self.assertEqual((pointer['mode'],pointer['speed']),('target',1))
        self.assertAlmostEqual(pointer['x'],.8);self.assertAlmostEqual(pointer['y'],.25)
        expected=[pointer['x'],pointer['y']]
        deadline=time.monotonic()+3
        while not self.session.lab.output.status().target_reached and time.monotonic()<deadline:
            time.sleep(.01);self.feed(missing_pose=True,pupil_x=.65,pupil_y=.375)
        self.assertTrue(self.session.lab.output.status().target_reached)
        self.session.lab.output.collect()
        count=self.session.lab.output.counts[1]
        for i in range(25):
            time.sleep(.01)
            self.feed(missing_pose=True,pupil_x=.65+(.0005 if i%2 else -.0005),pupil_y=.375)
        output=self.session.lab.state()['output']
        self.assertEqual(output['pointer_position'],expected)
        self.assertEqual(output['event_counts'][1],count)
        self.assertIsNone(output['error'])
        self.feed(left_closed=True)
        self.assertEqual(self.session.lab.state()['message']['pointer']['speed'],0)
        time.sleep(.04)
        self.assertEqual(self.session.lab.output.snapshot()['pointer_position'],expected)

    def test_default_pupils_reach_all_four_compiled_driver_corners(self):
        from Drivers.output import default_library
        library=Path(os.environ.get('FID_LIBRARY',default_library()))
        if not library.is_file():self.skipTest('Build Drivers or set FID_LIBRARY')
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        self.session.lab.settings({'runtime':{'pointer_speed':2500}})
        self.session.configure_output('dry-run',library)
        self.session.lab.action({'action':'arm'});self.feed()
        # Synthetic downward iris movement is only .009 eye widths here. No
        # detector re-fit, head pose, or extreme eyelid movement is required.
        for x,y,expected in ((.2,.545,(0,1)),(.8,.545,(1,1)),(.8,.2,(1,0)),(.2,.2,(0,0))):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                self.feed(missing_pose=True,pupil_x=x,pupil_y=y)
                output=self.session.lab.output.snapshot()
                if output['target_reached'] and output['pointer_position']==list(expected):break
                time.sleep(.01)
            self.assertEqual(output['pointer_position'],list(expected))
            self.assertTrue(output['target_reached'])
            self.assertIsNone(output['error'])
            count=output['event_counts'][1]
            for _ in range(8):
                time.sleep(.01);self.feed(missing_pose=True,pupil_x=x,pupil_y=y)
            self.assertEqual(self.session.lab.output.snapshot()['event_counts'][1],count)

    def test_face_profile_cannot_restore_old_pointer_filters_in_either_mapping(self):
        self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        before=self.core.export_calibration()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old-response.json';self.session.save_profile(path)
            data=json.loads(path.read_text())
            data['processing']['pointer']['smoothing_ms']=200
            data['processing']['interpolation_ms']=100
            path.write_text(json.dumps(data))
            for identity in ('gaming-keyboard-mouse-1','mouse-test'):
                self.session.lab.select_mapping(identity)
                selected=self.session.lab.state()['mapping']
                selected['pointer_down_gain']=5
                selected['target_smoothing_ms']=12
                selected['response']['pointer']['smoothing_ms']=17
                if identity=='mouse-test':selected['head_motion']['speed_gain']=.5
                self.session.lab.update_mapping(selected)
                self.session.lab.action({'action':'arm'});self.feed()
                self.session.load_profile(path)
                pointer=self.session.lab.processor.pointer
                self.assertEqual(pointer.config.smoothing_ms,12 if identity.startswith('gaming') else 17)
                self.assertEqual(pointer.down_gain,5)
                self.assertEqual(self.session.lab.state()['mapping']['head_motion'],selected['head_motion'])
                self.assertEqual(self.session.lab.state()['mapping']['head_wink_clicks'],selected['head_wink_clicks'])
                state=self.session.lab.state()
                self.assertEqual(state['snapshot']['diagnostics']['pointer_interpolation_ms'],0)
                self.assertFalse(state['snapshot']['armed'])
                self.assertEqual(self.core.export_calibration(),before)

    def test_incompatible_profile_freshness_cannot_partially_replace_detector(self):
        self.session.lab.select_mapping('gaming-keyboard-mouse-1')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'short-age.json';self.session.save_profile(path)
            data=json.loads(path.read_text())
            data['processing'].update(stale_ms=80,interpolation_ms=0)
            path.write_text(json.dumps(data))
            self.core.head=AxisCalibration(-12,0,12,endpoint_tolerance=.05)
            before=self.core.export_calibration()
            mapping=self.session.lab.state()['mapping'];mapping['target_interpolation_ms']=100
            self.session.lab.update_mapping(mapping)
            with self.assertRaisesRegex(ValueError,'Target interpolation'):
                self.session.load_profile(path)
            self.assertEqual(self.core.export_calibration(),before)
            self.assertFalse(self.session.lab.processor.armed)

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_native_pupil_panel_displays_raw_values_without_guide_controls(self):
        import tkinter as tk
        from types import SimpleNamespace
        from Vision.lab import DetectionLab
        from App.desktop import CalibrationBridge
        root=tk.Tk();self.addCleanup(root.destroy)
        errors=[];root.report_callback_exception=lambda *error:errors.append(error)
        root.geometry('1230x910')
        container=tk.Frame(root);container.pack(fill='both',expand=True)
        ui=DetectionLab(root,SimpleNamespace(demo=True),runtime=CalibrationBridge(self.session),container=container)
        self.addCleanup(ui.close_panels)
        ui.calibration_tabs.select(ui.pupil_tab);root.update();ui.tick()
        self.assertFalse(hasattr(ui.pupil_panel,'start'))
        self.assertFalse(hasattr(ui.pupil_panel,'retry'))
        self.assertFalse(hasattr(ui.pupil_panel,'reset'))
        self.assertIn('no calibration needed',ui.pupil_panel.message.get())
        self.feed(pupil_x=.75);ui.tick();root.update()
        self.assertIn('Normalized X/Y: (0.750, 0.500)',ui.pupil_details.get())
        self.assertNotIn('Compensated',ui.pupil_details.get())
        self.assertTrue(ui.pupil_panel.canvas.find_withtag('pupil-cell'))
        self.assertIsNone(root.grab_current())
        self.assertEqual(errors,[])
