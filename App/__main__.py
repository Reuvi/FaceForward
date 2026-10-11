"""Launch the native input preview; hardware-free Vision demo is the default."""

import argparse
import json
import sys
from pathlib import Path
import time

from .mouse_runtime import MouseSession
from .paths import DEFAULT_MODEL, ROOT
from .diagnostics import DiagnosticLog


def main():
    parser = argparse.ArgumentParser(description="Native Vision + Processing mouse/keyboard preview")
    parser.add_argument("--source", choices=("demo", "replay", "camera", "detector-demo"), default="demo")
    parser.add_argument("--replay", help="SignalFrame NDJSON file")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="local MediaPipe model")
    parser.add_argument("--camera-id", type=int, default=0)
    parser.add_argument("--fps", type=float, default=30)
    parser.add_argument("--config", type=Path, help="Processing JSON settings")
    parser.add_argument("--mapping", choices=("mouse", "gaming-keyboard-mouse-1", "mouse-test"), default=None,
                        help="initial mapping; otherwise use a measured personal default when available")
    parser.add_argument("--factory-defaults", action="store_true",
                        help="ignore the personal target-game default for this run")
    parser.add_argument("--output", choices=("preview", "dry-run", "native"), default="preview",
                        help="native sends real OS input and requires the camera source")
    parser.add_argument("--driver-library", type=Path, help="compiled face_input_driver library (default Drivers/build)")
    parser.add_argument("--subject", help="explicit replay subject (camera calibration requires selection in the UI)")
    parser.add_argument("--no-preview", action="store_true", help="skip camera overlay drawing")
    parser.add_argument("--headless", action="store_true", help="bounded pipeline smoke check without Tk")
    parser.add_argument("--frames", type=int, default=120, help="headless source frame limit")
    parser.add_argument("--diagnostic-log", type=Path, default=ROOT / ".local" / "diagnostics" / "live-control.jsonl",
                        help="bounded local scalar/error log; contains no images or saved calibration models")
    parser.add_argument("--no-diagnostics", action="store_true", help="disable local diagnostic logging")
    options = parser.parse_args()
    if options.output == "native" and options.source != "camera":
        parser.error("--output native requires --source camera")
    session = MouseSession()
    if not options.no_diagnostics:
        session.diagnostics = DiagnosticLog(options.diagnostic_log)
    try:
        from Processing.target_game.storage import configure_startup
        try:
            options.tuning_status = configure_startup(session.lab, options.mapping, factory=options.factory_defaults)
        except (ValueError,OSError) as exc:
            session.lab.select_mapping(options.mapping or "gaming-keyboard-mouse-1")
            options.tuning_status = "Personal default could not load: "+str(exc)
            print(options.tuning_status, file=sys.stderr)
        options.mapping = session.lab.mapping_id
        if options.config:
            data = json.loads(options.config.read_text())
            # Input ownership/subject come from App; preserve processor tunables.
            session.lab.settings({"config": data.get("config", data)})
        if options.headless:
            session.lab.start()
            session.start(options.source, path=options.replay, fps=options.fps,
                          model=options.model, camera_id=options.camera_id,
                          preview=False, count=options.frames)
            session.configure_output(options.output, options.driver_library)
            if options.subject and options.source == "replay":
                session.lab.settings({"runtime": {"subject_id": options.subject}})
            session.lab.action({"action": "arm"})
            left = right = pointer = scroll = False
            keys = dict.fromkeys(("w", "s", "space", "left_shift"), False)
            cursor = 0
            while session.thread.is_alive():
                with session.lock:
                    source_state = session.state(include_detector=True) if session.diagnostics else None
                    state = session.lab.state(cursor)
                if session.diagnostics:
                    session.diagnostics.record(source_state, state)
                for row in state["trace"]:
                    left |= bool(row["left_out"]); right |= bool(row["right_out"])
                    pointer |= abs(row["out_x"] - 0.5) > 0.01 or abs(row["out_y"] - 0.5) > 0.01
                    scroll |= abs(row["out_scroll"] - 0.5) > 0.01
                    for key in keys:
                        keys[key] |= bool(row.get("key_"+key))
                    cursor = row["id"]
                time.sleep(0.02)
            result = session.state()
            print(json.dumps({key: result[key] for key in ("mode", "status", "received", "accepted", "actual_hz", "error")}
                             | {"observed": {"left": left, "right": right, "pointer": pointer, "scroll": scroll, "keys": keys},
                                "final_output": session.lab.state()["message"],
                                "driver": session.lab.state()["output"]}, indent=2))
            error = result["error"] or session.lab.state()["output"].get("error")
            if error:
                parser.exit(1, error + "\n")
        else:
            from .desktop import run
            run(session, options)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"Could not start input preview: {exc}\n")
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        if session.diagnostics:
            try:
                session.diagnostics.record(session.state(include_detector=True), session.lab.state())
            finally:
                session.diagnostics.close()


if __name__ == "__main__":
    main()
