"""Display-only curve and response previews using the actual Processing filters."""
from dataclasses import replace

from Processing.mouse.config import MouseConfig
from Processing.mouse.engine import AxisFilter, EyeGate, axis_target
from Processing.mappings.config import Mapping
from Processing.mappings.engine import HeadGate
from Processing.mappings.head_pointer import HeadPointerFilter
from Processing.mappings.target import TargetFilter
from .model import legacy_eye_timing


def filter_for(state,channel):
    config=MouseConfig.from_dict(state['config'])
    mapping=Mapping.from_dict(state['mapping']) if state['mapping'] else None
    if channel=='scroll':return AxisFilter(config.scroll,1),config.interpolation_ms
    if mapping:
        args=dict(gain=mapping.pointer_gain,down_gain=mapping.pointer_down_gain,adaptive=mapping.adaptive_pointer)
        if mapping.pointer_mode=='target':
            return TargetFilter(replace(config.pointer,smoothing_ms=mapping.target_smoothing_ms),
                                jitter=mapping.target_jitter,delay_ms=mapping.target_interpolation_ms,**args),mapping.target_interpolation_ms
        if mapping.input_mode=='head-mouse' and mapping.head_motion.enabled:
            return HeadPointerFilter(config.pointer,mapping.head_motion,**args),config.interpolation_ms
        return AxisFilter(config.pointer,2,**args),config.interpolation_ms
    return AxisFilter(config.pointer,2),config.interpolation_ms


def steady_curves(state,channel):
    if channel == 'mouth_brake':
        config=Mapping.from_dict(state['mapping']).presentation
        return {'Resistance':[(i/100,config.brake(i/100)) for i in range(101)]}
    if channel == 'gestures':return {'OFF / ON':[(0,0),(1,1)]}
    if channel in ('left','right','mouth'):return {'ON/OFF':[(0,0),(1,1)]}
    if channel.startswith('head_'):
        config=getattr(Mapping.from_dict(state['mapping']),channel)
        return {name:[(x/100,1 if 2*x/100-1>=threshold else 0 if 2*x/100-1<=-threshold else .5)
                      for x in range(101)] for name,threshold in (('Press',config.activation),('Release',config.release))}
    filt,_=filter_for(state,channel)
    lines={}
    for axis in range(filt.dimensions):
        points=[]
        for i in range(101):
            value=i/100
            raw=[filt.config.center_y] if filt.dimensions==1 else [filt.config.center_x,filt.config.center_y]
            raw[axis]=value
            signed=filt.normalize(raw)
            if isinstance(filt,TargetFilter):output=tuple(max(-1,min(1,v*filt.gain)) for v in signed)
            else:_,output=axis_target(signed,filt.config,gain=filt.gain)
            points.append((value,(output[axis]+1)/2))
        lines['Scroll' if filt.dimensions==1 else ('X','Y')[axis]]=points
    return lines


def response_preview(state,channel):
    """Synthetic outward turn, hold and return. Never feeds the live controller."""
    if channel in ('left','right') and (state.get('mapping') or {}).get('presentation',{}).get('enabled'):
        from Processing.mappings.presentation import EyeGestures
        gestures=EyeGestures();config=Mapping.from_dict(state['mapping']).presentation
        raw=[];out=[]
        for t in range(0,2501,10):
            closed=200<=t<800
            gestures.sample(closed if channel=='left' else False, closed if channel=='right' else False,t,config)
            raw.append((t/1000,int(closed)))
            out.append((t/1000,int((gestures.click or gestures.drag) if channel=='left' else gestures.enter)))
        return {'Eye closure':raw,'Command':out}
    if channel in ('left','right','mouth'):
        eye=EyeGate(None if channel=='mouth' else getattr(MouseConfig.from_dict(state['config']),channel+'_eye'))
        raw=[];out=[]
        for t in range(0,2501,10):
            closed=200<=t<800
            eye.sample(closed,t,instant=channel=='mouth',appearance_intent=not legacy_eye_timing(state),reopened=not closed)
            raw.append((t/1000,int(closed)));out.append((t/1000,int(eye.down)))
        return {'Mouth open' if channel=='mouth' else 'Eye action':raw,'Command':out}
    if channel == 'mouth_brake':
        config=Mapping.from_dict(state['mapping']).presentation
        raw=[(t/1000, max(0,min(1,(t-200)/600)) if t<1200 else max(0,1-(t-1200)/600)) for t in range(0,2501,10)]
        return {'Opening':raw, 'Resistance':[(t,config.brake(value)) for t,value in raw]}
    if channel == 'gestures':
        from Processing.mappings.presentation import EyeGestures
        gestures=EyeGestures();config=Mapping.from_dict(state['mapping']).presentation
        result={'Both closed':[], 'Toggle':[]}
        for t in range(0,2501,10):
            closed=300<=t<1800
            gestures.sample(closed,closed,t,config)
            result['Both closed'].append((t/1000,int(closed)))
            result['Toggle'].append((t/1000,int(gestures.toggle)))
        return result
    head=channel.startswith('head_')
    if head:
        gates=[HeadGate(getattr(Mapping.from_dict(state['mapping']),channel))]
        dimensions=1
    else:
        f,delay=filter_for(state,channel)
        dimensions=f.dimensions
        gates=[f] if dimensions==1 else [f,filter_for(state,channel)[0]]
    result={'Input':[]}
    names=['Key direction'] if head else ['Scroll'] if dimensions==1 else ['X','Y']
    result.update({name:[] for name in names})
    next_capture=0
    for t in range(0,2501,10):
        amount=max(0,min(1,(t-150)/150)) if t<800 else max(0,1-(t-800)/200)
        value=.5+.3*amount
        result['Input'].append((t/1000,value))
        capture=t>=next_capture
        if capture:next_capture+=1000/30
        for axis,(name,gate) in enumerate(zip(names,gates)):
            if head:
                if capture:gate.sample(value,t,True)
                output=(gate.direction+1)/2
            else:
                centers=[gate.config.center_y] if dimensions==1 else [gate.config.center_x,gate.config.center_y]
                # The synthetic relative turn starts/ends at the saved center.
                centers[axis]+=(1-centers[axis])*.6*amount
                raw=centers[0] if dimensions==1 else tuple(centers)
                if capture:gate.push(raw,t)
                output=(gate.step(t,delay,.01)[axis if dimensions==2 else 0]+1)/2
            result[name].append((t/1000,output))
    return result


def live_values(state,channel):
    snap=state['snapshot'];diag=snap['diagnostics']
    if channel=='mouth_brake':
        brake=diag.get('mouth_brake',{})
        return [('Resistance',brake.get('openness'),brake.get('resistance') if brake.get('known') else None)]
    if channel=='gestures':
        request=snap.get('dictation_request',{})
        return [('Dictation',int(request.get('active',False)),int(request.get('active',False)))]
    if channel=='pointer':
        raw=diag['raw_pointer']
        return [(name,None if raw is None else raw[i],snap['pointer_'+name.lower()] if raw is not None else None)
                for i,name in enumerate(('X','Y'))]
    if channel=='scroll':
        raw=diag['raw_scroll']
        return [('Scroll',raw,snap['scroll_y'] if raw is not None else None)]
    if channel.startswith('head_'):
        raw=diag[channel]['raw']
        return [('Key direction',raw,(diag[channel]['direction']+1)/2 if raw is not None else None)]
    if 'button_actions' in diag:
        action=diag['button_actions']['mouth' if channel=='mouth' else channel+'_eye']
        raw=action['raw']
        return [('Mouth open' if channel=='mouth' else 'Eye action',
                 None if raw is None else int(raw),action['down'] if raw is not None else None)]
    raw=diag[channel+'_closed']
    return [('Eye action',None if raw is None else int(raw),snap[channel+'_click'] if raw is not None else None)]
