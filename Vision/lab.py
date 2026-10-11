"""Native detector-only calibration lab. Run: python -m Vision.lab --demo."""

import argparse
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2

from .eye_view import EyeGuidePanel
from .movement_view import MovementPanel, draw_position, draw_raw_scopes, draw_calibrated_scope, draw_pupil_scope
from .eye_scope import draw_eye_scope, draw_feature_scope
from .features import DetectionConfig
from .tongue_view import TongueSetupPanel
from .pupil_view import PupilPanel
from .lab_runtime import LabRuntime


class DetectionLab:
    def __init__(self, root, args, *, runtime=None, container=None, visible=None):
        self.root, self.args = root, args
        self.embedded = container is not None
        self.visible = visible
        self.runtime = runtime if runtime is not None else LabRuntime()
        self.photos = {}
        self.after_id = None
        if not self.embedded:
            root.title("Vision Detection Lab — calibration only / no mouse output")
            root.geometry("1230x910")
            root.minsize(1100, 830)
        self.source = tk.StringVar(value="Synthetic demo" if args.demo else "Camera")
        self.status = tk.StringVar(value="Single user: start a source; your face connects automatically.")
        self.source_status = tk.StringVar()
        self.metrics = tk.StringVar()
        self.eye_details = tk.StringVar()
        self.head_details = tk.StringVar()
        self.tongue_details = tk.StringVar()
        outer = ttk.Frame(container if self.embedded else root, padding=10)
        outer.pack(fill="both", expand=True)
        bar = ttk.Frame(outer)
        bar.pack(fill="x")
        if self.embedded:
            ttk.Label(bar, text="Calibrate the selected Vision source. Then open Live lab.").pack(side="left")
        else:
            ttk.Label(bar, text="DETECTION LAB", font=("Arial",16,"bold")).pack(side="left", padx=(0,20))
            ttk.Combobox(bar, textvariable=self.source, values=("Camera","Synthetic demo"), state="readonly", width=17).pack(side="left")
            ttk.Button(bar, text="Start", command=self.start).pack(side="left", padx=5)
            ttk.Button(bar, text="Stop (keep calibration)", command=self.runtime.stop).pack(side="left")
            ttk.Label(bar, text="Single user · automatic face attachment").pack(side="left", padx=10)
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
        self.eye_scope_mode=tk.StringVar(value="Wink samples")
        self.eye_scope_picker=ttk.Combobox(left,textvariable=self.eye_scope_mode,state="readonly",
            values=("Wink samples","Left facial features","Right facial features","Eye ratios"))
        self.eye_scope_picker.pack(fill="x")
        self.movement_scope_mode=tk.StringVar(value="Raw detector signals")
        self.movement_scope_picker=ttk.Combobox(left,textvariable=self.movement_scope_mode,state="readonly",
            values=("Raw detector signals","Calibrated positions"))
        self.scope=tk.Canvas(left,height=180 if self.embedded else 220,bg="#14202c",highlightthickness=0)
        self.scope.pack(fill="x",pady=6)
        ttk.Label(left,textvariable=self.metrics,justify="left",wraplength=620,font=("Menlo",9 if self.embedded else 10)).pack(anchor="w")
        tabs=ttk.Notebook(right); tabs.pack(fill="both",expand=True)
        eye=self.tab(tabs,"1 Eyes")
        self.calibration_tabs, self.eye_tab = tabs, eye
        self.eye_panel = EyeGuidePanel(eye,root,self.call)
        ttk.Label(eye,textvariable=self.eye_details,justify="left",wraplength=465,font=("Menlo",10)).pack(anchor="w",pady=8)
        head=self.tab(tabs,"2 Head Y")
        self.head_tab=head
        self.text(head,"Nod your head up and down. The guide learns your comfortable pitch limits and neutral position automatically.")
        self.head_panel=MovementPanel(head,root,self.call,"head")
        self.text(head,"Purple shows pitch in degrees using your learned range; green uses the full 0–1 range. Your up limit is 0, neutral is .5 and down limit is 1. Move only as far as comfortable.")
        ttk.Label(head,textvariable=self.head_details,justify="left",wraplength=440,font=("Menlo",10)).pack(anchor="w",pady=10)
        self.tongue_tab=self.tab(tabs,"3 Tongue")
        self.tongue_reset=ttk.Button(self.tongue_tab,text="Reset tongue — start over",command=lambda:self.call("reset_tongue"))
        self.tongue_reset.pack(fill="x",pady=3)
        self.tongue_panel=MovementPanel(self.tongue_tab,root,self.call,"tongue")
        tongue=self.scroll_content(self.tongue_tab)
        self.tongue_setup=TongueSetupPanel(tongue,self.call)
        self.mouth=self.tongue_setup.mouth
        self.mouth.bind("<Button-1>",self.mark_tongue)
        ttk.Label(tongue,textvariable=self.tongue_details,justify="left",wraplength=420,font=("Menlo",10)).pack(anchor="w",pady=6)
        self.pupil_tab=self.tab(tabs,"4 Pupils")
        self.text(self.pupil_tab,"Use your pupil direction as a joystick. Center stops; farther left/right/up/down means more input. Both eyes must be open and visible. This is eye direction, not exact screen gaze.")
        self.pupil_panel=PupilPanel(self.pupil_tab,root,self.call)
        ttk.Button(self.pupil_tab,text="Reset pupil calibration",command=lambda:self.call("reset_pupil")).pack(fill="x",pady=4)
        self.pupil_details=tk.StringVar()
        ttk.Label(self.pupil_tab,textvariable=self.pupil_details,wraplength=440,justify="left").pack(anchor="w",pady=8)
        settings=self.tab(tabs,"Settings")
        self.text(settings,"Edit tunables below. Applying clears calibration; your face reconnects automatically. Saving stores these tunables only. Use Save active profile in the main App to save learned calibration. Head calibration always uses pitch.")
        ttk.Button(settings,text="Reset all calibration",command=lambda:self.call("reset_calibration")).pack(fill="x",pady=5)
        self.settings=tk.Text(settings,width=48,height=26,font=("Menlo",10))
        self.settings.pack(fill="both",expand=True,pady=5)
        self.displayed_config = self.runtime.snapshot()["config"]
        self.settings.insert("1.0",json.dumps(self.editable_settings(self.displayed_config),indent=2))
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

    def scroll_content(self,parent):
        canvas=tk.Canvas(parent,bg="#14202c",highlightthickness=0)
        scrollbar=ttk.Scrollbar(parent,orient="vertical",command=canvas.yview)
        scrollbar.pack(side="right",fill="y");canvas.pack(side="left",fill="both",expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content=ttk.Frame(canvas)
        window=canvas.create_window(0,0,window=content,anchor="nw")
        content.bind("<Configure>",lambda event:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda event:canvas.itemconfigure(window,width=event.width))
        return content

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
        photo = self.photos.get("mouth")
        if photo is None:
            return
        x = (event.x - (self.mouth.winfo_width() - photo.width()) / 2) / photo.width()
        y = (event.y - (self.mouth.winfo_height() - photo.height()) / 2) / photo.height()
        self.call("mark_tongue",x,y)

    @staticmethod
    def editable_settings(config):
        return {key: value for key, value in config.items()
                if key not in ("head_mode", "head_position_separation")}

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
                self.settings.delete("1.0","end");self.settings.insert("1.0",json.dumps(self.editable_settings(config.to_dict()),indent=2))
            except (ValueError,OSError) as exc:
                messagebox.showerror("Cannot load",str(exc),parent=self.root)

    def save_settings(self):
        try:
            config=DetectionConfig.from_dict(json.loads(self.settings.get("1.0","end")))
            config=DetectionConfig.from_dict(self.editable_settings(config.to_dict()))
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

    def show_image(self,widget,key,bgr,size,*,frozen=False,marks=()):
        if bgr is None:
            widget.configure(image="",text="No current image",pady=15)
            self.photos.pop(key,None)
            return
        if key == "mouth" and frozen:
            bgr=bgr.copy()
            for x, y in marks:
                cx, cy = round(x * (bgr.shape[1]-1)), round(y * (bgr.shape[0]-1))
                cv2.rectangle(bgr,(cx-5,cy-5),(cx+5,cy+5),(0,230,255),1)
        rgb=cv2.cvtColor(cv2.resize(bgr,size),cv2.COLOR_BGR2RGB)
        photo=tk.PhotoImage(data=f"P6\n{size[0]} {size[1]}\n255\n".encode()+rgb.tobytes(),format="PPM")
        self.photos[key]=photo;widget.configure(image=photo,text="",pady=0)

    @staticmethod
    def fmt(value):
        return "—" if value is None else f"{value:.3f}"

    def tick(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id=None
        state=self.runtime.snapshot()
        hidden=(self.visible is not None and not self.visible()) or self.root.state()=="iconic"
        if state["eye_guide"] and state["eye_guide"]["active"] and (hidden or self.calibration_tabs.select()!=str(self.eye_tab)):
            self.eye_panel.cancel()
            state=self.runtime.snapshot()
            self.eye_panel.update(state)
        if hidden:
            self.pupil_panel.close_window()
            if state.get("movement_guide") and state["movement_guide"]["active"]:
                self.call("cancel")
            self.after_id=self.root.after(200,self.tick)
            return
        guide=state.get("movement_guide")
        expected=({"head":self.head_tab,"tongue":self.tongue_tab,"pupil":self.pupil_tab}.get(guide["kind"]) if guide else None)
        if guide and guide["active"] and self.calibration_tabs.select()!=str(expected):
            self.call("cancel")
            state=self.runtime.snapshot()
        self.eye_panel.update(state)
        self.head_panel.update(state)
        self.tongue_panel.update(state)
        self.pupil_panel.update(state)
        self.tongue_setup.update(state)
        tongue_busy = (state["collecting"] in ("tongue_absent", "validate_absent", "validate_visible")
                       or bool(state.get("movement_guide") and state["movement_guide"]["kind"] == "tongue" and state["movement_guide"]["active"]))
        self.tongue_reset.configure(state="normal" if not state["calibrating"] or tongue_busy else "disabled")
        if state["config"] != self.displayed_config:
            self.displayed_config = state["config"]
            self.settings.delete("1.0","end")
            self.settings.insert("1.0",json.dumps(self.editable_settings(self.displayed_config),indent=2))
        self.status.set(state["notice"])
        frame=state["frame"] or {"faces":[]}
        timing=state["timing"]
        self.source_status.set(f"{state['source']}   |   capture #{(state['frame'] or {}).get('sequence','—')}   |   single user: {'detected' if state['selected'] else 'waiting for face'}   |   " +
            "   ".join(f"{k}: {v:.1f}" for k,v in timing.items()))
        self.show_image(self.preview,"preview",state["preview"],(320,240))
        self.show_image(self.mouth,"mouth",state["mouth"],(256,256),frozen=state["frozen"],marks=state.get("tongue_marks",()))
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
            reading=state.get("wink_readings",{}).get(side,{})
            eye_lines.append("Wink: "+reading.get("state","unknown")+"; "+("calibrated" if side in state.get("wink_models",{}) else "needs wink-action training"))
            if reading.get("features"):
                v=reading["features"]
                eye_lines.append(f"Blink {v[1]:.2f} · squint {v[2]:.2f} · cheek {v[3]:.2f} · brow {v[4]:.2f}")
            report=state.get("wink_models",{}).get(side)
            if report:
                eye_lines.append(f"Check: {report['wink_recognized']}/{report['wink_frames']} wink frames; {report['false_wink_frames']} false ON")
            eye_lines.append("")
        self.eye_details.set("\n".join(eye_lines))
        head=state["features"].get("head",{})
        self.head_details.set(f"Raw pitch: {self.fmt(head.get('value'))}°\nNormalized Y: {self.fmt(signals.get('head_y',{}).get('value'))}\nQuality: {head.get('quality',0):.2f}\n{state['reasons'].get('head','Waiting for face')}\n\nLearned references: " + (f"\nUp {state['head']['low']:.1f}° = 0\nNeutral {state['head']['center']:.1f}° = .5\nDown {state['head']['high']:.1f}° = 1" if state["head"] else "not calibrated"))
        pupil=state.get("pupil",{})
        self.pupil_details.set("Raw position (eye widths): "+str(pupil.get("xy"))+"\n"+state["reasons"].get("pupil",pupil.get("reason","Waiting"))+"\n"+
            "\n".join(f"{side.title()}: {v.get('xy')} · {v.get('reason')}" for side,v in pupil.get("eyes",{}).items()))
        val=state["validation"]
        self.tongue_details.set(f"{'FROZEN — click tissue' if state['frozen'] else 'LIVE crop / green candidate mask'}\n{state['reasons'].get('tongue','Waiting for face')}\nRaw tip (mouth widths): {state['candidate']}\nPixels: {state['tongue_pixels']}\n" + "\n".join(f"{k}: {'PASS' if v['passed'] else 'FAIL'} ({v['detected_fraction']:.0%}, n={v['samples']})" for k,v in val.items()))
        self.metrics.set("\n".join(f"{k:16} {self.fmt(signals.get(k,{}).get('value'))}   {'valid' if signals.get(k,{}).get('valid') else 'unavailable'}" for k in ("left_eye_open","right_eye_open","head_y","tongue_x","tongue_y","gaze_x","gaze_y")))
        if self.calibration_tabs.select()==str(self.eye_tab):
            draw_eye_scope(self.eye_scope,state)
            self.movement_scope_picker.pack_forget()
            self.eye_scope_picker.pack(fill="x",before=self.scope)
            if self.eye_scope_mode.get()=="Wink samples":
                draw_eye_scope(self.scope,state,intent=True)
            else:
                draw_feature_scope(self.scope,state,self.eye_scope_mode.get())
        else:
            self.eye_scope_picker.pack_forget()
            self.movement_scope_picker.pack(fill="x",before=self.scope)
            kind="pupil" if self.calibration_tabs.select()==str(self.pupil_tab) else "tongue" if self.calibration_tabs.select()==str(self.tongue_tab) else "head"
            draw_position(self.eye_scope,state,kind)
            if self.movement_scope_mode.get()=="Calibrated positions":draw_calibrated_scope(self.scope,state)
            elif kind=="pupil":draw_pupil_scope(self.scope,state)
            else:draw_raw_scopes(self.scope,state)
        self.after_id=self.root.after(100,self.tick)

    def close_panels(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id=None
        self.eye_panel.close()
        self.head_panel.close()
        self.tongue_panel.close()
        self.pupil_panel.close()

    def close(self):
        self.close_panels()
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
