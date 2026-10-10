"""Bounded synthetic research processing benchmark (no inference, capture or UI)."""

import json
import platform
from statistics import median
from time import perf_counter_ns
from .processor import ResearchProcessor


def main():
    processor = ResearchProcessor()
    durations = []
    for i in range(10200):
        t = i * 1000 / 30
        blink = 1.0 if i % 90 in range(20, 24) else 0.0
        packet = dict(
            format="face_features_v1",
            session_id="benchmark",
            sequence=i,
            timestamp_ms=t,
            subject_id="synthetic",
            generation=0,
            values=dict(
                left_closure=blink,
                right_closure=blink,
                yaw=0.0,
                pitch=0.0,
                roll=0.0,
                face_x=0.5,
                face_y=0.5,
            ),
        )
        start = perf_counter_ns()
        processor.feed(packet, {}, t)
        if i >= 200:
            durations.append((perf_counter_ns() - start) / 1000)
    print(
        json.dumps(
            dict(
                samples=len(durations),
                python=platform.python_version(),
                machine=platform.machine(),
                median_us=median(durations),
                p95_us=sorted(durations)[int(0.95 * len(durations))],
                note="Synthetic rules path; excludes camera, inference, drawing and OS scheduling.",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
