import importlib.util
import unittest

AVAILABLE=all(importlib.util.find_spec(k) for k in ('cv2','numpy'))
if AVAILABLE:
    from Vision.calibration import EyeCalibration
    from Vision.demo_detection import demo_image
    from Vision.features import Feature
    from Vision.pupil import measure


@unittest.skipUnless(AVAILABLE,'Vision dependencies required')
class PersonalPupilQualityTests(unittest.TestCase):
    def reading(self, ratio=.12, blink=.5, fits=True, quality=1, **values):
        _,observations=demo_image(left_ratio=ratio,right_ratio=ratio,**values)
        observation=observations[0]
        for side in ('left','right'):observation.expressions['eyeBlink'+side.title()]=blink
        features={side:Feature(ratio,quality) for side in ('left','right')}
        calibration=EyeCalibration.fit_guided([.04]*12,[[.12]*12,[.25]*12],min_separation=.015)
        return measure(observation,features,{s:calibration for s in features} if fits else None)

    def test_personal_open_geometry_recovers_narrow_eyes_without_changing_coordinates(self):
        reading=self.reading(pupil_x=.75)
        self.assertIsNotNone(reading.xy)
        self.assertAlmostEqual(reading.xy[0],.1)
        self.assertEqual(reading.eyes['left']['aperture_source'],'personal open geometry')
        self.assertIsNone(self.reading(fits=False,pupil_x=.75).xy)

    def test_closed_uncertain_strong_blink_and_bad_image_are_still_invalid(self):
        for values in ({'ratio':.04,'blink':.1},{'ratio':.075,'blink':.1},
                       {'blink':.85},{'quality':0},{'blink':float('nan')}):
            self.assertIsNone(self.reading(**values).xy)

    def test_personal_evidence_is_same_eye_only_and_both_irises_still_required(self):
        _,observations=demo_image(left_ratio=.12,right_ratio=.12)
        features={s:Feature(.12,1) for s in ('left','right')}
        fit=EyeCalibration.fit_guided([.04]*12,[[.12]*12],min_separation=.015)
        reading=measure(observations[0],features,{'left':fit})
        self.assertTrue(reading.eyes['left']['valid'])
        self.assertFalse(reading.eyes['right']['valid'])
        self.assertIsNone(reading.xy)

    def test_no_fit_required_for_clear_eyes_and_coordinates_stay_compatible(self):
        for x,y in ((.5,.5),(.25,.25),(.75,.75)):
            old=self.reading(ratio=.25,blink=.08,fits=False,pupil_x=x,pupil_y=y)
            new=self.reading(ratio=.25,blink=.08,fits=True,pupil_x=x,pupil_y=y)
            self.assertIsNotNone(old.xy)
            self.assertEqual(old.xy,new.xy)
            self.assertEqual(old.quality,new.quality)
