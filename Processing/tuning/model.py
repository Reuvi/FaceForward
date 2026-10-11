"""Validated response-only edits and profiles; no camera, UI or driver dependency."""
from copy import deepcopy
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile

from Processing.mouse.config import MouseConfig, number
from Processing.mappings.config import Mapping, action_label, mouse_test_mapping


@dataclass(frozen=True)
class Slider:
    key: str
    label: str
    low: float
    high: float
    step: float
    path: tuple
    unit: str = ''



def legacy_eye_timing(state):
    mapping=state['mapping']
    if mapping and (mapping['input_mode']=='head-mouse' or not mapping['require_wink']):return False
    return ((state.get('raw') or {}).get('format')=='raw_mouse_v1' or
            state.get('runtime',{}).get('source')=='mock')


def channels(state):
    mapping=state['mapping']
    result=[('pointer', 'Head X/Y → mouse' if mapping and mapping['input_mode']=='head-mouse' else 'Pupils X/Y → mouse')]
    if mapping and mapping['input_mode']=='gaming':
        bindings=mapping['bindings']
        for axis,directions in (('head_x',('left','right')),('head_y',('up','down'))):
            if any(bindings[d]!='none' for d in directions):
                result.append((axis,axis.replace('_',' ').title()+' → '+' / '.join(bindings[d] for d in directions)))
    if mapping is None:result.append(('scroll','Head Y → scroll'))
    if not mapping or mapping['input_mode']!='head-mouse' or mapping['head_wink_clicks']:
        mode=' wink' if not mapping or mapping['require_wink'] else ' open/closed'
        result.extend((side,side.title()+mode+' → '+action_label(mapping['button_bindings'][side+'_eye'])
                       if mapping else side.title()+mode+' → '+side+' click') for side in ('left','right'))
    if mapping and mapping['button_bindings']['mouth'] != 'none':
        result.append(('mouth','Mouth open → '+action_label(mapping['button_bindings']['mouth'])))
    return result


def sliders(state, channel):
    if channel not in dict(channels(state)):raise ValueError('This input is not mapped')
    mapping=state['mapping']
    result=[]
    def add(key,label,lo,hi,step,path,unit=''):
        result.append(Slider(key,label,lo,hi,step,tuple(path.split('.')),unit))
    if channel in ('left','right','mouth'):
        if channel != 'mouth' and legacy_eye_timing(state):
            add('dwell_ms','Closure confirmation',50,3000,10,f'config.{channel}_eye.dwell_ms','ms')
            add('release_ms','Reopen confirmation',0,500,5,f'config.{channel}_eye.release_ms','ms')
        return result
    if channel.startswith('head_'):
        for key,label,lo,hi,step,unit in (
            ('activation','Press threshold',.01,1,.01,''),('release','Release threshold',0,.99,.01,''),
            ('smoothing_ms','Input smoothing',0,500,5,'ms'),('confirmation_ms','Press confirmation',0,1000,5,'ms')):
            add(key,label,lo,hi,step,f'mapping.{channel}.{key}',unit)
        return result
    target=channel=='pointer' and mapping and mapping['pointer_mode']=='target'
    if mapping and channel=='pointer':
        add('gain','Signal gain',.1,4,.01,'mapping.pointer_gain','×')
        add('down_gain','Downward amplification',1,8,.05,'mapping.pointer_down_gain','×')
    if target:
        add('smoothing_ms','Position smoothing',0,1000,5,'mapping.target_smoothing_ms','ms')
        add('delay_ms','Position delay',0,min(250,state['config']['stale_ms']-1),1,'mapping.target_interpolation_ms','ms')
        add('jitter','Fixation dead band',0,.1,.001,'mapping.target_jitter')
        return result
    for key,label,lo,hi,step,unit in (
        ('deadzone','Rest dead zone',0,.8,.005,''),('hysteresis','Start margin',0,.15,.005,''),
        ('exponent','Curve exponent',.2,5,.05,''),('smoothing_ms','Motion smoothing',0,1000,5,'ms'),
        ('acceleration','Acceleration',.1,100,.1,'/s'),('deceleration','Braking',.1,100,.1,'/s')):
        add(key,label,lo,hi,step,f'config.{channel}.{key}',unit)
    add('delay_ms','Input delay (shared)',0,min(250,state['config']['stale_ms']-1),1,'config.interpolation_ms','ms')
    head=channel=='pointer' and mapping and mapping['input_mode']=='head-mouse' and mapping['head_motion']['enabled']
    if head:
        add('speed_gain','Fast-turn boost',0,2,.01,'mapping.head_motion.speed_gain','× extra')
        add('return_brake','Return braking',0,1,.01,'mapping.head_motion.return_brake')
    else:
        for key,label,lo,hi,step,unit in (
            ('jump_threshold','Quick-move threshold',0,2,.01,''),('boost_gain','Quick-move gain',0,1,.005,''),
            ('boost_max','Maximum extra boost',0,3,.05,'×'),('boost_decay_ms','Boost fade time',1,2000,5,'ms')):
            add(key,label,lo,hi,step,f'config.{channel}.{key}',unit)
    return result


def value_at(state,path):
    for key in path:state=state[key]
    return state


def edited(state,channel,changes):
    if not isinstance(changes,dict) or not changes:raise ValueError('Supply response slider values')
    allowed={s.key:s for s in sliders(state,channel)}
    if set(changes)-set(allowed):raise ValueError('Only active response sliders can be edited live')
    data={'config':deepcopy(state['config']),'mapping':deepcopy(state['mapping'])}
    for key,value in changes.items():
        spec=allowed[key];number(value,spec.label,spec.low,spec.high)
        parent=value_at(data,spec.path[:-1]);parent[spec.path[-1]]=value
    if channel.startswith('head_'):
        head=data['mapping'][channel]
        if head['release']>=head['activation']:
            if 'activation' in changes:head['release']=max(0,head['activation']-.01)
            else:head['activation']=min(1,head['release']+.01)
    config=MouseConfig.from_dict(data['config'])
    mapping=None
    if data['mapping'] is not None:
        data['mapping']['response']=config.to_dict()
        mapping=Mapping.from_dict(data['mapping'])
    return config,mapping


def profile(state,name):
    result=dict(format='signal_tuning_profile_v1',name=name,mapping=state['mapping'],
                mouse_config=state['config'] if state['mapping'] is None else None,
                speeds={key:state['runtime'][key] for key in ('pointer_speed','scroll_speed')})
    validate_profile(result)
    return deepcopy(result)


def validate_profile(data):
    fields={'format','name','mapping','mouse_config','speeds'}
    if not isinstance(data,dict) or set(data)!=fields or data['format']!='signal_tuning_profile_v1':
        raise ValueError('Expected a signal_tuning_profile_v1 file')
    name=data['name']
    if not isinstance(name,str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):
        raise ValueError('Use a profile name of 1–100 readable characters')
    mapping=Mapping.from_dict(data['mapping']) if data['mapping'] is not None else None
    if mapping:
        if data['mouse_config'] is not None:raise ValueError('Profile contains conflicting response settings')
        config=mapping.response
    else:
        raw=data['mouse_config']
        expected=MouseConfig().to_dict()
        if not isinstance(raw,dict) or set(raw)!=set(expected):
            raise ValueError('Profile needs complete mouse response settings')
        for key in ('pointer','scroll','left_eye','right_eye'):
            if not isinstance(raw[key],dict) or set(raw[key])!=set(expected[key]):
                raise ValueError('Profile needs complete '+key+' response settings')
        config=MouseConfig.from_dict(raw)
    speeds=data['speeds']
    if not isinstance(speeds,dict) or set(speeds)!={'pointer_speed','scroll_speed'}:
        raise ValueError('Profile needs mouse and scroll speed settings')
    number(speeds['pointer_speed'],'Mouse speed',50,2500)
    number(speeds['scroll_speed'],'Scroll speed',20,1500)
    return config,mapping,dict(speeds)


def default_profile(state):
    mapping=Mapping.from_dict(state['mapping']) if state['mapping'] else None
    if mapping:
        base=mouse_test_mapping() if mapping.input_mode=='head-mouse' else Mapping()
        # A user's routing/identity and pointer mode are separate from response tuning.
        base=replace(base,id=mapping.id,name=mapping.name,revision=mapping.revision+1,
                     bindings=mapping.bindings,pointer_mode=mapping.pointer_mode,
                     head_wink_clicks=mapping.head_wink_clicks, require_wink=mapping.require_wink,
                     button_bindings=mapping.button_bindings)
        data={**state,'mapping':base.to_dict()}
    else:
        data={**state,'config':replace(MouseConfig(),pointer_source=state['config']['pointer_source']).to_dict()}
    data['runtime']={**state['runtime'],'pointer_speed':900,'scroll_speed':450}
    return profile(data,'Default — '+('precision head' if mapping and mapping.input_mode=='head-mouse' else 'gaming' if mapping else 'mouse and scroll'))


def read_profile(path):
    with Path(path).open('rb') as stream:raw=stream.read(65537)
    if len(raw)>65536:raise ValueError('Tuning profile exceeds 64 KiB')
    try:data=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise ValueError('Tuning profile is not valid JSON') from exc
    validate_profile(data)
    return data


def write_profile(path,data):
    validate_profile(data)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.tuning-',delete=False) as stream:
            temporary=stream.name
            json.dump(data,stream,indent=2,allow_nan=False);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:os.unlink(temporary)
