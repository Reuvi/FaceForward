"""Native measurement, labeled-trial, mapping and gaze experiment view."""

import json
import tkinter as tk
from tkinter import ttk, filedialog
from math import isfinite

from Processing.mouse.desktop import Scope, BLUE, AMBER, GREEN, BG, TEXT, MUTED
from Processing.research.settings import DEFAULTS, SOURCES
from .research_runtime import LABELS

GRAPHS = {
    "Eyes / timing": [
        (
            "Left: closure / calibrated blink / squint",
            ("left_closure", "left_blink_normalized", "eyeSquintLeft"),
            (0, 1),
        ),
        (
            "Right: closure / calibrated blink / squint",
            ("right_closure", "right_blink_normalized", "eyeSquintRight"),
            (0, 1),
        ),
        (
            "Closure elapsed: left / right (ms)",
            ("left_elapsed_ms", "right_elapsed_ms"),
            (0, 1600),
        ),
        (
            "Peak closing speed: left / right (units/s)",
            ("left_close_speed", "right_close_speed"),
            (0, 40),
        ),
        (
            "Peak reopening speed: left / right (units/s)",
            ("left_open_speed", "right_open_speed"),
            (0, 40),
        ),
        (
            "Qualified left / right; left image quality",
            ("left_qualified", "right_qualified", "left_quality"),
            (0, 1),
        ),
    ],
    "Face / supporting features": [
        ("Cheek squint: left / right", ("cheekSquintLeft", "cheekSquintRight"), (0, 1)),
        (
            "Brow down L / R; inner brow up",
            ("browDownLeft", "browDownRight", "browInnerUp"),
            (0, 1),
        ),
        (
            "Smile: left / right; jaw open",
            ("mouthSmileLeft", "mouthSmileRight", "jawOpen"),
            (0, 1),
        ),
        (
            "Brow distance / eye width: left / right",
            ("left_brow_gap", "right_brow_gap"),
            (0, 3),
        ),
        (
            "Cheek distance / eye width: left / right",
            ("left_cheek_gap", "right_cheek_gap"),
            (0, 3),
        ),
        (
            "Raw blink: left / right; left image quality",
            ("eyeBlinkLeft", "eyeBlinkRight", "left_quality"),
            (0, 1),
        ),
    ],
    "Head / motion quality": [
        ("Yaw / pitch / roll (radians)", ("yaw", "pitch", "roll"), (-1, 1)),
        ("Face center X / Y (image fraction)", ("face_x", "face_y"), (0, 1)),
        ("Log face width / image width", ("face_scale",), (-3, 0)),
        ("Angular speed (rad/s)", ("pose_speed",), (0, 5)),
        (
            "Image quality L / R; bilateral overlap",
            ("left_quality", "right_quality", "eye_overlap"),
            (0, 1),
        ),
        ("Raw eyelid ratio: left / right", ("left_ratio", "right_ratio"), (0, 0.4)),
    ],
    "Gaze / pointer": [
        (
            "Left iris X / Y (eye width units)",
            ("left_iris_x", "left_iris_y"),
            (-0.3, 1),
        ),
        (
            "Right iris X / Y (eye width units)",
            ("right_iris_x", "right_iris_y"),
            (-0.3, 1),
        ),
        ("Predicted viewport X / Y", ("gaze_estimate_x", "gaze_estimate_y"), (0, 1)),
        ("Preview pointer X / Y", ("pointer_x", "pointer_y"), (0, 1)),
        ("Head yaw / pitch (radians)", ("yaw", "pitch"), (-0.8, 0.8)),
        ("Closure left / right", ("left_closure", "right_closure"), (0, 1)),
    ],
}
COLORS = {
    "natural_blink": BLUE,
    "left_wink": GREEN,
    "right_wink": GREEN,
    "both_intentional": GREEN,
    "bilateral_natural": AMBER,
    "long_closure": "#ef8686",
}


class ResearchView:
    def __init__(self, parent, root, session, guard):
        self.root = root
        self.session = session
        self.core = session.research
        self.parent = parent
        self.guard = lambda fn: guard(
            fn if fn == self.export else lambda: self.locked(fn)
        )
        from Vision.eye_view import CalibrationSounds

        self.sounds = CalibrationSounds(root)
        self.sound_target = None
        self.config_seen = None
        self.popup = None
        self.pending = None
        self.presented = None
        self.closed = False
        self.graph_name = None
        self.last_event = 0
        self.vars = {}
        self.status = tk.StringVar()
        self.summary = tk.StringVar()
        self.preview_status = tk.StringVar()
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", padx=8, pady=5)
        for text, command in (
            ("Start research preview", self.arm),
            ("Stop", self.stop),
            ("Export scalar data", self.export),
        ):
            ttk.Button(
                toolbar, text=text, command=lambda f=command: self.guard(f)
            ).pack(side="left", padx=4)
        ttk.Label(
            toolbar, text="EXPERIMENTAL • same camera/profile • no OS output"
        ).pack(side="right")
        ttk.Label(parent, textvariable=self.status, wraplength=1250).pack(
            anchor="w", padx=12, pady=4
        )
        tabs = ttk.Notebook(parent)
        tabs.pack(fill="both", expand=True, padx=8, pady=4)
        self.tabs = tabs
        self.measurements = ttk.Frame(tabs, padding=8)
        tabs.add(self.measurements, text="Measurements & preview")
        row = ttk.Frame(self.measurements)
        row.pack(fill="x")
        self.graph = tk.StringVar(value="Eyes / timing")
        ttk.Combobox(
            row,
            textvariable=self.graph,
            values=list(GRAPHS),
            state="readonly",
            width=30,
        ).pack(side="left")
        ttk.Label(
            row,
            text="Channel order: cyan / amber / green · dark = unknown hold · measurements remain invalid",
        ).pack(side="left", padx=10)
        charts = ttk.Frame(self.measurements)
        charts.pack(fill="x", pady=6)
        self.scopes = []
        for i in range(6):
            charts.columnconfigure(i % 3, weight=1, uniform="research")
            scope = Scope(charts, "", ("empty",))
            scope.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            self.scopes.append(scope)
        self.preview = tk.Canvas(
            self.measurements,
            height=190,
            background=BG,
            highlightthickness=1,
            highlightbackground="#334950",
        )
        self.preview.pack(fill="both", expand=True, pady=6)
        ttk.Label(self.measurements, textvariable=self.preview_status).pack(anchor="w")
        trial_tab = ttk.Frame(tabs, padding=8)
        tabs.add(trial_tab, text="Trials & evidence")
        controls = ttk.Frame(trial_tab)
        controls.pack(fill="x")
        self.label = tk.StringVar(value="natural_blink")
        self.role = tk.StringVar(value="train")
        self.expected = tk.StringVar(value="1")
        for text, var, options, width in (
            ("Label", self.label, LABELS, 20),
            ("Dataset", self.role, ("train", "validation"), 12),
        ):
            ttk.Label(controls, text=text).pack(side="left", padx=4)
            ttk.Combobox(
                controls,
                textvariable=var,
                values=options,
                state="readonly",
                width=width,
            ).pack(side="left")
        ttk.Label(controls, text="Intended repetitions").pack(side="left", padx=5)
        ttk.Entry(controls, textvariable=self.expected, width=4).pack(side="left")
        for text, command in (
            ("Record trial", self.begin),
            ("Finish trial", self.core.end_trial),
            ("Suggest duration", self.suggest),
            ("Compare 3 models", lambda: self.core.submit("events")),
        ):
            ttk.Button(
                controls, text=text, command=lambda f=command: self.guard(f)
            ).pack(side="left", padx=3)
        ttk.Label(
            trial_tab,
            text="Natural blinks: read normally. Record intentional gestures comfortably. Use separate validation trials; include talking, smiling and long closures.",
            wraplength=1200,
        ).pack(anchor="w", pady=5)
        ttk.Label(trial_tab, textvariable=self.summary, wraplength=1200).pack(
            anchor="w", pady=4
        )
        self.hist = tk.Canvas(trial_tab, height=180, bg=BG, highlightthickness=0)
        self.hist.pack(fill="x")
        scatter_controls = ttk.Frame(trial_tab)
        scatter_controls.pack(fill="x")
        ttk.Label(scatter_controls, text="Duration versus").pack(side="left")
        self.scatter_key = tk.StringVar(value="cheek")
        ttk.Combobox(
            scatter_controls,
            textvariable=self.scatter_key,
            values=(
                "peak",
                "close_speed",
                "open_speed",
                "blink",
                "squint",
                "cheek",
                "brow",
                "brow_gap",
                "pose_speed",
                "sync_lag_ms",
                "overlap_ms",
            ),
            state="readonly",
            width=18,
        ).pack(side="left", padx=6)
        ttk.Label(
            scatter_controls,
            text="Blue: natural blink • green: intended • amber: bilateral natural • red: prolonged",
        ).pack(side="left", padx=10)
        self.scatter = tk.Canvas(trial_tab, height=130, bg=BG, highlightthickness=0)
        self.scatter.pack(fill="x")
        columns = ("eye", "label", "ms", "close/s", "open/s", "peak", "result")
        self.table = ttk.Treeview(trial_tab, columns=columns, show="headings", height=6)
        for key in columns:
            self.table.heading(key, text=key)
            self.table.column(key, width=115 if key != "result" else 270)
        self.table.pack(fill="both", expand=True, pady=5)
        self.report = ttk.Label(trial_tab, text="", wraplength=1250, justify="left")
        self.report.pack(anchor="w")
        config_tab = ttk.Frame(tabs, padding=10)
        tabs.add(config_tab, text="Capabilities & settings")
        ttk.Label(
            config_tab,
            text="Choose comfortable inputs; Disabled removes an action. Changes disarm preview. A failed eye does not disable the other.",
            wraplength=1200,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=6)
        choices = dict(
            policy=("independent", "strict"),
            click_mode=("release", "hold"),
            pointer_mode=("tongue", "head", "gaze"),
            model=("rules", "geometry", "blink", "face"),
            left_source=SOURCES,
            right_source=SOURCES,
        )
        for i, (key, value) in enumerate(DEFAULTS.items()):
            r, col = i // 2 + 1, (i % 2) * 2
            ttk.Label(config_tab, text=key).grid(
                row=r, column=col, sticky="w", padx=(8, 12), pady=3
            )
            var = tk.StringVar(value=str(value))
            self.vars[key] = var
            options = ("True", "False") if type(value) is bool else choices.get(key)
            widget = (
                ttk.Combobox(
                    config_tab,
                    textvariable=var,
                    values=options,
                    state="readonly",
                    width=22,
                )
                if options
                else ttk.Entry(config_tab, textvariable=var, width=24)
            )
            widget.grid(row=r, column=col + 1, sticky="ew", padx=(0, 25), pady=3)
        r = (len(DEFAULTS) + 1) // 2 + 2
        for i, (text, command) in enumerate(
            (
                ("Apply settings", self.apply),
                ("Fit expressions / pose", self.core.fit_expressions),
                ("Set head neutral", self.head_neutral),
            )
        ):
            ttk.Button(
                config_tab, text=text, command=lambda f=command: self.guard(f)
            ).grid(row=r, column=i, sticky="w", pady=8)
        ttk.Label(
            config_tab,
            text="Smile/brow: record rest plus smile/brow TRAIN trials, then Fit expressions. Pose gate: record an open_pose TRAIN trial covering comfortable head movement. Validate alternatives during ordinary activity.",
            wraplength=1100,
        ).grid(row=r + 1, column=0, columnspan=4, sticky="w", pady=8)
        self.capabilities = ttk.Label(config_tab, text="", wraplength=1200)
        self.capabilities.grid(row=r + 2, column=0, columnspan=4, sticky="w")
        gaze_tab = ttk.Frame(tabs, padding=12)
        tabs.add(gaze_tab, text="Head-compensated gaze")
        ttk.Label(
            gaze_tab,
            text="A separate screen-point estimator. Calibrate eyes first; then collect known targets with comfortable head turns. Tongue remains the default pointer.",
            wraplength=1200,
        ).pack(anchor="w", pady=8)
        row = ttk.Frame(gaze_tab)
        row.pack(fill="x")
        for text, command in (
            ("Collect gaze targets", lambda: self.start_gaze(False)),
            ("Fit / compare gaze", lambda: self.core.submit("gaze")),
            ("Fresh validation targets", lambda: self.start_gaze(True)),
            ("Evaluate validation", lambda: self.core.submit("gaze_validation")),
        ):
            ttk.Button(row, text=text, command=lambda f=command: self.guard(f)).pack(
                side="left", padx=5
            )
        ttk.Label(
            gaze_tab,
            text="Training: 9 targets × 5 head poses, then a separate validation pass (90 fixations, about 3–4 minutes). Pause for rest; skip unsupported poses. Fresh validation uses 45 fixations. Sparse data restricts the supported pose range.\n\nAfter a good fit, record fresh validation; gaze preview stays disabled until error fits the configured target radius and all validation episodes lie inside the trained range. Switch pointer_mode to gaze and disable scrolling to avoid nod/scroll conflicts.\n\nA wink latches the last fresh target; an accepted click commits there after reopening. Missing gaze never advances dwell. Profiles save coefficients; a loaded gaze profile requires fresh validation.",
            wraplength=1150,
            justify="left",
        ).pack(anchor="w", pady=15)
        self.gaze_report = ttk.Label(gaze_tab, text="", wraplength=1200, justify="left")
        self.gaze_report.pack(anchor="w")
        self.timer = root.after(100, self.tick)

    def locked(self, fn):
        with self.session.lock:
            return fn()

    def stop(self):
        self.core.stop("Stopped")
        self.session.lab.action({"action": "stop"})

    def begin(self):
        self.locked(
            lambda: self.core.begin_trial(
                self.label.get(), self.role.get(), int(self.expected.get())
            )
        )

    def arm(self):
        with self.session.lock:
            if (
                self.session.detector_runtime
                and self.session.detector_runtime.workbench.calibrating
            ):
                raise ValueError("Finish eye/head/tongue collection first")
            self.core.arm()
            self.session.lab.action({"action": "arm"})

    def apply(self):
        self.core.end_trial()
        data = {
            k: (
                self.vars[k].get() == "True"
                if type(v) is bool
                else float(self.vars[k].get())
                if type(v) in (int, float)
                else self.vars[k].get()
            )
            for k, v in DEFAULTS.items()
        }
        if data["gaze_radius_px"] != self.core.processor.config["gaze_radius_px"]:
            self.core.gaze_ready = False
        self.locked(lambda: self.core.processor.configure(data))
        self.core.revision += 1

    def suggest(self):
        data = self.locked(self.core.suggest_duration)
        for key, value in data.items():
            self.vars[key].set(str(value))

    def head_neutral(self):
        if (
            self.core.packet is None
            or self.core.clock() - self.core.packet["timestamp_ms"]
            > self.core.processor.config["stale_ms"]
        ):
            raise ValueError("Select a fresh face")
        for key in ("x", "y"):
            value = self.core.packet["values"].get("face_" + key)
            if value is None:
                raise ValueError("Fresh head position required")
            self.vars["head_center_" + key].set(str(value))

    def export(self):
        directory = filedialog.askdirectory(
            parent=self.root,
            title="Save local scalar research data",
            initialdir="data/private",
        )
        if directory:
            self.status.set(
                "Exported " + str(self.locked(lambda: self.core.export(directory)))
            )

    def start_gaze(self, validation):
        self.locked(
            lambda: self.core.start_gaze(
                (self.root.winfo_screenwidth(), self.root.winfo_screenheight()),
                validation,
            )
        )

    def cancel_gaze(self):
        self.sounds.play("cancel")
        with self.session.lock:
            self.core.fixations = None
            self.core.processor.reset("Gaze calibration cancelled")
            self.core.revision += 1
        self.dismiss()

    def dismiss(self):
        if self.pending:
            self.root.after_cancel(self.pending)
            self.pending = None
        if self.popup:
            self.popup.close()
            self.popup = None
        self.presented = None

    def gaze_action(self, action):
        with self.session.lock:
            run = self.core.fixations
            if not run or not run.active:
                return
            if action == "pause":
                run.paused = not run.paused
                run.start = None
                run.samples = []
                run.total_samples = 0
            elif action == "skip":
                run.advance()
            elif action == "retry":
                if run.index > 0:
                    run.index -= 1
                    run.episodes = [e for e in run.episodes if e["index"] < run.index]
                run.start = None
                run.samples = []
                run.total_samples = 0
            self.presented = None
            self.sound_target = None

    def present(self, token, index):
        self.pending = None
        with self.session.lock:
            run = self.core.fixations
            if (
                self.popup
                and self.popup.ready
                and run
                and run.token == token
                and run.index == index
                and not run.paused
            ):
                run.present(index, self.core.clock())
                if self.sound_target != (token, index):
                    self.sounds.play("start" if index == 0 else "target")
                    self.sound_target = (token, index)

    def update_gaze(self, state):
        if not state or not state["active"]:
            if self.popup and state:
                self.sounds.play("success")
            self.dismiss()
            return
        if self.root.state() == "iconic":
            self.cancel_gaze()
            return
        if self.popup is None:
            from Vision.eye_view import FullscreenEyeGuide

            self.popup = FullscreenEyeGuide(self.root, self.cancel_gaze)
            self.popup.cancel_button.place(relx=0.86, rely=1, y=-20, anchor="s")
            for x, label, action in (
                (0.18, "Pause / resume", "pause"),
                (0.40, "Retry previous", "retry"),
                (0.62, "Skip target", "skip"),
            ):
                ttk.Button(
                    self.popup.window,
                    text=label,
                    command=lambda a=action: self.gaze_action(a),
                ).place(relx=x, rely=1, y=-20, anchor="s")
        canvas = self.popup.canvas
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        canvas.create_text(
            w / 2,
            35,
            text=f"Gaze target {state['index'] + 1}/{state['total']} · {state['role'].upper()}",
            fill=TEXT,
            font=("Arial", 22, "bold"),
        )
        canvas.create_text(
            w / 2,
            80,
            text=f"Head: {state['pose'].upper()} (comfortable range) · keep looking at the dot",
            fill=TEXT,
            font=("Arial", 16),
            width=w - 80,
        )
        x, y = state["target"]
        x *= w
        y *= h
        canvas.create_oval(
            x - 16, y - 16, x + 16, y + 16, fill=BLUE, outline="white", width=2
        )
        canvas.create_text(
            w / 2,
            h - 82,
            text="PAUSED — resume when ready"
            if state["paused"]
            else f"{state['remaining_ms'] / 1000:.1f}s · usable samples {state['samples']} · {state['notice']}",
            fill=TEXT,
            font=("Arial", 12),
            width=w - 80,
        )
        if (
            state["waiting"]
            and not state["paused"]
            and self.popup.ready
            and self.pending is None
        ):
            self.pending = self.root.after_idle(
                lambda: self.present(state["token"], state["index"])
            )

    def draw_evidence(self, events, trials):
        eyes = [
            e
            for e in events
            if e["channel"] in ("left", "right") and e["label"] != "unlabeled"
        ]
        self.hist.delete("all")
        w = max(300, self.hist.winfo_width())
        maximum = max(1000, max((e["duration_ms"] for e in eyes), default=1000))
        maximum = min(10000, maximum * 1.1)
        for i, side in enumerate(("left", "right")):
            x0 = i * w / 2 + 45
            span = w / 2 - 70
            bins = {}
            for e in eyes:
                if e["channel"] == side:
                    b = min(19, int(e["duration_ms"] / maximum * 20))
                    key = (b, COLORS.get(e["label"], MUTED))
                    bins[key] = bins.get(key, 0) + 1
            max_count = (
                max(
                    (
                        sum(v for (b, c), v in bins.items() if b == index)
                        for index in range(20)
                    ),
                    default=1,
                )
                or 1
            )
            for b in range(20):
                top = 145
                for color in dict.fromkeys([*COLORS.values(), MUTED]):
                    count = bins.get((b, color), 0)
                    height = count / max_count * 100
                    if height:
                        self.hist.create_rectangle(
                            x0 + b / 20 * span,
                            top - height,
                            x0 + (b + 1) / 20 * span - 2,
                            top,
                            fill=color,
                            outline="",
                        )
                    top -= height
            self.hist.create_text(
                x0,
                14,
                text=side.upper() + " completed closure durations",
                fill=TEXT,
                anchor="w",
            )
            for f in (0, 0.5, 1):
                self.hist.create_text(
                    x0 + f * span, 163, text=f"{maximum * f:.0f} ms", fill=MUTED
                )
        canvas = self.scatter
        canvas.delete("all")
        w = max(300, canvas.winfo_width())
        key = self.scatter_key.get()
        points = [
            e for e in eyes if type(e.get(key)) in (int, float) and isfinite(e[key])
        ]
        ymax = max(0.01, max((e[key] for e in points), default=1))
        canvas.create_text(
            8,
            8,
            text=f"{key}: 0 → {ymax:.2f}  |  X: duration 0 → {maximum:.0f} ms",
            fill=MUTED,
            anchor="nw",
        )
        for e in points:
            x = 30 + e["duration_ms"] / maximum * (w - 60)
            y = 112 - e[key] / ymax * 80
            canvas.create_oval(
                x - 3,
                y - 3,
                x + 3,
                y + 3,
                fill=COLORS.get(e["label"], MUTED),
                outline="",
            )
        positives = [
            t
            for t in trials
            if not t.get("aborted")
            and t["label"] in ("left_wink", "right_wink", "both_intentional")
        ]
        negatives = [
            t
            for t in trials
            if not t.get("aborted")
            and t["label"]
            in (
                "natural_blink",
                "bilateral_natural",
                "long_closure",
                "talking",
                "smiling",
                "tongue",
                "looking_down",
                "rest",
            )
        ]
        minutes = sum(t["duration_ms"] for t in negatives) / 60000
        false = sum(t["left_actions"] + t["right_actions"] for t in negatives)
        requested = sum(
            t["expected"] * (2 if t["label"] == "both_intentional" else 1)
            for t in positives
        )
        accepted = sum(
            t["left_actions"]
            if t["label"] == "left_wink"
            else t["right_actions"]
            if t["label"] == "right_wink"
            else t["left_actions"] + t["right_actions"]
            for t in positives
        )
        wrong = sum(
            t["right_actions"]
            if t["label"] == "left_wink"
            else t["left_actions"]
            if t["label"] == "right_wink"
            else 0
            for t in positives
        )
        invalid = sum(t["invalid"] for t in trials)
        frames = sum(t["frames"] for t in trials)
        latency = [e["latency_ms"] for e in eyes if e["accepted"]]
        latency_text = (
            f" · decision latency median {sorted(latency)[len(latency) // 2]:.0f} ms"
            if latency
            else ""
        )
        self.summary.set(
            f"Invalid eye frames {invalid}/{frames}"
            + latency_text
            + f"\nAll recorded trials: {len(trials)} · requested {requested} intended actions / {accepted} matching decisions · wrong side {wrong}\nNegative activity: {false} decisions / {minutes:.2f} min"
            + (f" = {false / minutes:.2f}/min" if minutes else "")
            + " · short rejected closures still appear below. Counts are not proof of live accuracy."
        )
        newest = events[-1]["id"] if events else 0
        if newest != self.last_event:
            self.last_event = newest
            self.table.delete(*self.table.get_children())
            for e in events[-60:][::-1]:
                self.table.insert(
                    "",
                    "end",
                    values=(
                        e["channel"],
                        e["label"],
                        f"{e['duration_ms']:.0f}",
                        f"{e['close_speed']:.1f}",
                        f"{e['open_speed']:.1f}",
                        f"{e['peak']:.2f}",
                        e["reason"],
                    ),
                )

    def tick(self):
        if self.closed:
            return
        with self.session.lock:
            self.core.poll()
            p = self.core.processor
            if self.core.gaze_ready and tuple(self.core.gaze["viewport"]) != (
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            ):
                self.core.gaze_ready = False
                p.reset("Screen size changed; recalibrate gaze")
            # Profile/source replacement is the only automatic form reset.
            if self.config_seen is not p:
                self.config_seen = p
                for key, value in p.config.items():
                    self.vars[key].set(str(value))
            fix = (
                self.core.fixations.state(self.core.clock())
                if self.core.fixations
                else None
            )
            if not self.parent.winfo_ismapped():
                self.update_gaze(fix)
                self.timer = self.root.after(100, self.tick)
                return
            rows = list(p.trace)[-1200:]
            if (
                rows
                and self.core.clock() / 1000 - rows[-1]["t"]
                > p.config["stale_ms"] / 1000
            ):
                rows.append({"t": self.core.clock() / 1000, "scope_context": p.context})
            events = list(p.events)
            trials = list(self.core.trials)
            report = self.core.report
            output = dict(p.output)
            delivered = p.eye_sample
            cursor = list(p.cursor)
            count = p.click_id
            trial = p.trial
            states = " | ".join(
                f"{side}: {p.gates[side].phase}" for side in ("left", "right")
            )
            fix = (
                self.core.fixations.state(self.core.clock())
                if self.core.fixations
                else None
            )
            fits = list(p.fits)
            pose = dict(p.pose_bounds)
            gaze = self.core.gaze
            ready = self.core.gaze_ready
            reason = p.reason
        self.status.set(
            ("RECORDING " + trial["label"] + " · " if trial else "")
            + states
            + " · "
            + reason
        )
        specs = GRAPHS[self.graph.get()]
        if self.graph_name != self.graph.get():
            self.graph_name = self.graph.get()
            for scope, (title, keys, limits) in zip(self.scopes, specs):
                scope.keys = keys
                scope.limits = limits
                scope.size = None
                scope.winfo_children()[0].configure(text=title)
        for scope in self.scopes:
            scope.draw(rows)
        self.draw_evidence(events, trials)
        self.report.configure(text=report)
        self.capabilities.configure(
            text="Calibrated scalar inputs: "
            + (", ".join(fits) or "none; rerun eye guide for blink coefficients")
            + "\nSupported pose limits (radians/log scale): "
            + str(pose)
        )
        self.gaze_report.configure(
            text=report
            + "\n\nCurrent gaze model: "
            + (json.dumps(gaze["report"], indent=2) if gaze else "none")
            + f"\nFresh validation: {ready}"
        )
        canvas = self.preview
        canvas.delete("all")
        w, h = max(100, canvas.winfo_width()), max(80, canvas.winfo_height())
        canvas.create_text(
            12,
            12,
            text="Research preview · " + output.get("pointer_mode", "tongue"),
            fill=MUTED,
            anchor="nw",
        )
        x, y = cursor
        canvas.create_oval(
            x * w - 7,
            y * h - 7,
            x * w + 7,
            y * h + 7,
            fill=GREEN if output.get("enabled") else MUTED,
            outline="",
        )
        canvas.create_text(
            w - 12,
            12,
            text=f"Ordered clicks: {count} · dwell {output.get('dwell', 0):.0%}",
            fill=TEXT,
            anchor="ne",
        )
        eye_text = "Waiting for captured eye samples"
        if delivered:
            eye_text = (
                f"Last capture {delivered['sequence']} eye inputs: "
                + " / ".join(
                    f"{side} {delivered[side]['value']:.2f} ({'known' if delivered[side]['known'] else 'unknown / held'})"
                    for side in ("left", "right")
                )
            )
        self.preview_status.set(
            eye_text
            + "\n"
            + f"{output.get('format')} · enabled {output.get('enabled')} · buttons {output.get('buttons')} · scroll {output.get('scroll', 0.5):.3f}"
        )
        self.update_gaze(fix)
        self.timer = self.root.after(100, self.tick)

    def close(self):
        self.closed = True
        self.sounds.close()
        if self.timer:
            self.root.after_cancel(self.timer)
        self.dismiss()
