"""Native Tk desktop tester. The processing clock runs independently of drawing."""

from collections import deque
import csv
import json
import tkinter as tk
from tkinter import filedialog, ttk

from LabUI.traces import darker, trace_runs

from .controller import Lab


BG, PANEL, EDGE = "#10191e", "#1a272d", "#334950"
TEXT, MUTED = "#e9f1ed", "#9cafb3"
GREEN, BLUE, AMBER = "#b7ed90", "#74ccef", "#efbf82"
SCENARIOS = {"Manual controls": "manual", "Blink vs independent winks": "blink_wink",
             "Pointer orbit": "pointer_circle", "Scroll flick and settle": "scroll_flick",
             "Small input jitter": "jitter", "Stream dropout": "dropout"}


def label(parent, text="", **kwargs):
    return ttk.Label(parent, text=text, **kwargs)


def set_var(variable, value):
    if variable.get() != value:
        variable.set(value)


def compact_points(coords):
    """Remove redundant collinear points, retaining step edges and endpoints."""
    result = []
    for x, y in zip(coords[::2], coords[1::2]):
        if len(result) >= 4:
            ax, ay, bx, by = result[-4:]
            if abs((bx - ax) * (y - by) - (by - ay) * (x - bx)) < 0.001:
                result[-2:] = (x, y)
                continue
        result.extend((x, y))
    return result


class Scope(ttk.Frame):
    def __init__(self, parent, title, keys, limits=(0, 1)):
        super().__init__(parent, style="Panel.TFrame", padding=(9, 7))
        self.keys = keys
        self.channels = [2 if key.endswith("_out") else min(index,2) for index,key in enumerate(keys)]
        self.limits = limits
        label(self, title, style="Small.TLabel").pack(anchor="w")
        self.canvas = tk.Canvas(self, background=BG, height=106, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(5, 0))
        self.size = None
        self.lines = []
        self.drawn = None

    def draw(self, rows):
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 20:
            return
        left, right, top, bottom = 24, width - 9, 10, height - 19
        if self.size != (width, height):
            self.size = (width, height)
            self.drawn = None
            canvas.delete("all")
            low, high = self.limits
            for value in (low, (low + high) / 2, high):
                y = bottom - (value - low) / (high - low) * (bottom - top)
                canvas.create_line(left, y, right, y, fill=EDGE)
                canvas.create_text(3, y, text=str(value), fill=MUTED, anchor="w", font=("Menlo", 8))
            for index in range(5):
                x = left + (right - left) * index / 4
                canvas.create_line(x, top, x, bottom, fill="#23343c")
                canvas.create_text(min(x, right - 8), height - 6, text="now" if index == 4 else f"{index * 2 - 8}s",
                                   fill=MUTED, font=("Menlo", 8))
            self.lines = [canvas.create_line(0, 0, 0, 0, fill=color, width=2 if index == 2 else 1.3,
                                             dash=(3, 3) if index == 1 else ())
                          for index in self.channels for color in ((BLUE, AMBER, GREEN)[index],)]
        if not rows:
            for line in self.lines:
                canvas.itemconfigure(line, state="hidden")
            canvas.delete("gap-run")
            self.drawn = None
            return
        end = rows[-1]["t"]
        channel_runs = []
        for channel, key in enumerate(self.keys):
            samples = ((row["t"], row.get(key), row.get("scope_context", 0)) for row in rows)
            stepped = channel == 0 or key in ("left_out", "right_out", "eye_overlap") or key.endswith("_qualified")
            runs = []
            for unknown, points in trace_runs(samples, step=stepped, start=end-8):
                coords = []
                low, high = self.limits
                for timestamp, value in points:
                    x = left + (timestamp-end+8)/8*(right-left)
                    y = bottom - max(0, min(1, (value-low)/(high-low)))*(bottom-top)
                    coords.extend((x, y))
                runs.append((unknown, compact_points(coords)))
            channel_runs.append(runs)
        if channel_runs == self.drawn:
            return
        self.drawn = channel_runs
        canvas.delete("gap-run")
        for channel, runs in enumerate(channel_runs):
            canvas.itemconfigure(self.lines[channel], state="hidden")
            style = self.channels[channel]
            color = (BLUE, AMBER, GREEN)[style]
            for unknown, points in runs:
                canvas.create_line(*points, fill=darker(color) if unknown else color,
                                   width=2 if style == 2 else 1.3,
                                   dash=(3, 3) if style == 1 else (), tags="gap-run")



class DesktopLab:
    heading = "Mouse Signal Lab"
    subtitle = "Native Python · local processing · simulated mouse output"
    footer = "Mouse preview only    •    Start with centered inputs; Escape stops output"

    def __init__(self, root, lab=None):
        self.root = root
        self.lab = lab or Lab()
        self.closed = False
        self.after = 0
        self.generation = -1
        self.history = deque(maxlen=2000)
        self.frozen = None
        self.state = self.lab.state()
        self.setting_vars = {}
        self.grid_size = None
        self.input_cells = []
        self.vector_cells = []
        self.drawn_inputs = None
        self.drawn_preview = None
        self.refresh_count = 0
        self.mock_widgets = []
        self.input_mode = None
        self.reset_preview()
        root.title("Mouse Signal Lab — Native Python")
        root.geometry("1420x970")
        root.minsize(1150, 850)
        root.configure(background=BG)
        self.style()
        self.build()
        self.lab.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda event: self.action("stop"))
        self.refresh()

    def style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=("Helvetica Neue", 11))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Small.TLabel", background=PANEL, foreground=MUTED, font=("Helvetica Neue", 10))
        style.configure("Panel.TLabel", background=PANEL)
        style.configure("Title.TLabel", font=("Helvetica Neue", 25, "bold"))
        style.configure("Heading.TLabel", background=PANEL, font=("Helvetica Neue", 12, "bold"))
        style.configure("Metric.TLabel", background=PANEL, foreground=GREEN, font=("Menlo", 19))
        style.configure("TButton", padding=(10, 6), background="#2b3e46", foreground=TEXT, borderwidth=1)
        style.map("TButton", background=[("active", "#405961")])
        style.configure("Start.TButton", background=GREEN, foreground="#19231c")
        style.map("Start.TButton", background=[("active", "#d0f5b4")], foreground=[("active", "#19231c")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, padding=4)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TCombobox", fieldbackground="#e4ece9", foreground="#142026", padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", "#e4ece9")], foreground=[("readonly", "#142026")])
        style.configure("TEntry", fieldbackground="#e4ece9", foreground="#142026", padding=5)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#26383f", padding=(18, 8))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", GREEN)])
        style.configure("TLabelframe", background=PANEL, bordercolor=EDGE)
        style.configure("TLabelframe.Label", background=PANEL, foreground=GREEN)

    def button(self, parent, text, command, **kwargs):
        return ttk.Button(parent, text=text, command=lambda: self.guarded(command), **kwargs)

    def guarded(self, fn):
        try:
            result = fn()
            self.message.set("")
            return result
        except (ValueError, TypeError, OSError, KeyError) as exc:
            self.message.set(str(exc))

    def action(self, action_name, **kwargs):
        return self.guarded(lambda: self.lab.action({"action": action_name, **kwargs}))

    def build(self):
        header = ttk.Frame(self.root, padding=(22, 17, 22, 8))
        header.pack(fill="x")
        label(header, "FACE CONTROLLER / PROCESSING", foreground=GREEN, font=("Menlo", 9)).grid(row=0, column=0, sticky="w")
        label(header, self.heading, style="Title.TLabel").grid(row=1, column=0, sticky="w")
        label(header, self.subtitle, foreground=MUTED).grid(row=2, column=0, sticky="w", pady=(3, 0))
        header.columnconfigure(0, weight=1)
        self.button(header, "Start preview", lambda: self.action("arm"), style="Start.TButton").grid(row=1, column=1, padx=5)
        self.button(header, "Stop / Esc", lambda: self.action("stop")).grid(row=1, column=2, padx=5)
        self.status = tk.StringVar(value="Preview stopped")
        self.timing = tk.StringVar()
        status = ttk.Frame(self.root, padding=(23, 2, 23, 6)); status.pack(fill="x")
        label(status, textvariable=self.status, foreground=GREEN).pack(side="left")
        label(status, textvariable=self.timing, foreground=MUTED, font=("Menlo", 9)).pack(side="right")
        self.notebook = ttk.Notebook(self.root); self.notebook.pack(fill="both", expand=True, padx=18, pady=6)
        self.live = ttk.Frame(self.notebook, padding=12)
        self.settings_page = ttk.Frame(self.notebook, padding=18)
        self.inspect_page = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(self.live, text="Live lab")
        self.notebook.add(self.settings_page, text="Transfer settings")
        self.notebook.add(self.inspect_page, text="Input / output")
        self.build_live()
        self.build_settings()
        self.build_inspector()
        self.message = tk.StringVar()
        label(self.root, textvariable=self.message, foreground="#ffa79c", wraplength=1300).pack(fill="x", padx=22)
        label(self.root, self.footer,
              foreground=MUTED, font=("Menlo", 9)).pack(anchor="w", padx=22, pady=(4, 10))

    def build_live(self):
        self.live.columnconfigure(1, weight=1)
        self.live.rowconfigure(2, weight=1)
        inputs = ttk.Frame(self.live, style="Panel.TFrame", padding=13)
        inputs.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        label(inputs, "01  Input bench", style="Heading.TLabel").pack(anchor="w")
        self.scenario = tk.StringVar(value="Manual controls")
        combo = ttk.Combobox(inputs, textvariable=self.scenario, values=list(SCENARIOS), state="readonly", width=30)
        combo.pack(fill="x", pady=8)
        self.mock_combo = combo
        combo.bind("<<ComboboxSelected>>", lambda event: self.action("scenario", name=SCENARIOS[self.scenario.get()]))
        maps = ttk.Frame(inputs, style="Panel.TFrame"); maps.pack(fill="x")
        label(maps, "2D pointer matrix", style="Small.TLabel").grid(row=0, column=0, sticky="w")
        label(maps, "Head Y", style="Small.TLabel").grid(row=0, column=1, padx=(12, 0))
        self.matrix = tk.Canvas(maps, width=245, height=215, background=BG, highlightthickness=0)
        self.matrix.grid(row=1, column=0, pady=5)
        self.vector = tk.Canvas(maps, width=38, height=215, background=BG, highlightthickness=0)
        self.vector.grid(row=1, column=1, padx=(12, 0), pady=5)
        self.matrix.bind("<Button-1>", self.matrix_input); self.matrix.bind("<B1-Motion>", self.matrix_input)
        self.vector.bind("<Button-1>", self.vector_input); self.vector.bind("<B1-Motion>", self.vector_input)
        self.position = tk.StringVar(value="Center = stopped; offset = velocity")
        label(inputs, textvariable=self.position, style="Small.TLabel").pack(anchor="w")
        eyes = ttk.Frame(inputs, style="Panel.TFrame"); eyes.pack(fill="x", pady=4)
        self.eye_vars = {}
        for eye in ("left", "right"):
            var = tk.BooleanVar(value=False); self.eye_vars[eye] = var
            widget = ttk.Checkbutton(eyes, text=f"{eye.title()} eye closed → {eye} click", variable=var,
                                     command=lambda key=eye: self.lab.control({key: self.eye_vars[key].get()}))
            widget.pack(anchor="w"); self.mock_widgets.append(widget)
        buttons = ttk.Frame(inputs, style="Panel.TFrame"); buttons.pack(fill="x", pady=(3, 0))
        for text, action in (("Blink 120 ms", "blink"), ("Left wink", "left_wink"), ("Right wink", "right_wink")):
            widget = self.button(buttons, text, lambda action=action: self.lab.action({"action": action}))
            widget.pack(side="left", padx=(0, 4)); self.mock_widgets.append(widget)
        widget = self.button(inputs, "Center inputs & open eyes", lambda: self.lab.action({"action": "center"}))
        widget.pack(fill="x", pady=(7, 0)); self.mock_widgets.append(widget)

        preview = ttk.Frame(self.live, style="Panel.TFrame", padding=13)
        preview.grid(row=0, column=1, sticky="nsew")
        heading = ttk.Frame(preview, style="Panel.TFrame"); heading.pack(fill="x")
        label(heading, "02  Mouse playground", style="Heading.TLabel").pack(side="left")
        self.button(heading, "Reset counters", self.reset_preview).pack(side="right")
        metrics = ttk.Frame(preview, style="Panel.TFrame"); metrics.pack(fill="x", pady=9)
        self.metrics = {}
        for index, (name, title) in enumerate((("pointer_x", "POINTER X"), ("pointer_y", "POINTER Y"), ("scroll_y", "SCROLL"), ("buttons", "LEFT / RIGHT"))):
            cell = ttk.Frame(metrics, style="Panel.TFrame"); cell.pack(side="left", fill="x", expand=True)
            label(cell, title, style="Small.TLabel").pack(anchor="w")
            var = tk.StringVar(value="0.500"); self.metrics[name] = var
            label(cell, textvariable=var, style="Metric.TLabel").pack(anchor="w")
        self.playground = tk.Canvas(preview, height=230, background=BG, highlightthickness=1, highlightbackground=EDGE)
        self.playground.pack(fill="both", expand=True)
        self.playground.bind("<Configure>", lambda event: self.build_playground())
        self.counts = tk.StringVar(value="Left presses 0 · Right presses 0 · Scroll 0 px")
        label(preview, textvariable=self.counts, style="Small.TLabel").pack(anchor="w", pady=6)
        row = ttk.Frame(preview, style="Panel.TFrame"); row.pack(fill="x")
        self.stream_button = self.button(row, "Pause input stream", lambda: self.lab.action({"action": "stream", "enabled": not self.state["streaming"]}))
        self.stream_button.pack(side="left", padx=(0, 7))
        self.mock_widgets.append(self.stream_button)
        self.button(row, "Calibrate current neutral", lambda: self.lab.action({"action": "calibrate"})).pack(side="left")
        self.boost = tk.StringVar()
        label(preview, textvariable=self.boost, style="Small.TLabel").pack(anchor="w", pady=(6, 0))

        scope_header = ttk.Frame(self.live, padding=(0, 10, 0, 6)); scope_header.grid(row=1, column=0, columnspan=2, sticky="ew")
        label(scope_header, "03  Signal scope / 8 s • dark = unknown hold", font=("Helvetica Neue", 11, "bold")).pack(side="left")
        self.button(scope_header, "Export CSV", self.export_trace).pack(side="right", padx=(6, 0))
        self.freeze_button = self.button(scope_header, "Freeze scope", self.freeze)
        self.freeze_button.pack(side="right", padx=(6, 12))
        for text, color in (("Output", GREEN), ("Interpolation / dwell", AMBER), ("Raw samples", BLUE)):
            if getattr(self,"appearance_eyes",False) and text=="Interpolation / dwell":text="Axis interpolation"
            label(scope_header, "— " + text, foreground=color, font=("Helvetica Neue", 9)).pack(side="right", padx=7)
        charts = ttk.Frame(self.live); charts.grid(row=2, column=0, columnspan=2, sticky="nsew")
        charts.rowconfigure((0, 1), weight=1)
        self.scopes = []
        axis = ttk.Frame(charts); axis.grid(row=0, column=0, sticky="nsew", pady=(0, 7))
        eyes = ttk.Frame(charts); eyes.grid(row=1, column=0, sticky="nsew")
        charts.columnconfigure(0, weight=1)
        for parent, specs in ((axis, (("Pointer X / left ↔ right", ("raw_x", "interp_x", "out_x")),
                                     ("Pointer Y / up ↔ down", ("raw_y", "interp_y", "out_y")),
                                     ("Scroll Y / up ↔ down", ("raw_scroll", "interp_scroll", "out_scroll")))),
                              (eyes, (("Left eye → left click (independent)", ("left_raw", "left_dwell", "left_out")),
                                      ("Right eye → right click (independent)", ("right_raw", "right_dwell", "right_out"))))):
            parent.rowconfigure(0, weight=1)
            for index, (title, keys) in enumerate(specs):
                if getattr(self,"appearance_eyes",False) and keys[0] in ("left_raw","right_raw"):
                    title=title.replace("eye", "eye input")
                    keys=(keys[0],keys[2])
                parent.columnconfigure(index, weight=1, uniform="scope")
                scope = Scope(parent, title, keys); scope.grid(row=0, column=index, sticky="nsew", padx=(0, 6 if index < len(specs) - 1 else 0))
                self.scopes.append(scope)

    def build_settings(self):
        toolbar = ttk.Frame(self.settings_page); toolbar.pack(fill="x")
        for text, command in (("Apply settings", self.apply_settings), ("Export JSON", self.export_settings), ("Import JSON", self.import_settings)):
            self.button(toolbar, text, command).pack(side="left", padx=(0, 8))
        label(self.settings_page, "Applying settings stops preview. Camera wink states use facial calibration, with no duration threshold." if getattr(self,"appearance_eyes",False) else "Applying settings stops the preview and resets filters. Center inputs, then start again. Each eye has its own timings.",
              foreground=MUTED, wraplength=1200).pack(anchor="w", pady=12)
        groups = ttk.Frame(self.settings_page); groups.pack(fill="both", expand=True)
        specs = [
            ("Sampling & source", [
                ("runtime.sample_hz", "Input Hz", None), ("config.interpolation_ms", "Interpolation ms", None),
                ("config.stale_ms", "Stale timeout ms", None), ("config.pointer_source", "Pointer source", (self.lab.locked_pointer_source,) if self.lab.locked_pointer_source else ("tongue", "gaze")),
                ("config.closed_value", "Closed eye bit", ("1", "0")), ("runtime.rows", "Matrix rows (odd)", None),
                ("runtime.columns", "Matrix columns (odd)", None), ("runtime.vector_size", "Vector size (odd)", None),
                ("runtime.source", "Sample source", ("mock", "external")), ("runtime.subject_id", "Selected subject", "text"),
                ("config.min_confidence", "V1 min confidence", None)],
             "Output: 100 Hz; scope: 10 Hz. Input and output clocks run independently of the UI. External mode accepts local Python calls."),
            ("Independent eyes", [
                ("config.left_eye.dwell_ms", "Left dwell ms", None), ("config.left_eye.release_ms", "Left release ms", None),
                ("config.right_eye.dwell_ms", "Right dwell ms", None), ("config.right_eye.release_ms", "Right release ms", None)],
             "1 = closed by default. Short closures do not click. Long closures hold the corresponding button. No combined-eye suppression. Each eye must first be open."),
        ]
        if getattr(self,"appearance_eyes",False):
            specs[1]=("Independent wink samples", [],
                      "Train wink actions in Detection calibration. A recognized wink stays ON while held and turns OFF on reopening. No dwell or release delay. Legacy raw demos/replays retain their original timing.")
        for axis in ("pointer", "scroll"):
            fields = [(f"config.{axis}.{key}", text, kind) for key, text, kind in (
                ("deadzone", "Dead zone", None), ("hysteresis", "Activation margin", None), ("exponent", "Response exponent", None),
                ("smoothing_ms", "Smoothing ms", None), ("acceleration", "Acceleration / s", None),
                ("deceleration", "Deceleration / s", None), ("jump_threshold", "Min jump", None),
                ("boost_gain", "Boost gain (s)", None), ("boost_max", "Max boost", None), ("boost_decay_ms", "Boost decay ms", None),
                ("center_y", "Neutral Y", None), ("invert_y", "Invert Y", "bool"))]
            if axis == "pointer":
                fields.extend((("config.pointer.center_x", "Neutral X", None), ("config.pointer.invert_x", "Invert X", "bool")))
            fields.append((f"runtime.{axis}_speed", "Preview max px/s", None))
            specs.append((axis.title() + " response", fields,
                          "Normalized velocity: 0.5 is stopped. Boost gain 0 disables flick boost. Speeds in px/s apply to the preview only."))
        for index, (title, fields, help_text) in enumerate(specs):
            groups.columnconfigure(index, weight=1, uniform="settings")
            group = ttk.LabelFrame(groups, text=title, padding=12)
            group.grid(row=0, column=index, sticky="nsew", padx=(0, 8))
            group.columnconfigure(1, weight=1)
            for row, (path, text, kind) in enumerate(fields):
                label(group, text, style="Small.TLabel").grid(row=row, column=0, sticky="w", pady=5)
                var = tk.BooleanVar() if kind == "bool" else tk.StringVar()
                self.setting_vars[path] = (var, kind)
                if kind == "bool":
                    widget = ttk.Checkbutton(group, variable=var)
                elif isinstance(kind, tuple):
                    widget = ttk.Combobox(group, textvariable=var, values=kind, state="readonly", width=9)
                else:
                    widget = ttk.Entry(group, textvariable=var, width=10)
                widget.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=5)
            label(group, help_text, style="Small.TLabel", wraplength=245).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=15)

    def build_inspector(self):
        label(self.inspect_page, "Raw input and provisional driver output", font=("Helvetica Neue", 16, "bold")).pack(anchor="w")
        label(self.inspect_page, "Serialization is isolated in mouse/output.py. The final emulator format is still pending.", foreground=MUTED).pack(anchor="w", pady=8)
        panes = ttk.Panedwindow(self.inspect_page, orient="horizontal"); panes.pack(fill="both", expand=True)
        self.raw_text, self.output_text = (tk.Text(panes, background=BG, foreground=TEXT, insertbackground=TEXT, font=("Menlo", 10), wrap="none", width=50) for _ in range(2))
        panes.add(self.raw_text, weight=1); panes.add(self.output_text, weight=1)

    def reset_preview(self):
        self.sim = {"x": 0.5, "y": 0.5, "scroll": 0.0, "left": 0, "right": 0,
                    "prev_left": 0, "prev_right": 0, "t": None}

    def build_playground(self):
        canvas = self.playground
        self.drawn_preview = None
        width, height = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete("all")
        for x in range(15, width, 24):
            for y in range(15, height, 24):
                canvas.create_oval(x, y, x + 1, y + 1, fill=EDGE, outline="")
        canvas.create_text(15, 14, anchor="nw", text="SIMULATED DESKTOP   /   0.5 = stopped", fill=MUTED, font=("Menlo", 9))
        x0, x1 = width * 0.2, width * 0.8
        canvas.create_rectangle(x0, 40, x1, 600, fill="#d9e4d8", outline="", tags="paper")
        canvas.create_text(x0 + 22, 84, anchor="nw", text="Move with intention.", font=("Helvetica Neue", 21, "bold"), fill="#354c3c", tags="paper")
        canvas.create_text(x0 + 22, 123, anchor="nw", text="The matrix drives this cursor.\nThe head vector scrolls this page.", font=("Helvetica Neue", 12), fill="#354c3c", tags="paper")
        for index in range(20):
            y = 200 + index * 19
            canvas.create_line(x0 + 23, y, x1 - 23 - (60 if index % 3 == 0 else 0), y, width=5, fill="#b3c3b1", tags="paper")
        self.paper_shift = 0
        self.cursor = canvas.create_polygon(0, 0, 0, 25, 7, 19, 12, 29, 17, 27, 12, 17, 22, 17,
                                             fill=GREEN, outline=BG, width=2)

    def matrix_input(self, event):
        runtime = self.state["runtime"]
        if runtime["source"] != "mock":
            return
        x = min(runtime["columns"] - 1, max(0, int(event.x / self.matrix.winfo_width() * runtime["columns"])))
        y = min(runtime["rows"] - 1, max(0, int(event.y / self.matrix.winfo_height() * runtime["rows"])))
        self.lab.control({"x": x / (runtime["columns"] - 1), "y": y / (runtime["rows"] - 1)})

    def vector_input(self, event):
        if self.state["runtime"]["source"] != "mock":
            return
        size = self.state["runtime"]["vector_size"]
        index = min(size - 1, max(0, int(event.y / self.vector.winfo_height() * size)))
        self.lab.control({"scroll": index / (size - 1)})

    def draw_inputs(self, state):
        runtime, diag = state["runtime"], state["snapshot"]["diagnostics"]
        size = (runtime["rows"], runtime["columns"], runtime["vector_size"])
        if self.grid_size != size:
            self.drawn_inputs = None
            self.grid_size = size
            self.matrix.delete("all"); self.vector.delete("all")
            self.input_cells, self.vector_cells = [], []
            for y in range(size[0]):
                for x in range(size[1]):
                    cell = self.matrix.create_rectangle(x * 245 / size[1] + 2, y * 215 / size[0] + 2,
                                                        (x + 1) * 245 / size[1] - 2, (y + 1) * 215 / size[0] - 2,
                                                        fill=EDGE, outline="")
                    self.input_cells.append((cell, x, y))
            for y in range(size[2]):
                self.vector_cells.append(self.vector.create_rectangle(3, y * 215 / size[2] + 2, 35,
                                                                      (y + 1) * 215 / size[2] - 2, fill=EDGE, outline=""))
        point = diag["raw_pointer"]
        active = (round(point[0] * (size[1] - 1)), round(point[1] * (size[0] - 1))) if point else None
        active_y = round(diag["raw_scroll"] * (size[2] - 1)) if diag["raw_scroll"] is not None else None
        if self.drawn_inputs != (active, active_y):
            for cell, x, y in self.input_cells:
                self.matrix.itemconfigure(cell, fill=GREEN if active == (x, y) else "#50626a" if (x, y) == ((size[1] - 1) // 2, (size[0] - 1) // 2) else EDGE)
            for y, cell in enumerate(self.vector_cells):
                self.vector.itemconfigure(cell, fill=GREEN if active_y == y else "#50626a" if y == (size[2] - 1) // 2 else EDGE)
            self.drawn_inputs = (active, active_y)
        set_var(self.position, f"X {point[0]:.3f}   Y {point[1]:.3f}  / offset = velocity" if point else "No valid pointer sample")
        for eye, var in self.eye_vars.items():
            set_var(var, state["manual"][eye] if runtime["source"] == "mock" else bool(diag[eye + "_closed"]))

    @staticmethod
    def get_path(value, path):
        for key in path.split("."):
            value = value[key]
        return value

    def fill_settings(self):
        for path, (var, _) in self.setting_vars.items():
            var.set(self.get_path(self.state, path))

    def edited_settings(self):
        data = json.loads(json.dumps({"config": self.state["config"], "runtime": self.state["runtime"]}))
        for path, (var, kind) in self.setting_vars.items():
            keys = path.split(".")
            target = data
            for key in keys[:-1]:
                target = target[key]
            original = target[keys[-1]]
            if kind == "bool":
                value = var.get()
            elif isinstance(original, str):
                value = var.get()
            else:
                try:
                    value = int(var.get()) if path in ("runtime.rows", "runtime.columns", "runtime.vector_size", "config.closed_value") else float(var.get())
                except ValueError as exc:
                    raise ValueError(f"Invalid number for {path}") from exc
            target[keys[-1]] = value
        return data

    def apply_settings(self):
        self.lab.settings(self.edited_settings())

    def export_settings(self):
        settings = self.edited_settings()
        # Validate without changing the active processor.
        from .config import MouseConfig
        MouseConfig.from_dict(settings["config"])
        path = filedialog.asksaveasfilename(parent=self.root, title="Save mouse settings", defaultextension=".json", filetypes=[("JSON settings", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(settings, file, indent=2, allow_nan=False)

    def import_settings(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load mouse settings", filetypes=[("JSON settings", "*.json")])
        if path:
            with open(path, encoding="utf-8") as file:
                data = json.loads(file.read(262145))
            if not isinstance(data, dict):
                raise ValueError("Settings must be an object")
            self.lab.settings(data if "config" in data else {"config": data})

    def freeze(self):
        self.frozen = None if self.frozen is not None else list(self.history)
        self.freeze_button.configure(text="Resume scope" if self.frozen is not None else "Freeze scope")

    def export_trace(self):
        rows = self.frozen if self.frozen is not None else list(self.history)
        if not rows:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Save signal trace", defaultextension=".csv", filetypes=[("CSV trace", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

    def integrate(self, rows, runtime):
        width, height = max(1, self.playground.winfo_width()), max(1, self.playground.winfo_height())
        for row in rows:
            dt = 0 if self.sim["t"] is None else max(0, min(0.05, row["t"] - self.sim["t"]))
            self.sim["t"] = row["t"]
            for axis, dimension in (("x", width), ("y", height)):
                self.sim[axis] = max(0.03, min(0.92, self.sim[axis] + (2 * row["out_" + axis] - 1) * runtime["pointer_speed"] * dt / dimension))
            self.sim["scroll"] += (2 * row["out_scroll"] - 1) * runtime["scroll_speed"] * dt
            for eye in ("left", "right"):
                if row[eye + "_out"] and not self.sim["prev_" + eye]:
                    self.sim[eye] += 1
                self.sim["prev_" + eye] = row[eye + "_out"]

    def refresh(self):
        if self.closed:
            return
        self.state = state = self.lab.state(self.after)
        if self.generation != state["generation"]:
            self.generation = state["generation"]
            self.history.clear(); self.frozen = None; self.sim["t"] = None
            self.sim["prev_left"] = self.sim["prev_right"] = 0
            self.freeze_button.configure(text="Freeze scope")
            self.fill_settings()
        self.integrate(state["trace"], state["runtime"])
        self.history.extend(state["trace"])
        if state["trace"]:
            self.after = state["trace"][-1]["id"]
        snap, diag = state["snapshot"], state["snapshot"]["diagnostics"]
        if self.input_mode != state["runtime"]["source"]:
            self.input_mode = state["runtime"]["source"]
            external = self.input_mode == "external"
            self.mock_combo.configure(state="disabled" if external else "readonly")
            for widget in self.mock_widgets:
                widget.configure(state="disabled" if external else "normal")
        set_var(self.status, snap["status"])
        age = "—" if diag["age_ms"] is None else f"{diag['age_ms']:.0f}"
        self.refresh_count += 1
        if self.refresh_count % 5 == 0:
            source = "VISION / EXTERNAL" if state["runtime"]["source"] == "external" else f"INPUT {state['runtime']['sample_hz']:g} Hz"
            set_var(self.timing, f"{source}  →  PROCESS 100 Hz  /  SCOPE 10 Hz  /  AGE {age} ms")
        if self.notebook.select() == str(self.live):
            self.draw_inputs(state)
            for name in ("pointer_x", "pointer_y", "scroll_y"):
                set_var(self.metrics[name], f"{snap[name]:.3f}")
            set_var(self.metrics["buttons"], f"{snap['left_click']} / {snap['right_click']}")
            set_var(self.counts, f"Left presses {self.sim['left']}  ·  Right presses {self.sim['right']}  ·  Scroll {self.sim['scroll']:.0f} px")
            set_var(self.boost, f"Boost   pointer {diag['pointer_boost']:.2f} / scroll {diag['scroll_boost']:.2f}   ·   Neutral = 0.5")
            button_text = "Pause input stream" if state["streaming"] else "Resume input stream"
            if self.stream_button.cget("text") != button_text:
                self.stream_button.configure(text=button_text)
            set_var(self.scenario, "External input (read only)" if state["runtime"]["source"] == "external"
                    else next(name for name, value in SCENARIOS.items() if value == state["scenario"]))
            if hasattr(self, "cursor"):
                x = self.sim["x"] * self.playground.winfo_width(); y = self.sim["y"] * self.playground.winfo_height()
                x, y = round(x), round(y)
                color = BLUE if snap["right_click"] else AMBER if snap["left_click"] else GREEN
                if self.drawn_preview != (x, y, color):
                    self.playground.coords(self.cursor, x, y, x, y + 25, x + 7, y + 19, x + 12, y + 29, x + 17, y + 27, x + 12, y + 17, x + 22, y + 17)
                    self.playground.itemconfigure(self.cursor, fill=color)
                    self.drawn_preview = (x, y, color)
                shift = round(-max(-25, min(430, self.sim["scroll"])))
                if shift != self.paper_shift:
                    self.playground.move("paper", 0, shift - self.paper_shift); self.paper_shift = shift
            if self.refresh_count % 2 == 0:
                rows = self.frozen if self.frozen is not None else list(self.history)
                for scope in self.scopes:
                    scope.draw(rows)
        elif self.notebook.select() == str(self.inspect_page):
            for widget, data in ((self.raw_text, state["raw"]), (self.output_text, state["message"])):
                widget.configure(state="normal"); widget.delete("1.0", "end")
                widget.insert("1.0", json.dumps(data, indent=2)); widget.configure(state="disabled")
        self.root.after(50, self.refresh)

    def close(self):
        self.closed = True
        self.lab.close()
        self.root.destroy()


def run(settings=None):
    lab = Lab()
    if settings:
        lab.settings(settings if "config" in settings else {"config": settings})
    root = tk.Tk()
    app = DesktopLab(root, lab)
    print("Native Mouse Signal Lab opened. No browser, network server, or OS mouse events.", flush=True)
    try:
        root.mainloop()
    finally:
        if not app.closed:
            app.close()
