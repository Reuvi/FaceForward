import time
import unittest

from Processing.mouse.controller import Lab, now_ms
from Processing.mouse.mocks import raw_frame


class NativeControllerTests(unittest.TestCase):
    def setUp(self):
        self.lab = Lab()
        self.addCleanup(self.lab.close)

    def test_controls_are_independent(self):
        self.lab.control({"left": True})
        self.assertTrue(self.lab.manual["left"])
        self.assertFalse(self.lab.manual["right"])
        with self.assertRaises(ValueError):
            self.lab.control({"right": 1})

    def test_configuration_validation_is_atomic(self):
        with self.assertRaises(ValueError):
            self.lab.settings({"runtime": {"sample_hz": 0}})
        self.assertEqual(self.lab.runtime["sample_hz"], 30)
        self.lab.settings({"config": {"left_eye": {"dwell_ms": 180}, "right_eye": {"dwell_ms": 600}}})
        config = self.lab.state()["config"]
        self.assertEqual(config["left_eye"]["dwell_ms"], 180)
        self.assertEqual(config["right_eye"]["dwell_ms"], 600)

    def test_local_detector_calls_require_explicit_source(self):
        with self.assertRaises(ValueError):
            self.lab.ingest(raw_frame(0, now_ms()))
        self.lab.settings({"runtime": {"source": "external", "subject_id": "test-person"}})
        self.lab.action({"action": "arm"})
        result = self.lab.ingest(raw_frame(0, now_ms(), subject_id="test-person"))
        self.assertTrue(result["accepted"])
        self.lab.step(now_ms())
        self.assertTrue(self.lab.state()["message"]["enabled"])
        self.assertEqual(self.lab.state()["raw"]["subject_id"], "test-person")

    def test_trace_cursor_and_pause(self):
        self.lab.step(now_ms())
        row = self.lab.state()["trace"][-1]
        self.assertEqual(self.lab.state(row["id"])["trace"], [])
        self.lab.action({"action": "stream", "enabled": False})
        self.assertFalse(self.lab.state()["streaming"])

    def test_clock_survives_reconfiguration_and_calibration(self):
        self.lab.step(now_ms())
        self.lab.start()
        self.lab.action({"action": "calibrate"})
        for _ in range(5):
            self.lab.settings({"config": {"left_eye": {"dwell_ms": 200}}})
            self.lab.action({"action": "arm"})
        before = self.lab.trace_id
        deadline = time.monotonic() + 1
        while self.lab.trace_id <= before and time.monotonic() < deadline:
            self.lab.stop_event.wait(0.01)
        self.assertGreater(self.lab.trace_id, before)
        self.assertTrue(self.lab.thread.is_alive())

    def test_settings_roundtrip_includes_lab_controls(self):
        self.lab.settings({"runtime": {"sample_hz": 60, "rows": 15}, "config": {"pointer": {"boost_gain": 0}}})
        state = self.lab.state()
        other = Lab()
        self.addCleanup(other.close)
        other.settings({"config": state["config"], "runtime": state["runtime"]})
        self.assertEqual(other.runtime, self.lab.runtime)
        self.assertEqual(other.processor.config, self.lab.processor.config)


if __name__ == "__main__":
    unittest.main()
