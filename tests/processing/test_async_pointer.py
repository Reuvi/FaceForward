"""A slow tongue must neither forge samples nor stop independent eye/head input."""
from copy import deepcopy
import unittest

from Processing.mouse.config import MouseConfig
from Processing.mouse.engine import MouseProcessor
from Processing.mouse.signals import decode


def frame(sequence, timestamp, *, tongue_sequence=0, tongue_time=0, x=.5, head=.5, wink=0):
    def m(value):
        return dict(value=value, valid=value is not None, confidence=1 if value is not None else 0)
    result = dict(schema_version=1, session_id="live", sequence=sequence, timestamp_ms=timestamp,
                  faces=[dict(subject_id="me", signals=dict(
                      left_eye_open=m(0 if wink else 1), right_eye_open=m(1),
                      tongue_x=m(x), tongue_y=m(.5), head_y=m(head), gaze_x=m(.7), gaze_y=m(.6)))],
                  tongue_sample=dict(format="tongue_sample_v1", session_id="live", subject_id="me",
                                     sequence=tongue_sequence, timestamp_ms=tongue_time))
    result["eye_intent"] = dict(format="eye_intent_v1", session_id="live", subject_id="me",
                               sequence=sequence, timestamp_ms=timestamp,
                               left=dict(value=wink, known=True, state="wink" if wink else "open"),
                               right=dict(value=0, known=True, state="open"))
    return result


class AsyncPointerTests(unittest.TestCase):
    def test_repeated_origin_is_not_inserted_or_retimestamped_and_expires_independently(self):
        p = MouseProcessor(subject_id="me"); p.arm()
        p.accept(frame(0, 0), 0); p.tick(0)
        p.accept(frame(1, 30, tongue_sequence=1, tongue_time=25, x=.9), 30)
        for seq, now in enumerate(range(50, 301, 25), 2):
            self.assertTrue(p.accept(frame(seq, now, tongue_sequence=1, tongue_time=25, x=.9, head=.8, wink=1), now)["accepted"])
            output = p.tick(now)
            if now <= 275:
                self.assertEqual(list(p.pointer.history), [(0, (.5, .5)), (25, (.9, .5))])
        self.assertFalse(p.pointer.valid)
        self.assertTrue(output["enabled"])
        self.assertEqual(output["left_click"], 1)
        self.assertEqual(output["right_click"], 0)
        self.assertNotEqual(output["scroll_y"], .5)
        self.assertEqual(output["pointer_x"], .5)

    def test_output_clock_expires_tongue_between_capture_frames(self):
        p = MouseProcessor(subject_id="me"); p.arm()
        p.accept(frame(0, 0), 0); p.tick(0)
        p.accept(frame(1, 200, tongue_sequence=1, tongue_time=10, x=1), 200); p.tick(200)
        self.assertTrue(p.pointer.valid)
        output = p.tick(261)
        self.assertTrue(output["enabled"])
        self.assertFalse(p.pointer.valid)
        self.assertEqual(output["pointer_x"], .5)

    def test_malformed_stale_future_or_cross_subject_origin_only_invalidates_pointer(self):
        base = frame(10, 100)
        variants = [None, {}, dict(base["tongue_sample"], sequence=True),
                    dict(base["tongue_sample"], timestamp_ms=float("nan")),
                    dict(base["tongue_sample"], timestamp_ms=101),
                    dict(base["tongue_sample"], sequence=11),
                    dict(base["tongue_sample"], subject_id="other"),
                    dict(base["tongue_sample"], session_id="old")]
        for origin in variants:
            f = deepcopy(base); f["tongue_sample"] = origin
            p = MouseProcessor(subject_id="me"); p.arm()
            self.assertTrue(p.accept(f, 100)["accepted"])
            self.assertTrue(p.tick(100)["enabled"])
            self.assertFalse(p.pointer.valid)
            self.assertTrue(p.scroll.valid)

    def test_out_of_order_duplicate_after_invalid_and_rearm_need_new_tongue_evidence(self):
        p = MouseProcessor(subject_id="me"); p.arm()
        p.accept(frame(5, 50, tongue_sequence=5, tongue_time=45), 50); p.tick(50)
        p.accept(frame(6, 60, tongue_sequence=4, tongue_time=40), 60)
        self.assertFalse(p.pointer.valid)
        p.accept(frame(7, 70, tongue_sequence=5, tongue_time=45), 70)
        self.assertFalse(p.pointer.valid)
        p.accept(frame(8, 80, tongue_sequence=8, tongue_time=75), 80)
        self.assertTrue(p.pointer.valid)
        p.accept(frame(9, 90, tongue_sequence=8, tongue_time=75, x=None), 90)
        self.assertFalse(p.pointer.valid)
        p.accept(frame(10, 100, tongue_sequence=8, tongue_time=75), 100)
        self.assertFalse(p.pointer.valid)
        p.arm()
        p.accept(frame(11, 110, tongue_sequence=8, tongue_time=75), 110)
        self.assertFalse(p.pointer.valid)

    def test_gaze_and_legacy_keep_capture_timestamps(self):
        f = frame(9, 100, tongue_sequence=0, tongue_time=0)
        p = MouseProcessor(MouseConfig(pointer_source="gaze"), subject_id="me")
        self.assertTrue(p.accept(f, 100)["accepted"])
        self.assertEqual(list(p.pointer.history), [(100, (.7, .6))])
        self.assertFalse(decode(f, p.config, "me").pointer_async)
        del f["tongue_sample"]
        self.assertFalse(decode(f, MouseConfig(), "me").pointer_async)
