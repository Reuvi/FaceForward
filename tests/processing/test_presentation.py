from copy import deepcopy
from dataclasses import replace
import unittest

from Processing.mappings.config import Mapping, PresentationConfig, presentation_mapping, mouse_test_mapping
from Processing.mappings.presentation import PresentationProcessor
from Processing.mouse.controller import Lab
from Processing.tuning.model import profile, default_profile, sliders
from Processing.tuning.preview import steady_curves, response_preview, live_values
from gaming_fixtures import frame


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.seq=0
        self.core=PresentationProcessor(subject_id='person');self.core.arm()
        self.feed()

    def feed(self, **values):
        self.now+=20;self.seq+=1
        self.assertTrue(self.core.accept(frame(self.seq,self.now,**values),self.now)['accepted'])
        return self.core.tick(self.now)

    def hold(self, count=30, **values):
        return [self.feed(**values) for _ in range(count)]

    def test_left_down_on_closure_up_on_open_enter_on_reopen(self):
        self.assertTrue(self.core.enabled)
        snaps=self.hold(10,left='closed')
        self.assertTrue(all(s['presentation']['drag_left'] for s in snaps))
        self.assertFalse(any(s['left_click'] for s in snaps))
        self.assertFalse(self.feed()['presentation']['drag_left'])
        self.hold(10,right='closed')
        self.assertTrue(self.feed()['presentation']['enter'])
        self.assertFalse(self.feed()['presentation']['enter'])
        snap=self.feed(openness=1)
        self.assertFalse(any(snap['keys'].values()))
        self.assertEqual(snap['right_click'],0)

    def test_short_blinks_and_skewed_chords_do_not_leak_actions(self):
        self.hold(3,left='closed',right='closed');self.feed()
        self.assertEqual(self.core.dictation_toggle,0)
        self.feed(left='closed')
        snaps=self.hold(30,left='closed',right='closed')
        snaps+=self.hold(3,right='closed')+[self.feed()]
        self.assertTrue(self.core.dictating)
        self.assertEqual(self.core.dictation_toggle,1)
        self.assertFalse(any(s['left_click'] or s['presentation']['enter'] for s in snaps))
        self.hold(40,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,2)
        self.assertFalse(self.core.dictating)
        self.hold(40,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,2)

    def test_unknown_closing_preserves_baseline_but_resets_full_chord_hold(self):
        self.feed(left='unknown',right='unknown')
        self.hold(15,left='closed',right='closed')
        self.feed(left='unknown',right='closed')
        self.hold(15,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,0)
        self.hold(10,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,1)
        self.feed(left='unknown',right='unknown')
        self.hold(30,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,1)  # No rearm without reopen.
        self.feed();self.feed(left='unknown',right='unknown')
        self.hold(30,left='closed',right='closed')
        self.assertEqual(self.core.dictation_toggle,2)

    def test_unknown_during_right_action_never_replays_return(self):
        self.hold(10,right='closed');self.feed(right='unknown')
        self.assertFalse(self.feed()['presentation']['enter'])
        self.feed(right='unknown')
        self.hold(10,right='closed')
        self.assertTrue(self.feed()['presentation']['enter'])

    def test_interrupted_chord_cannot_turn_into_a_solo_return(self):
        self.hold(10,left='closed',right='closed')
        self.feed(left='unknown',right='closed')
        snaps=self.hold(10,right='closed')+[self.feed()]
        self.assertFalse(any(s['presentation']['enter'] for s in snaps))
        self.assertEqual(self.core.dictation_toggle,0)

    def test_drag_releases_on_reopen_unknown_stop_and_stale(self):
        self.assertTrue(self.hold(35,left='closed')[-1]['presentation']['drag_left'])
        snap=self.feed();self.assertFalse(snap['presentation']['drag_left']);self.assertFalse(snap['left_click'])
        self.hold(35,left='closed')
        self.assertTrue(self.feed(right='unknown',left='closed')['presentation']['drag_left'])
        self.assertFalse(self.feed(left='unknown')['presentation']['drag_left'])
        self.assertFalse(self.hold(35,left='closed')[-1]['presentation']['drag_left'])
        self.feed();self.hold(35,left='closed');self.core.disarm()
        self.assertFalse(self.core.tick(self.now)['presentation']['drag_left'])
        self.core.arm();self.feed();self.hold(35,left='closed')
        self.now+=300;snap=self.core.tick(self.now)
        self.assertFalse(snap['enabled']);self.assertFalse(snap['presentation']['drag_left'])
        self.assertFalse(self.feed()['enabled'])

    def test_unknown_left_releases_and_requires_reopen_before_another_press(self):
        self.hold(12,left='closed');self.feed(left='unknown')
        self.assertFalse(self.hold(12,left='closed')[-1]['presentation']['drag_left'])
        self.feed()
        self.assertTrue(self.feed(left='closed')['presentation']['drag_left'])

    def test_wink_flag_gates_left_but_both_eyes_use_anatomical_closure(self):
        self.wink_mode()
        self.assertFalse(self.feed(left='closed')['presentation']['drag_left'])
        self.assertTrue(self.feed(left='wink')['presentation']['drag_left'])
        self.assertFalse(self.feed()['presentation']['drag_left'])
        self.hold(30,left='closed',right='closed')
        self.assertTrue(self.core.dictating)

    def wink_mode(self):
        self.core=PresentationProcessor(replace(presentation_mapping(),require_wink=True),'person')
        self.core.arm();self.feed()

    def intent_unknown(self, side='left'):
        self.now+=20;self.seq+=1
        sample=frame(self.seq,self.now,**{side:'closed'})
        sample['eye_intent'][side]=dict(value=None,known=False,state='unknown')
        self.assertTrue(self.core.accept(sample,self.now)['accepted'])
        return self.core.tick(self.now)

    def test_logged_pattern_valid_left_wink_survives_right_unknown(self):
        self.wink_mode()
        # Closing can pass through unknown geometry before recognition. The
        # opposite eye also flickers unknown in the user's diagnostic samples.
        self.feed(left='unknown',right='unknown')
        self.hold(3,left='closed',right='unknown')
        snap=self.feed(left='wink',right='unknown')
        self.assertTrue(snap['presentation']['drag_left'])
        self.assertTrue(snap['presentation']['left_known'])
        self.assertFalse(snap['presentation']['eyes_known'])
        self.assertTrue(snap['diagnostics']['eyes']['left']['down'])
        self.assertTrue(snap['diagnostics']['button_actions']['left_eye']['down'])
        self.assertTrue(self.feed(left='wink',right='unknown')['presentation']['drag_left'])
        self.assertFalse(self.feed(left='unknown',right='unknown')['presentation']['drag_left'])
        self.assertFalse(self.feed(left='wink',right='unknown')['presentation']['drag_left'])
        self.feed(right='unknown')  # Only the left eye has to reopen.
        self.assertTrue(self.feed(left='wink',right='unknown')['presentation']['drag_left'])

    def test_brief_recognized_wink_presses_in_same_capture_and_release_is_not_click_pulse(self):
        self.wink_mode()
        self.feed(left='closed')
        self.assertTrue(self.feed(left='wink')['presentation']['drag_left'])
        snap=self.feed()
        self.assertFalse(snap['presentation']['drag_left'])
        self.assertFalse(snap['left_click'])
        self.feed(right='wink')
        self.assertTrue(self.feed()['presentation']['enter'])

    def test_unknown_wink_with_known_geometry_releases_without_repress(self):
        self.wink_mode()
        self.hold(10,left='wink')
        self.assertFalse(self.intent_unknown()['presentation']['drag_left'])
        self.assertFalse(self.hold(10,left='wink')[-1]['presentation']['drag_left'])
        self.feed()
        self.assertTrue(self.feed(left='wink')['presentation']['drag_left'])

    def test_closed_nonwink_releases_without_repressing_until_open(self):
        self.wink_mode()
        self.feed(left='wink')
        self.assertFalse(self.feed(left='closed')['presentation']['drag_left'])
        self.assertFalse(self.hold(35,left='wink')[-1]['presentation']['drag_left'])
        self.feed()
        self.assertTrue(self.feed(left='wink')['presentation']['drag_left'])

    def test_no_press_without_observed_open_and_presentation_cannot_disable_eyes(self):
        self.wink_mode();self.core.disarm();self.core.arm()
        self.assertFalse(self.feed(left='wink',right='unknown')['presentation']['drag_left'])
        self.assertFalse(self.core.gestures.left_button.ready)
        with self.assertRaises(ValueError):
            replace(presentation_mapping(),head_wink_clicks=False)

    def test_short_wink_then_both_eyes_still_suppresses_solo(self):
        self.wink_mode()
        self.feed(left='closed');self.feed(left='wink')
        snaps=self.hold(30,left='closed',right='closed')
        snaps+=self.hold(3,right='wink')+[self.feed()]
        self.assertEqual(self.core.dictation_toggle,1)
        self.assertFalse(any(s['left_click'] or s['presentation']['enter'] for s in snaps))

    def test_capture_counts_keep_brief_action_and_blockers_visible_between_ticks(self):
        self.wink_mode()
        snap=self.feed(left='closed')
        self.assertIn('waiting for calibrated wink',snap['diagnostics']['eye_gesture']['status'])
        self.feed(left='wink');self.feed()
        snap=self.feed()
        counts=snap['diagnostics']['eye_gesture']['counts']
        self.assertEqual(counts['left_action_frames'],1)
        self.assertEqual(counts['left_presses'],1)
        self.assertEqual(counts['left_releases'],1)
        self.assertEqual(counts['clicks'],0)
        for _ in range(5):
            self.assertEqual(self.core.tick(self.now)['diagnostics']['eye_gesture']['counts'],counts)
        snap=self.intent_unknown()
        self.assertIn('Left eye unknown',snap['diagnostics']['eye_gesture']['status'])
        self.assertEqual(snap['diagnostics']['eye_gesture']['counts']['left_unknown_frames'],1)
        self.assertIn('Left eye unknown',snap['instructions'][0]['instruction'])

    def test_wink_gesture_sliders_omit_inapplicable_solo_delay(self):
        lab=Lab(clock=lambda:self.now);self.addCleanup(lab.close)
        lab.select_mapping('presentation')
        mapping=lab.state()['mapping'];mapping['require_wink']=True;lab.update_mapping(mapping)
        self.assertEqual([s.key for s in sliders(lab.state(),'gestures')],['chord_ms'])

    def test_progressive_brake_zero_at_full_no_reverse_or_frame_rate_damping(self):
        velocities=[]
        for openness in (0,.2,.4,.65,1):
            self.core=PresentationProcessor(subject_id='person');self.core.arm();self.feed()
            snap=self.hold(70,head_x=.7,openness=openness)[-1]
            velocities.append(snap['pointer_x']-.5)
        self.assertGreater(velocities[0],velocities[1]);self.assertGreater(velocities[1],velocities[2])
        self.assertEqual(velocities[3:], [0,0])
        self.assertGreater(self.hold(40,head_x=.7)[-1]['pointer_x'],.5)
        self.assertEqual(self.feed(head_x=.7,openness=1)['pointer_x'],.5)
        self.assertEqual(self.feed(head_x=.7,openness=None)['pointer_x'],.5)
        self.assertGreaterEqual(self.feed(head_x=.7)['pointer_x'],.5)

    def test_dictation_freezes_motion_and_waits_for_head_neutral_afterward(self):
        self.hold(30,left='closed',right='closed',head_x=.7)
        snap=self.feed(head_x=.7,openness=1)
        self.assertTrue(snap['dictation_request']['active'])
        self.assertEqual(snap['pointer_x'],.5)
        self.hold(30,left='closed',right='closed',head_x=.7)
        self.assertEqual(self.feed(head_x=.7)['pointer_x'],.5)
        self.feed()
        self.assertGreater(self.hold(30,head_x=.7)[-1]['pointer_x'],.5)

    def test_rejected_capture_cannot_change_anatomical_eye_state(self):
        self.hold(10,left='closed')
        before=self.core.sample
        duplicate=frame(self.seq,self.now,left='unknown',right='unknown')
        self.assertFalse(self.core.accept(duplicate,self.now)['accepted'])
        self.assertIs(self.core.sample,before)
        self.assertTrue(self.core.tick(self.now)['presentation']['eyes_known'])
        self.assertFalse(self.feed()['presentation']['drag_left'])

    def test_startup_reuses_personal_response_without_modifying_saved_profile(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from Processing.target_game.storage import configure_startup
        from Processing.tuning.model import write_profile
        source=Lab(clock=lambda:self.now);self.addCleanup(source.close)
        source.select_mapping('mouse-test')
        mapping=source.processor.mapping
        mapping=replace(mapping,pointer_down_gain=2.7,
                        response=replace(mapping.response,pointer=replace(mapping.response.pointer,exponent=2.1,center_x=.35)))
        source.update_mapping(mapping.to_dict())
        data=profile(source.state(),'Measured head response')
        with TemporaryDirectory() as folder:
            path=Path(folder)/'personal.json';write_profile(path,data);before=path.read_bytes()
            for choice in (None,'presentation'):
                lab=Lab(clock=lambda:self.now);self.addCleanup(lab.close)
                configure_startup(lab,choice,path)
                selected=lab.mappings['presentation']
                self.assertEqual(selected.response,mapping.response)
                self.assertEqual(selected.pointer_down_gain,2.7)
                self.assertFalse(selected.require_wink)
                self.assertFalse(lab.processor.armed)
            self.assertEqual(path.read_bytes(),before)

    def test_migration_profiles_sliders_and_copy_preserve_mode(self):
        old=mouse_test_mapping().to_dict();old['format']='input_mapping_v8';old.pop('presentation')
        self.assertFalse(Mapping.from_dict(old).presentation.enabled)
        lab=Lab(clock=lambda:self.now);self.addCleanup(lab.close)
        lab.select_mapping('presentation')
        state=lab.state();self.assertIsInstance(lab.processor,PresentationProcessor)
        self.assertFalse(state['mapping']['require_wink'])
        for channel in ('mouth_brake','gestures'):
            self.assertTrue(sliders(state,channel));self.assertTrue(steady_curves(state,channel))
            self.assertTrue(response_preview(state,channel));self.assertTrue(live_values(state,channel))
        lab.tune_response('mouth_brake',{'mouth_full':.5},mapping_id='presentation',generation=state['generation'])
        self.assertEqual(lab.processor.mapping.presentation.mouth_full,.5)
        lab.apply_tuning_profile(profile(lab.state(),'Test'))
        self.assertIsInstance(lab.processor,PresentationProcessor)
        self.assertFalse(lab.processor.armed)
        lab.apply_tuning_profile(default_profile(lab.state()))
        self.assertTrue(lab.processor.mapping.presentation.enabled)
        lab.copy_mapping('Talk and browse')
        self.assertTrue(lab.processor.mapping.presentation.enabled)
        self.assertEqual(Mapping.from_dict(lab.state()['mapping']).to_dict(),lab.state()['mapping'])
        for invalid in ({'enabled':1},{'mouth_full':.1,'mouth_start':.2},{'mouth_exponent':float('nan')}):
            with self.assertRaises(ValueError):PresentationConfig(**invalid)
        bad=deepcopy(old);bad['format']='input_mapping_v9'
        with self.assertRaises((ValueError,KeyError)):Mapping.from_dict(bad)
