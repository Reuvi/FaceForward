"""One native live curve editor, shared by App and the standalone lab."""
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, ttk

from .model import legacy_eye_timing, channels, sliders, value_at, profile, default_profile, read_profile, write_profile
from .preview import steady_curves, response_preview, live_values

BG='#111827'
FG='#e5e7eb'
MUTED='#9ca3af'
COLORS=('#60a5fa','#fbbf24','#34d399')
PROFILE_DIR=Path(__file__).resolve().parents[2]/'local-profiles'/'tuning'


class CurveEditor:
    def __init__(self,parent,lab):
        self.lab=lab
        self.window=tk.Toplevel(parent)
        self.window.title('Live signal curves')
        self.window.geometry('1120x780')
        self.window.minsize(920,650)
        self.window.protocol('WM_DELETE_WINDOW',self.hide)
        self.window.bind('<Escape>',lambda event:self.stop())
        self.pending=None
        self.changes={}
        self.syncing=False
        self.context=None
        self.next_draw=0
        self.widgets={}
        self.channel='pointer'
        self.state=None
        self.curves={};self.timeline={}
        outer=ttk.Frame(self.window,padding=16);outer.pack(fill='both',expand=True)
        top=ttk.Frame(outer);top.pack(fill='x')
        ttk.Label(top,text='Live signal curves',font=('TkDefaultFont',18,'bold')).pack(side='left')
        ttk.Button(top,text='Stop output · Esc',command=self.stop).pack(side='right')
        self.connection=tk.StringVar()
        ttk.Label(outer,textvariable=self.connection).pack(anchor='w',pady=(4,10))
        bar=ttk.Frame(outer);bar.pack(fill='x')
        ttk.Label(bar,text='Tuning profile').pack(side='left')
        self.name=tk.StringVar(value='My tuning')
        ttk.Entry(bar,textvariable=self.name,width=27).pack(side='left',padx=8)
        for text,fn in (('Save as…',self.save),('Load…',self.load),('Default profile',self.defaults)):
            ttk.Button(bar,text=text,command=lambda f=fn:self.guarded(f)).pack(side='left',padx=3)
        self.notice=tk.StringVar(value='Sliders change the running response. Loading a profile stops output.')
        ttk.Label(outer,textvariable=self.notice,wraplength=1060).pack(anchor='w',pady=(8,8))
        body=ttk.Frame(outer);body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=410);left.pack(side='left',fill='y',padx=(0,18));left.pack_propagate(False)
        self.selector=ttk.Combobox(left,state='readonly',width=38)
        self.selector.pack(fill='x',pady=(0,8))
        self.selector.bind('<<ComboboxSelected>>',lambda event:self.select_channel())
        self.explanation=tk.StringVar()
        ttk.Label(left,textvariable=self.explanation,wraplength=400,justify='left').pack(fill='x',pady=(0,8))
        self.controls_canvas=tk.Canvas(left,highlightthickness=0,bg=BG)
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.controls_canvas.yview)
        scroll.pack(side='right',fill='y')
        self.controls_canvas.pack(fill='both',expand=True)
        self.controls_canvas.configure(yscrollcommand=scroll.set)
        self.controls=ttk.Frame(self.controls_canvas)
        slot=self.controls_canvas.create_window(0,0,window=self.controls,anchor='nw')
        self.controls.bind('<Configure>',lambda event:self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox('all')))
        self.controls_canvas.bind('<Configure>',lambda event:self.controls_canvas.itemconfigure(slot,width=event.width))
        graphs=ttk.Frame(body);graphs.pack(side='left',fill='both',expand=True)
        ttk.Label(graphs,text='Response curve + live input/output',font=('TkDefaultFont',12,'bold')).pack(anchor='w')
        self.curve_canvas=tk.Canvas(graphs,bg=BG,highlightthickness=0,height=260)
        self.curve_canvas.pack(fill='both',expand=True,pady=(6,8))
        self.output_legend=tk.StringVar()
        ttk.Label(graphs,textvariable=self.output_legend,wraplength=620).pack(anchor='w')
        self.readout=tk.StringVar()
        ttk.Label(graphs,textvariable=self.readout,wraplength=650).pack(anchor='w',pady=(0,10))
        self.timing_title=tk.StringVar()
        ttk.Label(graphs,textvariable=self.timing_title,font=('TkDefaultFont',12,'bold')).pack(anchor='w')
        self.time_canvas=tk.Canvas(graphs,bg=BG,highlightthickness=0,height=210)
        self.time_canvas.pack(fill='both',expand=True,pady=(6,0))
        ttk.Label(graphs,text='Blue: input   Gold/green: response · simulation never controls the mouse',wraplength=600).pack(anchor='w',pady=5)
        for canvas in (self.curve_canvas,self.time_canvas):
            canvas.bind('<Configure>',lambda event:self.draw())
        self.refresh(lab.state(),force=True)

    def guarded(self,fn):
        try:return fn()
        except (ValueError,TypeError,OSError,KeyError) as exc:
            self.notice.set(str(exc))
            return False

    def stop(self):
        self.lab.action({'action':'stop'})
        self.notice.set('Output stopped. Sliders still edit the saved response; press Start on Signals to resume.')
        self.refresh(self.lab.state())

    def hide(self):
        self.flush()
        self.window.withdraw()

    def show(self):
        self.window.deiconify();self.window.lift()
        self.refresh(self.lab.state(),force=True)

    def cancel_pending(self):
        if self.pending is not None:
            self.window.after_cancel(self.pending);self.pending=None
        self.changes.clear()

    def select_channel(self):
        self.flush()
        index=self.selector.current()
        if index>=0:self.channel=self.channel_choices[index][0]
        self.refresh(self.lab.state(),force=True)

    def rebuild(self,state):
        self.syncing=True
        for child in self.controls.winfo_children():child.destroy()
        self.widgets={}
        self.channel_choices=channels(state)
        if self.channel not in dict(self.channel_choices):self.channel='pointer'
        self.selector.configure(values=[name for _,name in self.channel_choices])
        self.selector.current(next(i for i,(key,_) in enumerate(self.channel_choices) if key==self.channel))
        if self.channel in ('left','right'):
            detail='Calibrated winks are ON/OFF actions, with one click on activation. There is no strength curve or added timer. Unknown releases this eye; reopening re-arms it. Train the wink in Calibration.'
        elif self.channel.startswith('head_'):
            detail='Press/release thresholds create a key gate. Smoothing and confirmation control its response time. Editing releases this axis; center it to re-arm. The other inputs keep working.'
        elif self.channel=='scroll':
            detail='Head Y sets scroll speed. Shape the curve and adjust its ramp, braking and boost fade. Input delay is shared with pointer velocity.'
        elif state['mapping'] and state['mapping']['pointer_mode']=='target':
            detail='Pupil position becomes a screen destination. Gain and downward amplification change reach; smoothing, delay and fixation dead band control settling. X and Y curves show one axis at a time.'
        else:
            detail='X/Y share a smooth radial speed curve. X and Y lines show each axis with the other centered; diagonal motion is bounded. Gain shapes speed; acceleration and braking shape timing.'
        if self.channel in ('left','right') and legacy_eye_timing(state):
            detail='Legacy raw closure input: confirmation and reopening timers are active here. Calibrated camera winks bypass these timers. Each eye remains independent.'
        self.timing_title.set('Timing preview · synthetic wink' if self.channel in ('left','right') else 'Timing preview · synthetic turn, hold, return')
        self.explanation.set(detail)
        target=self.channel=='pointer' and state['mapping'] and state['mapping']['pointer_mode']=='target'
        self.output_legend.set('Output: OFF (0) / ON (1); the driver clicks once on activation.' if self.channel in ('left','right') else
                               'Output: screen position, with 0.5 at center.' if target else
                               'Output: 0 = left/up, 0.5 = released, 1 = right/down.' if self.channel.startswith('head_') else
                               'Output speed: 0 = full left/up, 0.5 = stopped, 1 = full right/down.')
        specs=sliders(state,self.channel)
        if not specs:
            ttk.Label(self.controls,text='Instant calibrated action\n\nOFF → no click\nON → one click\nHeld ON → no repeats',justify='left').pack(anchor='w',pady=20)
        for spec in specs:
            row=ttk.Frame(self.controls);row.pack(fill='x',pady=(2,7))
            ttk.Label(row,text=spec.label).grid(row=0,column=0,sticky='w')
            text=tk.StringVar()
            ttk.Label(row,textvariable=text,width=14,anchor='e').grid(row=0,column=1,sticky='e')
            value=tk.DoubleVar(value=value_at(state,spec.path))
            widget=ttk.Scale(row,from_=spec.low,to=spec.high,variable=value,
                             command=lambda v,s=spec:self.changed(s,v))
            widget.grid(row=1,column=0,columnspan=2,sticky='ew',pady=2)
            row.columnconfigure(0,weight=1)
            self.widgets[spec.key]=(value,text,widget,spec)
            self.set_label(spec.key,value.get())
        self.syncing=False
        self.curves=steady_curves(state,self.channel)
        self.timeline=response_preview(state,self.channel)
        self.controls_canvas.yview_moveto(0)

    def set_label(self,key,value):
        _,text,_,spec=self.widgets[key]
        text.set(f'{value:.3g} {spec.unit}'.rstrip())

    def changed(self,spec,value):
        if self.syncing:return
        value=max(spec.low,min(spec.high,round(float(value)/spec.step)*spec.step))
        self.set_label(spec.key,value)
        self.changes[spec.key]=value
        if self.pending is None:self.pending=self.window.after(40,self.flush)

    def flush(self):
        if self.pending is not None:self.window.after_cancel(self.pending);self.pending=None
        if not self.changes:return True
        changes,self.changes=self.changes,{}
        try:
            generation=self.lab.tune_response(self.channel,changes,mapping_id=self.context[0],generation=self.context[1])
        except ValueError as exc:
            self.notice.set(str(exc));self.refresh(self.lab.state(),force=True);return False
        self.state=self.lab.state()
        self.context=(self.state['mapping_id'],generation,legacy_eye_timing(self.state))
        self.syncing=True
        for key,(var,_,_,spec) in self.widgets.items():
            value=value_at(self.state,spec.path);var.set(value);self.set_label(key,value)
        self.syncing=False
        self.curves=steady_curves(self.state,self.channel)
        self.timeline=response_preview(self.state,self.channel)
        self.notice.set('Live response updated. Save as… keeps this tuning across restarts.')
        self.draw()
        return True

    def refresh(self,state,force=False):
        if not force and not self.window.winfo_viewable():return
        context=(state['mapping_id'],state['generation'],legacy_eye_timing(state))
        if context!=self.context or force:
            self.cancel_pending()
            self.context=context
            self.state=state
            self.rebuild(state)
        self.state=state
        mode={'preview':'Preview','dry-run':'Driver dry run','native':'Live mouse + keyboard'}[state['output']['mode']]
        running='RUNNING · sliders affect output immediately' if state['snapshot']['enabled'] else 'OUTPUT STOPPED · edits do not start it'
        self.connection.set(mode+' · '+running)
        if force or time.monotonic()>=self.next_draw:
            self.next_draw=time.monotonic()+.1
            self.draw()

    @staticmethod
    def chart(canvas,lines,*,duration=1,xlabel='',markers=()):
        canvas.delete('all')
        w,h=max(200,canvas.winfo_width()),max(160,canvas.winfo_height())
        x0,y0,x1,y1=46,30,w-18,h-38
        def point(x,y):return x0+x/duration*(x1-x0),y1-y*(y1-y0)
        for value in (0,.25,.5,.75,1):
            x,y=point(value*duration,value)
            canvas.create_line(x0,y,x1,y,fill='#263244')
            canvas.create_line(x,y0,x,y1,fill='#263244')
            canvas.create_text(x0-8,y,text=f'{value:g}',fill=MUTED,anchor='e',font=('TkDefaultFont',9))
            canvas.create_text(x,y1+12,text=f'{value*duration:g}',fill=MUTED,font=('TkDefaultFont',9))
        for i,(name,points) in enumerate(lines.items()):
            color=COLORS[i%len(COLORS)]
            coords=[v for x,y in points for v in point(x,y)]
            if len(coords)>=4:canvas.create_line(*coords,fill=color,width=2)
            canvas.create_text(x0+i*130,13,text=name,fill=color,anchor='w')
        for i,(_,raw,out) in enumerate(markers):
            if raw is not None and out is not None:
                x,y=point(raw,out)
                canvas.create_oval(x-5,y-5,x+5,y+5,fill=COLORS[i%len(COLORS)],outline=FG,width=2)
        canvas.create_text((x0+x1)/2,h-7,text=xlabel,fill=MUTED,font=('TkDefaultFont',9))

    def draw(self):
        if self.state is None:return
        values=live_values(self.state,self.channel)
        self.chart(self.curve_canvas,self.curves,xlabel='Eye action: OFF (0) → ON (1)' if self.channel in ('left','right') else 'Input: 0 → neutral 0.5 → 1',markers=values)
        self.chart(self.time_canvas,self.timeline,duration=2.5,xlabel='Seconds · return starts at 0.8 s')
        self.readout.set('   |   '.join(name+': unknown · released' if raw is None else
                         f'{name}: input {raw:.3f} → output {out:.3f}' for name,raw,out in values))

    def save(self):
        if not self.flush():return
        data=profile(self.lab.state(),self.name.get())
        path=filedialog.asksaveasfilename(parent=self.window,title='Save tuning profile',
             initialdir=PROFILE_DIR if PROFILE_DIR.exists() else PROFILE_DIR.parent,
             initialfile='signal-tuning.json',defaultextension='.json',filetypes=[('Tuning profile','*.json')])
        if path:
            write_profile(path,data)
            self.notice.set('Saved tuning profile: '+Path(path).name)

    def load(self):
        path=filedialog.askopenfilename(parent=self.window,title='Load tuning profile',
             initialdir=PROFILE_DIR if PROFILE_DIR.exists() else PROFILE_DIR.parent,filetypes=[('Tuning profile','*.json')])
        if path:
            data=read_profile(path)
            self.lab.apply_tuning_profile(data)
            self.name.set(data['name'])
            self.refresh(self.lab.state(),force=True)
            self.notice.set('Profile loaded. Output stopped; center/release inputs and press Start on Signals.')

    def defaults(self):
        data=default_profile(self.lab.state())
        self.lab.apply_tuning_profile(data)
        self.name.set(data['name'])
        self.refresh(self.lab.state(),force=True)
        self.notice.set('Default response restored. Output stopped; press Start on Signals when ready.')
