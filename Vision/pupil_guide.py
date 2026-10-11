"""Pupil guide reuses the head guide's prompt and capture-window machinery."""
import numpy as np

from .movement_guide import MovementGuide
from .pupil_calibration import (CHECK_NAMES, POSE_NAMES, compensate, fit_endpoints,
                                fit_pose, normalize, validate_model)

TARGETS = dict(center=(.5, .5), left=(.06, .5), right=(.94, .5), up=(.5, .06), down=(.5, .94))
EXPECTED = dict(center=(.5, .5), diagonal=(.5, .5), left=(0., .5), right=(1., .5), up=(.5, 0.), down=(.5, 1.))


class PupilGuide(MovementGuide):
    dimensions = 5  # iris X/Y plus yaw, pitch and roll from the SAME capture.

    def __init__(self, config):
        super().__init__("head", config)
        self.kind, self.label = "pupil", "Pupils"
        self.steps = [("train", name, TARGETS["center"]) for name in POSE_NAMES]
        self.steps += [("train", name, TARGETS[name]) for name in ("left", "right", "up", "down")]
        self.steps += [("check", name, TARGETS.get(name, TARGETS["center"])) for name in CHECK_NAMES]
        self.model = None

    def retry(self):
        super().retry()
        # Rebuild fits from accepted groups; never keep a provisional failed fit.
        self.model = fit_pose(self.groups) if all(k in self.groups for k in POSE_NAMES) else None
        if self.model and all(k in self.groups for k in ("left", "right", "up", "down")):
            self.model = fit_endpoints(self.model, self.groups)

    def _finish(self):
        role, name, _ = self.steps[self.index]
        usable = [v for v in self.values if v is not None]
        try:
            if len(usable) < self.config.min_samples or len(usable) < .8*len(self.values):
                raise ValueError("Too few clear samples; keep both eyes visible, then retry this step")
            values = np.array(usable)
            spread = np.percentile(values, 90, axis=0)-np.percentile(values, 10, axis=0)
            if (spread[:2] > .045).any() or (spread[2:] > 6).any():
                raise ValueError("Position was moving during capture; settle first, then retry this step")
            if role == "train":
                if name not in POSE_NAMES:
                    ref = self.model["reference_pose"]
                    if np.max(np.abs(np.median(values[:, 2:4], axis=0)-ref[:2])) > 5:
                        raise ValueError("Return your head to its original center; move only your eyes to the dot")
                    corrected_samples = [compensate(self.model, v[:2], v[2:]) for v in usable]
                    for value, reason in corrected_samples:
                        if value is None:
                            raise ValueError(reason)
                    corrected = np.median([value for value, _ in corrected_samples], axis=0)
                    axis = 0 if name in ("left", "right") else 1
                    signed = (corrected[axis]-self.model["center"][axis]) * (-1 if name in ("left", "up") else 1)
                    if signed < .015:
                        raise ValueError(f"{name.upper()} was too close to center or reversed; retry looking toward that dot")
                candidate = dict(self.groups, **{name: usable})
                if name == POSE_NAMES[-1]:
                    self.model = fit_pose(candidate)
                if name == "down":
                    self.model = fit_endpoints(self.model, candidate)
                self.groups[name] = usable
            else:
                if name == "diagonal":
                    ref = self.model["reference_pose"]
                    pose = np.median(values[:, 2:4], axis=0)
                    if min(abs(pose-ref[:2])) < 2:
                        raise ValueError("For this check, turn AND nod slightly while keeping your eyes on the center dot")
                mapped = [normalize(self.model, v[:2], v[2:])[0] if v else None for v in self.values]
                target = EXPECTED[name]
                matches = [v is not None and max(abs(a-b) for a, b in zip(v, target)) <= self.config.position_check_tolerance for v in mapped]
                rate = sum(matches)/len(matches)
                if rate < .9:
                    raise ValueError(f"{name} check: {rate:.0%} matched; need 90%. Retry the pose or restart pupils")
                self.checks[name] = dict(samples=len(matches), matched_fraction=rate)
            if self.index == len(self.steps)-1:
                self.model["checks"] = dict(self.checks)
                self.model = validate_model(self.model)
                self.active, self.passed = False, True
                self.report = "Pupil calibration passed. Head-compensated personal directions are ready."
                return
            self.index += 1
            self.start_ms = self.rest_end_ms = None
            self.resting = self.config.movement_rest_ms > 0
            self.values = []
        except (ValueError, TypeError) as exc:
            self.active = False
            self.report = "Pupil calibration rejected: " + str(exc)

    def state(self, now):
        state = super().state(now)
        name = state["name"]
        if name == "center":
            instruction = "Face the screen comfortably. Look at the CENTER dot; keep both eyes open."
        elif name.startswith("head_"):
            direction = name[5:].upper()
            action = "Turn" if direction in ("LEFT", "RIGHT") else "Nod"
            instruction = f"KEEP LOOKING at the CENTER dot. {action} your HEAD {direction} about 10–15°. Keep both eyes visible; do not tilt sideways."
        elif name == "diagonal":
            instruction = "Head-compensation CHECK: keep looking at CENTER. Turn your head slightly RIGHT and nod slightly DOWN (half your earlier turns)."
        else:
            instruction = f"Head back at CENTER. Move ONLY YOUR EYES toward the {name.upper()} dot, as far as comfortable. Hold during the capture sound."
            if state["role"] == "check":
                instruction = "CHECK again: " + instruction
        state.update(resting=self.resting, instruction="Rest your eyes — no training samples" if self.resting else instruction,
                     next_instruction=instruction)
        return state

    def demo_controls(self):
        """Explicit synthetic fixture with cross-axis head drift; never camera data."""
        name = self.steps[self.index][1]
        yaw, pitch = {"head_left":(-12, 0), "head_right":(12, 0), "head_up":(0, -12),
                      "head_down":(0, 12), "diagonal":(6, 6)}.get(name, (0, 0))
        x, y = EXPECTED.get(name, (.5, .5))
        return dict(left_closed=False, right_closed=False, natural_blink=False,
                    head_x=.5+yaw/40, head=.5+pitch/40,
                    pupil_x=x+(yaw*.002+pitch*.0004)/.4,
                    pupil_y=y+(pitch*.001+yaw*.0002)/.2)
