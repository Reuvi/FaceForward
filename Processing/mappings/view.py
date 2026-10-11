"""Native mapping selection, readable commands and independent head settings."""

from copy import deepcopy
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk

from Processing.mouse.desktop import Scope, label, set_var, BG, TEXT, MUTED, GREEN
from .config import DIRECTIONS, KEYS


class MappingPanel(ttk.Frame):
    def __init__(self, parent, desktop):
        super().__init__(parent, padding=14)
        self.desktop, self.lab = desktop, desktop.lab
        self.generation = -1
        self.mapping_choices = []
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        label(toolbar, "Active mapping").pack(side="left", padx=(0, 8))
        self.selector = ttk.Combobox(toolbar, state="readonly", width=56)
        self.selector.pack(side="left", fill="x", expand=True)
        self.selector.bind("<<ComboboxSelected>>", lambda event: desktop.guarded(self.select))
        for title, command in (("Copy as…", self.copy), ("Export mapping", self.export), ("Import mapping", self.load)):
            desktop.button(toolbar, title, command).pack(side="left", padx=4)
        self.notice = tk.StringVar()
        label(self, textvariable=self.notice, foreground=GREEN, wraplength=1250).pack(anchor="w", pady=7)

        settings = ttk.Frame(self)
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
        self.apply_button = desktop.button(self, "Apply mapping settings — stops output", self.apply)
        self.apply_button.pack(anchor="w", pady=7)
        label(self, "Head thresholds use the fraction of your calibrated range from neutral. Pointer curve/dead zone are in Transfer settings. Eyes use calibrated actions without a dwell timer.",
              foreground=MUTED, wraplength=1250).pack(anchor="w", pady=(0, 6))

        style = ttk.Style(self)
        style.configure("Mapping.Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=25)
        self.table = ttk.Treeview(self, columns=("input", "raw", "filtered", "threshold", "instruction"), show="headings", height=8, style="Mapping.Treeview")
        for key, title, width in (("input","Input",145), ("raw","Raw",80), ("filtered","Filtered",80),
                                   ("threshold","Start / release",210), ("instruction","Instruction",400)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=60, stretch=key in ("threshold","instruction"))
        self.table.pack(fill="x")
        scopes = ttk.Frame(self)
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

    def mock_control(self, key, value):
        if self.lab.runtime["source"] == "mock":
            self.lab.control({key: float(value)})

    def select(self):
        index = self.selector.current()
        if index >= 0:
            self.lab.select_mapping(self.mapping_choices[index]["id"])

    def apply(self):
        data = deepcopy(self.lab.state()["mapping"])
        if data is None:
            raise ValueError("Select a gaming mapping first")
        data["name"], data["pointer_gain"] = self.name.get(), float(self.gain.get())
        data["revision"] += 1
        for (axis, key), var in self.fields.items():
            data[axis][key] = float(var.get())
        data["bindings"] = {key: var.get() for key, var in self.bindings.items()}
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

    def refresh(self, state, history):
        if state["mappings"] != self.mapping_choices:
            self.mapping_choices = state["mappings"]
            self.selector.configure(values=[f"{m['name']} [{m['id']}]" for m in self.mapping_choices])
        if self.generation != state["generation"]:
            self.generation = state["generation"]
            self.selector.current(next(i for i, m in enumerate(self.mapping_choices) if m["id"] == state["mapping_id"]))
            mapping = state["mapping"]
            for widget in self.edit_widgets:
                widget.configure(state="disabled" if mapping is None else "readonly" if isinstance(widget, ttk.Combobox) else "normal")
            self.apply_button.configure(state="disabled" if mapping is None else "normal")
            self.name.set(mapping["name"] if mapping else "Mouse and scroll")
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
        if self.desktop.notebook.select() == str(self):
            for scope in self.scopes:
                scope.draw(list(history))
