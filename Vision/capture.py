"""Explicit, synchronous OpenCV capture. No hardware is opened on import."""

from dataclasses import dataclass
import math
from time import sleep

from .signals import CaptureSession, Envelope, monotonic_ms


class CaptureError(RuntimeError):
    """A capture failure terminates the stream; it is not a no-face observation."""


@dataclass(frozen=True)
class CapturedImage:
    envelope: Envelope
    bgr: object


class OpenCVCamera:
    """One read/inference at a time; no Python inference backlog.

    The capture timestamp approximates acquisition with read-completion time.
    Driver buffering is backend-dependent even when buffer size 1 is requested.
    """

    def __init__(self, camera_id=0, *, width=640, height=480, fps=30.0,
                 clock=monotonic_ms, sleeper=sleep, cv2_module=None):
        if type(camera_id) is not int or camera_id < 0:
            raise ValueError("camera_id must be a nonnegative integer")
        if any(type(value) is not int or value <= 0 for value in (width, height)):
            raise ValueError("resolution must contain positive integers")
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
            raise ValueError("fps must be finite and positive")
        self.camera_id, self.width, self.height, self.fps = camera_id, width, height, fps
        self.clock, self.sleeper, self.cv2 = clock, sleeper, cv2_module
        self.session = CaptureSession(clock)
        self.capture = None
        self.next_due = None

    def __enter__(self):
        if self.capture is not None:
            raise CaptureError("camera is already open")
        if self.cv2 is None:
            import cv2
            self.cv2 = cv2
        try:
            self.capture = self.cv2.VideoCapture(self.camera_id)
            if not self.capture.isOpened():
                raise CaptureError(f"cannot open camera {self.camera_id}")
            for key, value in (
                (self.cv2.CAP_PROP_FRAME_WIDTH, self.width),
                (self.cv2.CAP_PROP_FRAME_HEIGHT, self.height),
                (self.cv2.CAP_PROP_FPS, self.fps),
                (self.cv2.CAP_PROP_BUFFERSIZE, 1),
            ):
                self.capture.set(key, value)  # Backend may decline these requests.
            self.session.restart()
            self.next_due = None
            return self
        except Exception:
            self.close()
            raise

    def read(self):
        if self.capture is None:
            raise CaptureError("camera must be explicitly opened first")
        try:
            if self.next_due is not None:
                delay = self.next_due - self.clock()
                if delay > 0:
                    self.sleeper(delay / 1000.0)
            ok, image = self.capture.read()
            if not ok or image is None or getattr(image, "size", 0) == 0:
                raise CaptureError("camera read failed; stream stopped")
            envelope = self.session.stamp()
            self.next_due = envelope.timestamp_ms + 1000.0 / self.fps
            return CapturedImage(envelope, image)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def __exit__(self, *exc):
        self.close()
