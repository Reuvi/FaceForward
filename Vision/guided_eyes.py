"""Bounded, capture-timed eye calibration. No camera, UI, or click dependencies."""

from .calibration import EyeCalibration
from .signals import finite_number

# Prompt positions, not measured gaze labels. The user supplies the open/closed label.
STEPS = (
    ("center", "Eyes open — follow the dot", (.5, .5)),
    ("left", "Eyes open — look toward the dot", (.15, .5)),
    ("right", "Eyes open — look toward the dot", (.85, .5)),
    ("up", "Eyes open — look toward the dot", (.5, .18)),
    ("down", "Eyes open — look toward the dot", (.5, .82)),
    ("closed", "Gently close BOTH eyes", None),
    ("reopen", "Open BOTH eyes — follow the dot", (.5, .5)),
)


class GuidedEyes:
    def __init__(self, config):
        self.config = config
        self.index = 0
        self.active = True
        self.start_ms = None
        self.resting = False
        self.rest_end_ms = None
        self.last_timestamp = None
        self.groups = {side: [] for side in ("left", "right")}
        self.values = {side: [] for side in self.groups}
        self.rejected = {side: 0 for side in self.groups}
        self.errors = {}
        self.fits = {}
        self.report = ""

    @property
    def step(self):
        return STEPS[self.index]

    @property
    def settle_ms(self):
        # Allow time to hear the cue and pose, including after the closed phase.
        return max(self.config.settle_ms, 1500) if self.step[0] in ("closed", "reopen") else self.config.settle_ms

    def present(self, index, now, phase=None):
        """UI acknowledges the displayed instruction before any timing starts."""
        expected = "rest" if self.resting else "prepare"
        if not self.active or index != self.index or phase not in (None, expected):
            return
        if self.resting:
            if self.rest_end_ms is None:
                self.rest_end_ms = now + self.config.eye_rest_ms
        elif self.start_ms is None:
            self.start_ms = now + self.settle_ms

    def feed(self, timestamp, features):
        if self.active and self.resting:
            if self.rest_end_ms is not None and timestamp >= self.rest_end_ms:
                self.resting = False
                self.rest_end_ms = None
            return  # Rest and the transition frame never train either eye.
        if (not self.active or self.start_ms is None or timestamp < self.start_ms
                or self.last_timestamp is not None and timestamp <= self.last_timestamp):
            return
        self.last_timestamp = timestamp
        if timestamp >= self.start_ms + self.config.collect_ms:
            self._finish_step()
            return
        for side in self.values:
            if len(self.values[side]) + self.rejected[side] >= 512:
                continue
            feature = features.get(side)
            if feature and feature.quality > 0 and finite_number(feature.value):
                self.values[side].append(feature.value)
            else:
                self.rejected[side] += 1

    def _finish_step(self):
        for side, values in self.values.items():
            if side in self.errors:
                continue
            try:
                if (len(values) < self.config.min_samples
                        or len(values) < .8 * (len(values) + self.rejected[side])):
                    raise ValueError(f"{self.step[0]}: too few clear samples; improve visibility and retry")
                if self.step[0] == "reopen":
                    fit = self.fits[side]
                    # New samples, not training data. Unknown counts as a failed check.
                    if sum(fit.classify(v, 1)["value"] == 1 for v in values) / len(values) < .9:
                        raise ValueError("reopen check failed; restart with comfortably open eyes")
                elif self.step[0] == "closed":
                    self.fits[side] = EyeCalibration.fit_guided(
                        values, self.groups[side], min_separation=self.config.eye_separation)
                else:
                    self.groups[side].append(list(values))
            except ValueError as exc:
                self.errors[side] = str(exc)
                self.fits.pop(side, None)
        if self.index == len(STEPS) - 1:
            self.active = False
            self.report = " | ".join(f"{side.title()}: " + ("ready" if side in self.fits else self.errors[side]) for side in self.values)
        else:
            self.index += 1
            self.start_ms = None
            self.resting = self.config.eye_rest_ms > 0
            self.rest_end_ms = None
            self.values = {side: [] for side in self.values}
            self.rejected = {side: 0 for side in self.rejected}

    def state(self, now):
        waiting = self.rest_end_ms is None if self.resting else self.start_ms is None
        preparing = self.resting or self.start_ms is None or now < self.start_ms
        if self.resting:
            remaining = self.config.eye_rest_ms if waiting else max(0, self.rest_end_ms-now)
        else:
            remaining = (self.settle_ms if waiting else max(0, self.start_ms-now)) if preparing else max(0, self.start_ms+self.config.collect_ms-now)
        phase = "complete" if not self.active else "rest" if self.resting else "prepare" if preparing else "capture"
        return {"active": self.active, "index": self.index, "total": len(STEPS),
                "name": self.step[0],
                "instruction": "Rest your eyes — blink or close them naturally" if self.resting else self.step[1],
                "target": None if self.resting else self.step[2],
                "waiting": waiting, "preparing": preparing, "resting": self.resting, "phase": phase,
                "capture_start_ms": self.start_ms,
                "capture_end_ms": self.start_ms+self.config.collect_ms if self.start_ms is not None else None,
                "remaining_ms": remaining, "closed_duration_ms": max(self.config.settle_ms,1500)+self.config.collect_ms,
                "samples": {s: len(v) for s,v in self.values.items()},
                "errors": dict(self.errors), "report": self.report,
                "passed": len(self.fits) if not self.active else 0}
