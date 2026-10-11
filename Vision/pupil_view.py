"""Personal pupil calibration, a temporary native guide and square matrix."""

import tkinter as tk
from tkinter import ttk

from .pupil import MATRIX_SIZE, matrix_cell
from .eye_view import CalibrationSounds, FullscreenEyeGuide
from LabUI.traces import darker


def draw_matrix(canvas, state):
    from .movement_view import display_point

    canvas.delete("all")
    width, height = max(200, canvas.winfo_width()), max(200, canvas.winfo_height())
    extent = min(width - 32, height - 68)
    x0, y0 = (width - extent) / 2, 30
    cell_size = extent / MATRIX_SIZE
    color = "#6ed7fe"
    canvas.create_text(width / 2, 10, text="Pupil matrix · 11 × 11", fill="white")
    point, known = display_point(state, ("gaze_x", "gaze_y"))
    cell = matrix_cell(point)
    if cell is not None:
        row, column = cell
        x, y = x0 + column * cell_size, y0 + row * cell_size
        canvas.create_rectangle(
            x,
            y,
            x + cell_size,
            y + cell_size,
            fill=color if known else darker(color),
            outline="",
            tags="pupil-cell",
        )
    for index in range(MATRIX_SIZE + 1):
        p = index * cell_size
        canvas.create_line(
            x0 + p, y0, x0 + p, y0 + extent, fill="#455565", tags="matrix-grid"
        )
        canvas.create_line(
            x0, y0 + p, x0 + extent, y0 + p, fill="#455565", tags="matrix-grid"
        )
    if point is not None:
        # Continuous dot over the quantized cell grid, with the endpoints centered
        # in the first/last cells. Drawing cannot create a control measurement.
        x = x0 + (0.5 + point[0] * (MATRIX_SIZE - 1)) * cell_size
        y = y0 + (0.5 + point[1] * (MATRIX_SIZE - 1)) * cell_size
        canvas.create_oval(
            x - 3,
            y - 3,
            x + 3,
            y + 3,
            fill="white" if known else "#596675",
            outline="",
            tags="pupil-point",
        )
    canvas.create_text(
        width / 2,
        y0 + extent + 15,
        text=(
            f"row {cell[0]}, column {cell[1]}"
            + (" · UNKNOWN display hold" if not known else "")
            if cell
            else "Waiting for both pupils"
        ),
        fill=color if known else "#adbbcc",
    )
    canvas.create_text(
        width / 2,
        height - 7,
        text="Up = row 0 · your left = column 0 · center = (5, 5)",
        fill="#adbbcc",
        font=("Arial", 9),
    )


class PupilPanel:
    def __init__(self, parent, root, call):
        self.root, self.call = root, call
        self.sounds = CalibrationSounds(root)
        self.event = self.fullscreen = self.pending_present = None
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=8)
        self.message = tk.StringVar(
            value="Calibrate comfortable eye directions with head compensation"
        )
        ttk.Label(self.frame, textvariable=self.message, wraplength=420).pack(
            anchor="w"
        )
        ttk.Label(
            self.frame,
            text="One highlighted cell marks the direction. The small dot shows the precise X/Y value. Dark cells hold the last visible position only; unknown input stays unavailable.",
            wraplength=420,
        ).pack(anchor="w", pady=5)
        self.start = ttk.Button(self.frame, text="Start / restart pupil guide", command=lambda: call("start_pupil_guide"))
        self.start.pack(fill="x", pady=3)
        self.retry = ttk.Button(self.frame, text="Retry failed step", command=lambda: call("retry_pupil_step"))
        self.retry.pack(fill="x", pady=3)
        self.reset = ttk.Button(self.frame, text="Reset pupils only", command=lambda: self.reset_pupils())
        self.reset.pack(fill="x", pady=3)
        self.canvas = tk.Canvas(
            self.frame, height=310, bg="#14202c", highlightthickness=0
        )
        self.canvas.pack(fill="x", pady=5)

    def update(self, state):
        draw_matrix(self.canvas, state)
        guide = state.get("pupil_guide")
        active = bool(guide and guide["active"])
        self.start.configure(state="normal" if not state["calibrating"] or active else "disabled")
        self.reset.configure(state="normal" if not state["calibrating"] or active else "disabled")
        self.retry.configure(state="normal" if guide and not guide["active"] and not guide["passed"] and not state["calibrating"] else "disabled")
        if not active:
            self.dismiss_fullscreen()
            self.message.set(guide["report"] if guide else ("Personal pupil calibration loaded" if state.get("pupil_model") else "Start the guide to define directions. Raw iris data is available before calibration."))
            if guide and self.event and self.event[2]:
                self.sounds.play("success" if guide["passed"] else "retry")
            self.event = None
            return
        event = (state["generation"], guide["index"], guide["active"], guide["phase"])
        self.message.set(guide["instruction"])
        if self.fullscreen is None:
            self.fullscreen = FullscreenEyeGuide(self.root, self.cancel)
            self.fullscreen.window.title("Pupil calibration — Escape to cancel")
        progress = f"{guide['phase'].upper()} · {guide['remaining_ms']/1000:.1f}s · {guide['samples']} clear / {guide['rejected']} rejected"
        self.fullscreen.update(guide, f"Pupils · step {guide['index']+1}/{guide['total']}", guide["instruction"], progress)
        if event != self.event:
            self.sounds.play({"rest":"rest", "prepare":"resume", "capture":"capture"}[guide["phase"]])
            self.event = event
        if guide["waiting"] and self.pending_present is None:
            self.pending_present = self.root.after_idle(lambda e=event: self.present(e))

    def present(self, event):
        self.pending_present = None
        if event != self.event or self.fullscreen is None:
            return
        if not self.fullscreen.ready:
            self.pending_present = self.root.after(30, lambda: self.present(event))
        elif self.fullscreen.canvas.find_all():
            self.call("present_pupil_step", event[1], event[3], event[0])

    def dismiss_fullscreen(self):
        if self.pending_present is not None:
            self.root.after_cancel(self.pending_present)
            self.pending_present = None
        if self.fullscreen is not None:
            self.fullscreen.close()
            self.fullscreen = None

    def cancel(self):
        self.dismiss_fullscreen()
        self.call("cancel")
        self.sounds.play("cancel")

    def reset_pupils(self):
        self.dismiss_fullscreen()
        self.call("reset_pupils")

    def close(self):
        self.dismiss_fullscreen()
        self.sounds.close()
