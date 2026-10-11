"""Native guided eye prompts, audible cues and sampled binary scopes."""

import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import wave

CUE_LEGEND = ("Four low tones: rest • Rising pair: next pose • Three high tones: capture\n"
              "Descending pair: close • Two high tones: reopen • Rising trio: done")


class CalibrationSounds:
    """Short local tones; afplay on macOS, asynchronous winsound or Tk fallback."""
    PATTERNS = {"start": (660,), "target": (520,), "close": (440, 330),
                "reopen": (880, 880), "success": (660, 880, 1100),
                "retry": (330, 330, 330), "cancel": (880, 880, 330), "test": (660, 880),
                "rest": (440, 440, 440, 440), "rest_reopen": (880, 880, 440, 440, 440, 440),
                "resume": (520, 660), "capture": (1100, 1100, 1100)}

    def __init__(self, root):
        self.root = root
        self.directory = tempfile.TemporaryDirectory(prefix="face-mouse-cues-")
        self.player = shutil.which("afplay") if sys.platform == "darwin" else None
        self.process = None
        self.pending = []
        for name, tones in self.PATTERNS.items():
            samples = []
            for frequency in tones:
                count = 2646  # 120 ms at 22050 Hz, with a click-free amplitude envelope.
                samples.extend(int(7000*min(1,i/220,(count-i)/220)*math.sin(2*math.pi*frequency*i/22050)) for i in range(count))
                samples.extend([0]*2205)
            with wave.open(str(Path(self.directory.name)/(name+".wav")), "wb") as handle:
                handle.setparams((1,2,22050,0,"NONE","not compressed"))
                handle.writeframes(struct.pack("<"+"h"*len(samples), *samples))

    def play(self, name):
        for task in self.pending:
            self.root.after_cancel(task)
        self.pending.clear()
        path = str(Path(self.directory.name)/(name+".wav"))
        try:
            if self.player:
                if self.process is not None:
                    if self.process.poll() is None:
                        self.process.terminate()
                    self.process.wait(timeout=1)
                self.process = subprocess.Popen([self.player,path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        for i in range(len(self.PATTERNS[name])):
            self.pending.append(self.root.after(i*250,self.root.bell))

    def close(self):
        for task in self.pending:
            self.root.after_cancel(task)
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=1)
        self.directory.cleanup()


class FullscreenEyeGuide:
    """Temporary native overlay. It shares the guide; it never owns a camera."""

    def __init__(self, root, cancel):
        self.root = root
        self.previous_focus = root.focus_get()
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Eye calibration — Escape to cancel")
        self.window.transient(root)
        # A borderless overlay avoids changing the lab's size or creating a
        # separate macOS full-screen Space. Tk reports the current screen bounds.
        self.window.overrideredirect(True)
        self.window.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
        self.window.configure(background="#10191e")
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", cancel)
        self.window.bind("<Escape>", lambda event: (cancel(), "break")[1])
        self.canvas = tk.Canvas(self.window, background="#10191e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.cancel_button = ttk.Button(self.window, text="Cancel calibration · Esc", command=cancel)
        self.cancel_button.place(relx=.5, rely=1, y=-28, anchor="s")
        self.window.deiconify()
        self.window.lift()
        self.window.grab_set()
        self.window.focus_set()

    @property
    def ready(self):
        return self.window.winfo_ismapped() and self.canvas.winfo_width() > 100

    def update(self, guide, title, instruction, progress):
        canvas = self.canvas
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 100 or h < 100:
            return
        canvas.create_text(w/2, 35, text=title, fill="#e9f1ed", font=("Arial", 23, "bold"), width=w-80)
        canvas.create_text(w/2, 84, text=instruction, fill="#c2d0df", font=("Arial", 16), width=w-100, justify="center")
        if guide["resting"]:
            seconds = math.ceil(guide["remaining_ms"] / 1000)
            canvas.create_text(w/2,h*.38,text=f"REST · {seconds}s",fill="#75e3a8",font=("Arial",48,"bold"),justify="center",width=w-80,tags="rest-countdown")
            canvas.create_text(w/2,h*.51,text="Next: " + guide.get("next_instruction", guide["instruction"]),fill="#ffffff",font=("Arial",23,"bold"),justify="center",width=w-120,tags="rest-instruction")
            canvas.create_text(w/2,h*.63,text="Relax now. Wait for the ready and capture tones.\nNo calibration samples are being recorded.",fill="#c2d0df",font=("Arial",16),justify="center",width=w-120)
        elif guide["target"]:
            x, y = guide["target"]
            x = x*w
            y = 135+y*max(1, h-310)
            canvas.create_oval(x-25,y-25,x+25,y+25,outline="#345b6c",width=2)
            canvas.create_oval(x-15,y-15,x+15,y+15,fill="#6ed7fe",outline="white",width=2)
            canvas.create_oval(x-3,y-3,x+3,y+3,fill="white",outline="")
        else:
            canvas.create_text(w/2,h/2,text="CLOSE GENTLY\nListen for TWO HIGH TONES to reopen",fill="#ffa663",font=("Arial",27,"bold"),justify="center",width=w-80)
        canvas.create_text(w/2,h-128,text=progress,fill="#c2d0df",font=("Arial",16),justify="center",width=w-80)
        canvas.create_text(w/2,h-78,text="Follow only as far as comfortable • The lab returns automatically",fill="#9cafb3",font=("Arial",12),width=w-80)

    def close(self):
        if self.window is None:
            return
        self.window.grab_release()
        self.window.destroy()
        self.window = None
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()


class EyeGuidePanel:
    def __init__(self, parent, root, call):
        self.root, self.call = root, call
        self.sounds = CalibrationSounds(root)
        self.event = None
        self.aborted = False
        self.fullscreen = None
        self.pending_present = None
        self.rest_seconds = tk.StringVar(value="3")
        self.rest_seen = None
        self.title = tk.StringVar(value="Two separate calibration stages")
        self.instruction = tk.StringVar(value="1. Eye open/closed geometry. 2. Wink action.\nRetrying wink actions keeps your eye geometry.")
        self.fit_status = tk.StringVar()
        self.progress = tk.StringVar(value=CUE_LEGEND)
        ttk.Label(parent,textvariable=self.title,font=("Arial",17,"bold"),wraplength=465).pack(anchor="w",pady=(4,8))
        ttk.Label(parent,textvariable=self.instruction,font=("Arial",13),wraplength=465,justify="left").pack(anchor="w",pady=(0,8))
        ttk.Label(parent,textvariable=self.fit_status,wraplength=465,justify="left").pack(anchor="w",pady=(0,6))
        self.target = tk.Canvas(parent,height=100,bg="#14202c",highlightthickness=0)
        self.target.pack(fill="x")
        ttk.Label(parent,textvariable=self.progress,font=("Arial",11),wraplength=465,justify="left").pack(anchor="w",pady=8)
        rest_row=ttk.Frame(parent);rest_row.pack(fill="x",pady=(0,6))
        ttk.Label(rest_row,text="Rest between steps (seconds)").pack(side="left")
        # The app's light foreground otherwise lands on the spinbox's light field.
        style=ttk.Style(parent)
        style.configure("EyeRest.TSpinbox",fieldbackground="#e4ece9",foreground="#142026",
                        insertcolor="#142026",background="#cfdbd6",arrowcolor="#142026",
                        selectbackground="#365d6a",selectforeground="#ffffff",padding=5)
        style.map("EyeRest.TSpinbox",foreground=[("disabled","#465b62")],
                  fieldbackground=[("disabled","#cbd6d2")],
                  arrowcolor=[("disabled","#465b62"),("active","#142026")])
        self.rest_input=ttk.Spinbox(rest_row,from_=0,to=30,increment=.5,width=6,
                                  textvariable=self.rest_seconds,style="EyeRest.TSpinbox")
        self.rest_input.pack(side="left",padx=8)
        self.start=ttk.Button(parent,text="1  Start eye open/closed",command=lambda:call("start_eye_guide",self.rest_seconds.get()))
        self.start.pack(fill="x",pady=3)
        self.wink_start=ttk.Button(parent,text="2  Start wink action",command=lambda:call("start_wink_guide",self.rest_seconds.get()),state="disabled")
        self.wink_start.pack(fill="x",pady=3)
        buttons=ttk.Frame(parent);buttons.pack(fill="x",pady=4)
        ttk.Button(buttons,text="Cancel",command=self.cancel).pack(side="left",padx=5)
        self.test_sound=ttk.Button(buttons,text="Test sound",command=lambda:self.sounds.play("test"))
        self.test_sound.pack(side="right")
        ttk.Label(parent,text="Keep your head comfortable; only follow as far as feels natural.\nEyes stay independent. Dark traces hold unknown values for display only.",wraplength=465,justify="left").pack(anchor="w",pady=5)

    def dismiss_fullscreen(self):
        if self.pending_present is not None:
            self.root.after_cancel(self.pending_present)
            self.pending_present = None
        if self.fullscreen is not None:
            self.fullscreen.close()
            self.fullscreen = None

    def close(self):
        self.dismiss_fullscreen()
        self.sounds.close()

    def cancel(self):
        self.aborted=True
        self.dismiss_fullscreen()
        self.call("cancel")
        self.sounds.play("cancel")
        self.event=None

    def update(self, state):
        guide=state["eye_guide"]
        kind=guide.get("kind", "winks" if guide.get("wink_training") else "geometry") if guide else None
        active=bool(guide and guide["active"])
        busy=bool(state.get("calibrating") and not active)
        eyes=state["eyes"]
        models=state.get("wink_models", {})
        self.fit_status.set("Eye open/closed: " + (", ".join(eyes) if eyes else "needs calibration") +
                            "\nWink action: " + (", ".join(models) if models else "needs training"))
        rest_ms=state.get("config",{}).get("eye_rest_ms")
        if rest_ms is not None and rest_ms != self.rest_seen:
            self.rest_seconds.set(f"{rest_ms/1000:g}")
            self.rest_seen=rest_ms
        self.rest_input.configure(state="disabled" if guide and guide["active"] else "normal")
        self.start.configure(text="1  Restart eye open/closed" if eyes or kind=="geometry" else "1  Start eye open/closed",
                             state="disabled" if busy or active and kind!="geometry" else "normal")
        self.wink_start.configure(text="2  Restart wink action" if models or kind=="winks" else "2  Start wink action",
                                  state="disabled" if not eyes or busy or active and kind!="winks" else "normal")
        # A sound test must not interrupt the close/reopen instruction cues.
        self.test_sound.configure(state="disabled" if guide and guide["active"] else "normal")
        self.target.delete("all")
        w,h=max(100,self.target.winfo_width()),self.target.winfo_height()
        if not guide:
            self.dismiss_fullscreen()
            if self.event and self.event[2]:
                self.aborted=True
                self.sounds.play("cancel")
            self.event=None
            self.title.set("Calibration stopped — open your eyes" if self.aborted else "Two separate calibration stages")
            self.instruction.set("Completed eye geometry is retained during wink-action retries. Choose the stage to restart." if self.aborted else "First calibrate Eye open/closed; then start Wink action.\nRestarting geometry clears its dependent wink models.")
            self.progress.set(CUE_LEGEND)
            self.target.create_text(w/2,h/2,text="Eye geometry ready · start Wink action" if eyes else "Look at the camera, then start Eye open/closed",fill="#c2d0df",font=("Arial",13),width=w-20)
            if state.get("wink_models") and not self.aborted:
                self.title.set("Wink calibration ready")
                self.instruction.set("Check comfortable closed-eye actions and reopening in the scopes. Restart Wink action to keep your eye geometry.")
                self.progress.set("Checked eye models: "+", ".join(state["wink_models"]))
                self.target.delete("all")
                self.target.create_text(w/2,h/2,text="WINK ACTION = 1 · OPEN = 0",fill="#75e3a8",font=("Arial",16,"bold"))
            return
        self.aborted=False
        event=(state["generation"],guide["index"],guide["active"],guide["phase"])
        if event != self.event:
            self.event=event
            cue=("success" if guide["passed"]==2 else "retry") if not guide["active"] else (
                ("rest_reopen" if guide["name"]=="reopen" else "rest") if guide["resting"] else
                "capture" if guide["phase"]=="capture" else
                "start" if guide["index"]==0 else guide["name"] if guide["name"] in ("closed","reopen") else "resume")
            self.sounds.play("close" if cue=="closed" else cue)
        if not guide["active"]:
            self.dismiss_fullscreen()
            geometry=kind=="geometry"
            self.title.set(("Eye open/closed ready" if geometry else "Wink action ready") if guide["passed"]==2 else "Check each eye’s calibration result")
            self.instruction.set("Eye geometry is retained. Start Wink action separately when ready." if geometry and eyes else
                                 "Retry Eye open/closed with a clear view." if geometry else
                                 "Eye geometry retained. Retry only Wink action if needed.")
            self.progress.set(guide["report"])
            self.target.create_text(w/2,h/2,text="EYE OPEN / CLOSED\nGeometry stage complete" if geometry else "WINK ACTION = 1     OPEN = 0\nNo minimum wink duration\nDark = unknown, last value held",fill="#75e3a8",font=("Arial",16,"bold"),justify="center")
            return
        self.title.set(f"Rest before step {guide['index']+1} / {guide['total']}" if guide["resting"] else f"Step {guide['index']+1} / {guide['total']} — {guide.get('stage', 'Eye shape')} · {guide['name'].upper()}")
        self.instruction.set(guide["instruction"] + ("\nNext: " + guide.get("next_instruction", "Wait for the next instruction") if guide["resting"] else
            "\nFollow the named pose during the capture tones; relax when the rest tone sounds." if guide.get("wink_training") else
            f"\nOpen at TWO HIGH TONES (about {guide['closed_duration_ms']/1000:.0f}s)." if guide["name"]=="closed" else "\nKeep your eyes comfortably open; do not squint."))
        stage="Rest — no samples" if guide["resting"] else "Get ready" if guide["preparing"] else "Sampling — follow the instruction"
        self.progress.set(f"{stage}: {guide['remaining_ms']/1000:.1f}s\nUsable frames: left {guide['samples']['left']}  /  right {guide['samples']['right']}")
        if guide["resting"]:
            self.target.create_text(w/2,h/2,text=f"REST · {math.ceil(guide['remaining_ms']/1000)}s\nNo samples recorded",fill="#75e3a8",font=("Arial",24,"bold"),justify="center",tags="rest-countdown")
        elif guide["target"]:
            x,y=guide["target"];x*=w;y*=h
            self.target.create_oval(x-14,y-14,x+14,y+14,fill="#6ed7fe",outline="white",width=2)
            self.target.create_oval(x-3,y-3,x+3,y+3,fill="white",outline="")
        else:
            self.target.create_text(w/2,h/2,text="CLOSE GENTLY\nListen for two high tones",fill="#ffa663",font=("Arial",19,"bold"),justify="center")
        if self.fullscreen is None:
            self.fullscreen = FullscreenEyeGuide(self.root, self.cancel)
        self.fullscreen.update(guide,self.title.get(),self.instruction.get(),self.progress.get())
        if guide["waiting"] and self.pending_present is None:
            # A step cannot sample until the full-screen instruction is mapped
            # and painted. Re-check the event so cancellation/restart cannot
            # acknowledge an old step in the new guide.
            self.pending_present = self.root.after_idle(lambda event=event: self.present(event))

    def present(self, event):
        self.pending_present = None
        if event != self.event or self.fullscreen is None:
            return
        if not self.fullscreen.ready:
            self.pending_present = self.root.after(30,lambda: self.present(event))
            return
        # First mapping may precede the next 10 Hz refresh. Paint on that refresh
        # before acknowledging; the panel's next update reschedules this callback.
        if not self.fullscreen.canvas.find_all():
            return
        self.call("present_eye_step",event[1],event[3],event[0])
