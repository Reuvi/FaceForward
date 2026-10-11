"""Detector-only calibration state. No Processing, Drivers, UI, or OS events."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig, analyze_features
from .wink_guide import EyeCalibrationFlow
from .movement_guide import MovementGuide
from .wink_model import NAMES, measure as measure_winks, score as wink_score, classify as classify_wink
from .pupil import PupilReading, measure as measure_pupils, normalize as normalize_pupils, settings as pupil_settings, MEASUREMENT as PUPIL_MEASUREMENT
from .pipeline import VisionPipeline
from .signals import SINGLE_SUBJECT, invalid, make_face, measurement, monotonic_ms
from .tongue import TONGUE_MEASUREMENT, TongueModel, TongueResult, mouth_crop, sample_colors
from .tongue_async import AsyncTongue


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
        # Position remains decodable for old files, never an active lab mode.
        self.config = replace(config, head_mode="pitch") if config else DetectionConfig()
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
        self.movement_guide = None
        self.samples = {}
        self.eyes = {}
        self.winks = {}
        self.wink_vectors = {}
        self.wink_readings = {}
        self.head = self.head_x = None
        self.pupil_settings = pupil_settings()
        self.pupil = PupilReading()
        self.tongue_range = None
        self.positives, self.negatives = [], []
        self.tongue_marks = []
        self.tongue_model = None
        self.validation = {}
        self.notice = "Single user: start a source, then calibrate or load a profile"
        self.reasons = {}
        self.trace = deque(maxlen=9000)
        self.generation = 0
        self.async_tongue = AsyncTongue()

    @property
    def independent_tongue(self):
        return hasattr(self.tongue_model, "measurement")

    def close(self):
        self.async_tongue.worker.close()

    def _clear_calibration(self):
        self.async_tongue.invalidate()
        self.samples.clear()
        self.eyes.clear()
        self.winks.clear()
        self.wink_readings.clear()
        self.head = self.head_x = None
        self.pupil_settings = pupil_settings()
        self.pupil = PupilReading()
        self.tongue_range = None
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.crop = self.frozen_crop = None
        self.positives, self.negatives = [], []
        self.tongue_marks = []
        self.tongue_model = None
        self.validation.clear()
        self.tongue = TongueResult()
        self.generation += 1

    def disconnect(self, reason="Source stopped; calibration retained"):
        """Drop live evidence and unfinished capture, retaining the user's fits."""
        self.async_tongue.invalidate()
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.crop = self.frozen_crop = None
        self.tongue = TongueResult()
        if self.tongue_model is not None:
            self.tongue_model.reset_tracking()
        self.selected = None
        self.observations = {}
        self.features = {}
        self.pupil = PupilReading()
        self.wink_vectors = {}
        self.wink_readings = {}
        self.reasons = {}
        self.notice = reason
        if self.frame is not None:
            self.frame = dict(self.frame, faces=[make_face(f["subject_id"]) for f in self.frame["faces"]])
            if "eye_intent" in self.frame:
                self.frame["eye_intent"]=dict(self.frame["eye_intent"],
                    left=dict(value=None,known=False,state="unknown"),right=dict(value=None,known=False,state="unknown"))

    def reset_calibration(self):
        segment = self.tongue_model if hasattr(self.tongue_model, "measurement") else None
        self._clear_calibration()
        self.tongue_model = segment
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
        config = replace(DetectionConfig.from_dict(values), head_mode="pitch")
        self.reset_calibration()
        self.notice = "Settings changed; recalibrate or load a saved profile"
        self.config = config
        self.pipeline.tracker.max_gap_ms = config.stale_ms

    def export_calibration(self):
        from .presets import encode_preset
        self._require_idle()
        return encode_preset(self)

    def load_calibration(self, data):
        from .presets import decode_preset, decode_winks, decode_tongue_range, decode_pupil_settings, decode_head_x
        self._require_idle()
        config, eyes, head, tongue = decode_preset(data)
        winks = decode_winks(data)
        tongue_range = decode_tongue_range(data, config)
        pupil_options = decode_pupil_settings(data)
        head_x = decode_head_x(data, config)
        migrated_neural = data["version"] < 9 and hasattr(tongue, "measurement")
        if migrated_neural:
            from .lip_boundary import LipBoundaryModel
            tongue, tongue_range = LipBoundaryModel(), None
        active_segment = self.tongue_model if hasattr(self.tongue_model, "measurement") else None
        if active_segment is not None and not hasattr(tongue, "measurement"):
            tongue, tongue_range = active_segment, None
        elif active_segment is not None and getattr(tongue,"measurement",None) == active_segment.measurement:
            tongue.path = active_segment.path
        self.expire()
        self._clear_calibration()
        self._invalidate("left_eye_open", "right_eye_open", "head_y", "head_x", "tongue_x", "tongue_y", "gaze_x", "gaze_y")
        self.config, self.eyes, self.head, self.tongue_model = config, eyes, head, tongue
        self.head_x = head_x
        self.winks = winks
        self.pupil_settings = pupil_options
        self.tongue_range = tongue_range
        self.pipeline.tracker.max_gap_ms = config.stale_ms
        self.notice = "Profile loaded. Check live readings; output remains stopped."
        if data["settings"].get("head_mode", "position") == "position":
            self.notice += " Old image-position head fit removed; run the head pitch guide. Other compatible fits retained."
        if data["version"]<5 and data.get("tongue") is not None:
            self.notice += " Old centroid tongue calibration removed; repeat appearance and tip range. Compatible eyes/pitch retained."
        if data["version"] in (6, 7) and data.get("pupil") is not None:
            self.notice += " Old pupil fit removed; direct MediaPipe direction needs no calibration."
        if active_segment is not None and data.get("tongue_measurement") != active_segment.measurement:
            self.notice += " Incompatible tongue range removed; this backend needs its own position guide."
        if migrated_neural:
            self.notice += " Old neural tongue range removed; inspect the new lip-boundary color detector and learn its range."
        if tongue is not None:
            self.notice += (" Recheck saved tongue range." if tongue_range else
                            " Run tongue position guide to learn a personal range.")
        if eyes and not winks:
            self.notice += " Run eye calibration for wink recognition; legacy closures cannot click."

    def _invalidate(self, *keys):
        guide=self.movement_guide
        if guide and not guide.active and (("head_y" in keys and guide.kind=="head")
                or ("head_x" in keys and guide.kind=="head_x")
                or ("tongue_x" in keys and guide.kind=="tongue")):
            self.movement_guide=None
        if self.frame:
            if "eye_intent" in self.frame:
                intent=dict(self.frame["eye_intent"])
                for side in ("left","right"):
                    if side+"_eye_open" in keys:
                        intent[side]=dict(value=None,known=False,state="unknown")
                        self.wink_readings.pop(side,None)
                self.frame=dict(self.frame,eye_intent=intent)
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
            self.winks.pop(target.split("_")[0], None)
            self.eyes.pop(target.split("_")[0], None)
            self._invalidate(target.split("_")[0] + "_eye_open")
        if target.startswith("head_"):
            self.head = None
            self._invalidate("head_y")
        if target == "tongue_absent":
            self._invalidate("tongue_x", "tongue_y")
            self.tongue_model = None
            self.tongue_range = None
            self.validation.clear()
            self.positives = []
            self.tongue_marks = []
            self.frozen_crop = None
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
        return (self.job is not None or bool(self.eye_guide and self.eye_guide.active)
                or bool(self.movement_guide and self.movement_guide.active))

    def _eye_guide_config(self, rest_seconds, kind):
        self._require_subject()
        if (self.job is not None or self.movement_guide and self.movement_guide.active
                or self.eye_guide and self.eye_guide.active and self.eye_guide.kind != kind):
            raise ValueError("Finish or cancel the current collection first")
        if rest_seconds is not None:
            try:
                rest_ms = float(rest_seconds) * 1000
            except (ValueError, TypeError) as exc:
                raise ValueError("Rest between steps must be 0–30 seconds") from exc
            return replace(self.config, eye_rest_ms=rest_ms)
        return self.config

    def start_eye_guide(self, rest_seconds=None):
        self.config = self._eye_guide_config(rest_seconds, "geometry")
        self.eyes.clear()
        self.winks.clear()
        for target in list(self.samples):
            if target.startswith(("left_", "right_")):
                del self.samples[target]
        self._invalidate("left_eye_open", "right_eye_open")
        self.generation += 1
        self.eye_guide = EyeCalibrationFlow(self.config)
        self.notice = "Eye open/closed calibration: follow the dot. Train wink actions separately afterward."

    def start_wink_guide(self, rest_seconds=None):
        config = self._eye_guide_config(rest_seconds, "winks")
        if not self.eyes:
            raise ValueError("Complete eye open/closed calibration before starting Wink action")
        self.config = config
        self.winks.clear()
        self._invalidate("left_eye_open", "right_eye_open")
        self.generation += 1
        self.eye_guide = EyeCalibrationFlow(self.config, eyes=self.eyes)
        self.notice = "Wink action: eye open/closed calibration retained. Retry this stage independently."

    def present_eye_step(self, index, phase=None, generation=None):
        self.expire()
        if self.eye_guide and (generation is None or generation == self.generation):
            self.eye_guide.present(index, self.clock(), phase)

    def cancel(self):
        self.async_tongue.invalidate()
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.notice = "Collection cancelled"

    def start_movement_guide(self, kind, recheck=False):
        self._require_subject()
        self._require_idle()
        if kind == "pupil":
            raise ValueError("Pupils use direct MediaPipe direction; no calibration is required")
        if kind not in ("head","head_x","tongue") or type(recheck) is not bool:
            raise ValueError("Choose head pitch, head yaw or tongue calibration")
        saved = self.tongue_range if kind == "tongue" else None
        if recheck and saved is None:
            raise ValueError("A saved range is required for rechecking")
        if kind=="tongue" and self.tongue_model is None:
            raise ValueError("Train tongue appearance first: empty mouth, freeze/mark tongue, fit")
        if kind=="head":
            self.head=None
            self._invalidate("head_y")
        elif kind=="head_x":
            # A failed retry must not discard a previously usable horizontal fit.
            self._invalidate("head_x")
        else:
            if not recheck:self.tongue_range=None
            self.validation.clear()
            self._invalidate("tongue_x","tongue_y")
        self.movement_guide=MovementGuide(kind,self.config,existing=saved if recheck else None)
        self.generation+=1
        self.notice=f"Guided {kind}: follow the target at comfortable limits"

    def present_movement_step(self, index, phase, generation=None):
        self.expire()
        if generation is not None and generation!=self.generation:
            return
        if self.movement_guide:
            self.movement_guide.present(index,self.clock(),phase)

    def retry_tongue_step(self):
        self._require_subject()
        self._require_idle()
        guide = self.movement_guide
        if guide is None or guide.kind not in ("tongue","head_x") or guide.passed:
            raise ValueError("There is no failed tongue or Head X pose to retry")
        guide.retry()
        self.generation += 1
        self.notice = "Retry this Head X pose; follow the preparation and capture cues." if guide.kind=="head_x" else "Retry this tongue pose. Get comfortable, then press I'm in position — capture."

    def _guide_movement(self, timestamp):
        guide=self.movement_guide
        if not guide or not guide.active:return
        if guide.kind in ("head", "head_x"):
            feature=self.features[guide.kind]
            guide.feed(timestamp,(feature.value,),feature.quality>0)
        else:
            value=self.tongue.xy
            if guide.steps[guide.index][0]=="absence":
                value=(1,) if self.tongue.candidate_present else None
            usable = self.crop is not None and self.features["face"].quality > 0
            usable = usable and not (self.tongue_model and self.tongue_model.report.get("error"))
            if self.independent_tongue:
                if self.async_tongue.new:
                    guide.feed(self.async_tongue.latest.job.timestamp_ms, value, usable, finish=False)
                # Grace admits late evidence from this window, never later poses.
                guide.advance(timestamp, grace_ms=self.config.stale_ms)
            else:
                guide.feed(timestamp, value, usable)
        if not guide.active:
            self.notice=guide.report
            if guide.passed:
                if guide.kind=="head":
                    self.head=guide.fits["y"]
                elif guide.kind=="head_x":
                    self.head_x=guide.fits["x"]
                else:
                    self.tongue_range=dict(guide.fits)
                    count=sum(v["samples"] for v in guide.checks.values())
                    rate=sum(v["samples"]*v["detected_fraction"] for v in guide.checks.values())/count
                    self.validation={"validate_absent":guide.absence,
                                     "validate_visible":{"passed":True,"detected_fraction":rate,"samples":count}}

    def use_lip_boundary(self):
        from .lip_boundary import LipBoundaryModel
        self._require_idle()
        self.reset_tongue()
        self.tongue_model = LipBoundaryModel()
        self.notice = "Lip-boundary color detector ready. Inspect the outline/extension, then learn its position range."

    def load_tongue_model(self, path):
        from .tongue_segment import SegmentedTongueModel
        self._require_idle()
        model = SegmentedTongueModel(path)
        model.verify_file()
        self.reset_tongue()
        self.tongue_model = model
        self.notice = "Local tongue segmentation ready. Inspect its mask, then start the position guide."

    def set_pupil_sensitivity(self, x, y):
        self._require_idle()
        options = pupil_settings(dict(measurement=PUPIL_MEASUREMENT, x_sensitivity=x, y_sensitivity=y))
        self.pupil_settings = options
        self._invalidate("gaze_x", "gaze_y")
        self.generation += 1
        self.notice = "Pupil sensitivity updated; direct measurements resume on the next capture. Other fits retained."

    def _require_idle(self):
        if self.calibrating:
            raise ValueError("Finish or cancel the current collection first")

    def freeze_mouth(self):
        self._require_subject()
        self._require_idle()
        if self.crop is None or self.features.get("face") is None or self.features["face"].quality == 0:
            raise ValueError("A visible, sufficiently open mouth is required")
        self.frozen_crop = self.crop
        self.tongue_marks = []
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
        self.tongue_marks = (self.tongue_marks + [(x, y)])[-40:]
        self.tongue_model = None
        self.tongue_range = None
        self.validation.clear()
        self.notice = f"Added tongue patch ({len(self.positives)} positive pixels). Fit when both classes are collected."

    def clear_tongue_marks(self):
        self._require_idle()
        self._invalidate("tongue_x", "tongue_y")
        self.positives = []
        self.tongue_marks = []
        self.tongue_model = self.tongue_range = None
        self.validation.clear()
        self.tongue = TongueResult()
        self.notice = "Tongue marks cleared; background kept. Freeze a visible tongue and mark tissue again."
        self.generation += 1

    def fit_tongue(self):
        self._require_subject()
        self._require_idle()
        model = TongueModel.fit(self.positives, self.negatives, self.config.tongue_margin)
        self._invalidate("tongue_x", "tongue_y")
        self.tongue_model = model
        self.tongue_range = None
        self.validation.clear()
        self.frozen_crop = None
        self.notice = "Appearance model fitted. Inspect the mask, then start tongue position guide."

    def reset_head_x(self):
        if self.movement_guide and self.movement_guide.kind == "head_x":
            self.movement_guide = None
        self._require_idle()
        self.head_x = None
        self._invalidate("head_x")
        self.generation += 1
        self.notice = "Head X calibration cleared; vertical pitch and other completed fits retained."

    def reset_tongue(self):
        self.async_tongue.invalidate()
        segment = self.tongue_model if hasattr(self.tongue_model, "measurement") else None
        # Reset must work during this channel's collection, including failed or
        # paused guides, without cancelling unrelated eye/head work.
        if self.job and self.job.target in ("tongue_absent", "validate_absent", "validate_visible"):
            self.job = None
        if self.movement_guide and self.movement_guide.kind == "tongue":
            self.movement_guide = None
        self._require_idle()
        self._invalidate("tongue_x", "tongue_y")
        self.job = None
        self.positives, self.negatives = [], []
        self.tongue_marks = []
        self.tongue_model = segment
        if segment is not None: segment.reset_tracking()
        self.tongue_range = None
        self.validation.clear()
        self.frozen_crop = None
        self.samples = {key: value for key, value in self.samples.items()
                        if key not in ("tongue_absent", "validate_absent", "validate_visible")}
        self.tongue = TongueResult()
        self.generation += 1
        self.notice = ("Tongue range cleared; local detector retained. Inspect its overlay, then start position guide." if segment else
                       "Tongue reset. Start at 1: open your mouth with tongue hidden, then capture background.")
        self.reasons["tongue"] = "Tongue model uncalibrated"

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
        if self.independent_tongue and job.target.startswith(("tongue_", "validate_")):
            if timestamp >= job.end_ms + self.config.stale_ms:
                self._finish_collection()
                return
            if not self.async_tongue.new:
                return
            timestamp = self.async_tongue.latest.job.timestamp_ms
            if timestamp >= job.end_ms:
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
            if (self.crop is not None and self.features["face"].quality > 0
                    and not (self.independent_tongue and self.tongue_model.report.get("error"))):
                if len(job.values) < 512:
                    job.values.append(int(self.tongue.candidate_present if target=="validate_absent" else self.tongue.xy is not None))
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
        self.pupil = PupilReading()
        self.wink_vectors = {}
        self.wink_readings = {}
        self.crop = None
        self.tongue = TongueResult()
        self.reasons = {}
        if self.selected:
            observation = self.observations[self.selected]
            self.features = analyze_features(captured.bgr, observation, self.config)
            self.wink_vectors = measure_winks(observation,self.features)
            self.pupil = measure_pupils(observation, self.features)
            self.crop, mouth_reason = mouth_crop(captured.bgr, observation, self.config,
                lip_boundary=getattr(self.tongue_model,"backend",None)=="lip-boundary")
            if self.independent_tongue:
                self.tongue = self.async_tongue.update(
                    frame, self.crop, self.features["face"].quality, self.tongue_model,
                    self.config, self.generation, self.clock())
            elif self.crop is not None and self.features["face"].quality > 0 and self.tongue_model is not None:
                self.tongue = self.tongue_model.detect(self.crop, self.config, timestamp_ms=frame["timestamp_ms"])
            elif self.crop is None:
                self.tongue.reason = mouth_reason
            elif self.features["face"].quality == 0:
                self.tongue.reason = self.features["face"].reason
            if self.tongue_model is not None and self.tongue.xy is None:
                self.tongue_model.reset_tracking()
            self._collect_frame(frame["timestamp_ms"])
            self._guide_movement(frame["timestamp_ms"])
            if self.eye_guide and self.eye_guide.active:
                self.eye_guide.feed(frame["timestamp_ms"], self.features, self.wink_vectors)
                if not self.eye_guide.active:
                    if self.eye_guide.kind == "geometry":
                        self.eyes = dict(self.eye_guide.fits)
                    else:
                        self.winks = dict(self.eye_guide.models)
                    self.notice = self.eye_guide.report
            values = {}
            for side in ("left", "right"):
                feature, calibration = self.features[side], self.eyes.get(side)
                reason = feature.reason
                if calibration is None:
                    reason = "Complete Eye open/closed calibration"
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
                self.reasons["head"] = "Run guided head calibration"
            elif feature.quality > 0 and feature.value is not None:
                value = self.head.normalize(feature.value)
                values["head_y"] = measurement(value, feature.quality)
                self.reasons["head"] = "Calibrated head Y" if value is not None else "Outside calibrated head range"
            feature = self.features["head_x"]
            self.reasons["head_x"] = feature.reason
            if self.head_x is None:
                self.reasons["head_x"] = "Run guided horizontal head calibration"
            elif feature.quality > 0 and feature.value is not None:
                limits = sorted((self.head_x.low, self.head_x.high))
                bounded = max(limits[0], min(limits[1], feature.value))
                value = self.head_x.normalize(bounded)
                values["head_x"] = measurement(value, feature.quality)
                self.reasons["head_x"] = ("Head X at calibrated limit · tracking remains valid"
                                           if bounded != feature.value else "Calibrated head X")
            self.reasons["pupil"] = self.pupil.reason
            xy = normalize_pupils(self.pupil.xy, self.pupil_settings)
            if xy is not None:
                values["gaze_x"], values["gaze_y"] = [measurement(v, self.pupil.quality) for v in xy]
                self.reasons["pupil"] = "Direct MediaPipe iris direction · no calibration"
            passed = all(self.validation.get(name, {}).get("passed", False) for name in ("validate_absent", "validate_visible"))
            self.reasons["tongue"] = self.tongue.reason
            if self.tongue.xy is not None:
                if passed and self.tongue_range:
                    quality = min(self.tongue.quality, self.features["face"].quality)
                    if self.independent_tongue and self.async_tongue.latest:
                        quality = min(quality, self.async_tongue.latest.job.face_quality)
                    xy=[self.tongue_range[key].normalize(value) for key,value in zip(("x","y"),self.tongue.xy)]
                    if all(value is not None for value in xy):
                        values["tongue_x"] = measurement(xy[0], quality)
                        values["tongue_y"] = measurement(xy[1], quality)
                        self.reasons["tongue"]="Calibrated tongue front-edge position"
                    else:
                        self.reasons["tongue"]="Outside calibrated tongue range"
                else:
                    self.reasons["tongue"] = "Candidate only: run tongue position guide" if not self.tongue_range else "Recheck saved tongue range before valid output"
            frame["faces"] = [make_face(face["subject_id"], values if face["subject_id"] == self.selected else {})
                              for face in frame["faces"]]
        frame["diagnostic_only"] = True
        frame["position_space"] = "personal_tongue_tip_v1"
        frame["tongue_measurement"] = getattr(self.tongue_model, "measurement", TONGUE_MEASUREMENT)
        frame["gaze_measurement"] = PUPIL_MEASUREMENT
        if self.independent_tongue:
            frame["tongue_sample"] = self.async_tongue.sample(frame, SINGLE_SUBJECT)
        intent = dict(format="eye_intent_v1",subject_id=SINGLE_SUBJECT,
                      **{key:frame[key] for key in ("session_id","sequence","timestamp_ms")})
        signals = frame["faces"][0]["signals"] if frame["faces"] else {}
        for side in ("left","right"):
            raw = signals.get(side+"_eye_open",{})
            model, vector = self.winks.get(side), self.wink_vectors.get(side)
            score = wink_score(model,vector) if model else None
            opened = raw.get("valid") and raw.get("value")==1
            closed = raw.get("valid") and raw.get("value")==0
            bit = 0 if opened else classify_wink(model,vector) if closed and model else None
            intent[side] = dict(value=bit,known=bit is not None,
                                state="open" if opened else "wink" if bit==1 else "closed" if bit==0 else "unknown")
            self.wink_readings[side] = dict(intent[side],score=score,features=vector,
                                           calibrated=model is not None)
        frame["eye_intent"] = intent
        self.frame = frame
        self._record()
        return frame

    def _record(self):
        frame = self.frame
        signals = next((f["signals"] for f in frame["faces"] if f["subject_id"] == self.selected), {})
        row = {"session_id": frame["session_id"], "sequence": frame["sequence"], "timestamp_ms": frame["timestamp_ms"],
               "position_space": frame["position_space"], "tongue_measurement": frame["tongue_measurement"],
               "tongue_raw_units": "mouth_widths",
               "tongue_tip_x": self.tongue.xy[0] if self.tongue.xy else None,
               "tongue_tip_y": self.tongue.xy[1] if self.tongue.xy else None,
               "tongue_region_x": self.tongue.centroid[0] if self.tongue.centroid else None,
               "tongue_region_y": self.tongue.centroid[1] if self.tongue.centroid else None,
               "tongue_candidate_present": self.tongue.candidate_present,
               "tongue_tip_extension": self.tongue.extension,
               "tongue_tip_reason": self.tongue.reason,
               "subject_id": SINGLE_SUBJECT, "calibration_generation": self.generation, "head_mode": self.config.head_mode,
               "head_raw_units": "image_height_fraction" if self.config.head_mode == "position" else "degrees",
               "mouth_opening_ratio": self.crop.opening_ratio if self.crop else None,
               "mouth_width_px": self.crop.width_px if self.crop else None,
               "tongue_candidate_x": self.tongue.xy[0] if self.tongue.xy else None,
               "tongue_candidate_y": self.tongue.xy[1] if self.tongue.xy else None,
               "tongue_area_fraction": self.tongue.area_fraction, "tongue_quality": self.tongue.quality}
        row.update(gaze_measurement=PUPIL_MEASUREMENT,
                   pupil_x_sensitivity=self.pupil_settings["x_sensitivity"],
                   pupil_y_sensitivity=self.pupil_settings["y_sensitivity"],
                   pupil_raw_x=self.pupil.xy[0] if self.pupil.xy else None,
                   pupil_raw_y=self.pupil.xy[1] if self.pupil.xy else None,
                   pupil_reason=self.reasons.get("pupil", self.pupil.reason),
                   tongue_inference_ms=(self.tongue_model.report.get("inference_ms") if self.tongue_model else None),
                   tongue_model_confidence=(self.tongue_model.report.get("confidence") if self.tongue_model else None))
        for side in ("left", "right"):
            eye = self.pupil.eyes.get(side, {})
            for axis, index in (("x", 0), ("y", 1)):
                row[side+"_pupil_"+axis] = eye["xy"][index] if eye.get("xy") else None
        for side in ("left", "right", "head", "head_x"):
            feature = self.features.get(side)
            row[side + "_raw"] = feature.value if feature else None
            row[side + "_quality"] = feature.quality if feature else 0
            row[side + "_reason"] = self.reasons.get(side, "No selected subject")
            for key in ("brightness", "focus", "clipped_fraction"):
                row[side + "_" + key] = feature.metrics.get(key) if feature else None
        row["head_x_raw_units"] = "degrees"
        row["head_x_saturated"] = bool(self.head_x and self.features.get("head_x")
            and self.features["head_x"].value is not None and self.features["head_x"].quality > 0
            and not min(self.head_x.low,self.head_x.high) <= self.features["head_x"].value <= max(self.head_x.low,self.head_x.high))
        for key in ("left_eye_open", "right_eye_open", "head_y", "head_x", "tongue_x", "tongue_y", "gaze_x", "gaze_y"):
            item = signals.get(key, {})
            row[key] = item.get("value")
            row[key + "_valid"] = item.get("valid", False)
            row[key + "_confidence"] = item.get("confidence", 0)
        for side in ("left", "right"):
            reading = self.wink_readings.get(side,{})
            row[side+"_wink_bit"] = reading.get("value")
            row[side+"_wink_score"] = reading.get("score")
            for index,key in enumerate(NAMES):
                row[side+"_"+key] = reading["features"][index] if reading.get("features") else None
            calibration = self.eyes.get(side)
            row[side + "_closed_limit_raw"] = calibration.closed_limit if calibration else None
            row[side + "_open_limit_raw"] = calibration.open_limit if calibration else None
            row[side + "_threshold_raw"] = (calibration.closed + calibration.threshold * (calibration.opened - calibration.closed)) if calibration else None
            value = signals.get(side + "_eye_open", {}).get("value")
            row[side + "_closed_bit"] = 1 - value if value is not None else None
        for name in ("validate_absent", "validate_visible"):
            row[name + "_passed"] = self.validation.get(name, {}).get("passed", False)
        row["tongue_reason"] = self.reasons.get("tongue", "No selected subject")
        source = frame.get("tongue_sample", frame)
        row.update(tongue_sequence=source["sequence"], tongue_timestamp_ms=source["timestamp_ms"],
                   tongue_age_ms=(frame["timestamp_ms"]-source["timestamp_ms"] if source["timestamp_ms"] is not None else None),
                   tongue_new=not self.independent_tongue or self.async_tongue.new)
        if self.independent_tongue and not self.async_tongue.new:
            # The plot's existing dark-hold renderer supplies the previous height.
            # Keep numeric held control values only in the timestamped SignalFrame.
            for key in ("tongue_tip_x", "tongue_tip_y", "tongue_x", "tongue_y",
                        "tongue_candidate_x", "tongue_candidate_y", "tongue_region_x", "tongue_region_y"):
                row[key] = None
            row.update(tongue_x_valid=False, tongue_y_valid=False, tongue_quality=0)
        self.trace.append(row)

    def state(self):
        self.expire()
        return {"frame": self.frame, "selected": self.selected, "notice": self.notice,
                "scope_subject": SINGLE_SUBJECT,
                "pupil": asdict(self.pupil), "pupil_settings": dict(self.pupil_settings),
                "tongue_worker": self.async_tongue.state(self.clock()) if self.independent_tongue else None,
                "tongue_backend": getattr(self.tongue_model,"backend","color"),
                "wink_readings": dict(self.wink_readings),
                "wink_models": {side:model["report"] for side,model in self.winks.items()},
                "features": {k: asdict(v) for k, v in self.features.items()}, "reasons": dict(self.reasons),
                "eyes": {k: asdict(v) for k, v in self.eyes.items()}, "head": asdict(self.head) if self.head else None,
                "head_x": asdict(self.head_x) if self.head_x else None,
                "tongue_range": {k:asdict(v) for k,v in self.tongue_range.items()} if self.tongue_range else None,
                "movement_guide": self.movement_guide.state(self.clock()) if self.movement_guide else None,
                "samples": {k: len(v) for k, v in self.samples.items()},
                "tongue_pixels": {"positive": len(self.positives), "negative": len(self.negatives)},
                "tongue_marks": list(self.tongue_marks),
                "tongue_fit": self.tongue_model.report if self.tongue_model else None,
                "validation": dict(self.validation), "collecting": self.job.target if self.job else None,
                "collection_phase": ("prepare" if self.clock() < self.job.start_ms else "capture") if self.job else None,
                "collection_remaining_ms": max(0, (self.job.start_ms if self.clock() < self.job.start_ms else self.job.end_ms) - self.clock()) if self.job else None,
                "generation": self.generation, "config": self.config.to_dict(),
                "eye_guide": self.eye_guide.state(self.clock()) if self.eye_guide else None,
                "calibrating": self.calibrating}
