"""Run synthetic/replay output or explicitly opt in to camera diagnostics."""

import argparse
import json
import sys

from .signals import monotonic_ms
from .sources import read_ndjson, replay, synthetic_records


def emit(frame):
    print(json.dumps(frame, allow_nan=False, separators=(",", ":")), flush=True)


def camera(args):
    from .capture import OpenCVCamera
    from .landmarks import MediaPipeDetector
    from .overlay import render_overlay
    from .pipeline import VisionPipeline
    pipeline = VisionPipeline()
    count = 0
    first = last = None
    latency_total = 0.0
    # Model loading precedes hardware acquisition so a bad model never opens it.
    with MediaPipeDetector(args.model) as detector:
        try:
            with OpenCVCamera(args.camera_id, width=args.width, height=args.height, fps=args.fps) as source:
                print("Camera diagnostics: calibration/quality validation pending; control signals invalid.",
                      file=sys.stderr)
                while args.frames is None or count < args.frames:
                    captured = source.read()
                    observations = detector.detect(captured)
                    frame = pipeline.process(captured, observations)
                    emit(frame)
                    last = captured.envelope.timestamp_ms
                    first = last if first is None else first
                    latency_total += monotonic_ms() - last
                    count += 1
                    if args.preview:
                        detector.cv2.imshow("Vision diagnostics",
                                            render_overlay(captured.bgr, observations, frame,
                                                           mirrored=not args.unmirrored_preview))
                        if detector.cv2.waitKey(1) & 0xFF == ord("q"):
                            break
        finally:
            if args.preview:
                detector.cv2.destroyAllWindows()
            print(json.dumps({
                "captured_frames": count,
                "observed_fps": ((count - 1) * 1000 / (last - first)
                                 if count > 1 and last > first else None),
                "mean_read_to_output_ms": latency_total / count if count else None,
                "timestamp_source": "read_completion",
            }), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    synthetic = commands.add_parser("synthetic", help="synthetic SignalFrame NDJSON; no hardware")
    synthetic.add_argument("--frames", type=int, default=120)
    synthetic.add_argument("--fps", type=float, default=30)
    recorded = commands.add_parser("replay", help="rebase and replay SignalFrame NDJSON")
    recorded.add_argument("path")
    live = commands.add_parser("camera", help="explicit live camera diagnostics")
    live.add_argument("--model", required=True)
    live.add_argument("--camera-id", type=int, default=0)
    live.add_argument("--width", type=int, default=640)
    live.add_argument("--height", type=int, default=480)
    live.add_argument("--fps", type=float, default=30)
    live.add_argument("--frames", type=int)
    live.add_argument("--preview", action="store_true")
    live.add_argument("--unmirrored-preview", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "camera":
            if args.frames is not None and args.frames < 1:
                parser.error("--frames must be positive")
            camera(args)
        else:
            records = (synthetic_records(count=args.frames, fps=args.fps)
                       if args.mode == "synthetic" else read_ndjson(args.path))
            for frame in replay(records):
                emit(frame)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 1
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"Vision stream stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
