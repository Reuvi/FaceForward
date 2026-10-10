"""Native source/diagnostic view built around the existing Processing lab."""

from collections import deque
import tkinter as tk
import json
from pathlib import Path
from types import SimpleNamespace
from tkinter import filedialog, ttk

from Processing.mouse.desktop import DesktopLab, Scope, label, set_var, BG, PANEL, TEXT, MUTED, GREEN
from Vision.signals import SIGNALS


SOURCES = {"Vision demo (synthetic)": "demo", "Vision replay (NDJSON)": "replay",
           "Camera (live calibration)": "camera",
           "Detector demo (synthetic pixels)": "detector-demo"}


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
    heading = "Vision + Processing"
    subtitle = "Mouse MVP · native signal lab · simulated mouse output"
    footer = "Mouse preview only    •    Live detector capabilities and raw measurements appear in Vision source & raw signals"

    def __init__(self, root, session, options):
        self.session = session
        self.options = options
        self.vision_history = deque(maxlen=1200)
        self.vision_generation = -1
        self.vision_sequence = None
        self.vision_after = None
        self.preview_photo = None
        self.preview_seen = -1
        self.table_values = {}
        self.calibration_ui = None
        super().__init__(root, session.lab)
        root.title("Face Mouse MVP — Vision + Processing")
        self.notebook.select(self.vision_page)
        self.start_source()
        self.refresh_vision()
        self.notebook.bind("<<NotebookTabChanged>>", self.open_calibration, add="+")

    def build(self):
        super().build()
        # Synthetic eye toggles belong to the standalone Processing developer lab.
        for widget in self.mock_widgets:
            if isinstance(widget, ttk.Checkbutton):
                widget.pack_forget()
        style = ttk.Style(self.root)
        style.configure("Vision.Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=23)
        style.map("Vision.Treeview", background=[("selected", "#405961")], foreground=[("selected", TEXT)])
        self.calibration_page = ttk.Frame(self.notebook)
        self.notebook.insert(0, self.calibration_page, text="Detection calibration")
        self.calibration_hint = label(self.calibration_page, "Choose Camera or Detector demo on the Vision source tab; select your face, then calibrate here.")
        self.calibration_hint.pack(pady=30)
        self.vision_page = ttk.Frame(self.notebook, padding=14)
        self.notebook.insert(0, self.vision_page, text="Vision source & raw signals")
        controls = ttk.Frame(self.vision_page)
        controls.pack(fill="x")
        self.source_var = tk.StringVar(value=next(k for k, v in SOURCES.items() if v == self.options.source))
        ttk.Combobox(controls, textvariable=self.source_var, values=list(SOURCES), state="readonly", width=34).pack(side="left", padx=(0, 8))
        self.button(controls, "Start source", self.start_source).pack(side="left", padx=4)
        self.button(controls, "Stop source", self.session.stop).pack(side="left", padx=4)
        self.button(controls, "Choose replay file", self.choose_replay).pack(side="left", padx=4)
        self.button(controls, "Choose model", self.choose_model).pack(side="left", padx=4)
        label(controls, "FPS").pack(side="left", padx=(15, 5))
        self.fps_var = tk.StringVar(value=str(self.options.fps))
        ttk.Entry(controls, textvariable=self.fps_var, width=5).pack(side="left")
        self.source_status = tk.StringVar(value="Starting Vision")
        label(self.vision_page, textvariable=self.source_status, foreground=GREEN).pack(anchor="w", pady=(10, 5))
        self.source_detail = tk.StringVar()
        label(self.vision_page, textvariable=self.source_detail, foreground=MUTED, wraplength=1270).pack(anchor="w")

        selection = ttk.Frame(self.vision_page)
        selection.pack(fill="x", pady=10)
        label(selection, "Subject").pack(side="left", padx=(0, 8))
        self.subject_var = tk.StringVar()
        self.subject_combo = ttk.Combobox(selection, textvariable=self.subject_var, values=[], state="readonly", width=28)
        self.subject_combo.pack(side="left", padx=(0, 8))
        self.button(selection, "Use selected subject", lambda:self.guarded(self.select_subject)).pack(side="left")
        self.button(selection, "Save active profile", self.save_profile).pack(side="left", padx=8)
        self.button(selection, "Load profile for face", self.load_profile).pack(side="left")
        self.selected_text = tk.StringVar()
        label(selection, textvariable=self.selected_text, foreground=MUTED).pack(side="left", padx=15)

        self.profile_text = tk.StringVar()
        label(self.vision_page, textvariable=self.profile_text, foreground=MUTED).pack(anchor="w", pady=(0,8))

        panels = ttk.Frame(self.vision_page); panels.pack(fill="both", expand=True)
        panels.columnconfigure(0, weight=1); panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)
        signals = ttk.Frame(panels, style="Panel.TFrame", padding=12)
        signals.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        label(signals, "Vision measurements before Processing", style="Heading.TLabel").pack(anchor="w")
        label(signals, "SignalFrame eyes: 1 = open, 0 = closed. Raw mock bits use 1 = closed.", style="Small.TLabel").pack(anchor="w", pady=(5, 8))
        columns = ("signal", "value", "confidence", "status")
        self.signal_table = ttk.Treeview(signals, columns=columns, show="headings", height=8, style="Vision.Treeview")
        for name, width in zip(columns, (155, 75, 80, 120)):
            self.signal_table.heading(name, text=name.title())
            self.signal_table.column(name, width=width, minwidth=60, stretch=True)
        for name in SIGNALS:
            self.signal_table.insert("", "end", iid=name, values=(name, "—", "—", "Unavailable"))
        self.signal_table.pack(fill="x")
        self.raw_ratios = tk.StringVar(value="No camera landmarks received")
        label(signals, "Raw camera ratios / selected subject", style="Heading.TLabel").pack(anchor="w", pady=(13, 6))
        label(signals, textvariable=self.raw_ratios, style="Panel.TLabel", font=("Menlo", 10), justify="left", wraplength=520).pack(anchor="w")
        label(signals, "Calibrate in Detection calibration. Valid measurements feed the same Processing lab.\nTongue segmentation is experimental; inspect its mask and validation checks.",
              style="Small.TLabel", wraplength=550).pack(anchor="w", pady=12)
        self.input_result = tk.StringVar()
        label(signals, textvariable=self.input_result, style="Small.TLabel", wraplength=540).pack(anchor="w")

        camera = ttk.Frame(panels, style="Panel.TFrame", padding=12)
        camera.grid(row=0, column=1, sticky="nsew")
        label(camera, "Camera / source preview", style="Heading.TLabel").pack(anchor="w")
        self.camera_canvas = tk.Canvas(camera, width=480, height=360, background=BG, highlightthickness=0)
        self.camera_canvas.pack(expand=True, pady=8)
        self.preview_item = self.camera_canvas.create_image(0, 0, anchor="nw")
        self.preview_hint = self.camera_canvas.create_text(240, 180, text="", fill=TEXT, width=410,
                                                          font=("Helvetica Neue", 14), justify="center")
        label(camera, "Camera frames stay in memory. The preview does not record video.", style="Small.TLabel").pack(anchor="w")

        scopes = ttk.Frame(self.vision_page); scopes.pack(fill="x", pady=(12, 0))
        self.raw_scopes = []
        for i, (title, keys, limits) in enumerate((
            ("Raw eyelid gap / eye width · left blue / right amber", ("left_open", "right_open"), (0, 0.5)),
            ("Raw iris X / eye width · left blue / right amber", ("left_x", "right_x"), (0, 1)),
            ("Raw iris Y / eye width · left blue / right amber", ("left_y", "right_y"), (-0.3, 0.3)),
        )):
            scopes.columnconfigure(i, weight=1, uniform="vision-scope")
            scope = Scope(scopes, title, keys, limits)
            scope.grid(row=0, column=i, sticky="nsew", padx=(0, 7))
            self.raw_scopes.append(scope)

    def open_calibration(self, event=None):
        if self.notebook.select() != str(self.calibration_page) or self.calibration_ui is not None:
            return
        try:
            from Vision.lab import DetectionLab
            bridge = CalibrationBridge(self.session)
            bridge.snapshot()  # Dependency/setup errors leave the rest of the lab usable.
            self.calibration_hint.pack_forget()
            self.calibration_ui = DetectionLab(
                self.root, SimpleNamespace(demo=False, camera=False), runtime=bridge,
                container=self.calibration_page,
                visible=lambda: not self.closed and self.notebook.select() == str(self.calibration_page))
        except (ImportError, OSError) as exc:
            self.calibration_hint.configure(text=f"Install Vision/requirements.txt in Vision/.venv, then launch with that Python. {exc}")

    def save_profile(self):
        directory = Path("local-profiles")
        directory.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root, title="Save active face + mouse profile", initialdir=str(directory.resolve()),
                                           initialfile="face-mouse.json", defaultextension=".json")
        if path:
            self.guarded(lambda: self.session.save_profile(path))

    def load_profile(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load profile for the selected face", initialdir=str(Path("local-profiles").resolve()),
                                         filetypes=[("Face + mouse profiles", "*.json")])
        if path:
            if self.guarded(lambda: (self.session.load_profile(path), True)):
                self.notebook.select(self.calibration_page)
                self.open_calibration()

    def edited_settings(self):
        data = super().edited_settings()
        current = self.lab.state()["runtime"]
        if any(data["runtime"][key] != current[key] for key in ("source", "subject_id")):
            raise ValueError("Select the source and face on the Vision source tab")
        return data

    def import_settings(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load Processing transfer settings", filetypes=[("JSON settings", "*.json")])
        if path:
            with Path(path).open("rb") as handle:
                raw = handle.read(262145)
            if len(raw) > 262144:
                raise ValueError("Settings exceed 256 KiB")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Settings must be an object")
            if data.get("format") == "face_mouse_profile_v1":
                raise ValueError("Use Load profile for face on the Vision source tab for a combined profile")
            config = data.get("config", data)
            runtime = dict(data.get("runtime", {})) if "config" in data else {}
            for key in ("source", "subject_id"):
                runtime.pop(key, None)
            self.lab.settings({"config": config, "runtime": runtime})

    def choose_replay(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose SignalFrame replay", filetypes=[("NDJSON", "*.ndjson"), ("All files", "*")])
        if path:
            self.options.replay = path
            self.source_var.set("Vision replay (NDJSON)")

    def choose_model(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose local MediaPipe model", filetypes=[("MediaPipe task", "*.task")])
        if path:
            self.options.model = path

    def start_source(self):
        def start():
            self.session.start(SOURCES[self.source_var.get()], path=self.options.replay,
                               model=self.options.model, fps=float(self.fps_var.get()),
                               camera_id=self.options.camera_id, preview=not self.options.no_preview)
            if self.options.subject and SOURCES[self.source_var.get()] == "replay":
                self.lab.settings({"runtime": {"subject_id": self.options.subject}})
        self.guarded(start)

    def select_subject(self):
        self.session.select_subject(self.subject_var.get())
        self.vision_history.clear()

    def refresh_vision(self):
        if self.closed:
            return
        state = self.session.state()
        frame = state["frame"]
        lab_state = self.lab.state(self.after)
        selected = lab_state["runtime"]["subject_id"]
        fresh = (state["running"] and state["age_ms"] is not None
                 and state["age_ms"] <= lab_state["config"]["stale_ms"])
        if self.vision_generation != state["generation"]:
            self.vision_generation = state["generation"]
            self.vision_history.clear()
            self.vision_sequence = None
            self.preview_seen = -1
            self.preview_photo = None
            self.camera_canvas.itemconfigure(self.preview_item, image="")
        faces = (frame or {}).get("faces", [])
        ids = tuple(face["subject_id"] for face in faces)
        if tuple(self.subject_combo.cget("values")) != ids:
            self.subject_combo.configure(values=ids)
        # Display a choice, but bind it only when the user presses Use selected.
        if self.subject_var.get() not in ids:
            set_var(self.subject_var, selected if selected in ids else ids[0] if ids else "")
        age = "—" if state["age_ms"] is None else f"{state['age_ms']:.0f}"
        set_var(self.source_status, f"{state['status']}  |  actual {state['actual_hz']:.1f} Hz  |  received {state['received']} / accepted {state['accepted']}  |  age {age} ms")
        details = {
            "demo": "SYNTHETIC: all four mouse actions. Click Start preview, then open Live lab. Cycle: short blink → left wink → right wink → both → tongue circle → head up/down. Neutral periods allow arming.",
            "replay": "REPLAY: select a subject explicitly, then Start preview with neutral input. Capture gaps are preserved. EOF stops output; restart the source and re-arm to repeat.",
            "camera": "LIVE CAMERA: select your face → Detection calibration (or load a profile) → Start preview → Live lab. One camera stream feeds all tabs; no OS mouse output.",
            "detector-demo": "SYNTHETIC PIXELS: select subject-0, open Detection calibration and Start eye calibration. The fixture follows the guide automatically, then cycles independent closures. No camera or ML.",
        }
        set_var(self.source_detail, state["error"] or details[state["mode"]])
        set_var(self.selected_text, "Processing subject: " + selected)
        set_var(self.profile_text, "Profile: " + state["profile_label"] + (" | attached to selected face; preview starts separately" if state["profile_bound"] else " | no saved profile attached; calibrate or load explicitly"))
        face = next((face for face in faces if face["subject_id"] == selected), None)
        for name in SIGNALS:
            item = face["signals"][name] if face else None
            valid = item and item["valid"]
            status = "Valid" if valid and fresh else "Stale / stopped" if valid else "Unavailable"
            values = (name, f"{item['value']:.4f}" if valid else "—", f"{item['confidence']:.2f}" if item else "—", status)
            if self.table_values.get(name) != values:
                self.signal_table.item(name, values=values)
                self.table_values[name] = values
        raw = state["observations"].get(selected, {})
        eyes = raw.get("eyes", {})
        lines = []
        for eye in ("left", "right"):
            ratios = eyes.get(eye)
            lines.append(f"{eye:5s} open {ratios['openness']:.4f}   X {ratios['horizontal']:.4f}   Y {ratios['vertical']:.4f}" if ratios
                         else f"{eye:5s} unavailable")
        detector_state = None
        if self.session.detector_runtime is not None and state["mode"] in ("camera", "detector-demo"):
            detector_state = self.session.detector_state()
            lines = []
            for key, feature in detector_state["features"].items():
                if key != "face":
                    value = feature["value"]
                    reading = "—" if value is None else f"{value:.4f}"
                    lines.append(f"{key:5s} raw {reading}   quality {feature['quality']:.2f}")
            lines.append("Head units: " + ("image-height fraction" if detector_state["config"]["head_mode"] == "position" else "pitch degrees"))
            lines.append(detector_state["notice"])
        ref = raw.get("head_reference")
        if ref and state["mode"] not in ("camera", "detector-demo"):
            lines.append(f"Face span: {ref['width']:.1f} px   (uncalibrated)")
        if not fresh:
            lines.append("Source stopped or stale; values above are last observed")
        set_var(self.raw_ratios, "\n".join(lines))
        result = lab_state["input_status"]
        set_var(self.input_result, "Latest input: " + (result["reason"] if result else "waiting"))
        token = (frame["session_id"], frame["sequence"], selected) if frame else None
        if token and token != self.vision_sequence:
            self.vision_sequence = token
            row = {"t": frame["timestamp_ms"] / 1000, "scope_context": (frame["session_id"], selected, detector_state["generation"] if detector_state else None)}
            for eye in ("left", "right"):
                ratios = eyes.get(eye, {})
                for field, key in (("open", "openness"), ("x", "horizontal"), ("y", "vertical")):
                    row[f"{eye}_{field}"] = ratios.get(key) if fresh else None
            if detector_state is not None:
                for eye in ("left", "right"):
                    feature = detector_state["features"].get(eye, {})
                    row[eye + "_open"] = feature.get("value") if fresh and feature.get("quality", 0) > 0 else None
            self.vision_history.append(row)
        if self.notebook.select() == str(self.vision_page):
            for scope in self.raw_scopes:
                scope.draw(list(self.vision_history))
            if state["preview"] is not None and state["preview_id"] != self.preview_seen:
                self.preview_photo = tk.PhotoImage(data=state["preview"], format="PPM")
                self.preview_seen = state["preview_id"]
                self.camera_canvas.itemconfigure(self.preview_item, image=self.preview_photo)
            hint = ("" if fresh else "Source stopped / last camera frame") if self.preview_photo else (
                "Vision demo\n\nSynthetic signals → mouse filters → simulated desktop\n\nOpen Live lab to watch all four controls." if state["mode"] == "demo"
                else "No camera preview\n\n" + ("Replay contains measurements only." if state["mode"] == "replay" else "Waiting for camera frames. Check source status."))
            self.camera_canvas.itemconfigure(self.preview_hint, text=hint)
            self.camera_canvas.coords(self.preview_hint, 240, 20 if self.preview_photo else 180)
        self.vision_after = self.root.after(100, self.refresh_vision)

    def close(self):
        if not self.closed:
            if self.calibration_ui is not None:
                self.calibration_ui.eye_panel.close()
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
