"""Conservative, auditable one-parameter hypotheses and repeated A/B comparison."""
from copy import deepcopy
import hashlib
import json
import statistics

from Processing.tuning.model import edited, validate_profile
from .model import median, summarize


def fingerprint(profile):
    data=deepcopy(profile);data.pop('name',None)
    if data.get('mapping'):data['mapping'].pop('revision',None)
    return hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()


def usable(report):
    trials=report['trials']
    valid=[t for t in trials if t['valid']]
    successes=[t for t in valid if t['success']]
    return (report.get('mode')=='live-head' and report.get('complete') is True
            and len({t['target']['id'] for t in valid})==16 and len(successes)>=12
            and sum(t['target']['size']=='small' for t in successes)>=3
            and sum(t['roughness'] is not None for t in successes)>=12)


def propose(report):
    if not usable(report):
        return dict(changes={},reason='Need a complete live-head round with at least 12 successful targets, including 3 small ones. Practice and interrupted attempts cannot tune.')
    current=report['profile'];config,mapping,_=validate_profile(current)
    if mapping is None or mapping.input_mode!='head-mouse':
        return dict(changes={},reason='Automatic suggestions currently target head-controlled mouse mappings.')
    complete=[t for t in report['trials'] if t['valid'] and t['success']]
    small=[t for t in complete if t['target']['size']=='small']
    summary=summarize(complete)
    overshoot=median([t['overshoot_radii'] for t in complete],0)
    choices=[]
    # Rules propose experiments. Previously rejected candidates are skipped.
    if summary['small_reentries']>=.5:
        if config.pointer.exponent<3:
            choices.append(('exponent',min(3,round(config.pointer.exponent+.15,2)),
                f"Small targets needed {summary['small_reentries']:.2f} re-entries on average. Test a gentler small-motion curve."))
        if mapping.pointer_gain>.5:
            choices.append(('gain',max(.5,round(mapping.pointer_gain*.9,2)),
                'Small targets had repeated re-entries. Test 10% less gain; the comparison will check the travel-time cost.'))
    if overshoot>.4 and mapping.head_motion.enabled and mapping.head_motion.return_brake<.9:
        choices.append(('return_brake',min(.9,round(mapping.head_motion.return_brake+.1,2)),
                        f'Median travel overshot by {overshoot:.2f} target radii. Test stronger return braking.'))
    direction={}
    for name in ('up','down'):
        rows=[t for t in complete if t['target']['direction']==name]
        if len(rows)>=3:
            direction[name]=(median([t['arrival_s']/max(.1,t['difficulty_bits']) for t in rows]),
                             statistics.mean(t['reentries'] for t in rows))
    if (len(direction)==2 and direction['down'][0]>1.4*direction['up'][0]
            and direction['down'][1]<=direction['up'][1]+.25 and mapping.pointer_down_gain<8):
        choices.append(('down_gain',min(8,round(mapping.pointer_down_gain*1.1,2)),
            f"Downward arrival time per difficulty unit was {direction['down'][0]/max(.01,direction['up'][0]):.2f}× upward, without extra re-entries. Test 10% more downward gain."))
    if summary['roughness'] is not None and summary['roughness']>2 and config.pointer.smoothing_ms<80:
        choices.append(('smoothing_ms',min(80,config.pointer.smoothing_ms+5),
            f"Repeated speed/direction changes produced roughness {summary['roughness']:.2f}. Test 5 ms more smoothing; travel speed must remain acceptable."))
    if (summary['arrival_s']>2 and summary['path_efficiency']>.7 and summary['reentries']<.25
          and mapping.pointer_gain<3 and median([t['settling_s'] for t in small],0)<.5):
        choices.append(('gain',min(3,round(mapping.pointer_gain*1.1,2)),
                        'Travel was slow but direct, with stable small targets. Test 10% more gain.'))
    state=dict(mapping=mapping.to_dict(),config=config.to_dict(),raw=None,runtime={'source':'external'})
    rejected=set(report.get('rejected_candidates',[]))
    for key,value,reason in choices:
        _,updated=edited(state,'pointer',{key:value})
        candidate=deepcopy(current);candidate['name']='Target game candidate';candidate['mapping']=updated.to_dict()
        validate_profile(candidate)
        if fingerprint(candidate) not in rejected:
            return dict(changes={key:value},reason=reason,profile=candidate)
    return dict(changes={},reason='No untested adjustment is clearly supported. Keep the baseline and review the saved paths before another change.')


def compare(baseline,candidate):
    if not usable(baseline) or not usable(candidate):
        return dict(better=False,reason='Insufficient usable trials for a comparison.')
    if baseline.get('source_context')!=candidate.get('source_context'):
        return dict(better=False,reason='Camera/calibration context changed; comparison is not matched.')
    if baseline['geometry']!=candidate['geometry']:
        return dict(better=False,reason='Game position/size changed; comparison is not matched.')
    a={t['target']['id']:t for t in baseline['trials'] if t['valid']}
    b={t['target']['id']:t for t in candidate['trials'] if t['valid']}
    keys=[k for k in a.keys()&b.keys() if a[k]['success'] and b[k]['success']]
    if len(keys)<12:return dict(better=False,reason='Need at least 12 matched successful targets.')
    # Trial geometry, not just friendly labels, must match.
    if any(a[k]['target']!=b[k]['target'] for k in keys):
        return dict(better=False,reason='Target geometry changed; repeat the comparison.')
    sa,sb=summarize([a[k] for k in keys]),summarize([b[k] for k in keys])
    # The exact departure point within the home ring varies. Normalize the
    # non-dwell time by each trial's actual distance/target-width difficulty.
    ratios=[(max(.05,b[k]['acquisition_s']-.6)/max(.1,b[k]['difficulty_bits'])) /
            (max(.05,a[k]['acquisition_s']-.6)/max(.1,a[k]['difficulty_bits'])) for k in keys]
    time_ratio=median(ratios)
    completion_ok=sum(t['success'] for t in b.values())>=sum(t['success'] for t in a.values())
    precision_ok=(sb['small_reentries']<=sa['small_reentries']+.1 and sb['reentries']<=sa['reentries']+.1
                  and sb['hold_error_radii']<=sa['hold_error_radii']+.1)
    smooth_ok=sb['roughness']<=sa['roughness']*1.1+.15
    faster=time_ratio<=.95
    steadier=(sa['small_reentries']>=.25 and sb['small_reentries']<=sa['small_reentries']*.8
              and time_ratio<=1.1)
    smoother=(sa['roughness']>=.5 and sb['roughness']<=sa['roughness']*.8 and time_ratio<=1.05)
    better=completion_ok and precision_ok and smooth_ok and (faster or steadier or smoother)
    return dict(better=better,matched=len(keys),time_ratio=time_ratio,baseline=sa,candidate=sb,
                guards=dict(completion=completion_ok,precision=precision_ok,smoothness=smooth_ok),
                reason='Candidate improved with precision and smoothness protected.' if better else
                'Candidate did not show a clear improvement within the speed, precision and smoothness limits.')


def decision(reports):
    if len(reports)!=4 or [r['kind'] for r in reports]!=['A','B','B','A']:
        return dict(complete=False,winner=None,reason='Complete the A → B → B → A comparison before changing defaults.')
    first,second=compare(reports[0],reports[1]),compare(reports[3],reports[2])
    eligible=all(usable(r) for r in reports)
    same_a=fingerprint(reports[0]['profile'])==fingerprint(reports[3]['profile'])
    same_b=fingerprint(reports[1]['profile'])==fingerprint(reports[2]['profile'])
    geometry=all(r['geometry']==reports[0]['geometry'] and r.get('source_context')==reports[0].get('source_context') for r in reports)
    if not (eligible and same_a and same_b and geometry):
        return dict(complete=False,winner=None,comparisons=[first,second],reason='Rounds were not sufficiently complete or matched. Defaults unchanged.')
    winner='B' if first['better'] and second['better'] else 'A'
    original={t['target']['id']:t['acquisition_s'] for t in reports[0]['trials'] if t['valid'] and t['success']}
    repeated={t['target']['id']:t['acquisition_s'] for t in reports[3]['trials'] if t['valid'] and t['success']}
    practice=median([repeated[k]/max(.01,original[k]) for k in original.keys()&repeated.keys()])
    return dict(complete=True,winner=winner,comparisons=[first,second],baseline_repeat_time_ratio=practice,
                reason='Candidate won both comparisons; saved as your personal default.' if winner=='B' else
                'Results were mixed or no better; baseline remains your personal default.')
