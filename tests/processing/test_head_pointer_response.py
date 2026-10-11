from copy import deepcopy
from dataclasses import replace
import math
import unittest

from Processing.mappings.config import HeadMotionConfig, Mapping, mouse_test_mapping
from Processing.mappings.engine import HeadMouseProcessor
from Processing.mappings.head_pointer import HeadPointerFilter
from Processing.mouse.engine import AxisFilter, length
from gaming_fixtures import frame


class HeadPointerResponseTests(unittest.TestCase):
    def make_filter(self, **options):
        mapping=mouse_test_mapping()
        return HeadPointerFilter(mapping.response.pointer, mapping.head_motion,
                                 gain=mapping.pointer_gain, down_gain=mapping.pointer_down_gain, **options)

    @staticmethod
    def capture(f,t,x=.5,y=.5,dt=.02):
        f.push((x,y),t)
        return f.step(t,0,dt)

    def test_fast_outward_turn_boosts_more_than_slow_turn_at_same_position(self):
        results=[]
        for duration in (160,1600):
            f=self.make_filter();self.capture(f,0)
            for i in range(1,duration//20+1):
                self.capture(f,i*20,x=.5+.25*i*20/duration)
            results.append((f.target[0],f.motion_state.copy()))
        self.assertGreater(results[0][0],results[1][0]*1.5)
        self.assertEqual(results[0][1]['phase'],'accelerating')
        self.assertEqual(results[1][1]['multiplier'],1)

    def test_stationary_head_keeps_original_steady_speed(self):
        f=self.make_filter();self.capture(f,0)
        self.capture(f,20,x=.7);self.assertGreater(f.motion_state['multiplier'],1)
        old=AxisFilter(f.config,2,gain=f.gain,down_gain=3,adaptive=True)
        for i in range(2,80):
            self.capture(f,i*20,x=.7)
            self.capture(old,i*20,x=.7)
        self.assertEqual(f.motion_state['multiplier'],1)
        self.assertEqual(f.motion_state['phase'],'steady')
        self.assertAlmostEqual(f.velocity[0],old.velocity[0],places=5)

    def test_return_never_gets_outward_boost_and_stops_without_reversal(self):
        f=self.make_filter();old=AxisFilter(f.config,2,gain=f.gain,down_gain=3,adaptive=True)
        for i in range(20):
            for filt in (f,old):self.capture(filt,i*20,x=.8)
        response=[];baseline=[]
        for i in range(1,7):
            x=.8-i*.05
            response.append(self.capture(f,380+i*20,x=x)[0])
            baseline.append(self.capture(old,380+i*20,x=x)[0])
            self.assertEqual(f.motion_state['multiplier'],1)
            self.assertGreater(f.motion_state['braking'],0)
        self.assertLess(sum(response),sum(baseline)*.8)
        self.assertTrue(all(0 <= a <= b for a,b in zip(response[1:],response)))
        for i in range(1,16):
            self.capture(f,500+i*20)
            self.assertGreaterEqual(f.velocity[0],0)
        self.assertEqual(f.velocity,(0,0))

    def test_both_axes_diagonals_inversion_and_down_gain_keep_bounded_direction(self):
        for dx,dy in ((.2,0),(-.2,0),(0,.2),(0,-.2),(.2,.2),(-.2,-.2)):
            for inverted in (False,True):
                f=self.make_filter();f.config=replace(f.config,invert_x=inverted,invert_y=inverted)
                self.capture(f,0)
                for i in range(1,9):
                    value=self.capture(f,i*20,x=.5+dx*i/8,y=.5+dy*i/8)
                    self.assertLessEqual(length(value),1+1e-12)
                for output,direction in zip(value,(dx,dy)):
                    if direction:self.assertGreater(output*direction*(-1 if inverted else 1),0)
                self.assertGreater(f.motion_state['multiplier'],1)
        # The 3x downward response must not look like 3x physical head speed.
        a,b=self.make_filter(),self.make_filter()
        for i in range(9):
            self.capture(a,i*20,y=.5+i*.01)
            self.capture(b,i*20,x=.5+i*.01)
        self.assertAlmostEqual(a.motion_state['radial_speed'],b.motion_state['radial_speed'])

    def test_neutral_noise_and_deflected_jitter_do_not_accelerate(self):
        f=self.make_filter()
        for i in range(60):
            value=self.capture(f,i*20,x=.5+.003*math.sin(i),y=.5+.003*math.cos(i))
            self.assertEqual(value,(0,0))
            self.assertEqual(f.motion_state['multiplier'],1)
        self.capture(f,1200,x=.7)
        for i in range(1,60):
            self.capture(f,1200+i*20,x=.7+(.001 if i%2 else -.001))
            self.assertEqual(f.motion_state['multiplier'],1)

    def test_captured_speed_is_independent_of_camera_rate_and_output_ticks(self):
        states=[]
        for capture_ms in (10,20,40):
            for output_ms in (5,10):
                f=self.make_filter();self.capture(f,0)
                for t in range(output_ms,241,output_ms):
                    if t%capture_ms==0:f.push((.5+t/1000,.5),t)
                    f.step(t,0,output_ms/1000)
                states.append(f.motion_state)
        for state in states:
            self.assertAlmostEqual(state['radial_speed'],2)
            self.assertAlmostEqual(state['multiplier'],1.75)

    def test_repeated_ticks_expire_response_and_same_timestamp_replaces_sample(self):
        f=self.make_filter();self.capture(f,0)
        self.capture(f,40,x=.6)
        self.assertGreater(f.motion_state['multiplier'],1)
        f.push((.5,.5),40);f.step(40,0,0)
        self.assertEqual(len(f.history),2)
        self.assertEqual(f.motion_state['multiplier'],1)
        self.capture(f,60,x=.7)
        self.assertGreater(f.motion_state['multiplier'],1)
        for t in range(70,211,10):f.step(t,0,.01)
        self.assertEqual(f.motion_state['multiplier'],1)
        self.assertEqual(len(f.history),3)
        self.capture(f,220,x=.2)
        self.assertEqual(f.motion_state['multiplier'],1)  # Cross-neutral reversal.

    def test_unknown_clears_speed_history_and_staleness_requires_rearm(self):
        core=HeadMouseProcessor(subject_id='person');core.arm()
        def feed(seq,t,**values):
            self.assertTrue(core.accept(frame(seq,t,**values),t)['accepted'])
            return core.tick(t)
        feed(1,1000);feed(2,1020,head_x=.6)
        self.assertGreater(core.pointer.motion_state['multiplier'],1)
        snap=feed(3,1040,head_y=None)
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
        self.assertEqual(core.pointer.motion_state['multiplier'],1)
        feed(4,1060,head_x=.7)
        self.assertEqual(core.pointer.motion_state['multiplier'],1)
        self.assertFalse(core.tick(1311)['armed'])
        self.assertFalse(feed(5,1320)['armed'])
        core.arm();snap=feed(6,1340)
        self.assertTrue(snap['enabled'])
        self.assertEqual(core.pointer.motion_state['multiplier'],1)

    def test_off_switch_matches_previous_filter_and_v4_import_keeps_it_off(self):
        mapping=mouse_test_mapping()
        legacy=mapping.to_dict();legacy['format']='input_mapping_v4';del legacy['head_motion'];del legacy['head_wink_clicks'];del legacy['require_wink'];del legacy['button_bindings'];del legacy['presentation']
        loaded=Mapping.from_dict(legacy)
        self.assertFalse(loaded.head_motion.enabled)
        core=HeadMouseProcessor(loaded,subject_id='person')
        self.assertIs(type(core.pointer),AxisFilter)
        reference=AxisFilter(loaded.response.pointer,2,gain=loaded.pointer_gain,down_gain=3,adaptive=True)
        for i in range(40):
            x=.5+.25*math.sin(i*.2);y=.5+.1*math.cos(i*.2)
            self.assertEqual(self.capture(core.pointer,i*20,x,y),self.capture(reference,i*20,x,y))
        self.assertEqual(Mapping.from_dict(mapping.to_dict()),mapping)
        for update in ({'enabled':1},{'speed_gain':float('nan')},{'return_brake':-1},{'speed_gain':3}):
            bad=deepcopy(mapping.to_dict());bad['head_motion'].update(update)
            with self.assertRaises(ValueError):Mapping.from_dict(bad)
        with self.assertRaises(ValueError):replace(Mapping(),head_motion=HeadMotionConfig(enabled=True))
