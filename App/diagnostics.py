"""Readable live blockers and bounded local scalar logs; never used for control."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time


def pointer_status(source, lab):
    snap, config = lab["snapshot"], lab["config"]
    diag, detector = snap["diagnostics"], source.get("detector") or {}
    head_only = snap.get("pointer_input") == "head"
    target = snap.get("pointer_mode") == "target"
    input_name = "Head X/Y" if head_only else "Pupil"
    if lab["output"].get("error"):
        return "Pointer stopped: " + lab["output"]["error"]
    if source.get("error"):
        return "Pointer stopped: " + source["error"]
    if diag["raw_pointer"] is None:
        age = source.get("age_ms")
        if age is None or age > config["stale_ms"]:
            return "Pointer unavailable: waiting for a fresh camera/input sample."
        signals = next((f["signals"] for f in (source.get("frame") or {}).get("faces", [])
                        if f["subject_id"] == lab["runtime"]["subject_id"]), {})
        if head_only:
            details = []
            for key, name, reason_key in (("head_x", "Head X", "head_x"), ("head_y", "Head Y", "head")):
                signal = signals.get(key, {})
                if not signal.get("valid"):
                    details.append(name+": "+detector.get("reasons", {}).get(reason_key, "calibrate this head axis"))
                elif signal.get("confidence", 0) < config["min_confidence"]:
                    details.append(name+": confidence below threshold")
            return "Pointer unavailable: " + ("; ".join(details) or "waiting for fresh calibrated Head X and Head Y.")
        pupils = [signals.get(key, {}) for key in ("gaze_x", "gaze_y")]
        if all(p.get("valid") for p in pupils):
            quality = min(p.get("confidence", 0) for p in pupils)
            if quality < config["min_confidence"]:
                return f"Pointer unavailable: pupil confidence {quality:.2f} is below {config['min_confidence']:.2f}."
        reason = detector.get("reasons", {}).get("pupil", "Both pupils must be visible and usable; no pupil calibration is needed.")
        eyes = (detector.get("pupil") or {}).get("eyes", {})
        details = [f"{side.title()}: {eye['reason']}" for side, eye in eyes.items()
                   if not eye.get("valid") and eye.get("reason")]
        return "Pointer unavailable: " + reason + (" · " + "; ".join(details) if details else "")
    if not snap["armed"]:
        return input_name + " input available. Output is stopped; press Start when ready."
    if not snap["enabled"]:
        pending = []
        radius = diag.get("pointer_radius")
        if not target and radius is not None and radius > config["pointer"]["deadzone"]:
            pending.append("Head X/Y" if head_only else "pupils")
        for key, name in (() if head_only else (("head_x", "Head X"), ("head_y", "Head Y"))):
            if not diag.get(key, {}).get("neutral", True):
                pending.append(name)
        return ("Waiting to start: center " + ", ".join(pending) + "." if pending else
                "Waiting to start: release eye actions and center head inputs." if target else
                "Waiting to start: release eye actions and center inputs.")
    if target:
        location = f"X {snap['pointer_x']:.1%}, Y {snap['pointer_y']:.1%}"
        status = ("preview" if lab["output"]["mode"] == "preview" else
                  "arrived" if lab["output"].get("target_reached") else "moving toward point")
        return f"Approximate screen destination: {location} · {status}."
    radius = diag.get("pointer_radius")
    threshold = config["pointer"]["deadzone"] + config["pointer"]["hysteresis"]
    if radius is not None and not diag.get("pointer_active"):
        if radius > threshold:
            return f"Pointer filtering: radius {radius:.3f} exceeds {threshold:.3f}; waiting for filtered movement."
        return f"Pointer inside dead zone: radius {radius:.3f}; movement starts above {threshold:.3f}."
    x, y = 2*snap["pointer_x"]-1, 2*snap["pointer_y"]-1
    return f"Pointer request: X {x:+.1%}, Y {y:+.1%}."


class DiagnosticLog:
    """UI/headless observations at most 5 Hz, plus changed stop/error reasons.

    File I/O stays outside capture/Processing threads. Logs are observations, not
    a complete frame replay. Three rotating 1 MB files bound retained data.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.handler = None
        self.error = None
        self.last_state = None
        self.next_sample = 0
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.handler = RotatingFileHandler(self.path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
            self.path.chmod(0o600)
            self._write({"event":"session_start"})
        except OSError as exc:
            self._failed(exc)

    def _failed(self, exc):
        self.error = str(exc)
        if self.handler:
            try:
                self.handler.close()
            except OSError:
                pass
            self.handler = None

    def _write(self, values):
        if self.handler is None:
            return
        try:
            text = json.dumps(dict(time=time.time(), **values), allow_nan=False)
            record = logging.LogRecord("live-control", logging.INFO, "", 0, text, (), None)
            # Raise logging I/O errors here so they can be shown without stopping control.
            if self.handler.shouldRollover(record):
                self.handler.doRollover()
                self.path.chmod(0o600)
            self.handler.stream.write(text + "\n")
            self.handler.flush()
        except (OSError, ValueError) as exc:
            self._failed(exc)

    def record_error(self, error):
        self._write({"event":"ui_error", "error":str(error)})

    def record(self, source, lab):
        snap, output = lab["snapshot"], lab["output"]
        diag, detector = snap["diagnostics"], source.get("detector") or {}
        reasons = detector.get("reasons", {})
        state = (snap["armed"], snap["enabled"], snap["status"], output.get("error"),
                 source.get("error"), reasons.get("pupil"), diag["raw_pointer"] is not None, lab["mapping_id"])
        now = time.monotonic()
        if state == self.last_state and now < self.next_sample:
            return
        self.last_state, self.next_sample = state, now + .2
        signals = next((f["signals"] for f in (source.get("frame") or {}).get("faces", [])
                        if f["subject_id"] == lab["runtime"]["subject_id"]), {})
        self._write({"event":"sample", "source":source["mode"], "capture":snap["source_sequence"],
                     "capture_ms":snap["source_timestamp_ms"], "age_ms":diag.get("age_ms"),
                     "detector_capture":(source.get("frame") or {}).get("sequence"),
                     "armed":snap["armed"], "enabled":snap["enabled"], "status":snap["status"],
                     "pointer_status":pointer_status(source, lab), "pupil_reason":reasons.get("pupil"),
                     "mapping_id":lab["mapping_id"], "pointer_input":snap.get("pointer_input", "pupils"),
                     "pupils":{key:signals.get(key) for key in ("gaze_x", "gaze_y")},
                     "pupil_eyes":{side:{key:eye.get(key) for key in ("valid","reason","lid_gap","blink","aperture_source")}
                                   for side, eye in detector.get("pupil", {}).get("eyes", {}).items()},
                     "processed_pupils":diag["raw_pointer"] if snap.get("pointer_input") != "head" else None,
                     "pointer_input_values":diag["raw_pointer"], "radius":diag.get("pointer_radius"),
                     "head_reasons":{k:reasons.get(k) for k in ("head_x", "head")},
                     "head_x":diag.get("head_x"), "head_y":diag.get("head_y"),
                     "pointer_demand":[snap["pointer_x"],snap["pointer_y"]],
                     "pointer_mode":snap.get("pointer_mode", "velocity"),
                     "target_speed":snap.get("target_speed"),
                     "driver_position":lab["output"].get("pointer_position"),
                     "target_reached":lab["output"].get("target_reached"),
                     "pointer_filter":dict(lab["config"]["pointer"],
                                           smoothing_ms=diag.get("pointer_smoothing_ms", lab["config"]["pointer"]["smoothing_ms"])),
                     "pointer_interpolation_ms":diag.get("pointer_interpolation_ms", lab["config"]["interpolation_ms"]),
                     "pointer_down_gain":diag.get("pointer_down_gain", 1),
                     "target_jitter":diag.get("target_jitter"), "min_confidence":lab["config"]["min_confidence"],
                     "pointer_gain":(lab.get("mapping") or {}).get("pointer_gain",1),
                     "adaptive_pointer":(lab.get("mapping") or {}).get("adaptive_pointer", False),
                     "pointer_speed":lab["runtime"]["pointer_speed"],
                     "camera_error":source.get("error"), "driver_mode":output["mode"],
                     "driver_error":output.get("error"), "driver_events":output.get("event_counts",{})})

    def close(self):
        self._write({"event":"session_end"})
        if self.handler:
            self.handler.close()
            self.handler = None
