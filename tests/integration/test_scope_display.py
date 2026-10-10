"""Shared plot semantics, independent of Tk and control-state interpolation."""

from copy import deepcopy
import unittest

from LabUI.traces import darker, trace_runs
from Vision.eye_scope import scope_samples


class TraceDisplayTests(unittest.TestCase):
    def run_trace(self, values, **kwargs):
        return trace_runs([(i, value, "one") for i, value in enumerate(values)], **kwargs)

    def test_unknown_is_flat_and_recovery_is_a_jump_for_analog_and_bits(self):
        expected = [(True, [(0, .2), (1, .2), (2, .2), (3, .2)]),
                    (False, [(3, .2), (3, .8)])]
        for step in (False, True):
            self.assertEqual(self.run_trace([.2, None, None, .8], step=step), expected)

    def test_initial_unknown_and_zero_are_not_confused(self):
        self.assertEqual(self.run_trace([None, None, None]), [])
        self.assertEqual(self.run_trace([None, 0, None]), [(True, [(1, 0), (2, 0)])])

    def test_seed_before_visible_window_is_held_but_not_drawn_outside_it(self):
        self.assertEqual(self.run_trace([1, None, None, None], start=1.5),
                         [(True, [(1.5, 1), (2, 1), (3, 1)])])

    def test_session_identity_reset_and_time_reversal_drop_the_hold(self):
        for context in ("new", None):
            self.assertEqual(trace_runs([(0, 1, "old"), (1, None, context), (2, None, context)]), [])
        self.assertEqual(trace_runs([(3, 1, "old"), (2, None, "old"), (4, None, "old")]), [])

    def test_stale_interval_and_nonfinite_values_are_unknown(self):
        self.assertEqual(trace_runs([(0, 1, 0), (10, 0, 0)], max_gap=2),
                         [(True, [(0, 1), (10, 1)]), (False, [(10, 1), (10, 0)])])
        self.assertEqual(self.run_trace([0, float("nan"), float("inf")]),
                         [(True, [(0, 0), (1, 0), (2, 0)])])

    def test_display_never_mutates_source_values_or_validity(self):
        rows = [dict(timestamp_ms=i, subject_id="one", calibration_generation=2,
                     left_raw=.2, left_quality=q, head_y=.6, head_y_valid=False)
                for i, q in enumerate((1, 0, 0))]
        original = deepcopy(rows)
        self.assertEqual(trace_runs(scope_samples(rows, "left_raw", "one", 2)),
                         [(True, [(0, .2), (1, .2), (2, .2)])])
        self.assertEqual(trace_runs(scope_samples(rows, "head_y", "one", 2)), [])
        self.assertEqual(rows, original)

    def test_known_binary_changes_step_while_known_analog_changes_connect(self):
        self.assertEqual(self.run_trace([0, 1], step=True), [(False, [(0, 0), (1, 0), (1, 1)])])
        self.assertEqual(self.run_trace([0, 1]), [(False, [(0, 0), (1, 1)])])

    def test_dark_trace_retains_channel_color_at_lower_brightness(self):
        color = "#74ccef"
        dim = darker(color)
        for i in (1, 3, 5):
            self.assertAlmostEqual(int(dim[i:i+2], 16)/int(color[i:i+2], 16), .52, delta=.005)
