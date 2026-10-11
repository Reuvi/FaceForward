"""Independent held keys/clicks and relative head control, without OS input."""
from copy import deepcopy
from dataclasses import replace
import unittest

from Processing.mappings.config import Mapping, mouse_test_mapping
from Processing.mappings.engine import HeadMouseProcessor
from Processing.mouse.controller import Lab
from Processing.mouse.output import control_message
from Processing.tuning.model import default_profile, profile, channels, sliders
from Processing.tuning.preview import live_values, response_preview
from gaming_fixtures import frame


class MouthButtonTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.seq = 0
        self.core = HeadMouseProcessor(subject_id='person')
        self.core.arm()

    def feed(self, **values):
        self.now += 20
        self.seq += 1
        data = frame(self.seq, self.now, **values)
        self.assertTrue(self.core.accept(data, self.now)['accepted'])
        return self.core.tick(self.now)

    def test_simultaneous_w_space_and_left_click_are_independent(self):
        self.assertTrue(self.feed()['enabled'])
        for _ in range(15):
            snap = self.feed(left='wink', right='wink', mouth=1, head_x=.7)
            self.assertEqual((snap['keys']['w'], snap['keys']['space']), (1, 1))
            self.assertEqual((snap['left_click'], snap['right_click']), (1, 0))
            self.assertGreater(snap['pointer_x'], .5)
            command = control_message(snap)
            self.assertEqual(command['pointer']['mode'], 'velocity')
            self.assertNotIn('speed', command['pointer'])
        snap = self.feed(left='wink', mouth=0, head_x=.7)
        self.assertEqual((snap['keys']['w'], snap['keys']['space'], snap['left_click']), (1, 0, 0))
        snap = self.feed(mouth=1)
        self.assertEqual((snap['keys']['w'], snap['keys']['space']), (0, 1))

    def test_missing_head_does_not_release_valid_buttons_but_stops_pointer(self):
        self.feed()
        snap = self.feed(head_x=None, head_y=None, left='wink', right='wink', mouth=1)
        self.assertEqual((snap['pointer_x'], snap['pointer_y']), (.5, .5))
        self.assertFalse(snap['known']['pointer'])
        self.assertEqual((snap['keys']['w'], snap['keys']['space'], snap['left_click']), (1, 1, 1))
        self.assertTrue(snap['known']['keys']['w'])
        self.assertTrue(snap['known']['keys']['space'])
        self.assertFalse(snap['known']['head_x'])

    def test_unknown_mouth_releases_space_and_needs_closed_baseline(self):
        self.feed()
        self.feed(mouth=1)
        snap = self.feed(mouth=None, left='wink', right='wink', head_y=.6)
        self.assertEqual((snap['keys']['space'], snap['keys']['w'], snap['left_click']), (0, 1, 1))
        self.assertFalse(snap['known']['keys']['space'])
        self.assertIsNone(snap['diagnostics']['mouth_open'])
        self.assertGreater(snap['pointer_y'], .5)
        self.assertEqual(self.feed(mouth=1)['keys']['space'], 0)
        self.feed(mouth=0)
        self.assertEqual(self.feed(mouth=1)['keys']['space'], 1)

    def test_unknown_eye_releases_w_without_suppressing_right_click_or_space(self):
        self.feed()
        self.feed(left='wink', mouth=1)
        snap = self.feed(left='unknown', right='wink', mouth=1)
        self.assertEqual((snap['keys']['w'], snap['keys']['space'], snap['left_click']), (0, 1, 1))
        self.assertFalse(snap['known']['keys']['w'])
        self.assertTrue(snap['known']['left_click'])  # Right eye, not anatomical left.
        self.assertEqual(self.feed(left='wink')['keys']['w'], 0)
        self.feed()
        self.assertEqual(self.feed(left='wink')['keys']['w'], 1)

    def test_startup_open_mouth_and_recenter_wait_for_close(self):
        for center in (False, True):
            self.core.arm(center=center)
            self.assertFalse(self.feed(mouth=1)['enabled'])
            self.assertTrue(self.feed(mouth=0)['enabled'])
            self.assertEqual(self.feed(mouth=1)['keys']['space'], 1)

    def test_loss_stale_stop_restart_release_and_never_auto_rearm(self):
        for kind in ('loss', 'stale', 'stop', 'restart'):
            with self.subTest(kind=kind):
                self.core = HeadMouseProcessor(subject_id='person')
                self.core.arm();self.feed();self.feed(left='wink', right='wink', mouth=1)
                if kind == 'stop':
                    self.core.disarm()
                elif kind == 'stale':
                    self.now += 300
                elif kind == 'loss':
                    self.seq += 1;self.now += 1
                    data = frame(self.seq, self.now);data['faces'] = []
                    self.assertFalse(self.core.accept(data, self.now)['accepted'])
                else:
                    self.feed(session='restarted')
                snap = self.core.tick(self.now)
                self.assertFalse(snap['enabled'])
                self.assertFalse(any(snap['keys'].values()))
                self.assertEqual((snap['left_click'], snap['right_click']), (0, 0))
                self.assertFalse(self.feed()['enabled'])

    def test_invalid_or_missing_mouth_is_unknown_not_closed(self):
        self.feed();self.feed(mouth=1)
        for bad in (None, .3, -1, 2, True, '1', float('nan')):
            snap = self.feed(mouth=bad)
            self.assertFalse(snap['known']['keys']['space'])
            self.assertEqual(snap['keys']['space'], 0)
        self.now += 20;self.seq += 1
        data = frame(self.seq, self.now, mouth=1)
        data['faces'][0]['signals']['mouth_open']['confidence'] = .1
        self.assertTrue(self.core.accept(data, self.now)['accepted'])
        self.assertFalse(self.core.tick(self.now)['known']['keys']['space'])
        self.now += 20;self.seq += 1
        data = frame(self.seq, self.now);del data['faces'][0]['signals']['mouth_open']
        self.assertTrue(self.core.accept(data, self.now)['accepted'])
        self.assertFalse(self.core.tick(self.now)['known']['keys']['space'])

    def test_shared_key_bindings_combine_without_early_release(self):
        self.core = HeadMouseProcessor(replace(mouse_test_mapping(), button_bindings=('w', 'left_click', 'w')), 'person')
        self.core.arm();self.feed()
        self.assertEqual(self.feed(left='wink', mouth=1)['keys']['w'], 1)
        self.assertEqual(self.feed(mouth=1)['keys']['w'], 1)
        self.assertEqual(self.feed()['keys']['w'], 0)

    def test_plain_closure_mode_uses_same_new_assignments(self):
        self.core = HeadMouseProcessor(replace(mouse_test_mapping(), require_wink=False), 'person')
        self.core.arm();self.feed()
        snap = self.feed(left='closed', right='closed', mouth=1)
        self.assertEqual((snap['keys']['w'], snap['left_click'], snap['keys']['space']), (1, 1, 1))

    def test_legacy_mappings_keep_previous_assignments_and_tuning(self):
        original = mouse_test_mapping().to_dict()
        original['response']['pointer']['exponent'] = 2.1
        for version in (6, 7):
            old = deepcopy(original);old['format'] = f'input_mapping_v{version}'
            del old['button_bindings'];del old['presentation']
            if version == 6:del old['require_wink']
            restored = Mapping.from_dict(old)
            self.assertEqual(restored.button_bindings, ('left_click', 'right_click', 'none'))
            self.assertEqual(restored.response.pointer.exponent, 2.1)
        for broken in ({'left_eye': 'w'}, {'left_eye': 'unknown', 'right_eye': 'left_click', 'mouth': 'space'}, None):
            data = deepcopy(original);data['button_bindings'] = broken
            with self.assertRaises(ValueError):Mapping.from_dict(data)

    def test_profiles_defaults_and_live_readouts_follow_assigned_actions(self):
        lab = Lab(clock=lambda: self.now);self.addCleanup(lab.close)
        lab.select_mapping('mouse-test')
        lab.settings({'runtime': {'source': 'external', 'subject_id': 'person'}})
        lab.action({'action': 'arm'})
        lab.ingest(frame(1, self.now))
        self.now += 20;lab.ingest(frame(2, self.now, left='wink', mouth=1))
        state = lab.state()
        self.assertIn(('mouth', 'Mouth open → SPACE'), channels(state))
        self.assertEqual(sliders(state, 'mouth'), [])
        self.assertEqual(live_values(state, 'left')[0][2], 1)
        self.assertEqual(live_values(state, 'mouth')[0][2], 1)
        self.assertEqual(max(y for _, y in response_preview(state, 'mouth')['Command']), 1)
        default = default_profile(state)
        self.assertEqual(default['mapping']['button_bindings'], state['mapping']['button_bindings'])
        saved = profile(state, 'New buttons')
        lab.apply_tuning_profile(saved)
        self.assertFalse(lab.state()['snapshot']['armed'])
        self.assertFalse(any(lab.state()['message']['keys'].values()))
        changed = lab.state()['mapping'];changed['button_bindings']['mouth'] = 'w'
        lab.update_mapping(changed)
        self.assertFalse(lab.state()['snapshot']['armed'])
