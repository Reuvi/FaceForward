"""Detector-only calibration state. No Processing, Drivers, UI, or OS events."""

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from .calibration import AxisCalibration, EyeCalibration
from .features import DetectionConfig, analyze_features
from .wink_guide import EyeCalibrationFlow
from .movement_guide import MovementGuide
from .head_guide import HeadPitchGuide
from .pupil_guide import PupilGuide
from .pupil_calibration import normalize as normalize_pupils, SPACE as PUPIL_SPACE
from .wink_model import NAMES, measure as measure_winks, score as wink_score, classify as classify_wink
from .pupil import PupilReading, measure as measure_pupils, matrix_sample as pupil_matrix, MEASUREMENT as PUPIL_MEASUREMENT
from .pipeline import VisionPipeline
from .signals import SINGLE_SUBJECT, invalid, make_face, measurement, monotonic_ms


TARGETS = ("left_open", "left_closed", "right_open", "right_closed",
           "head_neutral", "head_up", "head_down")


@dataclass
class Collection:
    target: str
    start_ms: float
    end_ms: float
    values: list = field(default_factory=list)
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
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.pupil_guide = None
        self.samples = {}
        self.eyes = {}
        self.winks = {}
        self.wink_vectors = {}
        self.wink_readings = {}
        self.head = self.head_x = None
        self.pupil_model = None
        self.pupil = PupilReading()
        self.pupil_corrected = None
        self.notice = "Single user: start a source, then calibrate or load a profile"
        self.reasons = {}
        self.trace = deque(maxlen=9000)
        self.generation = 0

    def close(self):
        """No independent model workers remain in this workbench."""

    def _clear_calibration(self):
        self.samples.clear()
        self.eyes.clear()
        self.winks.clear()
        self.wink_readings.clear()
        self.head = self.head_x = None
        self.pupil_model = None
        self.pupil = PupilReading()
        self.pupil_corrected = None
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.pupil_guide = None
        self.generation += 1

    def disconnect(self, reason="Source stopped; calibration retained"):
        """Drop live evidence and unfinished capture, retaining the user's fits."""
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.pupil_guide = None
        self.selected = None
        self.observations = {}
        self.features = {}
        self.pupil = PupilReading()
        self.pupil_corrected = None
        self.wink_vectors = {}
        self.wink_readings = {}
        self.reasons = {}
        self.notice = reason
        if self.frame is not None:
            self.frame = dict(self.frame, faces=[make_face(f["subject_id"]) for f in self.frame["faces"]])
            self.frame["pupil_matrix"] = pupil_matrix(self.frame, SINGLE_SUBJECT)
            if "eye_intent" in self.frame:
                self.frame["eye_intent"]=dict(self.frame["eye_intent"],
                    left=dict(value=None,known=False,state="unknown"),right=dict(value=None,known=False,state="unknown"))

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
        from .presets import decode_preset, decode_winks, decode_head_x, decode_pupil
        self._require_idle()
        config, eyes, head, _ = decode_preset(data)
        winks = decode_winks(data)
        head_x = decode_head_x(data, config)
        pupil_model = decode_pupil(data)
        self.expire()
        self._clear_calibration()
        self._invalidate("left_eye_open", "right_eye_open", "head_y", "head_x", "gaze_x", "gaze_y")
        self.config, self.eyes, self.head, self.head_x = config, eyes, head, head_x
        self.winks = winks
        self.pupil_model = pupil_model
        self.pipeline.tracker.max_gap_ms = config.stale_ms
        self.notice = "Profile loaded. Check live readings; output remains stopped."
        if data["settings"].get("head_mode", "position") == "position":
            self.notice += " Old image-position head fit removed; run the head pitch guide."
        if data["version"] < 12:
            self.notice += " Retired tongue state and old pupil settings discarded; run the new pupil guide."
        if eyes and not winks:
            self.notice += " Run Wink action calibration for wink recognition."

    def _invalidate(self, *keys):
        guide=self.movement_guide
        if guide and not guide.active and (("head_y" in keys and guide.kind=="head")
                or ("head_x" in keys and guide.kind=="head_x")):
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
            self.frame["pupil_matrix"] = pupil_matrix(self.frame, SINGLE_SUBJECT)

    def collect(self, target):
        self._require_subject()
        if target not in TARGETS:
            raise ValueError("Unknown calibration target")
        self._require_idle()
        if target.startswith(("left_", "right_")):
            self.winks.pop(target.split("_")[0], None)
            self.eyes.pop(target.split("_")[0], None)
            self._invalidate(target.split("_")[0] + "_eye_open")
        if target.startswith("head_"):
            self.head = None
            self._invalidate("head_y")
        self.samples.pop(target, None)
        start = self.clock() + self.config.settle_ms
        self.job = Collection(target, start, start + self.config.collect_ms)
        self.notice = "Prepare: " + target.replace("_", " ")

    @property
    def calibrating(self):
        return (self.job is not None or bool(self.eye_guide and self.eye_guide.active)
                or bool(self.movement_guide and self.movement_guide.active)
                or bool(self.pupil_guide and self.pupil_guide.active))

    def _eye_guide_config(self, rest_seconds, kind):
        self._require_subject()
        if (self.job is not None or self.pupil_guide and self.pupil_guide.active
                or self.movement_guide and self.movement_guide.active
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
        self.job = None
        self.eye_guide = None
        self.movement_guide = None
        self.pupil_guide = None
        self.notice = "Collection cancelled"

    def start_movement_guide(self, kind, recheck=False):
        self._require_subject()
        self._require_idle()
        if kind == "pupil":
            return self.start_pupil_guide()
        if kind not in ("head", "head_x") or recheck:
            raise ValueError("Choose head pitch or head yaw calibration")
        if kind=="head":
            # Keep a completed fit until every check of its replacement passes.
            self._invalidate("head_y")
        elif kind=="head_x":
            # A failed retry must not discard a previously usable horizontal fit.
            self._invalidate("head_x")
        self.movement_guide=HeadPitchGuide(self.config) if kind=="head" else MovementGuide(kind,self.config)
        self.generation+=1
        self.notice=f"Guided {kind}: follow the target at comfortable limits"

    def present_movement_step(self, index, phase, generation=None):
        self.expire()
        if generation is not None and generation!=self.generation:
            return
        if self.movement_guide:
            self.movement_guide.present(index,self.clock(),phase)

    def _require_head_y_edit(self):
        self._require_subject()
        if (self.job or self.eye_guide and self.eye_guide.active
                or self.pupil_guide and self.pupil_guide.active
                or self.movement_guide and self.movement_guide.active and self.movement_guide.kind != "head"):
            raise ValueError("Finish or cancel the other calibration first")

    def redo_head_y_step(self, role, name):
        self._require_head_y_edit()
        guide = self.movement_guide
        if not isinstance(guide, HeadPitchGuide):
            guide = HeadPitchGuide(self.config, existing=self.head)
        guide.redo(role, name)
        self.movement_guide = guide
        self._invalidate("head_y")
        self.generation += 1
        self.notice = f"Redo Head Y {name} {role}: other references and the last working fit are retained."

    def retry_movement_step(self):
        self._require_subject()
        guide = self.movement_guide
        if isinstance(guide, HeadPitchGuide):
            self._require_head_y_edit()
            guide.retry()
            self._invalidate("head_y")
            self.generation += 1
            self.notice = "Retry this Head Y step; other accepted poses are retained."
            return
        self._require_idle()
        if guide is None or guide.kind != "head_x" or guide.passed:
            raise ValueError("There is no failed Head X pose to retry")
        guide.retry()
        self.generation += 1
        self.notice = "Retry this Head X pose; follow the preparation and capture cues."

    def _guide_movement(self, timestamp):
        guide=self.movement_guide
        if not guide or not guide.active:return
        feature=self.features[guide.kind]
        guide.feed(timestamp,(feature.value,),feature.quality>0)
        if not guide.active:
            self.notice=guide.report
            if guide.passed:
                if guide.kind=="head":
                    self.head=guide.fits["y"]
                elif guide.kind=="head_x":
                    self.head_x=guide.fits["x"]

    def start_pupil_guide(self):
        self._require_subject()
        if self.pupil_guide:
            self.pupil_guide = None
        self._require_idle()
        self.pupil_guide = PupilGuide(self.config)
        self._invalidate("gaze_x", "gaze_y")
        self.generation += 1
        self.notice = "Pupil guide: first keep looking at center while moving your head, then move only your eyes."

    def present_pupil_step(self, index, phase, generation=None):
        self.expire()
        if self.pupil_guide and (generation is None or generation == self.generation):
            self.pupil_guide.present(index, self.clock(), phase)

    def retry_pupil_step(self):
        self._require_subject()
        self._require_idle()
        if not self.pupil_guide or self.pupil_guide.passed:
            raise ValueError("There is no failed pupil pose to retry")
        self.pupil_guide.retry()
        self.generation += 1

    def reset_pupils(self):
        self.pupil_guide = None
        self._require_idle()
        self.pupil_model = None
        self.pupil_corrected = None
        self._invalidate("gaze_x", "gaze_y")
        self.generation += 1
        self.notice = "Pupils reset. Eye and head calibration retained; run the pupil guide."

    def _guide_pupils(self, timestamp):
        guide = self.pupil_guide
        if not guide or not guide.active:
            return
        reading = self.pupil
        value = (*reading.xy, *reading.pose) if reading.xy is not None and reading.pose is not None else None
        guide.feed(timestamp, value, reading.quality > 0)
        if not guide.active:
            self.notice = guide.report
            if guide.passed:
                self.pupil_model = guide.model

    def _require_idle(self):
        if self.calibrating:
            raise ValueError("Finish or cancel the current collection first")

    def reset_head_x(self):
        if self.movement_guide and self.movement_guide.kind == "head_x":
            self.movement_guide = None
        self._require_idle()
        self.head_x = None
        self._invalidate("head_x")
        self.generation += 1
        self.notice = "Head X calibration cleared; vertical pitch and other completed fits retained."

    def _finish_collection(self):
        job, self.job = self.job, None
        if (len(job.values) < self.config.min_samples
                or len(job.values) < 0.8 * (len(job.values) + job.rejected)):
            self.notice = f"Rejected {job.target}: only {len(job.values)} usable samples ({job.rejected} rejected). Retry with better visibility."
            return
        target = job.target
        try:
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
        if feature is not None and feature.quality > 0 and feature.value is not None:
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
        self.pupil_corrected = None
        self.wink_vectors = {}
        self.wink_readings = {}
        self.reasons = {}
        if self.selected:
            observation = self.observations[self.selected]
            self.features = analyze_features(captured.bgr, observation, self.config)
            self.wink_vectors = measure_winks(observation,self.features)
            self.pupil = measure_pupils(observation, self.features)
            self._collect_frame(frame["timestamp_ms"])
            self._guide_movement(frame["timestamp_ms"])
            self._guide_pupils(frame["timestamp_ms"])
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
            xy, self.pupil_corrected, reason = normalize_pupils(self.pupil_model, self.pupil.xy, self.pupil.pose)
            if self.pupil.xy is not None:
                self.reasons["pupil"] = reason
            if xy is not None:
                values["gaze_x"], values["gaze_y"] = [measurement(v, self.pupil.quality) for v in xy]
                self.reasons["pupil"] = reason
            frame["faces"] = [make_face(face["subject_id"], values if face["subject_id"] == self.selected else {})
                              for face in frame["faces"]]
        frame["diagnostic_only"] = True
        frame["gaze_measurement"] = PUPIL_SPACE
        frame["pupil_matrix"] = pupil_matrix(frame, SINGLE_SUBJECT)
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
               "subject_id": SINGLE_SUBJECT, "calibration_generation": self.generation, "head_mode": self.config.head_mode,
               "head_raw_units": "image_height_fraction" if self.config.head_mode == "position" else "degrees"}
        row.update(gaze_measurement=PUPIL_SPACE, pupil_measurement=PUPIL_MEASUREMENT,
                   pupil_compensated_x=self.pupil_corrected[0] if self.pupil_corrected else None,
                   pupil_compensated_y=self.pupil_corrected[1] if self.pupil_corrected else None,
                   pupil_pose_yaw=self.pupil.pose[0] if self.pupil.pose else None,
                   pupil_pose_pitch=self.pupil.pose[1] if self.pupil.pose else None,
                   pupil_pose_roll=self.pupil.pose[2] if self.pupil.pose else None,
                   pupil_raw_x=self.pupil.xy[0] if self.pupil.xy else None,
                   pupil_raw_y=self.pupil.xy[1] if self.pupil.xy else None,
                   pupil_reason=self.reasons.get("pupil", self.pupil.reason))
        grid = frame["pupil_matrix"]
        row.update(pupil_matrix_row=grid["row"], pupil_matrix_column=grid["column"],
                   pupil_matrix_size=grid["size"], pupil_matrix_valid=grid["valid"])
        for side in ("left", "right"):
            eye = self.pupil.eyes.get(side, {})
            for key in ("lid_gap", "blink", "look_down", "look_up", "down_supported"):
                row[side+"_pupil_"+key] = eye.get(key)
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
        for key in ("left_eye_open", "right_eye_open", "head_y", "head_x", "gaze_x", "gaze_y"):
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
        self.trace.append(row)

    def state(self):
        self.expire()
        return {"frame": self.frame, "selected": self.selected, "notice": self.notice,
                "scope_subject": SINGLE_SUBJECT,
                "pupil": asdict(self.pupil),
                "pupil_corrected": self.pupil_corrected,
                "pupil_model": self.pupil_model,
                "pupil_guide": self.pupil_guide.state(self.clock()) if self.pupil_guide else None,
                "wink_readings": dict(self.wink_readings),
                "wink_models": {side:model["report"] for side,model in self.winks.items()},
                "features": {k: asdict(v) for k, v in self.features.items()}, "reasons": dict(self.reasons),
                "eyes": {k: asdict(v) for k, v in self.eyes.items()}, "head": asdict(self.head) if self.head else None,
                "head_x": asdict(self.head_x) if self.head_x else None,
                "movement_guide": self.movement_guide.state(self.clock()) if self.movement_guide else None,
                "samples": {k: len(v) for k, v in self.samples.items()},
                "collecting": self.job.target if self.job else None,
                "collection_phase": ("prepare" if self.clock() < self.job.start_ms else "capture") if self.job else None,
                "collection_remaining_ms": max(0, (self.job.start_ms if self.clock() < self.job.start_ms else self.job.end_ms) - self.clock()) if self.job else None,
                "generation": self.generation, "config": self.config.active_dict(),
                "eye_guide": self.eye_guide.state(self.clock()) if self.eye_guide else None,
                "calibrating": self.calibrating}
