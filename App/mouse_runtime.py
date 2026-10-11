"""In-process Vision → Processing composition; one producer, no frame queue."""

from collections import deque
from dataclasses import asdict
from pathlib import Path
import threading
import time

from Processing.mouse.controller import Lab
from Vision.mouse_demo import SUBJECT, mouse_demo_records
from Vision.signals import SINGLE_SUBJECT, monotonic_ms, validate_frame
from Vision.sources import read_ndjson, replay


class SourceStopped(Exception):
    pass


class MouseSession:
    """App owns producer lifecycle; Lab owns the independent processing clock.

    All state locks are acquired session → lab. Frames/diagnostics handed to this
    class must not be mutated afterwards. Preview retains one PPM image in memory.
    Camera and detector-demo share one selected-face calibration workbench.
    Uncalibrated channels remain invalid; native output is an explicit mode.
    """

    def __init__(self, lab=None, *, clock=monotonic_ms):
        self.clock = clock
        self.lab = lab or Lab(clock=clock)
        self.lab.locked_pointer_source = "gaze"
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
        self.detector_runtime = None
        self.profile_label = "Unsaved calibration"
        self.profile_binding = None
        self.diagnostics = None

    def configure_output(self, mode="preview", library=None):
        with self.lock:
            if self.closed:
                raise ValueError("Session is closed")
            if mode not in ("preview", "dry-run", "native"):
                raise ValueError("Choose preview, dry-run or native output")
            if mode == "native" and self.mode != "camera":
                raise ValueError("Live mouse/keyboard output requires the Camera source")
            self.lab.set_output(None)
            if mode != "preview":
                from Drivers.output import DriverOutput
                output = DriverOutput(mode, library, clock=self.clock)
                try:
                    self.lab.set_output(output)
                except Exception:
                    output.close()
                    raise

    def select_subject(self, subject_id):
        with self.lock:
            available = {face["subject_id"] for face in (self.frame or {}).get("faces", [])}
            if subject_id not in available:
                raise ValueError("Select a subject present in the latest Vision frame")
            if self.mode in ("camera", "detector-demo"):
                self.ensure_detector_runtime().command("select", subject_id)
                return  # Already attached automatically; preserve the user's fits.
            self.lab.settings({"runtime": {"subject_id": subject_id}})

    def ensure_detector_runtime(self):
        """Lazily load optional image dependencies, with the session's single lock."""
        with self.lock:
            if self.detector_runtime is None:
                from Vision.lab_runtime import LabRuntime
                self.detector_runtime = LabRuntime(clock=self.clock, lock=self.lock)
            return self.detector_runtime

    def detector_command(self, name, *args):
        allowed = {"start_eye_guide", "start_wink_guide", "present_eye_step",
                   "start_movement_guide", "present_movement_step", "reset_head_x",
                   "redo_head_y_step", "retry_movement_step", "collect", "cancel", "configure", "reset_calibration"}
        if name not in allowed:
            raise ValueError("Unsupported calibration command")
        with self.lock:
            if self.mode not in ("camera", "detector-demo"):
                raise ValueError("Choose Camera or Detector demo on Signals first")
            runtime = self.ensure_detector_runtime()
            self.lab.disconnect("Calibration changed; start preview again when ready",
                                clear_eye_history=name in ("start_eye_guide", "start_wink_guide", "configure", "collect", "reset_calibration"))
            result = runtime.command(name, *args)
            if name not in ("cancel", "present_eye_step", "present_movement_step"):
                self.profile_label = "Modified calibration — save profile to keep it"
                self.profile_binding = None
            return result

    def detector_state(self):
        with self.lock:
            runtime = self.ensure_detector_runtime()
            self._expire_detector()
            state = runtime.snapshot()
            if self.mode not in ("camera", "detector-demo"):
                state["notice"] = "Choose Camera or Detector demo on Signals to calibrate"
            if state["selected"] is None and self.mode in ("camera", "detector-demo"):
                self.lab.disconnect("Waiting for the single user's face; calibration retained")
            state["source"] = self.status
            return state

    def deliver_detection(self, captured, observations, *, inference_ms=0, preview=True):
        """One captured image feeds both calibration diagnostics and Processing."""
        with self.lock:
            observations = list(observations)
            runtime = self.ensure_detector_runtime()
            core = runtime.workbench
            previous_session, collecting = core.session, core.calibrating
            previous_timestamp = core.frame["timestamp_ms"] if core.frame else None
            previous_preview = runtime.preview
            try:
                frame = runtime.ingest(captured, observations, inference_ms=inference_ms, preview=preview)
            except Exception:
                self.lab.disconnect("Invalid detector capture; calibration retained")
                raise
            with self.lab.lock:
                if self.lab.runtime["subject_id"] != SINGLE_SUBJECT:
                    self.lab.settings({"runtime": {"subject_id": SINGLE_SUBJECT}})
            if previous_session is not None and previous_session != core.session:
                self.lab.disconnect("Camera restarted; calibration retained")
            elif previous_timestamp is not None and frame["timestamp_ms"] - previous_timestamp > core.config.stale_ms:
                self.lab.disconnect("Capture gap; calibration retained")
            if collecting or core.calibrating or core.selected is None:
                self.lab.disconnect("Preview paused: calibrating or face unavailable; calibration retained")
            raw = {
                face["subject_id"]: {
                    "eyes": {name: asdict(ratios) for name, ratios in observation.eyes.items()},
                    "head_reference": asdict(observation.head_reference) if observation.head_reference else None,
                    "box": asdict(observation.box),
                }
                for face, observation in zip(frame["faces"], observations)
            }
            ppm = None
            if preview and runtime.preview is not None and runtime.preview is not previous_preview:
                import cv2
                ok, encoded = cv2.imencode(".ppm", cv2.resize(runtime.preview, (480, 360)))
                if ok:
                    ppm = encoded.tobytes()
            forwarded = dict(frame, diagnostic_only=False)
            self.deliver(forwarded, observations=raw, preview=ppm, inference_ms=inference_ms)
            return forwarded

    def save_profile(self, path):
        from Processing.mouse.profiles import FORMAT_V3, write_profile
        with self.lock:
            if self.mode not in ("camera", "detector-demo"):
                raise ValueError("Profiles require Camera or Detector demo calibration")
            core = self.ensure_detector_runtime().workbench
            self._expire_detector()
            detector = core.export_calibration()
            state = self.lab.state()
            data = {"format": FORMAT_V3, "source_kind": "camera" if self.mode == "camera" else "synthetic",
                    "detector": detector, "processing": state["config"],
                    "preview": {key: state["runtime"][key] for key in ("pointer_speed", "scroll_speed")}}
            write_profile(path, data)
            self.profile_label = Path(path).name
            self.profile_binding = (self.mode, core.generation)

    def load_profile(self, path):
        data = self.read_profile(path)
        with self.lock:
            kind = "camera" if self.mode == "camera" else "synthetic" if self.mode == "detector-demo" else None
            if data["source_kind"] != kind:
                raise ValueError("Profile source does not match. Camera and synthetic profiles are separate.")
            core = self.ensure_detector_runtime().workbench
            self._expire_detector()
            # Validate fully and require idle collection; loading needs no face.
            core.load_calibration(data["detector"])
            self.lab.settings({"config": data["processing"],
                               "runtime": dict(data["preview"], subject_id=SINGLE_SUBJECT, source="external")})
            self.profile_label = Path(path).name
            self.profile_binding = (self.mode, core.generation)

    @staticmethod
    def read_profile(path):
        """Validate before the UI stops or changes an existing source."""
        from Processing.mouse.profiles import read_profile
        from Vision.presets import decode_preset
        data = read_profile(path)
        decode_preset(data["detector"])
        if "research" in data:
            from .research_runtime import validate_profile
            validate_profile(data["research"])
        return data

    def prepare_source(self, mode):
        """Select an idle source without opening hardware; supports paused loading."""
        if mode not in ("demo", "replay", "camera", "detector-demo"):
            raise ValueError("source must be demo, replay, camera, or detector-demo")
        with self.lock:
            if self.closed:
                raise ValueError("Session is closed")
            if self.thread is not None and self.thread.is_alive():
                raise ValueError("Wait for the current source to close before switching")
            if mode == self.mode:
                return
            if mode in ("camera", "detector-demo"):
                self.ensure_detector_runtime()
            if mode != "camera" and self.lab.state()["output"]["mode"] == "native":
                self.lab.set_output(None)
            if self.detector_runtime is not None:
                self.detector_runtime.workbench.reset_calibration()
            self.mode, self.status, self.error = mode, "Source stopped", None
            self.frame, self.preview, self.observations = None, None, {}
            self.received = self.accepted = 0
            self.received_at = self.inference_ms = None
            self.times.clear()
            self.profile_binding, self.profile_label = None, "Unsaved calibration"
            self.generation += 1
            subject = SINGLE_SUBJECT if mode in ("camera", "detector-demo") else SUBJECT if mode == "demo" else "select-a-subject"
            self.lab.settings({"runtime": {"source": "external", "subject_id": subject}})

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

    def _expire_detector(self):
        if self.mode in ("camera", "detector-demo") and self.detector_runtime is not None:
            core = self.detector_runtime.workbench
            selected = core.selected
            core.expire()
            if selected is not None and core.selected is None:
                self.lab.disconnect("Detector input stale; calibration retained")
                if core.frame is not None:
                    self.frame = dict(core.frame, diagnostic_only=False)

    def state(self, *, include_detector=False):
        with self.lock:
            self._expire_detector()
            span = self.times[-1] - self.times[0] if len(self.times) > 1 else 0
            age = self.clock() - self.frame["timestamp_ms"] if self.frame is not None else None
            running = self.thread is not None and self.thread.is_alive() and not self.stop_event.is_set()
            detector=(self.detector_state() if include_detector and self.detector_runtime is not None
                      and self.mode in ("camera","detector-demo") else None)
            # Calibration mutations can invalidate an output between captures.
            # Use the same snapshot for the setup table and raw plots.
            frame=dict(detector["frame"],diagnostic_only=False) if detector and detector["frame"] else self.frame
            return {"mode": self.mode, "status": self.status, "error": self.error,
                    "running": running, "generation": self.generation,
                    "frame": frame, "observations": self.observations, "detector": detector,
                    "preview": self.preview, "preview_id": self.preview_id,
                    "received": self.received, "accepted": self.accepted,
                    "age_ms": age, "inference_ms": self.inference_ms,
                    "profile_label": self.profile_label,
                    "profile_bound": self._profile_bound(),
                    "actual_hz": (len(self.times) - 1) * 1000 / span if span > 0 else 0}

    def _profile_bound(self):
        if self.detector_runtime is None:
            return False
        core = self.detector_runtime.workbench
        return self.profile_binding == (self.mode, core.generation)

    def start(self, mode="demo", *, path=None, fps=30, camera_id=0, model=None,
              preview=True, count=None):
        if mode not in ("demo", "replay", "camera", "detector-demo"):
            raise ValueError("source must be demo, replay, camera, or detector-demo")
        if mode == "replay" and not path:
            raise ValueError("Choose a SignalFrame NDJSON replay file")
        if mode == "camera" and not model:
            raise ValueError("Choose the local face_landmarker.task model")
        if mode == "camera" and not Path(model).expanduser().is_file():
            raise ValueError(f"Camera model not found: {model}. Choose face_landmarker.task in Camera settings.")
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
            if mode in ("camera", "detector-demo"):
                self.ensure_detector_runtime()
            self.prepare_source(mode)
            if self.detector_runtime is not None:
                core = self.detector_runtime.workbench
                core.disconnect("Source starting; calibration retained. Waiting for the face.")
                self.detector_runtime.preview = None
                self.detector_runtime.preview_due = 0
                self.detector_runtime.previous_timestamp = None
            self.stop_event.clear()
            self.mode, self.status, self.error = mode, "Starting " + mode, None
            self.frame, self.preview, self.observations = None, None, {}
            self.received = self.accepted = 0
            self.received_at = self.inference_ms = None
            self.times.clear()
            self.generation += 1
            subject = SINGLE_SUBJECT if mode in ("camera", "detector-demo") else SUBJECT if mode == "demo" else "select-a-subject"
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
            elif mode == "detector-demo":
                self._detector_demo(fps, preview, count)
            else:
                records = mouse_demo_records(count=count, fps=fps) if mode == "demo" else read_ndjson(path)
                for index, frame in enumerate(replay(records, clock=self.clock, sleeper=self._wait)):
                    with self.lock:
                        if self.stop_event.is_set():
                            raise SourceStopped()
                        if mode == "demo" and self.lab.mapping_id != "mouse":
                            from Processing.mappings.demo import gaming_demo_frame
                            frame = gaming_demo_frame(frame, fps)
                        self.deliver(frame)
                    if count is not None and index + 1 >= count:
                        break
        except SourceStopped:
            reason = "Vision source stopped"
        except Exception as exc:
            detail = str(exc)
            if isinstance(exc, ImportError):
                detail += ". Launch with Vision/.venv/bin/python after installing Vision/requirements.txt."
            elif mode == "camera" and "camera" in detail.lower():
                detail += ". Check camera permissions for the launching app, close other camera apps, and check Camera ID in Camera settings."
            reason = "Vision source error: " + detail
            with self.lock:
                self.error = detail
        finally:
            with self.lock:
                if self.stop_event.is_set():
                    reason = "Vision source stopped"
                self.status = reason
                self.lab.disconnect(reason)
                if self.detector_runtime is not None:
                    self.detector_runtime.workbench.disconnect(reason)
                    self.detector_runtime.preview = None

    def _camera(self, camera_id, model, fps, preview, count):
        from Vision.capture import OpenCVCamera
        from Vision.landmarks import LAB_TRACKING_CONFIDENCE, MediaPipeDetector
        self.ensure_detector_runtime()
        index = 0
        self.detector_runtime.tracker_floors = dict(face_presence_floor=LAB_TRACKING_CONFIDENCE,
                                                   face_tracking_floor=LAB_TRACKING_CONFIDENCE)
        with MediaPipeDetector(
                model, include_pose=True, include_expressions=True,
                min_face_presence_confidence=LAB_TRACKING_CONFIDENCE,
                min_tracking_confidence=LAB_TRACKING_CONFIDENCE
        ) as detector, OpenCVCamera(camera_id, fps=fps, clock=self.clock) as camera:
            while not self.stop_event.is_set() and (count is None or index < count):
                captured = camera.read()
                started = time.perf_counter()
                observations = detector.detect(captured)
                inference_ms = (time.perf_counter() - started) * 1000
                with self.lock:
                    if self.stop_event.is_set():
                        raise SourceStopped()
                    self.deliver_detection(captured, observations, inference_ms=inference_ms, preview=preview)
                    self.status = "Camera running"
                index += 1

    def _detector_demo(self, fps, preview, count):
        from Vision.capture import CapturedImage
        from Vision.demo_detection import demo_image
        from Vision.signals import CaptureSession
        runtime = self.ensure_detector_runtime()
        runtime.tracker_floors = {}
        session = CaptureSession(self.clock)
        index = 0
        while not self.stop_event.is_set() and (count is None or index < count):
            started = time.perf_counter()
            with self.lock:
                controls = runtime.demo_input()
            bgr, observations = demo_image(**controls)
            captured = CapturedImage(session.stamp(), bgr)
            with self.lock:
                if self.stop_event.is_set():
                    raise SourceStopped()
                self.deliver_detection(captured, observations, preview=preview)
            index += 1
            self._wait(max(0, 1/fps-(time.perf_counter()-started)))

    def stop(self):
        with self.lock:
            self.stop_event.set()
            self.status = "Stopping Vision source" if self.thread and self.thread.is_alive() else "Vision source stopped"
            self.lab.disconnect("Vision source stopped")
            if self.detector_runtime is not None:
                self.detector_runtime.workbench.disconnect("Source stopped; calibration retained")
                self.detector_runtime.preview = None

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
        if self.detector_runtime is not None:
            self.detector_runtime.close()
