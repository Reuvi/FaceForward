"""Separate geometry and short open/closed-action guides, timed by capture."""

from .guided_eyes import GuidedEyes
from .wink_model import fit, check


def prompts():
    return tuple(
        (role, kind, instruction, 1)
        for role in ("train", "check")
        for kind, instruction in (
            ("relaxed", "Keep both eyes comfortably OPEN; look at the dot"),
            ("left", "Close your LEFT eye with your usual wink movement; hold until the rest tone"),
            ("right", "Close your RIGHT eye with your usual wink movement; hold until the rest tone"),
        )
    )


PROMPTS = prompts()


class EyeCalibrationFlow:
    def __init__(self, config, *, eyes=None):
        if eyes is not None and not eyes:
            raise ValueError("Complete eye open/closed calibration before wink actions")
        self.config = config
        self.kind = "geometry" if eyes is None else "winks"
        self.geometry = GuidedEyes(config) if eyes is None else None
        self.calibrated_eyes = dict(eyes or {})
        self.wink_index = None if eyes is None else 0
        self.prompts = tuple(p for p in PROMPTS if p[1] == "relaxed" or p[1] in self.calibrated_eyes)
        self.active = True
        self.start_ms = self.rest_end_ms = self.last_timestamp = None
        self.resting = False
        self.windows = []
        self.models = {}
        self.errors = {}
        self.report = ""
        self._reset_window()

    def _reset_window(self):
        self.values = {s: [] for s in ("left", "right")}
        self.rejected = {s: 0 for s in self.values}
        self.seen = {s: 0 for s in self.values}

    @property
    def fits(self):
        return self.geometry.fits if self.geometry is not None else self.calibrated_eyes

    @property
    def groups(self):
        return self.geometry.groups if self.geometry is not None else {}

    @property
    def index(self):
        return (
            self.geometry.index
            if self.wink_index is None
            else self.wink_index
        )

    @property
    def step(self):
        if self.wink_index is None:
            return self.geometry.step
        role, kind, instruction, _ = self.prompts[self.wink_index]
        return (kind, instruction, (0.5, 0.5))

    @property
    def collecting_ms(self):
        return self.config.collect_ms * self.prompts[self.wink_index][3]

    def present(self, index, now, phase=None):
        if self.wink_index is None:
            self.geometry.present(index, now, phase)
            return
        expected = "rest" if self.resting else "prepare"
        if not self.active or index != self.index or phase not in (None, expected):
            return
        if self.resting:
            if self.rest_end_ms is None:
                self.rest_end_ms = now + self.config.eye_rest_ms
        elif self.start_ms is None:
            self.start_ms = now + self.config.settle_ms

    def feed(self, t, features, vectors):
        if self.wink_index is None:
            self.geometry.feed(t, features)
            if not self.geometry.active:
                self.errors = dict(self.geometry.errors)
                self.active = False
                self.report = self.geometry.report
                if self.fits:
                    self.report += " · Eye open/closed ready. Start Wink action when ready."
            return
        if not self.active:
            return
        if self.resting:
            if self.rest_end_ms is not None and t >= self.rest_end_ms:
                self.resting = False
                self.rest_end_ms = None
            return
        if (
            self.start_ms is None
            or t < self.start_ms
            or self.last_timestamp is not None
            and t <= self.last_timestamp
        ):
            return
        self.last_timestamp = t
        if t >= self.start_ms + self.collecting_ms:
            self._finish_window()
            return
        role, kind, _, _ = self.prompts[self.wink_index]
        for side, geometry in self.fits.items():
            if kind not in (side, "relaxed"):
                continue
            self.seen[side] += 1
            vector = vectors.get(side)
            feature = features.get(side)
            if vector is None or feature is None or feature.quality <= 0:
                self.rejected[side] += 1
                continue
            observed = geometry.classify(feature.value, feature.quality)
            # Prompt labels apply only to the measured open/closed state. Starting
            # a hold during preparation is fine; only capture frames can train.
            wanted = 1 if kind == "relaxed" else 0
            if observed["valid"] and observed["value"] == wanted and len(self.values[side]) < 512:
                self.values[side].append(vector)

    def _finish_window(self):
        role, kind, _, _ = self.prompts[self.wink_index]
        self.windows.append(
            dict(
                role=role,
                kind=kind,
                values=self.values,
                rejected=self.rejected,
                seen=self.seen,
            )
        )
        if self.wink_index == len(self.prompts) - 1:
            self.active = False
            self._fit()
        else:
            self.wink_index += 1
            self.start_ms = None
            self.resting = self.config.eye_rest_ms > 0
            self.rest_end_ms = None
            self._reset_window()

    def _fit(self):
        for side in self.fits:
            try:
                sets = {}
                for role in ("train", "check"):
                    windows = [w for w in self.windows if w["role"] == role]
                    if any(
                        w["seen"][side] == 0
                        or w["rejected"][side] > 0.2 * w["seen"][side]
                        for w in windows
                        if w["kind"] in (side, "relaxed")
                    ):
                        raise ValueError(
                            f"Too many missing {role} facial measurements; retry with a clear camera view"
                        )
                    relevant = [w for w in windows if w["kind"] in (side, "relaxed")]
                    if any(len(w["values"][side]) < self.config.min_samples for w in relevant):
                        raise ValueError(f"Too few clear {role} open/closed action frames; follow the named eye prompt")
                    positive = [w for w in windows if w["kind"] == side]
                    sets[role] = (
                        [
                            w["values"][side]
                            for w in windows
                            if w["kind"] == "relaxed"
                        ],
                        [w["values"][side] for w in positive],
                    )
                model = fit(*sets["train"])
                self.models[side] = check(model, *sets["check"])
            except ValueError as exc:
                self.errors[side] = str(exc)
        self.report = " | ".join(
            f"{side.title()}: "
            + (
                "wink check passed"
                if side in self.models
                else self.errors.get(side, "needs another pass")
            )
            for side in ("left", "right")
        )

    def state(self, now):
        if self.wink_index is None:
            state = self.geometry.state(now)
            state.update(
                kind=self.kind, stage="Eye open/closed", wink_training=False,
                report=self.report if not self.active else state["report"],
            )
            return state
        role, kind, instruction, _ = self.prompts[self.wink_index]
        waiting = self.rest_end_ms is None if self.resting else self.start_ms is None
        preparing = self.resting or self.start_ms is None or now < self.start_ms
        remaining = (
            (self.config.eye_rest_ms if waiting else max(0, self.rest_end_ms - now))
            if self.resting
            else (
                self.config.settle_ms
                if waiting
                else max(0, self.start_ms - now)
                if preparing
                else max(0, self.start_ms + self.collecting_ms - now)
            )
        )
        phase = (
            "complete"
            if not self.active
            else "rest"
            if self.resting
            else "prepare"
            if preparing
            else "capture"
        )
        return dict(
            active=self.active,
            index=self.index,
            total=len(self.prompts),
            kind=self.kind,
            name=kind,
            instruction="Rest your eyes — no training samples"
            if self.resting
            else instruction,
            next_instruction=instruction,
            target=None if self.resting else (0.5, 0.5),
            waiting=waiting,
            preparing=preparing,
            resting=self.resting,
            phase=phase,
            capture_start_ms=self.start_ms,
            capture_end_ms=self.start_ms + self.collecting_ms
            if self.start_ms is not None
            else None,
            remaining_ms=remaining,
            closed_duration_ms=0,
            samples={s: len(v) for s, v in self.values.items()},
            errors=dict(self.errors),
            report=self.report,
            passed=len(self.models) if not self.active else 0,
            stage="Learn wink action" if role == "train" else "Check on new movements",
            wink_training=True,
        )
