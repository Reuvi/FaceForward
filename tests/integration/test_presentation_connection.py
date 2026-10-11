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

    def test_compiled_click_enter_drag_and_relative_movement(self):
        self.hold(10,left='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(3),1)
        self.hold(10,right='closed');state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(9),1)
        state=self.hold(35,left='closed')[-1]
        self.assertEqual(state['output']['event_counts'].get(10),1)
        for _ in range(8):
            time.sleep(.01)
            state=self.feed(left='closed',head_x=.7)
        self.assertGreater(state['output']['event_counts'].get(1,0),0)
        self.assertEqual(state['message']['pointer']['mode'],'velocity')
        state=self.feed()
        self.assertEqual(state['output']['event_counts'].get(11),1)
        self.assertEqual(state['output']['event_counts'].get(3),1)
        self.assertEqual(state['output']['held_keys'],0)

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
        self.assertEqual(state['output']['event_counts'].get(3),1)
        self.assertEqual(state['message']['pointer']['x'],.5)

    def test_bad_presentation_payload_is_rejected_before_button_can_press(self):
        from Processing.mouse.output import control_message
        snap=self.lab.processor.tick(self.now)
        message=control_message(snap)
        message['presentation']=dict(enter=True,drag_left=False,eyes_known=False)
        with self.assertRaises(DriverError):self.lab.output.submit(message,self.lab.runtime)
        self.assertFalse(self.lab.output.status().enabled)
