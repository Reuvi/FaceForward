"""Selected capture joins, profile migration, scalar exports and screen guidance."""

import csv
from copy import deepcopy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from threading import RLock
from unittest.mock import patch
from App.research_runtime import ResearchSession, Fixations, validate_profile


def observation(t, seq=None, left=0.0, right=0.0, **extra):
    values = dict(
        left_closure=left,
        right_closure=right,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        face_x=0.5,
        face_y=0.5,
        face_scale=-0.8,
        left_iris_x=0.5,
        left_iris_y=0.1,
        right_iris_x=0.5,
        right_iris_y=0.1,
    )
    values.update(extra)
    p = dict(
        format="face_features_v1",
        session_id="session",
        subject_id="face",
        sequence=int(t) if seq is None else seq,
        timestamp_ms=t,
        generation=1,
        values=values,
    )
    f = dict(
        session_id=p["session_id"],
        sequence=p["sequence"],
        timestamp_ms=t,
        faces=[{"subject_id": "face"}],
    )
    return f, p


class ResearchSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.core = ResearchSession(lambda: self.now)
        self.addCleanup(self.core.close)
        self.feed()

    def feed(self, **values):
        self.now += 25
        f, p = observation(self.now, **values)
        self.core.observe(f, p, {})
        return f, p

    def test_missing_face_records_unknown_and_does_not_advance_gesture(self):
        self.core.arm()
        self.feed(left=1.0)
        self.now += 25
        frame, _ = observation(self.now)
        self.core.observe(frame, None, {})
        self.assertFalse(self.core.processor.armed)
        self.assertNotIn("left_closure", self.core.processor.trace[-1])
        self.assertEqual(self.core.processor.trace[-1]["t"], self.now / 1000)

    def test_join_mismatch_rejected_without_mutating_trace(self):
        f, p = observation(self.now + 25)
        p["subject_id"] = "other"
        count = len(self.core.processor.trace)
        with self.assertRaises(ValueError):
            self.core.observe(f, p, {})
        self.assertEqual(len(self.core.processor.trace), count)
        self.assertFalse(self.core.processor.armed)

    def test_duplicate_stale_nonfinite_frames_cannot_add_calibration_or_graph_data(
        self,
    ):
        f, p = self.feed()
        last = deepcopy(self.core.processor.trace[-1])
        self.core.observe(f, p, {})
        self.assertEqual(last, self.core.processor.trace[-1])
        self.now += 500
        self.core.observe(f, p, {})
        self.assertEqual(last, self.core.processor.trace[-1])
        f, p = observation(self.now)
        p["values"]["yaw"] = float("nan")
        with self.assertRaises(ValueError):
            self.core.observe(f, p, {})

    def test_trial_has_config_and_exports_null_without_display_holds(self):
        self.core.begin_trial("natural_blink", "train", 3)
        self.feed(left=None)
        trial = self.core.end_trial()
        self.assertEqual(trial["invalid"], 1)
        self.assertEqual(trial["expected"], 3)
        self.assertIn("left_min_ms", json.loads(trial["settings_json"]))
        with tempfile.TemporaryDirectory() as directory:
            out = self.core.export(directory)
            with (out / "frames.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[-1]["left_closure"], "")
            self.assertIn("profile", json.loads((out / "report.json").read_text()))

    def test_profile_round_trip_is_disarmed_and_validation_is_not_persisted(self):
        profile = self.core.profile()
        self.core.processor.armed = True
        self.core.gaze_ready = True
        self.core.load_profile(profile)
        self.assertFalse(self.core.processor.armed)
        self.assertFalse(self.core.gaze_ready)
        self.assertIsNone(self.core.packet)
        bad = deepcopy(profile)
        bad["fits"] = {"eyeBlinkLeft": {"open": 0.4, "active": 0.41}}
        with self.assertRaises(ValueError):
            self.core.load_profile(bad)
        self.assertEqual(self.core.profile(), profile)
        bad = deepcopy(profile)
        bad["settings"]["pose_gate"] = True
        with self.assertRaises(ValueError):
            validate_profile(bad)

    def test_overlapping_distributions_do_not_suggest_duration(self):
        for side in ("left", "right"):
            for i in range(6):
                for label, duration in (("natural_blink", 400), (side + "_wink", 300)):
                    self.core.processor.events.append(
                        dict(
                            channel=side,
                            role="train",
                            label=label,
                            duration_ms=duration,
                        )
                    )
        original = self.core.processor.config.copy()
        suggestion = self.core.suggest_duration()
        self.assertEqual(suggestion, original)
        self.assertIn("overlap", self.core.report)
        self.core.processor.events.clear()

    def test_calibration_and_fresh_input_gate_arming_and_trial_collection(self):
        self.core.calibrating = True
        with self.assertRaises(ValueError):
            self.core.arm()
        with self.assertRaises(ValueError):
            self.core.begin_trial("rest", "train")
        with self.assertRaises(ValueError):
            self.core.start_gaze((1440, 900))
        self.core.calibrating = False
        self.now += 300
        with self.assertRaises(ValueError):
            self.core.start_gaze((1440, 900))

    def test_gaze_cannot_validate_with_its_own_training_sequence(self):
        self.core.fixations = Fixations((1440, 900))
        self.core.fixations.active = False
        self.core.gaze = {"model": "placeholder"}
        with self.assertRaisesRegex(ValueError, "fresh validation"):
            self.core.submit("gaze_validation")
        self.core.gaze = None

    def test_fixations_wait_until_painted_ignore_duplicates_and_count_whole_episodes(
        self,
    ):
        run = Fixations((1440, 900))
        _, p = observation(1000)
        v = p["values"]
        run.feed(1000, v)
        self.assertEqual(run.samples, [])
        run.present(0, 1000)
        for t in range(1700, 3201, 50):
            run.feed(t, v)
            run.feed(t, v)
        self.assertEqual(len(run.episodes), 1)
        self.assertEqual(run.index, 1)
        self.assertEqual(run.episodes[0]["index"], 0)
        self.assertEqual(len(run.steps), 90)
        self.assertEqual(len(Fixations((1440, 900), validation_only=True).steps), 45)


@unittest.skipUnless(
    os.environ.get("RUN_TK_TESTS") == "1", "Explicit desktop Tk test required"
)
class ResearchWindowTests(unittest.TestCase):
    def test_graphs_trials_fullscreen_ack_and_cancellation(self):
        import tkinter as tk
        from tkinter import ttk
        from App.research_view import ResearchView, GRAPHS

        root = tk.Tk()
        root.geometry("1350x850")
        self.addCleanup(root.destroy)
        core = ResearchSession(lambda: 1000)
        self.addCleanup(core.close)
        session = SimpleNamespace(research=core, lock=RLock())
        parent = ttk.Frame(root)
        parent.pack(fill="both", expand=True)
        with patch("Vision.eye_view.CalibrationSounds"):
            view = ResearchView(parent, root, session, lambda fn: fn())
            self.addCleanup(view.close)
            root.update()
            for graph in GRAPHS:
                view.graph.set(graph)
                view.tick()
                root.update()
            core.fixations = Fixations(
                (root.winfo_screenwidth(), root.winfo_screenheight())
            )
            view.tick()
            root.update()
            view.tick()
            root.update()
            self.assertIsNotNone(core.fixations.start)
            self.assertTrue(view.popup.ready)
            self.assertEqual(view.popup.window.winfo_width(), root.winfo_screenwidth())
            view.gaze_action("pause")
            self.assertTrue(core.fixations.paused)
            view.popup.cancel_button.invoke()
            self.assertIsNone(core.fixations)
            self.assertIsNone(view.popup)
