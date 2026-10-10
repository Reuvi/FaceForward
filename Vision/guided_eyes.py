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

    def present(self, index, now):
        """UI acknowledges the displayed instruction before any timing starts."""
        if self.active and index == self.index and self.start_ms is None:
            self.start_ms = now + self.settle_ms

    def feed(self, timestamp, features):
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
            self.values = {side: [] for side in self.values}
            self.rejected = {side: 0 for side in self.rejected}

    def state(self, now):
        preparing = self.start_ms is None or now < self.start_ms
        remaining = (self.settle_ms if self.start_ms is None else max(0, self.start_ms-now)) if preparing else max(0, self.start_ms+self.config.collect_ms-now)
        return {"active": self.active, "index": self.index, "total": len(STEPS),
                "name": self.step[0], "instruction": self.step[1], "target": self.step[2],
                "waiting": self.start_ms is None, "preparing": preparing,
                "remaining_ms": remaining, "closed_duration_ms": max(self.config.settle_ms,1500)+self.config.collect_ms,
                "samples": {s: len(v) for s,v in self.values.items()},
                "errors": dict(self.errors), "report": self.report,
                "passed": len(self.fits) if not self.active else 0}
