"""Offline scheduling experiment using generated face pixels/landmarks (no camera).

Compare fast captures without tongue, with deliberately slow tongue, and optionally
with the real local ONNX model. This measures scheduling, not live face-model FPS.
"""
import argparse
from functools import partial
import json
import statistics
import time

from .capture import CapturedImage
from .demo_detection import demo_image
from .lab_runtime import LabRuntime
from .signals import Envelope, monotonic_ms
from .tongue import TongueResult
from .tongue_async import AsyncTongue
from .tongue_segment import SegmentedTongueModel
from .tongue_worker import TongueWorker


def slow_backend(connection, *, delay_ms):
    connection.send("ready")
    try:
        while True:
            connection.recv()
            time.sleep(delay_ms / 1000)
            connection.send((TongueResult(reason="Synthetic slow backend"),
                             dict(error=None, inference_ms=delay_ms, confidence=0)))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


def run(kind, *, seconds, fps, delay_ms, model):
    runtime = LabRuntime()
    core = runtime.workbench
    durations, timestamps = [], []
    if kind != "baseline":
        core.tongue_model = SegmentedTongueModel(model or "/synthetic-unused.onnx")
        if kind == "slow":
            core.async_tongue = AsyncTongue(TongueWorker(target=partial(slow_backend, delay_ms=delay_ms)))
    try:
        started = time.monotonic()
        for sequence in range(round(seconds*fps)):
            due = started + sequence / fps
            time.sleep(max(0, due-time.monotonic()))
            bgr, obs = demo_image(tongue=True, head=.4 if sequence % 2 else .6)
            timestamp = monotonic_ms()
            begin = time.perf_counter()
            runtime.ingest(CapturedImage(Envelope(kind, sequence, timestamp), bgr), obs, preview=False)
            durations.append((time.perf_counter()-begin)*1000)
            timestamps.append(timestamp)
        worker = core.async_tongue.worker.state()
        ordered = sorted(durations)
        return dict(source="generated pixels and landmarks; no camera/MediaPipe", mode=kind,
                    captures=len(timestamps), trace_rows=len(core.trace),
                    fast_hz=(len(timestamps)-1)*1000/(timestamps[-1]-timestamps[0]),
                    fast_step_median_ms=statistics.median(durations),
                    fast_step_p95_ms=ordered[int(.95*(len(ordered)-1))],
                    tongue=worker, injected_delay_ms=delay_ms if kind == "slow" else None)
    finally:
        runtime.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--fps", type=float, default=30)
    parser.add_argument("--tongue-delay-ms", type=float, default=500)
    parser.add_argument("--model", help="Also run the real pinned local ONNX tongue model")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60 or not 1 <= args.fps <= 120 or not 1 <= args.tongue_delay_ms <= 5000:
        parser.error("Use seconds 1–60, fps 1–120, tongue delay 1–5000 ms")
    if round(args.seconds*args.fps) < 2:
        parser.error("At least two captures are required")
    for kind in ("baseline", "slow", "model") if args.model else ("baseline", "slow"):
        print(json.dumps(run(kind, seconds=args.seconds, fps=args.fps,
                             delay_ms=args.tongue_delay_ms, model=args.model), indent=2), flush=True)


if __name__ == "__main__":
    main()
