"""One camera/inference worker and one latest snapshot; no frame queue or UI calls."""

from contextlib import ExitStack
from copy import deepcopy
import csv
from pathlib import Path
from threading import Event, RLock, Thread
from time import perf_counter

import cv2

from .capture import CapturedImage, OpenCVCamera
from .demo_detection import demo_image
from .landmarks import MediaPipeDetector
from .signals import CaptureSession, monotonic_ms
from .workbench import DetectorWorkbench


class LabRuntime:
    def __init__(self, config=None, *, clock=monotonic_ms, lock=None):
        self.clock = clock
        self.lock = lock if lock is not None else RLock()
        self.workbench = DetectorWorkbench(config, clock=clock)
        self.previous_timestamp = None
        self.stop_event = Event()
        self.worker = None
        self.source = "Stopped"
        self.preview = None
        self.demo_controls = {}
        self.timing = {}
        self.preview_due = 0
        self.source_kind = None

    def start(self, *, demo=False, model=None, camera_id=0, fps=30):
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ValueError("Stop the running source before starting another")
            kind = "synthetic" if demo else "camera"
            if self.source_kind is not None and self.source_kind != kind:
                self.workbench.reset_calibration()
            self.source_kind = kind
            self.workbench.disconnect("Starting source; calibration retained. Waiting for the face.")
            self.workbench.validation.clear()
            self.preview = None
            self.timing = {}
            self.preview_due = 0
            self.stop_event.clear()
            self.source = "SYNTHETIC pixels + landmarks (no ML)" if demo else "Local camera / MediaPipe CPU"
            self.worker = Thread(target=self._run, args=(demo, model, camera_id, fps), daemon=True, name="vision-lab")
            self.worker.start()

    def _run(self, demo, model, camera_id, fps):
        try:
            with ExitStack() as stack:
                if demo:
                    session = CaptureSession()
                else:
                    detector = stack.enter_context(MediaPipeDetector(model, include_pose=True, include_expressions=True))
                    camera = stack.enter_context(OpenCVCamera(camera_id, fps=fps))
                self.previous_timestamp = None
                while not self.stop_event.is_set():
                    started = perf_counter()
                    if demo:
                        with self.lock:
                            controls = self.demo_input()
                        bgr, observations = demo_image(**controls)
                        captured = CapturedImage(session.stamp(), bgr)
                        inference_ms = 0
                    else:
                        captured = camera.read()
                        inference_start = perf_counter()
                        observations = detector.detect(captured)
                        inference_ms = (perf_counter() - inference_start) * 1000
                    with self.lock:
                        if self.stop_event.is_set():
                            break
                        self.ingest(captured, observations, inference_ms=inference_ms)
                    if demo:
                        self.stop_event.wait(max(0, 1/fps - (perf_counter()-started)))
        except Exception as exc:
            with self.lock:
                self.workbench.disconnect(f"Source failed: {exc}")
                self.source = "Error — " + str(exc)
        finally:
            with self.lock:
                self.preview = None
                if not self.source.startswith("Error"):
                    self.source = "Stopped"
                    self.workbench.disconnect()

    def demo_input(self):
        """Automatic developer fixture; camera inputs never pass through this path."""
        with self.lock:
            guide = self.workbench.eye_guide
            controls = dict(self.demo_controls)  # Available to developer scripts only.
            if guide and guide.active:
                state=guide.state(self.clock())
                if state.get("wink_training"):
                    controls.update(left_closed=False,right_closed=False,natural_blink=False)
                    if state["phase"]=="capture":
                        elapsed=self.clock()-state["capture_start_ms"]
                        duration=state["capture_end_ms"]-state["capture_start_ms"]
                        if state["name"]=="blinks":
                            controls["natural_blink"] = .2 <= (elapsed/(duration/4))%1 < .45
                        elif state["name"] in ("left","right"):
                            controls[state["name"]+"_closed"] = .2<=elapsed/duration<.75
                else:
                    ratio = .25 if state["resting"] else {"center": .25, "left": .21, "right": .22, "up": .28,
                             "down": .14, "closed": .04, "reopen": .25}[guide.step[0]]
                    controls.update(left_ratio=ratio, right_ratio=ratio*.94)
            elif guide and not controls:
                # Independent holds and simultaneous closure exercise the two scopes.
                phase = (self.clock()/1000) % 8
                controls.update(left_closed=2 <= phase < 3 or 6 <= phase < 7,
                                right_closed=4 <= phase < 5 or 6 <= phase < 7)
            return controls

    def ingest(self, captured, observations, *, inference_ms=0, preview=True):
        """Externally driven path: process one capture without starting a worker."""
        with self.lock:
            observations = list(observations)
            started = perf_counter()
            frame = self.workbench.process(captured, observations)
            timestamp = frame["timestamp_ms"]
            previous = self.previous_timestamp
            self.timing = {
                "sample_hz": 1000/(timestamp-previous) if previous is not None and timestamp > previous else 0,
                "inference_ms": inference_ms,
                "features_ms": (perf_counter()-started)*1000,
                "age_ms": self.clock()-timestamp,
            }
            self.previous_timestamp = timestamp
            if preview and self.clock() >= self.preview_due:
                self.preview = self._preview(captured.bgr, observations, frame)
                self.preview_due = self.clock() + 100
            return frame

    def _preview(self, bgr, observations, frame):
        image = bgr.copy()
        h, w = image.shape[:2]
        for face, obs in zip(frame["faces"], observations):
            selected = face["subject_id"] == self.workbench.selected
            color = (80, 230, 120) if selected else (0, 180, 255)
            box = obs.box
            a = (int(box.x*w), int(box.y*h))
            b = (int((box.x+box.width)*w), int((box.y+box.height)*h))
            cv2.rectangle(image, a, b, color, 2)
            cv2.putText(image, face["subject_id"], (a[0], max(15,a[1]-5)), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
            for index in (13, 14, 61, 291, 168, 263, 362, 133, 33):
                if index < len(obs.points):
                    cv2.circle(image, tuple(round(v) for v in obs.points[index]), 2, color, -1)
        core = self.workbench
        if core.crop is not None and core.tongue.xy is not None:
            cv2.circle(image, tuple(round(v) for v in core.crop.image_point(core.tongue.xy)), 4, (255, 255, 0), -1)
        cv2.putText(image, "Unmirrored | user's LEFT is image RIGHT", (8, h-12), cv2.FONT_HERSHEY_SIMPLEX, .48, (245,245,245), 1)
        return cv2.resize(image, (640, 480))

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self.workbench.disconnect("Stopping source; calibration retained")
            self.preview = None
        # Do not block Tk on a slow backend. start() rejects a still-running worker.

    def close(self):
        self.stop()
        if self.worker is not None:
            self.worker.join(timeout=2)

    def command(self, name, *args):
        with self.lock:
            return getattr(self.workbench, name)(*args)

    def snapshot(self):
        with self.lock:
            state = deepcopy(self.workbench.state())
            rows=[]
            # Include at most one older seed per plotted channel. A long unknown
            # interval can then retain its last display height after that capture
            # leaves the 8-second view, without sending the full history to Tk.
            needed = {"left_raw", "right_raw", "head_raw", "left_closed_bit", "right_closed_bit",
                      "head_y", "tongue_x", "tongue_y", "left_wink_bit", "right_wink_bit"}
            needed.update(side+"_"+key for side in ("left","right")
                          for key in ("blink","squint","cheek","brow","wink_score"))
            cutoff = self.workbench.trace[-1]["timestamp_ms"]-8000 if self.workbench.trace else 0
            scope_subject = state.get("scope_subject", state["selected"])
            for row in reversed(self.workbench.trace):
                in_view = row["timestamp_ms"] >= cutoff
                matching = (scope_subject and row["subject_id"] == scope_subject
                            and row["calibration_generation"] == state["generation"])
                if not in_view and (not needed or not matching):
                    break
                available = {key for key in needed if matching and row.get(key) is not None
                             and (not key.endswith("_raw") or row.get(key[:-4]+"_quality", 0) > 0)}
                if in_view or available:
                    rows.append(row)
                if not in_view:
                    needed -= available
            state.update(source=self.source, timing=dict(self.timing), preview=self.preview,
                         trace=list(reversed(rows)))
            crop = self.workbench.frozen_crop or self.workbench.crop
            state["mouth"] = crop.bgr.copy() if crop else None
            state["frozen"] = self.workbench.frozen_crop is not None
            if crop and not state["frozen"] and self.workbench.tongue.mask is not None:
                mask = self.workbench.tongue.mask > 0
                state["mouth"][mask] = (state["mouth"][mask]*.4 + (0,150,0)).astype("uint8")
            state["candidate"] = self.workbench.tongue.xy
            return state

    def export_trace(self, path):
        with self.lock:
            rows = list(self.workbench.trace)
        if not rows:
            raise ValueError("No samples recorded yet")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)
