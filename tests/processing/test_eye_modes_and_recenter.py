"""Synthetic closure selection and fresh head-center startup; no camera/OS input."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from Processing.mappings.config import Mapping, mouse_test_mapping
from Processing.mappings.engine import GamingProcessor, HeadMouseProcessor
from Processing.mouse.controller import Lab
from Processing.tuning.model import default_profile, profile, read_profile, write_profile, channels, sliders
from gaming_fixtures import frame


class EyeModeTests(unittest.TestCase):
    def core(self, head=True):
        mapping = mouse_test_mapping() if head else Mapping()
        core = (HeadMouseProcessor if head else GamingProcessor)(replace(mapping, require_wink=False), subject_id='person')
        core.arm()
        return core

    def feed(self, core, seq, **values):
        data = frame(seq, 1000+seq*20, **values)
        # Plain mode ignores absent, unknown and even malformed wink metadata.
        data['eye_intent'] = {'not': 'used'}
        self.assertTrue(core.accept(data, data['timestamp_ms'])['accepted'])
        return core.tick(data['timestamp_ms'])

    def test_both_mappings_receive_instant_independent_closures(self):
        for head in (False, True):
            with self.subTest(head=head):
                core = self.core(head)
                self.assertTrue(self.feed(core, 1)['enabled'])
                snap = self.feed(core, 2, left='closed')
                self.assertEqual((snap['left_click'], snap['right_click']), (1, 0))
                snap = self.feed(core, 3, left='closed', right='blink')
                self.assertEqual((snap['left_click'], snap['right_click']), (1, 1))
                snap = self.feed(core, 4, right='closed')
                self.assertEqual((snap['left_click'], snap['right_click']), (0, 1))
                self.assertEqual(snap['instructions'][0]['threshold'], 'Open / closed')
                self.assertFalse(core.sample.appearance_intent)

    def test_unknown_releases_just_that_eye_and_requires_actual_reopen(self):
        core = self.core()
        self.feed(core, 1)
        self.feed(core, 2, left='closed', right='closed')
        snap = self.feed(core, 3, left='unknown', right='closed', head_x=.7)
        self.assertEqual((snap['left_click'], snap['right_click']), (0, 1))
        self.assertFalse(snap['known']['left_click'])
        self.assertEqual(core.eye_sample['left']['value'], 1)  # Numeric hold never clicks.
        self.assertGreater(snap['pointer_x'], .5)
        self.assertEqual(self.feed(core, 4, left='closed')['left_click'], 0)
        self.feed(core, 5)
        self.assertEqual(self.feed(core, 6, left='closed')['left_click'], 1)

    def test_closed_start_waits_for_open_and_invalid_geometry_never_clicks(self):
        core = self.core()
        self.assertFalse(self.feed(core, 1, left='closed')['enabled'])
        self.assertTrue(self.feed(core, 2)['enabled'])
        for seq, value, confidence in ((3, 0, .2), (4, .3, 1), (5, None, 1)):
            data = frame(seq, 1000+seq*20, left='wink')
            data['faces'][0]['signals']['left_eye_open'].update(value=value, confidence=confidence)
            self.assertTrue(core.accept(data, data['timestamp_ms'])['accepted'])
            snap = core.tick(data['timestamp_ms'])
            self.assertFalse(snap['known']['left_click'])
            self.assertEqual(snap['left_click'], 0)

    def test_plain_raw_input_uses_configured_polarity_without_timers(self):
        for polarity in (0, 1):
            mapping = mouse_test_mapping()
            mapping = replace(mapping, require_wink=False, response=replace(mapping.response, closed_value=polarity))
            core = HeadMouseProcessor(mapping, 'person');core.arm()
            for seq in (1, 2, 3):
                data = dict(format='raw_mouse_v1', session_id='raw', subject_id='person', sequence=seq,
                            timestamp_ms=1000+seq*20, left_eye=polarity if seq==2 else 1-polarity,
                            right_eye=1-polarity, head_horizontal=[0,1,0], head_vertical=[0,1,0])
                self.assertTrue(core.accept(data, data['timestamp_ms'])['accepted'])
                self.assertEqual(core.tick(data['timestamp_ms'])['left_click'], int(seq==2))

    def test_clicks_off_ignores_geometry_even_when_plain_selected(self):
        core = HeadMouseProcessor(replace(mouse_test_mapping(), require_wink=False, head_wink_clicks=False), 'person')
        core.arm()
        for seq in (1, 2):
            snap = self.feed(core, seq, left='closed', right='closed')
            self.assertTrue(snap['enabled'])
            self.assertEqual((snap['left_click'],snap['right_click']), (0,0))
            self.assertFalse(snap['known']['left_click'])

    def test_mode_validation_migration_and_roundtrip(self):
        plain = replace(mouse_test_mapping(), require_wink=False)
        self.assertEqual(Mapping.from_dict(plain.to_dict()), plain)
        old = plain.to_dict();old['format']='input_mapping_v6';del old['require_wink']
        loaded = Mapping.from_dict(old)
        self.assertTrue(loaded.require_wink)
        self.assertEqual(loaded.response, plain.response)
        self.assertTrue(loaded.head_wink_clicks)
        for value in (0, 1, None, 'false'):
            with self.assertRaises(ValueError):replace(plain, require_wink=value)
        invalid=deepcopy(old);invalid['require_wink']=False
        with self.assertRaises(ValueError):Mapping.from_dict(invalid)


class RecenterTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.seq=0
        self.lab=Lab(clock=lambda:self.now);self.addCleanup(self.lab.close)
        self.lab.select_mapping('mouse-test')
        self.lab.settings({'runtime':{'source':'external','subject_id':'person'}})

    def feed(self, **values):
        self.now+=20;self.seq+=1
        self.assertTrue(self.lab.ingest(frame(self.seq,self.now,**values))['accepted'])
        return self.lab.state()

    def mode(self, value):
        state=self.lab.state()
        self.lab.set_eye_mode(value,mapping_id=state['mapping_id'],generation=state['generation'])

    def test_recenter_unblocks_offset_pose_with_neutral_first_command_then_movement(self):
        self.lab.action({'action':'arm'})
        state=self.feed(head_x=.3,head_y=.7)
        self.assertTrue(state['snapshot']['armed']);self.assertFalse(state['snapshot']['enabled'])
        self.lab.action({'action':'center_head_start'})
        self.assertEqual(self.lab.state()['config']['pointer']['center_x'],.5)
        self.assertFalse(self.lab.state()['snapshot']['enabled'])
        # Capture newer than the button sets a different center; never cached input.
        state=self.feed(head_x=.32,head_y=.68)
        self.assertTrue(state['snapshot']['enabled'])
        self.assertEqual(state['message']['pointer'],dict(mode='velocity',x=.5,y=.5))
        self.assertEqual(state['config']['pointer']['center_x'],.32)
        self.assertEqual(state['config']['pointer']['center_y'],.68)
        self.assertEqual(state['mapping']['response'],state['config'])
        self.assertEqual(state['config']['pointer']['deadzone'],.03)
        for _ in range(12):state=self.feed(head_x=.4,head_y=.7)
        self.assertGreater(state['snapshot']['pointer_x'],.5)
        self.assertGreater(state['snapshot']['pointer_y'],.5)
        self.assertTrue(all(v==0 for v in state['message']['keys'].values()))

    def test_pending_center_waits_for_valid_axes_and_released_eyes_and_range(self):
        self.lab.action({'action':'center_head_start'})
        for values, reason in ((dict(head_y=None),'valid Head'), (dict(left='wink'),'open your eyes'),
                               (dict(head_x=1),'range limits')):
            state=self.feed(**values)
            self.assertFalse(state['snapshot']['enabled'])
            self.assertTrue(state['snapshot']['diagnostics']['head_center_pending'])
            self.assertIn(reason,state['snapshot']['status'])
        state=self.feed(head_x=.3,head_y=.7,left='unknown',right='unknown')
        self.assertTrue(state['snapshot']['enabled'])
        self.assertFalse(state['snapshot']['diagnostics']['head_center_pending'])
        self.assertEqual(state['snapshot']['left_click'],0)

    def test_stop_loss_stale_and_restart_cancel_pending_center(self):
        for kind in ('stop','loss','stale','restart','settings','mapping'):
            with self.subTest(kind=kind):
                self.lab.select_mapping('mouse-test')
                self.feed()
                self.lab.action({'action':'center_head_start'})
                if kind=='stop':self.lab.action({'action':'stop'})
                elif kind=='loss':
                    self.now+=20;self.seq+=1
                    data=frame(self.seq,self.now);data['faces']=[]
                    self.lab.ingest(data)
                elif kind=='stale':
                    self.feed(head_y=None);self.now+=300;self.lab.step(self.now)
                elif kind=='restart':
                    self.now+=20;self.seq+=1
                    self.lab.ingest(frame(self.seq,self.now,session='new'))
                elif kind=='settings':self.lab.settings({})
                else:self.lab.select_mapping('gaming-keyboard-mouse-1')
                self.assertFalse(self.lab.processor.armed)
                self.assertFalse(getattr(self.lab.processor,'center_requested',False))
                self.assertFalse(self.feed()['snapshot']['enabled'])

    def test_no_frames_after_recenter_expires_without_auto_resume(self):
        for tick_first in (False, True):
            with self.subTest(tick_first=tick_first):
                self.lab.action({'action':'center_head_start'})
                self.now+=300
                if tick_first:self.lab.step(self.now)
                state=self.feed(head_x=.3,head_y=.7)
                self.assertFalse(state['snapshot']['armed'])
                self.assertFalse(state['snapshot']['enabled'])
                self.assertFalse(self.lab.processor.center_requested)
                self.assertEqual(state['config']['pointer']['center_x'],.5)

    def test_rejected_duplicate_cannot_capture_center(self):
        self.feed()
        data=deepcopy(self.lab.state()['raw'])
        self.lab.action({'action':'center_head_start'})
        self.assertFalse(self.lab.ingest(data)['accepted'])
        self.assertTrue(self.lab.processor.center_requested)
        self.assertFalse(self.lab.state()['snapshot']['enabled'])
        self.assertTrue(self.feed(head_x=.3,head_y=.7)['snapshot']['enabled'])

    def test_source_choice_disarms_preserves_response_and_rejects_stale_ui(self):
        self.lab.action({'action':'arm'});self.feed();self.feed(left='wink')
        before=self.lab.state();self.mode(False)
        after=self.lab.state()
        self.assertFalse(after['snapshot']['armed'])
        self.assertEqual(after['config'],before['config'])
        self.assertEqual(after['snapshot']['left_click'],0)
        self.assertFalse(self.feed(left='closed')['snapshot']['enabled'])
        with self.assertRaises(ValueError):
            self.lab.set_eye_mode(True,mapping_id=before['mapping_id'],generation=before['generation'])
        self.assertFalse(self.lab.state()['mapping']['require_wink'])
        self.lab.action({'action':'arm'});self.feed()
        self.assertEqual(self.feed(left='closed')['snapshot']['left_click'],1)

    def test_profiles_copy_export_and_defaults_preserve_plain_choice(self):
        self.mode(False)
        self.lab.action({'action':'center_head_start'});self.feed(head_x=.3,head_y=.7)
        self.lab.copy_mapping('Head closure clicks')
        state=self.lab.state()
        self.assertFalse(default_profile(state)['mapping']['require_wink'])
        self.assertIn(('left','Left open/closed → left click'), channels(state))
        self.assertEqual(sliders(state,'left'),[])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tuning.json';write_profile(path,profile(state,'Closure clicks'))
            self.mode(True)
            self.lab.apply_tuning_profile(read_profile(path))
            self.assertFalse(self.lab.state()['mapping']['require_wink'])
            self.assertEqual(self.lab.state()['config']['pointer']['center_x'],.3)
            self.assertFalse(self.lab.processor.armed)
            mapping_path=Path(directory)/'mapping.json';self.lab.export_mapping(mapping_path)
            self.lab.select_mapping('gaming-keyboard-mouse-1');self.lab.import_mapping(mapping_path)
            self.assertFalse(self.lab.state()['mapping']['require_wink'])
            self.assertEqual(self.lab.state()['config']['pointer']['center_y'],.7)

    def test_recenter_only_applies_to_head_pointer(self):
        self.lab.select_mapping('gaming-keyboard-mouse-1')
        with self.assertRaises(ValueError):self.lab.action({'action':'center_head_start'})
