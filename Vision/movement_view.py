"""Native movement guidance and raw/normalized position diagnostics."""

import tkinter as tk
from tkinter import ttk
from .eye_view import CalibrationSounds
from .eye_scope import scope_samples
from LabUI.traces import darker, trace_runs


def draw_raw_scopes(canvas, state):
    """Read only the workbench capture history, shared by every detector view."""
    canvas.delete("all")
    width, height = max(320, canvas.winfo_width()), max(160, canvas.winfo_height())
    pitch = state["config"]["head_mode"] == "pitch"
    specs = (
        (
            "Raw lid gap / eye width",
            (("left_raw", "Left", "#6ed7fe"), ("right_raw", "Right", "#ffa663")),
            0,
            0.5,
        ),
        (
            "Raw head pitch · degrees"
            if pitch
            else "Raw head Y · image-height fraction",
            (("head_raw", "Head", "#b18bff"),),
            -45 if pitch else 0,
            45 if pitch else 1,
        ),
        (
            "Raw tongue centroid · mouth fraction",
            (
                ("tongue_candidate_x", "X", "#75e3a8"),
                ("tongue_candidate_y", "Y", "#f2d66f"),
            ),
            0,
            1,
        ),
    )
    rows = state["trace"]
    start = (rows[-1]["timestamp_ms"] if rows else 0) - 8000
    for index, (title, series, low, high) in enumerate(specs):
        x = index * width / 3
        size = width / 3
        canvas.create_text(
            x + 8,
            5,
            text=title,
            fill="white",
            anchor="nw",
            width=size - 16,
            font=("Arial", 10),
        )
        canvas.create_text(
            x + 8,
            37,
            text=f"{low:g}–{high:g}",
            fill="#adbbcc",
            anchor="nw",
            font=("Arial", 9),
        )
        for i, (key, label, color) in enumerate(series):
            canvas.create_text(
                x + 70 + i * 65,
                37,
                text=label,
                fill=color,
                anchor="nw",
                font=("Arial", 9),
            )
            for unknown, segment in trace_runs(
                scope_samples(rows, key, state["scope_subject"], state["generation"]),
                max_gap=state["config"]["stale_ms"],
                start=start,
            ):
                points = []
                for timestamp, value in segment:
                    points.extend(
                        (
                            x + 8 + (timestamp - start) / 8000 * (size - 16),
                            height
                            - 25
                            - (max(low, min(high, value)) - low)
                            / (high - low)
                            * (height - 83),
                        )
                    )
                canvas.create_line(
                    *points, fill=darker(color) if unknown else color, width=2
                )
        canvas.create_line(
            x + 8, height - 25, x + size - 8, height - 25, fill="#354555"
        )
    canvas.create_text(
        width - 8,
        height - 3,
        text="Captured samples · last 8 s · dark = unknown hold · tongue needs appearance training",
        fill="#adbbcc",
        anchor="se",
        font=("Arial", 9),
    )


def display_point(state, keys):
    """Last known position is display-only; never fill the returned SignalFrame."""
    frame = state["frame"] or {}
    context = (frame.get("session_id"), state["scope_subject"], state["generation"])
    for row in reversed(state["trace"]):
        if (
            row.get("session_id"),
            row.get("subject_id"),
            row.get("calibration_generation"),
        ) != context:
            continue
        if all(
            row.get(key) is not None
            and row.get(key + "_valid", True)
            and (not key.endswith("_raw") or row.get(key[:-4] + "_quality", 0) > 0)
            for key in keys
        ):
            current = bool(
                state["selected"] and row["sequence"] == frame.get("sequence")
            )
            if current and keys[0] in ("head_y", "tongue_x"):
                signals = next(
                    (
                        face["signals"]
                        for face in frame.get("faces", [])
                        if face["subject_id"] == state["selected"]
                    ),
                    {},
                )
                current = all(signals.get(key, {}).get("valid", False) for key in keys)
            return tuple(row[key] for key in keys), current
    return None, False


def draw_calibrated_scope(canvas, state):
    canvas.delete("all")
    width, height = max(320, canvas.winfo_width()), max(160, canvas.winfo_height())
    rows = state["trace"]
    start = (rows[-1]["timestamp_ms"] if rows else 0) - 8000
    canvas.create_text(
        8,
        5,
        text="Calibrated positions · 0–1 · center .5 · no device mapping",
        fill="white",
        anchor="nw",
        font=("Arial", 10),
    )
    for index, (key, title, color) in enumerate(
        (
            ("head_y", "Head Y", "#b18bff"),
            ("tongue_x", "Tongue X", "#75e3a8"),
            ("tongue_y", "Tongue Y", "#f2d66f"),
        )
    ):
        canvas.create_text(
            8 + index * width / 3,
            26,
            text=title,
            fill=color,
            anchor="nw",
            font=("Arial", 10),
        )
        for unknown, segment in trace_runs(
            scope_samples(rows, key, state["scope_subject"], state["generation"]),
            max_gap=state["config"]["stale_ms"],
            start=start,
        ):
            points = []
            for timestamp, value in segment:
                points.extend(
                    (
                        8 + (timestamp - start) / 8000 * (width - 16),
                        height - 22 - value * (height - 78),
                    )
                )
            canvas.create_line(
                *points, fill=darker(color) if unknown else color, width=2
            )
    canvas.create_text(
        width - 8,
        height - 3,
        text="Last 8 s · dark = unavailable, previous position held for display",
        fill="#adbbcc",
        anchor="se",
        font=("Arial", 9),
    )


def draw_position(canvas, state, kind):
    canvas.delete("all")
    w, h = max(360, canvas.winfo_width()), max(160, canvas.winfo_height())
    frame = state["frame"] or {}
    pitch = state["config"]["head_mode"] == "pitch"
    guide = state.get("movement_guide")
    target = (
        guide["target"] if guide and guide["active"] and guide["kind"] == kind else None
    )
    if kind == "head":
        raw, raw_known = display_point(state, ("head_raw",))
        normalized, known = display_point(state, ("head_y",))
        for i, (title, point, valid, color) in enumerate(
            (
                (
                    "Raw pitch · degrees" if pitch else "Raw head · image fraction",
                    raw,
                    raw_known,
                    "#b18bff",
                ),
                (
                    "Personal head Y · up 0 / neutral .5 / down 1",
                    normalized,
                    known,
                    "#75e3a8",
                ),
            )
        ):
            x = 15 + i * w / 2
            size = w / 2 - 30
            canvas.create_text(
                x,
                5,
                text=title,
                fill="white",
                anchor="nw",
                width=size,
                font=("Arial", 10),
            )
            canvas.create_line(
                x + size / 2, 50, x + size / 2, h - 32, fill="#455565", width=5
            )
            canvas.create_line(
                x + size / 2 - 10,
                (h + 18) / 2,
                x + size / 2 + 10,
                (h + 18) / 2,
                fill="#aab8c8",
            )
            for fraction, label in (
                (0, "−45°" if i == 0 and pitch else "0"),
                (0.5, "0°" if i == 0 and pitch else ".5"),
                (1, "45°" if i == 0 and pitch else "1"),
            ):
                canvas.create_text(
                    x + size / 2 + 15,
                    50 + fraction * (h - 82),
                    text=label,
                    fill="#adbbcc",
                    anchor="w",
                    font=("Arial", 9),
                )
            if point:
                value = (point[0] + 45) / 90 if i == 0 and pitch else point[0]
                y = 50 + max(0, min(1, value)) * (h - 82)
                canvas.create_oval(
                    x + size / 2 - 7,
                    y - 7,
                    x + size / 2 + 7,
                    y + 7,
                    fill=color if valid else darker(color),
                    outline="",
                )
                canvas.create_text(
                    x + 5,
                    h - 20,
                    text=f"{point[0]:.3f}" + (" · unknown hold" if not valid else ""),
                    fill=color,
                    anchor="w",
                )
            if i == 1 and target is not None:
                y = 50 + target[0] * (h - 82)
                canvas.create_line(x, y, x + size, y, fill="#ffa663", dash=(4, 3))
    else:
        for index, (keys, title, color) in enumerate(
            (
                (
                    ("tongue_candidate_x", "tongue_candidate_y"),
                    "Raw centroid · mouth coordinates",
                    "#75e3a8",
                ),
                (
                    ("tongue_x", "tongue_y"),
                    "Personal position · center (.5, .5)",
                    "#6ed7fe",
                ),
            )
        ):
            x0 = 15 + index * w / 2
            x1 = (index + 1) * w / 2 - 15
            y0 = 40
            y1 = h - 30
            canvas.create_text(
                x0,
                5,
                text=title,
                fill="white",
                anchor="nw",
                width=x1 - x0,
                font=("Arial", 10),
            )
            canvas.create_rectangle(x0, y0, x1, y1, outline="#455565")
            canvas.create_line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, fill="#354555")
            canvas.create_line(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2, fill="#354555")
            canvas.create_text(
                x0 + 3,
                y0 + 3,
                text="0,0 · left/up",
                fill="#adbbcc",
                anchor="nw",
                font=("Arial", 8),
            )
            canvas.create_text(
                x1 - 3,
                y1 - 3,
                text="1,1 · right/down",
                fill="#adbbcc",
                anchor="se",
                font=("Arial", 8),
            )
            bounds = state.get("tongue_range")
            if index == 0 and bounds:
                canvas.create_rectangle(
                    x0 + bounds["x"]["low"] * (x1 - x0),
                    y0 + bounds["y"]["low"] * (y1 - y0),
                    x0 + bounds["x"]["high"] * (x1 - x0),
                    y0 + bounds["y"]["high"] * (y1 - y0),
                    outline="#b18bff",
                    dash=(4, 3),
                )
            point, known = display_point(state, keys)
            if point:
                x = x0 + point[0] * (x1 - x0)
                y = y0 + point[1] * (y1 - y0)
                canvas.create_oval(
                    x - 6,
                    y - 6,
                    x + 6,
                    y + 6,
                    fill=color if known else darker(color),
                    outline="",
                )
                canvas.create_text(
                    x0,
                    h - 17,
                    text=f"({point[0]:.3f}, {point[1]:.3f})"
                    + (" unknown" if not known else ""),
                    fill=color,
                    anchor="w",
                )
            if index == 1 and target is not None:
                x = x0 + target[0] * (x1 - x0)
                y = y0 + target[1] * (y1 - y0)
                canvas.create_oval(
                    x - 9, y - 9, x + 9, y + 9, outline="#ffa663", width=2
                )
    canvas.create_text(
        w - 8,
        h - 2,
        text=f"Capture #{frame.get('sequence', '—')} · orange = requested target · plot holds never drive output",
        fill="#adbbcc",
        anchor="se",
        font=("Arial", 9),
    )


class MovementPanel:
    def __init__(self, parent, root, call, kind):
        self.root, self.call, self.kind = root, call, kind
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x")
        self.title = tk.StringVar(value=f"{kind.title()} position guide")
        self.instruction = tk.StringVar()
        self.progress = tk.StringVar()
        self.sounds = CalibrationSounds(root)
        self.event = None
        self.pending = None
        ttk.Label(
            self.frame,
            textvariable=self.title,
            font=("Arial", 15, "bold"),
            wraplength=440,
        ).pack(anchor="w", pady=5)
        ttk.Label(
            self.frame, textvariable=self.instruction, wraplength=440, justify="left"
        ).pack(anchor="w")
        ttk.Label(
            self.frame, textvariable=self.progress, wraplength=440, justify="left"
        ).pack(anchor="w", pady=5)
        row = ttk.Frame(self.frame)
        row.pack(fill="x", pady=5)
        self.start = ttk.Button(
            row,
            text=f"Start {kind} position guide",
            command=lambda: call("start_movement_guide", kind),
        )
        self.start.pack(side="left")
        ttk.Button(row, text="Cancel", command=lambda: call("cancel")).pack(
            side="left", padx=5
        )
        if kind == "tongue":
            self.recheck = ttk.Button(
                self.frame,
                text="Recheck saved tongue range",
                command=lambda: call("start_movement_guide", "tongue", True),
            )
            self.recheck.pack(fill="x", pady=3)

    def update(self, state):
        guide = state.get("movement_guide")
        self.start.configure(
            state="disabled"
            if state["calibrating"] or self.kind == "tongue" and not state["tongue_fit"]
            else "normal"
        )
        if self.kind == "tongue":
            self.recheck.configure(
                state="normal"
                if state.get("tongue_range") and not state["calibrating"]
                else "disabled"
            )
        if not guide or guide["kind"] != self.kind:
            self.title.set(self.kind.title() + " position guide")
            self.instruction.set(
                "Neutral → up → down, followed by new checks."
                if self.kind == "head"
                else "Train appearance below, then follow center/left/right/up/down targets. Later checks use new captures."
            )
            self.progress.set(
                "Capture tones = hold the pose; low tones = rest. No device transfer functions are applied here."
            )
            self.event = None
            return
        event = (state["generation"], guide["index"], guide["phase"], guide["active"])
        if event != self.event:
            self.event = event
            cue = (
                ("success" if guide["passed"] else "retry")
                if not guide["active"]
                else {"rest": "rest", "prepare": "resume", "capture": "capture"}[
                    guide["phase"]
                ]
            )
            self.sounds.play(cue)
        self.title.set(
            f"{self.kind.title()} · {guide['index'] + 1}/{guide['total']} · {guide['role'].title()}"
        )
        self.instruction.set(
            guide["instruction"] if guide["active"] else guide["report"]
        )
        self.progress.set(
            f"{guide['phase'].upper()} · {guide['remaining_ms'] / 1000:.1f}s · {guide['samples']} usable / {guide['rejected']} unavailable"
            if guide["active"]
            else "Raw and calibrated positions appear beside the camera. Output remains stopped."
        )
        if guide["active"] and guide["waiting"] and self.pending is None:
            self.pending = self.root.after_idle(lambda: self.present(event))

    def present(self, event):
        self.pending = None
        if event == self.event and self.frame.winfo_ismapped():
            self.call("present_movement_step", event[1], event[2], event[0])

    def close(self):
        if self.pending is not None:
            self.root.after_cancel(self.pending)
        self.sounds.close()
