"""Precision head velocity and independent appearance-based wink actions."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from Processing.mappings.config import Mapping, mouse_test_mapping
from Processing.mappings.engine import HeadMouseProcessor
from Processing.mouse.controller import Lab
from gaming_fixtures import frame


class PreciseHeadWinkTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.seq=0
        self.core=HeadMouseProcessor(subject_id='person')
        self.core.arm()

    def feed(self, **values):
        self.now+=20;self.seq+=1
        self.assertTrue(self.core.accept(frame(self.seq,self.now,**values),self.now)['accepted'])
        return self.core.tick(self.now)

    def test_small_motion_is_precise_larger_motion_is_fast_and_bounded(self):
        speeds=[]
        for position in (.503,.525,.55,.6,.8,1):
            self.core.arm();self.feed()
            for _ in range(80):snap=self.feed(head_x=position)
            speed=(snap['pointer_x']*2-1)*900
            speeds.append(speed)
            self.assertEqual(snap['pointer_y'],.5)
            self.assertTrue(0 <= speed <= 900)
        self.assertEqual(speeds[0],0)
        self.assertTrue(.5 < speeds[1] < 2, speeds)
        self.assertTrue(5 < speeds[2] < 20, speeds)
        self.assertTrue(30 < speeds[3] < 80, speeds)
        self.assertGreater(speeds[4],400)
        self.assertGreater(speeds[5],899)
        self.assertEqual(sorted(speeds),speeds)

    def test_winks_are_immediate_independent_and_do_not_type_or_scroll(self):
        self.feed()
        for left,right in (('wink','open'),('open','wink'),('wink','wink'),('open','open')):
            snap=self.feed(left=left,right=right,head_x=.7,x=None,y=None)
            self.assertEqual((snap['left_click'],snap['right_click']),
                             (int(left=='wink'),int(right=='wink')))
            self.assertTrue(snap['enabled'])
            self.assertFalse(any(snap['keys'].values()))
            self.assertEqual(snap['scroll_y'],.5)
        self.assertEqual([r['input'] for r in snap['instructions']],
                         ['Left eye action','Right eye action','Head X','Head Y','Other inputs'])

    def test_unknown_releases_only_its_eye_and_requires_actual_reopening(self):
        self.feed();self.feed(left='wink')
        snap=self.feed(left='unknown',right='wink',head_x=.7)
        self.assertEqual((snap['left_click'],snap['right_click']),(0,1))
        self.assertFalse(snap['known']['left_click'])
        self.assertTrue(snap['known']['pointer'])
        for left in ('wink','blink','wink'):
            snap=self.feed(left=left,right='wink',head_x=.7)
            self.assertEqual((snap['left_click'],snap['right_click']),(0,1))
        self.feed(left='open',right='wink')
        self.assertEqual(self.feed(left='wink',right='wink')['left_click'],1)

    def test_untrained_eyes_allow_pointer_and_missing_head_allows_winks_after_start(self):
        self.assertTrue(self.feed(left='unknown',right='unknown')['enabled'])
        for _ in range(20):snap=self.feed(head_x=.7,left='unknown',right='unknown')
        self.assertGreater(snap['pointer_x'],.5)
        self.assertEqual((snap['left_click'],snap['right_click']),(0,0))
        self.feed()
        snap=self.feed(head_y=None,left='wink',right='wink')
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.assertFalse(snap['known']['pointer'])
        self.assertEqual((snap['left_click'],snap['right_click']),(1,1))

    def test_startup_wink_waits_for_release_and_new_activation(self):
        for _ in range(4):self.assertFalse(self.feed(left='wink')['enabled'])
        snap=self.feed()
        self.assertTrue(snap['enabled']);self.assertEqual(snap['left_click'],0)
        self.assertEqual(self.feed(left='wink')['left_click'],1)

    def test_anatomical_closure_without_intent_never_clicks(self):
        for seq in range(1,15):
            data=frame(seq,1000+seq*20,left='open' if seq==1 else 'wink',right='wink',head_x=.5 if seq==1 else .7)
            del data['eye_intent']
            self.assertTrue(self.core.accept(data,data['timestamp_ms'])['accepted'])
            snap=self.core.tick(data['timestamp_ms'])
            self.assertTrue(snap['enabled'])
            self.assertEqual((snap['left_click'],snap['right_click']),(0,0))
            self.assertFalse(snap['known']['left_click'])
        self.assertGreater(snap['pointer_x'],.5)

    def test_legacy_raw_closure_cannot_substitute_for_wink(self):
        for seq in range(1,15):
            data=dict(format='raw_mouse_v1',session_id='raw',subject_id='person',sequence=seq,
                      timestamp_ms=1000+seq*20,left_eye=seq>1,right_eye=seq>1,
                      head_horizontal=[0,1,0] if seq==1 else [0,0,1],head_vertical=[0,1,0])
            # Legacy eye values are numeric, not booleans.
            data.update(left_eye=int(seq>1),right_eye=int(seq>1))
            self.assertTrue(self.core.accept(data,data['timestamp_ms'])['accepted'])
            snap=self.core.tick(data['timestamp_ms'])
            self.assertEqual((snap['left_click'],snap['right_click']),(0,0))
            self.assertFalse(snap['known']['left_click'])
        self.assertGreater(snap['pointer_x'],.5)

    def test_malformed_intent_loss_staleness_and_stop_disarm_without_auto_resume(self):
        self.feed();self.feed(left='wink',right='wink')
        bad=frame(self.seq+1,self.now+20);bad['eye_intent']={'broken':True}
        self.assertFalse(self.core.accept(bad,self.now+20)['accepted'])
        self.assertFalse(self.feed()['enabled'])
        self.core.arm();self.feed();self.feed(left='wink')
        self.now+=300
        snap=self.core.tick(self.now)
        self.assertFalse(snap['armed']);self.assertEqual(snap['left_click'],0)
        self.assertFalse(self.feed()['enabled'])
        self.core.arm();self.feed();self.core.disarm()
        self.assertFalse(self.feed()['enabled'])

    def test_v5_migration_preserves_tuning_but_leaves_new_clicks_off(self):
        current=mouse_test_mapping().to_dict()
        old=deepcopy(current);old['format']='input_mapping_v5';del old['head_wink_clicks'];del old['require_wink']
        old['pointer_gain']=.9;old['response']['pointer']['deadzone']=.12
        loaded=Mapping.from_dict(old)
        self.assertFalse(loaded.head_wink_clicks)
        self.assertEqual(loaded.pointer_gain,.9)
        self.assertEqual(loaded.response.pointer.deadzone,.12)
        self.assertEqual(loaded.head_motion,mouse_test_mapping().head_motion)
        self.assertEqual(Mapping.from_dict(current),mouse_test_mapping())
        for value in (1,None,'yes'):
            bad=deepcopy(current);bad['head_wink_clicks']=value
            with self.assertRaises(ValueError):Mapping.from_dict(bad)
        with self.assertRaises(ValueError):replace(Mapping(),head_wink_clicks=True)

    def test_click_option_survives_copy_export_import_and_changes_disarm(self):
        lab=Lab(clock=lambda:self.now);self.addCleanup(lab.close)
        lab.select_mapping('mouse-test');lab.copy_mapping('My head winks')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mapping.json';lab.export_mapping(path)
            lab.select_mapping('gaming-keyboard-mouse-1');lab.import_mapping(path)
        self.assertTrue(lab.state()['mapping']['head_wink_clicks'])
        lab.action({'action':'arm'})
        changed=lab.state()['mapping'];changed['head_wink_clicks']=False
        lab.update_mapping(changed)
        self.assertFalse(lab.processor.armed)
        self.assertFalse(lab.state()['mapping']['head_wink_clicks'])
