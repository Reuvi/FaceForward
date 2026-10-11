"""Focused native camera, signal processing and calibration workspace."""

import tkinter as tk
from types import SimpleNamespace
from tkinter import filedialog, ttk

from Processing.mouse.desktop import DesktopLab, Scope, label, set_var, BG, TEXT, MUTED, GREEN
from Processing.mappings.view import MappingPanel
from Vision.movement_view import draw_raw_scopes
from Vision.eye_scope import draw_feature_scope
from .paths import DEFAULT_MODEL, PROFILE_DIRECTORY

SOURCES = {"Camera (live calibration)": "camera", "Vision demo (synthetic)": "demo",
           "Detector demo (synthetic pixels)": "detector-demo", "Vision replay (NDJSON)": "replay"}


class CalibrationBridge:
    """Embed Vision's existing view; all lifecycle and output decisions stay in App."""
    def __init__(self, session):
        self.session = session
        self.lock = session.lock

    def snapshot(self):
        return self.session.detector_state()

    def command(self, name, *args):
        return self.session.detector_command(name, *args)

    @property
    def demo_controls(self):
        return self.session.ensure_detector_runtime().demo_controls

    @demo_controls.setter
    def demo_controls(self, values):
        self.session.ensure_detector_runtime().demo_controls = values

    def export_trace(self, path):
        return self.session.ensure_detector_runtime().export_trace(path)


class IntegratedDesktop(DesktopLab):
    appearance_eyes = True
    compact_shell = True
    heading = "Face controller"
    subtitle = "Choose your camera, load a profile, then start control."
    footer = "Stop / Escape releases output    •    Calibration and profile changes require Start again"

    def __init__(self, root, session, options):
        self.session, self.options = session, options
        self.vision_generation = -1
        self.vision_after = None
        self.preview_photo = None
        self.preview_seen = -1
        self.calibration_ui = None
        self.source_request = 0
        self.camera_settings = None
        super().__init__(root, session.lab)
        root.title("Face controller — Signals and Calibration")
        root.geometry("1280x900")
        self.notebook.select(self.vision_page)
        self.start_source()
        if getattr(options, "output", "preview") != "preview":
            self.guarded(lambda: self.session.configure_output(options.output, getattr(options, "driver_library", None)))
        self.refresh_vision()
        self.notebook.bind("<<NotebookTabChanged>>", self.open_calibration, add="+")

    def guarded(self, fn):
        # Clear before calling: nested UI actions must not erase an inner error.
        self.message.set("")
        try:
            return fn()
        except ImportError as exc:
            self.message.set(f"{exc}. Launch with Vision/.venv/bin/python after installing Vision/requirements.txt.")
        except (ValueError, TypeError, OSError, KeyError) as exc:
            self.message.set(str(exc))

    def build_pages(self):
        self.vision_page = ttk.Frame(self.notebook, padding=12)
        self.calibration_page = ttk.Frame(self.notebook)
        self.notebook.add(self.vision_page, text="Signals")
        self.notebook.add(self.calibration_page, text="Calibration")
        self.calibration_hint = label(self.calibration_page, "Choose Camera on Signals, load a profile or start the calibration guides here.")
        self.calibration_hint.pack(pady=30)

        controls = ttk.Frame(self.vision_page)
        controls.pack(fill="x")
        label(controls, "Source").pack(side="left", padx=(0,8))
        self.source_var = tk.StringVar(value=self.source_name(self.options.source))
        self.source_picker = ttk.Combobox(controls, textvariable=self.source_var, values=list(SOURCES), state="readonly", width=28)
        self.source_picker.pack(side="left")
        self.source_picker.bind("<<ComboboxSelected>>", lambda event: self.start_source())
        self.source_start = self.button(controls, "Start source", self.start_source)
        self.source_start.pack(side="left", padx=6)
        self.button(controls, "Stop source", self.stop_source).pack(side="left")
        self.button(controls, "Camera settings…", self.show_camera_settings).pack(side="left", padx=6)
        self.button(controls, "Load profile…", self.load_profile).pack(side="right")
        self.save_profile_button = self.button(controls, "Save profile…", self.save_profile)
        self.save_profile_button.pack(side="right", padx=6)
        self.fps_var = tk.StringVar(value=str(self.options.fps))
        self.camera_id_var = tk.StringVar(value=str(self.options.camera_id))
        self.model_var = tk.StringVar(value=str(self.options.model or DEFAULT_MODEL))

        selection = self.profile_row = ttk.Frame(self.vision_page)
        selection.pack(fill="x", pady=(8,0))
        self.profile_text = tk.StringVar()
        label(selection, textvariable=self.profile_text, foreground=MUTED).pack(side="left")
        self.selected_text = tk.StringVar()
        label(selection, textvariable=self.selected_text, foreground=MUTED).pack(side="right")
        self.replay_selection = ttk.Frame(self.vision_page)
        label(self.replay_selection, "Replay subject").pack(side="left", padx=(0,8))
        self.subject_var = tk.StringVar()
        self.subject_combo = ttk.Combobox(self.replay_selection, textvariable=self.subject_var, state="readonly", width=28)
        self.subject_combo.pack(side="left")
        self.button(self.replay_selection, "Use selected subject", lambda: self.session.select_subject(self.subject_var.get())).pack(side="left", padx=6)
        self.button(self.replay_selection, "Choose replay…", self.choose_replay).pack(side="left")

        output_row = ttk.Frame(self.vision_page)
        output_row.pack(fill="x", pady=8)
        label(output_row, "Output").pack(side="left", padx=(0,8))
        self.output_choices = {"Preview": "preview", "Driver dry run": "dry-run", "Live mouse + keyboard": "native"}
        self.output_var = tk.StringVar(value=next(name for name, mode in self.output_choices.items() if mode == getattr(self.options,"output","preview")))
        ttk.Combobox(output_row, textvariable=self.output_var, values=list(self.output_choices), state="readonly", width=25).pack(side="left")
        self.button(output_row, "Connect output", self.connect_output).pack(side="left", padx=6)
        self.driver_text = tk.StringVar()
        label(output_row, textvariable=self.driver_text, foreground=GREEN, wraplength=700).pack(side="left")
        self.source_status = tk.StringVar()
        label(self.vision_page, textvariable=self.source_status, foreground=GREEN).pack(anchor="w")
        self.source_detail = tk.StringVar()
        label(self.vision_page, textvariable=self.source_detail, foreground=MUTED, wraplength=1180).pack(anchor="w", pady=(3,8))

        panels = ttk.Frame(self.vision_page)
        panels.pack(fill="both", expand=True)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)
        camera = ttk.Frame(panels, style="Panel.TFrame", padding=10)
        camera.grid(row=0, column=0, sticky="nsew", padx=(0,12))
        label(camera, "Camera", style="Heading.TLabel").pack(anchor="w")
        self.camera_canvas = tk.Canvas(camera, width=320, height=240, background=BG, highlightthickness=0)
        self.camera_canvas.pack(pady=8)
        self.preview_item = self.camera_canvas.create_image(0,0,anchor="nw")
        self.preview_hint = self.camera_canvas.create_text(160,120,text="",fill=TEXT,width=290,font=("Helvetica Neue",12),justify="center")
        self.raw_ratios = tk.StringVar()
        self.input_result = tk.StringVar()
        label(camera, textvariable=self.input_result, style="Small.TLabel", wraplength=315).pack(anchor="w", pady=(8,0))
        mapping = ttk.Frame(panels)
        mapping.grid(row=0,column=1,sticky="nsew")
        label(mapping, "Input → filtered signal → command", foreground=GREEN, font=("Helvetica Neue",13,"bold")).pack(anchor="w",pady=(0,8))
        self.mapping_page = MappingPanel(mapping, self, compact=True)
        self.mapping_page.pack(fill="both",expand=True)

        scopes = ttk.Frame(self.vision_page)
        scopes.pack(side="bottom",fill="x", pady=(10,0),before=panels)
        row = ttk.Frame(scopes)
        row.pack(fill="x")
        self.raw_capture = tk.StringVar()
        label(row, textvariable=self.raw_capture, foreground=MUTED).pack(side="left")
        self.raw_graph = tk.StringVar(value="All signals")
        ttk.Combobox(row,textvariable=self.raw_graph,values=("All signals","Head processing","Pointer processing","Left facial features","Right facial features","Eye ratios"),state="readonly",width=21).pack(side="right")
        self.raw_canvas = tk.Canvas(scopes,height=170,background=BG,highlightthickness=0)
        self.raw_canvas.pack(fill="x")
        self.processed_scopes = ttk.Frame(scopes)
        self.processing_charts = {}
        for name, keys in (("Head X",("raw_head_x","filtered_head_x")),("Head Y",("raw_head_y","filtered_head_y")),
                           ("Pointer X",("raw_x","interp_x","out_x")),("Pointer Y",("raw_y","interp_y","out_y"))):
            self.processing_charts[name] = Scope(self.processed_scopes, name+" · input / filtered / output", keys)
            self.processing_charts[name].canvas.configure(height=140)

    @staticmethod
    def source_name(mode):
        return next(name for name, value in SOURCES.items() if value == mode)

    def refresh(self):
        if self.closed:
            return
        self.state = state = self.lab.state(self.after)
        if self.generation != state["generation"]:
            self.generation = state["generation"]
            self.history.clear()
        self.history.extend(state["trace"])
        if state["trace"]:
            self.after = state["trace"][-1]["id"]
        self.mapping_page.refresh(state, self.history)
        mode = state["output"]["mode"]
        self.start_button.configure(text="Start live control" if mode == "native" else "Start dry run" if mode == "dry-run" else "Start preview")
        set_var(self.status, state["snapshot"]["status"] if state["snapshot"]["armed"] else "Output stopped · press Start when ready")
        set_var(self.timing, "PROCESSING 100 Hz · DISPLAY 10 Hz")
        self.root.after(50,self.refresh)

    def open_calibration(self, event=None):
        if self.notebook.select() != str(self.calibration_page) or self.calibration_ui is not None:
            return
        try:
            from Vision.lab import DetectionLab
            bridge = CalibrationBridge(self.session)
            bridge.snapshot()
            self.calibration_hint.pack_forget()
            self.calibration_ui = DetectionLab(self.root,SimpleNamespace(demo=False,camera=False),runtime=bridge,
                container=self.calibration_page,visible=lambda: not self.closed and self.notebook.select()==str(self.calibration_page))
        except (ImportError,OSError) as exc:
            self.calibration_hint.configure(text=f"Install Vision/requirements.txt in Vision/.venv, then launch with that Python. {exc}")

    def save_profile(self):
        PROFILE_DIRECTORY.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root,title="Save face + mouse profile",initialdir=str(PROFILE_DIRECTORY),initialfile="face-mouse.json",defaultextension=".json")
        if path:
            self.guarded(lambda: self.session.save_profile(path))

    def load_profile(self):
        path = filedialog.askopenfilename(parent=self.root,title="Load saved profile",initialdir=str(PROFILE_DIRECTORY),filetypes=[("Face + mouse profiles","*.json")])
        if not path:
            return
        def load():
            data = self.session.read_profile(path)
            mode = "camera" if data["source_kind"] == "camera" else "detector-demo"
            def apply():
                self.session.load_profile(path)
                self.notebook.select(self.vision_page)
                self.message.set("Profile loaded. Older pupil settings need the pupil guide in Calibration; compatible eye/head fits are retained."
                                 if data["detector"]["version"] < 12 else
                                 "Profile loaded. Center your inputs and press Start when ready.")
            self.source_var.set(self.source_name(mode))
            if mode == self.session.mode:
                apply()  # Loading a paused source stays paused; no face is required.
            else:
                self.request_source(mode,start=self.session.state()["running"],on_ready=apply)
        self.guarded(load)

    def show_camera_settings(self):
        if self.camera_settings is not None and self.camera_settings.winfo_exists():
            self.camera_settings.lift()
            return
        dialog = self.camera_settings = tk.Toplevel(self.root)
        dialog.title("Camera settings")
        dialog.transient(self.root)
        body = ttk.Frame(dialog,padding=18)
        body.pack(fill="both",expand=True)
        for row,(title,var) in enumerate((("Camera ID",self.camera_id_var),("Requested FPS",self.fps_var),("Local face model",self.model_var))):
            label(body,title).grid(row=row,column=0,sticky="w",pady=6)
            ttk.Entry(body,textvariable=var,width=65 if row==2 else 8).grid(row=row,column=1,sticky="w",padx=10)
        self.button(body,"Choose model…",self.choose_model).grid(row=3,column=1,sticky="w",padx=10)
        label(body,"Close other camera apps if needed. Camera permissions belong to the app used to launch Python.\nChanges take effect on the next camera start.",foreground=MUTED).grid(row=4,column=0,columnspan=2,pady=12)
        self.button(body,"Done",dialog.destroy).grid(row=5,column=1,sticky="e")

    def choose_replay(self):
        path = filedialog.askopenfilename(parent=self.root,title="Choose SignalFrame replay",filetypes=[("NDJSON","*.ndjson")])
        if path:
            self.options.replay = path
            self.source_var.set(self.source_name("replay"))
            self.start_source()

    def choose_model(self):
        path = filedialog.askopenfilename(parent=self.root,title="Choose local MediaPipe model",filetypes=[("MediaPipe task","*.task")])
        if path:
            self.model_var.set(path)

    def start_source(self):
        def start():
            mode = SOURCES[self.source_var.get()]
            if mode == "replay" and not self.options.replay:
                self.choose_replay()
                return
            self.request_source(mode)
        self.guarded(start)

    def request_source(self, mode, *, start=True, on_ready=None):
        """Release first; poll the old worker without blocking Tk or opening a second camera."""
        fps, camera_id = float(self.fps_var.get()), int(self.camera_id_var.get())
        if not 1 <= fps <= 120 or camera_id < 0:
            raise ValueError("FPS must be 1–120 and Camera ID must be nonnegative")
        model = self.model_var.get()
        self.source_request += 1
        request = self.source_request
        self.session.stop()
        def finish():
            if self.closed or request != self.source_request:
                return
            if self.session.thread is not None and self.session.thread.is_alive():
                self.root.after(50,finish)
                return
            def connect():
                self.session.prepare_source(mode)
                if on_ready:
                    on_ready()
                if start:
                    self.session.start(mode,path=self.options.replay,model=model,fps=fps,camera_id=camera_id,preview=not self.options.no_preview)
                    if getattr(self.options,"subject",None) and mode=="replay":
                        self.lab.settings({"runtime":{"subject_id":self.options.subject}})
            self.guarded(connect)
        finish()

    def stop_source(self):
        self.source_request += 1
        self.session.stop()

    def connect_output(self):
        self.session.configure_output(self.output_choices[self.output_var.get()],getattr(self.options,"driver_library",None))

    def refresh_vision(self):
        if self.closed:
            return
        state = self.session.state(include_detector=True)
        lab_state = self.lab.state(self.after)
        output = lab_state["output"]
        output_label = {"preview":"Preview","dry-run":"Driver dry run","native":"LIVE mouse + keyboard"}[output["mode"]]
        set_var(self.driver_text,output_label+" · "+(output.get("error") or ("running" if output["enabled"] else "stopped")))
        selected = lab_state["runtime"]["subject_id"]
        fresh = state["running"] and state["age_ms"] is not None and state["age_ms"] <= lab_state["config"]["stale_ms"]
        if self.vision_generation != state["generation"]:
            self.vision_generation = state["generation"]
            self.preview_seen = -1
            self.preview_photo = None
            self.camera_canvas.itemconfigure(self.preview_item,image="")
        faces = (state["frame"] or {}).get("faces",[])
        ids = tuple(face["subject_id"] for face in faces)
        if state["mode"]=="replay":
            self.replay_selection.pack(fill="x",before=self.profile_row)
        else:
            self.replay_selection.pack_forget()
        self.subject_combo.configure(values=ids)
        if self.subject_var.get() not in ids:
            set_var(self.subject_var,selected if selected in ids else ids[0] if ids else "")
        self.source_start.configure(text=("Restart camera" if state["running"] else "Start camera") if SOURCES[self.source_var.get()]=="camera" else ("Restart source" if state["running"] else "Start source"))
        set_var(self.source_status,f"{state['status']} · {state['actual_hz']:.1f} frames/s · {state['received']} captures")
        details = {
            "demo":"Synthetic demo — choose Camera above to use your face, or load a camera profile. No camera is open.",
            "replay":"Recorded measurements. Select a replay subject; EOF stops output.",
            "camera":"Load a saved profile or open Calibration. Center inputs and open both eyes before starting control.",
            "detector-demo":"Synthetic face pixels — calibration practice without a camera.",
        }
        set_var(self.source_detail,state["error"] or details[state["mode"]])
        set_var(self.selected_text,("Face detected" if ids and fresh else "Waiting for face" if state["running"] else "Source stopped") if state["mode"] in ("camera","detector-demo") else "Synthetic / replay input")
        set_var(self.profile_text,"Profile: "+state["profile_label"]+(" · saved calibration active" if state["profile_bound"] else ""))
        detector = state["detector"]
        lines = []
        if detector:
            for key, feature in detector["features"].items():
                if key == "face":
                    continue
                value = feature["value"]
                lines.append(f"{key}: {'unknown' if value is None else f'{value:.3f}'}")
            lines = ["Raw detector readings", " · ".join(lines[:2])," · ".join(lines[2:4])," · ".join(lines[4:]),"Head angles in degrees; pupils in eye-width units."]
        if not fresh:
            lines.append("Waiting for fresh input; output released.")
        set_var(self.raw_ratios,"\n".join(lines))
        result = lab_state["input_status"]
        set_var(self.input_result,"Input: "+(result["reason"] if result else "waiting"))
        if self.notebook.select()==str(self.vision_page):
            self.draw_signal_scopes(detector)
            if state["preview"] is not None and state["preview_id"] != self.preview_seen:
                self.preview_photo = tk.PhotoImage(data=state["preview"],format="PPM").zoom(2).subsample(3)
                self.preview_seen = state["preview_id"]
                self.camera_canvas.itemconfigure(self.preview_item,image=self.preview_photo)
            hint = ("" if fresh else "Last camera frame · output released") if self.preview_photo else (
                "Synthetic demo\n\nChoose Camera above or load your camera profile." if state["mode"]=="demo" else
                "Replay has no camera image." if state["mode"]=="replay" else
                "Camera failed to start\n\n"+state["error"] if state["error"] else
                "Preview disabled (--no-preview)" if self.options.no_preview and state["received"] else
                "Waiting for frames…" if state["running"] else "Camera stopped\n\nPress Start camera." if state["mode"]=="camera" else "Detector demo stopped")
            self.camera_canvas.itemconfigure(self.preview_hint,text=hint)
            self.camera_canvas.coords(self.preview_hint,160,16 if self.preview_photo else 120)
        self.vision_after = self.root.after(100,self.refresh_vision)

    def draw_signal_scopes(self, detector):
        graph = self.raw_graph.get()
        processed = graph in ("Head processing","Pointer processing")
        if processed:
            self.raw_canvas.pack_forget()
            self.processed_scopes.pack(fill="x")
            for name, scope in self.processing_charts.items():
                if name.startswith("Head" if graph=="Head processing" else "Pointer"):
                    scope.pack(side="left",fill="both",expand=True)
                    scope.draw(list(self.history))
                else:
                    scope.pack_forget()
            set_var(self.raw_capture,"Blue: input · amber: filtered · green: output")
        else:
            self.processed_scopes.pack_forget()
            self.raw_canvas.pack(fill="x")
            if detector:
                if graph=="All signals":
                    draw_raw_scopes(self.raw_canvas,detector)
                else:
                    draw_feature_scope(self.raw_canvas,detector,graph,include_score=False)
                capture = detector["frame"] or {}
                set_var(self.raw_capture,f"Raw capture #{capture.get('sequence','—')} · shared with Calibration")
            else:
                self.raw_canvas.delete("all")
                self.raw_canvas.create_text(15,25,text="Choose Head processing or Pointer processing to see this demo's signals.",fill=MUTED,anchor="nw")
                set_var(self.raw_capture,"Raw camera measurements appear with Camera or Detector demo")

    def close(self):
        if not self.closed:
            self.source_request += 1
            if self.calibration_ui is not None:
                self.calibration_ui.close_panels()
            self.closed = True
            self.session.close()
            self.root.destroy()


def run(session, options):
    root = tk.Tk()
    app = IntegratedDesktop(root, session, options)
    try:
        root.mainloop()
    finally:
        if not app.closed:
            app.close()
