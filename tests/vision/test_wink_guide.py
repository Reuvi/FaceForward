"""Guide labels use distinct capture windows; no rest/prepare data leaks into fits."""

import importlib.util
from types import SimpleNamespace
import unittest

from Vision.features import DetectionConfig
from Vision.wink_guide import EyeCalibrationFlow, PROMPTS
from Vision.wink_model import classify
from test_wink_model import vector


@unittest.skipUnless(
    importlib.util.find_spec("numpy"), "Vision NumPy dependency required"
)
class WinkGuideTests(unittest.TestCase):
    def run_guide(self, *, confuse_right=False, bad_check=False, missing=False):
        guide = EyeCalibrationFlow(
            DetectionConfig(
                settle_ms=100, collect_ms=400, eye_rest_ms=100, min_samples=8
            )
        )
        now = 1000
        while guide.active:
            state = guide.state(now)
            if state["waiting"]:
                guide.present(guide.index, now, state["phase"])
            state = guide.state(now)
            ratios = {"left": 0.25, "right": 0.25}
            vectors = {s: vector(opened=True) for s in ratios}
            if state["wink_training"]:
                if state["phase"] == "capture":
                    fraction = (now - state["capture_start_ms"]) / (
                        state["capture_end_ms"] - state["capture_start_ms"]
                    )
                    role, kind, _, _ = PROMPTS[guide.wink_index]
                    for side in ratios:
                        closed = (
                            kind == "blinks" and 0.2 <= (fraction * 4) % 1 < 0.45
                        ) or (kind == side and 0.2 <= fraction < 0.75)
                        ratios[side] = 0.04 if closed else 0.25
                        wink = (
                            kind == side
                            and closed
                            and not (side == "right" and confuse_right)
                        )
                        if (
                            bad_check
                            and role == "check"
                            and kind == "blinks"
                            and closed
                        ):
                            wink = True
                        vectors[side] = vector(wink, opened=not closed)
                    if missing and kind == "relaxed":
                        vectors["left"] = None
                else:
                    # Poisoned rest/preparation appearances must not teach either label.
                    vectors = {s: [900.0] * 8 for s in ratios}
            else:
                ratio = {
                    "center": 0.25,
                    "left": 0.21,
                    "right": 0.22,
                    "up": 0.28,
                    "down": 0.14,
                    "closed": 0.04,
                    "reopen": 0.25,
                }[state["name"]]
                ratios = {s: ratio for s in ratios}
            guide.feed(
                now,
                {s: SimpleNamespace(value=v, quality=1) for s, v in ratios.items()},
                vectors,
            )
            now += 25
            self.assertLess(now, 100000)
        return guide

    def test_full_flow_trains_checks_and_excludes_rest(self):
        guide = self.run_guide()
        self.assertEqual(set(guide.models), {"left", "right"}, guide.report)
        for model in guide.models.values():
            self.assertEqual(classify(model, vector()), 0)
            self.assertEqual(classify(model, vector(True)), 1)
            self.assertEqual(model["report"]["wink_attempts"], 2)

    def test_one_unreliable_eye_does_not_disable_the_other(self):
        guide = self.run_guide(confuse_right=True)
        self.assertEqual(set(guide.models), {"left"})
        self.assertIn("Right:", guide.report)

    def test_validation_movements_cannot_train_away_a_failure(self):
        guide = self.run_guide(bad_check=True)
        self.assertFalse(guide.models)
        self.assertIn("false wink", guide.report)

    def test_missing_features_reject_only_the_affected_eye(self):
        guide = self.run_guide(missing=True)
        self.assertEqual(set(guide.models), {"right"})
        self.assertIn("missing train facial measurements", guide.report)
