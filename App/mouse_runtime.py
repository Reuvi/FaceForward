"""In-process Vision → Processing composition; one producer, no frame queue."""

from collections import deque
from dataclasses import asdict
import threading
import time

from Processing.mouse.controller import Lab
from Vision.mouse_demo import SUBJECT, mouse_demo_records
from Vision.signals import monotonic_ms, validate_frame
from Vision.sources import read_ndjson, replay


class SourceStopped(Exception):
    pass


class MouseSession:
    """App owns producer lifecycle; Lab owns the independent processing clock.

    All state locks are acquired session → lab. Frames/diagnostics handed to this
    class must not be mutated afterwards. Preview retains one PPM image in memory.
    Live camera measurements remain invalid without Vision calibration/quality.
    """

    def __init__(self, lab=None, *, clock=monotonic_ms):
        self.clock = clock
        self.lab = lab or Lab(clock=clock)
        self.lab.settings({"runtime": {"source": "external", "subject_id": SUBJECT}})
        self.lab.locked_source = "external"
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.frame = None
        self.observations = {}
        self.preview = None
        self.preview_id = 0
        self.times = deque(maxlen=60)
        self.mode = "demo"
        self.status = "Source stopped"
        self.error = None
        self.received = self.accepted = 0
        self.received_at = None
        self.inference_ms = None
        self.generation = 0
        self.closed = False

    def select_subject(self, subject_id):
        with self.lock:
            available = {face["subject_id"] for face in (self.frame or {}).get("faces", [])}
            if subject_id not in available:
                raise ValueError("Select a subject present in the latest Vision frame")
            self.lab.settings({"runtime": {"subject_id": subject_id}})

    def deliver(self, frame, *, observations=None, preview=None, inference_ms=None):
        """Synchronous public handoff, also usable with injected clocks in tests."""
        with self.lock:
            if self.closed:
                raise RuntimeError("Session is closed")
            try:
                validate_frame(frame)
            except (ValueError, TypeError) as exc:
                self.lab.disconnect("Invalid Vision frame")
                self.error = str(exc)
                raise
            self.frame = frame
            self.observations = observations or {}
            self.received_at = self.clock()
            self.times.append(self.received_at)
            self.inference_ms = inference_ms
            self.received += 1
            if preview is not None:
                self.preview = preview
                self.preview_id += 1
            result = self.lab.ingest(frame)
            self.accepted += int(result["accepted"])
            return result

    def state(self):
        with self.lock:
            span = self.times[-1] - self.times[0] if len(self.times) > 1 else 0
            age = self.clock() - self.received_at if self.received_at is not None else None
            running = self.thread is not None and self.thread.is_alive() and not self.stop_event.is_set()
            return {"mode": self.mode, "status": self.status, "error": self.error,
                    "running": running, "generation": self.generation,
                    "frame": self.frame, "observations": self.observations,
                    "preview": self.preview, "preview_id": self.preview_id,
                    "received": self.received, "accepted": self.accepted,
                    "age_ms": age, "inference_ms": self.inference_ms,
                    "actual_hz": (len(self.times) - 1) * 1000 / span if span > 0 else 0}

    def start(self, mode="demo", *, path=None, fps=30, camera_id=0, model=None,
              preview=True, count=None):
        if mode not in ("demo", "replay", "camera"):
            raise ValueError("source must be demo, replay, or camera")
        if mode == "replay" and not path:
            raise ValueError("Choose a SignalFrame NDJSON replay file")
        if mode == "camera" and not model:
            raise ValueError("Choose the local face_landmarker.task model")
        # Validate options before starting any thread or camera.
        if type(fps) not in (int, float) or not 1 <= fps <= 120:
            raise ValueError("source FPS must be between 1 and 120")
        if count is not None and (type(count) is not int or count < 1):
            raise ValueError("frame count must be a positive integer")
        if type(camera_id) is not int or camera_id < 0:
            raise ValueError("camera ID must be a nonnegative integer")
        with self.lock:
            if self.closed:
                raise RuntimeError("Session is closed")
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Stop the current source and wait for it to close before restarting")
            self.stop_event.clear()
            self.mode, self.status, self.error = mode, "Starting " + mode, None
            self.frame, self.preview, self.observations = None, None, {}
            self.received = self.accepted = 0
            self.received_at = self.inference_ms = None
            self.times.clear()
            self.generation += 1
            subject = SUBJECT if mode == "demo" else "select-a-subject"
            self.lab.settings({"runtime": {"source": "external", "subject_id": subject}})
            self.thread = threading.Thread(
                target=self._run, args=(mode, path, fps, camera_id, model, preview, count),
                name="vision-source", daemon=True,
            )
            self.thread.start()

    def _wait(self, seconds):
        if self.stop_event.wait(seconds):
            raise SourceStopped()

    def _run(self, mode, path, fps, camera_id, model, preview, count):
        reason = "Vision source ended"
        try:
            with self.lock:
                self.status = "Synthetic Vision demo" if mode == "demo" else "Vision " + mode
            if mode == "camera":
                self._camera(camera_id, model, fps, preview, count)
            else:
                records = mouse_demo_records(count=count, fps=fps) if mode == "demo" else read_ndjson(path)
                for index, frame in enumerate(replay(records, clock=self.clock, sleeper=self._wait)):
                    with self.lock:
                        if self.stop_event.is_set():
                            raise SourceStopped()
                        self.deliver(frame)
                    if count is not None and index + 1 >= count:
                        break
        except SourceStopped:
            reason = "Vision source stopped"
        except Exception as exc:
            reason = "Vision source error: " + str(exc)
            with self.lock:
                self.error = str(exc)
        finally:
            with self.lock:
                if self.stop_event.is_set():
                    reason = "Vision source stopped"
                self.status = reason
                self.lab.disconnect(reason)

    def _camera(self, camera_id, model, fps, preview, count):
        # Optional dependencies are imported only for explicit camera mode.
        from Vision.capture import OpenCVCamera
        from Vision.landmarks import MediaPipeDetector
        from Vision.overlay import render_overlay
        from Vision.pipeline import VisionPipeline

        pipeline = VisionPipeline()
        last_preview = float("-inf")
        index = 0
        # Validate/load the model before acquiring the camera.
        with MediaPipeDetector(model) as detector, OpenCVCamera(camera_id, fps=fps, clock=self.clock) as camera:
            while not self.stop_event.is_set() and (count is None or index < count):
                captured = camera.read()
                started = time.perf_counter()
                observations = detector.detect(captured)
                frame = pipeline.process(captured, observations)
                inference_ms = (time.perf_counter() - started) * 1000
                raw = {
                    face["subject_id"]: {
                        "eyes": {name: asdict(ratios) for name, ratios in observation.eyes.items()},
                        "head_reference": asdict(observation.head_reference) if observation.head_reference else None,
                        "box": asdict(observation.box),
                    }
                    for face, observation in zip(frame["faces"], observations)
                }
                ppm = None
                now = self.clock()
                if preview and now - last_preview >= 100:
                    import cv2
                    image = render_overlay(captured.bgr, observations, frame,
                                           caption="Uncalibrated camera diagnostics")
                    image = cv2.resize(image, (480, 360))
                    ok, encoded = cv2.imencode(".ppm", image)
                    if ok:
                        ppm = encoded.tobytes()
                    last_preview = now
                with self.lock:
                    if self.stop_event.is_set():
                        raise SourceStopped()
                    self.deliver(frame, observations=raw, preview=ppm, inference_ms=inference_ms)
                index += 1

    def stop(self):
        with self.lock:
            self.stop_event.set()
            self.status = "Stopping Vision source" if self.thread and self.thread.is_alive() else "Vision source stopped"
            self.lab.disconnect("Vision source stopped")

    def close(self):
        if self.closed:
            return
        self.stop()
        if self.thread is not None:
            self.thread.join(timeout=2)
        with self.lock:
            self.closed = True
            self.preview = None
        self.lab.close()
