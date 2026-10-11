"""Live direct pupil direction controls; no calibration wizard or popup."""
import tkinter as tk
from tkinter import ttk


class PupilPanel:
    def __init__(self, parent, root, call):
        self.call = call
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="x", pady=8)
        self.values = [tk.StringVar(value="1.0"), tk.StringVar(value="1.0")]
        self.applied = None
        self.message = tk.StringVar(value="Direct MediaPipe tracking · no calibration required")
        ttk.Label(self.frame, textvariable=self.message, wraplength=420).pack(anchor="w")
        self.inputs = []
        for title, value in zip(("Horizontal sensitivity", "Vertical sensitivity"), self.values):
            row = ttk.Frame(self.frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=title).pack(side="left")
            control = ttk.Spinbox(row, from_=.25, to=4, increment=.25, textvariable=value, width=7)
            control.pack(side="right")
            self.inputs.append(control)
        ttk.Label(self.frame, text="Higher sensitivity reaches the edges with less eye movement. Range: 0.25–4. Both start at 1.", wraplength=420).pack(anchor="w", pady=5)
        self.apply_button = ttk.Button(self.frame, text="Apply pupil sensitivity", command=self.apply)
        self.apply_button.pack(fill="x", pady=3)
        self.reset_button = ttk.Button(self.frame, text="Restore default sensitivity", command=lambda: call("set_pupil_sensitivity", 1., 1.))
        self.reset_button.pack(fill="x", pady=3)

    def apply(self):
        try:
            values = [float(v.get()) for v in self.values]
        except (ValueError, tk.TclError):
            self.message.set("Enter two numbers from 0.25 to 4.")
            return
        self.call("set_pupil_sensitivity", *values)

    def update(self, state):
        options = state["pupil_settings"]
        pair = tuple(options[k] for k in ("x_sensitivity", "y_sensitivity"))
        if pair != self.applied:
            for variable, value in zip(self.values, pair):
                variable.set(f"{value:g}")
            self.applied = pair
            self.message.set("Direct MediaPipe tracking · no calibration required")
        enabled = "disabled" if state["calibrating"] else "normal"
        for widget in (*self.inputs, self.apply_button, self.reset_button):
            widget.configure(state=enabled)

    def close(self):
        pass
