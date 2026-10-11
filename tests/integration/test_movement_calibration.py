"""Generated images exercise personal movement ranges and shared capture views."""

from copy import deepcopy
import importlib.util
import unittest

AVAILABLE = all(importlib.util.find_spec(name) for name in ("cv2", "numpy"))
if AVAILABLE:
    import cv2
    from App.mouse_runtime import MouseSession
    from Vision.calibration import EyeCalibration
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.signals import Envelope


@unittest.skipUnless(AVAILABLE, "Vision pixel dependencies required")
class MovementIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.sequence = 0
        self.session = MouseSession(clock=lambda: self.now)
        self.addCleanup(self.session.close)
        self.session.mode = "detector-demo"
        self.runtime = self.session.ensure_detector_runtime()
        self.core = self.runtime.workbench
        self.session.detector_command(
            "configure",
            dict(settle_ms=0, collect_ms=300, movement_rest_ms=0, min_samples=5),
        )
        self.feed()

    def feed(self, *, blank=False, round_candidate=False, **controls):
        self.now += 25
        self.sequence += 1
        image, observations = demo_image(**controls)
        if round_candidate:
            cv2.circle(image, (320, 326), 22, (115, 100, 215), -1)
        return self.session.deliver_detection(
            CapturedImage(Envelope("movement", self.sequence, self.now), image),
            [] if blank else observations,
            preview=False,
        )

    def collect(self, target, **controls):
        self.session.detector_command("collect", target)
        while self.core.job:
            self.feed(**controls)


    def guide(self, kind, recheck=False, **override):
        self.session.detector_command("start_movement_guide", kind, recheck)
        while self.core.movement_guide.active:
            state = self.core.movement_guide.state(self.now)
            if state["waiting"]:
                self.session.detector_command(
                    "present_movement_step", state["index"], state["phase"]
                )
            self.feed(**dict(self.runtime.demo_input(), **override))
            self.assertFalse(self.session.lab.processor.armed)
        return self.core.movement_guide

    def test_pitch_guide_preserves_eyes_and_uses_full_personal_range(self):
        eye = EyeCalibration(0.04, 0.25, 0.5)
        self.core.eyes["left"] = eye
        self.assertEqual(self.core.config.head_mode, "pitch")
        for _ in range(2):
            self.assertEqual(self.core.eyes["left"], eye)
            self.assertTrue(self.guide("head").passed, self.core.notice)
            for head, want in ((0.2, 0), (.35, .25), (0.5, 0.5), (.65, .75), (0.8, 1)):
                self.assertAlmostEqual(
                    self.feed(head=head)["faces"][0]["signals"]["head_y"]["value"],
                    want,
                    places=5,
                )
            self.assertFalse(
                self.feed(head=1)["faces"][0]["signals"]["head_y"]["valid"]
            )

    def test_pitch_ignores_image_translation_and_missing_transform_is_invalid(self):
        self.assertTrue(self.guide("head").passed)
        image, observations = demo_image(head=.8)
        observations[0].rotation = demo_image(head=.5)[1][0].rotation
        for rotation, expected in ((observations[0].rotation, .5), (None, None)):
            observations[0].rotation = rotation
            self.now += 25
            self.sequence += 1
            frame = self.session.deliver_detection(
                CapturedImage(Envelope("movement", self.sequence, self.now), image),
                observations, preview=False,
            )
            head = frame["faces"][0]["signals"]["head_y"]
            self.assertEqual(head["value"], expected)
            self.assertEqual(head["valid"], expected is not None)
        self.assertIsNotNone(self.core.head)

    def test_legacy_position_profile_discards_only_head_and_pitch_roundtrips(self):
        self.core.eyes["left"] = EyeCalibration(.04, .25, .5)
        self.assertTrue(self.guide("head").passed)
        original = self.core.export_calibration()
        fitted = self.core.head
        self.core.load_calibration(original)
        self.assertEqual(self.core.head, fitted)
        for explicit in (True, False):
            old = deepcopy(original)
            old.update(version=5, algorithm="color-tongue-tip-v5", tongue=None, tongue_range=None, tongue_measurement="color_tip_mouth_width_v1")
            old.pop("head_x"); old.pop("pupil")
            old["settings"].pop("head_yaw_separation")
            old["head"].update(low=.3, center=.5, high=.7)
            if explicit:
                old["settings"]["head_mode"] = "position"
            else:
                old["settings"].pop("head_mode")
            self.core.load_calibration(old)
            self.assertEqual(self.core.config.head_mode, "pitch")
            self.assertIsNone(self.core.head)
            migrated = self.core.export_calibration()
            for key in ("eyes", "winks"):
                self.assertEqual(migrated[key], original[key])
            self.assertIn("head pitch guide", self.core.notice)
            self.assertFalse(self.feed()["faces"][0]["signals"]["head_y"]["valid"])
            invalid = deepcopy(old)
            invalid["head"]["high"] = 1000
            with self.assertRaises(ValueError):
                self.core.load_calibration(invalid)
            self.assertEqual(self.core.export_calibration(), migrated)

    def test_old_settings_cannot_reenable_position_mode(self):
        self.session.detector_command("configure", dict(self.core.config.to_dict(), head_mode="position"))
        self.assertEqual(self.core.config.head_mode, "pitch")
        with self.assertRaises(ValueError):
            self.session.detector_command("set_head_mode", "position")

    def test_raw_before_calibration_and_same_capture_history_across_views(self):
        for head in (0.3, 0.4, 0.5, 0.6, 0.7):
            self.feed(head=head)
        setup = self.session.state(include_detector=True)
        calibration = self.session.detector_state()
        self.assertEqual(setup["detector"]["trace"], calibration["trace"])
        self.assertEqual(len(calibration["trace"]), self.sequence)
        self.assertEqual(setup["frame"]["sequence"], calibration["frame"]["sequence"])
        self.assertEqual(setup["frame"]["faces"], calibration["frame"]["faces"])
        self.assertIsNotNone(calibration["trace"][-1]["head_raw"])
        self.assertIsNotNone(calibration["trace"][-1]["left_raw"])
        self.assertIsNone(calibration["trace"][-1]["head_y"])
        self.assertNotIn("tongue_candidate_x", calibration["trace"][-1])
        self.assertIsNone(self.runtime.worker)







    def test_late_ui_ack_cannot_start_a_restarted_guide(self):
        self.session.detector_command("start_movement_guide", "head")
        previous = self.core.generation
        self.session.detector_command("cancel")
        self.session.detector_command("start_movement_guide", "head")
        self.session.detector_command("present_movement_step", 0, "prepare", previous)
        self.assertIsNone(self.core.movement_guide.start_ms)
        self.session.detector_command(
            "present_movement_step", 0, "prepare", self.core.generation
        )
        self.assertEqual(self.core.movement_guide.start_ms, self.now)
