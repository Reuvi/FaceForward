import copy
import json
from pathlib import Path
import tempfile
import unittest

from Vision.signals import CaptureSession, Envelope, SIGNALS, invalid, make_face, measurement, validate_frame
from Vision.sources import read_ndjson, replay, synthetic_records


class Clock:
    def __init__(self, now=1000.0):
        self.now = now
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds * 1000


class SignalTests(unittest.TestCase):
    def test_contract_example_accepted(self):
        path = Path(__file__).resolve().parents[2] / "Contracts/examples/signal-frame.json"
        validate_frame(json.loads(path.read_text()))

    def test_missing_measurements_are_invalid_and_independent(self):
        a, b = make_face("a"), make_face("b")
        self.assertEqual(set(a["signals"]), set(SIGNALS))
        self.assertTrue(all(item == invalid() for item in a["signals"].values()))
        a["signals"]["gaze_x"]["confidence"] = 0.9
        self.assertEqual(b["signals"]["gaze_x"], invalid())

    def test_bad_detector_values_fail_closed(self):
        for value in (float("nan"), float("inf"), -0.1, 1.1, True, "0.5", None, 10 ** 400):
            with self.subTest(value=value):
                self.assertEqual(measurement(value, 0.9), invalid())
        for confidence in (None, -1, 1.1, True, float("nan"), 0):
            self.assertEqual(measurement(0.5, confidence), invalid())

    def test_valid_endpoints_and_intermediate_v1_eyes(self):
        face = make_face("a", {"left_eye_open": measurement(0.3, 0.5),
                               "gaze_x": measurement(0, 1), "gaze_y": measurement(1, 1)})
        validate_frame(Envelope("s", 0, 0).frame([face]))

    def test_malformed_frames_rejected(self):
        good = Envelope("s", 0, 0).frame([make_face("a")])
        mutations = [
            ("schema_version", True), ("sequence", -1), ("sequence", 0.5),
            ("sequence", True), ("timestamp_ms", float("nan")),
            ("timestamp_ms", float("inf")), ("timestamp_ms", -1),
            ("session_id", ""), ("faces", {}), ("faces", [make_face("a")] * 3),
            ("faces", [make_face("a"), make_face("a")]),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                frame = copy.deepcopy(good)
                frame[key] = value
                with self.assertRaises(ValueError):
                    validate_frame(frame)
        for item in ({}, {"value": 0, "confidence": 0, "valid": False},
                     {"value": None, "confidence": 1, "valid": False},
                     {"value": 0.5, "confidence": True, "valid": True}):
            frame = copy.deepcopy(good)
            frame["faces"][0]["signals"]["gaze_x"] = item
            with self.assertRaises(ValueError):
                validate_frame(frame)

    def test_capture_envelope_restart_gaps_and_clock_failure(self):
        clock = Clock()
        session = CaptureSession(clock)
        first = session.stamp()
        clock.now += 17
        second = session.stamp(skipped=2)
        self.assertEqual((first.sequence, second.sequence), (0, 3))
        self.assertEqual(second.timestamp_ms - first.timestamp_ms, 17)
        self.assertEqual(first.frame([])["timestamp_ms"], 1000)
        session.restart()
        self.assertNotEqual(session.stamp().session_id, first.session_id)
        clock.now = 999
        with self.assertRaises(ValueError):
            session.stamp()


class ReplayTests(unittest.TestCase):
    def records(self):
        return [Envelope("recording", seq, stamp).frame([make_face("one")])
                for seq, stamp in ((1, 45), (3, 62), (9, 110))]

    def test_irregular_timing_and_gaps_are_preserved(self):
        clock = Clock()
        original = self.records()
        before = copy.deepcopy(original)
        output = list(replay(original, clock=clock, sleeper=clock.sleep))
        self.assertEqual([f["timestamp_ms"] for f in output], [1000, 1017, 1065])
        self.assertEqual([f["sequence"] for f in output], [1, 3, 9])
        self.assertNotEqual(output[0]["session_id"], "recording")
        self.assertEqual(len({f["session_id"] for f in output}), 1)
        self.assertEqual(original, before)

    def test_slow_consumer_does_not_refresh_old_capture_time(self):
        clock = Clock()
        stream = replay(self.records(), clock=clock, sleeper=clock.sleep)
        next(stream)
        clock.now += 1000
        self.assertEqual(next(stream)["timestamp_ms"], 1017)
        self.assertEqual(clock.sleeps, [])

    def test_restart_creates_new_session_and_rebases(self):
        clock = Clock()
        original = self.records()
        original.append(Envelope("restart", 0, 1).frame([]))
        output = list(replay(original, clock=clock, sleeper=clock.sleep))
        self.assertNotEqual(output[-1]["session_id"], output[-2]["session_id"])
        self.assertEqual(output[-1]["sequence"], 0)
        self.assertEqual(output[-1]["timestamp_ms"], 1065)

    def test_replaying_again_changes_session(self):
        clock = Clock()
        run = lambda: list(replay(self.records(), clock=clock, sleeper=clock.sleep))
        self.assertNotEqual(run()[0]["session_id"], run()[0]["session_id"])

    def test_nonfinite_clock_rejected(self):
        with self.assertRaises(ValueError):
            list(replay(self.records(), clock=lambda: float("nan")))

    def test_clock_regression_rejected(self):
        times = iter((1000.0, 999.0))
        with self.assertRaisesRegex(ValueError, "clock moved backwards"):
            list(replay(self.records(), clock=lambda: next(times)))

    def test_duplicates_and_backwards_capture_times_rejected(self):
        for key, value in (("sequence", 1), ("timestamp_ms", 44)):
            original = self.records()
            original[1][key] = value
            clock = Clock()
            with self.assertRaises(ValueError):
                list(replay(original, clock=clock, sleeper=clock.sleep))

    def test_ndjson_line_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.ndjson"
            path.write_text("\n" + json.dumps(self.records()[0]) + "\nnot json\n")
            with self.assertRaisesRegex(ValueError, ":3:"):
                list(read_ndjson(path))

    def test_synthetic_scenario_no_one_two_faces_loss_and_wink(self):
        frames = list(synthetic_records(count=245))
        self.assertEqual({len(frame["faces"]) for frame in frames}, {0, 1, 2})
        for frame in frames:
            validate_frame(frame)
            for face in frame["faces"]:
                for name in ("left_eye_open", "right_eye_open"):
                    item = face["signals"][name]
                    if item["valid"]:
                        self.assertIn(item["value"], (0, 1))
                self.assertEqual(face["signals"]["tongue_x"], invalid())
        wink = frames[32]["faces"][0]["signals"]
        self.assertEqual(wink["left_eye_open"]["value"], 0)
        self.assertEqual(wink["right_eye_open"]["value"], 1)
        self.assertEqual(wink["gaze_x"], invalid())
        self.assertNotEqual(frames[10]["faces"][0]["subject_id"],
                            frames[130]["faces"][0]["subject_id"])


if __name__ == "__main__":
    unittest.main()
