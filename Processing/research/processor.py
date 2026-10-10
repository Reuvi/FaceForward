"""Experimental mappings and ordered preview actions; never sends OS input."""

from collections import deque
from copy import deepcopy
from math import exp, hypot

from .gestures import Gesture, finite
from .settings import settings
from .models import predict


def validate_packet(packet):
    fields = {
        "format",
        "timestamp_ms",
        "session_id",
        "subject_id",
        "sequence",
        "generation",
        "values",
    }
    if (
        not isinstance(packet, dict)
        or set(packet) != fields
        or packet["format"] != "face_features_v1"
    ):
        raise ValueError("Invalid feature packet")
    if not finite(packet["timestamp_ms"]) or packet["timestamp_ms"] < 0:
        raise ValueError("Invalid capture time")
    if any(
        type(packet[k]) is not int or packet[k] < 0 for k in ("sequence", "generation")
    ):
        raise ValueError("Invalid feature sequence/generation")
    if any(
        not isinstance(packet[k], str) or not packet[k]
        for k in ("session_id", "subject_id")
    ):
        raise ValueError("Invalid feature identity")
    if not isinstance(packet["values"], dict) or any(
        not isinstance(k, str) or v is not None and not finite(v)
        for k, v in packet["values"].items()
    ):
        raise ValueError("Feature values must be finite scalars or null")


class ResearchProcessor:
    def __init__(self, config=None):
        self.config = settings(config)
        self.models = {}
        self.fits = {}
        self.pose_bounds = {}
        self.trace = deque(maxlen=9000)
        self.events = deque(maxlen=2000)
        self.clicks = deque(maxlen=256)
        self.event_id = 0
        self.click_id = 0
        self.context = None
        self.last_sequence = None
        self.last_time = None
        self.trial = None
        self.cursor = [0.5, 0.5]
        self.velocity = [0.0, 0.0]
        self.last_pointer = None
        self.gates = {
            key: Gesture() for key in ("left", "right", "both", "smile", "brow")
        }
        self.event_trials = {}
        self.latches = {}
        self.previous_pose = None
        self.motion_until = 0
        self.armed = False
        self.reason = "Preview stopped"
        self.dwell_anchor = None
        self.dwell_start = None
        self.dwell_clicked = False
        self.output = {}
        self.reset()

    def reset(self, reason="Preview stopped", *, clear_context=False):
        self.armed = False
        self.reason = reason
        for gate in self.gates.values():
            gate.reset()
        self.event_trials.clear()
        self.latches.clear()
        self.last_pointer = None
        self.velocity = [0.0, 0.0]
        self.dwell_start = None
        self.dwell_anchor = None
        self.dwell_clicked = False
        self.output = dict(
            format="research_preview_v1",
            enabled=False,
            pointer_mode=self.config["pointer_mode"],
            position=None,
            velocity=[0.5, 0.5],
            scroll=0.5,
            buttons={"left": 0, "right": 0},
            dwell=0.0,
        )
        if clear_context:
            self.context = None
            self.last_time = None
            self.last_sequence = None
            self.previous_pose = None
            self.motion_until = 0

    def configure(self, data):
        candidate = settings(data)
        if candidate["pose_gate"] and not self.pose_bounds:
            raise ValueError("Record open_pose training before enabling pose gate")
        if candidate["model"] != "rules":
            for side in ("left", "right"):
                if candidate[side + "_source"] in ("left_eye", "right_eye"):
                    eye = candidate[side + "_source"].split("_")[0]
                    model = self.models.get(eye, {}).get(candidate["model"])
                    if not model or not model["validated"]:
                        raise ValueError(
                            f"{eye}: selected model needs successful held-out validation"
                        )
        self.config = candidate
        self.reset("Settings changed; explicitly start preview")

    def normalize(self, key, value):
        fit = self.fits.get(key)
        if not fit or not finite(value):
            return None
        return max(0, min(1, (value - fit["open"]) / (fit["active"] - fit["open"])))

    def emit(self, button, t, target=None):
        self.click_id += 1
        self.clicks.append(
            dict(
                id=self.click_id,
                button=button,
                timestamp_ms=t,
                position=target,
                delivery="ordered_press_release",
            )
        )

    def feed(self, packet, base, now, gaze=None):
        try:
            validate_packet(packet)
        except ValueError:
            self.reset("Invalid feature packet")
            raise
        t = packet["timestamp_ms"]
        context = (packet["session_id"], packet["subject_id"], packet["generation"])
        if self.context != context:
            self.reset("Face/calibration changed; start preview", clear_context=True)
            self.context = context
        if self.last_sequence is not None and (
            packet["sequence"] <= self.last_sequence or t <= self.last_time
        ):
            self.reset("Duplicate/out-of-order research input")
            return
        if not 0 <= now - t <= self.config["stale_ms"]:
            self.reset("Stale research input")
            return
        dt = 0 if self.last_time is None else (t - self.last_time) / 1000
        if self.last_time is not None and dt * 1000 > self.config["stale_ms"]:
            self.reset("Input gap; start preview")
        self.last_time = t
        self.last_sequence = packet["sequence"]
        v = packet["values"]
        c = self.config
        pose = [v.get(k) for k in ("yaw", "pitch", "roll")]
        motion = None
        if all(finite(x) for x in pose):
            if self.previous_pose and dt > 0:
                motion = max(abs(a - b) / dt for a, b in zip(pose, self.previous_pose))
            self.previous_pose = pose
        else:
            self.previous_pose = None
        if motion is not None and motion > c["motion_limit"]:
            self.motion_until = t + c["recovery_ms"]
        supported = not c["pose_gate"] or all(
            finite(v.get(k)) and a <= v[k] <= b
            for k, (a, b) in self.pose_bounds.items()
        )
        stable = t >= self.motion_until and supported
        values = {
            s: v.get(s + "_closure") if stable else None for s in ("left", "right")
        }

        def expression(key):
            return self.normalize(key, v.get(key)) if stable else None

        smiles = [expression("mouthSmile" + s) for s in ("Left", "Right")]
        values["smile"] = max(smiles) if all(x is not None for x in smiles) else None
        values["brow"] = expression("browInnerUp")
        values["both"] = (
            min(values["left"], values["right"])
            if all(values[s] is not None for s in ("left", "right"))
            else None
        )
        row = dict(
            t=t / 1000,
            sequence=packet["sequence"],
            scope_context=context,
            pose_speed=motion,
            **v,
        )
        row["eye_overlap"] = (
            float(all(values[s] >= c["activation"] for s in ("left", "right")))
            if all(values[s] is not None for s in ("left", "right"))
            else None
        )
        row.update(
            {
                f"{s}_blink_normalized": expression("eyeBlink" + s.title())
                for s in ("left", "right")
            }
        )
        button_states = {"left": 0, "right": 0}
        for channel, gate in self.gates.items():
            mapped = [
                button
                for button in ("left", "right")
                if c[button + "_source"]
                == dict(
                    left="left_eye",
                    right="right_eye",
                    both="both_eyes",
                    smile="smile",
                    brow="brow",
                )[channel]
            ]
            side = channel if channel in ("left", "right") else "left"
            opposite = values["right" if side == "left" else "left"]
            suffix = side.title()
            features = dict(
                blink=expression("eyeBlink" + suffix),
                squint=v.get("eyeSquint" + suffix),
                cheek=v.get("cheekSquint" + suffix),
                brow=v.get("browDown" + suffix),
                brow_gap=v.get(side + "_brow_gap"),
                cheek_gap=v.get(side + "_cheek_gap"),
                pose_speed=motion,
            )
            before = gate.onset
            event = gate.feed(
                t,
                values[channel],
                opposite,
                features,
                c,
                c[
                    (
                        side
                        if channel in ("left", "right")
                        else mapped[0]
                        if mapped
                        else "left"
                    )
                    + "_min_ms"
                ],
                strict=c["policy"] == "strict" and channel in ("left", "right"),
            )
            if before is None and gate.onset is not None:
                self.event_trials[channel] = deepcopy(self.trial)
                self.latches[channel] = (
                    list(self.cursor)
                    if self.last_pointer is not None
                    and t - self.last_pointer <= c["stale_ms"]
                    else None
                )
            state = gate.state(t)
            row.update(
                {
                    channel + "_" + k: state[k]
                    for k in ("elapsed_ms", "close_speed", "open_speed", "peak")
                }
            )
            row[channel + "_qualified"] = (
                1
                if state["phase"] == "QUALIFIED"
                else 0
                if values[channel] is not None
                else None
            )
            if values[channel] is None:
                for key in ("elapsed_ms", "close_speed", "open_speed", "peak"):
                    row[channel + "_" + key] = None
            for button in mapped:
                button_states[button] = int(self.armed and gate.held)
            if event:
                self.event_id += 1
                trial = self.event_trials.pop(channel, None) or {}
                event.update(
                    id=self.event_id,
                    channel=channel,
                    trial_id=trial.get("id"),
                    label=trial.get("label", "unlabeled"),
                    role=trial.get("role", "train"),
                    decision_ms=t,
                    sample_age_ms=now - t,
                    latency_ms=t - event["onset_ms"],
                    session_id=packet["session_id"],
                    subject_id=packet["subject_id"],
                    generation=packet["generation"],
                    model_score=None,
                    emitted=False,
                )
                if (
                    c["model"] != "rules"
                    and event["accepted"]
                    and channel in ("left", "right")
                ):
                    model = self.models.get(channel, {}).get(c["model"])
                    score = (
                        predict(model, event) if model and model["validated"] else None
                    )
                    event["model_score"] = score
                    event["accepted"] = score is not None and score >= 0.5
                    if not event["accepted"]:
                        event["reason"] = "event model rejected / unavailable"
                target = self.latches.pop(channel, None)
                if self.armed and event["accepted"] and c["click_mode"] == "release":
                    if (
                        c["pointer_mode"] != "gaze"
                        or target is not None
                        and gaze is not None
                    ):
                        for button in mapped:
                            self.emit(
                                button,
                                t,
                                target if c["pointer_mode"] == "gaze" else None,
                            )
                        event["emitted"] = bool(mapped)
                self.events.append(event)
        fresh_pointer = False
        position = None
        scroll = 0.5
        if self.armed:
            if c["pointer_mode"] == "gaze":
                if stable and gaze is not None:
                    alpha = (
                        1
                        if not self.last_pointer or c["gaze_smoothing_ms"] == 0
                        else 1 - exp(-dt * 1000 / c["gaze_smoothing_ms"])
                    )
                    self.cursor = [
                        max(0, min(1, a + alpha * (b - a)))
                        for a, b in zip(self.cursor, gaze)
                    ]
                    fresh_pointer = True
                    position = list(self.cursor)
                self.velocity = [0.0, 0.0]
            else:
                if c["pointer_mode"] == "tongue":
                    fresh_pointer = bool(
                        base.get("enabled")
                        and base.get("diagnostics", {}).get("raw_pointer") is not None
                    )
                    target = (
                        [2 * base[k] - 1 for k in ("pointer_x", "pointer_y")]
                        if fresh_pointer
                        else [0.0, 0.0]
                    )
                else:
                    fresh_pointer = stable and all(
                        finite(v.get(k)) for k in ("face_x", "face_y")
                    )
                    target = []
                    for key, center in (
                        ("face_x", c["head_center_x"]),
                        ("face_y", c["head_center_y"]),
                    ):
                        offset = (
                            (v[key] - center) / c["head_range"] if fresh_pointer else 0
                        )
                        target.append(
                            0
                            if abs(offset) <= c["head_deadzone"]
                            else max(-1, min(1, offset))
                        )
                if fresh_pointer:
                    for i in (0, 1):
                        delta = target[i] - self.velocity[i]
                        self.velocity[i] += max(-4 * dt, min(4 * dt, delta))
                        self.cursor[i] = max(
                            0, min(1, self.cursor[i] + self.velocity[i] * dt * 0.6)
                        )
                else:
                    self.velocity = [0.0, 0.0]
            if fresh_pointer:
                self.last_pointer = t
            if c["scroll_enabled"] and base.get("enabled"):
                scroll = base.get("scroll_y", 0.5)
        progress = 0.0
        dwell_button = next(
            (b for b in ("left", "right") if c[b + "_source"] == "dwell"), None
        )
        if self.armed and dwell_button and fresh_pointer:
            if (
                self.dwell_anchor is None
                or hypot(*(a - b for a, b in zip(self.cursor, self.dwell_anchor)))
                > c["dwell_radius"]
            ):
                self.dwell_anchor = list(self.cursor)
                self.dwell_start = t
                self.dwell_clicked = False
            if self.dwell_start is None:
                self.dwell_start = t
            progress = min(1, (t - self.dwell_start) / c["dwell_ms"])
            if progress >= 1 and not self.dwell_clicked:
                self.emit(
                    dwell_button,
                    t,
                    list(self.cursor) if c["pointer_mode"] == "gaze" else None,
                )
                self.dwell_clicked = True
        else:
            # Invalid intervals pause dwell; leaving the target is still required after a click.
            self.dwell_start = None
        self.output = dict(
            format="research_preview_v1",
            enabled=self.armed,
            pointer_mode=c["pointer_mode"],
            position=position,
            velocity=[(x + 1) / 2 for x in self.velocity],
            scroll=scroll,
            buttons=button_states,
            dwell=progress,
        )
        row.update(
            gaze_x=None if gaze is None else gaze[0],
            gaze_y=None if gaze is None else gaze[1],
            pointer_x=self.cursor[0] if fresh_pointer else None,
            pointer_y=self.cursor[1] if fresh_pointer else None,
        )
        self.trace.append(row)
        return True

    def preview(self, after_click=0):
        """Ordered events with a cursor. A lagging consumer must reset on click_gap."""
        if type(after_click) is not int or not 0 <= after_click <= self.click_id:
            raise ValueError("Invalid click cursor")
        result = deepcopy(self.output)
        result["click_cursor"] = self.click_id
        result["click_gap"] = bool(
            self.clicks and after_click < self.clicks[0]["id"] - 1
        )
        result["clicks"] = deepcopy([e for e in self.clicks if e["id"] > after_click])
        return result

    def expire(self, now):
        if (
            self.last_time is not None
            and now - self.last_time > self.config["stale_ms"]
        ):
            self.reset("Research input stale; start again")
