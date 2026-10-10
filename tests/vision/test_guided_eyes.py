"""Deterministic pose coverage, independent fits, timing and ambiguity behavior."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from Vision.calibration import EyeCalibration
from Vision.guided_eyes import GuidedEyes
from Vision.eye_scope import binary_segments


class GuidedEyeTests(unittest.TestCase):
    def setUp(self):
        self.config=SimpleNamespace(settle_ms=0,collect_ms=400,min_samples=8,eye_separation=.015)
        self.guide=GuidedEyes(self.config)
        self.now=1000

    def step(self, left=.25, right=.23, quality=1):
        guide=self.guide
        guide.present(guide.index,self.now)
        self.now=guide.start_ms
        for _ in range(16):
            features={s:SimpleNamespace(value=v,quality=quality) for s,v in (("left",left),("right",right))}
            guide.feed(self.now,features)
            self.now+=25
        guide.feed(self.now,{})

    def train(self, bad_right=False):
        for value in (.25,.21,.22,.28,.12):
            self.step(value,.04 if bad_right else value*.94)
        self.step(.04,.04)

    def test_multiple_open_poses_and_uncertain_gap(self):
        fit=EyeCalibration.fit_guided([.04]*20,[[v]*20 for v in (.25,.21,.22,.28,.12)],min_separation=.015)
        for ratio in (.12,.21,.25,.28):self.assertEqual(fit.classify(ratio,1)["value"],1)
        self.assertEqual(fit.classify(.04,1)["value"],0)
        self.assertFalse(fit.classify(.08,1)["valid"])
        self.assertEqual(fit.classify(fit.closed_limit,1)["value"],0)
        self.assertEqual(fit.classify(fit.open_limit,1)["value"],1)
        with self.assertRaises(ValueError):replace(fit,open_limit=None)
        with self.assertRaises(ValueError):replace(fit,closed_limit=fit.open_limit)

    def test_blinks_trimmed_within_pose_but_bad_open_pose_rejected(self):
        fit=EyeCalibration.fit_guided([.04]*20,[[.25]*18+[.04]*2,[.12]*20],min_separation=.015)
        self.assertEqual(fit.classify(.12,1)["value"],1)
        for groups in ([[.25]*20,[.04]*20],[[.25]*14+[.04]*6],[]):
            with self.assertRaises(ValueError):EyeCalibration.fit_guided([.04]*20,groups,min_separation=.015)

    def test_fresh_reopen_check_and_independent_partial_result(self):
        self.train(bad_right=True)
        self.assertTrue(self.guide.active)
        self.step()
        self.assertFalse(self.guide.active)
        self.assertEqual(set(self.guide.fits),{"left"})
        self.assertIn("right",self.guide.errors)
        self.assertEqual(self.guide.state(self.now)["passed"],1)

    def test_failed_reopen_does_not_publish_old_fit(self):
        self.train()
        self.step(.04,.23)
        self.assertEqual(set(self.guide.fits),{"right"})
        self.assertIn("reopen",self.guide.errors["left"])

    def test_prompt_acknowledgment_stale_and_duplicate_samples(self):
        feature={s:SimpleNamespace(value=.25,quality=1) for s in ("left","right")}
        self.guide.feed(5000,feature)
        self.assertEqual(self.guide.index,0)
        self.assertEqual(self.guide.values["left"],[])
        self.guide.present(1,5000)  # Stale UI instruction cannot start this step.
        self.assertIsNone(self.guide.start_ms)
        self.guide.present(0,5000)
        for t in (4900,5000,5000,4999):self.guide.feed(t,feature)
        self.assertEqual(len(self.guide.values["left"]),1)
        self.guide.feed(5400,{})
        self.assertIn("left",self.guide.errors)
        self.assertIsNone(self.guide.start_ms)

    def test_low_quality_group_rejected_even_when_values_look_open(self):
        self.step(quality=0)
        self.assertIn("left",self.guide.errors)
        self.assertIn("right",self.guide.errors)

    def test_binary_scope_steps_do_not_bridge_invalid_stale_or_other_subject(self):
        def row(t,v,subject="one",generation=1):
            return dict(timestamp_ms=t,left_closed_bit=v,subject_id=subject,calibration_generation=generation)
        rows=[row(0,0),row(50,1),row(100,None),row(150,0),row(500,1),row(550,1,"other"),row(600,0),row(650,1,generation=2)]
        segments=binary_segments(rows,"left_closed_bit","one",1,250)
        self.assertEqual(segments,[((0,0),(50,0),(50,1))])
