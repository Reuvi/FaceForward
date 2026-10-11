"""Native lab controller with an independent 100 Hz processing clock; no network."""

from collections import deque
from copy import deepcopy
from dataclasses import replace
import re
import threading
import time

from .config import MouseConfig, number
from .engine import MouseProcessor
from .mocks import SCENARIOS, raw_frame, scenario
from .output import control_message
from Processing.eye_samples import trace_fields
from Processing.tuning.model import edited, validate_profile
from Processing.mappings.config import GAMING_ID, MOUSE_TEST_ID, Mapping, mouse_test_mapping, read_mapping, write_mapping
from Processing.mappings.engine import GamingProcessor, HeadMouseProcessor


def now_ms():
    return time.monotonic() * 1000.0


class Lab:
    def __init__(self, config=None, *, clock=now_ms):
        self.lock = threading.RLock()
        self.clock = clock
        self.locked_source = None
        self.locked_pointer_source = None
        self.mapping_id = "mouse"
        self.mappings = {GAMING_ID: Mapping(), MOUSE_TEST_ID: mouse_test_mapping()}
        self.mouse_config = config or MouseConfig()
        self.commands = deque(maxlen=512)
        self.command_id = 0
        self.last_command_state = None
        self.output = None
        self.output_error = None
        self.output_status = {"mode": "preview", "enabled": False, "error": None}
        self.processor = MouseProcessor(config)
        self.runtime = {"sample_hz": 30, "rows": 9, "columns": 9, "vector_size": 11,
                        "pointer_speed": 900, "scroll_speed": 450, "source": "mock", "subject_id": "mock-person"}
        self.manual = {"x": 0.5, "y": 0.5, "scroll": 0.5, "head_x": .5, "left": False, "right": False}
        self.scenario_name = "manual"
        self.started = self.scenario_start = self.clock()
        self.next_sample = self.started
        self.sample_sequence = 0
        self.last_raw = None
        self.last_ingest = None
        self.snapshot = self.processor.tick(self.started)
        self.trace = deque(maxlen=2000)
        self.trace_id = 0
        self.generation = 0
        self.tuning_revision = 0
        self.pulses = {"left": 0.0, "right": 0.0}
        self.streaming = True
        self.stop_event = threading.Event()
        self.thread = None

    def step(self, timestamp):
        with self.lock:
            if self.runtime["source"] == "mock" and self.streaming and timestamp >= self.next_sample:
                state = scenario(self.scenario_name, (timestamp - self.scenario_start) / 1000.0, self.manual)
                for eye in ("left", "right"):
                    state[eye] = state[eye] or timestamp < self.pulses[eye]
                period = 1000.0 / self.runtime["sample_hz"]
                self.next_sample = timestamp + period - ((timestamp - self.next_sample) % period)
                if state["deliver"]:
                    self.last_raw = raw_frame(
                        self.sample_sequence, timestamp, state,
                        closed_value=self.processor.config.closed_value,
                        rows=self.runtime["rows"], columns=self.runtime["columns"],
                        vector_size=self.runtime["vector_size"], subject_id=self.runtime["subject_id"],
                    )
                    self._accept(self.last_raw, timestamp)
                    self.sample_sequence += 1
            self.take_snapshot(timestamp)
            self.trace_id += 1
            snap, diag = self.snapshot, self.snapshot["diagnostics"]
            point, interpolated = diag["raw_pointer"], diag["interpolated_pointer"]
            self.trace.append({
                **trace_fields(self.processor.eye_sample),
                "eye_sample_sequence": self.processor.eye_sample["sequence"] if self.processor.eye_sample else None,
                "eye_sample_timestamp_ms": self.processor.eye_sample["timestamp_ms"] if self.processor.eye_sample else None,
                "id": self.trace_id, "t": (timestamp - self.started) / 1000.0,
                "sample": snap["source_sequence"],
                "raw_x": point[0] if point else None, "raw_y": point[1] if point else None,
                "raw_scroll": diag["raw_scroll"],
                "interp_x": interpolated[0] if interpolated else None,
                "interp_y": interpolated[1] if interpolated else None,
                "interp_scroll": diag["interpolated_scroll"],
                "target_x": (diag["pointer_target"][0] + 1) / 2,
                "target_y": (diag["pointer_target"][1] + 1) / 2,
                "target_scroll": (diag["scroll_target"] + 1) / 2,
                "out_x": snap["pointer_x"], "out_y": snap["pointer_y"], "out_scroll": snap["scroll_y"],
                "pointer_mode": snap.get("pointer_mode", "velocity"),
                "target_speed": snap.get("target_speed", 0),
                "left_raw": int(diag["left_closed"]) if diag["left_closed"] is not None else None,
                "right_raw": int(diag["right_closed"]) if diag["right_closed"] is not None else None,
                "left_out": snap["left_click"], "right_out": snap["right_click"],
                "left_action_out": diag.get("button_actions", {}).get("left_eye", {}).get("down", snap["left_click"]),
                "right_action_out": diag.get("button_actions", {}).get("right_eye", {}).get("down", snap["right_click"]),
                "mouth_raw": diag.get("mouth_open"),
                "mouth_action_out": diag.get("button_actions", {}).get("mouth", {}).get("down", 0),
                "left_dwell": diag["left_dwell"], "right_dwell": diag["right_dwell"],
                "raw_head_x": diag.get("head_x", {}).get("raw"),
                "filtered_head_x": diag.get("head_x", {}).get("filtered"),
                "raw_head_y": diag.get("head_y", {}).get("raw"),
                "filtered_head_y": diag.get("head_y", {}).get("filtered"),
                **{"key_"+key: snap.get("keys", {}).get(key, 0)
                   for key in ("w", "a", "s", "d", "space", "left_shift")},
            })

    def take_snapshot(self, timestamp):
        """Called under the lab lock on captures and ticks, never from drawing."""
        self.snapshot = self.processor.tick(timestamp)
        message = control_message(self.snapshot)
        if self.output is not None:
            try:
                self.output.submit(message, self.runtime)
                self.output_status = self.output.snapshot()
            except Exception as exc:
                # A sink failure must never kill the independent freshness clock.
                self.output_error = str(exc)
                self.processor.disarm("Driver stopped: "+str(exc))
                try:
                    self.output.pause()
                except Exception:
                    pass
                self.snapshot = self.processor.tick(timestamp)
                message = control_message(self.snapshot)
                self.output_status = {"mode": self.output.mode, "enabled": False, "error": str(exc)}
        if message["format"] == "device_control_v1":
            state = (message["output_session_id"], message["enabled"],
                     tuple(message["buttons"].values()), tuple(message["keys"].values()))
            if state != self.last_command_state:
                self.command_id += 1
                self.commands.append({"id": self.command_id, "command": message})
                self.last_command_state = state
        else:
            self.last_command_state = None

    def set_output(self, output=None):
        """App injects a serialized sink; Processing has no driver dependency."""
        with self.lock:
            self.processor.disarm("Output changed; press Start again")
            self.take_snapshot(self.clock())
            previous, self.output = self.output, None
            if previous is not None:
                previous.close()
            self.output = output
            self.output_error = None
            self.output_status = {"mode": "preview", "enabled": False, "error": None}
            self.take_snapshot(self.clock())

    def start(self):
        if self.thread is not None:
            raise RuntimeError("Processing clock has already been started")
        if self.stop_event.is_set():
            raise RuntimeError("Closed lab cannot be restarted")
        def run():
            deadline = time.monotonic()
            while not self.stop_event.is_set():
                with self.lock:
                    self.step(self.clock())
                deadline += 0.01
                self.stop_event.wait(max(0, deadline - time.monotonic()))
                if time.monotonic() - deadline > 0.1:
                    deadline = time.monotonic()
        self.thread = threading.Thread(target=run, name="mouse-processing-clock", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        with self.lock:
            self.processor.disarm("Lab closed")
            self.take_snapshot(self.clock())
            if self.output is not None:
                self.output.close()
                self.output = None
        if self.thread:
            self.thread.join(timeout=2)

    def state(self, after=0, *, after_command=None):
        with self.lock:
            commands = list(self.commands)
            gap = after_command is not None and bool(commands) and after_command < commands[0]["id"]-1
            return {"eye_sample": self.processor.eye_sample, "snapshot": self.snapshot, "message": control_message(self.snapshot),
                    "output": deepcopy(dict(self.output_status, error=self.output_error or self.output_status.get("error"))),
                    "mapping_id": self.mapping_id,
                    "mapping": self.mappings[self.mapping_id].to_dict() if self.mapping_id != "mouse" else None,
                    "mappings": [{"id": "mouse", "name": "Mouse and scroll"}] +
                                [{"id": value.id, "name": value.name} for value in self.mappings.values()],
                    "commands": deepcopy(commands[-8:] if after_command is None else [c for c in commands if c["id"] > after_command]),
                    "command_id": self.command_id, "command_gap": gap,
                    "trace": [row for row in self.trace if row["id"] > after],
                    "raw": self.last_raw, "runtime": self.runtime.copy(), "manual": self.manual.copy(),
                    "config": self.processor.config.to_dict(), "scenario": self.scenario_name,
                    "streaming": self.streaming, "generation": self.generation, "tuning_revision": self.tuning_revision,
                    "input_status": self.last_ingest}

    def control(self, values):
        allowed = set(self.manual)
        if set(values) - allowed:
            raise ValueError("Unknown manual input")
        for key, value in values.items():
            if key in ("left", "right"):
                if type(value) is not bool:
                    raise ValueError("Eye inputs must be boolean closed states")
            else:
                number(value, key, 0, 1)
        with self.lock:
            self.manual.update(values)

    def settings(self, values):
        if set(values) - {"config", "runtime"}:
            raise ValueError("Unknown settings group")
        with self.lock:
            config = MouseConfig.from_dict(values.get("config", self.processor.config.to_dict()))
            if self.locked_pointer_source is not None:
                config = replace(config, pointer_source=self.locked_pointer_source)
            runtime = dict(self.runtime)
            if not isinstance(values.get("runtime", {}), dict):
                raise ValueError("runtime must be an object")
            runtime.update(values.get("runtime", {}))
            if set(runtime) != set(self.runtime):
                raise ValueError("Unknown lab setting")
            number(runtime["sample_hz"], "sample_hz", 5, 120)
            number(runtime["pointer_speed"], "pointer_speed", 50, 2500)
            number(runtime["scroll_speed"], "scroll_speed", 20, 1500)
            for name in ("rows", "columns", "vector_size"):
                value = runtime[name]
                if type(value) is not int or not 3 <= value <= 31 or value % 2 != 1:
                    raise ValueError(f"{name} must be an odd integer from 3 to 31")
            if runtime["source"] not in ("mock", "external"):
                raise ValueError("source must be mock or external")
            if self.locked_source is not None and runtime["source"] != self.locked_source:
                raise ValueError("The integrated app owns the input source; use its Vision source tab")
            if not isinstance(runtime["subject_id"], str) or not 1 <= len(runtime["subject_id"]) <= 128:
                raise ValueError("subject_id must be a nonempty string of at most 128 characters")
            mapping = None
            if self.mapping_id != "mouse":
                mapping = self.mappings[self.mapping_id]
                config = replace(config, pointer_source="gaze")
                mapping = replace(mapping, response=config, revision=mapping.revision + int(config != mapping.response))
            self.processor.disarm("Settings changed; start preview again")
            self.take_snapshot(self.clock())
            if self.mapping_id == "mouse":
                self.mouse_config = config
                self.processor = MouseProcessor(config, subject_id=runtime["subject_id"])
            else:
                self.mappings[self.mapping_id] = mapping
                processor = HeadMouseProcessor if mapping.input_mode == "head-mouse" else GamingProcessor
                self.processor = processor(mapping, subject_id=runtime["subject_id"])
            self.runtime = runtime
            self.trace.clear()
            self.generation += 1
            self.last_raw = None
            self.last_ingest = None
            self.pulses = {"left": 0.0, "right": 0.0}
            self.take_snapshot(self.clock())
            self.next_sample = self.clock()

    def select_mapping(self, mapping_id):
        with self.lock:
            if mapping_id != "mouse" and mapping_id not in self.mappings:
                raise ValueError("Unknown mapping")
            self.processor.disarm("Mapping changed; start preview again")
            self.take_snapshot(self.clock())
            self.mapping_id = mapping_id
            config = self.mouse_config if mapping_id == "mouse" else self.mappings[mapping_id].response
            self.settings({"config": config.to_dict()})

    def update_mapping(self, data):
        mapping = Mapping.from_dict(data)  # Validate everything before releasing/replacing.
        with self.lock:
            self.mappings[mapping.id] = mapping
            self.select_mapping(mapping.id)

    def set_eye_mode(self, require_wink, *, mapping_id, generation):
        with self.lock:
            if mapping_id != self.mapping_id or generation != self.generation:
                raise ValueError("Mapping/settings changed; refresh the curve editor")
            if self.mapping_id == "mouse":
                raise ValueError("Select a named mapping to choose the eye input")
            mapping = self.mappings[self.mapping_id]
            updated = replace(mapping, require_wink=require_wink, revision=mapping.revision+1)
            self.update_mapping(updated.to_dict())

    def _accept(self, frame, timestamp):
        """Accept under the lab lock and retain an explicitly recentered mapping."""
        result = self.processor.accept(frame, timestamp)
        if isinstance(self.processor, HeadMouseProcessor) and self.processor.mapping is not self.mappings[self.mapping_id]:
            self.mappings[self.mapping_id] = self.processor.mapping
            self.generation += 1
        return result

    def tune_response(self, channel, changes, *, mapping_id, generation):
        """Hot-update only transfer parameters; never restart or arm the source."""
        with self.lock:
            if mapping_id != self.mapping_id or generation != self.generation:
                raise ValueError("Mapping/settings changed; refresh the curve editor")
            current = dict(config=self.processor.config.to_dict(), raw=self.last_raw, runtime=self.runtime,
                           mapping=self.mappings[self.mapping_id].to_dict() if self.mapping_id != "mouse" else None)
            config, mapping = edited(current, channel, changes)
            core = self.processor
            if mapping:
                # Driver routing revision stays stable during response-only edits.
                core.mapping = mapping
                self.mappings[self.mapping_id] = mapping
                for axis in ("head_x", "head_y"):
                    gate = getattr(core, axis)
                    new = getattr(mapping, axis)
                    if new != gate.config:
                        gate.config = new
                        gate.reset()  # Release changed key gates; require fresh neutral.
            else:self.mouse_config = config
            for side in ("left", "right"):
                gate = getattr(core, side)
                new = getattr(config, side+"_eye")
                if new != gate.config:
                    gate.config = new
                    gate.reset()
            core.config = config
            pointer_config = (replace(config.pointer, smoothing_ms=mapping.target_smoothing_ms)
                              if mapping and mapping.pointer_mode == "target" else config.pointer)
            core.pointer.retune(pointer_config, gain=mapping.pointer_gain if mapping else 1,
                                down_gain=mapping.pointer_down_gain if mapping else 1)
            if mapping and mapping.pointer_mode == "target":
                core.pointer.jitter = mapping.target_jitter
                core.pointer.delay_ms = mapping.target_interpolation_ms
            if mapping and mapping.input_mode == "head-mouse" and mapping.head_motion.enabled:
                core.pointer.motion = mapping.head_motion
            core.scroll.retune(config.scroll)
            self.generation += 1
            self.tuning_revision += 1
            if core.armed and not core.enabled:
                # A larger dead zone must not start output from a cached sample.
                # Keep the explicit Start request, but require a new capture.
                core.received_ms = None
            self.take_snapshot(self.clock())
            return self.generation

    def apply_tuning_profile(self, data):
        config, mapping, speeds = validate_profile(data)
        with self.lock:
            if self.locked_pointer_source is not None:
                config = replace(config, pointer_source=self.locked_pointer_source)
                if mapping:mapping = replace(mapping, response=config)
            self.processor.disarm("Tuning profile loaded; press Start again")
            self.take_snapshot(self.clock())
            self.mapping_id = mapping.id if mapping else "mouse"
            if mapping:self.mappings[mapping.id] = mapping
            self.settings({"config":config.to_dict(), "runtime":speeds})
            self.tuning_revision += 1

    def copy_mapping(self, name):
        with self.lock:
            if self.mapping_id == "mouse":
                raise ValueError("Select a gaming mapping to copy")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Enter a mapping name")
            stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:55]
            if not stem or not stem[0].isalpha():
                stem = "mapping-"+stem[:47]
            identity, suffix = stem, 2
            while identity in self.mappings or identity == "mouse":
                identity = f"{stem}-{suffix}"
                suffix += 1
            mapping = replace(self.mappings[self.mapping_id], id=identity, name=name, revision=1)
            self.update_mapping(mapping.to_dict())

    def export_mapping(self, path):
        with self.lock:
            if self.mapping_id == "mouse":
                raise ValueError("Select a gaming mapping to export")
            write_mapping(path, self.mappings[self.mapping_id])

    def import_mapping(self, path):
        self.update_mapping(read_mapping(path).to_dict())

    def action(self, values):
        action = values.get("action")
        with self.lock:
            timestamp = self.clock()
            if action == "arm":
                self.output_error = None
                self.processor.arm()
            elif action == "center_head_start":
                if not isinstance(self.processor, HeadMouseProcessor):
                    raise ValueError("Center head & start needs a head mouse mapping")
                self.processor.disarm("Recentering head; output released")
                self.take_snapshot(timestamp)
                self.output_error = None
                self.processor.arm(center=True)
            elif action == "stop":
                self.processor.disarm()
            elif action == "center":
                self.manual.update(x=0.5, y=0.5, scroll=0.5, head_x=.5, left=False, right=False)
                self.pulses = {"left": 0.0, "right": 0.0}
                self.scenario_name = "manual"
            elif action == "stream":
                if type(values.get("enabled")) is not bool:
                    raise ValueError("enabled must be boolean")
                self.streaming = values["enabled"]
            elif action == "scenario":
                if values.get("name") not in SCENARIOS:
                    raise ValueError("Unknown scenario")
                self.scenario_name = values["name"]
                self.scenario_start = timestamp
                self.streaming = True
                self.processor.arm()
            elif action in ("blink", "left_wink", "right_wink"):
                eyes = ("left", "right") if action == "blink" else (action.split("_")[0],)
                for eye in eyes:
                    duration = 120 if action == "blink" else getattr(self.processor.config, eye + "_eye").dwell_ms + 180
                    self.pulses[eye] = timestamp + duration
            elif action == "calibrate":
                sample = self.processor.sample
                if sample is None or timestamp - sample.timestamp_ms > self.processor.config.stale_ms:
                    raise ValueError("Calibration needs a fresh sample")
                config = self.processor.config
                if sample.pointer is not None:
                    config = replace(config, pointer=replace(config.pointer, center_x=sample.pointer[0], center_y=sample.pointer[1]))
                if sample.scroll is not None:
                    config = replace(config, scroll=replace(config.scroll, center_y=sample.scroll))
                self.settings({"config": config.to_dict()})
            else:
                raise ValueError("Unknown action")
            self.take_snapshot(self.clock())

    def disconnect(self, reason, *, clear_eye_history=False):
        """Release output immediately at source EOF/error/stop, before timeout."""
        with self.lock:
            self.processor.disarm(reason)
            if clear_eye_history:
                self.processor.eye_sample = None
            self.take_snapshot(self.clock())

    def ingest(self, frame):
        with self.lock:
            if self.runtime["source"] != "external":
                raise ValueError("Select external source before submitting detector frames")
            timestamp = self.clock()
            result = self._accept(frame, timestamp)
            # Show the actual latest input, including subject loss/rejected frames.
            self.last_raw = frame
            self.last_ingest = result
            if self.mapping_id != "mouse" or self.output is not None:
                self.take_snapshot(timestamp)
            return dict(result, eye_sample=self.processor.eye_sample)
