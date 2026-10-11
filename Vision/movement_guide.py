"""Capture-timed position calibration, independent of device transfer functions."""

from dataclasses import asdict, replace
from .calibration import AxisCalibration
from .signals import finite_number

HEAD_TARGETS = (("neutral", (0.5,)), ("up", (0.0,)), ("down", (1.0,)))
HEAD_X_TARGETS = (("neutral", (0.5,)), ("left", (0.0,)), ("right", (1.0,)))
TONGUE_TARGETS = (
    ("center", (0.5, 0.5)),
    ("left", (0.0, 0.5)),
    ("right", (1.0, 0.5)),
    ("up", (0.5, 0.0)),
    ("down", (0.5, 1.0)),
)


def validate_range(value, config, *, bounds=(-.8, .8), separation=None, label="Tongue"):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        raise ValueError(f"{label} range needs x and y axis fits")
    result = {}
    for name, fields in value.items():
        if not isinstance(fields, dict) or set(fields) != {
            "low",
            "center",
            "high",
            "endpoint_tolerance",
        }:
            raise ValueError(f"Invalid {label.lower()} range fields")
        fit = AxisCalibration(**fields)
        if (
            not bounds[0] <= fit.low < fit.center < fit.high <= bounds[1]
            or min(fit.center - fit.low, fit.high - fit.center)
            < (config.tongue_position_separation if separation is None else separation)
            or fit.endpoint_tolerance != config.endpoint_tolerance
        ):
            raise ValueError(f"{label} range is too small or does not match settings")
        result[name] = fit
    return result


class MovementGuide:
    def __init__(self, kind, config, *, existing=None):
        if kind not in ("head", "head_x", "tongue"):
            raise ValueError("Movement guide must be head, head_x or tongue")
        self.kind, self.config = kind, config
        self.label = "Head X" if kind == "head_x" else kind.title()
        targets = HEAD_TARGETS if kind == "head" else HEAD_X_TARGETS if kind == "head_x" else TONGUE_TARGETS
        self.steps = [("absence", "absent", None)] if kind == "tongue" else []
        if existing is None:
            self.steps += [("train", name, target) for name, target in targets]
        self.steps += [("check", name, target) for name, target in targets]
        self.fits = dict(existing or {})
        self.index = 0
        self.active = True
        self.passed = False
        self.resting = False
        self.start_ms = self.rest_end_ms = self.last_timestamp = None
        self.values = []
        self.groups = {}
        self.checks = {}
        self.absence = None
        self.report = ""

    def present(self, index, now, phase):
        expected = "rest" if self.resting else "prepare"
        if not self.active or index != self.index or phase != expected:
            return
        if self.resting and self.rest_end_ms is None:
            self.rest_end_ms = now + self.config.movement_rest_ms
        elif not self.resting and self.start_ms is None:
            self.start_ms = now + self.config.settle_ms

    def retry(self):
        if self.active or self.passed:
            raise ValueError("Only a failed pose can be retried")
        role, name, _ = self.steps[self.index]
        if role == "train":
            self.groups.pop(name, None)
            self.fits = {}
        elif role == "check":
            self.checks.pop(name, None)
        else:
            self.absence = None
        self.values = []
        self.start_ms = self.rest_end_ms = None
        self.resting = False
        self.report = ""
        self.active = True

    def advance(self, now, *, grace_ms=0):
        """Advance wall-clock phases without inventing detector observations."""
        if not self.active:
            return
        if self.resting:
            if self.rest_end_ms is not None and now >= self.rest_end_ms:
                self.resting = False
                self.rest_end_ms = None
        elif self.start_ms is not None and now >= self.start_ms + self.config.collect_ms + grace_ms:
            self._finish()

    def feed(self, timestamp, value, usable, *, finish=True):
        if not self.active:
            return
        if self.resting:
            if finish:
                self.advance(timestamp)
            return
        if (
            self.start_ms is None
            or timestamp < self.start_ms
            or self.last_timestamp is not None
            and timestamp <= self.last_timestamp
        ):
            return
        self.last_timestamp = timestamp
        if timestamp >= self.start_ms + self.config.collect_ms:
            if finish:
                self._finish()
            return
        if len(self.values) >= 512:
            return
        role, _, _ = self.steps[self.index]
        if role == "absence":
            sample = int(value is not None) if usable else None
        else:
            dimensions = getattr(self, "dimensions", 1 if self.kind in ("head", "head_x") else 2)
            sample = (
                tuple(value)
                if usable
                and isinstance(value, (tuple, list))
                and len(value) == dimensions
                and all(finite_number(v) for v in value)
                else None
            )
        self.values.append(sample)

    def normalized(self, value):
        if value is None or not self.fits:
            return None
        names = ("y",) if self.kind == "head" else ("x",) if self.kind == "head_x" else ("x", "y")
        result = tuple(self.fits[key].normalize(v) for key, v in zip(names, value))
        return result if all(v is not None for v in result) else None

    def _fit(self):
        c = self.config
        if self.kind in ("head", "head_x"):
            separation = (
                c.head_position_separation
                if c.head_mode == "position"
                else c.head_pitch_separation
            )
            if self.kind == "head_x":
                separation = c.head_yaw_separation
            targets = ("left", "neutral", "right") if self.kind == "head_x" else ("up", "neutral", "down")
            fit = AxisCalibration.fit(
                *(
                    [v[0] for v in self.groups[name]]
                    for name in targets
                ),
                min_separation=separation,
            )
            self.fits = {"x" if self.kind == "head_x" else "y": replace(fit, endpoint_tolerance=c.endpoint_tolerance)}
        else:
            for index, (key, low, high) in enumerate(
                (("x", "left", "right"), ("y", "up", "down"))
            ):
                fit = AxisCalibration.fit(
                    *(
                        [v[index] for v in self.groups[name]]
                        for name in (low, "center", high)
                    ),
                    min_separation=c.tongue_position_separation,
                )
                self.fits[key] = replace(fit, endpoint_tolerance=c.endpoint_tolerance)
            validate_range({key: asdict(fit) for key, fit in self.fits.items()}, c,
                           bounds=(-.8,.8), label=self.kind.title())

    def _finish(self):
        role, name, target = self.steps[self.index]
        usable = [v for v in self.values if v is not None]
        try:
            if len(usable) < self.config.min_samples or len(usable) < 0.8 * len(
                self.values
            ):
                raise ValueError(
                    f"{name}: too few clear samples; keep the feature visible and retry"
                )
            if role == "absence":
                rate = sum(usable) / len(usable)
                if rate > 0.05:
                    raise ValueError(
                        f"Absent check failed: candidate on {rate:.0%} of frames; inspect the live tongue mask before retrying"
                    )
                self.absence = {
                    "passed": True,
                    "detected_fraction": rate,
                    "samples": len(usable),
                }
            elif role == "train":
                self.groups[name] = usable
                if self.steps[self.index + 1][0] == "check":
                    self._fit()
            else:
                mapped = [self.normalized(v) for v in self.values]
                matches = [
                    v is not None
                    and max(abs(a - b) for a, b in zip(v, target))
                    <= self.config.position_check_tolerance
                    for v in mapped
                ]
                fraction = sum(matches) / len(matches)
                self.checks[name] = {
                    "samples": len(matches),
                    "matched_fraction": fraction,
                    "detected_fraction": len(usable) / len(self.values),
                }
                if fraction < 0.9:
                    raise ValueError(
                        f"{name} check: {fraction:.0%} within target; need 90%. Retry comfortable, repeatable positions"
                    )
            if self.index == len(self.steps) - 1:
                self.active = False
                self.passed = True
                self.report = f"{self.label} position calibration passed; inspect raw and calibrated positions"
                return
            self.index += 1
            self.start_ms = None
            self.resting = self.config.movement_rest_ms > 0
            self.rest_end_ms = None
            self.values = []
        except ValueError as exc:
            self.active = False
            self.report = "Calibration rejected: " + str(exc)

    def state(self, now):
        role, name, target = self.steps[self.index]
        phase = (
            "complete"
            if not self.active
            else "rest"
            if self.resting
            else "prepare"
            if self.start_ms is None or now < self.start_ms
            else "capture"
        )
        waiting = self.rest_end_ms is None if self.resting else self.start_ms is None
        if self.resting:
            remaining = (
                self.config.movement_rest_ms
                if waiting
                else max(0, self.rest_end_ms - now)
            )
        elif waiting:
            remaining = self.config.settle_ms
        else:
            remaining = max(
                0,
                (
                    self.start_ms
                    if phase == "prepare"
                    else self.start_ms + self.config.collect_ms
                )
                - now,
            )
        if name == "absent":
            instruction = (
                "Open your mouth but keep the tongue hidden behind your teeth. Keep your head still."
            )
        elif self.kind == "head_x":
            instruction = (
                "Rest in your comfortable NEUTRAL head position, facing the camera"
                if name == "neutral"
                else f"Turn your head slightly toward YOUR {name.upper()} (about 10–20°)"
            )
            instruction += ". Use a comfortable turn, keep both eyes visible, and avoid tilting sideways."
        elif self.kind == "head":
            movement = (
                "Move your whole head"
                if self.config.head_mode == "position"
                else "Nod your head"
            )
            instruction = (
                "Rest in your comfortable NEUTRAL head position"
                if name == "neutral"
                else f"{movement} {name.upper()} to a comfortable limit"
            )
        else:
            instruction = (
                "Show your tongue at its comfortable CENTER"
                if name == "center"
                else f"Move your tongue toward YOUR {name.upper()} comfortable limit"
            )
            instruction += ". Keep the tip visible past your lip and your head still; move only as far as comfortable."
            if name in ("left", "right"):
                instruction += " YOUR side, even if the camera view looks reversed. Keep its height near center."
            elif name in ("up", "down"):
                instruction += " Keep it centered left-to-right."
        return dict(
            kind=self.kind,
            index=self.index,
            total=len(self.steps),
            active=self.active,
            passed=self.passed,
            phase=phase,
            waiting=waiting,
            remaining_ms=remaining,
            role=role,
            name=name,
            target=target,
            instruction="Rest comfortably — no training samples"
            if self.resting
            else instruction,
            next_instruction=instruction,
            samples=sum(v is not None for v in self.values),
            rejected=sum(v is None for v in self.values),
            report=self.report,
            checks=dict(self.checks),
        )
