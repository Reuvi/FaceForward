"""Capture-time gestures and features. No clocks based on rendering or frame counts."""

from math import isfinite


def finite(value):
    return type(value) in (int, float) and isfinite(value)


class Gesture:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase = "WAIT_OPEN"
        self.open_since = None
        self.onset = None
        self.first_open = None
        self.last = None
        self.peak = 0.0
        self.area = 0.0
        self.close_speed = 0.0
        self.open_speed = 0.0
        self.support = {}
        self.opposite_peak = 0.0
        self.cooldown_until = 0.0
        self.held = False
        self.reason = "Need a fresh open baseline"
        self.blocked = False
        self.opposite_since = None
        self.sync_lag = None
        self.overlap_ms = 0.0

    def feed(self, t, value, opposite, features, cfg, minimum, *, strict=False):
        event = None
        if (
            not finite(value)
            or strict
            and (not finite(opposite) or opposite > cfg["release"])
        ):
            if self.onset is not None:
                event = self.finish(t, "invalid/opposite eye", False)
            self.reset()
            return event
        if self.last and not 0 < t - self.last[0] <= cfg["stale_ms"]:
            self.reset()
        if finite(opposite):
            if opposite >= cfg["activation"] and self.opposite_since is None:
                self.opposite_since = t
            elif opposite <= cfg["release"]:
                self.opposite_since = None
        else:
            self.opposite_since = None
        speed = (
            0
            if self.last is None
            else (value - self.last[1]) * 1000 / (t - self.last[0])
        )
        dt = 0 if self.last is None else t - self.last[0]
        self.last = (t, value)
        if self.phase in ("WAIT_OPEN", "COOLDOWN"):
            if value <= cfg["release"]:
                if self.open_since is None:
                    self.open_since = t
                if t - self.open_since >= cfg["open_ms"] and t >= self.cooldown_until:
                    self.phase = "READY"
                    self.reason = "Ready"
            else:
                self.open_since = None
        elif self.phase == "READY":
            if value >= cfg["activation"]:
                self.onset = t
                self.phase = "CANDIDATE"
                self.peak = value
                self.close_speed = max(0, speed)
                self.open_speed = 0
                self.area = 0
                self.support = {}
                self.opposite_peak = opposite if finite(opposite) else 0
                self.reason = "Measuring closure"
                dt = 0
                self.sync_lag = (
                    None if self.opposite_since is None else self.opposite_since - t
                )
                self.overlap_ms = 0.0
        if self.onset is not None:
            self.peak = max(self.peak, value)
            self.area += value * dt / 1000
            if self.sync_lag is None and self.opposite_since is not None:
                self.sync_lag = self.opposite_since - self.onset
            if (
                value >= cfg["activation"]
                and finite(opposite)
                and opposite >= cfg["activation"]
            ):
                self.overlap_ms += dt
            self.close_speed = max(self.close_speed, speed)
            self.open_speed = max(self.open_speed, -speed)
            if finite(opposite):
                self.opposite_peak = max(self.opposite_peak, opposite)
            for key, score in features.items():
                if finite(score):
                    self.support[key] = max(self.support.get(key, score), score)
            if value <= cfg["release"]:
                if self.first_open is None:
                    self.first_open = t
                duration = self.first_open - self.onset
                self.held = False
                if t - self.first_open >= cfg["open_ms"]:
                    accepted = (
                        duration >= minimum
                        and (duration <= cfg["max_ms"] or cfg["click_mode"] == "hold")
                        and not self.blocked
                    )
                    event = self.finish(
                        self.first_open,
                        "accepted"
                        if accepted
                        else "too short"
                        if duration < minimum
                        else "too long",
                        accepted,
                    )
                    self.phase = "COOLDOWN"
                    self.cooldown_until = t + cfg["cooldown_ms"]
                    self.open_since = t
            else:
                self.first_open = None
                if t - self.onset > cfg["max_ms"] and cfg["click_mode"] == "release":
                    self.blocked = True
                    self.phase = "TOO_LONG"
                    self.reason = "Prolonged closure; reopen to reset"
                elif t - self.onset >= minimum:
                    self.phase = "QUALIFIED"
                    self.reason = (
                        "Release to click"
                        if cfg["click_mode"] == "release"
                        else "Holding"
                    )
                    self.held = cfg["click_mode"] == "hold"
        return event

    def finish(self, t, reason, accepted):
        event = dict(
            onset_ms=self.onset,
            end_ms=t,
            duration_ms=max(0, t - self.onset),
            peak=self.peak,
            area=self.area,
            close_speed=self.close_speed,
            open_speed=self.open_speed,
            opposite_peak=self.opposite_peak,
            sync_lag_ms=self.sync_lag,
            overlap_ms=self.overlap_ms,
            accepted=accepted,
            reason=reason,
            **self.support,
        )
        self.onset = None
        self.first_open = None
        self.held = False
        self.blocked = False
        self.reason = reason
        return event

    def state(self, t):
        return dict(
            phase=self.phase,
            reason=self.reason,
            elapsed_ms=0 if self.onset is None else t - self.onset,
            held=self.held,
            peak=self.peak,
            close_speed=self.close_speed,
            open_speed=self.open_speed,
        )
