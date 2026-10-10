from dataclasses import replace
import math
import random
import unittest

from Processing.mouse.config import AxisConfig, EyeConfig, MouseConfig
from Processing.mouse.engine import AxisFilter, MouseProcessor
from Processing.mouse.mocks import raw_frame
from Processing.mouse.output import mouse_message
from Processing.mouse.signals import decode, one_hot_matrix, one_hot_vector


class SignalTests(unittest.TestCase):
    def test_matrix_corners_and_rectangular_grid(self):
        self.assertEqual(one_hot_matrix([[1, 0, 0], [0, 0, 0]]), (0, 0))
        self.assertEqual(one_hot_matrix([[0, 0, 0], [0, 0, 1]]), (1, 1))
        self.assertEqual(one_hot_matrix([[0, 1, 0], [0, 0, 0]]), (0.5, 0))

    def test_vector_plain_row_and_column(self):
        for values in ([0, 1, 0], [[0, 1, 0]], [[0], [1], [0]]):
            self.assertEqual(one_hot_vector(values), 0.5)
        self.assertEqual(one_hot_vector([1, 0]), 0)
        self.assertEqual(one_hot_vector([0, 1]), 1)

    def test_missing_ambiguous_nonfinite_and_ragged_inputs(self):
        for values in (None, [], [1], [0, 0], [1, 1], [True, 0], [0, math.nan], [0, 0.5]):
            with self.subTest(values=values):
                self.assertIsNone(one_hot_vector(values))
        for values in (None, [], [[1]], [[1, 0], [0]], [[0, 0], [0, 0]], [[1, 0], [0, 1]], [[1, math.inf], [0, 0]]):
            self.assertIsNone(one_hot_matrix(values))

    def test_raw_eye_polarity_and_separate_signals(self):
        frame = raw_frame(0, 0, {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": True, "right": False})
        sample = decode(frame, MouseConfig(), "mock-person")
        self.assertIs(sample.left_closed, True)
        self.assertIs(sample.right_closed, False)
        sample = decode(frame, MouseConfig(closed_value=0), "mock-person")
        self.assertIs(sample.left_closed, False)
        self.assertIs(sample.right_closed, True)

    def test_signalframe_v1_selected_subject_confidence_and_eye_convention(self):
        def item(value, confidence=1):
            return {"value": value, "confidence": confidence, "valid": True}
        frame = {"schema_version": 1, "session_id": "a", "sequence": 0, "timestamp_ms": 0,
                 "faces": [{"subject_id": "other", "signals": {}}, {"subject_id": "me", "signals": {
                     "left_eye_open": item(0), "right_eye_open": item(1), "tongue_x": item(0.3),
                     "tongue_y": item(0.7), "head_y": item(0.2, 0.1)}}]}
        sample = decode(frame, MouseConfig(closed_value=0), "me")
        self.assertEqual(sample.pointer, (0.3, 0.7))
        self.assertIsNone(sample.scroll)
        self.assertEqual((sample.left_closed, sample.right_closed), (True, False))
        with self.assertRaises(ValueError):
            decode(frame, MouseConfig(), "missing")


class ConfigTests(unittest.TestCase):
    def test_json_roundtrip_independent_eye_settings(self):
        config = MouseConfig(left_eye=EyeConfig(200, 30), right_eye=EyeConfig(600, 90))
        self.assertEqual(config, MouseConfig.from_dict(config.to_dict()))

    def test_bad_settings_rejected(self):
        for values in ({"closed_value": True}, {"mode": "gamepad"}, {"mystery": 1},
                       {"left_eye": {"dwell_ms": 0}}, {"pointer": {"smoothing_ms": math.nan}},
                       {"pointer": {"deadzone": 1}}, {"stale_ms": 100, "interpolation_ms": 150}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MouseConfig.from_dict(values)


class AxisTests(unittest.TestCase):
    def test_causal_interpolation_and_hold(self):
        axis = AxisFilter(AxisConfig(), 1)
        axis.push(0, 0); axis.push(1, 100)
        self.assertEqual(axis.interpolate(50), (0.5,))
        self.assertEqual(axis.interpolate(200), (1,))
        axis.push(None, 210); axis.push(0, 220)
        self.assertEqual(axis.interpolate(215), (0,))

    def test_deadzone_and_activation_hysteresis(self):
        axis = AxisFilter(AxisConfig(deadzone=0.2, hysteresis=0.05, smoothing_ms=0), 1)
        axis.push(0.62, 0)  # Signed magnitude .24: below activation .25.
        self.assertEqual(axis.step(0, 0, 0.1), (0,))
        axis.push(0.7, 100); axis.step(100, 0, 0.1)
        self.assertTrue(axis.active)
        axis.push(0.62, 200); axis.step(200, 0, 0.1)
        self.assertTrue(axis.active)
        axis.push(0.59, 300); axis.step(300, 0, 0.1)
        self.assertFalse(axis.active)

    def test_acceleration_limits_and_radial_speed_bound(self):
        axis = AxisFilter(AxisConfig(smoothing_ms=0, acceleration=2), 2)
        axis.push((1, 1), 0)
        previous = (0, 0)
        for i in range(100):
            value = axis.step(i * 10, 0, 0.01)
            self.assertLessEqual(math.dist(value, previous), 0.0200001)
            self.assertLessEqual(math.hypot(*value), 1.0000001)
            previous = value

    def test_boost_decays_while_offset_retains_steady_velocity(self):
        axis = AxisFilter(AxisConfig(smoothing_ms=0, boost_gain=0.2), 1)
        axis.push(0.5, 0); axis.push(0.75, 100)
        axis.step(100, 0, 0.01)
        initial_boost, initial_target = axis.boost, axis.target[0]
        for i in range(1, 201):
            axis.step(100 + i * 10, 0, 0.01)
        self.assertGreater(initial_boost, axis.boost)
        self.assertGreater(initial_target, axis.target[0])
        self.assertGreater(axis.velocity[0], 0)

    def test_smoothing_independent_of_output_rate(self):
        outputs = []
        for hz in (50, 100, 200):
            axis = AxisFilter(AxisConfig(acceleration=100, smoothing_ms=120, boost_gain=0), 1)
            axis.push(0.8, 0)
            for i in range(hz):
                axis.step((i + 1) * 1000 / hz, 0, 1 / hz)
            outputs.append(axis.velocity[0])
        self.assertAlmostEqual(min(outputs), max(outputs), places=10)


class ProcessorTests(unittest.TestCase):
    def simulate(self, states, duration=1200, config=None, sample_every=20):
        processor = MouseProcessor(config)
        processor.arm()
        outputs = []
        sequence = 0
        for timestamp in range(0, duration + 1, 10):
            if timestamp % sample_every == 0:
                state = {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": False, "right": False}
                state.update(states(timestamp))
                processor.accept(raw_frame(sequence, timestamp, state), timestamp)
                sequence += 1
            outputs.append(processor.tick(timestamp))
        return processor, outputs

    def test_ordinary_short_blinks_make_no_click(self):
        _, outputs = self.simulate(lambda t: {"left": 200 <= t < 320, "right": 200 <= t < 320})
        self.assertFalse(any(o["left_click"] or o["right_click"] for o in outputs))

    def test_independent_wink_and_single_hold_release(self):
        _, outputs = self.simulate(lambda t: {"left": 200 <= t < 800})
        active = [o for o in outputs if o["left_click"]]
        self.assertEqual(active[0]["timestamp_ms"], 520)
        self.assertEqual(active[-1]["timestamp_ms"], 850)
        self.assertFalse(any(o["right_click"] for o in outputs))
        self.assertEqual(sum(o["left_click"] and not p["left_click"] for p, o in zip(outputs, outputs[1:])), 1)

    def test_both_long_closures_are_independent_no_suppression(self):
        config = MouseConfig(left_eye=EyeConfig(200, 40), right_eye=EyeConfig(500, 100))
        _, outputs = self.simulate(lambda t: {"left": 200 <= t < 900, "right": 200 <= t < 900}, config=config)
        left = [o for o in outputs if o["left_click"]]
        right = [o for o in outputs if o["right_click"]]
        self.assertEqual(left[0]["timestamp_ms"], 400)
        self.assertEqual(right[0]["timestamp_ms"], 700)
        self.assertEqual(left[-1]["timestamp_ms"], 930)
        self.assertEqual(right[-1]["timestamp_ms"], 990)

    def test_dwell_uses_elapsed_time_across_input_rates(self):
        starts = []
        for interval in (20, 40, 100):
            _, outputs = self.simulate(lambda t: {"left": t >= 200}, sample_every=interval)
            starts.append(next(o["timestamp_ms"] for o in outputs if o["left_click"]))
        self.assertEqual(starts, [520, 520, 600])  # First actual sample after 320 ms dwell.

    def test_start_closed_requires_own_open_baseline(self):
        _, outputs = self.simulate(lambda t: {"left": True, "right": 200 <= t < 900})
        self.assertFalse(any(o["left_click"] for o in outputs))
        self.assertTrue(any(o["right_click"] for o in outputs))

    def test_invalid_left_eye_does_not_cancel_right(self):
        processor, outputs = self.simulate(lambda t: {"left": t >= 200, "right": t >= 200}, duration=800)
        self.assertEqual((outputs[-1]["left_click"], outputs[-1]["right_click"]), (1, 1))
        frame = raw_frame(41, 820, {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": True, "right": True})
        frame["left_eye"] = None
        processor.accept(frame, 820)
        output = processor.tick(820)
        self.assertEqual((output["left_click"], output["right_click"]), (0, 1))

    def test_dropout_immediately_neutralizes_then_requires_rearm(self):
        processor, _ = self.simulate(lambda t: {"x": 0.75 if t > 100 else 0.5, "left": t >= 200}, duration=800)
        for timestamp in range(810, 1070, 10):
            output = processor.tick(timestamp)
        self.assertFalse(output["enabled"])
        self.assertEqual((output["pointer_x"], output["scroll_y"], output["left_click"]), (0.5, 0.5, 0))
        processor.accept(raw_frame(42, 1080), 1080)
        self.assertFalse(processor.tick(1080)["enabled"])

    def test_duplicate_does_not_refresh_watchdog(self):
        processor = MouseProcessor(); processor.arm()
        frame = raw_frame(0, 0); processor.accept(frame, 0); processor.tick(0)
        self.assertFalse(processor.accept(frame, 200)["accepted"])
        self.assertFalse(processor.tick(251)["enabled"])

    def test_input_gap_cannot_complete_a_pending_eye_dwell(self):
        processor, _ = self.simulate(lambda t: {"left": t >= 200}, duration=400)
        self.assertFalse(processor.left.down)
        # No output ticks during this gap: accept() must still reset continuity.
        processor.accept(raw_frame(21, 700, {"x": 0.5, "y": 0.5, "scroll": 0.5,
                                            "left": True, "right": False}), 700)
        self.assertFalse(processor.armed)
        self.assertEqual(processor.tick(700)["left_click"], 0)

    def test_output_clock_gap_disarms_even_with_fresh_input(self):
        processor, _ = self.simulate(lambda t: {}, duration=200)
        for sequence, timestamp in enumerate(range(220, 601, 20), start=11):
            processor.accept(raw_frame(sequence, timestamp), timestamp)
        output = processor.tick(600)
        self.assertFalse(output["enabled"])
        self.assertIn("Output clock gap", output["status"])

    def test_stopped_clock_gap_preserves_stopped_status(self):
        processor = MouseProcessor()
        processor.tick(0)
        self.assertEqual(processor.tick(1000)["status"], "Preview stopped")

    def test_new_session_disarms_and_unknown_subject_cannot_take_over(self):
        processor, _ = self.simulate(lambda t: {}, duration=200)
        self.assertTrue(processor.enabled)
        processor.accept(raw_frame(0, 220, session_id="restart"), 220)
        self.assertFalse(processor.tick(220)["enabled"])
        processor.arm()
        result = processor.accept(raw_frame(1, 240, subject_id="other"), 240)
        self.assertFalse(result["accepted"])
        self.assertFalse(processor.armed)

    def test_invalid_matrix_neutralizes_pointer_without_click_coupling(self):
        processor, _ = self.simulate(lambda t: {"x": 0.75 if t > 100 else 0.5, "left": t >= 200}, duration=800)
        frame = raw_frame(41, 820, {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": True, "right": False})
        frame["tongue"] = [[0, 0], [0, 0]]
        processor.accept(frame, 820)
        output = processor.tick(820)
        self.assertEqual(output["pointer_x"], 0.5)
        self.assertEqual(output["left_click"], 1)

    def test_future_malformed_and_backwards_clock(self):
        processor = MouseProcessor(); processor.arm()
        self.assertFalse(processor.accept(raw_frame(0, 100), 0)["accepted"])
        self.assertFalse(processor.accept({"sequence": 2}, 0)["accepted"])
        processor.tick(20)
        with self.assertRaises(ValueError):
            processor.tick(10)

    def test_output_adapter_tracks_distinct_output_and_source_sequences(self):
        _, outputs = self.simulate(lambda t: {}, duration=40)
        first, second = outputs[2:4]
        self.assertEqual(first["source_sequence"], second["source_sequence"])
        self.assertNotEqual(first["sequence"], second["sequence"])
        message = mouse_message(second)
        self.assertEqual(message["format"], "mouse_preview_v0")
        self.assertEqual(message["velocity"], {"x": 0.5, "y": 0.5, "scroll": 0.5})

    def test_random_valid_inputs_stay_finite_and_normalized(self):
        rng = random.Random(19)
        processor, _ = self.simulate(lambda t: {}, duration=100)
        for index in range(1000):
            timestamp = 120 + index * 10
            state = {"x": rng.random(), "y": rng.random(), "scroll": rng.random(),
                     "left": bool(rng.randrange(2)), "right": bool(rng.randrange(2))}
            processor.accept(raw_frame(index + 6, timestamp, state), timestamp)
            output = processor.tick(timestamp)
            for key in ("pointer_x", "pointer_y", "scroll_y", "left_click", "right_click"):
                self.assertTrue(math.isfinite(output[key]) and 0 <= output[key] <= 1)


if __name__ == "__main__":
    unittest.main()
