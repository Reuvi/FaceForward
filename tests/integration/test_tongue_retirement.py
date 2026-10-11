"""Retired input cannot re-enter the live path through files, settings or UI."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in ('cv2', 'numpy'))
if AVAILABLE:
    from App.mouse_runtime import MouseSession
    from Vision.calibration import AxisCalibration, EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope, invalid


def legacy_profile(current, version):
    algorithms = ('lid-gap-head-y-lab-color-v1', 'guided-lid-gap-head-y-lab-color-v2',
                  'frame-wink-eye-head-tongue-v3', 'personal-head-tongue-ranges-v4',
                  'color-tongue-tip-v5', 'tongue-segmentation-pupil-joystick-v6',
                  'independent-head-axes-v7', 'direct-mediapipe-pupils-v8',
                  'lip-boundary-head-reliability-v9', 'fixed-pupil-matrix-v10', 'eyes-head-pupils-v11')
    data = deepcopy(current)
    if version == 11:
        data.update(version=11, algorithm=algorithms[10], pupil={'measurement':'mediapipe_iris_direction_v3'})
        return data
    data.update(version=version, algorithm=algorithms[version-1],
                tongue={'positive': [[40,160,140]], 'negative': [[20,100,100]], 'radius': 6, 'margin': 4})
    if version < 3:
        data.pop('winks')
    if version == 1:
        for eye in data['eyes'].values():
            eye.pop('closed_limit'); eye.pop('open_limit')
    if version >= 4:
        fit = dict(low=.2, center=.5, high=.8, endpoint_tolerance=.05) if version == 4 else dict(low=-.2, center=0, high=.2, endpoint_tolerance=.05)
        data['tongue_range'] = {key: dict(fit) for key in ('x', 'y')}
    if version >= 5:
        data['tongue_measurement'] = 'color_tip_mouth_width_v1'
    if version < 6:
        data.pop('pupil')
    elif version < 8:
        data['pupil'] = None
    elif version < 10:
        data['pupil'] = dict(measurement='mediapipe_iris_direction_v2', x_sensitivity=2, y_sensitivity=.5)
    elif version == 10:
        data['pupil'] = dict(measurement='mediapipe_iris_direction_v3')
    if version < 7:
        data.pop('head_x')
    return data


@unittest.skipUnless(AVAILABLE, 'pixel dependencies required')
class TongueRetirement(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.session = MouseSession(clock=lambda: self.now)
        self.addCleanup(self.session.close)
        self.session.mode = 'detector-demo'
        self.runtime = self.session.ensure_detector_runtime()
        self.core = self.runtime.workbench
        self.core.eyes = {'left': EyeCalibration(.04,.25,.5)}
        self.core.head = AxisCalibration(-12,0,12,endpoint_tolerance=.05)
        self.core.head_x = AxisCalibration(-15,0,15,endpoint_tolerance=.05)

    def feed(self, sequence, **controls):
        self.now += 25
        pixels, faces = demo_image(**controls)
        return self.session.deliver_detection(CapturedImage(Envelope('retired',sequence,self.now),pixels),faces,preview=False)

    def test_every_capture_has_only_active_diagnostics_and_no_tongue_work(self):
        from tests.vision.pupil_fixture import pupil_fixture
        self.core.pupil_model = pupil_fixture()
        with patch('Vision.tongue.mouth_crop', side_effect=AssertionError('retired crop')), \
             patch('Vision.tongue_worker.TongueWorker', side_effect=AssertionError('retired worker')):
            for i in range(30):
                frame = self.feed(i, tongue=True, head_x=.3 if i % 2 else .7, pupil_x=.75)
                values = frame['faces'][0]['signals']
                self.assertEqual(values['tongue_x'], invalid())
                self.assertEqual(values['tongue_y'], invalid())
                self.assertTrue(all(values[k]['valid'] for k in ('head_x','head_y','gaze_x','gaze_y','left_eye_open')))
                self.assertEqual(frame['eye_intent']['sequence'], i)
                self.assertEqual(frame['pupil_matrix']['sequence'], i)
                self.assertFalse(any('tongue' in key for key in frame))
            # The later mouth-button request permits only these scalar fields;
            # no tongue/crop/model diagnostics are restored.
            self.assertFalse(any('tongue' in key or ('mouth' in key and key not in ('mouth_open','mouth_score'))
                                 for key in self.core.trace[-1]))
        self.assertEqual(len(self.core.trace),30)
        self.assertFalse(hasattr(self.core, 'async_tongue'))
        self.assertFalse(hasattr(self.core, 'tongue_model'))
        self.assertFalse(any('tongue' in key or 'mouth' in key for key in self.runtime.snapshot()))
        self.assertEqual(self.runtime.snapshot()['trace'], self.session.state(include_detector=True)['detector']['trace'])
        self.assertFalse(self.runtime.demo_input()['tongue'])

    def test_all_legacy_versions_keep_compatible_fits_and_drop_retired_fields(self):
        baseline = self.core.export_calibration()
        for version in range(1,12):
            with self.subTest(version=version):
                old = legacy_profile(baseline,version)
                self.core.load_calibration(old)
                saved = self.core.export_calibration()
                self.assertEqual(saved['version'],13)
                self.assertEqual(saved['eyes'],baseline['eyes'])
                self.assertEqual(saved['head'],baseline['head'])
                self.assertEqual(saved['head_x'],baseline['head_x'] if version>=7 else None)
                self.assertFalse(any('tongue' in key for key in saved))
                self.assertFalse(any('tongue' in key or 'mouth' in key for key in saved['settings']))
                self.assertFalse(hasattr(self.core, 'tongue_model'))

    def test_both_historical_v10_pupil_identities_migrate_without_losing_other_fits(self):
        baseline = self.core.export_calibration()
        for identity in ('mediapipe_iris_direction_v2','mediapipe_iris_direction_v3'):
            old = legacy_profile(baseline,10)
            old['pupil']['measurement'] = identity
            self.core.load_calibration(old)
            self.assertEqual(self.core.export_calibration(),baseline)
            self.assertIsNone(self.core.pupil_model)
        old['pupil']['measurement'] = 'unrecognized-geometry'
        with self.assertRaises(ValueError):
            self.core.load_calibration(old)
        self.assertEqual(self.core.export_calibration(),baseline)

    def test_neural_and_lip_profiles_validate_then_discard_without_loading_models(self):
        from Vision.tongue_segment import MEASUREMENT, MODEL_SHA256
        from Vision.lip_boundary import MEASUREMENT as LIP_MEASUREMENT, ALGORITHM
        baseline = self.core.export_calibration()
        for measurement, identity in ((MEASUREMENT,dict(backend='yolov8n-seg',sha256=MODEL_SHA256)),
                                       (LIP_MEASUREMENT,dict(backend='lip-boundary',algorithm=ALGORITHM))):
            old = legacy_profile(baseline,10)
            old.update(tongue_measurement=measurement,tongue=identity)
            with patch('Vision.tongue_worker.TongueWorker',side_effect=AssertionError('worker created')):
                self.core.load_calibration(old)
            self.assertEqual(self.core.export_calibration(),baseline)
            broken=deepcopy(old);broken['tongue']['backend']='unknown'
            with self.assertRaises(ValueError): self.core.load_calibration(broken)
            self.assertEqual(self.core.export_calibration(),baseline)

    def test_old_pointer_profile_and_settings_use_pupils_and_stay_disarmed(self):
        from Processing.mouse.profiles import read_profile, write_profile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profile.json'
            self.session.save_profile(path)
            data=read_profile(path)
            data['processing']['pointer_source']='tongue'
            data['processing']['pointer']['smoothing_ms']=135
            data['detector']=legacy_profile(data['detector'],10)
            write_profile(path,data)
            self.session.lab.processor.armed=True
            self.session.load_profile(path)
            self.assertFalse(self.session.lab.processor.armed)
            self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
            self.assertEqual(self.session.lab.state()['config']['pointer']['smoothing_ms'],135)
            self.feed(1,pupil_x=.8)
            self.assertIsNotNone(self.session.lab.processor.sample.pointer)
            self.assertIsNotNone(self.core.pupil.xy)
            self.assertIsNone(self.core.pupil_model)
            self.session.lab.settings({'config':data['processing']})
            self.assertEqual(self.session.lab.state()['config']['pointer_source'],'gaze')
            self.session.save_profile(path)
            self.assertEqual(read_profile(path)['detector']['version'],13)
            self.assertEqual(read_profile(path)['processing']['pointer_source'],'gaze')

    def test_retired_commands_cannot_change_calibration(self):
        self.feed(0)
        baseline=self.core.export_calibration()
        for name in ('load_tongue_model','use_lip_boundary','freeze_mouth','mark_tongue','fit_tongue','reset_tongue','retry_tongue_step'):
            with self.assertRaises(ValueError):self.session.detector_command(name)
            self.assertEqual(self.core.export_calibration(),baseline)
        with self.assertRaises(ValueError):self.session.detector_command('start_movement_guide','tongue')
        with self.assertRaises(ValueError):self.session.detector_command('collect','tongue_absent')
        self.assertEqual(self.core.export_calibration(),baseline)

    def test_fresh_runtime_and_current_profile_do_not_import_tongue_modules(self):
        code='''
import json, sys
from Vision.lab_runtime import LabRuntime
from Vision.demo_detection import demo_image
from Vision.capture import CapturedImage
from Vision.signals import Envelope
runtime=LabRuntime(clock=lambda:1000)
pixels,faces=demo_image()
runtime.ingest(CapturedImage(Envelope('test',0,1000),pixels),faces,preview=False)
core=runtime.workbench
core.load_calibration(core.export_calibration())
runtime.close()
print(json.dumps([key for key in sys.modules if key.startswith(('Vision.tongue','Vision.lip_boundary'))]))
'''
        result=subprocess.run([sys.executable,'-c',code],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[])

    @unittest.skipUnless(os.environ.get('RUN_TK_TESTS')=='1','native Tk check')
    def test_integrated_source_and_transfer_settings_offer_only_pupils(self):
        import tkinter as tk
        from types import SimpleNamespace
        from App.desktop import IntegratedDesktop
        root=tk.Tk();self.addCleanup(root.destroy)
        errors=[];root.report_callback_exception=lambda *error:errors.append(error)
        options=SimpleNamespace(source='detector-demo',fps=30,camera_id=0,model='unused',replay=None,no_preview=True)
        with patch.object(IntegratedDesktop,'start_source'),patch('Vision.eye_view.CalibrationSounds'),patch('Vision.movement_view.CalibrationSounds'):
            ui=IntegratedDesktop(root,self.session,options)
            self.addCleanup(ui.calibration_ui.close_panels) if ui.calibration_ui else None
            self.feed(0,pupil_x=.75)
            ui.refresh_vision();root.update()
            self.assertNotIn('tongue_x',ui.mapping_page.table.get_children())
            self.assertNotIn('tongue_y',ui.mapping_page.table.get_children())
            self.assertNotIn('Tongue',ui.raw_ratios.get())
            self.assertEqual(ui.lab.state()['config']['pointer_source'],'gaze')
            self.assertNotIn('config.pointer_source',ui.setting_vars)
            self.assertFalse(hasattr(ui,'pointer_picker'))
            self.assertEqual(errors,[])
            ui.closed=True
