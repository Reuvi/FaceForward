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
    def __init__(self, config=None):
        self.lock = RLock()
        self.workbench = DetectorWorkbench(config)
        self.stop_event = Event()
        self.worker = None
        self.source = "Stopped"
        self.preview = None
        self.demo_controls = {}
        self.timing = {}
        self.preview_due = 0

    def start(self, *, demo=False, model=None, camera_id=0, fps=30):
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ValueError("Stop the running source before starting another")
            self.workbench.disconnect("Starting source; select a subject when visible")
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
                    detector = stack.enter_context(MediaPipeDetector(model, include_pose=True))
                    camera = stack.enter_context(OpenCVCamera(camera_id, fps=fps))
                previous = None
                while not self.stop_event.is_set():
                    started = perf_counter()
                    if demo:
                        with self.lock:
                            controls = dict(self.demo_controls)
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
                        processing_start = perf_counter()
                        frame = self.workbench.process(captured, observations)
                        self.timing = {
                            "sample_hz": 1000 / (frame["timestamp_ms"] - previous) if previous is not None and frame["timestamp_ms"] > previous else 0,
                            "inference_ms": inference_ms,
                            "features_ms": (perf_counter()-processing_start)*1000,
                            "age_ms": monotonic_ms()-frame["timestamp_ms"],
                        }
                        previous = frame["timestamp_ms"]
                        if monotonic_ms() >= self.preview_due:
                            self.preview = self._preview(captured.bgr, observations, frame)
                            self.preview_due = monotonic_ms() + 100  # 10 Hz drawing; sampling is separate.
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
            self.workbench.disconnect("Stopping source; all calibration cleared")
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
            state.update(source=self.source, timing=dict(self.timing), preview=self.preview,
                         trace=list(self.workbench.trace)[-180:])
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
