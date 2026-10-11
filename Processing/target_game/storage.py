"""Private bounded round records and validated personal tuning defaults."""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid

from Processing.tuning.model import read_profile, validate_profile, write_profile
from .analysis import fingerprint

ROOT=Path(__file__).resolve().parents[2]/'.local'/'target-game'
DEFAULT_PATH=ROOT/'personal-default.json'


def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False,prefix='.report-') as stream:
            temporary=stream.name
            json.dump(data,stream,indent=2,allow_nan=False);stream.write('\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path);temporary=None
    finally:
        if temporary:os.unlink(temporary)


class Recorder:
    def __init__(self, root=ROOT):
        self.id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        self.path=Path(root)/self.id;self.path.mkdir(parents=True,mode=0o700)
        self.stream=(self.path/'cursor.jsonl').open('x',encoding='utf-8')
        (self.path/'cursor.jsonl').chmod(0o600)
        self.samples=0;self.closed=False
        self.write(dict(event='session_start',format='pointer_game_trace_v1',id=self.id))

    def write(self,event):
        if self.closed:raise ValueError('Recorder is closed')
        if event.get('event')=='sample':
            self.samples+=1
            if self.samples>180000:raise ValueError('Session sample limit reached; start a new session')
        self.stream.write(json.dumps(event,allow_nan=False,separators=(',',':'))+'\n')
        if event.get('event')!='sample':self.stream.flush()

    def report(self,index,report):
        atomic_json(self.path/f'round-{index+1}.json',report)
        fields=('id','direction','size','attempt','valid','success','timeout','arrival_s','acquisition_s',
                'settling_s','reentries','exits','path_efficiency','overshoot_radii','roughness','hold_error_radii','reason')
        path=self.path/f'round-{index+1}.csv'
        with path.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            for trial in report['trials']:
                row=dict(trial,**trial['target']);writer.writerow({k:row.get(k) for k in fields})
        path.chmod(0o600)
        self.write(dict(event='round_end',index=index,summary=report['summary']))

    def close(self):
        if self.closed:return
        try:self.write(dict(event='session_end'))
        finally:self.stream.close();self.closed=True


def save_default(profile, path=DEFAULT_PATH):
    _,mapping,_=validate_profile(profile)
    if mapping is None or mapping.input_mode!='head-mouse':raise ValueError('Personal game defaults require a head mouse mapping')
    write_profile(path,profile)
    Path(path).chmod(0o600)


def read_personal_default(path=DEFAULT_PATH):
    if not Path(path).is_file():raise ValueError('No personal default yet. Complete a live Target game comparison or keep a measured baseline.')
    data=read_profile(path)
    _,mapping,_=validate_profile(data)
    if mapping is None or mapping.input_mode!='head-mouse':raise ValueError('Saved personal default is not a head mouse mapping')
    return data


def configure_startup(lab, requested_mapping=None, path=DEFAULT_PATH, *, factory=False):
    """Explicit non-head mapping wins. Loading never starts output or the camera."""
    from Processing.mappings.config import GAMING_ID
    if factory or requested_mapping not in (None,'mouse-test'):
        lab.select_mapping(requested_mapping or GAMING_ID);return 'Built-in mapping selected'
    if Path(path).is_file():
        data=read_personal_default(path)
        lab.apply_tuning_profile(data)
        return 'Personal target-game default loaded · '+data['name']
    lab.select_mapping(requested_mapping or GAMING_ID)
    return 'Built-in response defaults'


def analyze_folder(path):
    from .analysis import decision, propose
    from .model import summarize
    path=Path(path)
    reports=[]
    for file in sorted(path.glob('round-*.json')):
        if file.stat().st_size>2_000_000:raise ValueError('Round report exceeds 2 MB')
        data=json.loads(file.read_text())
        if data.get('format')!='pointer_game_round_v1':raise ValueError('Unsupported round format')
        validate_profile(data['profile'])
        if data.get('profile_hash')!=fingerprint(data['profile']):raise ValueError('Round settings fingerprint mismatch')
        data['summary']=summarize(data['trials'])
        reports.append(data)
    if not reports:raise ValueError('No round reports found')
    return dict(rounds=[dict(kind=r['kind'],summary=r['summary'],mode=r['mode']) for r in reports],
                suggestion=propose(reports[0]),decision=decision(reports))


def history(root=ROOT):
    path=Path(root)/'history.json'
    if not path.is_file():return []
    if path.stat().st_size>1_000_000:raise ValueError('Tuning history exceeds 1 MB')
    data=json.loads(path.read_text())
    if not isinstance(data,list) or len(data)>128:raise ValueError('Invalid tuning history')
    for row in data:
        if not isinstance(row,dict) or set(row)!={'baseline','candidate','winner','session'}:
            raise ValueError('Invalid tuning history entry')
        if row['winner'] not in ('A','B') or not all(isinstance(row[k],str) for k in row):
            raise ValueError('Invalid tuning history values')
    return data


def remember(root, baseline, candidate, winner, session):
    records=history(root)
    records.append(dict(baseline=fingerprint(baseline),candidate=fingerprint(candidate),winner=winner,session=session))
    atomic_json(Path(root)/'history.json',records[-128:])
