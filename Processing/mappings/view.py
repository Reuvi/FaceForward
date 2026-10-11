"""Native mapping selection, readable commands and independent head settings."""

from copy import deepcopy
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk

from Processing.mouse.desktop import Scope, label, set_var, BG, TEXT, MUTED, GREEN
from .config import DIRECTIONS, KEYS


class MappingPanel(ttk.Frame):
    def __init__(self, parent, desktop, *, compact=False):
        super().__init__(parent, padding=0 if compact else 14)
        self.desktop, self.lab = desktop, desktop.lab
        self.compact = compact
        self.settings_window = None
        self.curve_editor = None
        self.generation = -1
        self.mapping_choices = []
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        label(toolbar, "Active mapping").pack(side="left", padx=(0, 8))
        self.selector = ttk.Combobox(toolbar, state="readonly", width=32 if compact else 56)
        self.selector.pack(side="left", fill="x", expand=True)
        self.selector.bind("<<ComboboxSelected>>", lambda event: desktop.guarded(self.select))
        if compact:
            desktop.button(toolbar, "Mapping settings…", self.show_settings).pack(side="left", padx=(8,0))
        desktop.button(toolbar, "Live curves…", self.show_curves).pack(side="left", padx=(8,0))
        self.center_row = ttk.Frame(self)
        self.center_button = desktop.button(self.center_row, "Center head & start",
                                            lambda: self.lab.action({"action":"center_head_start"}))
        self.center_button.pack(side="left", padx=(0,8))
        self.center_text = tk.StringVar()
        label(self.center_row, textvariable=self.center_text, foreground=MUTED).pack(side="left")
        self.notice = tk.StringVar()
        if not compact:
            label(self, textvariable=self.notice, foreground=GREEN, wraplength=1250).pack(anchor="w", pady=7)

        settings_parent = self
        if compact:
            self.settings_window = tk.Toplevel(self)
            self.settings_window.withdraw()
            self.settings_window.title("Mapping settings")
            self.settings_window.transient(desktop.root)
            self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
            settings_parent = ttk.Frame(self.settings_window, padding=18)
            settings_parent.pack(fill="both", expand=True)
        actions = ttk.Frame(settings_parent)
        actions.pack(fill="x", pady=(0,8))
        for title, command in (("Copy as…", self.copy), ("Export mapping", self.export), ("Import mapping", self.load)):
            desktop.button(actions, title, command).pack(side="left", padx=(0,8))
        settings = ttk.Frame(settings_parent)
        settings.pack(fill="x")
        self.fields = {}
        self.edit_widgets = []
        self.head_groups = []
        for column, axis in enumerate(("head_x", "head_y")):
            group = ttk.LabelFrame(settings, text="Head X · left / right" if axis == "head_x" else "Head Y · up / down", padding=8)
            group.grid(row=0, column=column, sticky="nsew", padx=(0, 9))
            self.head_groups.append(group)
            settings.columnconfigure(column, weight=1)
            for row, (key, title) in enumerate((("activation", "Start threshold"), ("release", "Release threshold"),
                                                 ("smoothing_ms", "Smoothing ms"), ("confirmation_ms", "Confirm ms"))):
                label(group, title).grid(row=row, column=0, sticky="w", padx=4, pady=3)
                var = tk.StringVar()
                self.fields[(axis, key)] = var
                widget = ttk.Entry(group, textvariable=var, width=8)
                widget.grid(row=row, column=1, padx=5)
                self.edit_widgets.append(widget)
        group = ttk.LabelFrame(settings, text="Mapping and pointer", padding=8)
        group.grid(row=0, column=2, sticky="nsew")
        settings.columnconfigure(2, weight=2)
        self.name, self.gain = tk.StringVar(), tk.StringVar()
        for row, (title, var) in enumerate((("Name", self.name), ("Pointer gain", self.gain))):
            label(group, title).grid(row=row, column=0, sticky="w", pady=3)
            entry = ttk.Entry(group, textvariable=var, width=33 if row == 0 else 8)
            entry.grid(row=row, column=1, columnspan=3, sticky="ew", padx=5)
            self.edit_widgets.append(entry)
        self.bindings = {}
        self.pointer_mode = tk.StringVar()
        label(group, "Pointer behavior").grid(row=2, column=0, sticky="w", pady=3)
        self.mode_widget = ttk.Combobox(group, textvariable=self.pointer_mode, state="readonly",
                                       values=("Screen destination", "Velocity"), width=22)
        self.mode_widget.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5)
        self.mode_widget.bind("<<ComboboxSelected>>", lambda event: self.pointer_controls())
        self.binding_group = ttk.Frame(group)
        self.binding_group.grid(row=3, column=0, columnspan=4, sticky="ew")
        for i, direction in enumerate(DIRECTIONS):
            row, col = i//2, (i%2)*2
            label(self.binding_group, direction.title()).grid(row=row, column=col, sticky="w", pady=3)
            var = tk.StringVar()
            self.bindings[direction] = var
            entry = ttk.Combobox(self.binding_group, textvariable=var, state="readonly", values=KEYS+("none",), width=10)
            entry.grid(row=row, column=col+1, padx=5)
            self.edit_widgets.append(entry)
        self.pointer_fields = {}
        self.pointer_widgets = {}
        self.target_jitter = tk.StringVar()
        self.jitter_label = label(group, "Fixation dead band (0–0.1)")
        self.jitter_label.grid(row=4, column=0, sticky="w", pady=3)
        self.jitter_widget = ttk.Entry(group, textvariable=self.target_jitter, width=8)
        self.jitter_widget.grid(row=4, column=1, sticky="w", padx=5)
        self.down_gain = tk.StringVar()
        label(group, "Downward boost (1–8×)").grid(row=5, column=0, sticky="w", pady=3)
        down_entry = ttk.Entry(group, textvariable=self.down_gain, width=8)
        down_entry.grid(row=5, column=1, sticky="w", padx=5)
        self.edit_widgets.append(down_entry)
        self.target_fields = {}
        self.target_widgets = []
        for row, (key, title) in enumerate((("target_smoothing_ms", "Position smoothing ms"),
                                           ("target_interpolation_ms", "Position delay ms")), start=6):
            var = tk.StringVar()
            self.target_fields[key] = var
            title_widget = label(group, title)
            title_widget.grid(row=row, column=0, sticky="w", pady=3)
            widget = ttk.Entry(group, textvariable=var, width=8)
            widget.grid(row=row, column=1, sticky="w", padx=5)
            self.target_widgets.extend((title_widget, widget))
        self.adaptive = tk.BooleanVar(value=True)
        self.adaptive_widget = ttk.Checkbutton(settings_parent, text="Adaptive pointer smoothing (1€)", variable=self.adaptive)
        self.adaptive_widget.pack(anchor="w", pady=5)
        self.motion_group = ttk.LabelFrame(settings_parent, text="Head movement response", padding=8)
        self.motion_enabled = tk.BooleanVar()
        ttk.Checkbutton(self.motion_group, text="Speed-aware acceleration and return braking",
                        variable=self.motion_enabled).grid(row=0, column=0, columnspan=4, sticky="w")
        self.motion_fields = {}
        for col, (key, title) in enumerate((("speed_gain", "Movement boost (0–2)"),
                                           ("return_brake", "Return braking (0–1)"))):
            label(self.motion_group, title).grid(row=1, column=col*2, sticky="w", padx=5, pady=5)
            var = tk.StringVar()
            self.motion_fields[key] = var
            ttk.Entry(self.motion_group, textvariable=var, width=8).grid(row=1, column=col*2+1, padx=5)
        self.wink_clicks = tk.BooleanVar()
        ttk.Checkbutton(self.motion_group, text="Eye clicks: left eye → left click, right eye → right click (source in Live curves)",
                        variable=self.wink_clicks).grid(row=2, column=0, columnspan=4, sticky="w", pady=4)
        self.pointer_group = None
        if compact:
            pointer = ttk.LabelFrame(settings_parent, text="Pointer response", padding=8)
            self.pointer_group = pointer
            pointer.pack(fill="x", pady=(10,0))
            for i, (key, title) in enumerate((("deadzone", "Dead zone"), ("hysteresis", "Activation margin"),
                    ("smoothing_ms", "Smoothing ms"), ("exponent", "Response curve"),
                    ("acceleration", "Acceleration / s"), ("deceleration", "Deceleration / s"))):
                row, col = divmod(i, 3)
                title_widget = label(pointer, title)
                title_widget.grid(row=row, column=col*2, sticky="w", padx=5, pady=5)
                var = tk.StringVar()
                self.pointer_fields[key] = var
                widget = ttk.Entry(pointer, textvariable=var, width=8)
                widget.grid(row=row,column=col*2+1,padx=5)
                self.pointer_widgets[key] = (title_widget, widget)
        self.apply_button = desktop.button(settings_parent, "Apply settings — stops output", self.apply)
        self.apply_button.pack(anchor="w", pady=7)
        self.help_text = tk.StringVar()
        label(settings_parent, textvariable=self.help_text,
              foreground=MUTED, wraplength=1250).pack(anchor="w", pady=(0, 6))
        self.settings_notice = tk.StringVar()
        if compact:
            label(settings_parent, textvariable=self.settings_notice, foreground="#ffa79c", wraplength=900).pack(anchor="w")

        style = ttk.Style(self)
        table_style = "CompactMapping.Treeview" if compact else "Mapping.Treeview"
        style.configure(table_style, background=BG, fieldbackground=BG, foreground=TEXT, rowheight=23 if compact else 25)
        self.table = ttk.Treeview(self, columns=("input", "raw", "filtered", "threshold", "instruction"), show="headings", height=8, style=table_style)
        for key, title, width in (("input","Input",125), ("raw","Input 0–1",75), ("filtered","Filtered",70),
                                   ("threshold","Start / release",170), ("instruction","Command",270)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=60, stretch=key in ("threshold","instruction"))
        self.table.pack(fill="x", pady=(4,0) if compact else 0)
        scopes = ttk.Frame(self)
        if not compact:
            scopes.pack(fill="both", expand=True, pady=7)
        self.scopes = []
        for index, (title, keys) in enumerate((("Head X · raw / filtered", ("raw_head_x", "filtered_head_x")),
                                                ("Head Y · raw / filtered", ("raw_head_y", "filtered_head_y")))):
            scope = Scope(scopes, title, keys)
            scope.grid(row=0, column=index, sticky="nsew", padx=(0, 6))
            scopes.columnconfigure(index, weight=1)
            self.scopes.append(scope)
        scopes.rowconfigure(0, weight=1)
        self.events = tk.StringVar()
        label(self, textvariable=self.events, foreground=MUTED, wraplength=1250).pack(anchor="w")
        self.mock = ttk.Frame(self)
        self.mock.pack(fill="x", pady=5)
        for key, title in (("head_x", "Synthetic head X"), ("scroll", "Synthetic head Y")):
            label(self.mock, title).pack(side="left", padx=5)
            widget = ttk.Scale(self.mock, from_=0, to=1, value=.5,
                               command=lambda value, key=key: self.mock_control(key, value))
            widget.pack(side="left", fill="x", expand=True, padx=5)

    def show_settings(self):
        self.settings_window.deiconify()
        self.settings_window.lift()

    def pointer_controls(self):
        target = self.pointer_mode.get() == "Screen destination"
        if self.pointer_group is not None:
            if target:
                self.pointer_group.pack_forget()
            else:
                self.pointer_group.pack(fill="x", pady=(10,0), before=self.apply_button)
        for widget in (self.jitter_label, self.jitter_widget, *self.target_widgets):
            widget.grid() if target else widget.grid_remove()
        visible = [(key, widgets) for key, widgets in self.pointer_widgets.items()
                   if not target]
        for widgets in self.pointer_widgets.values():
            for widget in widgets:
                widget.grid_remove()
        for i, (_, widgets) in enumerate(visible):
            row, col = divmod(i, 3)
            for offset, widget in enumerate(widgets):
                widget.grid(row=row, column=col*2+offset)

    def show_curves(self):
        from Processing.tuning.view import CurveEditor
        if self.curve_editor is None:
            self.curve_editor = CurveEditor(self.desktop.root, self.lab)
        else:self.curve_editor.show()

    def apply(self):
        try:
            self._apply()
        except (ValueError, TypeError, KeyError) as exc:
            self.settings_notice.set(str(exc))
            raise
        self.settings_notice.set("Settings applied. Center your inputs and press Start again.")

    def mock_control(self, key, value):
        if self.lab.runtime["source"] == "mock":
            self.lab.control({key: float(value)})

    def select(self):
        index = self.selector.current()
        if index >= 0:
            self.lab.select_mapping(self.mapping_choices[index]["id"])

    def _apply(self):
        data = deepcopy(self.lab.state()["mapping"])
        if data is None:
            if not self.compact:
                raise ValueError("Select a gaming mapping first")
            config = deepcopy(self.lab.state()["config"])
            config["pointer"].update({key:float(var.get()) for key,var in self.pointer_fields.items()})
            self.lab.settings({"config":config})
            return
        data["name"], data["pointer_gain"] = self.name.get(), float(self.gain.get())
        data["adaptive_pointer"] = self.adaptive.get()
        data["pointer_mode"] = "target" if self.pointer_mode.get() == "Screen destination" else "velocity"
        data["target_jitter"] = float(self.target_jitter.get())
        data["pointer_down_gain"] = float(self.down_gain.get())
        data["head_motion"] = dict(enabled=self.motion_enabled.get(),
                                   **{key:float(var.get()) for key,var in self.motion_fields.items()})
        data["head_wink_clicks"] = self.wink_clicks.get()
        data.update({key:float(var.get()) for key,var in self.target_fields.items()})
        data["revision"] += 1
        for (axis, key), var in self.fields.items():
            data[axis][key] = float(var.get())
        data["bindings"] = {key: var.get() for key, var in self.bindings.items()}
        data["response"]["pointer"].update({key:float(var.get()) for key,var in self.pointer_fields.items()})
        self.lab.update_mapping(data)

    def copy(self):
        name = simpledialog.askstring("Copy mapping", "Name for the new mapping:", parent=self)
        if name:
            self.lab.copy_mapping(name)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, title="Save applied mapping", defaultextension=".json", filetypes=[("Mapping JSON", "*.json")])
        if path:
            self.lab.export_mapping(path)

    def load(self):
        path = filedialog.askopenfilename(parent=self, title="Load mapping", filetypes=[("Mapping JSON", "*.json")])
        if path:
            self.lab.import_mapping(path)

    @staticmethod
    def mouse_rows(snap):
        """Keep the previous mouse mapping readable in the combined App view."""
        diag = snap["diagnostics"]
        rows = []
        for side in ("left", "right"):
            raw = diag[side+"_closed"]
            rows.append(dict(id="eye_"+side,input=side.title()+" eye action",
                raw=None if raw is None else int(raw),filtered=None if raw is None else int(raw),
                threshold="Calibrated action",instruction=side.title()+" mouse: "+("active" if snap[side+"_click"] else "released")))
        for index, axis in enumerate(("x", "y")):
            point, filtered = diag["raw_pointer"], diag["interpolated_pointer"]
            signed = 2*snap["pointer_"+axis]-1
            direction = (("right" if signed>0 else "left") if axis=="x" else ("down" if signed>0 else "up"))
            rows.append(dict(id="pupil_"+axis,input="Pupils "+axis.upper(),raw=point[index] if point else None,
                filtered=filtered[index] if filtered else None,threshold="Pointer dead zone",
                instruction="Pointer: "+("unknown; stopped" if point is None else "stopped" if abs(signed)<.0001 else f"{direction} {abs(signed):.0%}")))
        rows.append(dict(id="scroll",input="Head Y",raw=diag["raw_scroll"],filtered=diag["interpolated_scroll"],
            threshold="Scroll dead zone",instruction=f"Scroll velocity: {2*snap['scroll_y']-1:+.0%}"))
        return rows

    def refresh(self, state, history):
        if self.curve_editor is not None:self.curve_editor.refresh(state)
        if state["mappings"] != self.mapping_choices:
            self.mapping_choices = state["mappings"]
            self.selector.configure(values=[m["name"] if self.compact else f"{m['name']} [{m['id']}]" for m in self.mapping_choices])
        if self.generation != state["generation"]:
            self.generation = state["generation"]
            self.selector.current(next(i for i, m in enumerate(self.mapping_choices) if m["id"] == state["mapping_id"]))
            mapping = state["mapping"]
            head_only = bool(mapping and mapping.get("input_mode") == "head-mouse")
            if head_only:
                self.center_row.pack(fill="x", pady=5, after=self.selector.master)
                center=state["config"]["pointer"]
                self.center_text.set(f"Resting center: X {center['center_x']:.3f}, Y {center['center_y']:.3f} · hold a comfortable pose to recenter")
                self.motion_group.pack(fill="x", pady=(6,0), after=self.adaptive_widget)
            else:
                self.center_row.pack_forget()
                self.motion_group.pack_forget()
            motion = mapping["head_motion"] if mapping else dict(enabled=False,speed_gain=.75,return_brake=.65)
            self.motion_enabled.set(motion["enabled"])
            self.wink_clicks.set(mapping["head_wink_clicks"] if mapping else False)
            for key, var in self.motion_fields.items():
                var.set(motion[key])
            for group in (*self.head_groups, self.binding_group):
                group.grid_remove() if head_only else group.grid()
            self.adaptive_widget.configure(state="normal" if mapping else "disabled")
            self.adaptive.set(mapping.get("adaptive_pointer", True) if mapping else False)
            self.pointer_mode.set("Screen destination" if mapping and mapping["pointer_mode"] == "target" else "Velocity")
            self.target_jitter.set(mapping["target_jitter"] if mapping else .01)
            self.down_gain.set(mapping["pointer_down_gain"] if mapping else 1)
            for key, var in self.target_fields.items():
                var.set(mapping[key] if mapping else 0)
            self.mode_widget.configure(state="disabled" if head_only or not mapping else "readonly")
            self.pointer_controls()
            head_help = ("Head X + Head Y move the pointer together; both axes need calibration. Small movements give precise slow speed; larger, faster turns travel quickly. "
                         + ("Each eye clicks its matching mouse button. Choose calibrated wink or plain open/closed in Live curves. Pupils, keys and scroll are ignored."
                            if mapping and mapping["head_wink_clicks"] else "Eyes and pupils are ignored; no clicks, keys or scroll."))
            self.help_text.set((head_help
                               if head_only else "Head thresholds use the fraction of your calibrated range from neutral. Choose wink or plain eye open/closed clicks in Live curves; both are immediate.")
                               + (" Screen destination moves to a point and stops; without screen calibration its alignment is approximate. Fixation dead band 0.002 means 0.2% of the screen. Position smoothing/delay belong to this mapping. Velocity keeps moving while off-center."
                                  if not head_only else "")
                               + " Downward boost multiplies movement below center before inversion; pointer gain scales overall response."
                               + (" Faster turns away from neutral get a speed boost; returning toward neutral brakes the cursor. Holding your head still returns to normal speed. Uncheck speed-aware response to compare the original feel." if head_only else "")
                               + ("" if self.compact else " Velocity smoothing and response are in Transfer settings."))
            for widget in self.edit_widgets:
                widget.configure(state="disabled" if mapping is None else "readonly" if isinstance(widget, ttk.Combobox) else "normal")
            self.apply_button.configure(state="disabled" if mapping is None and not self.compact else "normal")
            self.name.set(mapping["name"] if mapping else "Mouse and scroll")
            for key, var in self.pointer_fields.items():
                var.set(state["config"]["pointer"][key])
            if mapping:
                self.gain.set(mapping["pointer_gain"])
                for (axis, key), var in self.fields.items():
                    var.set(mapping[axis][key])
                for key, var in self.bindings.items():
                    var.set(mapping["bindings"][key])
        if state["runtime"]["source"] == "external":
            self.mock.pack_forget()
        elif not self.mock.winfo_manager():
            self.mock.pack(fill="x", pady=5)
        snap = state["snapshot"]
        output = state["output"]
        mode = {"preview": "PREVIEW ONLY", "dry-run": "DRIVER DRY RUN · no OS events", "native": "LIVE MOUSE + KEYBOARD"}[output["mode"]]
        set_var(self.notice, mode+" · "+(output.get("error") or snap["status"]))
        rows = snap.get("instructions", [])
        if not rows and self.compact:
            rows = self.mouse_rows(snap)
        existing = set(self.table.get_children())
        for row in rows:
            values = (row["input"], *("unknown" if row[k] is None else f"{row[k]:.3f}" for k in ("raw","filtered")), row["threshold"], row["instruction"])
            if row["id"] in existing:
                if tuple(self.table.item(row["id"], "values")) != values:
                    self.table.item(row["id"], values=values)
                existing.remove(row["id"])
            else:
                self.table.insert("", "end", iid=row["id"], values=values)
        for identity in existing:
            self.table.delete(identity)
        if not rows:
            set_var(self.notice, mode+" · Mouse and scroll · "+(output.get("error") or snap["status"]))
        events = []
        for event in state["commands"][-3:]:
            command = event["command"]
            held = [key.upper() for key, value in command["keys"].items() if value]
            held += [key.replace("_click", " mouse") for key, value in command["buttons"].items() if value]
            events.append(f"#{event['id']} "+(" + ".join(held) or "all released"))
        set_var(self.events, "Recent command transitions: "+("   ·   ".join(events) or "none"))
        if output["mode"] != "preview":
            counts = output.get("event_counts", {})
            set_var(self.events, f"Driver events: {counts.get(3,0)} left clicks · {counts.get(4,0)} right clicks · {counts.get(7,0)} key downs · {counts.get(8,0)} key ups · {counts.get(1,0)} mouse moves")
        if not self.compact and self.desktop.notebook.select() == str(self):
            for scope in self.scopes:
                scope.draw(list(history))
