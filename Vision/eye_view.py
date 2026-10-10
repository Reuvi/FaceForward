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


class CalibrationSounds:
    """Short local tones; afplay on macOS, asynchronous winsound or Tk fallback."""
    PATTERNS = {"start": (660,), "target": (520,), "close": (440, 330),
                "reopen": (880, 880), "success": (660, 880, 1100),
                "retry": (330, 330, 330), "cancel": (880, 880, 330), "test": (660, 880)}

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


class EyeGuidePanel:
    def __init__(self, parent, root, call):
        self.root, self.call = root, call
        self.sounds = CalibrationSounds(root)
        self.event = None
        self.aborted = False
        self.title = tk.StringVar(value="Calibrate eyes in one guided pass")
        self.instruction = tk.StringVar(value="Follow the dot with eyes comfortably open.\nThen close gently and reopen at the sound.")
        self.progress = tk.StringVar(value="Start tone • low tones: close • two high tones: reopen\nThree rising tones: ready • three low tones: retry")
        ttk.Label(parent,textvariable=self.title,font=("Arial",17,"bold"),wraplength=465).pack(anchor="w",pady=(4,8))
        ttk.Label(parent,textvariable=self.instruction,font=("Arial",13),wraplength=465,justify="left").pack(anchor="w",pady=(0,8))
        self.target = tk.Canvas(parent,height=190,bg="#14202c",highlightthickness=0)
        self.target.pack(fill="x")
        ttk.Label(parent,textvariable=self.progress,font=("Arial",11),wraplength=465,justify="left").pack(anchor="w",pady=8)
        buttons=ttk.Frame(parent);buttons.pack(fill="x",pady=4)
        self.start=ttk.Button(buttons,text="Start eye calibration",command=lambda:call("start_eye_guide"))
        self.start.pack(side="left")
        ttk.Button(buttons,text="Cancel",command=self.cancel).pack(side="left",padx=5)
        self.test_sound=ttk.Button(buttons,text="Test sound",command=lambda:self.sounds.play("test"))
        self.test_sound.pack(side="right")
        ttk.Label(parent,text="Keep your head comfortable; only follow as far as feels natural.\nEyes stay independent. Gray / gaps mean uncertain or unavailable.",wraplength=465,justify="left").pack(anchor="w",pady=5)

    def cancel(self):
        self.aborted=True
        self.call("cancel")
        self.sounds.play("cancel")

    def update(self, state):
        guide=state["eye_guide"]
        self.start.configure(text="Restart eye calibration" if guide or state["eyes"] else "Start eye calibration")
        # A sound test must not interrupt the close/reopen instruction cues.
        self.test_sound.configure(state="disabled" if guide and guide["active"] else "normal")
        self.target.delete("all")
        w,h=max(100,self.target.winfo_width()),self.target.winfo_height()
        if not guide:
            if self.event and self.event[2]:
                self.aborted=True
                self.sounds.play("cancel")
            self.event=None
            self.title.set("Calibration stopped — open your eyes" if self.aborted else "Calibrate eyes in one guided pass")
            self.instruction.set("Select a visible face if needed, then Start again." if self.aborted else "Follow the dot with eyes comfortably open.\nThen close gently and reopen at the sound.")
            self.progress.set("Start tone • low tones: close • two high tones: reopen\nThree rising tones: ready • three low tones: retry")
            self.target.create_text(w/2,h/2,text="Select a face, then press Start",fill="#c2d0df",font=("Arial",14))
            return
        self.aborted=False
        event=(state["generation"],guide["index"],guide["active"])
        if event != self.event:
            self.event=event
            cue=("success" if guide["passed"]==2 else "retry") if not guide["active"] else (
                "start" if guide["index"]==0 else guide["name"] if guide["name"] in ("closed","reopen") else "target")
            self.sounds.play("close" if cue=="closed" else cue)
        if not guide["active"]:
            self.title.set("Eyes ready — try looking around" if guide["passed"]==2 else "Calibration needs another pass")
            self.instruction.set("Watch each eye’s 0 / 1 scope. Look in different directions, then close one eye at a time.")
            self.progress.set(guide["report"])
            self.target.create_text(w/2,h/2,text="OPEN = 0     CLOSED = 1\n\nA gap means no decision",fill="#75e3a8",font=("Arial",16,"bold"),justify="center")
            return
        self.title.set(f"Step {guide['index']+1} / {guide['total']} — {guide['name'].upper()}")
        self.instruction.set(guide["instruction"] + (f"\nOpen at TWO HIGH TONES (about {guide['closed_duration_ms']/1000:.0f}s)." if guide["name"]=="closed" else "\nKeep your eyes comfortably open; do not squint."))
        stage="Get ready" if guide["preparing"] else "Sampling — hold this pose"
        self.progress.set(f"{stage}: {guide['remaining_ms']/1000:.1f}s\nUsable frames: left {guide['samples']['left']}  /  right {guide['samples']['right']}")
        if guide["target"]:
            x,y=guide["target"];x*=w;y*=h
            self.target.create_oval(x-14,y-14,x+14,y+14,fill="#6ed7fe",outline="white",width=2)
            self.target.create_oval(x-3,y-3,x+3,y+3,fill="white",outline="")
        else:
            self.target.create_text(w/2,h/2,text="CLOSE GENTLY\nListen for two high tones",fill="#ffa663",font=("Arial",19,"bold"),justify="center")
        if guide["waiting"]:
            # Let Tk paint the new instruction before starting its capture timer.
            self.root.after_idle(lambda i=guide["index"]:self.call("present_eye_step",i))
