"""Headless CPU benchmark of matrix decoding and processing; excludes UI/detection."""

import argparse
import json
import math
import platform
import statistics
import time

from .engine import MouseProcessor
from .mocks import raw_frame


def benchmark(steps=10000):
    processor = MouseProcessor()
    processor.arm()
    costs = []
    started = time.perf_counter()
    for index in range(steps):
        timestamp = index * 10.0
        state = {"x": 0.5 if index < 20 else 0.5 + 0.3 * math.sin(index * 0.01),
                 "y": 0.5, "scroll": 0.5, "left": index % 200 > 120, "right": False}
        # A 33.3 Hz synthetic detector and 100 Hz output, using virtual timestamps.
        frame = raw_frame(index // 3, timestamp, state) if index % 3 == 0 else None
        before = time.perf_counter_ns()
        if frame:
            processor.accept(frame, timestamp)
        processor.tick(timestamp)
        costs.append((time.perf_counter_ns() - before) / 1000)
    total = time.perf_counter() - started
    sorted_costs = sorted(costs)
    return {"python": platform.python_version(), "platform": platform.system(), "steps": steps,
            "processing_mean_us": round(statistics.mean(costs), 2),
            "processing_p95_us": round(sorted_costs[int((len(sorted_costs) - 1) * 0.95)], 2),
            "processing_max_us": round(max(costs), 2), "wall_seconds": round(total, 4),
            "note": "Synthetic decoding + processor only; excludes detector, GUI, and driver latency."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=10000)
    args = parser.parse_args()
    if not 100 <= args.steps <= 1000000:
        parser.error("steps must be between 100 and 1000000")
    print(json.dumps(benchmark(args.steps), indent=2))
