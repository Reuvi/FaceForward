"""Unknown eyes remain sampled numeric no-actions without fabricating observations."""

import csv
import io
import unittest

from Processing.eye_samples import eye_sample, trace_fields
from Processing.mouse.config import MouseConfig
from Processing.mouse.controller import Lab
from Processing.mouse.engine import MouseProcessor
from Processing.mouse.mocks import raw_frame
from Processing.mouse.signals import decode
from Processing.research.processor import ResearchProcessor
from LabUI.traces import trace_runs


def feature(t, sequence, left=None, right=None, **extra):
    return dict(
        format="face_features_v1",
        session_id="capture",
        sequence=sequence,
        timestamp_ms=t,
        subject_id="person",
        generation=1,
        values=dict(left_closure=left, right_closure=right, **extra),
    )


class EyeFallbackTests(unittest.TestCase):
    def test_raw_unknown_is_numeric_open_with_both_polarities(self):
        for closed_value in (0, 1):
            frame = raw_frame(0, 0)
            frame.update(left_eye=None, right_eye=None, tongue=None, head_vertical=None)
            decoded = decode(
                frame, MouseConfig(closed_value=closed_value), "mock-person"
            )
            self.assertIs(decoded.left_closed, False)
            self.assertIs(decoded.right_closed, False)
            self.assertFalse(decoded.left_known)
            self.assertFalse(decoded.right_known)
            self.assertIsNone(decoded.pointer)
            self.assertIsNone(decoded.scroll)

    def test_each_unknown_frame_reaches_mouse_processing_with_its_capture_envelope(
        self,
    ):
        processor = MouseProcessor()
        processor.arm()
        for sequence in range(40):
            frame = raw_frame(sequence, sequence * 25)
            frame.update(left_eye=None, right_eye=None)
            self.assertTrue(processor.accept(frame, sequence * 25)["accepted"])
            sample = processor.eye_sample
            self.assertEqual(sample["sequence"], sequence)
            self.assertEqual(sample["timestamp_ms"], sequence * 25)
            self.assertEqual(sample["left"], {"value": 0.0, "known": False})
            output = processor.tick(sequence * 25)
            self.assertEqual(output["left_click"], 0)
            self.assertEqual(output["right_click"], 0)
            self.assertIsNone(output["diagnostics"]["left_closed"])
        self.assertEqual(processor.accepted, 40)
        self.assertFalse(processor.left.ready)

    def test_unknown_releases_a_hold_immediately_and_does_not_arm_the_eye(self):
        processor = MouseProcessor()
        processor.arm()
        for i in range(30):
            frame = raw_frame(
                i,
                i * 25,
                {"left": i >= 5, "right": False, "x": 0.5, "y": 0.5, "scroll": 0.5},
            )
            processor.accept(frame, i * 25)
            processor.tick(i * 25)
        self.assertTrue(processor.left.down)
        frame = raw_frame(30, 750)
        frame["left_eye"] = None
        processor.accept(frame, 750)
        out = processor.tick(750)
        self.assertEqual(out["left_click"], 0)
        self.assertFalse(processor.left.ready)
        self.assertEqual(processor.eye_sample["left"]["value"], 0.0)
        self.assertEqual(processor.eye_sample["right"], {"value": 0.0, "known": True})

    def test_absent_person_still_records_neutral_eyes_and_never_binds_bystander(self):
        processor = MouseProcessor()
        processor.arm()
        for i in range(4):
            frame = dict(
                schema_version=1,
                session_id="capture",
                sequence=i,
                timestamp_ms=i * 25,
                faces=[{"subject_id": "bystander", "signals": {}}],
            )
            self.assertFalse(
                processor.accept(frame, i * 25)["accepted"]
            )  # No controllable subject.
            self.assertEqual(processor.eye_sample["sequence"], i)
            self.assertEqual(processor.eye_sample["left"]["value"], 0.0)
            self.assertFalse(processor.eye_sample["left"]["known"])
            self.assertFalse(processor.armed)
        before = processor.eye_sample
        processor.accept(dict(frame, sequence=2), 100)
        self.assertEqual(processor.eye_sample, before)
        processor.accept(dict(frame, sequence=5, schema_version=99), 100)
        self.assertEqual(processor.eye_sample, before)

    def test_unknown_cannot_finish_a_research_release_click(self):
        p = ResearchProcessor()
        seq = 0

        def feed(left, right=0.0, gap=25):
            nonlocal seq
            seq += 1
            p.feed(feature(seq * gap, seq, left, right), {}, seq * gap)

        feed(0.0)
        p.armed = True
        for _ in range(6):
            feed(0.0)
        for _ in range(18):
            feed(1.0)
        for _ in range(5):
            feed(None)
        self.assertEqual(p.eye_sample["left"], {"value": 0.0, "known": False})
        self.assertEqual(p.click_id, 0)
        self.assertFalse(p.events[-1]["accepted"])
        self.assertEqual(p.gates["left"].phase, "WAIT_OPEN")
        self.assertIsNone(p.trace[-1]["left_closure"])
        self.assertEqual(p.trace[-1]["left_input"], 0.0)
        self.assertFalse(p.trace[-1]["left_input_known"])
        runs = trace_runs(
            (r["t"], r["left_closure"], r["scope_context"]) for r in p.trace
        )
        self.assertTrue(any(unknown for unknown, _ in runs))
        for _ in range(5):
            feed(0.0)
        self.assertEqual(p.click_id, 0)

    def test_new_sequence_at_equal_time_is_a_sample_without_advancing_dwell(self):
        p = ResearchProcessor()
        p.feed(feature(100, 0, 0.0, 0.0), {}, 100)
        p.feed(feature(200, 1, 0.0, 0.0), {}, 200)
        p.armed = True
        p.feed(feature(225, 2, 1.0, 0.0), {}, 225)
        p.feed(feature(225, 3, 1.0, 0.0), {}, 225)
        self.assertEqual(len(p.trace), 4)
        self.assertEqual(p.eye_sample["sequence"], 3)
        self.assertEqual(p.trace[-1]["left_elapsed_ms"], 0)
        self.assertEqual(p.click_id, 0)

    def test_unknown_binary_classification_overrides_finite_ratio_score(self):
        p = ResearchProcessor()
        p.feed(feature(100, 1, 0.8, 1.0, left_eye_known=0, right_eye_known=1), {}, 100)
        self.assertEqual(p.eye_sample["left"], {"value": 0.0, "known": False})
        self.assertEqual(p.eye_sample["right"], {"value": 1.0, "known": True})
        self.assertIsNone(p.trace[-1]["left_closure"])
        self.assertEqual(p.trace[-1]["left_measured_closure"], 0.8)

    def test_missing_research_face_updates_every_frame_without_duplicate_refresh(self):
        p = ResearchProcessor()
        for i in range(6):
            frame = dict(session_id="capture", sequence=i, timestamp_ms=i * 25)
            self.assertTrue(p.feed_unknown(frame, i * 25))
            self.assertEqual(p.eye_sample["sequence"], i)
            self.assertEqual(p.trace[-1]["left_input"], 0.0)
            self.assertFalse(p.output["enabled"])
        self.assertEqual(len(p.trace), 6)
        self.assertFalse(p.feed_unknown(frame, 125))
        self.assertEqual(len(p.trace), 6)
        self.assertFalse(p.feed_unknown(dict(frame, sequence=7), 1000))

    def test_fallback_does_not_modify_the_source_measurements(self):
        raw = {"session_id": "a", "sequence": 1, "timestamp_ms": 20}
        normalized = eye_sample(raw, None)
        self.assertNotIn("left", raw)
        self.assertEqual(trace_fields(normalized)["left_input"], 0.0)

    def test_csv_export_includes_rows_before_the_first_capture(self):
        lab = Lab(clock=lambda: 0)
        lab.streaming = False
        lab.step(0)
        lab.processor.accept(raw_frame(0, 10), 10)
        lab.step(10)
        rows = list(lab.trace)
        self.assertIsNone(rows[0]["left_input"])
        self.assertIsNone(rows[0]["eye_sample_sequence"])
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        exported = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(exported[0]["left_input"], "")
        self.assertEqual(exported[1]["left_input"], "0.0")
