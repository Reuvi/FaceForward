"""Bounded process isolation: camera/Tk only exchange references under a short lock.

Only the dispatcher does blocking IPC, process startup, joins and termination.
The child owns ONNX and temporal tip tracking. There is no camera in this process.
"""

from dataclasses import dataclass
import multiprocessing as mp
from threading import Condition, Thread
from time import monotonic


@dataclass
class TongueJob:
    session_id: str
    sequence: int
    timestamp_ms: float
    key: tuple
    path: str
    crop: object
    config: object
    face_quality: float


@dataclass
class TongueReply:
    job: TongueJob
    result: object
    report: dict


def tongue_process(connection):
    """Spawn entry point; never import App, Tk or Processing."""
    import cv2
    from .tongue_segment import SegmentedTongueModel
    cv2.setNumThreads(1)
    model = key = model_key = None
    try:
        connection.send("ready")
        while True:
            epoch, job = connection.recv()
            identity = (epoch, job.key, job.path)
            descriptor = (job.path, job.key[-1])
            if (model is None or model_key != descriptor
                    or key != identity and model.load_error is not None):
                model = SegmentedTongueModel(job.path, threads=1)
                model_key = descriptor
            if key != identity:
                model.reset_tracking()
                key = identity
            result = model.detect(job.crop, job.config, timestamp_ms=job.timestamp_ms)
            if result.xy is None:
                model.reset_tracking()
            connection.send((result, dict(model.report)))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class TongueWorker:
    """One in-flight + one replaceable pending job; latest completed reply only."""

    def __init__(self, *, target=tongue_process, timeout=10.0):
        self.target, self.timeout = target, timeout
        self.condition = Condition()
        self.thread = None
        self.process = None
        self.closed = False
        self.epoch = 0
        self.pending = self.reply = None
        self.error = None
        self.submitted = self.completed = self.replaced = 0
        self.last_completion = None
        self.hz = 0.0

    def submit(self, job):
        with self.condition:
            if self.closed or self.error:
                return
            self.submitted += 1
            self.replaced += int(self.pending is not None)
            self.pending = (self.epoch, job)
            if self.thread is None or not self.thread.is_alive():
                self.thread = Thread(target=self._run, daemon=True, name="tongue-dispatch")
                self.thread.start()
            self.condition.notify()

    def take(self):
        with self.condition:
            reply, self.reply = self.reply, None
            return reply

    def invalidate(self):
        with self.condition:
            self.epoch += 1
            self.pending = self.reply = None
            self.error = None
            self.last_completion = None
            self.hz = 0.0
            self.condition.notify()

    def state(self):
        with self.condition:
            elapsed = monotonic() - self.last_completion if self.last_completion is not None else None
            rate = self.hz if elapsed is not None and elapsed < max(1., 2.5/max(.1, self.hz)) else 0.
            return dict(hz=rate, submitted=self.submitted, completed=self.completed,
                        replaced=self.replaced, pending=int(self.pending is not None),
                        error=self.error)

    def _run(self):
        connection = child = process = None
        try:
            context = mp.get_context("spawn")
            connection, child = context.Pipe()
            process = context.Process(target=self.target, args=(child,), daemon=True,
                                      name="tongue-inference")
            process.start()
            child.close()
            with self.condition:
                self.process = process
            deadline = monotonic() + self.timeout
            while not connection.poll(.025):
                if self.closed:
                    return
                if not process.is_alive() or monotonic() >= deadline:
                    raise TimeoutError("Tongue worker startup failed or timed out; restart source to retry")
            if connection.recv() != "ready":
                raise RuntimeError("Invalid tongue worker handshake")
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.pending is not None)
                    if self.closed:
                        return
                    epoch, job = self.pending
                    self.pending = None
                connection.send((epoch, job))
                deadline = monotonic() + self.timeout
                while not connection.poll(.025):
                    if self.closed:
                        return
                    if not process.is_alive():
                        raise RuntimeError("Tongue worker exited")
                    if monotonic() >= deadline:
                        raise TimeoutError("Tongue worker timed out; restart source to retry")
                result, report = connection.recv()
                with self.condition:
                    if epoch == self.epoch and not self.closed:
                        self.completed += 1
                        completed = monotonic()
                        if self.last_completion is not None and completed > self.last_completion:
                            self.hz = 1 / (completed - self.last_completion)
                        self.last_completion = completed
                        self.reply = TongueReply(job, result, report)
        except Exception as exc:
            with self.condition:
                if not self.closed:
                    self.error = str(exc) or type(exc).__name__
                    self.pending = self.reply = None
        finally:
            if connection is not None:
                connection.close()
            if child is not None:
                child.close()
            if process is not None and process.pid is not None:
                # Runs on dispatcher, outside every camera/UI/session lock.
                if process.is_alive():
                    process.terminate()
                process.join(timeout=.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=.5)

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = self.reply = None
            self.condition.notify()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive() and self.process is not None and self.process.is_alive():
                self.process.terminate()
                self.thread.join(timeout=.5)
