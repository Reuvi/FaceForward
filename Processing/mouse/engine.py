"""Clock-injected mouse processor. No sleeping, networking, or OS side effects."""

from collections import deque
import math

from .config import MouseConfig
from .signals import decode, finite, SubjectMissing
from Processing.eye_samples import eye_sample, is_fresh_sample


def length(vector):
    return math.sqrt(sum(v * v for v in vector))


def centered(value, center):
    return (value - center) / (center if value < center else 1 - center)


class EyeGate:
    """One independent eye: open baseline → dwell → held → debounced release."""

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.down = False
        self.ready = False
        self.closed_since = None
        self.open_since = None
        self.progress = 0.0

    def sample(self, closed, timestamp, *, known=True):
        if not known or closed is None:
            self.reset()
            return
        if not closed:
            self.closed_since = None
            self.progress = 0.0
            if self.open_since is None:
                self.open_since = timestamp
            if timestamp - self.open_since >= self.config.release_ms:
                self.down = False
                self.ready = True
            return
        self.open_since = None
        if not self.ready:
            return
        if self.closed_since is None:
            self.closed_since = timestamp
        self.progress = min(1.0, (timestamp - self.closed_since) / self.config.dwell_ms)
        if self.progress >= 1.0:
            self.down = True


class AxisFilter:
    """Buffered interpolation → radial dead zone → curve → boost → limited velocity."""

    def __init__(self, config, dimensions):
        self.config = config
        self.dimensions = dimensions
        self.history = deque(maxlen=512)
        self.valid = False
        self.reset_motion()

    def reset_motion(self):
        self.velocity = (0.0,) * self.dimensions
        self.target = self.velocity
        self.position = None
        self.active = False
        self.boost = 0.0

    def clear(self):
        self.history.clear()
        self.valid = False
        self.reset_motion()

    def normalize(self, position):
        config = self.config
        if self.dimensions == 1:
            return (centered(position[0], config.center_y) * (-1 if config.invert_y else 1),)
        return (centered(position[0], config.center_x) * (-1 if config.invert_x else 1),
                centered(position[1], config.center_y) * (-1 if config.invert_y else 1))

    def push(self, value, timestamp):
        if value is None:
            self.clear()
            return
        point = (value,) if self.dimensions == 1 else tuple(value)
        # SignalFrame allows a newer sequence at the same capture timestamp.
        # Replace that point; do not divide by a zero sample interval.
        if self.history and timestamp == self.history[-1][0]:
            self.history[-1] = (timestamp, point)
            self.valid = True
            return
        if self.history:
            previous_time, previous = self.history[-1]
            dt = (timestamp - previous_time) / 1000.0
            current, prior = self.normalize(point), self.normalize(previous)
            jump = length(tuple(a - b for a, b in zip(current, prior)))
            if dt > 0 and jump >= self.config.jump_threshold and length(current) > self.config.deadzone:
                self.boost = max(self.boost, min(self.config.boost_max, jump / dt * self.config.boost_gain))
            elif length(current) <= self.config.deadzone:
                self.boost = 0.0
        self.history.append((timestamp, point))
        self.valid = True

    def interpolate(self, timestamp):
        if not self.valid or not self.history:
            return None
        if timestamp <= self.history[0][0]:
            return self.history[0][1]
        for (t0, p0), (t1, p1) in zip(self.history, list(self.history)[1:]):
            if t0 <= timestamp <= t1:
                weight = (timestamp - t0) / (t1 - t0)
                return tuple(a + (b - a) * weight for a, b in zip(p0, p1))
        # Causal zero-order hold until a newer sample arrives, never extrapolate.
        return self.history[-1][1]

    def neutral(self):
        return not self.valid or length(self.normalize(self.history[-1][1])) <= self.config.deadzone

    def step(self, now, delay_ms, dt):
        self.position = self.interpolate(now - delay_ms)
        if self.position is None:
            self.reset_motion()
            return self.velocity
        config = self.config
        signed = self.normalize(self.position)
        magnitude = length(signed)
        if self.active:
            self.active = magnitude > config.deadzone
        else:
            self.active = magnitude > config.deadzone + config.hysteresis
        self.boost *= math.exp(-dt * 1000.0 / config.boost_decay_ms)
        strength = 0.0
        if self.active:
            strength = ((min(1.0, magnitude) - config.deadzone) / (1 - config.deadzone)) ** config.exponent
            strength = min(1.0, strength * (1 + self.boost))
        self.target = tuple(v / magnitude * strength if magnitude else 0.0 for v in signed)
        alpha = 1.0 if config.smoothing_ms == 0 else -math.expm1(-dt * 1000.0 / config.smoothing_ms)
        desired = tuple(v + alpha * (t - v) for v, t in zip(self.velocity, self.target))
        delta = tuple(d - v for d, v in zip(desired, self.velocity))
        rate = config.deceleration if length(desired) < length(self.velocity) else config.acceleration
        scale = min(1.0, rate * dt / length(delta)) if length(delta) else 1.0
        self.velocity = tuple(max(-1.0, min(1.0, v + d * scale)) for v, d in zip(self.velocity, delta))
        if not self.active and length(self.velocity) < 0.0001:
            self.velocity = (0.0,) * self.dimensions
        return self.velocity


class MouseProcessor:
    """Call accept() on arrival; tick() on an independent output clock.

    All times use the same monotonic millisecond clock. Changing source/session,
    a stale stream, or malformed envelope disarms; arm() explicitly requests resume.
    The two EyeGate instances never read one another's state.
    """

    def __init__(self, config=None, subject_id="mock-person"):
        self.config = config or MouseConfig()
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError("Select a nonempty subject_id")
        self.subject_id = subject_id
        self.pointer = AxisFilter(self.config.pointer, 2)
        self.scroll = AxisFilter(self.config.scroll, 1)
        self.left = EyeGate(self.config.left_eye)
        self.right = EyeGate(self.config.right_eye)
        self.sample = None
        self.eye_sample = None
        self.session = None
        self.sequence = -1
        self.received_ms = None
        self.last_tick = None
        self.output_sequence = 0
        self.armed = False
        self.enabled = False
        self.reason = "Preview stopped"
        self.accepted = 0
        self.rejected = 0

    def arm(self):
        self.armed = True
        self.enabled = False
        self.reason = "Waiting for fresh neutral input"
        self.left.reset()
        self.right.reset()
        self.pointer.clear()
        self.scroll.clear()
        # A fresh sample after arm is required; cached values cannot enable output.
        self.received_ms = None

    def disarm(self, reason="Preview stopped"):
        self.armed = self.enabled = False
        self.received_ms = None
        self.reason = reason
        self.left.reset()
        self.right.reset()
        self.pointer.clear()
        self.scroll.clear()

    def record_eyes(self, frame, received_ms, sample=None):
        """Publish one numeric eye input for every fresh envelope, even without a face."""
        try:
            normalized = eye_sample(frame, self.subject_id,
                sample.left_closed if sample and sample.left_known else None,
                sample.right_closed if sample and sample.right_known else None)
        except (ValueError, AttributeError):
            return
        if is_fresh_sample(normalized, self.eye_sample, received_ms, self.config.stale_ms):
            self.eye_sample = normalized

    def accept(self, frame, received_ms):
        if not finite(received_ms):
            raise ValueError("received_ms must be finite")
        try:
            sample = decode(frame, self.config, self.subject_id)
            if not 0 <= received_ms - sample.timestamp_ms <= self.config.stale_ms:
                raise ValueError("Sample is future-dated or stale")
        except ValueError as exc:
            if isinstance(exc, SubjectMissing):
                self.record_eyes(frame, received_ms)
            self.rejected += 1
            self.disarm(str(exc))
            return {"accepted": False, "reason": str(exc)}
        if sample.session_id == self.session:
            if sample.sequence <= self.sequence or (self.sample and sample.timestamp_ms < self.sample.timestamp_ms):
                self.rejected += 1
                return {"accepted": False, "reason": "Duplicate or out-of-order sample"}
        elif self.session is not None:
            self.disarm("Source restarted; start preview again")
        # No dwell/interpolation may bridge a gap, even when tick was not called.
        if self.received_ms is not None and (
            received_ms - self.received_ms > self.config.stale_ms
            or (self.sample and sample.timestamp_ms - self.sample.timestamp_ms > self.config.stale_ms)
        ):
            self.disarm("Input gap; start preview again")
        self.session, self.sequence = sample.session_id, sample.sequence
        self.sample = sample
        self.received_ms = received_ms
        self.accepted += 1
        self.record_eyes(frame, received_ms, sample)
        self.pointer.push(sample.pointer, sample.timestamp_ms)
        self.scroll.push(sample.scroll, sample.timestamp_ms)
        if self.armed:
            self.left.sample(sample.left_closed, sample.timestamp_ms, known=sample.left_known)
            self.right.sample(sample.right_closed, sample.timestamp_ms, known=sample.right_known)
        return {"accepted": True, "reason": "Sample accepted"}

    def tick(self, now_ms):
        if not finite(now_ms) or (self.last_tick is not None and now_ms < self.last_tick):
            raise ValueError("Output clock must be finite and monotonic")
        dt = 0.0 if self.last_tick is None else (now_ms - self.last_tick) / 1000.0
        if dt * 1000.0 > self.config.stale_ms:
            if self.armed:
                self.disarm("Output clock gap; start preview again")
            dt = 0.0
        self.last_tick = now_ms
        fresh = (self.sample is not None and self.received_ms is not None
                 and 0 <= now_ms - self.sample.timestamp_ms <= self.config.stale_ms
                 and 0 <= now_ms - self.received_ms <= self.config.stale_ms)
        if self.armed and not fresh and self.received_ms is not None:
            self.disarm("Input stale; start preview again")
        if self.armed and fresh and not self.enabled:
            has_signal = (self.pointer.valid or self.scroll.valid or self.left.ready or self.right.ready)
            if has_signal and self.pointer.neutral() and self.scroll.neutral():
                self.enabled = True
                self.reason = "Running"
        pointer = self.pointer.step(now_ms, self.config.interpolation_ms, dt)
        scroll = self.scroll.step(now_ms, self.config.interpolation_ms, dt)[0]
        if not self.enabled:
            pointer, scroll = (0.0, 0.0), 0.0
            self.pointer.reset_motion()
            self.scroll.reset_motion()
        self.output_sequence += 1
        sample = self.sample
        return {
            "sequence": self.output_sequence, "timestamp_ms": now_ms,
            "source_sequence": sample.sequence if sample else None,
            "source_timestamp_ms": sample.timestamp_ms if sample else None,
            "session_id": self.session, "subject_id": self.subject_id,
            "enabled": self.enabled, "armed": self.armed, "status": self.reason,
            "pointer_x": (pointer[0] + 1) / 2, "pointer_y": (pointer[1] + 1) / 2,
            "scroll_y": (scroll + 1) / 2,
            "left_click": int(self.enabled and self.left.down),
            "right_click": int(self.enabled and self.right.down),
            "diagnostics": {
                "raw_pointer": list(sample.pointer) if sample and fresh and sample.pointer is not None else None,
                "raw_scroll": sample.scroll if sample and fresh else None,
                "left_closed": sample.left_closed if sample and fresh and sample.left_known else None,
                "right_closed": sample.right_closed if sample and fresh and sample.right_known else None,
                "left_dwell": self.left.progress, "right_dwell": self.right.progress,
                "interpolated_pointer": self.pointer.position,
                "interpolated_scroll": self.scroll.position[0] if self.scroll.position is not None else None,
                "pointer_target": self.pointer.target, "scroll_target": self.scroll.target[0],
                "pointer_boost": self.pointer.boost, "scroll_boost": self.scroll.boost,
                "age_ms": now_ms - sample.timestamp_ms if sample else None,
                "accepted": self.accepted, "rejected": self.rejected,
            },
        }
