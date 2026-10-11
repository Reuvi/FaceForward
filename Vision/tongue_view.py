"""Step-by-step native tongue appearance setup; no image processing here."""

import tkinter as tk
from tkinter import filedialog, ttk


class TongueSetupPanel:
    def __init__(self, parent, call):
        self.neural = ttk.Frame(parent)
        ttk.Label(self.neural, text="Local tongue segmentation — no color sampling", font=("Arial",12,"bold"), wraplength=420).pack(anchor="w")
        ttk.Label(self.neural, text="1  Open your mouth and show the front of your tongue past the lip.\n2  Check green follows tongue tissue and cyan follows the front-edge midpoint.\n3  Start the position guide above: hide tongue first, then center / left / right / up / down.\nNo background capture or clicking is needed.", wraplength=420, justify="left").pack(anchor="w", pady=5)
        self.backend_status = tk.StringVar()
        ttk.Label(self.neural, textvariable=self.backend_status, wraplength=420).pack(anchor="w")
        def choose():
            path = filedialog.askopenfilename(parent=parent, title="Choose tongue_seg.onnx", filetypes=[("ONNX model", "*.onnx")])
            if path: call("load_tongue_model", path)
        self.load_model = ttk.Button(parent, text="Load local tongue segmentation model…", command=choose)
        self.load_model.pack(fill="x", pady=4)
        self.legacy_top = ttk.Frame(parent)
        self.legacy_top.pack(fill="x")
        self.legacy_bottom = ttk.Frame(parent)
        self.hint = tk.StringVar()
        ttk.Label(self.legacy_top, textvariable=self.hint, wraplength=420, justify="left",
                  font=("Arial", 12, "bold")).pack(fill="x", pady=8)
        self.background = ttk.Button(self.legacy_top, text="1  Capture background — tongue hidden",
                                     command=lambda: call("collect", "tongue_absent"))
        self.background.pack(fill="x", pady=3)
        ttk.Label(self.legacy_top, text="Open your mouth, keep your tongue behind your teeth. Hold until capture finishes.",
                  wraplength=420).pack(anchor="w")
        self.freeze = ttk.Button(self.legacy_top, text="2  Freeze / retake tongue photo", command=lambda: call("freeze_mouth"))
        self.freeze.pack(fill="x", pady=(10, 3))
        ttk.Label(self.legacy_top, text="Show your tongue past the lip so its front edge is visible. Freeze, then click inside tongue tissue below—not lips, gums, teeth or an edge.",
                  wraplength=420).pack(anchor="w")
        self.mouth = tk.Label(parent, bg="#14202c", fg="white", text="Open your mouth to see the crop")
        self.mouth.pack(pady=6)
        self.legacy_bottom.pack(fill="x")
        self.clear = ttk.Button(self.legacy_bottom, text="Clear tongue marks — keep background",
                                command=lambda: call("clear_tongue_marks"))
        self.clear.pack(fill="x", pady=3)
        self.fit = ttk.Button(self.legacy_bottom, text="3  Fit and inspect tongue color", command=lambda: call("fit_tongue"))
        self.fit.pack(fill="x", pady=3)
        ttk.Label(self.legacy_bottom, text="Green should cover the tongue. Cyan marks its front-edge midpoint. Move slowly; if the mask follows lips or gums, reset and redo the background/marks. If there is no cyan tip, read the reason below and expose a clear front edge.",
                  wraplength=420).pack(anchor="w", pady=6)
        ttk.Label(self.legacy_bottom, text="4  Use Start tongue position guide above. Hide the tongue for its first check, then show it at center and each comfortable direction. Every pose waits for I'm in position — capture. A failed pose can be retried alone.",
                  wraplength=420).pack(anchor="w", pady=6)

    def update(self, state):
        busy = state["calibrating"]
        self.load_model.configure(state="disabled" if busy else "normal")
        if state.get("tongue_backend") == "segmentation":
            self.legacy_top.pack_forget(); self.legacy_bottom.pack_forget()
            self.neural.pack(fill="x", before=self.mouth)
            report = state.get("tongue_fit") or {}
            elapsed = report.get("inference_ms")
            confidence = report.get("confidence")
            self.backend_status.set((f"CPU inference: {elapsed:.1f} ms" if elapsed is not None else "Waiting for a clear mouth image") +
                                    (f" · score {confidence:.2f}" if confidence is not None else "") +
                                    ("\n"+report["error"] if report.get("error") else ""))
            return
        self.neural.pack_forget()
        self.legacy_top.pack(fill="x", before=self.mouth)
        self.legacy_bottom.pack(fill="x", after=self.mouth)
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
