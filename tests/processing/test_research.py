"""Deterministic capture-time gestures, alternative controls and event delivery."""

import unittest
from copy import deepcopy
from Processing.research.processor import ResearchProcessor
from Processing.research.settings import settings
from Processing.research.models import GROUPS, fit_models, validate_models


def packet(t, left=0.0, right=0.0, sequence=None, **values):
    return dict(
        format="face_features_v1",
        session_id="session",
        subject_id="face",
        generation=1,
        sequence=int(t) if sequence is None else sequence,
        timestamp_ms=t,
        values=dict(
            left_closure=left,
            right_closure=right,
            yaw=0.0,
            pitch=0.0,
            roll=0.0,
            face_x=0.5,
            face_y=0.5,
            **values,
        ),
    )


BASE = dict(
    enabled=True,
    pointer_x=0.5,
    pointer_y=0.5,
    scroll_y=0.5,
    diagnostics={"raw_pointer": (0.5, 0.5)},
)


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.p = ResearchProcessor()
        self.t = 0
        self.feed()
        self.p.armed = True
        self.hold(150)

    def feed(self, left=0.0, right=0.0, gap=25, base=BASE, gaze=None, **kw):
        self.t += gap
        self.p.feed(packet(self.t, left, right, **kw), base, self.t, gaze)
        return self.p.output

    def hold(self, duration, left=0.0, right=0.0, **kw):
        for _ in range(duration // 25):
            self.feed(left, right, **kw)

    def eyes(self):
        return [e for e in self.p.events if e["channel"] in ("left", "right")]

    def test_short_blink_is_recorded_but_wink_emits_once_after_reopening(self):
        self.hold(100, 1, 1)
        self.hold(350)
        self.assertEqual(len(self.eyes()), 2)
        self.assertTrue(all(not e["accepted"] for e in self.eyes()))
        self.assertEqual(self.p.click_id, 0)
        self.hold(450, 1)
        self.assertEqual(self.p.click_id, 0)
        self.hold(125)
        self.assertEqual(self.p.click_id, 1)
        self.hold(1500)
        self.assertEqual(self.p.click_id, 1)
        event = self.p.events[-1]
        self.assertEqual(event["duration_ms"], 450)
        self.assertEqual(event["latency_ms"], 550)
        self.assertEqual(event["sample_age_ms"], 0)
        self.assertEqual(self.p.preview()["clicks"][0]["button"], "left")

    def test_independent_bilateral_winks_and_invalid_opposite_eye(self):
        self.hold(450, 1, 1)
        self.hold(125)
        self.assertEqual([e["button"] for e in self.p.clicks], ["left", "right"])
        self.hold(350)
        self.hold(450, 1, None)
        self.hold(125, 0, None)
        self.assertEqual(self.p.click_id, 3)

    def test_strict_mode_rejects_bilateral_then_requires_clean_open_baseline(self):
        self.p.configure({"policy": "strict"})
        self.p.armed = True
        self.hold(150)
        self.hold(450, 1, 1)
        self.hold(200, 1, 0)
        self.hold(200)
        self.assertEqual(self.p.click_id, 0)
        self.hold(450, 1, 0)
        self.hold(125)
        self.assertEqual(self.p.click_id, 1)

    def test_prolonged_closure_is_rejected_and_hold_is_explicit(self):
        self.hold(1500, 1)
        self.hold(125)
        self.assertEqual(self.p.click_id, 0)
        self.assertEqual(self.eyes()[-1]["reason"], "too long")
        self.p.configure({"click_mode": "hold"})
        self.p.armed = True
        self.hold(150)
        self.hold(1500, 1)
        self.assertEqual(self.p.output["buttons"]["left"], 1)
        self.feed(None)
        self.assertEqual(self.p.output["buttons"]["left"], 0)

    def test_tracking_loss_gap_duplicate_and_context_never_finish_pending_action(self):
        for failure in ("missing", "gap", "duplicate", "context"):
            with self.subTest(failure=failure):
                self.p = ResearchProcessor()
                self.feed()
                self.p.armed = True
                self.hold(150)
                self.hold(400, 1)
                if failure == "missing":
                    self.feed(None)
                elif failure == "gap":
                    self.feed(1, gap=300)
                elif failure == "duplicate":
                    self.p.feed(packet(self.t, 1), BASE, self.t)
                else:
                    frame = packet(self.t + 25, 1)
                    frame["subject_id"] = "new"
                    self.t += 25
                    self.p.feed(frame, BASE, self.t)
                self.hold(200)
                self.assertEqual(self.p.click_id, 0)

    def test_irregular_samples_measure_elapsed_time(self):
        self.feed(1)
        onset = self.t
        for gap in (43, 67, 90, 120):
            self.feed(1, gap=gap)
        self.feed(0, gap=41)
        duration = self.t - onset
        self.feed(0, gap=87)
        event = self.eyes()[-1]
        self.assertEqual(event["duration_ms"], duration)
        self.assertTrue(event["accepted"])

    def test_dwell_requires_departure_and_unknown_does_not_repeat(self):
        self.p.configure(
            {"left_source": "dwell", "right_source": "disabled", "dwell_ms": 250}
        )
        self.p.armed = True
        self.hold(500)
        self.assertEqual(self.p.click_id, 1)
        self.feed(base={})
        self.hold(700)
        self.assertEqual(self.p.click_id, 1)

    def test_absolute_gaze_latches_target_and_never_becomes_velocity(self):
        self.p.configure(
            {"pointer_mode": "gaze", "scroll_enabled": False, "gaze_smoothing_ms": 0}
        )
        self.p.armed = True
        self.hold(150, gaze=[0.2, 0.3])
        self.hold(450, 1, gaze=None)
        self.hold(125, gaze=[0.8, 0.7])
        self.assertEqual(self.p.clicks[-1]["position"], [0.2, 0.3])
        self.assertEqual(self.p.output["velocity"], [0.5, 0.5])
        self.assertEqual(self.p.output["position"], [0.8, 0.7])

    def test_unfitted_alternative_cannot_fire_then_calibrated_smile_can(self):
        self.p.configure({"left_source": "smile", "right_source": "disabled"})
        self.p.armed = True
        self.hold(150, mouthSmileLeft=0.1, mouthSmileRight=0.1)
        self.hold(500, mouthSmileLeft=0.9, mouthSmileRight=0.9)
        self.assertEqual(self.p.click_id, 0)
        self.p.fits = {
            k: {"open": 0.1, "active": 0.9}
            for k in ("mouthSmileLeft", "mouthSmileRight")
        }
        self.hold(150, mouthSmileLeft=0.1, mouthSmileRight=0.1)
        self.hold(450, mouthSmileLeft=0.9, mouthSmileRight=0.9)
        self.hold(125, mouthSmileLeft=0.1, mouthSmileRight=0.1)
        self.assertEqual(self.p.click_id, 1)

    def test_motion_recovery_invalidity_and_event_queue_gap(self):
        self.hold(400, 1)
        frame = packet(self.t + 25, 1)
        frame["values"]["yaw"] = 1.0
        self.t += 25
        self.p.feed(frame, BASE, self.t)
        self.hold(250)
        self.assertEqual(self.p.click_id, 0)
        for _ in range(300):
            self.p.emit("left", self.t)
        self.assertTrue(self.p.preview()["click_gap"])
        self.assertEqual(len(self.p.preview()["clicks"]), 256)
        self.assertFalse(self.p.preview(299)["click_gap"])
        self.assertEqual(len(self.p.preview(299)["clicks"]), 1)

    def test_right_alternative_uses_right_minimum(self):
        self.p.configure(
            {"left_source": "disabled", "right_source": "brow", "right_min_ms": 650}
        )
        self.p.fits = {"browInnerUp": {"open": 0.1, "active": 0.9}}
        self.p.armed = True
        self.hold(150, browInnerUp=0.1)
        self.hold(450, browInnerUp=0.9)
        self.hold(125, browInnerUp=0.1)
        self.assertEqual(self.p.click_id, 0)
        self.hold(300, browInnerUp=0.1)
        self.hold(700, browInnerUp=0.9)
        self.hold(125, browInnerUp=0.1)
        self.assertEqual(self.p.clicks[-1]["button"], "right")

    def test_settings_and_nonfinite_features_fail_closed(self):
        for values in (
            {"activation": 0.2, "release": 0.8},
            {"pointer_mode": "head"},
            {"left_source": "both_eyes"},
            {"model": "face", "click_mode": "hold"},
        ):
            with self.assertRaises(ValueError):
                settings(values)
        with self.assertRaises(ValueError):
            self.feed(float("nan"))
        self.assertFalse(self.p.armed)


class EventModelTests(unittest.TestCase):
    def test_identical_held_out_events_for_all_ablations(self):
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy required for optional models")
        events = []
        for role in ("train", "validation"):
            for i in range(30):
                positive = i % 2 == 0
                e = {k: 0.8 if positive else 0.1 for k in GROUPS["face"]}
                e.update(
                    duration_ms=450 if positive else 100,
                    channel="left",
                    label="left_wink" if positive else "natural_blink",
                    role=role,
                    trial_id=f"{role}-{i}",
                )
                events.append(e)
        # Normal unlabeled activity is always present between deliberate trials.
        events.append(dict(label="unlabeled", role="train", trial_id=None))
        models, report = fit_models(events)
        validate_models(models)
        self.assertEqual(set(models["left"]), set(GROUPS))
        self.assertNotIn("opposite_peak", GROUPS["face"])
        for model in models["left"].values():
            self.assertTrue(model["validated"])
            self.assertEqual(model["report"]["fp"], 0)
            self.assertEqual(model["report"]["validation_events"], 30)
        bad = deepcopy(models)
        bad["left"]["geometry"]["scale"][0] = 0
        with self.assertRaises(ValueError):
            validate_models(bad)
        with self.assertRaises(ValueError):
            fit_models([e for e in events if e["role"] == "train"])
