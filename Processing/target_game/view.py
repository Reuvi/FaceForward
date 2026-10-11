"""Native target game. The OS cursor is observed, never warped or simulated here."""
import tkinter as tk
from tkinter import ttk

from .experiment import Experiment
from .storage import ROOT, DEFAULT_PATH

BG='#0b1220';TEXT='#e5edf8';MUTED='#91a4bf';BLUE='#60a5fa';GREEN='#4adea5';GOLD='#fbbf24'


class TargetGame:
    def __init__(self,parent,lab,source,*,root=ROOT,default_path=DEFAULT_PATH):
        self.lab=lab;self.source=source;self.storage_root=root;self.default_path=default_path
        self.window=tk.Toplevel(parent);self.window.title('Pointer training · measured tuning')
        self.window.geometry('1180x850');self.window.minsize(900,650)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.bind('<Escape>',lambda event:self.stop())
        self.window.bind('<Return>',self.enter)
        self.experiment=Experiment(lab,source,root=root,default_path=default_path)
        self.timer=None;self.closed=False;self.trail=[];self.last_index=None;self.error=None
        self.fullscreen=False
        outer=ttk.Frame(self.window,padding=14);outer.pack(fill='both',expand=True)
        title=ttk.Frame(outer);title.pack(fill='x')
        ttk.Label(title,text='Pointer training',font=('TkDefaultFont',22,'bold')).pack(side='left')
        ttk.Button(title,text='Stop · Esc',command=self.stop).pack(side='right')
        ttk.Button(title,text='Fullscreen',command=self.toggle_fullscreen).pack(side='right',padx=6)
        self.status=tk.StringVar(value='Move with your head only during measured trials. Hover to select; no clicks required.')
        status_row=ttk.Frame(outer,height=52);status_row.pack(fill='x',pady=(6,8));status_row.pack_propagate(False)
        status_label=ttk.Label(status_row,textvariable=self.status,wraplength=1100)
        status_label.pack(fill='x',anchor='w')
        status_label.bind('<Configure>',lambda event:status_label.configure(wraplength=max(200,event.width)))
        bar=ttk.Frame(outer);bar.pack(fill='x',pady=(0,8))
        self.start_button=ttk.Button(bar,text='Start baseline · Enter',command=lambda:self.guarded(self.start))
        self.start_button.pack(side='left')
        self.practice_button=ttk.Button(bar,text='Practice with mouse',command=lambda:self.guarded(lambda:self.start(practice=True)))
        self.practice_button.pack(side='left',padx=6)
        self.resume_button=ttk.Button(bar,text='Resume target',command=lambda:self.guarded(self.resume))
        self.resume_button.pack(side='left')
        self.keep_button=ttk.Button(bar,text='Keep baseline as default',command=lambda:self.guarded(self.keep))
        self.keep_button.pack(side='left',padx=6)
        ttk.Button(bar,text='New session',command=lambda:self.guarded(self.new_session)).pack(side='right')
        recovery=ttk.Frame(outer);recovery.pack(fill='x',pady=(0,8))
        self.recenter_button=ttk.Button(recovery,text='Recenter & continue',command=lambda:self.guarded(self.recenter))
        self.recenter_button.pack(side='left')
        ttk.Label(recovery,text='Use if Start is waiting for your resting pose. Existing rounds stay saved.').pack(side='left',padx=8)
        self.canvas=tk.Canvas(outer,background=BG,highlightthickness=0,cursor='crosshair')
        self.canvas.pack(fill='both',expand=True)
        self.footer=tk.StringVar(value='16 targets per round · 600 ms hold · A baseline → B adjustment → B repeat → A repeat')
        ttk.Label(outer,textvariable=self.footer,wraplength=1100).pack(anchor='w',pady=(8,0))
        self.window.update_idletasks()
        self.draw();self.tick()

    def geometry(self):
        return dict(width=self.canvas.winfo_width(),height=self.canvas.winfo_height(),
                    origin_x=self.canvas.winfo_rootx(),origin_y=self.canvas.winfo_rooty(),
                    screen_width=self.window.winfo_screenwidth(),screen_height=self.window.winfo_screenheight(),
                    tk_scaling=round(float(self.window.tk.call('tk','scaling')),5))

    def guarded(self,fn):
        try:
            fn();self.error=None
        except (ValueError,OSError,TypeError,KeyError) as exc:
            self.error=str(exc);self.status.set(self.error)
            self.lab.action({'action':'stop'})
            try:self.experiment.record_event('ui_error',reason=self.error)
            except OSError:pass
        self.draw()

    def start(self,practice=False):
        if self.experiment.closed or self.experiment.finished:self.new_session()
        self.experiment.begin(self.geometry(),practice=practice)
        self.trail=[];self.last_index=None

    def enter(self,event=None):
        if self.experiment.waiting:return 'break'
        if self.experiment.round:
            if self.experiment.round.phase=='paused':self.guarded(self.resume)
        else:self.guarded(self.start)
        return 'break'

    def resume(self):self.experiment.resume()

    def recenter(self):
        if self.experiment.closed or self.experiment.finished:self.new_session()
        self.experiment.recenter(self.geometry())

    def keep(self):self.experiment.keep_baseline()

    def new_session(self):
        self.experiment.cancel()
        self.experiment=Experiment(self.lab,self.source,root=self.storage_root,default_path=self.default_path)
        self.trail=[];self.last_index=None

    def toggle_fullscreen(self):
        if self.experiment.round or self.experiment.waiting or (self.experiment.reports and not self.experiment.finished):
            self.status.set('Keep the same window for this comparison. Choose New session to change fullscreen.');return
        self.fullscreen=not self.fullscreen
        self.window.attributes('-fullscreen',self.fullscreen)

    def stop(self):
        self.lab.action({'action':'stop'})
        try:self.experiment.cancel()
        except (OSError,ValueError) as exc:self.error=str(exc)
        self.status.set(self.error or ('Stopped. Completed results and personal defaults retained.' if self.experiment.finished else
                                      'Stopped. Partial results saved; candidate settings were not promoted.'))
        self.draw()

    def close(self):
        if self.closed:return
        self.stop();self.closed=True
        if self.timer is not None:self.window.after_cancel(self.timer);self.timer=None
        self.window.destroy()

    def show(self):
        self.window.deiconify();self.window.lift()

    def tick(self):
        if self.closed:return
        try:
            x,y=self.window.winfo_pointerxy();geometry=self.geometry()
            x-=geometry['origin_x'];y-=geometry['origin_y']
            experiment=self.experiment
            # Losing focus does not stop camera acquisition, but cannot score a trial.
            if experiment.round and experiment.round.phase not in ('paused','done'):
                focused=self.window.focus_displayof()
                if focused is None or focused.winfo_toplevel()!=self.window:
                    experiment.round.pause(self.lab.clock(),'Game lost focus; resume when ready.')
                    self.lab.action({'action':'stop'})
            experiment.poll(self.lab.clock(),x,y,geometry)
            if experiment.round:
                index=(experiment.round.index,experiment.round.phase)
                if index!=self.last_index:self.trail=[];self.last_index=index
                if experiment.round.phase=='target':self.trail=(self.trail+[(x,y)])[-360:]
            if not self.error and not experiment.closed:self.status.set(experiment.message)
            if experiment.recorder:self.footer.set('Saved locally · '+experiment.recorder.id+' · cursor trace and per-target reports')
            self.draw((x,y))
        except (ValueError,OSError,TypeError,KeyError,tk.TclError) as exc:
            self.error=str(exc);self.lab.action({'action':'stop'})
            try:self.experiment.cancel()
            except (ValueError,OSError):pass
            self.status.set('Test stopped: '+self.error)
        self.timer=self.window.after(16,self.tick)

    def draw(self,cursor=None):
        if self.closed:return
        c=self.canvas;c.delete('all');w,h=c.winfo_width(),c.winfo_height()
        e=self.experiment;r=e.round
        self.start_button.configure(state='disabled' if r or e.waiting else 'normal',
                                    text='New baseline · Enter' if e.finished or e.closed else
                                    f'Start {e.kind} round {len(e.reports)+1} · Enter' if e.reports else 'Start baseline · Enter')
        self.resume_button.configure(state='normal' if r and r.phase=='paused' and not e.waiting else 'disabled')
        self.recenter_button.configure(state='disabled' if e.mode=='practice' or r and r.phase!='paused' else 'normal')
        self.practice_button.configure(state='disabled' if r or e.waiting or e.reports else 'normal')
        self.keep_button.configure(state='normal' if len(e.reports)==1 and not r and not e.waiting and e.mode=='live-head' and not e.closed and not e.finished else 'disabled')
        if r and r.phase in ('home','target') and not e.waiting:
            target=r.targets[r.index]
            kind='PRACTICE · no tuning' if e.mode=='practice' else 'BASELINE A' if e.kind=='A' else 'ADJUSTMENT B'
            label=f'{kind}   ·   {r.index+1} / 16'
            c.create_text(24,26,text=label,anchor='w',fill=MUTED,font=('TkDefaultFont',12,'bold'))
            if r.phase=='home':
                x,y=r.home;radius=r.home_radius;color=BLUE
                instruction='Return to the home ring and hold briefly'
            else:
                x,y,radius=target.x,target.y,target.radius;color=GOLD
                instruction='Move into the target and hold for 0.6 s'
                c.create_line(*r.trial.start,x,y,fill='#26364b',dash=(4,8))
                if len(self.trail)>1:c.create_line(*[v for point in self.trail for v in point],fill='#376082',width=2)
            c.create_text(w/2,h-24,text=instruction,fill=TEXT,font=('TkDefaultFont',13))
            c.create_oval(x-radius,y-radius,x+radius,y+radius,outline=color,width=3,fill='#15283e')
            c.create_oval(x-2,y-2,x+2,y+2,fill=color,outline='')
            if r.progress:c.create_arc(x-radius-7,y-radius-7,x+radius+7,y+radius+7,start=90,
                                      extent=-360*r.progress,style='arc',outline=GREEN,width=5)
            if cursor:c.create_oval(cursor[0]-3,cursor[1]-3,cursor[0]+3,cursor[1]+3,fill=TEXT,outline='')
            if r.phase=='target':
                elapsed=max(0,(self.lab.clock()-r.trial.started)/1000)
                c.create_text(w-24,26,text=f'{elapsed:.1f} s   ·   exits {r.trial.exits}',anchor='e',fill=MUTED)
            return
        if e.waiting:
            self.center_text('Preparing live control',e.message+'\nReturn your head to the saved resting pose, or use Recenter & continue.\nUse Stop / Esc to cancel.')
        elif r and r.phase=='paused':self.center_text('Paused — this attempt does not count',r.reason+'\nPress Resume target after the issue is resolved.')
        elif e.reports:
            report=e.reports[-1];s=report['summary']
            def n(value,suffix=''):return '—' if value is None else f'{value:.2f}{suffix}'
            c.create_text(34,36,anchor='w',text='Round saved · '+('PRACTICE' if e.mode=='practice' else report['kind']),fill=TEXT,font=('TkDefaultFont',22,'bold'))
            rows=[('Targets completed',f"{s['completed']} / 16"),('First arrival',n(s['arrival_s'],' s')),
                  ('Arrival + stable hold',n(s['acquisition_s'],' s')),('Extra settling time',n(s['settling_s'],' s')),
                  ('Small-target re-entries',n(s['small_reentries'])),('Path efficiency',n(None if s['path_efficiency'] is None else s['path_efficiency']*100,'%')),
                  ('Motion roughness · lower is smoother',n(s['roughness'])),('Small-target hold error · target radii',n(s['hold_error_radii']))]
            for i,(label,value) in enumerate(rows):
                y=90+i*34
                c.create_text(34,y,anchor='w',text=label,fill=MUTED,font=('TkDefaultFont',12))
                c.create_text(w-36,y,anchor='e',text=value,fill=GREEN,font=('TkDefaultFont',16,'bold'))
            message=e.message
            if e.suggestion and e.suggestion['changes'] and not e.finished:
                changes=', '.join(f'{k} → {v:g}' for k,v in e.suggestion['changes'].items())
                message+='\nProposed experiment: '+changes+'\nRest, then press Enter for the next round. Return to the same head rest pose.'
            c.create_text(34,390,anchor='nw',text=message,width=w-68,fill=TEXT,font=('TkDefaultFont',12))
            if e.result and e.result.get('baseline_repeat_time_ratio') is not None:
                value=(e.result['baseline_repeat_time_ratio']-1)*100
                c.create_text(34,h-28,anchor='w',text=f'Baseline repeat time changed {value:+.1f}% — practice/fatigue can affect performance.',fill=MUTED)
        else:
            self.center_text('Move. Settle. Hold.',
                'Follow 16 targets at different distances and sizes.\nStay inside each one for 0.6 seconds — no clicking.\n\nUse Camera + Mouse test + connected Live output for measured tuning.\nStart live control on Signals first; keep your hands off the mouse during trials.\nPractice with mouse is separate and cannot change controller defaults.\n\nFour short rounds compare A → B → B → A. Take breaks between rounds.\nWindow size and position must remain the same.')

    def center_text(self,title,body):
        c=self.canvas;w,h=c.winfo_width(),c.winfo_height()
        c.create_text(w/2,h*.24,text=title,fill=TEXT,font=('TkDefaultFont',28,'bold'))
        c.create_text(w/2,h*.50,text=body,width=w-100,fill=MUTED,font=('TkDefaultFont',13),justify='center')
