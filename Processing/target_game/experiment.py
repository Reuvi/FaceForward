"""Explicit round lifecycle, synchronized scalar telemetry and measured defaults."""
from copy import deepcopy
from datetime import datetime, timezone

from Processing.tuning.model import profile
from .analysis import decision, fingerprint, propose, usable
from .model import Round, summarize
from .storage import DEFAULT_PATH, ROOT, Recorder, atomic_json, save_default, history, remember

KINDS=('A','B','B','A')


def telemetry(state,source):
    snap=state['snapshot'];diag=snap['diagnostics']
    return dict(source=source.get('mode'),source_error=source.get('error'),
                capture_sequence=snap['source_sequence'],capture_ms=snap['source_timestamp_ms'],
                capture_session=snap['session_id'],output_ms=snap['timestamp_ms'],
                head_x=diag.get('head_x',{}).get('raw'),head_y=diag.get('head_y',{}).get('raw'),
                pointer_known=snap.get('known',{}).get('pointer',False),
                pointer_request=[snap['pointer_x'],snap['pointer_y']],
                enabled=snap['enabled'],driver_enabled=state['output'].get('enabled',False),
                driver_mode=state['output']['mode'],driver_error=state['output'].get('error'),
                capture_age_ms=diag.get('age_ms'),eyes=diag.get('eyes'))


def live_problem(state,source):
    mapping=state['mapping'];snap=state['snapshot']
    if source.get('mode')!='camera':return 'Choose Camera for a measured head-control test.'
    if source.get('error'):return 'Camera: '+str(source['error'])
    if not mapping or mapping['input_mode']!='head-mouse':return 'Select Mouse test or a copied head mouse mapping.'
    if state['output']['mode']!='native':return 'Connect Live mouse + keyboard on Signals first.'
    if state['output'].get('error'):return 'Driver: '+state['output']['error']
    if not snap['enabled'] or not state['output'].get('enabled'):return snap['status']
    if not snap.get('known',{}).get('pointer'):return 'Head X or Head Y unavailable; retry after tracking returns.'
    age=snap['diagnostics'].get('age_ms')
    if age is None or not 0<=age<=state['config']['stale_ms']:return 'Head sample is stale.'
    return None


class Experiment:
    def __init__(self, lab, source, *, root=ROOT, default_path=DEFAULT_PATH):
        self.lab=lab;self.source=source;self.root=root;self.default_path=default_path
        self.recorder=None;self.reports=[];self.round=None;self.waiting=False
        self.mode=None;self.baseline=None;self.candidate=None;self.suggestion=None
        self.geometry=None;self.expected=None;self.capture_session=None;self.source_context=None;self.round_profile=None
        self.started=None;self.cursor=0;self.closed=False;self.finished=False
        self.message='Move to each target and hold for 0.6 s. No clicking needed.'
        self.result=None;self.rejected_candidates=[]

    def state(self):
        state=self.lab.state(self.cursor)
        if state['trace']:self.cursor=state['trace'][-1]['id']
        return state

    def begin(self, geometry, *, practice=False, center=False):
        if self.closed or self.finished:raise ValueError('Start a new session for another comparison.')
        if self.round or self.waiting:raise ValueError('A round is already in progress.')
        if len(self.reports)>=4:raise ValueError('Comparison complete')
        Round(geometry['width'],geometry['height'])  # Validate before changing output.
        state=self.state();source=self.source()
        if not self.reports:
            self.mode='practice' if practice else 'live-head'
            self.geometry=deepcopy(geometry)
        elif geometry!=self.geometry:raise ValueError('Keep the same window size and position for every comparison round.')
        if self.mode=='practice' and self.reports:raise ValueError('Practice complete; start a new session to play again.')
        context={key:source.get(key) for key in ('mode','source_generation','calibration_generation')}
        context['capture_session']=state['snapshot']['session_id']
        if self.reports and context!=self.source_context:
            raise ValueError('Camera or calibration changed; start a new baseline.')
        if self.mode=='live-head':
            mapping=state['mapping']
            if source.get('mode')!='camera' or state['output']['mode']!='native':
                raise ValueError('Choose Camera and connect Live mouse + keyboard on Signals first, or use Practice.')
            if not mapping or mapping['input_mode']!='head-mouse':raise ValueError('Select Mouse test for measured tuning.')
            if source.get('error') or state['output'].get('error'):raise ValueError('Resolve the camera/driver error before testing.')
            if self.reports:
                if not self.suggestion or not self.suggestion['changes']:raise ValueError('No supported candidate. Keep baseline or start a new session.')
                if fingerprint(profile(state,'Current'))!=self.expected:
                    raise ValueError('Settings changed outside the game. Start a new baseline.')
                selected=self.candidate if KINDS[len(self.reports)]=='B' else self.baseline
                self.lab.apply_tuning_profile(selected)
            if center and not self.reports:self.lab.action({'action':'center_head_start'})
            elif self.reports or not state['snapshot']['enabled']:self.lab.action({'action':'arm'})
        else:self.lab.action({'action':'stop'})
        self.expected=None if not self.reports else fingerprint(profile(self.state(),'Current'))
        self.waiting=True
        self.message=('Waiting for fresh live control. Keep your head at the same resting pose; open eye actions.'
                      if self.mode=='live-head' else 'Practice with the physical mouse. This data cannot change defaults.')

    def resume(self):
        if self.closed or self.finished:raise ValueError('This session has ended. Start a new session.')
        if not self.round or self.round.phase!='paused':return
        state=self.state()
        if self.mode=='live-head':
            if fingerprint(profile(state,'Current'))!=self.expected:raise ValueError('Settings changed; start a new baseline instead of resuming.')
            if state['output']['mode']!='native' or self.source().get('mode')!='camera':raise ValueError('Restore Camera and Live output before resuming.')
            self.lab.action({'action':'arm'})
        self.waiting=True;self.message='Resuming from home after fresh input. Return to the same head rest position.'

    def poll(self,timestamp,x,y,geometry):
        if self.closed or self.finished or (not self.round and not self.waiting):return
        state=self.state();source=self.source()
        problem=live_problem(state,source) if self.mode=='live-head' else None
        if geometry!=self.geometry:
            if self.round:self.round.pause(timestamp,'Window moved or resized. Restore it before resuming.')
            self.waiting=False;self.message='Window moved or resized. Restore it or start a new session.'
            self.lab.action({'action':'stop'});return
        if self.waiting:
            if problem:
                self.message='Waiting: '+problem
                if not state['snapshot']['armed'] and self.mode=='live-head':
                    self.waiting=False
                    if self.round:self.round.pause(timestamp,problem)
                return
            current=profile(state,'Target game baseline' if not self.reports else 'Target game '+KINDS[len(self.reports)])
            if self.expected and fingerprint(current)!=self.expected:
                self.waiting=False;self.message='Settings changed; start a new baseline.'
                self.lab.action({'action':'stop'});return
            if self.round:
                self.round.resume()
            else:
                if self.recorder is None:self.recorder=Recorder(self.root)
                if self.baseline is None:
                    self.baseline=deepcopy(current)
                    self.rejected_candidates=[r['candidate'] for r in history(self.root)
                        if r['baseline']==fingerprint(current) and r['winner']=='A']
                self.round_profile=current;self.expected=fingerprint(current)
                self.round=Round(geometry['width'],geometry['height']);self.started=timestamp
                self.capture_session=state['snapshot']['session_id']
                if self.source_context is None:
                    self.source_context={key:source.get(key) for key in ('mode','source_generation','calibration_generation')}
                    self.source_context['capture_session']=self.capture_session
                self.recorder.write(dict(event='round_start',index=len(self.reports),kind=KINDS[len(self.reports)],
                                         mode=self.mode,geometry=geometry,source_context=self.source_context,profile=current,profile_hash=self.expected))
            self.waiting=False
        if self.round.phase=='paused':return
        if self.mode=='live-head':
            if fingerprint(profile(state,'Current'))!=self.expected:problem='Settings changed during the round. Start a new baseline.'
            elif state['snapshot']['session_id']!=self.capture_session:problem='Camera session changed. Start a new baseline.'
            elif any(source.get(key)!=self.source_context.get(key) for key in ('source_generation','calibration_generation')):
                problem='Camera or calibration changed. Start a new baseline.'
        if timestamp-self.started>12*60*1000:problem='Round time limit reached; take a break and start again.'
        self.recorder.write(dict(event='sample',round=len(self.reports),time_ms=timestamp,x=x,y=y,
                                 phase=self.round.phase,target_index=self.round.index,
                                 valid_for_trial=problem is None,**telemetry(state,source)))
        if problem:
            self.round.pause(timestamp,problem);self.lab.action({'action':'stop'});self.message=problem
        else:
            self.round.sample(timestamp,x,y)
            if self.round.phase=='paused':
                self.lab.action({'action':'stop'});self.message=self.round.reason
        for event in self.round.drain_events():self.recorder.write(dict(round=len(self.reports),**event))
        if self.round.done:self.finish_round(timestamp)

    def report(self, timestamp, complete):
        return dict(format='pointer_game_round_v1',kind=KINDS[len(self.reports)],mode=self.mode,
                    complete=complete,geometry=self.geometry,source_context=self.source_context,profile=self.round_profile,
                    profile_hash=fingerprint(self.round_profile),created_utc=datetime.now(timezone.utc).isoformat(),
                    started_ms=self.started,ended_ms=timestamp,trials=deepcopy(self.round.trials),
                    summary=summarize(self.round.trials),rejected_candidates=self.rejected_candidates)

    def finish_round(self,timestamp):
        self.lab.action({'action':'stop'})
        report=self.report(timestamp,self.round.index==16)
        self.recorder.report(len(self.reports),report);self.reports.append(report);self.round=None
        self.message='Round saved. Rest before the next round.'
        if self.mode=='practice':
            self.finished=True;self.message='Practice saved. No controller settings changed.'
        elif len(self.reports)==1:
            self.suggestion=propose(report);self.candidate=self.suggestion.get('profile')
            self.message=self.suggestion['reason']
        elif len(self.reports)==4:
            self.result=decision(self.reports)
            if self.result['complete']:
                selected=self.candidate if self.result['winner']=='B' else self.baseline
                self.promote(selected)
                remember(self.root,self.baseline,self.candidate,self.result['winner'],self.recorder.id)
            else:self.lab.apply_tuning_profile(self.baseline)
            self.finished=True;self.message=self.result['reason']
            atomic_json(self.recorder.path/'decision.json',self.result)
        if self.finished:self.recorder.close()

    def promote(self,selected):
        selected=deepcopy(selected);selected['name']='Personal measured head control'
        save_default(selected,self.default_path)
        self.lab.apply_tuning_profile(selected)
        self.expected=fingerprint(profile(self.state(),'Current'))
        atomic_json(self.recorder.path/'selected-profile.json',selected)

    def keep_baseline(self):
        if self.round or self.waiting or len(self.reports)!=1 or not usable(self.reports[0]):
            raise ValueError('Finish a usable live baseline first.')
        if fingerprint(profile(self.state(),'Current'))!=self.expected:
            raise ValueError('Settings changed; start a new baseline.')
        self.promote(self.baseline)
        self.finished=True;self.message='Measured baseline saved as your personal default. No improvement is claimed.'
        atomic_json(self.recorder.path/'decision.json',dict(winner='A',reason=self.message,comparison_complete=False))
        self.recorder.close()

    def cancel(self):
        if self.closed:return
        state=self.state();timestamp=self.lab.clock()
        self.lab.action({'action':'stop'})
        try:
            if self.round and self.recorder:
                self.round.pause(timestamp,'Stopped by user')
                for event in self.round.drain_events():self.recorder.write(dict(round=len(self.reports),**event))
                atomic_json(self.recorder.path/'partial-round.json',self.report(timestamp,False))
            # Never replace settings edited outside this experiment.
            if (not self.finished and self.baseline and self.mode=='live-head' and self.expected
                    and fingerprint(profile(state,'Current'))==self.expected):
                self.lab.apply_tuning_profile(self.baseline)
        finally:
            self.closed=True;self.waiting=False;self.round=None
            if self.recorder:self.recorder.close()
