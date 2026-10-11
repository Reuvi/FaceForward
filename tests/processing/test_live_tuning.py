"""Live response updates, shared curve previews and strict local tuning profiles."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from Processing.mouse.controller import Lab
from Processing.mappings.config import GAMING_ID
from Processing.tuning.model import channels, sliders, profile, default_profile, read_profile, write_profile
from Processing.tuning.preview import filter_for, steady_curves, response_preview, live_values
from gaming_fixtures import frame


class LiveTuningTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.seq=0
        self.lab=Lab(clock=lambda:self.now)
        self.addCleanup(self.lab.close)
        self.lab.select_mapping('mouse-test')
        self.lab.settings({'runtime':{'source':'external','subject_id':'person'}})
        self.lab.action({'action':'arm'})
        self.feed()

    def feed(self,**values):
        self.now+=20;self.seq+=1
        self.assertTrue(self.lab.ingest(frame(self.seq,self.now,**values))['accepted'])
        return self.lab.state()['snapshot']

    def tune(self,channel,**changes):
        state=self.lab.state()
        self.lab.tune_response(channel,changes,mapping_id=state['mapping_id'],generation=state['generation'])

    def test_gain_changes_live_without_restarting_filter_or_replaying_wink(self):
        for _ in range(30):self.feed(head_x=.7,left='wink')
        core=self.lab.processor
        before=self.lab.state();history=list(core.pointer.history);velocity=core.pointer.velocity
        self.tune('pointer',gain=2)
        after=self.lab.state()
        self.assertIs(self.lab.processor,core)
        self.assertEqual(list(core.pointer.history),history)
        self.assertEqual(core.pointer.velocity,velocity)
        self.assertTrue(after['snapshot']['enabled'])
        self.assertEqual(after['message']['output_session_id'],before['message']['output_session_id'])
        self.assertEqual(after['message']['mapping_revision'],before['message']['mapping_revision'])
        self.assertEqual(after['snapshot']['left_click'],1)
        self.assertEqual(after['tuning_revision'],before['tuning_revision']+1)
        for _ in range(30):snap=self.feed(head_x=.7,left='wink')
        self.assertGreater(snap['pointer_x'],before['snapshot']['pointer_x'])

    def test_stopped_stale_and_unknown_cannot_be_reenabled_by_a_slider(self):
        self.lab.action({'action':'stop'});self.tune('pointer',gain=2)
        self.assertFalse(self.lab.state()['snapshot']['armed'])
        self.lab.action({'action':'arm'});self.feed();self.now+=300
        self.tune('pointer',gain=3)
        self.assertFalse(self.lab.state()['snapshot']['armed'])
        self.assertFalse(self.feed()['enabled'])
        self.lab.action({'action':'arm'});self.feed()
        self.feed(head_x=None,left='unknown')
        self.tune('pointer',down_gain=5)
        snap=self.lab.state()['snapshot']
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.assertFalse(snap['known']['pointer']);self.assertEqual(snap['left_click'],0)
        self.assertIsNone(live_values(self.lab.state(),'pointer')[0][1])

    def test_edit_cannot_satisfy_pending_start_from_a_cached_capture(self):
        self.lab.action({'action':'arm'})
        self.assertFalse(self.feed(head_x=.65)['enabled'])
        self.tune('pointer',deadzone=.5)
        self.assertFalse(self.lab.state()['snapshot']['enabled'])
        self.now+=10;self.lab.step(self.now)
        self.assertFalse(self.lab.state()['snapshot']['enabled'])
        self.assertTrue(self.feed()['enabled'])

    def test_invalid_and_obsolete_edits_are_atomic(self):
        state=self.lab.state()
        for change in ({'gain':float('nan')},{'gain':True},{'gain':5},{'pointer_mode':'target'},{'min_confidence':0}):
            with self.assertRaises(ValueError):self.tune('pointer',**change)
            self.assertEqual(self.lab.state()['mapping'],state['mapping'])
            self.assertEqual(self.lab.state()['generation'],state['generation'])
        self.lab.select_mapping(GAMING_ID)
        with self.assertRaisesRegex(ValueError,'refresh'):
            self.lab.tune_response('pointer',{'gain':2},mapping_id=state['mapping_id'],generation=state['generation'])

    def test_head_key_edits_release_only_that_axis_and_need_fresh_neutral(self):
        self.lab.select_mapping(GAMING_ID);self.lab.action({'action':'arm'});self.feed()
        for _ in range(30):self.feed(head_x=.9,head_y=.9,left='wink')
        before=self.lab.state()['snapshot']
        self.assertEqual((before['keys']['s'],before['keys']['w'],before['left_click']),(1,1,1))
        self.tune('head_x',activation=.1,confirmation_ms=0,smoothing_ms=0)
        snap=self.lab.state()['snapshot']
        self.assertEqual((snap['keys']['s'],snap['keys']['w'],snap['left_click']),(0,1,1))
        self.assertLess(self.lab.state()['mapping']['head_x']['release'],.1)
        self.assertEqual(self.feed(head_x=.9,head_y=.9,left='wink')['keys']['s'],0)
        self.feed(head_x=.5,head_y=.9,left='wink')
        self.assertEqual(self.feed(head_x=.9,head_y=.9,left='wink')['keys']['s'],1)

    def test_zero_smoothing_can_be_enabled_and_disabled_live_without_jump(self):
        for _ in range(25):self.feed(head_x=.7)
        core=self.lab.processor;old=core.pointer.velocity
        self.tune('pointer',smoothing_ms=0)
        self.assertIsNone(core.pointer.adaptive)
        self.assertEqual(core.pointer.velocity,old)
        self.feed(head_x=.6)
        old=core.pointer.velocity
        self.tune('pointer',smoothing_ms=100)
        self.assertIsNotNone(core.pointer.adaptive)
        self.assertEqual(core.pointer.velocity,old)
        self.assertEqual(core.pointer.adaptive.value,old)

    def test_target_tuning_preserves_position_and_updates_only_target_filtering(self):
        self.lab.select_mapping(GAMING_ID);self.lab.action({'action':'arm'});self.feed(x=.6)
        original=self.lab.state()['config']['pointer']['smoothing_ms']
        core=self.lab.processor;before=core.pointer.velocity
        self.tune('pointer',gain=1.5,smoothing_ms=0,delay_ms=20,jitter=.01)
        self.assertEqual(self.lab.state()['config']['pointer']['smoothing_ms'],original)
        self.assertEqual(core.pointer.delay_ms,20)
        self.assertEqual(core.pointer.jitter,.01)
        self.assertTrue(self.lab.state()['snapshot']['enabled'])
        self.assertTrue(all(0<=x<=1 for x in self.lab.state()['message']['pointer'].values() if isinstance(x,float)))
        self.assertNotEqual(core.pointer.velocity,before)  # Zero smoothing applies immediately.

    def test_scroll_and_pointer_tuning_stay_independent(self):
        self.lab.select_mapping('mouse');self.lab.action({'action':'arm'});self.feed()
        before=self.lab.state()['config']['pointer']
        self.tune('scroll',exponent=3,boost_decay_ms=800,acceleration=2)
        self.assertEqual(self.lab.state()['config']['pointer'],before)
        self.assertEqual(self.lab.processor.scroll.config.exponent,3)
        self.tune('pointer',delay_ms=30)
        self.assertEqual(self.lab.processor.config.interpolation_ms,30)

    def test_channels_and_sliders_only_expose_connected_controls(self):
        state=self.lab.state()
        self.assertEqual(set(dict(channels(state))),{'pointer','left','right'})
        keys={s.key for s in sliders(state,'pointer')}
        self.assertIn('speed_gain',keys);self.assertNotIn('boost_gain',keys)
        self.assertEqual(sliders(state,'left'),[])
        with self.assertRaises(ValueError):self.tune('left',dwell_ms=500)
        self.lab.select_mapping(GAMING_ID);state=self.lab.state()
        self.assertIn('head_x',dict(channels(state)))
        keys={s.key for s in sliders(state,'pointer')}
        self.assertIn('jitter',keys);self.assertNotIn('acceleration',keys)

    def test_default_and_saved_profiles_restore_real_settings_and_disarm(self):
        self.tune('pointer',gain=2.3,exponent=2.4,speed_gain=.5)
        data=profile(self.lab.state(),'Precision + reach')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tuning.json';write_profile(path,data)
            loaded=read_profile(path)
        self.assertEqual(loaded,data)
        self.lab.select_mapping(GAMING_ID)
        self.lab.apply_tuning_profile(loaded)
        state=self.lab.state()
        self.assertEqual(state['mapping_id'],'mouse-test')
        self.assertEqual(state['mapping']['pointer_gain'],2.3)
        self.assertEqual(state['config']['pointer']['exponent'],2.4)
        self.assertFalse(state['snapshot']['armed'])
        self.lab.apply_tuning_profile(default_profile(state))
        self.assertEqual(self.lab.state()['mapping']['pointer_gain'],1.4)
        self.assertEqual(self.lab.state()['config']['pointer']['exponent'],1.8)
        self.assertFalse(self.lab.state()['snapshot']['armed'])

    def test_profile_validation_finishes_before_touching_output(self):
        good=profile(self.lab.state(),'Good')
        for update in ({'name':''},{'speeds':{'pointer_speed':0,'scroll_speed':450}}, {'mouse_config':{}}, {'format':'unknown'}):
            bad=deepcopy(good);bad.update(update)
            before=self.lab.state()
            with self.assertRaises(ValueError):self.lab.apply_tuning_profile(bad)
            self.assertEqual(self.lab.state()['generation'],before['generation'])
            self.assertTrue(self.lab.state()['snapshot']['enabled'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            for text in ('{}','{not json',' '*65537):
                path.write_text(text)
                with self.assertRaises(ValueError):read_profile(path)

    def test_mouse_profile_roundtrip_and_defaults_keep_locked_source(self):
        self.lab.select_mapping('mouse')
        self.lab.locked_pointer_source='gaze'
        self.tune('scroll',exponent=2.2)
        data=profile(self.lab.state(),'Scroll')
        self.lab.apply_tuning_profile(data)
        self.assertEqual(self.lab.processor.config.pointer_source,'gaze')
        self.assertEqual(self.lab.processor.config.scroll.exponent,2.2)
        self.lab.apply_tuning_profile(default_profile(self.lab.state()))
        self.assertEqual(self.lab.processor.config.pointer_source,'gaze')
        self.assertEqual(self.lab.processor.config.scroll.exponent,1.8)

    def test_curve_preview_uses_same_targets_as_actual_filters(self):
        for mapping_id in ('mouse-test',GAMING_ID,'mouse'):
            self.lab.select_mapping(mapping_id)
            state=self.lab.state()
            for channel in ('pointer','scroll') if mapping_id=='mouse' else ('pointer',):
                curves=steady_curves(state,channel)
                for axis,points in enumerate(curves.values()):
                    for raw,expected in points[::10]:
                        filt,delay=filter_for(state,channel)
                        pos=raw if channel=='scroll' else (raw,.5) if axis==0 else (.5,raw)
                        filt.push(pos,0);filt.step(delay,delay,.01)
                        self.assertAlmostEqual((filt.target[axis]+1)/2,expected)

    def test_timing_preview_changes_with_braking_and_does_not_touch_live_state(self):
        before=self.lab.state()
        quick=response_preview(before,'pointer')
        self.assertEqual(self.lab.state()['generation'],before['generation'])
        self.assertEqual(self.lab.state()['snapshot'],before['snapshot'])
        self.tune('pointer',deceleration=.1,return_brake=0)
        slow=response_preview(self.lab.state(),'pointer')
        # At 1.2s input is centered; slow braking carries more residual speed.
        self.assertGreater(slow['X'][120][1],quick['X'][120][1])
        self.assertEqual(slow['Input'][-1][1],.5)

    def test_legacy_eye_timers_are_connected_only_for_raw_input(self):
        from Processing.mouse.mocks import raw_frame
        self.lab.select_mapping('mouse')
        self.lab.settings({'runtime':{'source':'mock'}})
        state=self.lab.state()
        self.assertEqual({s.key for s in sliders(state,'left')},{'dwell_ms','release_ms'})
        self.tune('left',dwell_ms=500,release_ms=0)
        self.assertEqual(self.lab.processor.left.config.dwell_ms,500)
        self.assertEqual(self.lab.processor.right.config.dwell_ms,320)
        timeline=response_preview(self.lab.state(),'left')
        self.assertEqual(timeline['Command'][40][1],0)
        self.assertEqual(timeline['Command'][75][1],1)
        self.lab.settings({'runtime':{'source':'external'}})
        state=self.lab.state()
        state['raw']=raw_frame(1,self.now,dict(x=.5,y=.5,scroll=.5,head_x=.5,left=False,right=False))
        self.assertEqual(len(sliders(state,'left')),2)
        state['raw']=frame(1,self.now)
        self.assertEqual(sliders(state,'left'),[])

    def test_profile_default_keeps_custom_mapping_identity_and_routing(self):
        self.lab.select_mapping(GAMING_ID);self.lab.copy_mapping('Custom keys')
        mapping=replace(self.lab.mappings[self.lab.mapping_id],bindings=('s','w','none','left_shift'),pointer_mode='velocity')
        self.lab.update_mapping(mapping.to_dict())
        self.lab.apply_tuning_profile(default_profile(self.lab.state()))
        actual=self.lab.mappings[self.lab.mapping_id]
        self.assertEqual((actual.id,actual.bindings,actual.pointer_mode),(mapping.id,mapping.bindings,mapping.pointer_mode))
