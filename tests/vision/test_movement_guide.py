"""Range fitting uses labeled capture windows and independent checks, not UI ticks."""

from dataclasses import asdict
import unittest
from Vision.features import DetectionConfig
from Vision.movement_guide import MovementGuide, validate_range


class MovementGuideTests(unittest.TestCase):
    def run_guide(
        self,
        kind="head",
        *,
        bad_check=False,
        missing=False,
        overlap=False,
        existing=None,
        reverse=False,
    ):
        config = DetectionConfig(
            settle_ms=50, collect_ms=400, movement_rest_ms=75, min_samples=8
        )
        guide = MovementGuide(kind, config, existing=existing)
        now = 1000
        while guide.active:
            state = guide.state(now)
            if state["waiting"]:
                guide.present(guide.index, now, state["phase"])
            state = guide.state(now)
            name = state["name"]
            if kind == "head":
                value = ({"up": -12, "neutral": 4, "down": 28}[name],)
                if reverse:
                    value = (-value[0],)
            else:
                value = {
                    "absent": None,
                    "center": (0.45, 0.55),
                    "left": (0.2, 0.55),
                    "right": (0.8, 0.55),
                    "up": (0.45, 0.25),
                    "down": (0.45, 0.8),
                }[name]
            if overlap and name == "up":
                value = (4,) if kind == "head" else (0.45, 0.55)
            if bad_check and state["role"] == "check":
                value = (50,) if kind == "head" else (0.9, 0.9)
            usable = not missing
            if state["phase"] in ("prepare", "rest"):
                value = (999.0,) if kind == "head" else (999.0, 999.0)
            guide.feed(now, value, usable)
            # Duplicate capture timestamp must not increase accepted sample count.
            count = len(guide.values)
            guide.feed(now, value, usable)
            self.assertEqual(len(guide.values), count)
            now += 25
            self.assertLess(now, 30000)
        return guide

    def test_asymmetric_pitch_and_reverse_axis_use_full_normalized_range(self):
        for reverse in (False, True):
            guide = self.run_guide(reverse=reverse)
            self.assertTrue(guide.passed, guide.report)
            direction = -1 if reverse else 1
            for degrees, expected in ((-12, 0), (-4, .25), (4, .5), (16, .75), (28, 1)):
                self.assertEqual(guide.normalized((degrees * direction,)), (expected,))
            self.assertEqual(guide.normalized((-13 * direction,)), (0,))
            self.assertEqual(guide.normalized((29 * direction,)), (1,))
            self.assertIsNone(guide.normalized((50 * direction,)))
            self.assertEqual(set(guide.checks), {"neutral", "up", "down"})

    def test_tongue_asymmetric_personal_range_and_recheck(self):
        guide = self.run_guide("tongue")
        self.assertTrue(guide.passed, guide.report)
        self.assertEqual(guide.normalized((0.45, 0.55)), (0.5, 0.5))
        self.assertEqual(guide.normalized((0.2, 0.8)), (0, 1))
        self.assertIsNone(guide.normalized((0.01, 0.5)))
        checked = self.run_guide("tongue", existing=guide.fits)
        self.assertTrue(checked.passed, checked.report)
        self.assertEqual(len(checked.steps), 6)

    def test_missing_overlapping_or_failed_fresh_checks_do_not_pass(self):
        for kwargs in (dict(missing=True), dict(overlap=True), dict(bad_check=True)):
            for kind in ("head", "tongue"):
                guide = self.run_guide(kind, **kwargs)
                self.assertFalse(guide.passed)
                self.assertIn("rejected", guide.report)

    def test_range_schema_rejects_inverted_or_tiny_axes(self):
        guide = self.run_guide("tongue")
        data = {key: asdict(fit) for key, fit in guide.fits.items()}
        self.assertEqual(validate_range(data, guide.config), guide.fits)
        data["x"]["low"] = 0.6
        with self.assertRaises(ValueError):
            validate_range(data, guide.config)

    def test_no_capture_before_prompt_ack(self):
        guide = MovementGuide("head", DetectionConfig())
        for t in range(100):
            guide.feed(t, (0.5,), True)
        self.assertEqual(guide.values, [])
        guide.present(9, 100, "prepare")
        self.assertIsNone(guide.start_ms)
