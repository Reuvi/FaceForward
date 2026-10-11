"""Head Y guide with selective capture/check correction and retained references."""
from statistics import median

from .calibration import AxisCalibration, _samples
from .movement_guide import HEAD_TARGETS, MovementGuide


class HeadPitchGuide(MovementGuide):
    def __init__(self, config, *, existing=None):
        super().__init__("head", config)
        self.label = "Head Y"
        self.required_checks = set() if existing else set(dict(HEAD_TARGETS))
        # Saved scalars are references, never synthetic observations.
        self.references = (dict(up=existing.low, neutral=existing.center, down=existing.high)
                           if existing else {})
        if existing:
            self.fits = {"y": existing}
            self.active, self.passed = False, True

    def _fit(self):
        if not self.references:
            return super()._fit()
        ordered = []
        for name in ("up", "neutral", "down"):
            if name in self.groups:
                ordered.append(_samples(v[0] for v in self.groups[name]))
            else:
                # A retained scalar contributes a bound, not a captured sample.
                ordered.append([self.references[name]])
        fit = AxisCalibration(*(median(values) for values in ordered),
                              endpoint_tolerance=self.config.endpoint_tolerance)
        direction = 1 if fit.high > fit.low else -1
        bounds = [[direction*v for v in values] for values in ordered]
        if any(min(b)-max(a) < self.config.head_pitch_separation for a,b in zip(bounds,bounds[1:])):
            raise ValueError("calibration targets overlap or have insufficient range")
        self.fits = {"y": fit}

    def redo(self, role, name):
        """Replace one labeled window; untouched captures/checks stay independent."""
        targets = dict(HEAD_TARGETS)
        if role not in ("train", "check") or name not in targets:
            raise ValueError("Choose a neutral, up or down capture/check")
        if role == "check" and not self.fits:
            if any(n not in self.groups and n not in self.references for n in targets):
                raise ValueError("Capture neutral, up and down before checking a pose")
            self._fit()  # Validate before changing the current guide on rejection.
        if role == "train":
            self.groups.pop(name, None)
            self.references.pop(name, None)
            self.fits.clear()
            self.checks.clear()  # Every check depends on the changed normalization.
            self.required_checks = set(targets)
            missing = [n for n in targets if n != name and n not in self.groups and n not in self.references]
            self.steps = [("train", n, targets[n]) for n in (name, *missing)]
            self.steps += [("check", n, target) for n,target in HEAD_TARGETS]
        else:
            # A completed/saved fit already passed its other checks. An unfinished
            # candidate still needs whichever checks have not passed yet.
            if self.passed:
                self.required_checks = {name}
            else:
                self.required_checks.add(name)
            remaining = [n for n in targets if n != name and n in self.required_checks
                         and self.checks.get(n, {}).get("matched_fraction", 0) < .9]
            self.checks.pop(name, None)
            self.steps = [("check", n, targets[n]) for n in (name, *remaining)]
        self.index = 0
        self.active, self.passed, self.resting = True, False, False
        self.start_ms = self.rest_end_ms = None
        self.values = []
        self.report = ""
        # Keep last_timestamp: delayed old frames cannot enter the new window.

    def retry(self):
        if self.passed:
            raise ValueError("Select a completed pose to redo")
        role,name,_ = self.steps[self.index]
        self.redo(role,name)

    def state(self, now):
        state = super().state(now)
        state["reference_sources"] = {
            name: "captured" if name in self.groups else "saved" if name in self.references else "needed"
            for name,_ in HEAD_TARGETS
        }
        return state
