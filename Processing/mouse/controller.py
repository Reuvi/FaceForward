"""Native lab controller with an independent 100 Hz processing clock; no network."""

from collections import deque
from dataclasses import replace
import threading
import time

from .config import MouseConfig, number
from .engine import MouseProcessor
from .mocks import SCENARIOS, raw_frame, scenario
from .output import mouse_message


def now_ms():
    return time.monotonic() * 1000.0


class Lab:
    def __init__(self, config=None, *, clock=now_ms):
        self.lock = threading.RLock()
        self.clock = clock
        self.locked_source = None
        self.processor = MouseProcessor(config)
        self.runtime = {"sample_hz": 30, "rows": 9, "columns": 9, "vector_size": 11,
                        "pointer_speed": 900, "scroll_speed": 450, "source": "mock", "subject_id": "mock-person"}
        self.manual = {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": False, "right": False}
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
                    self.processor.accept(self.last_raw, timestamp)
                    self.sample_sequence += 1
            self.snapshot = self.processor.tick(timestamp)
            self.trace_id += 1
            snap, diag = self.snapshot, self.snapshot["diagnostics"]
            point, interpolated = diag["raw_pointer"], diag["interpolated_pointer"]
            self.trace.append({
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
                "left_raw": int(diag["left_closed"]) if diag["left_closed"] is not None else None,
                "right_raw": int(diag["right_closed"]) if diag["right_closed"] is not None else None,
                "left_out": snap["left_click"], "right_out": snap["right_click"],
                "left_dwell": diag["left_dwell"], "right_dwell": diag["right_dwell"],
            })

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
        if self.thread:
            self.thread.join(timeout=2)
        with self.lock:
            self.processor.disarm("Lab closed")
            self.snapshot = self.processor.tick(self.clock())

    def state(self, after=0):
        with self.lock:
            return {"snapshot": self.snapshot, "message": mouse_message(self.snapshot),
                    "trace": [row for row in self.trace if row["id"] > after],
                    "raw": self.last_raw, "runtime": self.runtime.copy(), "manual": self.manual.copy(),
                    "config": self.processor.config.to_dict(), "scenario": self.scenario_name,
                    "streaming": self.streaming, "generation": self.generation,
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
            self.processor = MouseProcessor(config, subject_id=runtime["subject_id"])
            self.runtime = runtime
            self.trace.clear()
            self.generation += 1
            self.last_raw = None
            self.last_ingest = None
            self.pulses = {"left": 0.0, "right": 0.0}
            self.snapshot = self.processor.tick(self.clock())
            self.next_sample = self.clock()

    def action(self, values):
        action = values.get("action")
        with self.lock:
            timestamp = self.clock()
            if action == "arm":
                self.processor.arm()
            elif action == "stop":
                self.processor.disarm()
            elif action == "center":
                self.manual.update(x=0.5, y=0.5, scroll=0.5, left=False, right=False)
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
            self.snapshot = self.processor.tick(self.clock())

    def disconnect(self, reason):
        """Release output immediately at source EOF/error/stop, before timeout."""
        with self.lock:
            self.processor.disarm(reason)
            self.snapshot = self.processor.tick(self.clock())

    def ingest(self, frame):
        with self.lock:
            if self.runtime["source"] != "external":
                raise ValueError("Select external source before submitting detector frames")
            result = self.processor.accept(frame, self.clock())
            # Show the actual latest input, including subject loss/rejected frames.
            self.last_raw = frame
            self.last_ingest = result
            return result
