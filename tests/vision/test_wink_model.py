"""Synthetic appearance evidence, not a claim of accuracy on real people."""

from copy import deepcopy
import importlib.util
import unittest

from Vision.wink_model import NAMES, fit, check, classify, validate_models


def vector(wink=False, opened=False, variation=0):
    return [
        0.25 if opened else 0.04,
        0.08 if opened else 0.95,
        (0.65 if wink else 0.05) + variation,
        0.45 if wink else 0.04,
        0.3 if wink else 0.03,
        0.1,
        0.7,
        0.9,
    ]


def groups():
    negatives = [[vector(opened=True, variation=i * 0.001) for i in range(12)]]
    positives = [[vector(True, variation=i * 0.001) for i in range(12)]]
    return negatives, positives


@unittest.skipUnless(
    importlib.util.find_spec("numpy"), "Vision NumPy dependency required"
)
class WinkModelTests(unittest.TestCase):
    def model(self):
        negatives, positives = groups()
        return check(fit(negatives, positives), negatives, positives[:2])

    def test_open_and_closed_action_without_blink_examples(self):
        model = self.model()
        self.assertEqual(classify(model, vector(opened=True)), 0)
        self.assertEqual(classify(model, vector(True)), 1)
        self.assertFalse(
            any("duration" in k or "speed" in k or "opposite" in k for k in NAMES)
        )
        self.assertEqual(validate_models({"left": model}), {"left": model})

    def test_missing_nonfinite_or_out_of_range_appearance_is_unknown(self):
        model = self.model()
        self.assertIsNone(classify(model, None))
        bad = vector(True)
        bad[3] = float("nan")
        self.assertIsNone(classify(model, bad))
        bad = vector(True)
        bad[6] = 20
        self.assertIsNone(classify(model, bad))

    def test_overlapping_action_patterns_fail_instead_of_using_time(self):
        negatives, positives = groups()
        negatives[0] = deepcopy(positives[0])
        with self.assertRaises(ValueError):
            fit(negatives, positives)

    def test_fresh_bad_checks_reject_a_good_training_fit(self):
        negatives, positives = groups()
        model = fit(negatives, positives)
        negatives[0] = deepcopy(positives[0])
        with self.assertRaises(ValueError):
            check(model, negatives, positives[:2])

    def test_closed_action_can_match_natural_blink_appearance(self):
        # No extra squint/cheek movement or natural-blink contrast is mandatory.
        negatives = [[vector(opened=True) for _ in range(12)]]
        positives = [[vector() for _ in range(12)]]
        model = check(fit(negatives, positives), negatives, positives)
        self.assertEqual(classify(model, vector()), 1)
        self.assertEqual(classify(model, vector(opened=True)), 0)
        self.assertEqual(model["report"]["wink_attempts"], 1)
        validate_models({"left": model})

    def test_weak_or_malformed_saved_models_are_rejected(self):
        model = self.model()
        for mutate in (
            lambda m: m["names"].append("duration_ms"),
            lambda m: m["scale"].__setitem__(0, 0),
            lambda m: m.update(on=float("nan")),
            lambda m: m["report"].update(false_wink_frames=1),
        ):
            bad = deepcopy(model)
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_models({"left": bad})

    def test_two_eyes_can_have_different_models_or_one_unavailable(self):
        models = validate_models({"right": self.model()})
        self.assertNotIn("left", models)
        self.assertEqual(classify(models["right"], vector(True)), 1)
