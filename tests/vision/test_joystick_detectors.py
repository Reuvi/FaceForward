"""Synthetic algorithm checks; no claim of human tongue/gaze accuracy."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    import numpy as np
    from Vision.demo_detection import demo_image
    from Vision.features import DetectionConfig, analyze_features
    from Vision.pupil import measure, normalize, settings
    from Vision.tongue import mouth_crop
    from Vision.tongue_segment import SegmentedTongueModel, decode_mask


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class PupilMeasurements(unittest.TestCase):
    def reading(self, **kwargs):
        b, obs = demo_image(**kwargs)
        return measure(obs[0], analyze_features(b, obs[0], DetectionConfig()))

    def test_direction_units_and_polarity(self):
        for x,y in ((.5,.5),(0,.5),(1,.5),(.5,0),(.5,1)):
            r=self.reading(pupil_x=x,pupil_y=y)
            self.assertIsNotNone(r.xy,r.reason)
            self.assertAlmostEqual(r.xy[0],(x-.5)*.4)
            self.assertAlmostEqual(r.xy[1],(y-.5)*.2)

    def test_one_eye_closure_is_not_a_new_joystick_position(self):
        for kwargs in ({"left_closed":True},{"right_closed":True},{"natural_blink":True}):
            r=self.reading(**kwargs)
            self.assertIsNone(r.xy)
        self.assertTrue(self.reading(left_closed=True).eyes['right']['valid'])

    def test_missing_iris_blur_and_disagreement(self):
        b, obs=demo_image(); o=obs[0]
        self.assertIsNone(measure(o,analyze_features(np.zeros_like(b),o,DetectionConfig())).xy)
        points=list(o.points)
        for i in (474,475,476,477):points[i]=(points[i][0]+24,points[i][1])
        o.points=tuple(points)
        self.assertIn('disagree',measure(o,analyze_features(b,o,DetectionConfig())).reason)
        o.points=o.points[:468]
        self.assertIsNone(measure(o,analyze_features(b,o,DetectionConfig())).xy)

    def test_fixed_normalization_clamps_without_training_or_history(self):
        for raw, want in (((0,0),(.5,.5)), ((-.2,-.1),(0,0)), ((.2,.1),(1,1)),
                          ((.1,-.05),(.75,.25)), ((-.3,.2),(0,1))):
            self.assertEqual(normalize(raw,settings()),want)
        for raw in (None, (float('nan'),0), (0,float('inf'))):
            self.assertIsNone(normalize(raw,settings()))
        options=settings(dict(settings(), x_sensitivity=2, y_sensitivity=.5))
        self.assertEqual(normalize((.1,.1),options),(1,.75))

    def test_settings_validate_and_do_not_share_defaults(self):
        first=settings();first['x_sensitivity']=3
        self.assertEqual(settings()['x_sensitivity'],1)
        for value in (True, 0, .24, 4.01, float('nan'), float('inf')):
            with self.assertRaises(ValueError):settings(dict(settings(), x_sensitivity=value))
        for value in ({}, dict(settings(), extra=1), dict(settings(), measurement='old')):
            with self.assertRaises(ValueError):settings(value)

    def test_direction_survives_translation_scale_roll_and_missing_pose(self):
        import math
        b, obs=demo_image(pupil_x=.75,pupil_y=.25);o=obs[0]
        features=analyze_features(b,o,DetectionConfig());original=measure(o,features).xy
        angle=math.radians(20)
        o.points=tuple((30+1.4*(x*math.cos(angle)-y*math.sin(angle)),
                        45+1.4*(x*math.sin(angle)+y*math.cos(angle))) for x,y in o.points)
        o.rotation=None
        changed=measure(o,features)
        self.assertIsNone(changed.pose)
        for actual,want in zip(changed.xy,original):self.assertAlmostEqual(actual,want)


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class NeuralTongue(unittest.TestCase):
    def outputs(self):
        return [np.zeros((1,37,8400),np.float32),np.zeros((1,32,160,160),np.float32)]

    def test_absence_and_malformed_outputs(self):
        mask,score,reason=decode_mask(self.outputs())
        self.assertIsNone(mask);self.assertEqual(score,0)
        with self.assertRaises(ValueError):decode_mask([np.zeros((1,)),np.zeros((1,))])
        outputs=self.outputs();outputs[0][0,0,0]=np.nan
        with self.assertRaises(ValueError):decode_mask(outputs)

    def test_box_mask_projection_and_nms(self):
        outputs=self.outputs();p,proto=outputs
        p[0,:5,0]=[320,320,320,320,.9];p[0,5,0]=1
        proto[0,0,40:120,40:120]=1
        p[0,:,1]=p[0,:,0];p[0,4,1]=.8
        mask,score,_=decode_mask(outputs)
        self.assertAlmostEqual(score,.9,places=5)
        self.assertEqual(np.count_nonzero(mask),80*80)
        self.assertEqual(mask[80,80],255);self.assertEqual(mask[0,0],0)
        # A second distant supported box must not choose arbitrarily.
        p[0,:5,2]=[60,60,80,80,.85];p[0,5,2]=1
        mask,score,reason=decode_mask(outputs)
        self.assertIsNone(mask);self.assertIn('Multiple',reason)

    def test_missing_model_fails_closed_without_repeated_loading(self):
        b,o=demo_image(tongue=True);c=DetectionConfig();crop,_=mouth_crop(b,o[0],c)
        model=SegmentedTongueModel('/no/such/model.onnx')
        with patch.object(model,'_load',side_effect=ValueError('missing')) as load:
            for _ in range(3):self.assertIsNone(model.detect(crop,c).xy)
            self.assertEqual(load.call_count,1)
        self.assertIn('missing',model.report['error'])

    @unittest.skipUnless(os.environ.get('TONGUE_MODEL_PATH'), 'explicit local-model smoke')
    def test_real_local_model_runs_without_network(self):
        b,o=demo_image();c=DetectionConfig();crop,_=mouth_crop(b,o[0],c)
        model=SegmentedTongueModel(Path(os.environ['TONGUE_MODEL_PATH']))
        model.detect(crop,c)
        self.assertIsNotNone(model.session)
        self.assertIsNone(model.report['error'])
        self.assertGreater(model.report['inference_ms'],0)
