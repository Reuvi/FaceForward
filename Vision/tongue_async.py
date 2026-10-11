"""Associate independent tongue results with their original camera evidence."""

from .tongue import TongueResult
from .tongue_worker import TongueJob, TongueWorker


class AsyncTongue:
    def __init__(self, worker=None):
        self.worker = worker or TongueWorker()
        self.key = None
        self.latest = None
        self.new = False
        self.crop = None

    def invalidate(self):
        self.worker.invalidate()
        self.key = self.latest = self.crop = None
        self.new = False

    def update(self, frame, crop, quality, model, config, generation, now):
        key = (frame["session_id"], generation, id(model))
        if self.key != key:
            self.invalidate()
            self.key = key
            model.report.update(confidence=None, inference_ms=None, error=None)
        self.new = False
        self.crop = None
        if crop is None or quality <= 0:
            self.invalidate()
            return TongueResult(reason="Current mouth/face unavailable")
        reply = self.worker.take()
        if (reply is not None and reply.job.key == key
                and reply.job.session_id == frame["session_id"]
                and reply.job.sequence <= frame["sequence"]
                and reply.job.timestamp_ms <= frame["timestamp_ms"]
                and (self.latest is None or reply.job.sequence > self.latest.job.sequence)):
            model.report.update(reply.report)
            self.latest = reply
            self.new = 0 <= now - reply.job.timestamp_ms <= config.stale_ms
        self.worker.submit(TongueJob(frame["session_id"], frame["sequence"], frame["timestamp_ms"],
                                    key, str(model.path), crop, config, quality))
        error = self.worker.state()["error"]
        if error:
            model.report.update(error=error)
            return TongueResult(reason=error)
        if self.latest is None:
            return TongueResult(reason="Waiting for independent tongue worker")
        if not 0 <= now - self.latest.job.timestamp_ms <= config.stale_ms:
            return TongueResult(reason="Tongue result stale; other inputs continue")
        self.crop = self.latest.job.crop
        return self.latest.result

    def sample(self, frame, subject):
        job = self.latest.job if self.latest else None
        return dict(format="tongue_sample_v1", session_id=frame["session_id"], subject_id=subject,
                    sequence=job.sequence if job else None, timestamp_ms=job.timestamp_ms if job else None)

    def state(self, now):
        job = self.latest.job if self.latest else None
        return dict(self.worker.state(), new=self.new,
                    timestamp_ms=job.timestamp_ms if job else None,
                    sequence=job.sequence if job else None,
                    age_ms=now-job.timestamp_ms if job else None)
