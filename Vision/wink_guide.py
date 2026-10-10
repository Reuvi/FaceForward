"""Separately started geometry and blink/wink guides with shared capture timing."""

from .guided_eyes import GuidedEyes
from .wink_model import fit, check


def prompts():
    result = []
    for role, attempts in (("train", 3), ("check", 2)):
        result.extend(
            (
                (
                    role,
                    "blinks",
                    "Blink gently several times, as you normally would",
                    6,
                ),
                (
                    role,
                    "relaxed",
                    "Keep eyes relaxed; smile, talk and look slightly around",
                    2,
                ),
            )
        )
        for attempt in range(attempts):
            for side in ("left", "right"):
                result.append(
                    (
                        role,
                        side,
                        f"Wink your {side.upper()} eye once, then reopen naturally ({attempt + 1}/{attempts})",
                        1.6,
                    )
                )
    return tuple(result)


PROMPTS = prompts()


class EyeCalibrationFlow:
    def __init__(self, config, *, eyes=None):
        if eyes is not None and not eyes:
            raise ValueError("Complete eye open/closed calibration before blinks and winks")
        self.config = config
        self.kind = "geometry" if eyes is None else "winks"
        self.geometry = GuidedEyes(config) if eyes is None else None
        self.calibrated_eyes = dict(eyes or {})
        self.wink_index = None if eyes is None else 0
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
        self.closures = {s: 0 for s in self.values}
        self.was_closed = {s: None for s in self.values}

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
        role, kind, instruction, _ = PROMPTS[self.wink_index]
        return (kind, instruction, (0.5, 0.5))

    @property
    def collecting_ms(self):
        return self.config.collect_ms * PROMPTS[self.wink_index][3]

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
                    self.report += " · Eye open/closed ready. Start Blinks & winks when ready."
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
        role, kind, _, _ = PROMPTS[self.wink_index]
        for side, geometry in self.fits.items():
            if kind not in (side, "blinks", "relaxed"):
                continue
            self.seen[side] += 1
            vector = vectors.get(side)
            feature = features.get(side)
            if vector is None or feature is None or feature.quality <= 0:
                self.rejected[side] += 1
                self.was_closed[side] = None
                continue
            closed = feature.value < (geometry.closed + geometry.opened) / 2
            if closed and self.was_closed[side] is False:
                self.closures[side] += 1
            self.was_closed[side] = closed
            # Natural blink/wink labels describe closed portions only. They never
            # label the open time surrounding an attempt as an intentional wink.
            if (closed or kind == "relaxed") and len(self.values[side]) < 512:
                self.values[side].append(vector)

    def _finish_window(self):
        role, kind, _, _ = PROMPTS[self.wink_index]
        self.windows.append(
            dict(
                role=role,
                kind=kind,
                values=self.values,
                closures=self.closures,
                rejected=self.rejected,
                seen=self.seen,
            )
        )
        if self.wink_index == len(PROMPTS) - 1:
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
                        if w["kind"] in (side, "blinks", "relaxed")
                    ):
                        raise ValueError(
                            f"Too many missing {role} facial measurements; retry with a clear camera view"
                        )
                    blink = next(w for w in windows if w["kind"] == "blinks")
                    needed = 3 if role == "train" else 2
                    if (
                        blink["closures"][side] < needed
                        or len(blink["values"][side]) < 6
                    ):
                        raise ValueError(
                            f"Too few {role} blinks; blink gently several times after the capture tone"
                        )
                    positive = [w for w in windows if w["kind"] == side]
                    if any(w["closures"][side] < 1 for w in positive):
                        raise ValueError(
                            f"A {role} wink attempt needs visible open → wink samples; retry"
                        )
                    sets[role] = (
                        [
                            w["values"][side]
                            for w in windows
                            if w["kind"] in ("blinks", "relaxed")
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
        role, kind, instruction, _ = PROMPTS[self.wink_index]
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
            total=len(PROMPTS),
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
            stage="Learn blink/wink" if role == "train" else "Check on new movements",
            wink_training=True,
        )
