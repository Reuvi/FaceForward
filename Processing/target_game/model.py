"""Clock-injected dwell target course and cursor metrics. No camera/OS/UI effects."""
from dataclasses import asdict, dataclass
import math
import statistics

HOLD_MS = 600
HOME_MS = 350
TIMEOUT_MS = 20000
MAX_GAP_MS = 120


def median(values, default=None):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else default


def distance(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


@dataclass(frozen=True)
class Target:
    id: str
    direction: str
    size: str
    x: float
    y: float
    radius: float


def course(width, height):
    if not 640 <= width <= 10000 or not 400 <= height <= 10000:
        raise ValueError('Game area must be at least 640 × 400 pixels')
    # Interleave difficulty and direction; repeat exactly for all four rounds.
    specs = [('right','wide'),('down','small'),('left','medium'),('up','wide'),
             ('down-right','medium'),('left','small'),('down','wide'),('right','medium'),
             ('up-left','medium'),('up','small'),('left','wide'),('down','medium'),
             ('up-right','medium'),('right','small'),('up','medium'),('down-left','medium')]
    directions = {'right':(1,0),'left':(-1,0),'up':(0,-1),'down':(0,1),
                  'down-right':(1,1),'up-left':(-1,-1),'up-right':(1,-1),'down-left':(-1,1)}
    radii = {'wide':44,'medium':27,'small':14}
    result=[]
    for direction,size in specs:
        dx,dy=directions[direction]
        reach=.18 if size=='small' else .36
        result.append(Target(direction+'-'+size,direction,size,width/2+dx*(width-120)*reach,
                             height/2+dy*(height-120)*reach,radii[size]))
    return result


def roughness(points):
    """Uniform 50 ms velocities: excess variation above a straight speed hump.

    Pixel steps and irregular polling make unfiltered derivatives misleading.
    A 120 ms gap makes this measurement unavailable, rather than interpolating loss.
    """
    if len(points)<3 or points[-1][0]-points[0][0]<150:return None
    if any(b[0]-a[0]>MAX_GAP_MS for a,b in zip(points,points[1:])):return None
    grid=[];index=0;t=points[0][0]
    while t<=points[-1][0]:
        while index+1<len(points)-1 and points[index+1][0]<t:index+=1
        a,b=points[index:index+2]
        weight=(t-a[0])/(b[0]-a[0])
        grid.append((a[1]+weight*(b[1]-a[1]),a[2]+weight*(b[2]-a[2])))
        t+=50
    velocities=[((b[0]-a[0])/.05,(b[1]-a[1])/.05) for a,b in zip(grid,grid[1:])]
    peak=max((math.hypot(*v) for v in velocities),default=0)
    if peak<1:return 0.
    padded=[(0.,0.),*velocities,(0.,0.)]
    return max(0.,sum(distance(a,b) for a,b in zip(padded,padded[1:]))/(2*peak)-1)


class Trial:
    def __init__(self, target, timestamp, position, attempt):
        self.target=target;self.started=timestamp;self.start=position;self.attempt=attempt
        self.points=[];self.first_entry=None;self.inside_since=None
        self.inside=False;self.entries=0;self.exits=0;self.gaps=0
        self.progress=0.;self.finished=False

    def sample(self, timestamp, position):
        if self.points and timestamp<=self.points[-1][0]:raise ValueError('Cursor samples must increase in time')
        gap=bool(self.points and timestamp-self.points[-1][0]>MAX_GAP_MS)
        self.points.append((timestamp,*position))
        if gap:
            self.gaps+=1;self.inside_since=None
        inside=distance(position,(self.target.x,self.target.y))<=self.target.radius
        if inside and not self.inside:
            self.entries+=1
            if self.first_entry is None:self.first_entry=timestamp
        if not inside and self.inside:self.exits+=1
        if inside:
            if self.inside_since is None:self.inside_since=timestamp
            self.progress=min(1,(timestamp-self.inside_since)/HOLD_MS)
        else:self.inside_since=None;self.progress=0.
        self.inside=inside
        self.finished=self.progress>=1 or timestamp-self.started>=TIMEOUT_MS
        return self.finished

    def result(self, timestamp, reason=None):
        success=self.progress>=1 and reason is None
        d=distance(self.start,(self.target.x,self.target.y))
        ux,uy=((self.target.x-self.start[0])/d,(self.target.y-self.start[1])/d) if d else (1.,0.)
        projections=[(x-self.start[0])*ux+(y-self.start[1])*uy for _,x,y in self.points]
        transverse=[-(x-self.start[0])*uy+(y-self.start[1])*ux for _,x,y in self.points]
        path=sum(distance(a[1:],b[1:]) for a,b in zip(self.points,self.points[1:]))
        # Remove the required final hold from movement roughness, keep corrections.
        moving=[p for p in self.points if not success or p[0]<=self.inside_since]
        held=[distance((x,y),(self.target.x,self.target.y)) for t,x,y in self.points
              if success and t>=self.inside_since]
        elapsed=(timestamp-self.started)/1000
        return dict(target=asdict(self.target),attempt=self.attempt,success=success,
                    valid=reason is None and self.gaps==0,reason=reason or ('cursor sampling gap' if self.gaps else None),
                    timeout=not success and reason is None,started_ms=self.started,ended_ms=timestamp,
                    distance_px=d,difficulty_bits=math.log2(1+d/(2*self.target.radius)),
                    arrival_s=None if self.first_entry is None else (self.first_entry-self.started)/1000,
                    acquisition_s=elapsed,settling_s=None if self.first_entry is None else
                    max(0,(timestamp-self.first_entry)/1000-(HOLD_MS/1000 if success else 0)),
                    reentries=max(0,self.entries-1),exits=self.exits,
                    path_px=path,path_efficiency=min(1,max(0,d-self.target.radius)/path) if path else 0.,
                    overshoot_radii=max(0,max(projections,default=0)-d-self.target.radius)/self.target.radius,
                    variability_px=statistics.pstdev(transverse) if transverse else None,
                    hold_error_radii=math.sqrt(statistics.mean(v*v for v in held))/self.target.radius if held else None,
                    roughness=roughness(moving),sample_count=len(self.points),sampling_gaps=self.gaps)


class Round:
    def __init__(self, width, height):
        self.width=width;self.height=height;self.targets=course(width,height)
        self.index=0;self.phase='home';self.trial=None;self.home_since=None;self.progress=0.
        self.last_time=None;self.trials=[];self.events=[];self.attempt=0;self.reason=None
        self.home=(width/2,height/2);self.home_radius=32

    @property
    def done(self):return self.phase=='done'

    def pause(self, timestamp, reason):
        if self.done or self.phase=='paused':return
        if self.trial:
            result=self.trial.result(timestamp,reason)
            self.trials.append(result);self.events.append(dict(event='trial_end',trial=result))
        self.phase='paused';self.reason=reason;self.trial=None;self.home_since=None;self.progress=0.
        self.events.append(dict(event='pause',time_ms=timestamp,reason=reason))

    def resume(self):
        if self.phase!='paused':return
        self.phase='home';self.reason=None;self.last_time=None;self.home_since=None

    def sample(self, timestamp, x, y):
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (timestamp,x,y)):
            raise ValueError('Cursor time and position must be finite')
        if self.phase in ('done','paused'):return
        if self.last_time is not None:
            if timestamp<=self.last_time:raise ValueError('Cursor clock must increase')
            if timestamp-self.last_time>MAX_GAP_MS:
                self.pause(timestamp,'Cursor sampling paused; retry this target');return
        self.last_time=timestamp
        if self.phase=='home':
            if distance((x,y),self.home)<=self.home_radius:
                if self.home_since is None:self.home_since=timestamp
                self.progress=min(1,(timestamp-self.home_since)/HOME_MS)
                if self.progress>=1:
                    self.attempt+=1
                    if self.attempt>64:self.phase='done';self.reason='Too many interrupted attempts';return
                    self.trial=Trial(self.targets[self.index],timestamp,(x,y),self.attempt)
                    self.phase='target';self.progress=0.
                    self.events.append(dict(event='trial_start',time_ms=timestamp,target=asdict(self.trial.target),start=[x,y],attempt=self.attempt))
                    self.trial.sample(timestamp,(x,y))
            else:self.home_since=None;self.progress=0.
        else:
            finished=self.trial.sample(timestamp,(x,y));self.progress=self.trial.progress
            if finished:
                result=self.trial.result(timestamp);self.trials.append(result)
                self.events.append(dict(event='trial_end',trial=result))
                self.index+=1;self.trial=None;self.home_since=None;self.progress=0.
                self.phase='done' if self.index==len(self.targets) else 'home'

    def drain_events(self):
        events,self.events=self.events,[]
        return events


def summarize(trials):
    valid=[t for t in trials if t['valid']]
    complete=[t for t in valid if t['success']]
    small=[t for t in complete if t['target']['size']=='small']
    return dict(attempts=len(trials),valid=len(valid),completed=len(complete),
                success_rate=len(complete)/len(valid) if valid else 0,
                arrival_s=median(t['arrival_s'] for t in complete),
                acquisition_s=median(t['acquisition_s'] for t in complete),
                settling_s=median(t['settling_s'] for t in complete),
                reentries=statistics.mean(t['reentries'] for t in complete) if complete else None,
                small_reentries=statistics.mean(t['reentries'] for t in small) if small else None,
                path_efficiency=median(t['path_efficiency'] for t in complete),
                roughness=median(t['roughness'] for t in complete),
                hold_error_radii=median(t['hold_error_radii'] for t in small),
                timeouts=sum(t['timeout'] for t in valid))
