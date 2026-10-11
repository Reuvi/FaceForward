"""Temporary native full-screen pupil target, sharing the existing capture guide."""
import tkinter as tk
from .movement_view import MovementPanel


class PupilPanel(MovementPanel):
    def __init__(self, parent, root, call):
        super().__init__(parent, root, call, "pupil")
        self.window = self.canvas = None
        self.root_space_binding = self.root_escape_binding = None
        self.focus_pending = None

    def update(self, state):
        super().update(state)
        guide = state.get("movement_guide")
        active = guide and guide["kind"] == "pupil" and guide["active"]
        if not active:
            self.close_window()
            return
        if self.window is None:
            self.window = tk.Toplevel(self.root)
            self.window.title("Pupil joystick calibration")
            self.window.attributes("-fullscreen", True)
            self.window.configure(bg="#101c29")
            self.canvas = tk.Canvas(self.window, bg="#101c29", highlightthickness=0)
            self.canvas.pack(fill="both", expand=True)
            self.window.bind("<Escape>", lambda e: self.call("cancel"))
            self.window.bind("<space>", lambda e: self.capture_pose())
            self.window.protocol("WM_DELETE_WINDOW", lambda: self.call("cancel"))
            # On macOS fullscreen can leave keyboard focus on the parent toplevel.
            # Bind both, and remove only our temporary parent bindings on close.
            self.root_space_binding = self.root.bind("<space>", lambda e: self.capture_pose(), add="+")
            self.root_escape_binding = self.root.bind("<Escape>", lambda e: self.call("cancel"), add="+")
            self.window.update_idletasks()
            self.window.lift()
            self.focus_pending = self.window.after_idle(self.focus_target)
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 400), max(c.winfo_height(), 300)
        target = guide.get("target") or (.5, .5)
        x, y = (w*(.12+.76*target[0]), h*(.18+.58*target[1]))
        resting = guide["phase"] == "rest"
        c.create_oval(x-18, y-18, x+18, y+18, fill="#526070" if resting else "#55cfff", outline="white", width=2)
        c.create_text(w/2, 38, text=f"{guide['index']+1}/{guide['total']} · {guide['role'].upper()} · {guide['name'].upper()}", fill="white", font=("Arial",24,"bold"))
        text = (f"REST {guide['remaining_ms']/1000:.1f}s · relax your eyes" if resting else
                "Look at the dot. Keep your head still. Press SPACE when ready." if guide["waiting"] else
                f"{guide['phase'].upper()} {guide['remaining_ms']/1000:.1f}s · keep looking at the dot")
        c.create_text(w/2, h-100, text=text, fill="#ffe2a6", font=("Arial",22,"bold"), width=w-60)
        c.create_text(w/2, h-65, text="Tracking: "+state.get("pupil",{}).get("reason","Waiting"), fill="#a8dce9", font=("Arial",13), width=w-60)
        c.create_text(w/2, h-32, text="Comfortable movement only · Escape cancels · These are joystick directions, not screen-gaze training", fill="white", font=("Arial",14), width=w-60)

    def focus_target(self):
        self.focus_pending = None
        if self.window is not None:
            self.window.focus_force()

    def close_window(self):
        if self.focus_pending is not None and self.window is not None:
            self.window.after_cancel(self.focus_pending)
            self.focus_pending = None
        if self.root_space_binding:
            self.root.unbind("<space>", self.root_space_binding)
            self.root_space_binding = None
        if self.root_escape_binding:
            self.root.unbind("<Escape>", self.root_escape_binding)
            self.root_escape_binding = None
        if self.window is not None:
            self.window.destroy()
            self.window = self.canvas = None

    def close(self):
        self.close_window()
        super().close()
