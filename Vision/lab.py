"""Native detector-only calibration lab. Run: python -m Vision.lab --demo."""

import argparse
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2

from .eye_view import EyeGuidePanel
from .eye_scope import draw_eye_scope, scope_samples
from LabUI.traces import darker, trace_runs
from .features import DetectionConfig
from .lab_runtime import LabRuntime


class DetectionLab:
    def __init__(self, root, args, *, runtime=None, container=None, visible=None):
        self.root, self.args = root, args
        self.embedded = container is not None
        self.visible = visible
        self.runtime = runtime if runtime is not None else LabRuntime()
        self.photos = {}
        if not self.embedded:
            root.title("Vision Detection Lab — calibration only / no mouse output")
            root.geometry("1230x910")
            root.minsize(1100, 830)
        self.source = tk.StringVar(value="Synthetic demo" if args.demo else "Camera")
        self.subject = tk.StringVar()
        self.status = tk.StringVar(value="Start a source; then explicitly select your face.")
        self.source_status = tk.StringVar()
        self.metrics = tk.StringVar()
        self.eye_details = tk.StringVar()
        self.head_details = tk.StringVar()
        self.tongue_details = tk.StringVar()
        outer = ttk.Frame(container if self.embedded else root, padding=10)
        outer.pack(fill="both", expand=True)
        bar = ttk.Frame(outer)
        bar.pack(fill="x")
        self.subject_box = None
        if self.embedded:
            ttk.Label(bar, text="Calibrate the selected Vision source. Then open Live lab.").pack(side="left")
        else:
            ttk.Label(bar, text="DETECTION LAB", font=("Arial",16,"bold")).pack(side="left", padx=(0,20))
            ttk.Combobox(bar, textvariable=self.source, values=("Camera","Synthetic demo"), state="readonly", width=17).pack(side="left")
            ttk.Button(bar, text="Start", command=self.start).pack(side="left", padx=5)
            ttk.Button(bar, text="Stop / clear", command=self.runtime.stop).pack(side="left")
            self.subject_box = ttk.Combobox(bar, textvariable=self.subject, state="readonly", width=17)
            self.subject_box.pack(side="left", padx=(20,5))
            ttk.Button(bar, text="Select face", command=lambda:self.call("select",self.subject.get())).pack(side="left")
        ttk.Button(bar, text="Export trace CSV", command=self.export).pack(side="right")
        ttk.Label(outer,textvariable=self.source_status).pack(anchor="w",pady=5)
        bottom=ttk.Frame(outer);bottom.pack(side="bottom",fill="x",pady=(8,0))
        ttk.Label(bottom,textvariable=self.status,wraplength=1030,justify="left").pack(side="left",fill="x",expand=True)
        ttk.Button(bottom,text="Cancel capture",command=lambda:self.call("cancel")).pack(side="right")
        body = ttk.Frame(outer)
        body.pack(fill="both",expand=True)
        left = ttk.Frame(body)
        left.pack(side="left",fill="both",expand=True)
        right = ttk.Frame(body,width=510)
        right.pack(side="right",fill="both",padx=(12,0))
        right.pack_propagate(False)
        self.preview = tk.Label(left,bg="#15202b",width=640,height=1)
        self.preview.pack(fill="x")
        self.preview.configure(width=0,height=0,text="Camera is off",fg="white",pady=150)
        self.eye_scope=tk.Canvas(left,height=180,bg="#14202c",highlightthickness=0)
        self.eye_scope.pack(fill="x",pady=6)
        self.scope=tk.Canvas(left,height=180 if self.embedded else 220,bg="#14202c",highlightthickness=0)
        self.scope.pack(fill="x",pady=6)
        ttk.Label(left,textvariable=self.metrics,justify="left",wraplength=620,font=("Menlo",9 if self.embedded else 10)).pack(anchor="w")
        tabs=ttk.Notebook(right); tabs.pack(fill="both",expand=True)
        eye=self.tab(tabs,"1 Eyes")
        self.calibration_tabs, self.eye_tab = tabs, eye
        self.eye_panel = EyeGuidePanel(eye,root,self.call)
        ttk.Label(eye,textvariable=self.eye_details,justify="left",wraplength=465,font=("Menlo",10)).pack(anchor="w",pady=8)
        head=self.tab(tabs,"2 Head Y")
        self.text(head,"Default: nose-bridge height / image height. Move your whole head up and down. For nodding instead, change head_mode to pitch in Settings and recalibrate. Pitch uses the face model's camera-frame rotation in degrees.")
        self.text(head,"Hold a comfortable neutral pose, then a comfortable upper and lower limit. Use the same distance from the camera. Raw positions must form stable, distinct groups.")
        for target,label in (("head_neutral","Capture NEUTRAL"),("head_up","Capture UP"),("head_down","Capture DOWN")):
            ttk.Button(head,text=label,command=lambda t=target:self.call("collect",t)).pack(fill="x",pady=6)
        self.text(head,"Normalized Y: up = 0, neutral = 0.5, down = 1. Values beyond the calibrated tolerance are unavailable. This is position, not scroll velocity.")
        ttk.Label(head,textvariable=self.head_details,justify="left",wraplength=430,font=("Menlo",11)).pack(anchor="w",pady=15)
        tongue=self.tab(tabs,"3 Tongue")
        self.text(tongue,"Experimental appearance segmentation. Use steady lighting. First open your mouth with the tongue hidden; then freeze a visible tongue and click ONLY tongue tissue. Lips, gums and teeth must not be marked.")
        ttk.Button(tongue,text="1  Capture EMPTY open mouth",command=lambda:self.call("collect","tongue_absent")).pack(fill="x",pady=3)
        row=ttk.Frame(tongue);row.pack(fill="x",pady=3)
        ttk.Button(row,text="2  Freeze visible tongue",command=lambda:self.call("freeze_mouth")).pack(side="left")
        ttk.Button(row,text="3  Fit appearance model",command=lambda:self.call("fit_tongue")).pack(side="right")
        self.mouth=tk.Label(tongue,bg="#14202c",text="Mouth crop appears after selection",fg="white")
        self.mouth.pack(pady=6)
        self.mouth.bind("<Button-1>",self.mark_tongue)
        ttk.Button(tongue,text="Mark center patch (if covered by tongue)",command=lambda:self.call("mark_tongue",.5,.5)).pack(fill="x",pady=2)
        self.text(tongue,"Frozen image: click a tongue-only patch; repeat with another freeze if needed. Live green mask = candidate, not proof of tongue identity. X increases toward your anatomical right; Y downward.")
        row=ttk.Frame(tongue);row.pack(fill="x",pady=3)
        ttk.Button(row,text="4  Validate ABSENT",command=lambda:self.call("collect","validate_absent")).pack(side="left")
        ttk.Button(row,text="5  Validate VISIBLE",command=lambda:self.call("collect","validate_visible")).pack(side="right")
        ttk.Button(tongue,text="Reset tongue calibration",command=lambda:self.call("reset_tongue")).pack(fill="x",pady=3)
        ttk.Label(tongue,textvariable=self.tongue_details,justify="left",wraplength=430,font=("Menlo",10)).pack(anchor="w",pady=6)
        settings=self.tab(tabs,"Settings")
        self.text(settings,"Edit tunables below. Applying clears all calibration and face selection. Saving stores these tunables only; no face profile or images. head_mode is position or pitch. Measurements and defaults are documented in Vision/DETECTION_LAB.md.")
        self.settings=tk.Text(settings,width=48,height=26,font=("Menlo",10))
        self.settings.pack(fill="both",expand=True,pady=5)
        self.displayed_config = self.runtime.snapshot()["config"]
        self.settings.insert("1.0",json.dumps(self.displayed_config,indent=2))
        row=ttk.Frame(settings);row.pack(fill="x")
        ttk.Button(row,text="Apply settings",command=self.apply_settings).pack(side="left")
        ttk.Button(row,text="Load JSON",command=self.load_settings).pack(side="left")
        ttk.Button(row,text="Save JSON",command=self.save_settings).pack(side="left")
        if not self.embedded:
            root.protocol("WM_DELETE_WINDOW",self.close)
        self.tick()
        if not self.embedded and (args.demo or args.camera):
            root.after(150,self.start)

    def tab(self,tabs,title):
        frame=ttk.Frame(tabs,padding=10);tabs.add(frame,text=title);return frame

    def text(self,parent,text):
        ttk.Label(parent,text=text,wraplength=430,justify="left").pack(anchor="w",pady=7)

    def call(self,name,*args):
        try:
            self.runtime.command(name,*args)
        except (ValueError,TypeError) as exc:
            messagebox.showerror("Cannot complete calibration",str(exc),parent=self.root)

    def start(self):
        try:
            self.runtime.start(demo=self.source.get()=="Synthetic demo",model=self.args.model,camera_id=self.args.camera_id,fps=self.args.fps)
        except (ValueError,TypeError) as exc:
            messagebox.showerror("Cannot start",str(exc),parent=self.root)

    def mark_tongue(self,event):
        if not self.runtime.snapshot()["frozen"]:
            return
        self.call("mark_tongue",event.x/256,event.y/192)

    def apply_settings(self):
        try:
            self.runtime.command("configure",json.loads(self.settings.get("1.0","end")))
        except (ValueError,TypeError) as exc:
            messagebox.showerror("Invalid settings",str(exc),parent=self.root)

    def load_settings(self):
        path=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if path:
            try:
                config=DetectionConfig.from_dict(json.loads(Path(path).read_text()))
                self.settings.delete("1.0","end");self.settings.insert("1.0",json.dumps(config.to_dict(),indent=2))
            except (ValueError,OSError) as exc:
                messagebox.showerror("Cannot load",str(exc),parent=self.root)

    def save_settings(self):
        try:
            config=DetectionConfig.from_dict(json.loads(self.settings.get("1.0","end")))
            path=filedialog.asksaveasfilename(defaultextension=".json",initialfile="detector-settings.json")
            if path:
                Path(path).write_text(json.dumps(config.to_dict(),indent=2)+"\n")
        except (ValueError,OSError) as exc:
            messagebox.showerror("Cannot save",str(exc),parent=self.root)

    def export(self):
        directory=Path("data/private");directory.mkdir(parents=True,exist_ok=True)
        path=filedialog.asksaveasfilename(initialdir=str(directory.resolve()),initialfile="detector-trace.csv",defaultextension=".csv")
        if path:
            try:
                count=self.runtime.export_trace(path)
                messagebox.showinfo("Exported",f"Saved {count} scalar samples to {path}. No images saved.")
            except (ValueError,OSError) as exc:
                messagebox.showerror("Cannot export",str(exc))

    def show_image(self,widget,key,bgr,size,*,frozen=False):
        if bgr is None:
            widget.configure(image="",text="No current image",pady=15)
            self.photos.pop(key,None)
            return
        if key == "mouth" and frozen:
            bgr=bgr.copy()
            cv2.rectangle(bgr,(58,43),(69,54),(0,230,255),1)
        rgb=cv2.cvtColor(cv2.resize(bgr,size),cv2.COLOR_BGR2RGB)
        photo=tk.PhotoImage(data=f"P6\n{size[0]} {size[1]}\n255\n".encode()+rgb.tobytes(),format="PPM")
        self.photos[key]=photo;widget.configure(image=photo,text="",pady=0)

    @staticmethod
    def fmt(value):
        return "—" if value is None else f"{value:.3f}"

    def tick(self):
        state=self.runtime.snapshot()
        hidden=(self.visible is not None and not self.visible()) or self.root.state()=="iconic"
        if state["eye_guide"] and state["eye_guide"]["active"] and (hidden or self.calibration_tabs.select()!=str(self.eye_tab)):
            self.eye_panel.cancel()
            state=self.runtime.snapshot()
            self.eye_panel.update(state)
        if hidden:
            self.root.after(200,self.tick)
            return
        self.eye_panel.update(state)
        if state["config"] != self.displayed_config:
            self.displayed_config = state["config"]
            self.settings.delete("1.0","end")
            self.settings.insert("1.0",json.dumps(self.displayed_config,indent=2))
        self.status.set(state["notice"])
        frame=state["frame"] or {"faces":[]}
        subjects=[f["subject_id"] for f in frame["faces"]]
        if self.subject_box is not None:
            self.subject_box.configure(values=subjects)
            if self.subject.get() not in subjects:
                self.subject.set(subjects[0] if subjects else "")
        timing=state["timing"]
        self.source_status.set(f"{state['source']}   |   selected: {state['selected'] or 'none'}   |   " +
            "   ".join(f"{k}: {v:.1f}" for k,v in timing.items()))
        self.show_image(self.preview,"preview",state["preview"],(320,240))
        self.show_image(self.mouth,"mouth",state["mouth"],(256,192),frozen=state["frozen"])
        signals=next((f["signals"] for f in frame["faces"] if f["subject_id"]==state["selected"]),{})
        eye_lines=[]
        for side in ("left","right"):
            raw=state["features"].get(side,{})
            item=signals.get(side+"_eye_open",{})
            bit=1-int(item["value"]) if item.get("valid") else None
            cal=state["eyes"].get(side)
            label="OPEN (0)" if bit==0 else "CLOSED (1)" if bit==1 else "UNCERTAIN / unavailable"
            eye_lines.append(f"{side.upper()}: {label} | raw {self.fmt(raw.get('value'))}")
            if cal and cal.get("closed_limit") is not None:
                eye_lines.append(f"closed ≤ {cal['closed_limit']:.3f} | open ≥ {cal['open_limit']:.3f}")
            elif cal:
                eye_lines.append("Legacy threshold — run guide for open-pose coverage")
            eye_lines.append(state['reasons'].get(side,'Select a face')+"\n")
        self.eye_details.set("\n".join(eye_lines))
        head=state["features"].get("head",{})
        self.head_details.set(f"Mode: {state['config']['head_mode']}\nRaw: {self.fmt(head.get('value'))}\nNormalized Y: {self.fmt(signals.get('head_y',{}).get('value'))}\nQuality: {head.get('quality',0):.2f}\n{state['reasons'].get('head','Select a face')}\n\nCalibration: {state['head']}\nSamples: " + str({k:v for k,v in state['samples'].items() if k.startswith('head')}))
        val=state["validation"]
        self.tongue_details.set(f"{'FROZEN — click tissue' if state['frozen'] else 'LIVE crop / green candidate mask'}\n{state['reasons'].get('tongue','Select a face')}\nCandidate: {state['candidate']}\nPixels: {state['tongue_pixels']}\n" + "\n".join(f"{k}: {'PASS' if v['passed'] else 'FAIL'} ({v['detected_fraction']:.0%}, n={v['samples']})" for k,v in val.items()))
        self.metrics.set("\n".join(f"{k:16} {self.fmt(signals.get(k,{}).get('value'))}   {'valid' if signals.get(k,{}).get('valid') else 'unavailable'}" for k in ("left_eye_open","right_eye_open","head_y","tongue_x","tongue_y")))
        draw_eye_scope(self.eye_scope,state)
        self.draw_scope(state["trace"],state["selected"],state["generation"],state["config"]["head_mode"],state["config"]["stale_ms"])
        self.root.after(100,self.tick)

    def draw_scope(self,rows,selected,generation,head_mode,stale_ms):
        canvas=self.scope;canvas.delete("all")
        width=max(400,canvas.winfo_width())
        height=max(180,canvas.winfo_height())
        band=(height-16)/3
        specs=[("Raw eye ratio: left cyan / right orange (0–0.4)",(("left_raw","#6ed7fe"),("right_raw","#ffa663")),0,.4),
               ("Raw head Y: " + ("image fraction (0–1)" if head_mode=="position" else "pitch degrees (−45–45)"),(("head_raw","#b18bff"),),0 if head_mode=="position" else -45,1 if head_mode=="position" else 45),
               ("Normalized: head purple / tongue X green / Y yellow (0–1)",(("head_y","#b18bff"),("tongue_x","#75e3a8"),("tongue_y","#f2d66f")),0,1)]
        start=rows[-1]["timestamp_ms"]-8000 if rows else 0
        span=8000
        for index,(label,series,low,high) in enumerate(specs):
            top=5+index*band
            bottom=top+band-10
            canvas.create_text(8,top,text=label,fill="white",anchor="nw",font=("Arial",9))
            canvas.create_line(10,bottom,width-10,bottom,fill="#45515d")
            for key,color in series:
                for unknown, segment in trace_runs(scope_samples(rows,key,selected,generation),max_gap=stale_ms,start=start):
                    points=[]
                    for timestamp,value in segment:
                        points.extend((10+(timestamp-start)/span*(width-20),bottom-(max(low,min(high,value))-low)/(high-low)*(band-33)))
                    canvas.create_line(*points,fill=darker(color) if unknown else color,width=2)
        canvas.create_text(width-8,height-2,text="Last 8 s • dark = unknown hold (display only)",fill="#aab8c8",anchor="se",font=("Arial",9))

    def close(self):
        self.eye_panel.close()
        self.runtime.close();self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group()
    source.add_argument("--demo",action="store_true",help="Start generated pixels and landmarks; no camera or ML")
    source.add_argument("--camera",action="store_true",help="Explicitly open local camera on launch")
    parser.add_argument("--model",default="Vision/.local/face_landmarker.task")
    parser.add_argument("--camera-id",type=int,default=0)
    parser.add_argument("--fps",type=float,default=30)
    args=parser.parse_args()
    if not 1 <= args.fps <= 120 or args.camera_id < 0:
        parser.error("fps must be 1..120 and camera-id nonnegative")
    root=tk.Tk();DetectionLab(root,args);root.mainloop()


if __name__ == "__main__":
    main()
