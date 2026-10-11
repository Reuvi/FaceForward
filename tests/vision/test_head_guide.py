"""Selective Head Y corrections retain evidence but invalidate dependent checks."""
from copy import deepcopy
import unittest

from Vision.calibration import AxisCalibration
from Vision.features import DetectionConfig
from Vision.head_guide import HeadPitchGuide


class HeadPitchGuideTests(unittest.TestCase):
    def setUp(self):
        self.config=DetectionConfig(settle_ms=50,collect_ms=300,movement_rest_ms=80,min_samples=5)
        self.now=1000.
        self.positions=dict(neutral=0.,up=-12.,down=16.)

    def finish_step(self, guide, *, value=None, usable=True):
        if guide.resting:
            guide.present(guide.index,self.now,'rest')
            self.now+=81;guide.advance(self.now)
        guide.present(guide.index,self.now,'prepare')
        start=guide.start_ms
        role,name,_=guide.steps[guide.index]
        value=self.positions[name] if value is None else value
        for n in range(12):guide.feed(start+n*25,(value,),usable)
        self.now=start+301
        guide.feed(self.now,(value,),usable)
        return role,name

    def finish(self, guide):
        steps=[]
        for _ in range(10):
            if not guide.active:break
            steps.append(self.finish_step(guide))
        self.assertTrue(guide.passed,guide.report)
        return steps

    def test_redo_accepted_pose_keeps_others_and_rechecks_changed_mapping(self):
        guide=HeadPitchGuide(self.config)
        self.finish_step(guide);self.finish_step(guide)
        neutral=deepcopy(guide.groups['neutral'])
        guide.redo('train','up')
        self.assertEqual(guide.groups,{'neutral':neutral})
        self.assertEqual([(r,n) for r,n,_ in guide.steps],
                         [('train','up'),('train','down'),('check','neutral'),('check','up'),('check','down')])
        self.positions['up']=-18
        self.finish(guide)
        self.assertEqual(guide.fits['y'].low,-18)
        old_down=deepcopy(guide.groups['down'])
        guide.redo('train','neutral')
        self.assertEqual(guide.checks,{})
        self.assertEqual(guide.fits,{})
        self.assertEqual(guide.groups['down'],old_down)
        self.positions['neutral']=2
        steps=self.finish(guide)
        self.assertEqual(steps,[('train','neutral'),('check','neutral'),('check','up'),('check','down')])
        self.assertEqual(guide.fits['y'].center,2)

    def test_saved_fit_supplies_references_without_fabricating_samples(self):
        fit=AxisCalibration(-12,0,16,endpoint_tolerance=.05)
        guide=HeadPitchGuide(self.config,existing=fit)
        guide.redo('train','up')
        self.assertEqual(guide.groups,{})
        self.assertEqual(guide.references,dict(neutral=0,down=16))
        self.positions['up']=-20
        self.finish(guide)
        self.assertEqual(set(guide.groups),{'up'})
        self.assertEqual(guide.state(self.now)['reference_sources'],dict(neutral='saved',up='captured',down='saved'))
        self.assertEqual(guide.fits['y'],AxisCalibration(-20,0,16,endpoint_tolerance=.05))

    def test_failed_check_retry_keeps_fit_and_prior_checks(self):
        guide=HeadPitchGuide(self.config)
        for _ in range(4):self.finish_step(guide)
        previous=deepcopy(guide.groups);fit=guide.fits['y'];checks=deepcopy(guide.checks)
        self.finish_step(guide,value=0)
        self.assertFalse(guide.active);self.assertFalse(guide.passed)
        guide.retry()
        self.assertEqual(guide.groups,previous);self.assertEqual(guide.fits['y'],fit)
        self.assertEqual(guide.checks,checks)
        self.assertEqual(self.finish(guide),[('check','up'),('check','down')])
        guide.redo('check','neutral')
        self.assertEqual(self.finish(guide),[('check','neutral')])
        self.assertEqual(guide.groups,previous)

    def test_active_retry_excludes_old_window_and_duplicate_samples(self):
        guide=HeadPitchGuide(self.config)
        guide.present(0,self.now,'prepare')
        guide.feed(self.now+50,(99.,),True)
        self.now+=100
        guide.retry()
        self.assertIsNone(guide.start_ms);self.assertEqual(guide.values,[])
        guide.feed(self.now,(99.,),True);self.assertEqual(guide.values,[])
        guide.present(0,self.now,'prepare')
        guide.feed(self.now+49,(99.,),True);self.assertEqual(guide.values,[])
        guide.feed(self.now+50,(0.,),True)
        guide.feed(self.now+50,(99.,),True)
        self.assertEqual(guide.values,[(0.,)])

    def test_invalid_selection_or_missing_fit_does_not_change_capture(self):
        guide=HeadPitchGuide(self.config)
        guide.present(0,self.now,'prepare')
        before=deepcopy(guide.__dict__)
        for role,name in (('train','left'),('other','up'),('check','up')):
            with self.assertRaises(ValueError):guide.redo(role,name)
            self.assertEqual(guide.__dict__,before)
        self.finish(guide)
        with self.assertRaises(ValueError):guide.retry()

    def test_saved_fit_keeps_reversed_pitch_sign_and_rejects_overlapping_capture(self):
        guide=HeadPitchGuide(self.config,existing=AxisCalibration(12,0,-16,endpoint_tolerance=.05))
        guide.redo('train','down');self.positions=dict(neutral=0,up=12,down=-22)
        self.finish(guide)
        self.assertEqual(guide.fits['y'].normalize(-22),1)
        guide.redo('train','up')
        self.finish_step(guide,value=1)
        self.assertFalse(guide.active);self.assertFalse(guide.passed)
        self.assertIn('insufficient range',guide.report)
        self.assertEqual(guide.fits,{})

    def test_failed_check_cannot_be_skipped_by_selecting_a_different_check(self):
        guide=HeadPitchGuide(self.config)
        for _ in range(4):self.finish_step(guide)
        self.finish_step(guide,value=0)  # Up failed; neutral passed.
        guide.redo('check','neutral')
        self.assertEqual(self.finish(guide),[('check','neutral'),('check','up'),('check','down')])

    def test_loaded_fit_check_only_retry_remains_one_check(self):
        guide=HeadPitchGuide(self.config,existing=AxisCalibration(-12,0,16,endpoint_tolerance=.05))
        guide.redo('check','up')
        self.finish_step(guide,value=0)
        guide.retry()
        self.assertEqual(self.finish(guide),[('check','up')])
        self.assertEqual(guide.groups,{})
