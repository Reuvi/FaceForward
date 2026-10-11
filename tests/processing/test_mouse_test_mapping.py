from copy import deepcopy
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

from Processing.mappings.config import GAMING_ID, MOUSE_TEST_ID, Mapping, mouse_test_mapping
from Processing.mouse.controller import Lab
from gaming_fixtures import frame


class MouseTestMappingTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.sequence = 0
        self.lab = Lab(clock=lambda:self.now)
        self.addCleanup(self.lab.close)
        self.lab.select_mapping(MOUSE_TEST_ID)
        self.lab.settings({'runtime':{'source':'external','subject_id':'person'}})

    def feed(self, **values):
        self.now += 20
        self.sequence += 1
        data = frame(self.sequence, self.now, **values)
        self.assertTrue(self.lab.ingest(data)['accepted'])
        return self.lab.state()['snapshot']

    def assert_pointer_only(self, snap):
        self.assertEqual((snap['left_click'],snap['right_click'],snap['scroll_y']), (0,0,.5))
        self.assertFalse(any(snap['keys'].values()))
        self.assertFalse(snap['known']['left_click'])
        self.assertFalse(snap['known']['right_click'])

    def test_arms_from_head_neutral_with_closed_eyes_and_off_center_or_missing_pupils(self):
        for pupil in (None, 1):
            self.lab.action({'action':'arm'})
            snap = self.feed(x=pupil,y=pupil,left='wink',right='wink')
            self.assertTrue(snap['enabled'])
            self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
            self.assert_pointer_only(snap)

    def test_all_directions_diagonals_and_ignored_gestures(self):
        for x,y in ((.2,.5),(.8,.5),(.5,.2),(.5,.8),(.2,.2),(.8,.8),(.2,.8),(.8,.2)):
            self.lab.action({'action':'arm'});self.feed()
            for _ in range(25):
                snap = self.feed(head_x=x,head_y=y,left='wink',right='wink',x=1,y=0)
                self.assert_pointer_only(snap)
            for axis, position in (('x',x),('y',y)):
                demand = snap['pointer_'+axis]-.5
                if position == .5:self.assertAlmostEqual(demand,0)
                else:self.assertGreater(demand*(position-.5),0)
            self.assertEqual([r['input'] for r in snap['instructions']],['Head X','Head Y','Other inputs'])

    def test_either_missing_head_axis_stops_motion_immediately(self):
        for axis in ('head_x','head_y'):
            self.lab.action({'action':'arm'});self.feed()
            for _ in range(15):self.feed(head_x=.8,head_y=.8)
            snap = self.feed(**{axis:None})
            self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
            self.assertFalse(snap['known']['pointer'])
            self.assertIsNone(snap['diagnostics']['raw_pointer'])

    def test_tiny_nudges_stale_stop_and_no_automatic_rearming(self):
        self.lab.action({'action':'arm'});self.feed()
        for _ in range(25):snap=self.feed(head_x=.53,head_y=.53)
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.now += 300;self.lab.step(self.now)
        self.assertFalse(self.lab.processor.armed)
        self.assertFalse(self.feed()['enabled'])
        self.lab.action({'action':'arm'});self.feed()
        self.lab.action({'action':'stop'})
        self.assertFalse(self.feed()['enabled'])

    def test_ignored_malformed_eye_intent_cannot_block_head(self):
        self.lab.action({'action':'arm'})
        self.now+=20;self.sequence+=1
        data=frame(self.sequence,self.now);data['eye_intent']={'broken':True}
        self.assertTrue(self.lab.ingest(data)['accepted'])
        self.assertTrue(self.lab.state()['snapshot']['enabled'])

    def test_copy_export_import_preserves_head_mode_and_separate_response(self):
        self.lab.settings({'config':replace(self.lab.processor.config,interpolation_ms=15).to_dict()})
        self.lab.copy_mapping('My head mouse')
        self.assertEqual(self.lab.state()['mapping']['input_mode'],'head-mouse')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mouse-test.json';self.lab.export_mapping(path)
            self.lab.select_mapping(GAMING_ID)
            self.assertEqual(self.lab.processor.config.interpolation_ms,50)
            self.lab.import_mapping(path)
        self.assertEqual(self.lab.processor.config.interpolation_ms,15)
        self.assertFalse(self.lab.processor.armed)
        self.lab.action({'action':'arm'})
        self.assertTrue(self.feed(x=None,y=None,left='unknown',right='unknown')['enabled'])

    def test_mapping_versions_and_invalid_head_keyboard_bindings(self):
        current=Mapping().to_dict();self.assertEqual(current['format'],'input_mapping_v3')
        legacy=deepcopy(current);legacy['format']='input_mapping_v1'
        del legacy['input_mode'];del legacy['adaptive_pointer']
        del legacy['pointer_mode'];del legacy['target_jitter']
        self.assertEqual(Mapping.from_dict(legacy).to_dict(),Mapping(pointer_mode='velocity').to_dict())
        head=mouse_test_mapping().to_dict()
        self.assertEqual(Mapping.from_dict(head),mouse_test_mapping())
        for key,value in (('input_mode','unknown'),('adaptive_pointer',1)):
            broken=deepcopy(head);broken[key]=value
            with self.assertRaises(ValueError):Mapping.from_dict(broken)
        head['bindings']['left']='w'
        with self.assertRaises(ValueError):Mapping.from_dict(head)
