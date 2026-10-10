"""Research coordination over the existing capture worker. Scalar-only, bounded data."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import csv
import json
from math import isfinite
from pathlib import Path
import random
from statistics import median
from uuid import uuid4

from Processing.research.processor import ResearchProcessor, validate_packet
from Processing.research.settings import settings
from Processing.research.models import fit_models, validate_models

LABELS = (
    "natural_blink",
    "left_wink",
    "right_wink",
    "both_intentional",
    "bilateral_natural",
    "long_closure",
    "talking",
    "smiling",
    "tongue",
    "looking_down",
    "rest",
    "smile",
    "brow",
    "open_pose",
)


def quantile(values, p):
    values = sorted(values)
    return values[round((len(values) - 1) * p)]


def validate_profile(data):
    fields = {"settings", "fits", "pose_bounds", "models", "gaze"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid research profile fields")
    settings(data["settings"])
    validate_models(data["models"])
    allowed = {
        "eyeBlinkLeft",
        "eyeBlinkRight",
        "mouthSmileLeft",
        "mouthSmileRight",
        "browInnerUp",
    }
    if not isinstance(data["fits"], dict) or set(data["fits"]) - allowed:
        raise ValueError("Invalid expression fits")
    for fit in data["fits"].values():
        if (
            not isinstance(fit, dict)
            or set(fit) != {"open", "active"}
            or any(
                type(v) not in (int, float) or not isfinite(v) or not 0 <= v <= 1
                for v in fit.values()
            )
            or fit["active"] - fit["open"] < 0.05
        ):
            raise ValueError("Unreliable expression fit")
    if not isinstance(data["pose_bounds"], dict) or set(data["pose_bounds"]) - {
        "yaw",
        "pitch",
        "roll",
        "face_scale",
    }:
        raise ValueError("Invalid pose limits")
    for bounds in data["pose_bounds"].values():
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(type(v) in (float, int) and isfinite(v) for v in bounds)
            or bounds[0] > bounds[1]
        ):
            raise ValueError("Invalid pose range")
    if data["gaze"] is not None:
        from Vision.gaze_research import validate_model

        validate_model(data["gaze"])
    probe = ResearchProcessor()
    probe.models = data["models"]
    probe.pose_bounds = data["pose_bounds"]
    probe.configure(data["settings"])
    return deepcopy(data)


class Fixations:
    def __init__(self, viewport, *, validation_only=False):
        self.viewport = tuple(viewport)
        self.validation_only = validation_only
        grid = [(x, y) for y in (0.15, 0.5, 0.85) for x in (0.15, 0.5, 0.85)]
        rng = random.Random(17)
        self.steps = []
        roles = ("validation",) if validation_only else ("train", "validation")
        for role in roles:
            for pose in ("neutral", "left", "right", "up", "down"):
                targets = list(grid)
                rng.shuffle(targets)
                self.steps.extend((role, pose, target) for target in targets)
        self.index = 0
        self.start = None
        self.samples = []
        self.total_samples = 0
        self.episodes = []
        self.paused = False
        self.active = True
        self.notice = ""
        self.token = uuid4().hex
        self.last_time = None

    def present(self, index, now):
        if (
            self.active
            and not self.paused
            and index == self.index
            and self.start is None
        ):
            self.start = now + 700

    def advance(self):
        self.index += 1
        self.start = None
        self.samples = []
        self.total_samples = 0
        self.active = self.index < len(self.steps)

    def feed(self, t, values):
        from Vision.gaze_research import BASE, vector

        if self.last_time is not None and t <= self.last_time:
            return
        self.last_time = t
        if not self.active or self.paused or self.start is None or t < self.start:
            return
        if t >= self.start + 1500:
            if len(self.samples) >= 8 and len(self.samples) >= 0.8 * self.total_samples:
                role, pose, target = self.steps[self.index]
                self.episodes.append(
                    dict(
                        index=self.index,
                        role=role,
                        pose=pose,
                        target=target,
                        values={k: median(v[k] for v in self.samples) for k in BASE},
                    )
                )
                self.notice = "Fixation recorded"
            else:
                self.notice = "Skipped unclear fixation; use Retry before advancing next target if needed"
            self.advance()
            return
        self.total_samples += 1
        if vector(values) is not None and len(self.samples) < 256:
            self.samples.append(dict(values))

    def state(self, now):
        index = min(self.index, len(self.steps) - 1)
        role, pose, target = self.steps[index]
        return dict(
            index=index,
            total=len(self.steps),
            active=self.active,
            target=target,
            pose=pose,
            role=role,
            waiting=self.start is None,
            paused=self.paused,
            token=self.token,
            samples=len(self.samples),
            remaining_ms=2200
            if self.start is None
            else max(0, self.start + 1500 - now),
            notice=self.notice,
        )


class ResearchSession:
    def __init__(self, clock):
        self.clock = clock
        self.processor = ResearchProcessor()
        self.trials = deque(maxlen=400)
        self.run_id = uuid4().hex[:10]
        self.trial_count = 0
        self.packet = None
        self.guide_groups = {}
        self.was_guiding = False
        self.calibrating = False
        self.gaze = None
        self.gaze_ready = False
        self.fixations = None
        self.viewport = None
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="local-research-fit"
        )
        self.future = None
        self.job_kind = None
        self.revision = 0
        self.job_revision = None
        self.report = "Calibrate eyes, then record labeled train and validation trials."
        self.source_kind = None
        self.calibrating = False

    def reset_person(self):
        self.processor = ResearchProcessor(self.processor.config)
        # Trained acceptance and pose gates cannot transfer to a newly selected face.
        self.processor.config["model"] = "rules"
        self.processor.config["pose_gate"] = False
        self.packet = None
        self.guide_groups = {}
        self.was_guiding = False
        self.calibrating = False
        self.gaze = None
        self.gaze_ready = False
        self.fixations = None
        self.trials.clear()
        self.revision += 1

    def stop(self, reason):
        self.end_trial(aborted=True)
        self.processor.reset(reason)
        if self.fixations and self.fixations.active:
            self.fixations = None

    def observe(self, frame, packet, base, guide=None, calibrating=False):
        if packet is None:
            self.stop("No selected research subject")
            self.packet = None
            self.processor.feed_unknown(frame, self.clock())
            return
        try:
            validate_packet(packet)
        except ValueError:
            self.stop("Invalid feature packet")
            raise
        for key in ("session_id", "sequence", "timestamp_ms"):
            if packet[key] != frame[key]:
                self.stop("Mismatched feature envelope")
                raise ValueError("Feature/SignalFrame mismatch")
        if packet["subject_id"] not in {f["subject_id"] for f in frame["faces"]}:
            self.stop("Mismatched feature subject")
            raise ValueError("Feature subject mismatch")
        t = packet["timestamp_ms"]
        values = packet["values"]
        if not 0 <= self.clock() - t <= self.processor.config["stale_ms"]:
            self.stop("Stale feature packet")
            return
        if (
            self.packet
            and packet["session_id"] == self.packet["session_id"]
            and (
                packet["sequence"] <= self.packet["sequence"]
                or t < self.packet["timestamp_ms"]
            )
        ):
            self.stop("Duplicate/out-of-order feature packet")
            return
        self.packet = packet
        self.calibrating = calibrating
        if calibrating:
            self.processor.reset("Calibrating; preview stopped")
        if guide and guide["active"]:
            if not self.was_guiding:
                self.guide_groups = {}
            self.was_guiding = True
            if not guide["waiting"] and not guide["preparing"]:
                group = self.guide_groups.setdefault(guide["name"], [])
                if len(group) < 512:
                    group.append(dict(values))
        elif self.was_guiding:
            self.was_guiding = False
            if guide:
                for side in ("Left", "Right"):
                    key = "eyeBlink" + side
                    opened = [
                        v[key]
                        for name, group in self.guide_groups.items()
                        if name in ("center", "left", "right", "up", "down")
                        for v in group
                        if v.get(key) is not None
                    ]
                    closed = [
                        v[key]
                        for v in self.guide_groups.get("closed", [])
                        if v.get(key) is not None
                    ]
                    try:
                        self.fit_feature(key, opened, closed)
                    except ValueError:
                        self.processor.fits.pop(key, None)
            self.revision += 1
        if self.fixations and self.fixations.active:
            self.processor.reset("Gaze calibration; preview stopped")
            self.fixations.feed(t, values)
        gaze = None
        if self.gaze:
            from Vision.gaze_research import predict

            gaze = predict(self.gaze, values)
        recorded = self.processor.feed(
            packet, base, self.clock(), gaze if self.gaze_ready else None
        )
        if recorded:
            trial = self.processor.trial or {}
            self.processor.trace[-1].update(
                trial_id=trial.get("id"),
                label=trial.get("label", "unlabeled"),
                role=trial.get("role", "train"),
                session_id=packet["session_id"],
                subject_id=packet["subject_id"],
                source_kind=self.source_kind,
                gaze_estimate_x=gaze[0] if gaze else None,
                gaze_estimate_y=gaze[1] if gaze else None,
            )
        if self.processor.trial:
            trial = self.processor.trial
            trial["frames"] += 1
            trial["invalid"] += int(
                not self.processor.eye_sample["left"]["known"]
                or not self.processor.eye_sample["right"]["known"]
            )

    def fit_feature(self, key, opened, active):
        if min(len(opened), len(active)) < 12:
            raise ValueError(f"{key}: need at least 12 clear rest and active samples")
        a, b = quantile(opened, 0.95), quantile(active, 0.05)
        if b - a < 0.05:
            raise ValueError(
                f"{key}: rest/active distributions overlap; input remains disabled"
            )
        self.processor.fits[key] = dict(open=median(opened), active=median(active))

    def begin_trial(self, label, role, expected=1):
        if (
            label not in LABELS
            or role not in ("train", "validation")
            or type(expected) is not int
            or not 0 <= expected <= 1000
        ):
            raise ValueError("Invalid trial label/role/count")
        if self.calibrating:
            raise ValueError("Finish detector calibration first")
        if (
            self.packet is None
            or not 0
            <= self.clock() - self.packet["timestamp_ms"]
            <= self.processor.config["stale_ms"]
        ):
            raise ValueError("Select a fresh face first")
        if self.fixations and self.fixations.active:
            raise ValueError("Finish/cancel gaze calibration first")
        if self.processor.trial:
            raise ValueError("Finish the current trial first")
        for gate in self.processor.gates.values():
            gate.reset()
        self.trial_count += 1
        self.processor.trial = dict(
            id=f"{self.run_id}-{self.trial_count}",
            label=label,
            role=role,
            expected=expected,
            started_ms=self.clock(),
            frames=0,
            invalid=0,
            source_kind=self.source_kind,
            settings_json=json.dumps(self.processor.config, sort_keys=True),
        )
        self.report = f"Recording {role}: {label}. Begin from eyes open. Stop after the gesture(s) reopen."

    def end_trial(self, aborted=False):
        trial = self.processor.trial
        if trial:
            trial = dict(
                trial, duration_ms=self.clock() - trial["started_ms"], aborted=aborted
            )
            related = [e for e in self.processor.events if e["trial_id"] == trial["id"]]
            trial["left_actions"] = sum(
                e["accepted"] for e in related if e["channel"] == "left"
            )
            trial["right_actions"] = sum(
                e["accepted"] for e in related if e["channel"] == "right"
            )
            self.trials.append(trial)
            if aborted:
                for row in (*self.processor.events, *self.processor.trace):
                    if row.get("trial_id") == trial["id"]:
                        row["role"] = "aborted"
            self.processor.trial = None
            for gate in self.processor.gates.values():
                gate.reset()
            self.report = f"Saved trial {trial['id']}: left {trial['left_actions']}, right {trial['right_actions']}; invalid frames {trial['invalid']}/{trial['frames']}"
        return trial

    def fit_expressions(self):
        rows = list(self.processor.trace)
        messages = []
        for key, label in (
            ("mouthSmileLeft", "smile"),
            ("mouthSmileRight", "smile"),
            ("browInnerUp", "brow"),
        ):

            def values(target):
                return [
                    r[key]
                    for r in rows
                    if r.get("label") == target
                    and r.get("role") == "train"
                    and r.get(key) is not None
                ]

            try:
                self.fit_feature(key, values("rest"), values(label))
                messages.append(
                    key
                    + ": usable fit; validate against talking/smiling before mapping"
                )
            except ValueError as exc:
                self.processor.fits.pop(key, None)
                messages.append(str(exc))
        pose_rows = [
            r
            for r in rows
            if r.get("label") == "open_pose" and r.get("role") == "train"
        ]
        if len(pose_rows) >= 12:
            for key in ("yaw", "pitch", "roll", "face_scale"):
                observed = [r[key] for r in pose_rows if r.get(key) is not None]
                if len(observed) >= 0.8 * len(pose_rows):
                    self.processor.pose_bounds[key] = [
                        min(observed) - 0.03,
                        max(observed) + 0.03,
                    ]
        self.report = "\n".join(messages)
        self.revision += 1
        self.processor.reset("Feature fits changed")

    def suggest_duration(self):
        messages = []
        proposal = dict(self.processor.config)
        for side in ("left", "right"):
            rows = [
                e
                for e in self.processor.events
                if e["channel"] == side and e["role"] == "train"
            ]
            blinks = [e["duration_ms"] for e in rows if e["label"] == "natural_blink"]
            winks = [e["duration_ms"] for e in rows if e["label"] == side + "_wink"]
            if min(len(blinks), len(winks)) < 5:
                messages.append(side + ": need ≥5 labeled blinks and winks")
                continue
            a, b = quantile(blinks, 0.95), quantile(winks, 0.05)
            if a >= b:
                messages.append(
                    f"{side}: duration distributions overlap ({a:.0f} vs {b:.0f} ms); no duration-only recommendation"
                )
                continue
            proposal[side + "_min_ms"] = round((a + b) / 2)
            messages.append(
                f"{side}: blink p95 {a:.0f} ms; wink p05 {b:.0f} ms; suggested minimum {proposal[side + '_min_ms']} ms"
            )
        self.report = (
            "\n".join(messages)
            + "\nSuggestion only; review and Apply settings, then record validation."
        )
        return proposal

    def submit(self, kind):
        if kind not in ("events", "gaze", "gaze_validation"):
            raise ValueError("Unknown local fit")
        self.end_trial()
        if self.future and not self.future.done():
            raise ValueError("Local fit already running")
        self.processor.reset("Fitting; preview stopped")
        self.job_revision = self.revision
        self.job_kind = kind
        if kind == "events":
            self.future = self.executor.submit(
                fit_models, deepcopy(list(self.processor.events))
            )
        else:
            from Vision.gaze_research import fit_gaze, evaluate

            if not self.fixations or self.fixations.active:
                raise ValueError("Finish the gaze target sequence first")
            if kind == "gaze":
                self.future = self.executor.submit(
                    fit_gaze, deepcopy(self.fixations.episodes), self.fixations.viewport
                )
            else:
                if self.gaze is None:
                    raise ValueError("No gaze model")
                if not self.fixations.validation_only:
                    raise ValueError(
                        "Record a fresh validation target run after fitting; training targets cannot validate the model"
                    )
                self.future = self.executor.submit(
                    evaluate, deepcopy(self.gaze), deepcopy(self.fixations.episodes)
                )
        self.report = "Fitting/evaluating locally in the background…"

    def poll(self):
        self.processor.expire(self.clock())
        if self.future and self.future.done():
            job = self.future
            self.future = None
            try:
                result = job.result()
                if self.job_revision != self.revision:
                    raise ValueError(
                        "Discarded fit because source/profile/settings changed"
                    )
                if self.job_kind == "events":
                    self.processor.models, self.report = result
                elif self.job_kind == "gaze":
                    self.gaze, self.report = result
                    self.gaze_ready = False
                    self.report += (
                        "\nRecord a fresh validation run before enabling gaze preview."
                    )
                else:
                    report = result
                    self.gaze_ready = (
                        report["usable"] == report["episodes"]
                        and report["episodes"] >= 9
                        and report["targets"] == 9
                        and report["outside"] == 0
                        and report["p95_px"] is not None
                        and report["p95_px"] <= self.processor.config["gaze_radius_px"]
                    )
                    self.report = f"Fresh gaze validation: {report}; preview {'eligible' if self.gaze_ready else 'disabled — more calibration needed'}"
            except Exception as exc:
                self.report = f"Local fit failed: {exc}"

    def start_gaze(self, viewport, validation=False):
        if self.calibrating:
            raise ValueError("Finish detector calibration first")
        if (
            self.packet is None
            or not 0
            <= self.clock() - self.packet["timestamp_ms"]
            <= self.processor.config["stale_ms"]
        ):
            raise ValueError("Fresh input required")
        if self.packet is None or any(
            self.packet["values"].get(k) is None
            for k in ("left_iris_x", "right_iris_x", "yaw")
        ):
            raise ValueError("Fresh calibrated open eyes and head pose are required")
        if validation and (
            self.gaze is None or tuple(self.gaze["viewport"]) != tuple(viewport)
        ):
            raise ValueError("Fit gaze for this screen size first")
        self.end_trial()
        self.processor.reset("Gaze target collection")
        self.gaze_ready = False
        self.viewport = tuple(viewport)
        self.fixations = Fixations(viewport, validation_only=validation)
        self.revision += 1
        self.report = "Follow targets with the indicated comfortable head pose. Pause, retry or skip as needed."

    def arm(self):
        self.processor.expire(self.clock())
        if self.calibrating:
            raise ValueError("Finish detector calibration first")
        if (
            self.packet is None
            or self.clock() - self.packet["timestamp_ms"]
            > self.processor.config["stale_ms"]
        ):
            raise ValueError("Fresh input required")
        if self.processor.config["pointer_mode"] == "gaze" and not self.gaze_ready:
            raise ValueError("Fresh gaze validation must pass first")
        if self.fixations and self.fixations.active:
            raise ValueError("Finish gaze calibration first")
        self.processor.reset("Research preview armed")
        self.processor.armed = True

    def profile(self):
        return deepcopy(
            dict(
                settings=self.processor.config,
                fits=self.processor.fits,
                pose_bounds=self.processor.pose_bounds,
                models=self.processor.models,
                gaze=self.gaze,
            )
        )

    def load_profile(self, data):
        data = validate_profile(data)
        self.processor = ResearchProcessor(data["settings"])
        self.processor.fits = data["fits"]
        self.processor.pose_bounds = data["pose_bounds"]
        self.processor.models = data["models"]
        self.gaze = data["gaze"]
        self.gaze_ready = False
        self.fixations = None
        self.trials.clear()
        self.packet = None
        self.revision += 1
        self.report = "Profile loaded disarmed. Gaze requires a fresh validation run."

    def export(self, directory):
        directory = Path(directory) / (
            "research-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + self.run_id
        )
        directory.mkdir(parents=True, exist_ok=False)
        for name, rows in (
            ("frames", self.processor.trace),
            ("events", self.processor.events),
            ("trials", self.trials),
        ):
            rows = list(rows)
            keys = sorted(set().union(*(r.keys() for r in rows))) if rows else []
            with (directory / (name + ".csv")).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)
        (directory / "report.json").write_text(
            json.dumps(
                dict(
                    report=self.report,
                    profile=self.profile(),
                    gaze_episodes=self.fixations.episodes if self.fixations else [],
                    retention={"frames": 9000, "events": 2000, "trials": 400},
                    source_kind=self.source_kind,
                ),
                indent=2,
                allow_nan=False,
            )
        )
        return directory

    def close(self):
        self.stop("Closed")
        self.executor.shutdown(wait=False, cancel_futures=True)
