"""Dry-run terminal tester checks. Never create a native backend here."""
import argparse
import ctypes as ct
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES))
import python_ctypes as driver

LIBRARY = None


class CommandTests(unittest.TestCase):
    def test_target_and_velocity_commands(self):
        command = driver.parse_command("move 0.6 0.8 0.2")
        self.assertEqual(command.frame.pointer_mode, 1)
        self.assertEqual(command.frame.target_speed, 0.6)
        self.assertEqual(command.frame.target_x, 0.8)
        self.assertEqual(command.frame.target_y, 0.2)
        command = driver.parse_command("velocity 0.65 0.2")
        self.assertEqual(command.frame.pointer_mode, 0)
        self.assertEqual(command.frame.pointer_x, 0.65)
        self.assertEqual(command.frame.pointer_y, 0.2)
        self.assertEqual(command.frame.scroll, 0.5)
        self.assertEqual(command.frame.left_click, 0)
        self.assertEqual(driver.parse_command("scroll 0").frame.scroll, 0)
        self.assertEqual(driver.parse_command("scroll 1").frame.scroll, 1)

    def test_buttons_and_keys(self):
        for text, field in (("click left", "left_click"), ("click right", "right_click"),
                            ("key delete", "delete_key"), ("key insert", "insert_key")):
            with self.subTest(text=text):
                frame = driver.parse_command(text).frame
                self.assertEqual(getattr(frame, field), 1)
                self.assertEqual(frame.pointer_x, 0.5)
        held = driver.parse_command("hold w shift").frame
        self.assertEqual(held.keys_down, 1 | 32)
        self.assertEqual(driver.parse_command("hold space").frame.keys_down, 16)

    def test_advanced_frames_and_comments(self):
        for text in ("frame 0 1 0.5 1 0 0 0", "0 1 0.5 1 0 0 0"):
            self.assertEqual(driver.parse_command(text).frame.pointer_y, 1)
        self.assertEqual(driver.parse_command("click left # example").frame.left_click, 1)
        self.assertEqual(driver.parse_command("# comment").name, "empty")

    def test_invalid_commands(self):
        cases = ("move", "move 0.5", "move 0 1 2", "move nan 0.5 0.5", "scroll inf",
                 "scroll -0.1", "move 1.1 0.5 0.5", "velocity 1.1 0.5", "scroll abc", "click middle",
                 "key space", "status extra", "stop extra", "frame 0 0", "banana",
                 "hold", "hold q", "hold w w",
                 "frame 0.5 0.5 0.5 1 0 0 nan", "click 'left")
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                driver.parse_command(text)

    def test_control_commands(self):
        for text in ("help", "status", "stop", "quit"):
            self.assertEqual(driver.parse_command(text).name, text)
        self.assertEqual(driver.parse_command("EXIT").name, "quit")
        self.assertEqual(driver.parse_command("q").name, "quit")

    def test_readable_summary_and_capabilities(self):
        totals = {"counts": {3: 1, 5: 1}, "dx": -10, "dy": 5, "scroll": -2}
        text = driver.summarize(totals)
        self.assertIn("pointer left: 10 units", text)
        self.assertIn("scroll up: 2 detents", text)
        self.assertIn("left click: 1", text)
        self.assertIn("key-up transitions: 1", driver.summarize(
            {"counts": {8: 1}, "dx": 0, "dy": 0, "scroll": 0}))
        self.assertIn("limited", driver.capability_names(63 | 64))

    def test_setup_errors_and_missing_library(self):
        lib = driver.load_driver(LIBRARY)
        self.assertIn("/dev/uinput", driver.error_message(lib, 3, "Linux"))
        self.assertIn("Accessibility", driver.error_message(lib, 3, "Darwin"))
        self.assertIn("modprobe", driver.error_message(lib, 4, "Linux"))
        self.assertIn("FID_NATIVE_BACKEND=ON", driver.error_message(lib, 2, "Linux"))
        self.assertIn("X11 and XRandR", driver.error_message(lib, 2, "Linux"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(driver.DriverError, "Shared library not found"):
                driver.load_driver(Path(directory) / "missing.so")
            invalid = Path(directory) / "invalid.so"
            invalid.write_text("not a library")
            with self.assertRaisesRegex(driver.DriverError, "Could not load"):
                driver.load_driver(invalid)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.lib = driver.load_driver(LIBRARY)

        def check(code):
            if code:
                raise driver.DriverError(driver.error_message(self.lib, code))

        self.check = check
        config = driver.Config()
        self.lib.fid_default_config(ct.byref(config))
        self.assertEqual(config.abi_version, 3)
        self.assertEqual(config.backend, 0, "Tests must use dry-run only")
        self.handle = ct.c_void_p()
        check(self.lib.fid_create(ct.byref(config), ct.byref(self.handle)))
        self.args = SimpleNamespace(native=False, delay=0, duration=0.25, rate=60)
        self.messages = []
        self.session = driver.TestSession(self.lib, self.handle, check, self.args, self.messages.append)

    def tearDown(self):
        self.session.stop(quiet=True)
        self.lib.fid_destroy(self.handle)

    def finish(self, text):
        self.assertTrue(self.session.start(driver.parse_command(text)))
        self.session.thread.join(timeout=3)
        self.assertFalse(self.session.thread.is_alive())
        self.assertEqual(self.session.last_error, "none", self.messages)
        return self.session.last_totals

    def wait_phase(self, phase):
        until = time.monotonic() + 2
        while time.monotonic() < until:
            with self.session.lock:
                if self.session.phase == phase:
                    return
            time.sleep(0.005)
        self.fail(f"Did not reach phase {phase}: {self.messages}")

    def test_clicks_keys_and_repeat_rearming(self):
        for command, kind in (("click left", 3), ("click left", 3), ("click right", 4),
                              ("key delete", 5), ("key insert", 6)):
            with self.subTest(command=command):
                self.assertEqual(self.finish(command)["counts"].get(kind), 1)

    def test_held_key_lifecycle(self):
        totals = self.finish("hold w shift")
        self.assertEqual(totals["counts"].get(7), 2)
        self.assertEqual(totals["counts"].get(8), 2)
        status = driver.Status()
        self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
        self.assertEqual(status.held_key_mask, 0)

    def test_motion_and_scroll_at_both_rates(self):
        for rate in (30, 60):
            self.args.rate = rate
            with self.subTest(rate=rate):
                totals = self.finish("velocity 0.65 0.2")
                self.assertGreater(totals["dx"], 0)
                self.assertLess(totals["dy"], 0)
                self.assertGreater(self.finish("scroll 0.8")["scroll"], 0)

    def test_neutral_and_status(self):
        self.assertIn("DRY-RUN", self.session.status_text())
        self.assertIn("Output: paused", self.session.status_text())
        totals = self.finish("velocity 0.5 0.5")
        self.assertEqual(totals["counts"], {})

    def test_target_trial_reports_arrival(self):
        totals = self.finish("move 1 0.51 0.5")
        self.assertGreater(totals["counts"].get(1, 0), 0)
        self.assertTrue(any("Arrived at (0.510, 0.500)" in m for m in self.messages), self.messages)

    def test_stop_during_trial_and_reject_overlap(self):
        self.args.duration = 5
        self.session.start(driver.parse_command("velocity 0.65 0.5"))
        self.wait_phase("running")
        self.assertIn("Output: enabled", self.session.status_text())
        self.assertFalse(self.session.start(driver.parse_command("click left")))
        start = time.monotonic()
        self.session.stop()
        self.assertLess(time.monotonic() - start, 1)
        self.assertFalse(self.session.thread.is_alive())
        status = driver.Status()
        self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
        emitted = status.emitted_events
        self.assertFalse(status.enabled)
        time.sleep(0.05)
        self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
        self.assertEqual(status.emitted_events, emitted)

    def test_stop_during_focus_delay(self):
        # Exercise the focus-delay branch with a dry-run handle, never native.
        self.args.native, self.args.delay = True, 5
        self.session.start(driver.parse_command("click left"))
        self.wait_phase("focus delay")
        self.session.stop()
        status = driver.Status()
        self.check(self.lib.fid_get_status(self.handle, ct.byref(status)))
        self.assertEqual(status.accepted_frames, 0)
        self.assertEqual(status.emitted_events, 0)
        self.assertFalse(status.enabled)


class CLITests(unittest.TestCase):
    def command(self, *args, **kwargs):
        return subprocess.run([sys.executable, str(EXAMPLES / "python_ctypes.py"),
                               "--library", str(LIBRARY), *args], text=True,
                              capture_output=True, timeout=5, **kwargs)

    def test_help_status_stop_quit_and_eof(self):
        result = self.command("--interactive", input="help\nstatus\nstop\nunknown\nquit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("click left", result.stdout)
        self.assertIn("no trial is queued", result.stdout)
        self.assertIn("Input error:", result.stdout)
        self.assertEqual(self.command("--interactive", input="").returncode, 0)

    def test_probe_and_missing_library_no_traceback(self):
        result = self.command("--probe")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Output: paused", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            result = self.command("--library", str(Path(directory) / "missing.so"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("cmake -S . -B build", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_hard_input_simulation_dry_run(self):
        help_result = subprocess.run(
            [sys.executable, str(EXAMPLES / "hard_input_simulation.py"), "--help"],
            text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("default: 180", help_result.stdout)
        self.assertIn("default: 1", help_result.stdout)
        self.assertIn("default: 3", help_result.stdout)
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / "hard_input_simulation.py"),
             "--library", str(LIBRARY), "--delay", "0", "--w-frames", "4",
             "--rate", "60", "--spin-seconds", "0.1",
             "--space-tap-seconds", "0.05", "--space-hold-seconds", "0.1"],
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Hold W (4 frames at 60 Hz)", result.stdout)
        self.assertIn("Move mouse right", result.stdout)
        self.assertIn("Move mouse left", result.stdout)
        self.assertIn("Tap Space", result.stdout)
        self.assertIn("Hold Space", result.stdout)
        self.assertIn("W down/up=1/1", result.stdout)
        self.assertIn("Space down/up=2/2", result.stdout)

    def test_ctrl_c_cleanup(self):
        process = subprocess.Popen([sys.executable, str(EXAMPLES / "python_ctypes.py"),
                                   "--library", str(LIBRARY), "--interactive", "--duration", "5"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            process.stdin.write("velocity 0.65 0.5\n")
            process.stdin.flush()
            # Startup/trial messages are flushed; wait for initialization.
            for _ in range(12):
                if "Trial:" in process.stdout.readline():
                    break
            time.sleep(0.1)
            process.send_signal(signal.SIGINT)
            out, err = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, err)
            self.assertIn("Stopped. Output paused and driver closed.", out)
            self.assertNotIn("Traceback", err)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", required=True, type=Path)
    args, remaining = parser.parse_known_args()
    LIBRARY = args.library.resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
