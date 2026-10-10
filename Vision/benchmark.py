"""Local synthetic landmark-to-SignalFrame benchmark; no camera, model, or UI."""

import argparse
import json
import platform
import statistics
import time
from types import SimpleNamespace

from .calibration import AxisCalibration, EyeCalibration
from .capture import CapturedImage
from .landmarks import EYES, observation_from_landmarks
from .pipeline import EyeBinding, VisionPipeline
from .signals import Envelope


def synthetic_mesh(x_offset=0.0):
    """Pixel fixtures only; neither these faces nor their quality scores are real."""
    points = [SimpleNamespace(x=0.5, y=0.4) for _ in range(478)]

    def place(index, x, y):
        points[index] = SimpleNamespace(x=x / 640, y=y / 480)

    place(168, 320, 180)
    place(61, 270, 310)
    place(291, 370, 310)
    for side, center in (("left", 390), ("right", 250)):
        corners, pairs, irises = EYES[side]
        place(corners[0], center + 20, 200)
        place(corners[1], center - 20, 200)
        for i, (upper, lower) in enumerate(pairs):
            place(upper, center + (i - 1) * 8, 196)
            place(lower, center + (i - 1) * 8, 204)
        for index in irises:
            place(index, center - 4, 202)
    for point in points:
        point.x += x_offset
    return points


def summarize(values):
    ordered = sorted(values)
    return {
        "mean_us": round(statistics.mean(values), 2),
        "p95_us": round(ordered[int((len(ordered) - 1) * 0.95)], 2),
        "max_us": round(max(values), 2),
    }


def benchmark(*, iterations=5000, faces=1):
    if type(iterations) is not int or not 100 <= iterations <= 100000:
        raise ValueError("iterations must be an integer in [100, 100000]")
    if type(faces) is not int or faces not in (1, 2):
        raise ValueError("faces must be 1 or 2")
    meshes = [synthetic_mesh(offset) for offset in ((0.0,) if faces == 1 else (-0.2, 0.2))]
    pipeline = VisionPipeline()
    observations = [observation_from_landmarks(mesh, 640, 480) for mesh in meshes]
    initial = pipeline.process(CapturedImage(Envelope("benchmark", 0, 0), None), observations)
    eye = EyeCalibration(0.02, 0.22, 0.5, AxisCalibration(0.2, 0.5, 0.8),
                         AxisCalibration(-0.1, 0, 0.1))
    pipeline.bind(EyeBinding(
        "benchmark", initial["faces"][0]["subject_id"], eye, eye,
        lambda _: {"left": 0.9, "right": 0.9}, 0.2,
    ))
    timings, serialization = [], []
    warmup = 200
    for sequence in range(1, iterations + warmup + 1):
        captured = CapturedImage(Envelope("benchmark", sequence, sequence * 1000 / 30), None)
        started = time.perf_counter_ns()
        observations = [observation_from_landmarks(mesh, 640, 480) for mesh in meshes]
        frame = pipeline.process(captured, observations)
        processed = time.perf_counter_ns()
        json.dumps(frame, separators=(",", ":"), allow_nan=False)
        serialized = time.perf_counter_ns()
        if sequence > warmup:
            timings.append((processed - started) / 1000)
            serialization.append((serialized - processed) / 1000)
    return {
        "python": platform.python_version(), "platform": platform.system(),
        "machine": platform.machine(), "synthetic_faces": faces, "samples": iterations,
        "landmark_geometry_and_pipeline": summarize(timings),
        "optional_json_serialization": summarize(serialization),
        "note": "Excludes neural inference, capture, UI, driver, and OS scheduling guarantees. "
                "Local application integration passes dictionaries without JSON serialization.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--faces", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    try:
        result = benchmark(iterations=args.iterations, faces=args.faces)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
