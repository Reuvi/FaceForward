from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest

from Processing.mappings.config import Mapping, HeadConfig, mouse_test_mapping
from Processing.mappings.engine import GamingProcessor
from Processing.mappings.target import TargetFilter
from Processing.mouse.config import AxisConfig
from Processing.mouse.output import control_message
from gaming_fixtures import frame


class TargetPointerTests(unittest.TestCase):
    def setUp(self):
        mapping = Mapping(head_x=HeadConfig(smoothing_ms=0, confirmation_ms=0),
                          head_y=HeadConfig(smoothing_ms=0, confirmation_ms=0))
        self.core = GamingProcessor(mapping, subject_id='person')
        self.now = 1000.
        self.seq = 0
        self.core.arm()

    def feed(self, **values):
        self.now += 20; self.seq += 1
        self.assertTrue(self.core.accept(frame(self.seq, self.now, **values), self.now)['accepted'])
        return self.core.tick(self.now)

    def test_start_at_any_fresh_destination_and_steady_input_never_integrates(self):
        snap = self.feed(x=.6, y=.53)
        self.assertTrue(snap['enabled'])
        self.assertAlmostEqual(snap['pointer_x'], .7)
        self.assertAlmostEqual(snap['pointer_y'], .74)
        destination = control_message(snap)['pointer']
        for _ in range(150):
            snap = self.feed(x=.6, y=.53)
            self.assertEqual(control_message(snap)['pointer'], destination)
        self.assertIn('screen X 70.0%', snap['instructions'][-2]['instruction'])

    def test_compressed_downward_range_reaches_every_corner_after_moving(self):
        for adaptive in (True, False):
            self.core = GamingProcessor(replace(Mapping(), adaptive_pointer=adaptive), subject_id='person')
            self.core.arm(); self.feed()
            for x,y,expected in ((.25,.5625,(0,1)),(.75,.5625,(1,1)),(.75,.25,(1,0)),(.25,.25,(0,0))):
                for _ in range(30):
                    snap = self.feed(x=x,y=y)
                    self.assertTrue(0 <= snap['pointer_x'] <= 1 and 0 <= snap['pointer_y'] <= 1)
                self.assertEqual((snap['pointer_x'],snap['pointer_y']),expected)
                # Raw inputs are evidence; only destination coordinates expand.
                self.assertEqual(snap['diagnostics']['raw_pointer'],[x,y])

    def test_default_filter_responds_without_old_interpolation_delay(self):
        self.feed()
        snap = self.feed(x=.6, y=.53)
        self.assertGreater(snap['pointer_x'], .55)
        self.assertGreater(snap['pointer_y'], .55)
        self.assertEqual(snap['diagnostics']['pointer_interpolation_ms'],0)
        self.assertEqual(snap['diagnostics']['pointer_smoothing_ms'],20)

    def test_downward_boost_precedes_inversion_and_preserves_up_and_center(self):
        for inverted, expected in ((False,(.5,.74)),(True,(.5,.26))):
            mapping = Mapping(target_smoothing_ms=0, target_jitter=0)
            mapping = replace(mapping,response=replace(mapping.response,
                              pointer=replace(mapping.response.pointer,invert_y=inverted)))
            self.core=GamingProcessor(mapping,subject_id='person');self.core.arm()
            snap=self.feed()
            self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.5,.5))
            snap=self.feed(y=.53)
            self.assertAlmostEqual(snap['pointer_y'],expected[1])
            snap=self.feed(y=.47)
            self.assertAlmostEqual(snap['pointer_y'],.56 if inverted else .44)

    def test_fixation_dead_band_is_around_each_destination_not_screen_center(self):
        for center in ((.1,.2),(.8,.9),(.5,.5)):
            f = TargetFilter(AxisConfig(smoothing_ms=0), jitter=.01)
            f.push(center, 0); initial = f.step(0, 0, 0)
            for i in range(1,101):
                offset = .004 if i%2 else -.004
                f.push((center[0]+offset, center[1]-offset), i*20)
                self.assertEqual(f.step(i*20, 0, .02), initial)
            f.push((center[0]+.025,center[1]), 2020)
            self.assertNotEqual(f.step(2020,0,.02),initial)

    def test_smoothing_converges_without_overshoot_and_endpoints_are_reachable(self):
        for adaptive in (True, False):
            f = TargetFilter(AxisConfig(), adaptive=adaptive, jitter=0)
            f.push((.2,.2),0);f.step(0,0,0)
            values=[]
            for i in range(1,180):
                f.push((1,0),i*20)
                point = f.step(i*20,0,.02)
                values.append(point[0])
                self.assertTrue(all(-1 <= v <= 1 for v in point))
            self.assertEqual(values,sorted(values))
            self.assertAlmostEqual(values[-1],1,places=5)

    def test_invalid_stops_travel_without_center_command_and_keys_stay_independent(self):
        self.feed(x=.8)
        snap = self.feed(x=.8,head_y=.8)
        self.assertEqual(snap['keys']['w'],1)
        snap = self.feed(x=None,head_y=.8)
        self.assertEqual(control_message(snap)['pointer'], dict(mode='target', x=.5, y=.5, speed=0))
        self.assertFalse(snap['known']['pointer'])
        self.assertEqual(snap['keys']['w'],1)
        snap = self.core.tick(self.now+251)
        self.assertFalse(snap['armed'])
        self.assertFalse(any(snap['keys'].values()))
        self.assertEqual(snap['target_speed'],0)
        self.now += 251
        self.assertFalse(self.feed(x=.8)['armed'])

    def test_gain_inversion_same_timestamp_and_loss_do_not_replay_history(self):
        f = TargetFilter(AxisConfig(smoothing_ms=0,invert_x=True), gain=2, jitter=0)
        f.push((.6,.4),0);f.push((.7,.3),0)
        point=f.step(0,0,0)
        self.assertAlmostEqual(point[0],-.8);self.assertAlmostEqual(point[1],-.8)
        self.assertEqual(len(f.history),1)
        f.push(None,20);self.assertEqual(f.step(20,0,.02),(0,0))
        f.push((.2,.8),40)
        self.assertEqual(f.step(40,0,.02),(1,1))

    def test_button_head_start_gates_and_mapping_migration(self):
        self.assertFalse(self.feed(left='wink',x=.8)['enabled'])
        self.assertFalse(self.feed(head_x=.8,x=.8)['enabled'])
        self.assertTrue(self.feed(x=.8)['enabled'])
        current=Mapping().to_dict()
        for version in ('input_mapping_v1','input_mapping_v2'):
            old=deepcopy(current);old['format']=version
            for key in ('pointer_down_gain','target_smoothing_ms','target_interpolation_ms','head_motion'):del old[key]
            del old['pointer_mode'];del old['target_jitter']
            if version.endswith('v1'):
                del old['input_mode'];del old['adaptive_pointer']
            self.assertEqual(Mapping.from_dict(old).pointer_mode,'velocity')
        old=deepcopy(current);old['format']='input_mapping_v3'
        for key in ('pointer_down_gain','target_smoothing_ms','target_interpolation_ms','head_motion'):del old[key]
        old.update(pointer_gain=1,target_jitter=.01)
        migrated=Mapping.from_dict(old)
        self.assertEqual((migrated.pointer_down_gain,migrated.target_smoothing_ms,migrated.target_interpolation_ms),(1,90,50))
        self.assertEqual(Mapping.from_dict(migrated.to_dict()),migrated)
        self.core=GamingProcessor(migrated,subject_id='person');self.core.arm()
        snap=self.feed(x=.8,y=.9)
        self.assertEqual((snap['pointer_x'],snap['pointer_y']),(.8,.9))
        for key,value in (('pointer_mode','absolute'),('target_jitter',True),('target_jitter',float('nan')),('target_jitter',.2),
                          ('pointer_down_gain',0),('pointer_down_gain',True),('pointer_down_gain',float('inf')),
                          ('target_smoothing_ms',-1),('target_smoothing_ms',float('nan')),
                          ('target_interpolation_ms',250),('target_interpolation_ms',True)):
            bad=deepcopy(current);bad[key]=value
            with self.assertRaises(ValueError):Mapping.from_dict(bad)
        self.assertEqual(mouse_test_mapping().pointer_mode,'velocity')
        with self.assertRaises(ValueError):replace(mouse_test_mapping(),pointer_mode='target')

    def test_simulated_playground_arrives_and_unknown_does_not_pull_to_center(self):
        from Processing.mouse.desktop import DesktopLab
        ui=SimpleNamespace(playground=SimpleNamespace(winfo_width=lambda:1000,winfo_height=lambda:700),
                           sim=dict(x=.5,y=.5,t=None,scroll=0,left=0,right=0,prev_left=0,prev_right=0))
        def row(t,x=.8,y=.25,speed=1):
            return dict(t=t,pointer_mode='target',target_speed=speed,out_x=x,out_y=y,
                        out_scroll=.5,left_out=0,right_out=0)
        DesktopLab.integrate(ui,[row(i*.02) for i in range(100)],dict(pointer_speed=900,scroll_speed=480))
        self.assertAlmostEqual(ui.sim['x'],.8);self.assertAlmostEqual(ui.sim['y'],.25)
        before=(ui.sim['x'],ui.sim['y'])
        DesktopLab.integrate(ui,[row(2+i*.02,.5,.5,0) for i in range(10)],dict(pointer_speed=900,scroll_speed=480))
        self.assertEqual((ui.sim['x'],ui.sim['y']),before)
