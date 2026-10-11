"""Synthetic checks for compensation; these do not measure human accuracy."""
from copy import deepcopy
import unittest

import importlib.util
AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))
if AVAILABLE:
    from Vision.features import DetectionConfig
    from Vision.pupil_calibration import fit_pose, fit_endpoints, normalize, validate_model, CHECK_NAMES
    from Vision.pupil_guide import PupilGuide



def sample(x=0, y=0, yaw=0, pitch=0, roll=0):
    return (x+.003*yaw+.001*pitch, y-.0005*yaw+.002*pitch, yaw, pitch, roll)


def model_fixture():
    groups = {name:[sample(yaw=yaw, pitch=pitch)]*12 for name, yaw, pitch in
              (("center",0,0),("head_left",-12,0),("head_right",12,0),("head_up",0,-10),("head_down",0,10))}
    model = fit_pose(groups)
    groups.update({name:[sample(x,y)]*12 for name,x,y in
                   (("left",-.2,0),("right",.15,0),("up",0,-.1),("down",0,.04))})
    model = fit_endpoints(model, groups)
    model["checks"] = {name:dict(samples=12,matched_fraction=1.) for name in CHECK_NAMES}
    return validate_model(model)


@unittest.skipUnless(AVAILABLE, "Vision dependencies required")
class PupilCalibrationTests(unittest.TestCase):
    def test_asymmetric_personal_limits_and_intermediate_values(self):
        model = model_fixture()
        for x,y,target in ((-.2,0,(0,.5)),(.15,0,(1,.5)),(0,-.1,(.5,0)),(0,.04,(.5,1)),
                           (-.1,.02,(.25,.75)),(1,1,(1,1))):
            values = sample(x,y,6,-4)
            result, corrected, _ = normalize(model, values[:2], values[2:])
            for a,b in zip(result,target):self.assertAlmostEqual(a,b)
            for a,b in zip(corrected,(x,y)):self.assertAlmostEqual(a,b)

    def test_fixed_target_remains_centered_with_unseen_head_angles(self):
        model = model_fixture()
        for yaw,pitch in ((-9,3),(5,-7),(11,8),(-8,-6)):
            values=sample(yaw=yaw,pitch=pitch)
            result,_,_=normalize(model,values[:2],values[2:])
            for v in result:self.assertAlmostEqual(v,.5)
            self.assertGreater(max(abs(v) for v in values[:2]),.005)

    def test_invalid_inputs_and_unsupported_pose_never_fabricate_center(self):
        model=model_fixture()
        for fit,xy,pose in ((None,(0,0),(0,0,0)),(model,None,(0,0,0)),(model,(0,0),None),
                            (model,(0,0),(30,0,0)),(model,(0,0),(0,30,0)),(model,(0,0),(0,0,20)),
                            (model,(0,0),(float('nan'),0,0)),(model,(float('nan'),0),(0,0,0)),
                            (model,(True,0),(0,0,0)),(model,(0,0),3)):

            result,corrected,reason=normalize(fit,xy,pose)
            self.assertIsNone(result);self.assertIsNone(corrected);self.assertTrue(reason)

    def test_profiles_reject_bad_numbers_shapes_identity_and_unchecked_fits(self):
        original=model_fixture()
        bads=[]
        for key,value in (("slopes",[[float('nan'),0],[0,0]]),("slopes",[[.04,0],[0,0]]),
                          ("pose_bounds",[[-1,1],[-1,1]]),("low",[0,0]),("high",[1,1]),
                          ("reference_pose",[0,0]),("checks",{}),("space","old")):
            bad=deepcopy(original);bad[key]=value;bads.append(bad)
        bad=deepcopy(original);bad['checks']['diagonal']['matched_fraction']=.89;bads.append(bad)
        for bad in bads:
            with self.assertRaises(ValueError):validate_model(bad)
        self.assertEqual(validate_model(original),original)

    def test_pose_fit_rejects_missing_coverage_and_inconsistent_target(self):
        for flat in (True,False):
            groups={name:[sample(yaw=yaw,pitch=pitch)]*12 for name,yaw,pitch in
                    (("center",0,0),("head_left",-12,0),("head_right",12,0),("head_up",0,-10),("head_down",0,10))}
            if flat:groups={name:[sample()]*12 for name in groups}
            else:groups['center']=[sample(.15,.15)]*12
            with self.assertRaises(ValueError):fit_pose(groups)

    def test_guide_prompt_windows_rest_retry_and_fresh_checks(self):
        config=DetectionConfig(settle_ms=40,collect_ms=300,movement_rest_ms=80,min_samples=5)
        guide=PupilGuide(config);now=1000
        guide.feed(now,sample(),True);self.assertEqual(guide.values,[])
        guide.present(5,now,'prepare');self.assertIsNone(guide.start_ms)
        failed=False
        while guide.active:
            state=guide.state(now)
            if state['waiting']:guide.present(guide.index,now,state['phase'])
            if guide.resting:
                before=len(guide.values);guide.feed(now,sample(1,1),True)
                self.assertEqual(len(guide.values),before)
                now+=81;guide.advance(now);continue
            start=guide.start_ms
            guide.feed(start-1,sample(1,1),True)
            self.assertEqual(guide.values,[])
            name=state['name']
            yaw,pitch={"head_left":(-12,0),"head_right":(12,0),"head_up":(0,-10),"head_down":(0,10),"diagonal":(6,5)}.get(name,(0,0))
            x,y={"left":(-.2,0),"right":(.15,0),"up":(0,-.1),"down":(0,.04)}.get(name,(0,0))
            bad=guide.index==6 and not failed
            for i in range(12):
                timestamp=start+i*25
                guide.feed(timestamp,sample(x,y,yaw,pitch),not bad)
                guide.feed(timestamp,sample(1,1),True) # Duplicate must not train.
            now=start+301;guide.feed(now,sample(),True)
            if bad:
                self.assertFalse(guide.active);self.assertFalse(guide.passed)
                self.assertEqual(guide.index,6);guide.retry();failed=True
        self.assertTrue(guide.passed,guide.report)
        self.assertTrue(failed)
        self.assertEqual(set(guide.checks),set(CHECK_NAMES))
        validate_model(guide.model)

    def test_neutral_head_cannot_pass_held_out_head_check(self):
        guide=PupilGuide(DetectionConfig(min_samples=5))
        guide.model=model_fixture();guide.index=9
        guide.values=[sample()]*12
        guide._finish()
        self.assertFalse(guide.passed);self.assertFalse(guide.active)
        self.assertIn('turn AND nod',guide.report)
