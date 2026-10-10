"""Intent frames bypass closure timers while preserving unknown/rearm behavior."""

from copy import deepcopy
import unittest

from Processing.mouse.config import MouseConfig, EyeConfig
from Processing.mouse.engine import MouseProcessor
from Vision.signals import Envelope, make_face, measurement


class WinkSampleTests(unittest.TestCase):
    def setUp(self):
        self.time = 1000
        self.sequence = 0
        self.core = MouseProcessor(
            MouseConfig(left_eye=EyeConfig(3000, 500), right_eye=EyeConfig(3000, 500)),
            "person",
        )
        self.core.arm()

    def frame(self, left="open", right="open", dt=1):
        self.time += dt
        self.sequence += 1
        values = {
            side + "_eye_open": measurement(1 if state == "open" else 0, 1)
            for side, state in (("left", left), ("right", right))
        }
        frame = Envelope("test", self.sequence, self.time).frame(
            [make_face("person", values)]
        )
        intent = dict(
            format="eye_intent_v1",
            subject_id="person",
            **{k: frame[k] for k in ("session_id", "sequence", "timestamp_ms")},
        )
        for side, state in (("left", left), ("right", right)):
            intent[side] = dict(
                value=None if state == "unknown" else int(state == "wink"),
                known=state != "unknown",
                state=state,
            )
        frame["eye_intent"] = intent
        return frame

    def feed(self, *args, **kwargs):
        frame = self.frame(*args, **kwargs)
        result = self.core.accept(frame, self.time)
        self.assertTrue(result["accepted"], result)
        return self.core.tick(self.time)

    def test_first_wink_frame_on_first_reopen_frame_off_regardless_of_legacy_timers(
        self,
    ):
        self.feed()
        self.assertEqual(self.feed("wink")["left_click"], 1)
        self.assertEqual(self.feed("wink", dt=200)["left_click"], 1)
        self.assertEqual(self.feed()["left_click"], 0)

    def test_long_blink_stays_off_and_both_eyes_remain_independent(self):
        self.feed()
        for _ in range(30):
            self.assertEqual(self.feed("blink", dt=100)["left_click"], 0)
        both = self.feed("wink", "wink")
        self.assertEqual((both["left_click"], both["right_click"]), (1, 1))
        right = self.feed("blink", "wink")
        self.assertEqual((right["left_click"], right["right_click"]), (0, 1))

    def test_unknown_holds_input_releases_output_and_requires_actual_open(self):
        self.feed()
        self.feed("wink", "wink")
        state = self.feed("unknown", "wink")
        self.assertEqual(self.core.eye_sample["left"], {"value": 1.0, "known": False})
        self.assertEqual((state["left_click"], state["right_click"]), (0, 1))
        self.feed("blink", "wink")
        self.assertEqual(self.feed("wink", "wink")["left_click"], 0)
        self.feed("open", "wink")
        self.assertEqual(self.feed("wink", "wink")["left_click"], 1)

    def test_malformed_or_wrong_envelope_never_falls_back_to_raw_closed_eye(self):
        self.feed()
        frame = self.frame("wink")
        for mutate in (
            lambda d: d["eye_intent"].update(sequence=0),
            lambda d: d["eye_intent"].update(subject_id="other"),
            lambda d: d["eye_intent"]["left"].update(value=True),
            lambda d: d["eye_intent"]["left"].update(state="blink"),
            lambda d: d["eye_intent"]["left"].update(known=False),
        ):
            bad = deepcopy(frame)
            mutate(bad)
            self.assertFalse(self.core.accept(bad, self.time)["accepted"])
            self.assertFalse(self.core.armed)

    def test_legacy_sample_without_intent_keeps_legacy_dwell(self):
        frame = self.frame()
        frame.pop("eye_intent")
        self.core.accept(frame, self.time)
        self.core.tick(self.time)
        for _ in range(5):
            frame = self.frame(dt=100)
            frame.pop("eye_intent")
            self.core.accept(frame, self.time)
            self.core.tick(self.time)
        frame = self.frame("wink")
        frame.pop("eye_intent")
        self.core.accept(frame, self.time)
        self.assertEqual(self.core.tick(self.time)["left_click"], 0)
