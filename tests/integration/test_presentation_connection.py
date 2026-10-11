"""Full gesture → App dictation → compiled driver checks; never live OS/audio."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'processing'))
from gaming_fixtures import frame
from App.mouse_runtime import MouseSession
from App.dictation import DictationController
from Drivers.binding import DriverError
from Drivers.output import default_library


class SpeechFixture:
    def __init__(self):self.events=[];self.starts=0;self.finishes=0;self.cancels=0
    def start(self, **kwargs):self.starts+=1
    def finish(self):self.finishes+=1
    def cancel(self):self.cancels+=1;self.events=[]
    def poll(self):events,self.events=self.events,[];return events
    def emit(self, state, text=''):self.events.append(dict(state=state,text=text,message=state))


@unittest.skipUnless(default_library().is_file(),'Build Drivers first')
class PresentationConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.seq=0
        self.session=MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.lab=self.session.lab
        self.speech=SpeechFixture()
        self.session.dictation=DictationController(self.speech)
        self.lab.interaction=self.session.dictation
        self.lab.select_mapping('presentation')
        self.session.configure_output('dry-run')
        self.lab.settings({'runtime':{'subject_id':'person'}})
        self.lab.action({'action':'arm'})
        self.feed()

    def feed(self, **values):
        self.now+=20;self.seq+=1
        self.session.deliver(frame(self.seq,self.now,**values))
        state=self.lab.state()
        self.assertIsNone(state['output'].get('error'))
        return state

    def hold(self, count=30, **values):
        return [self.feed(**values) for _ in range(count)]

    def start_speech(self):
        states=self.hold(left='closed',right='closed')
        self.assertEqual(self.speech.starts,1)
        self.assertFalse(any(s['output']['event_counts'].get(3,0) or s['output']['event_counts'].get(9,0) for s in states))
        self.feed()
        self.speech.emit('listening')
        self.feed()

    def finish_speech(self, text):
        self.hold(left='closed',right='closed')
        self.assertEqual(self.speech.finishes,1)
        self.speech.emit('final',text)
        return self.feed()

    def test_compiled_left_down_hold_up_enter_and_relative_movement(self):
        state=self.feed(left='closed')
        self.assertEqual(state['output']['event_counts'].get(10),1)
        self.assertEqual(state['output']['event_counts'].get(11,0),0)
        self.hold(10,left='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(11),1)
        self.assertEqual(state['output']['event_counts'].get(3,0),0)
        self.hold(10,right='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(9),1)
        state=self.feed(left='closed')
        self.assertEqual(state['output']['event_counts'].get(10),2)
        for _ in range(8):
            time.sleep(.01)
            state=self.feed(left='closed',head_x=.7)
        self.assertGreater(state['output']['event_counts'].get(1,0),0)
        self.assertEqual(state['message']['pointer']['mode'],'velocity')
        state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(11),2)
        self.assertEqual(state['output']['event_counts'].get(3,0),0)
        self.assertEqual(state['output']['held_keys'],0)

    def test_logged_wink_and_unknown_pattern_reaches_compiled_down_up_once(self):
        mapping=self.lab.state()['mapping'];mapping['require_wink']=True
        self.lab.update_mapping(mapping)
        self.lab.action({'action':'arm'});self.feed()
        self.feed(left='unknown',right='unknown')
        self.hold(3,left='closed',right='unknown')
        state=self.feed(left='wink',right='unknown')
        self.assertEqual(state['output']['event_counts'].get(10),1)
        self.assertEqual(state['output']['event_counts'].get(11,0),0)
        self.assertTrue(state['message']['presentation']['left_known'])
        self.assertFalse(state['message']['presentation']['eyes_known'])
        for _ in range(8):self.lab.step(self.now)
        self.hold(10,left='wink',right='unknown')
        self.assertEqual(self.lab.state()['output']['event_counts'].get(10),1)
        state=self.feed(right='unknown')
        self.assertEqual(state['output']['event_counts'].get(11),1)
        self.assertEqual(state['output']['event_counts'].get(3,0),0)
        self.feed(left='wink',right='unknown')
        state=self.feed(left='unknown',right='unknown')
        self.assertEqual(state['output']['event_counts'].get(11),2)
        self.hold(10,left='wink',right='unknown')
        self.assertEqual(self.lab.state()['output']['event_counts'].get(10),2)
        self.feed();self.feed(left='wink')
        self.hold(30,left='closed',right='closed')
        state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(10),3)
        self.assertEqual(state['output']['event_counts'].get(11),3)
        self.assertEqual(self.speech.starts,1)

    def test_unknown_wink_releases_compiled_drag_without_click(self):
        mapping=self.lab.state()['mapping'];mapping['require_wink']=True
        self.lab.update_mapping(mapping)
        self.lab.action({'action':'arm'});self.feed()
        self.hold(35,left='wink')
        self.now+=20;self.seq+=1
        sample=frame(self.seq,self.now,left='closed')
        sample['eye_intent']['left']=dict(value=None,known=False,state='unknown')
        self.session.deliver(sample)
        state=self.lab.state()
        self.assertEqual(state['output']['event_counts'].get(10),1)
        self.assertEqual(state['output']['event_counts'].get(11),1)
        self.hold(35,left='wink');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(10),1)
        self.assertEqual(state['output']['event_counts'].get(3,0),0)

    def test_dictation_types_one_character_at_a_time_and_enter_is_separate(self):
        from unittest.mock import Mock
        typed=Mock(wraps=self.lab.output.type_character)
        self.lab.output.type_character=typed
        self.start_speech()
        self.speech.emit('partial','Hello')
        state=self.feed(head_x=.8)
        self.assertEqual(state['message']['pointer']['x'],.5)
        self.assertEqual(state['output']['event_counts'].get(12,0),0)
        state=self.finish_speech('Hi é🙂\nthere')
        self.assertEqual(state['output']['event_counts'].get(12,0),1)
        self.assertEqual(state['message']['pointer']['x'],.5)
        states=self.hold(30)
        state=states[-1]
        self.assertEqual(state['output']['event_counts'].get(12),len('Hi é🙂 there'))
        self.assertEqual(''.join(call.args[0] for call in typed.call_args_list),'Hi é🙂 there')
        self.assertEqual(state['output']['event_counts'].get(9,0),0)
        self.assertEqual(state['snapshot']['dictation']['state'],'idle')
        self.assertFalse(any(e['x'] is not None for e in state['output']['events'] if e['type']==12))
        self.hold(10,right='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(9),1)

    def test_stop_during_send_discards_remaining_text_and_never_resumes(self):
        self.start_speech();self.finish_speech('abcdef')
        self.lab.action({'action':'stop'})
        count=self.lab.state()['output']['event_counts'].get(12)
        self.assertEqual(count,1)
        self.assertFalse(self.session.dictation.pending)
        self.lab.action({'action':'arm'});self.hold(30)
        self.assertEqual(self.lab.state()['output']['event_counts'].get(12),count)

    def test_loss_cancels_listening_and_ignores_late_final(self):
        self.start_speech();self.speech.emit('partial','private text')
        self.feed()
        self.now+=20;self.seq+=1;lost=frame(self.seq,self.now);lost['faces']=[]
        self.session.deliver(lost)
        self.assertEqual(self.session.dictation.state,'idle')
        self.assertEqual(self.session.dictation.text,'')
        self.speech.emit('final','private text')
        self.hold(5)
        self.assertEqual(self.lab.state()['output']['event_counts'].get(12,0),0)
        self.assertFalse(self.lab.processor.armed)

    def test_speech_error_never_types_partial_and_requires_a_new_gesture(self):
        self.start_speech();self.speech.emit('partial','do not type')
        self.feed();self.speech.emit('error')
        state=self.feed()
        self.assertEqual(state['snapshot']['dictation']['state'],'error')
        self.assertEqual(state['output']['event_counts'].get(12,0),0)
        self.assertFalse(self.lab.processor.dictating)
        self.assertTrue(state['snapshot']['enabled'])

    def test_sounds_follow_actual_listening_once_and_stop_on_finish(self):
        cues=[];self.session.dictation.cue=cues.append
        self.hold(left='closed',right='closed')
        self.assertEqual(cues,[])  # Starting does not claim the mic is ready.
        self.feed();self.speech.emit('listening');self.feed()
        self.speech.emit('partial','Hi');self.feed()
        self.speech.emit('partial','Hi there');self.feed()
        self.assertEqual(cues,[True])
        self.finish_speech('Hi there');self.hold(30)
        self.assertEqual(cues,[True,False])

    def test_recording_end_error_and_stop_each_emit_one_off_sound(self):
        for end in ('captured','error','stop'):
            with self.subTest(end=end):
                self.lab.action({'action':'stop'});self.lab.action({'action':'arm'});self.feed()
                self.speech.starts=self.speech.finishes=0
                cues=[];self.session.dictation.cue=cues.append
                self.start_speech()
                if end=='stop':self.lab.action({'action':'stop'})
                else:self.speech.emit(end,'Hi');self.feed()
                if end=='captured':
                    self.speech.emit('partial','Hi there');self.feed()
                    self.assertEqual(self.session.dictation.state,'captured')
                self.session.dictation.cancel()
                self.assertEqual(cues,[True,False])

    def test_permission_failure_is_visible_without_a_false_listening_sound(self):
        cues=[];self.session.dictation.cue=cues.append
        self.hold(left='closed',right='closed')
        self.speech.events.append(dict(state='error',message='Allow Speech Recognition',code='speech_permission'))
        state=self.feed()
        self.assertEqual(cues,[])
        self.assertEqual(state['snapshot']['dictation']['error_code'],'speech_permission')
        self.assertIn('Allow',state['snapshot']['dictation']['message'])
        self.assertEqual(state['output']['event_counts'].get(12,0),0)

    def test_uncertain_closing_transition_still_starts_and_finishes_dictation(self):
        self.feed(left='unknown',right='unknown')
        self.start_speech()
        self.feed(left='unknown',right='unknown')
        self.finish_speech('Hello');state=self.hold(20)[-1]
        self.assertEqual(state['output']['event_counts'].get(12),5)

    def test_independent_watchdog_releases_drag_and_aux_calls_cannot_refresh_it(self):
        self.hold(35,left='closed')
        output=self.lab.output
        time.sleep(.3)
        status=output.status()
        self.assertFalse(status.enabled)
        self.assertNotEqual(output.lib.fid_type_character(output.handle,ord('X')),0)
        output.collect()
        self.assertEqual(output.counts[11],1)
        self.assertEqual(output.counts[12],0)

    def test_invalid_auxiliary_commands_release_drag(self):
        self.hold(35,left='closed');output=self.lab.output
        self.assertNotEqual(output.lib.fid_set_presentation(output.handle,1,1),0)
        self.assertFalse(output.status().enabled)
        output.collect();self.assertEqual(output.counts[11],1)

    def test_text_control_character_rejected_and_releases_output(self):
        output=self.lab.output
        with self.assertRaises(DriverError):output.type_character('\n')
        self.assertFalse(output.status().enabled)
        self.assertEqual(output.counts[12],0)

    def test_unsupported_or_preview_dictation_is_visible_without_emitting(self):
        self.session.configure_output('preview')
        self.lab.action({'action':'arm'});self.feed()
        self.hold(left='closed',right='closed')
        self.assertEqual(self.session.dictation.state,'error')
        self.assertIn('Connect',self.session.dictation.message)
        self.assertEqual(self.speech.starts,0)

    def test_actions_attempted_while_sending_do_not_leak_after_completion(self):
        self.start_speech();self.finish_speech('abcdefghijklmnop')
        self.hold(35,right='closed')
        state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(9,0),0)
        self.assertEqual(state['output']['event_counts'].get(3,0),0)
        self.hold(10,right='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(9),1)

    def test_synthetic_source_cannot_start_a_real_speech_provider(self):
        self.session.dictation=DictationController(self.speech,allow_capture=lambda:False)
        self.lab.interaction=self.session.dictation
        self.feed();self.hold(left='closed',right='closed')
        self.assertEqual(self.speech.starts,0)
        self.assertEqual(self.session.dictation.state,'error')
        self.assertIn('Camera',self.session.dictation.message)

    def test_unknown_mouth_stops_pointer_but_click_remains_available(self):
        self.hold(10,left='closed',openness=None,head_x=.7)
        state=self.feed(openness=None,head_x=.7)
        self.assertEqual(state['output']['event_counts'].get(10),1)
        self.assertEqual(state['output']['event_counts'].get(11),1)
        self.assertEqual(state['message']['pointer']['x'],.5)

    def test_bad_presentation_payload_is_rejected_before_button_can_press(self):
        from Processing.mouse.output import control_message
        snap=self.lab.processor.tick(self.now)
        message=control_message(snap)
        message['presentation']=dict(enter=True,drag_left=False,eyes_known=False)
        with self.assertRaises(DriverError):self.lab.output.submit(message,self.lab.runtime)
        self.assertFalse(self.lab.output.status().enabled)

    def test_per_eye_validity_does_not_allow_unknown_held_actions(self):
        from Processing.mouse.output import control_message
        for fields in (
                dict(enter=False,drag_left=True,eyes_known=True,left_known=False,right_known=True),
                dict(enter=True,drag_left=False,eyes_known=True,left_known=True,right_known=False),
                dict(enter=False,drag_left=True,eyes_known=False,left_known=True),
                dict(enter=False,drag_left=True,eyes_known=False,left_known=1,right_known=False)):
            with self.subTest(fields=fields):
                message=control_message(self.lab.processor.tick(self.now))
                message['presentation']=fields
                with self.assertRaises(DriverError):self.lab.output.submit(message,self.lab.runtime)
                self.assertFalse(self.lab.output.status().enabled)

    def test_stop_and_face_loss_release_held_left_and_never_rearm(self):
        self.feed(left='closed')
        self.lab.action({'action':'stop'})
        self.assertEqual(self.lab.output.snapshot()['event_counts'].get(11),1)
        self.hold(3,left='closed')
        self.assertEqual(self.lab.output.snapshot()['event_counts'].get(10),1)
        self.lab.action({'action':'arm'});self.feed();self.feed(left='closed')
        self.now+=20;self.seq+=1;lost=frame(self.seq,self.now);lost['faces']=[]
        self.session.deliver(lost)
        self.assertEqual(self.lab.output.snapshot()['event_counts'].get(11),2)
        self.assertFalse(self.feed()['snapshot']['armed'])

    def test_left_attempt_during_sending_does_not_press_after_completion(self):
        self.start_speech();self.finish_speech('abcdefghijklmnop')
        self.hold(35,left='closed')
        self.assertEqual(self.lab.output.snapshot()['event_counts'].get(10,0),0)
        self.feed()
        self.assertEqual(self.feed(left='closed')['output']['event_counts'].get(10),1)
