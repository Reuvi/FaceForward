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
        for column, axis in enumerate(("head_x", "head_y")):
            group = ttk.LabelFrame(settings, text="Head X · left / right" if axis == "head_x" else "Head Y · up / down", padding=8)
            group.grid(row=0, column=column, sticky="nsew", padx=(0, 9))
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
        for i, direction in enumerate(DIRECTIONS):
            row, col = 2+i//2, (i%2)*2
            label(group, direction.title()).grid(row=row, column=col, sticky="w", pady=3)
            var = tk.StringVar()
            self.bindings[direction] = var
            entry = ttk.Combobox(group, textvariable=var, state="readonly", values=KEYS+("none",), width=10)
            entry.grid(row=row, column=col+1, padx=5)
            self.edit_widgets.append(entry)
        self.pointer_fields = {}
        if compact:
            pointer = ttk.LabelFrame(settings_parent, text="Pupil pointer response", padding=8)
            pointer.pack(fill="x", pady=(10,0))
            for i, (key, title) in enumerate((("deadzone", "Dead zone"), ("hysteresis", "Activation margin"),
                    ("smoothing_ms", "Smoothing ms"), ("exponent", "Response curve"),
                    ("acceleration", "Acceleration / s"), ("deceleration", "Deceleration / s"))):
                row, col = divmod(i, 3)
                label(pointer, title).grid(row=row, column=col*2, sticky="w", padx=5, pady=5)
                var = tk.StringVar()
                self.pointer_fields[key] = var
                ttk.Entry(pointer, textvariable=var, width=8).grid(row=row,column=col*2+1,padx=5)
        self.apply_button = desktop.button(settings_parent, "Apply settings — stops output", self.apply)
        self.apply_button.pack(anchor="w", pady=7)
        label(settings_parent, "Head thresholds use the fraction of your calibrated range from neutral. Eyes use calibrated actions without a dwell timer." + ("" if compact else " Pointer curve/dead zone are in Transfer settings."),
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
        if state["mappings"] != self.mapping_choices:
            self.mapping_choices = state["mappings"]
            self.selector.configure(values=[m["name"] if self.compact else f"{m['name']} [{m['id']}]" for m in self.mapping_choices])
        if self.generation != state["generation"]:
            self.generation = state["generation"]
            self.selector.current(next(i for i, m in enumerate(self.mapping_choices) if m["id"] == state["mapping_id"]))
            mapping = state["mapping"]
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
