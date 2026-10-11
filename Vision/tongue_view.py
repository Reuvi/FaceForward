"""Step-by-step native tongue appearance setup; no image processing here."""

import tkinter as tk
from tkinter import ttk


class TongueSetupPanel:
    def __init__(self, parent, call):
        self.hint = tk.StringVar()
        ttk.Label(parent, textvariable=self.hint, wraplength=420, justify="left",
                  font=("Arial", 12, "bold")).pack(fill="x", pady=8)
        self.background = ttk.Button(parent, text="1  Capture background — tongue hidden",
                                     command=lambda: call("collect", "tongue_absent"))
        self.background.pack(fill="x", pady=3)
        ttk.Label(parent, text="Open your mouth, keep your tongue behind your teeth. Hold until capture finishes.",
                  wraplength=420).pack(anchor="w")
        self.freeze = ttk.Button(parent, text="2  Freeze / retake tongue photo", command=lambda: call("freeze_mouth"))
        self.freeze.pack(fill="x", pady=(10, 3))
        ttk.Label(parent, text="Show your tongue past the lip so its front edge is visible. Freeze, then click inside tongue tissue below—not lips, gums, teeth or an edge.",
                  wraplength=420).pack(anchor="w")
        self.mouth = tk.Label(parent, bg="#14202c", fg="white", text="Open your mouth to see the crop")
        self.mouth.pack(pady=6)
        self.clear = ttk.Button(parent, text="Clear tongue marks — keep background",
                                command=lambda: call("clear_tongue_marks"))
        self.clear.pack(fill="x", pady=3)
        self.fit = ttk.Button(parent, text="3  Fit and inspect tongue color", command=lambda: call("fit_tongue"))
        self.fit.pack(fill="x", pady=3)
        ttk.Label(parent, text="Green should cover the tongue. Cyan marks its front-edge midpoint. Move slowly; if the mask follows lips or gums, reset and redo the background/marks. If there is no cyan tip, read the reason below and expose a clear front edge.",
                  wraplength=420).pack(anchor="w", pady=6)
        ttk.Label(parent, text="4  Use Start tongue position guide above. Hide the tongue for its first check, then show it at center and each comfortable direction. Every pose waits for I'm in position — capture. A failed pose can be retried alone.",
                  wraplength=420).pack(anchor="w", pady=6)

    def update(self, state):
        busy = state["calibrating"]
        visible = bool(state["selected"])
        colors = state["tongue_pixels"]
        background = colors["negative"] >= 100
        self.background.configure(state="normal" if visible and not busy else "disabled")
        self.freeze.configure(state="normal" if visible and not busy and background else "disabled")
        self.clear.configure(state="normal" if not busy and colors["positive"] else "disabled")
        self.fit.configure(state="normal" if visible and not busy and background and colors["positive"] >= 100 else "disabled")
        if state["collecting"] == "tongue_absent":
            hint = f"{state['collection_phase'].upper()} · {state['collection_remaining_ms']/1000:.1f}s. Mouth open, tongue hidden."
        elif state["tongue_fit"]:
            hint = "3 ✓ Color fitted. Inspect the live mask, then start the position guide above."
        elif not background:
            hint = "Start with 1: capture the mouth and surrounding skin WITHOUT visible tongue."
        elif not state["frozen"]:
            hint = "1 ✓ Background ready. Show your tongue, then freeze a photo with 2."
        elif not colors["positive"]:
            hint = "Click inside the tongue in the frozen photo. Yellow boxes show your actual marks."
        else:
            hint = "2 ✓ Tongue marked. Add another tissue patch if needed, or use 3 to fit. Bad click? Clear marks."
        self.hint.set(hint)
