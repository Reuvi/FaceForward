"""Detector-only calibration state. No Processing, Drivers, UI, or OS events."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig, analyze_features
from .guided_eyes import GuidedEyes
from .pipeline import VisionPipeline
from .signals import SINGLE_SUBJECT, invalid, make_face, measurement, monotonic_ms
from .tongue import TongueModel, TongueResult, mouth_crop, sample_colors


TARGETS = ("left_open", "left_closed", "right_open", "right_closed",
           "head_neutral", "head_up", "head_down", "tongue_absent",
           "validate_absent", "validate_visible")


@dataclass
class Collection:
    target: str
    start_ms: float
    end_ms: float
    values: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    rejected: int = 0
    last_timestamp: object = None


class DetectorWorkbench:
    def __init__(self, config=None, *, clock=monotonic_ms):
        self.config = config or DetectionConfig()
        self.clock = clock
        self.pipeline = VisionPipeline()
        self.pipeline.tracker.max_gap_ms = self.config.stale_ms
        self.frame = None
        self.observations = {}
        self.selected = self.session = None
        self.features = {}
        self.crop = self.frozen_crop = None
        self.tongue = TongueResult()
        self.job = None
        self.eye_guide = None
        self.samples = {}
        self.eyes = {}
        self.head = None
        self.positives, self.negatives = [], []
        self.tongue_model = None
        self.validation = {}
        self.notice = "Single user: start a source, then calibrate or load a profile"
        self.reasons = {}
        self.trace = deque(maxlen=9000)
        self.generation = 0

    def _clear_calibration(self):
        self.samples.clear()
        self.eyes.clear()
        self.head = None
        self.job = None
        self.eye_guide = None
        self.crop = self.frozen_crop = None
        self.positives, self.negatives = [], []
        self.tongue_model = None
        self.validation.clear()
        self.tongue = TongueResult()
        self.generation += 1

    def disconnect(self, reason="Source stopped; calibration retained"):
        """Drop live evidence and unfinished capture, retaining the user's fits."""
        self.job = None
        self.eye_guide = None
        self.crop = self.frozen_crop = None
        self.tongue = TongueResult()
        self.selected = None
        self.observations = {}
        self.features = {}
        self.reasons = {}
        self.notice = reason
        if self.frame is not None:
            self.frame = dict(self.frame, faces=[make_face(f["subject_id"]) for f in self.frame["faces"]])

    def reset_calibration(self):
        self._clear_calibration()
        self.disconnect("Calibration cleared; calibrate or load a saved profile")

    def expire(self):
        if self.selected and (self.frame is None or not 0 <= self.clock() - self.frame["timestamp_ms"] <= self.config.stale_ms):
            self.disconnect("Input stale; calibration retained. Waiting for the face.")

    def _require_subject(self):
        self.expire()
        if not self.selected:
            raise ValueError("A fresh visible face is required to collect calibration")

    def select(self, subject):
        if self.frame is None or not 0 <= self.clock() - self.frame["timestamp_ms"] <= self.config.stale_ms:
            raise ValueError("Selection needs a fresh camera frame")
        if subject not in self.observations:
            raise ValueError("Select a subject present in the latest frame")
        # Compatibility for developer callers; selection no longer discards fits.
        self.selected = subject
        self.notice = "Single user ready; calibrate or load a profile"

    def configure(self, values):
        config = DetectionConfig.from_dict(values)
        self.reset_calibration()
        self.notice = "Settings changed; recalibrate or load a saved profile"
        self.config = config
        self.pipeline.tracker.max_gap_ms = config.stale_ms

    def export_calibration(self):
        from .presets import encode_preset
        self._require_idle()
        return encode_preset(self)

    def load_calibration(self, data):
        from .presets import decode_preset
        self._require_idle()
        config, eyes, head, tongue = decode_preset(data)
        self.expire()
        self._clear_calibration()
        self._invalidate("left_eye_open", "right_eye_open", "head_y", "tongue_x", "tongue_y")
        self.config, self.eyes, self.head, self.tongue_model = config, eyes, head, tongue
        self.pipeline.tracker.max_gap_ms = config.stale_ms
        self.notice = "Profile loaded for single user. Recheck eyes/head; repeat tongue ABSENT and VISIBLE checks."

    def _invalidate(self, *keys):
        if self.frame:
            faces = []
            for face in self.frame["faces"]:
                values = dict(face["signals"])
                if face["subject_id"] == self.selected:
                    values.update({key: invalid() for key in keys})
                faces.append(make_face(face["subject_id"], values))
            self.frame = dict(self.frame, faces=faces)

    def collect(self, target):
        self._require_subject()
        if target not in TARGETS:
            raise ValueError("Unknown calibration target")
        self._require_idle()
        if target.startswith("validate_") and self.tongue_model is None:
            raise ValueError("Fit the tongue appearance model first")
        if target.startswith(("left_", "right_")):
            self.eyes.pop(target.split("_")[0], None)
            self._invalidate(target.split("_")[0] + "_eye_open")
        if target.startswith("head_"):
            self.head = None
            self._invalidate("head_y")
        if target == "tongue_absent":
            self._invalidate("tongue_x", "tongue_y")
            self.tongue_model = None
            self.validation.clear()
        if target.startswith("validate_"):
            self._invalidate("tongue_x", "tongue_y")
            self.validation.pop(target, None)
        self.samples.pop(target, None)
        if target == "tongue_absent":
            self.negatives = []
        start = self.clock() + self.config.settle_ms
        self.job = Collection(target, start, start + self.config.collect_ms)
        self.notice = "Prepare: " + target.replace("_", " ")

    @property
    def calibrating(self):
        return self.job is not None or bool(self.eye_guide and self.eye_guide.active)

    def start_eye_guide(self, rest_seconds=None):
        self._require_subject()
        if self.job is not None:
            raise ValueError("Finish or cancel the current collection first")
        if rest_seconds is not None:
            try:
                rest_ms = float(rest_seconds) * 1000
            except (ValueError, TypeError) as exc:
                raise ValueError("Rest between steps must be 0–30 seconds") from exc
            self.config = replace(self.config, eye_rest_ms=rest_ms)
        self.eyes.clear()
        for target in list(self.samples):
            if target.startswith(("left_", "right_")):
                del self.samples[target]
        self._invalidate("left_eye_open", "right_eye_open")
        self.generation += 1
        self.eye_guide = GuidedEyes(self.config)
        self.notice = "Guided eyes: follow the dot with eyes comfortably open"

    def present_eye_step(self, index, phase=None):
        self.expire()
        if self.eye_guide:
            self.eye_guide.present(index, self.clock(), phase)

    def cancel(self):
        self.job = None
        self.eye_guide = None
        self.notice = "Collection cancelled"

    def _require_idle(self):
        if self.calibrating:
            raise ValueError("Finish or cancel the current collection first")

    def freeze_mouth(self):
        self._require_subject()
        self._require_idle()
        if self.crop is None or self.features.get("face") is None or self.features["face"].quality == 0:
            raise ValueError("A visible, sufficiently open mouth is required")
        self.frozen_crop = self.crop
        self.notice = "Mouth frozen in memory. Click a tongue-only patch, away from lips/teeth."

    def mark_tongue(self, x, y):
        self._require_subject()
        self._require_idle()
        if self.frozen_crop is None:
            raise ValueError("Freeze a mouth image with the tongue visible first")
        colors = sample_colors(self.frozen_crop, xy=(x, y))
        self._invalidate("tongue_x", "tongue_y")
        self.positives.extend(colors.tolist())
        self.positives = self.positives[-4000:]
        self.tongue_model = None
        self.validation.clear()
        self.notice = f"Added tongue patch ({len(self.positives)} positive pixels). Fit when both classes are collected."

    def fit_tongue(self):
        self._require_subject()
        self._require_idle()
        model = TongueModel.fit(self.positives, self.negatives, self.config.tongue_margin)
        self._invalidate("tongue_x", "tongue_y")
        self.tongue_model = model
        self.validation.clear()
        self.frozen_crop = None
        self.notice = "Appearance model fitted. Validate absent, then visible, on new frames."

    def reset_tongue(self):
        self._require_idle()
        self._invalidate("tongue_x", "tongue_y")
        self.job = None
        self.positives, self.negatives = [], []
        self.tongue_model = None
        self.validation.clear()
        self.frozen_crop = None
        self.notice = "Tongue calibration cleared"

    def _finish_collection(self):
        job, self.job = self.job, None
        if (len(job.values) < self.config.min_samples
                or len(job.values) < 0.8 * (len(job.values) + job.rejected)):
            self.notice = f"Rejected {job.target}: only {len(job.values)} usable samples ({job.rejected} rejected). Retry with better visibility."
            return
        target = job.target
        try:
            if target.startswith("validate_"):
                rate = sum(job.values) / len(job.values)
                passed = rate <= 0.05 if target == "validate_absent" else rate >= 0.8
                self.validation[target] = {"passed": passed, "detected_fraction": rate, "samples": len(job.values)}
                self.notice = f"{target}: {'PASS' if passed else 'FAIL'}, candidate on {rate:.0%} of {len(job.values)} usable frames"
                return
            if target == "tongue_absent":
                self.negatives = job.colors
                self.notice = f"Collected {len(job.values)} empty-mouth frames. Freeze a visible tongue and mark a patch next."
                return
            self.samples[target] = job.values
            if target.startswith(("left_", "right_")):
                side = target.split("_")[0]
                if all(side + suffix in self.samples for suffix in ("_open", "_closed")):
                    self.eyes[side] = EyeCalibration.fit(self.samples[side + "_closed"], self.samples[side + "_open"],
                                                        min_separation=self.config.eye_separation)
                    self.notice = f"{side.title()} eye calibrated independently"
                    return
            if target.startswith("head_") and all("head_" + x in self.samples for x in ("up", "neutral", "down")):
                separation = (self.config.head_position_separation if self.config.head_mode == "position"
                              else self.config.head_pitch_separation)
                fitted = AxisCalibration.fit(*(self.samples["head_" + x] for x in ("up", "neutral", "down")),
                                             min_separation=separation)
                self.head = replace(fitted, endpoint_tolerance=self.config.endpoint_tolerance)
                self.notice = "Head Y calibrated: up 0, neutral 0.5, down 1"
                return
            self.notice = f"Collected {target}; finish the remaining targets for this channel"
        except ValueError as exc:
            self.notice = "Calibration rejected: " + str(exc)

    def _collect_frame(self, timestamp):
        job = self.job
        if job is None:
            return
        if timestamp < job.start_ms:
            self.notice = f"Prepare {job.target.replace('_', ' ')}: {(job.start_ms - timestamp) / 1000:.1f}s"
            return
        if timestamp >= job.end_ms:
            self._finish_collection()
            return
        if timestamp == job.last_timestamp:
            return
        job.last_timestamp = timestamp
        target = job.target
        feature = self.features.get(target.split("_")[0])
        if target.startswith(("tongue_", "validate_")):
            if self.crop is not None and self.features["face"].quality > 0:
                if len(job.values) < 512:
                    job.values.append(int(self.tongue.xy is not None))
                if target == "tongue_absent" and len(job.colors) < 12000:
                    job.colors.extend(sample_colors(self.crop)[::4].tolist())
                    job.colors = job.colors[:12000]
            else:
                job.rejected += 1
        elif feature is not None and feature.quality > 0 and feature.value is not None:
            if len(job.values) < 512:
                job.values.append(feature.value)
        else:
            job.rejected += 1
        self.notice = f"Collecting {target.replace('_', ' ')}: {len(job.values)} usable / {job.rejected} rejected; {(job.end_ms - timestamp) / 1000:.1f}s"

    def process(self, captured, observations):
        previous_session = self.session
        previous_timestamp = self.frame["timestamp_ms"] if self.frame else None
        observations = list(observations)
        ambiguous = len(observations) > 1
        # Never choose between people in the single-user calibration path.
        if ambiguous:
            observations = []
        try:
            frame = self.pipeline.process(captured, observations)
        except Exception:
            self.disconnect("Invalid input; calibration retained")
            raise
        # Keep envelope/order validation from the pipeline; geometric reassociation
        # must not change the user's logical slot or reset downstream eye history.
        frame["faces"] = [make_face(SINGLE_SUBJECT) for _ in frame["faces"]]
        self.session = frame["session_id"]
        self.frame = frame
        current_observations = {face["subject_id"]: item for face, item in zip(frame["faces"], observations)}
        if previous_session is not None and previous_session != self.session:
            self.disconnect("Source restarted; calibration retained")
            self.validation.clear()
        elif previous_timestamp is not None and frame["timestamp_ms"] - previous_timestamp > self.config.stale_ms:
            self.disconnect("Capture gap; unfinished capture cancelled, completed calibration retained")
        if not 0 <= self.clock() - frame["timestamp_ms"] <= self.config.stale_ms:
            self.disconnect("Capture is stale or future-dated; calibration retained")
        elif not current_observations:
            self.disconnect("Multiple faces supplied; use one person. Calibration retained." if ambiguous
                            else "Face unavailable; calibration retained. Waiting for the face.")
        else:
            if self.selected is None:
                self.notice = "Single user detected; calibration retained. Calibrate or load a profile if needed."
            self.selected = SINGLE_SUBJECT
            self.observations = current_observations
        self.features = {}
        self.crop = None
        self.tongue = TongueResult()
        self.reasons = {}
        if self.selected:
            observation = self.observations[self.selected]
            self.features = analyze_features(captured.bgr, observation, self.config)
            self.crop, mouth_reason = mouth_crop(captured.bgr, observation, self.config)
            if self.crop is not None and self.features["face"].quality > 0 and self.tongue_model is not None:
                self.tongue = self.tongue_model.detect(self.crop, self.config)
            elif self.crop is None:
                self.tongue.reason = mouth_reason
            elif self.features["face"].quality == 0:
                self.tongue.reason = self.features["face"].reason
            self._collect_frame(frame["timestamp_ms"])
            if self.eye_guide and self.eye_guide.active:
                self.eye_guide.feed(frame["timestamp_ms"], self.features)
                if not self.eye_guide.active:
                    self.eyes = dict(self.eye_guide.fits)
                    self.notice = self.eye_guide.report
            values = {}
            for side in ("left", "right"):
                feature, calibration = self.features[side], self.eyes.get(side)
                reason = feature.reason
                if calibration is None:
                    reason = "Complete guided eye calibration"
                elif feature.quality > 0 and feature.value is not None:
                    if (calibration.closed_limit is not None
                            or feature.value <= max(calibration.opened * 1.8, calibration.opened + 0.04)):
                        values[side + "_eye_open"] = calibration.classify(feature.value, feature.quality)
                        reason = ("Classified independently" if values[side + "_eye_open"]["valid"]
                                  else "UNCERTAIN: between learned open and closed ranges")
                    else:
                        reason = "Openness far outside calibration"
                self.reasons[side] = reason
            feature = self.features["head"]
            self.reasons["head"] = feature.reason
            if self.head is None:
                self.reasons["head"] = "Collect head up, neutral, and down"
            elif feature.quality > 0 and feature.value is not None:
                value = self.head.normalize(feature.value)
                values["head_y"] = measurement(value, feature.quality)
                self.reasons["head"] = "Calibrated head Y" if value is not None else "Outside calibrated head range"
            passed = all(self.validation.get(name, {}).get("passed", False) for name in ("validate_absent", "validate_visible"))
            self.reasons["tongue"] = self.tongue.reason
            if self.tongue.xy is not None:
                if passed:
                    quality = min(self.tongue.quality, self.features["face"].quality)
                    values["tongue_x"] = measurement(self.tongue.xy[0], quality)
                    values["tongue_y"] = measurement(self.tongue.xy[1], quality)
                else:
                    self.reasons["tongue"] = "Candidate only: pass absent and visible checks before valid output"
            frame["faces"] = [make_face(face["subject_id"], values if face["subject_id"] == self.selected else {})
                              for face in frame["faces"]]
        frame["diagnostic_only"] = True
        self.frame = frame
        self._record()
        return frame

    def _record(self):
        frame = self.frame
        signals = next((f["signals"] for f in frame["faces"] if f["subject_id"] == self.selected), {})
        row = {"session_id": frame["session_id"], "sequence": frame["sequence"], "timestamp_ms": frame["timestamp_ms"],
               "subject_id": SINGLE_SUBJECT, "calibration_generation": self.generation, "head_mode": self.config.head_mode,
               "head_raw_units": "image_height_fraction" if self.config.head_mode == "position" else "degrees",
               "mouth_opening_ratio": self.crop.opening_ratio if self.crop else None,
               "mouth_width_px": self.crop.width_px if self.crop else None,
               "tongue_candidate_x": self.tongue.xy[0] if self.tongue.xy else None,
               "tongue_candidate_y": self.tongue.xy[1] if self.tongue.xy else None,
               "tongue_area_fraction": self.tongue.area_fraction, "tongue_quality": self.tongue.quality}
        for side in ("left", "right", "head"):
            feature = self.features.get(side)
            row[side + "_raw"] = feature.value if feature else None
            row[side + "_quality"] = feature.quality if feature else 0
            row[side + "_reason"] = self.reasons.get(side, "No selected subject")
            for key in ("brightness", "focus", "clipped_fraction"):
                row[side + "_" + key] = feature.metrics.get(key) if feature else None
        for key in ("left_eye_open", "right_eye_open", "head_y", "tongue_x", "tongue_y"):
            item = signals.get(key, {})
            row[key] = item.get("value")
            row[key + "_valid"] = item.get("valid", False)
            row[key + "_confidence"] = item.get("confidence", 0)
        for side in ("left", "right"):
            calibration = self.eyes.get(side)
            row[side + "_closed_limit_raw"] = calibration.closed_limit if calibration else None
            row[side + "_open_limit_raw"] = calibration.open_limit if calibration else None
            row[side + "_threshold_raw"] = (calibration.closed + calibration.threshold * (calibration.opened - calibration.closed)) if calibration else None
            value = signals.get(side + "_eye_open", {}).get("value")
            row[side + "_closed_bit"] = 1 - value if value is not None else None
        for name in ("validate_absent", "validate_visible"):
            row[name + "_passed"] = self.validation.get(name, {}).get("passed", False)
        row["tongue_reason"] = self.reasons.get("tongue", "No selected subject")
        self.trace.append(row)

    def state(self):
        self.expire()
        return {"frame": self.frame, "selected": self.selected, "notice": self.notice,
                "scope_subject": SINGLE_SUBJECT,
                "features": {k: asdict(v) for k, v in self.features.items()}, "reasons": dict(self.reasons),
                "eyes": {k: asdict(v) for k, v in self.eyes.items()}, "head": asdict(self.head) if self.head else None,
                "samples": {k: len(v) for k, v in self.samples.items()},
                "tongue_pixels": {"positive": len(self.positives), "negative": len(self.negatives)},
                "tongue_fit": self.tongue_model.report if self.tongue_model else None,
                "validation": dict(self.validation), "collecting": self.job.target if self.job else None,
                "generation": self.generation, "config": self.config.to_dict(),
                "eye_guide": self.eye_guide.state(self.clock()) if self.eye_guide else None,
                "calibrating": self.calibrating}
