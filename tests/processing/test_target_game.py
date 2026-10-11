"""Synthetic target paths and injected control telemetry, never human results."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from Processing.mouse.controller import Lab
from Processing.target_game.analysis import compare, decision, fingerprint, propose, usable
from Processing.target_game.experiment import Experiment
from Processing.target_game.model import Round, Target, Trial, course, roughness
from Processing.target_game.storage import analyze_folder, configure_startup, save_default
from Processing.tuning.model import profile, read_profile
from gaming_fixtures import frame

GEOMETRY=dict(width=1000,height=600,origin_x=0,origin_y=0,screen_width=1200,screen_height=800,tk_scaling=1.)


def traverse(round_,tick,*,mistakes=False):
    """tick(x,y) advances virtual time 50 ms and returns current model."""
    for index in range(16):
        for _ in range(12):
            if round_.phase!='home':break
            tick(*round_.home)
        if round_.phase!='target':raise AssertionError(round_.phase)
        target=round_.targets[index];start=round_.home
        for i in range(1,11):tick(start[0]+(target.x-start[0])*i/10,start[1]+(target.y-start[1])*i/10)
        if mistakes and target.size=='small':
            tick(target.x+target.radius+25,target.y);tick(target.x,target.y)
        for _ in range(16):
            if round_.phase!='target':break
            tick(target.x,target.y)
    if not round_.done:raise AssertionError('Round did not finish')


class MetricTests(unittest.TestCase):
    def test_course_is_repeatable_bounded_and_has_four_small_directions(self):
        for width,height in ((640,400),(1000,600),(2400,1300)):
            targets=course(width,height)
            self.assertEqual(targets,course(width,height));self.assertEqual(len(targets),16)
            self.assertEqual(len({t.id for t in targets}),16)
            self.assertEqual({t.direction for t in targets if t.size=='small'},{'up','down','left','right'})
            for t in targets:
                self.assertTrue(t.radius<t.x<width-t.radius)
                self.assertTrue(t.radius<t.y<height-t.radius)
        with self.assertRaises(ValueError):course(300,200)

    def test_arrival_settle_exits_and_continuous_hold(self):
        trial=Trial(Target('r','right','small',100,0,10),0,(0,0),1)
        for t,x in ((0,0),(100,50),(200,100),(250,112),(300,100),(400,100),(500,100),(600,100),(700,100),(800,100),(900,100)):
            trial.sample(t,(x,0))
        result=trial.result(900)
        self.assertTrue(result['success']);self.assertTrue(result['valid'])
        self.assertAlmostEqual(result['arrival_s'],.2)
        self.assertAlmostEqual(result['settling_s'],.1)
        self.assertEqual((result['reentries'],result['exits']),(1,1))
        self.assertAlmostEqual(result['overshoot_radii'],.2)
        self.assertLess(result['path_efficiency'],1)
        self.assertEqual(result['hold_error_radii'],0)

    def test_gap_cannot_complete_a_hold(self):
        trial=Trial(Target('r','right','small',100,0,10),0,(0,0),1)
        trial.sample(0,(0,0));trial.sample(50,(100,0));trial.sample(700,(100,0))
        self.assertFalse(trial.finished)
        self.assertEqual(trial.progress,0)
        result=trial.result(700)
        self.assertFalse(result['valid']);self.assertEqual(result['sampling_gaps'],1)

    def test_roughness_detects_stops_and_direction_reversal_without_polling_rate_bias(self):
        straight=[(t,t/10,0) for t in range(0,1001,10)]
        coarse=straight[::5]
        alternating=[(t,(t//100%2)*10,0) for t in range(0,1001,50)]
        self.assertAlmostEqual(roughness(straight),0)
        self.assertAlmostEqual(roughness(straight),roughness(coarse))
        self.assertGreater(roughness(alternating),roughness(straight)+1)
        self.assertIsNone(roughness([(0,0,0),(200,10,0),(400,20,0)]))

    def test_round_pause_records_invalid_attempt_then_retries_same_target(self):
        model=Round(1000,600)
        for t in range(0,401,50):model.sample(t,500,300)
        self.assertEqual(model.phase,'target')
        model.pause(450,'Head unavailable')
        self.assertFalse(model.trials[0]['valid']);self.assertFalse(model.trials[0]['success'])
        self.assertEqual(model.index,0);model.resume()
        for t in range(500,901,50):model.sample(t,500,300)
        self.assertEqual(model.trial.target.id,model.targets[0].id)
        self.assertEqual(model.trial.attempt,2)

    def test_round_finishes_timeouts_and_invalid_clock_is_rejected(self):
        model=Round(1000,600)
        for t in range(0,401,50):model.sample(t,500,300)
        for t in range(450,20401,50):model.sample(t,500,300)
        self.assertEqual(model.index,1);self.assertTrue(model.trials[0]['timeout'])
        with self.assertRaises(ValueError):model.sample(float('nan'),0,0)
        with self.assertRaises(ValueError):model.sample(20000,0,0)


class Sink:
    """Fake native sink for clock-injected lifecycle tests. Does not load a driver."""
    mode='native'
    def __init__(self):self.enabled=False
    def submit(self,message,runtime):self.enabled=message['enabled']
    def snapshot(self):return dict(mode=self.mode,enabled=self.enabled,error=None)
    def close(self):self.enabled=False
    def pause(self):self.enabled=False


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.seq=0
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.lab=Lab(clock=lambda:self.now);self.addCleanup(self.lab.close)
        self.lab.select_mapping('mouse-test');self.lab.settings({'runtime':{'source':'external','subject_id':'person'}})
        self.lab.set_output(Sink())
        self.source=dict(mode='camera',error=None,source_generation=1,calibration_generation=3)
        self.default=Path(self.folder.name)/'default.json'
        self.e=Experiment(self.lab,lambda:self.source,root=Path(self.folder.name)/'runs',default_path=self.default)
        self.addCleanup(self.e.cancel)

    def tick(self,x=500,y=300,**kwargs):
        self.now+=50;self.seq+=1
        self.lab.ingest(frame(self.seq,self.now,**kwargs))
        self.e.poll(self.now,x,y,GEOMETRY)

    def begin(self):
        self.e.begin(GEOMETRY);self.tick()
        self.assertIsNotNone(self.e.round)
        return self.e.round

    def baseline(self):
        model=self.begin();traverse(model,self.tick,mistakes=True)
        self.assertEqual(len(self.e.reports),1)
        return self.e.reports[0]

    def test_baseline_suggests_one_data_based_change_and_does_not_promote(self):
        report=self.baseline()
        self.assertTrue(usable(report))
        self.assertEqual(self.e.suggestion['changes'],{'exponent':1.95})
        self.assertFalse(self.default.exists())
        self.assertFalse(self.lab.processor.armed)
        self.assertEqual(self.lab.state()['config']['pointer']['exponent'],1.8)
        self.assertTrue((self.e.recorder.path/'round-1.csv').is_file())
        parsed=analyze_folder(self.e.recorder.path)
        self.assertEqual(parsed['suggestion']['changes'],{'exponent':1.95})
        self.assertFalse(parsed['decision']['complete'])

    def test_four_rounds_select_better_candidate_and_restore_default_without_arming(self):
        self.baseline()
        for mistakes in (False,False,True):
            model=self.begin();traverse(model,self.tick,mistakes=mistakes)
        self.assertTrue(self.e.finished);self.assertEqual(self.e.result['winner'],'B')
        data=read_profile(self.default)
        self.assertEqual(data['mapping']['response']['pointer']['exponent'],1.95)
        self.assertEqual(self.lab.state()['config']['pointer']['exponent'],1.95)
        self.assertFalse(self.lab.processor.armed)
        self.assertTrue((self.e.recorder.path/'decision.json').is_file())
        self.assertEqual(len(analyze_folder(self.e.recorder.path)['rounds']),4)

    def test_failed_adjustment_is_skipped_in_later_matching_baselines(self):
        from Processing.target_game.storage import history, remember
        report=self.baseline()
        remember(self.e.root,self.e.baseline,self.e.candidate,'A','synthetic-prior-test')
        records=history(self.e.root)
        report=deepcopy(report);report['rejected_candidates']=[records[0]['candidate']]
        suggestion=propose(report)
        self.assertEqual(suggestion['changes'],{'gain':1.26})
        report['rejected_candidates'].append(fingerprint(suggestion['profile']))
        next_suggestion=propose(report)
        self.assertNotIn('exponent',next_suggestion['changes'])
        self.assertNotIn('gain',next_suggestion['changes'])

    def test_candidate_must_win_both_comparisons(self):
        a=self.baseline();b=deepcopy(a);b['kind']='B';b['profile']=self.e.candidate
        for t in b['trials']:
            t['acquisition_s']*=.8;t['reentries']=0;t['roughness']=0
        a2=deepcopy(a);a2['kind']='A'
        b2=deepcopy(b)
        for t in b2['trials']:t['acquisition_s']*=2
        verdict=decision([a,b,b2,a2]);self.assertTrue(verdict['complete']);self.assertEqual(verdict['winner'],'A')
        worse=deepcopy(b)
        for t in worse['trials']:t['reentries']=10
        self.assertFalse(compare(a,worse)['better'])
        changed=deepcopy(b);changed['geometry']['origin_x']=5
        self.assertFalse(compare(a,changed)['better'])

    def test_practice_cannot_suggest_or_promote(self):
        self.source['mode']='demo';self.e.begin(GEOMETRY,practice=True);self.tick()
        traverse(self.e.round,self.tick,mistakes=True)
        self.assertFalse(usable(self.e.reports[0]))
        self.assertEqual(propose(self.e.reports[0])['changes'],{})
        self.assertFalse(self.default.exists());self.assertTrue(self.e.finished)
        with self.assertRaises(ValueError):self.e.keep_baseline()

    def test_unknown_input_pauses_and_records_null_without_auto_resume(self):
        model=self.begin()
        for _ in range(8):self.tick()
        self.tick(head_y=None)
        self.assertEqual(model.phase,'paused');self.assertFalse(self.lab.processor.armed)
        self.tick();self.assertEqual(model.phase,'paused')
        rows=[json.loads(line) for line in (self.e.recorder.path/'cursor.jsonl').read_text().splitlines()]
        invalid=[r for r in rows if r['event']=='sample' and not r['valid_for_trial']]
        self.assertIsNone(invalid[-1]['head_y'])
        self.e.resume();self.tick();self.assertEqual(model.phase,'home')

    def test_source_calibration_and_geometry_changes_cannot_score(self):
        model=self.begin();self.source['calibration_generation']+=1;self.tick()
        self.assertEqual(model.phase,'paused')
        self.assertIn('calibration',model.reason)
        self.assertFalse(self.lab.processor.enabled)

    def test_round_layout_change_pauses_before_scoring(self):
        model=self.begin()
        self.now+=50
        self.e.poll(self.now,500,300,dict(GEOMETRY,width=1100))
        self.assertEqual(model.phase,'paused')
        self.assertFalse(self.lab.processor.armed)

    def test_cancel_candidate_restores_baseline_but_preserves_unrelated_edits(self):
        self.baseline();self.begin()
        self.assertEqual(self.lab.processor.config.pointer.exponent,1.95)
        self.e.cancel()
        with self.assertRaisesRegex(ValueError,'ended'):self.e.resume()
        self.assertFalse(self.lab.processor.armed)
        self.assertEqual(self.lab.processor.config.pointer.exponent,1.8)
        self.assertFalse(self.default.exists())
        self.assertTrue((self.e.recorder.path/'partial-round.json').is_file())
        # A second experiment must not overwrite settings chosen elsewhere.
        other=Experiment(self.lab,lambda:self.source,root=self.folder.name,default_path=self.default)
        other.baseline=profile(self.lab.state(),'Before');other.expected=fingerprint(other.baseline);other.mode='live-head'
        state=self.lab.state();self.lab.tune_response('pointer',{'gain':2.5},mapping_id=state['mapping_id'],generation=state['generation'])
        other.cancel();self.assertEqual(self.lab.state()['mapping']['pointer_gain'],2.5)

    def test_default_load_honors_explicit_mapping_and_never_arms(self):
        self.baseline();self.e.keep_baseline()
        original=profile(self.lab.state(),'Saved')
        fresh=Lab(clock=lambda:self.now);self.addCleanup(fresh.close)
        configure_startup(fresh,None,self.default)
        self.assertEqual(fresh.mapping_id,'mouse-test');self.assertFalse(fresh.processor.armed)
        self.assertEqual(fresh.state()['config'],original['mapping']['response'])
        configure_startup(fresh,'gaming-keyboard-mouse-1',self.default)
        self.assertEqual(fresh.mapping_id,'gaming-keyboard-mouse-1')
        self.default.write_text('{invalid')
        configure_startup(fresh,'mouse-test',self.default,factory=True)
        self.assertEqual(fresh.mapping_id,'mouse-test')
        self.assertFalse(fresh.processor.armed)
        with self.assertRaises(ValueError):configure_startup(fresh,None,self.default)
        self.assertFalse(fresh.processor.armed)

    def test_invalid_default_type_and_tampered_report_rejected(self):
        self.baseline()
        target=self.e.recorder.path/'round-1.json';data=json.loads(target.read_text())
        data['profile']['mapping']['pointer_gain']=2.5;target.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'fingerprint'):analyze_folder(target.parent)
        self.lab.select_mapping('gaming-keyboard-mouse-1')
        with self.assertRaises(ValueError):save_default(profile(self.lab.state(),'Gaming'),self.default)

    def test_synthetic_or_disconnected_output_is_not_a_live_head_test(self):
        for key,value in (('mode','demo'),('error','camera failure')):
            old=self.source[key];self.source[key]=value
            with self.assertRaises(ValueError):self.e.begin(GEOMETRY)
            self.source[key]=old
        self.lab.set_output(None)
        with self.assertRaises(ValueError):self.e.begin(GEOMETRY)
