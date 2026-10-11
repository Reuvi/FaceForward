"""Isolation and lifecycle checks with a deliberately blocked model process."""
from functools import partial
import importlib.util
import multiprocessing as mp
import os
import time
import unittest

AVAILABLE = all(importlib.util.find_spec(k) for k in ("cv2", "numpy"))
if AVAILABLE:
    from Vision.tongue_worker import TongueJob, TongueWorker


def blocked_backend(connection, entered, release):
    from Vision.tongue import TongueResult
    connection.send("ready")
    try:
        while True:
            _, job = connection.recv()
            entered.set()
            release.wait(10)
            connection.send((TongueResult(xy=(.1, .2), quality=1),
                             {"inference_ms": 500, "confidence": 1, "error": None}))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


def crashed_backend(connection):
    connection.send("ready")
    connection.recv()
    connection.close()


def wait_for(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.005)
    raise AssertionError("Timed out waiting for test worker")


@unittest.skipUnless(AVAILABLE, "pixel dependencies required")
class WorkerTests(unittest.TestCase):
    def blocked(self, timeout=5):
        ctx = mp.get_context("spawn")
        entered, release = ctx.Event(), ctx.Event()
        worker = TongueWorker(target=partial(blocked_backend, entered=entered, release=release), timeout=timeout)
        self.addCleanup(worker.close)
        return worker, entered, release

    def job(self, sequence):
        return TongueJob("session", sequence, float(sequence*30), ("test",), "/unused", None, None, 1)

    def test_slow_backend_drops_pending_work_without_blocking_submit(self):
        worker, entered, release = self.blocked()
        worker.submit(self.job(0))
        self.assertTrue(entered.wait(5))
        start = time.perf_counter()
        for sequence in range(1, 101):
            worker.submit(self.job(sequence))
        self.assertLess(time.perf_counter()-start, .2)
        self.assertIsNone(worker.take())
        self.assertEqual(worker.state()["pending"], 1)
        self.assertEqual(worker.state()["replaced"], 99)
        release.set()
        def newest():
            reply = worker.take()
            return reply if reply and reply.job.sequence == 100 else None
        reply = wait_for(newest)
        self.assertEqual(reply.job.timestamp_ms, 3000)
        self.assertEqual(worker.state()["completed"], 2)
        worker.close()
        self.assertFalse(worker.thread.is_alive())
        self.assertFalse(worker.process.is_alive())

    def test_invalidation_rejects_running_reply_and_shutdown_never_waits_for_model(self):
        worker, entered, release = self.blocked()
        worker.submit(self.job(0)); self.assertTrue(entered.wait(5))
        worker.invalidate()
        release.set()
        worker.submit(self.job(4))
        reply = wait_for(worker.take)
        self.assertEqual(reply.job.sequence, 4)
        self.assertEqual(worker.state()["completed"], 1)
        release.clear(); entered.clear()
        worker.submit(self.job(5)); self.assertTrue(entered.wait(5))
        start = time.perf_counter(); worker.close()
        self.assertLess(time.perf_counter()-start, 1)
        self.assertFalse(worker.process.is_alive())

    def test_timeout_and_crash_are_reported_and_worker_is_reaped(self):
        worker, entered, _ = self.blocked(timeout=2)
        worker.submit(self.job(0)); self.assertTrue(entered.wait(5))
        self.assertIn("timed out", wait_for(lambda: worker.state()["error"]))
        worker.close(); self.assertFalse(worker.process.is_alive())
        crashed = TongueWorker(target=crashed_backend)
        self.addCleanup(crashed.close)
        crashed.submit(self.job(1))
        self.assertTrue(wait_for(lambda: crashed.state()["error"]))
        crashed.close(); self.assertFalse(crashed.process.is_alive())

    @unittest.skipUnless(os.environ.get("TONGUE_MODEL_PATH"), "local tongue model opt-in")
    def test_real_model_in_spawned_worker_keeps_original_capture(self):
        from Vision.demo_detection import demo_image
        from Vision.features import DetectionConfig
        from Vision.tongue import mouth_crop
        bgr, observations = demo_image(tongue=True)
        config = DetectionConfig()
        crop, _ = mouth_crop(bgr, observations[0], config)
        worker = TongueWorker()
        self.addCleanup(worker.close)
        job = TongueJob("real", 17, 1234., ("real",), os.environ["TONGUE_MODEL_PATH"], crop, config, .9)
        worker.submit(job)
        reply = wait_for(worker.take, timeout=12)
        self.assertEqual((reply.job.sequence, reply.job.timestamp_ms), (17, 1234))
        self.assertIsNone(reply.report["error"])
        self.assertGreater(reply.report["inference_ms"], 0)

    def test_builtin_boundary_worker_needs_no_model_file_and_keeps_original_crop(self):
        from Vision.demo_detection import demo_image
        from Vision.features import DetectionConfig
        from Vision.lip_boundary import LipBoundaryModel
        from Vision.tongue import mouth_crop
        bgr, observations = demo_image(tongue=True)
        config = DetectionConfig()
        crop, _ = mouth_crop(bgr, observations[0], config, lip_boundary=True)
        worker = TongueWorker()
        self.addCleanup(worker.close)
        job = TongueJob("color", 23, 1234., ("color",), LipBoundaryModel.path, crop, config, .9, "lip-boundary")
        worker.submit(job)
        reply = wait_for(worker.take, timeout=12)
        self.assertIs(reply.job.crop, crop)
        self.assertEqual((reply.job.sequence, reply.job.timestamp_ms), (23, 1234))
        self.assertIsNone(reply.report["error"])
        self.assertIsNotNone(reply.result.xy, reply.result.reason)
        self.assertIn("Lip-boundary", reply.report["backend"])
