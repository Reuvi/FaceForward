"""Fixed pupil direction and a native square matrix; no configurable controls."""

import tkinter as tk
from tkinter import ttk

from .pupil import MATRIX_SIZE, matrix_cell
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
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=8)
        self.message = tk.StringVar(
            value="Direct MediaPipe tracking · no calibration or sensitivity settings"
        )
        ttk.Label(self.frame, textvariable=self.message, wraplength=420).pack(
            anchor="w"
        )
        ttk.Label(
            self.frame,
            text="One highlighted cell marks the direction. The small dot shows the precise X/Y value. Dark cells hold the last visible position only; unknown input stays unavailable.",
            wraplength=420,
        ).pack(anchor="w", pady=5)
        self.canvas = tk.Canvas(
            self.frame, height=310, bg="#14202c", highlightthickness=0
        )
        self.canvas.pack(fill="x", pady=5)

    def update(self, state):
        draw_matrix(self.canvas, state)

    def close(self):
        pass
