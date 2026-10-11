"""Real C library, dry-run backend; never injects native events."""

from copy import deepcopy
import os
from pathlib import Path
import time
import unittest

from Drivers.binding import DriverError
from Drivers.output import DriverOutput, default_library

LIBRARY = Path(os.environ.get("FID_LIBRARY", default_library()))
RUNTIME = {"pointer_speed": 900, "scroll_speed": 480}


def command(seq, now, *, enabled=True):
    return {"format": "device_control_v1", "output_session_id": "output-1", "sequence": seq,
            "timestamp_ms": now, "enabled": enabled, "mapping_id": "gaming-keyboard-mouse-1", "mapping_revision": 1,
            "source": {"session_id": "capture-1", "sequence": seq, "timestamp_ms": now, "subject_id": "single-user"},
            "buttons": {"left_click": 0, "right_click": 0},
            "keys": dict.fromkeys(("w", "a", "s", "d", "space", "left_shift"), 0),
            "pointer": {"mode": "velocity", "x": .5, "y": .5}, "scroll_y": .5,
            "known": dict.fromkeys(("left_click", "right_click", "head_x", "head_y", "pointer"), True)}


@unittest.skipUnless(LIBRARY.is_file(), "Build Drivers or set FID_LIBRARY")
class OutputAdapterTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.output = DriverOutput("dry-run", LIBRARY, clock=lambda:self.now)
        self.addCleanup(self.output.close)
        self.seq = 0
        self.send()

    def send(self, **updates):
        self.seq += 1; self.now += 1
        data = command(self.seq,self.now)
        data.update(updates)
        self.output.submit(data,RUNTIME)
        return data

    def test_short_eye_pulses_and_holds_are_exact_clicks(self):
        for _ in range(4):
            self.send(buttons={"left_click":1,"right_click":1})
        self.assertEqual((self.output.counts[3],self.output.counts[4]),(1,1))
        self.send()
        self.send(buttons={"left_click":1,"right_click":0})
        self.send()
        self.assertEqual((self.output.counts[3],self.output.counts[4]),(2,1))

    def test_key_order_hold_and_stop_release(self):
        keys = command(0,0)["keys"];keys.update(w=1,left_shift=1)
        self.send(keys=keys)
        self.send(keys=keys)
        downs = [event["x"] for event in self.output.events if event["type"]==7]
        self.assertEqual(downs,[32,1])
        self.send(enabled=False)
        ups = [event["x"] for event in self.output.events if event["type"]==8]
        self.assertEqual(ups,[1,32])
        self.assertEqual(self.output.status().held_key_mask,0)

    def test_capture_age_cannot_be_renewed_by_output_ticks(self):
        source = self.send()["source"]
        self.now += 251
        with self.assertRaises(DriverError):self.send(source=source)
        self.assertFalse(self.output.status().enabled)

    def test_malformed_duplicate_unknown_and_changed_origin_fail_closed(self):
        cases = [lambda x:x.update(sequence=self.seq),
                 lambda x:x["pointer"].update(x=float("nan")),
                 lambda x:x["keys"].update(w=2),
                 lambda x:x["source"].update(session_id="new-session"),
                 lambda x:x.update(output_session_id="new-output"),
                 lambda x:x["known"].update(pointer=False),
                 lambda x:x.update(mapping_revision=2)]
        for mutate in cases:
            self.output.pause();self.send()
            keys = command(0,0)["keys"];keys["w"] = 1
            self.send(keys=keys)
            data = command(self.seq+1,self.now)
            data["pointer"]["x"] = .8
            mutate(data)
            with self.assertRaises(DriverError):self.output.submit(data,RUNTIME)
            self.assertFalse(self.output.status().enabled)
            self.assertEqual(self.output.status().held_key_mask,0)

    def test_rearm_requires_actual_neutral_and_disabled_cannot_hold(self):
        self.output.pause()
        with self.assertRaises(DriverError):self.send(buttons={"left_click":1,"right_click":0})
        self.send()
        with self.assertRaises(DriverError):self.send(enabled=False,pointer={"mode":"velocity","x":.7,"y":.5})
        self.assertFalse(self.output.status().enabled)

    def test_native_worker_watchdog_releases_when_python_stops_sending(self):
        keys = command(0,0)["keys"];keys["space"] = 1
        self.send(keys=keys)
        deadline = time.monotonic()+2
        while self.output.status().enabled and time.monotonic()<deadline:
            time.sleep(.01)
        status = self.output.status()
        self.assertTrue(status.timed_out)
        self.assertFalse(status.enabled)
        self.assertEqual(status.held_key_mask,0)
        # A resumed producer must not enable itself again.
        with self.assertRaises(DriverError):self.send()
        self.output.collect()
        self.assertTrue(any(event["type"]==8 and event["x"]==16 for event in self.output.events))

    def test_close_releases_and_invalid_library_is_clear(self):
        keys = command(0,0)["keys"];keys["s"] = 1
        self.send(keys=keys)
        self.output.close()
        self.assertFalse(self.output.handle)
        self.assertTrue(any(event["type"]==8 and event["x"]==4 for event in self.output.events))
        with self.assertRaises(DriverError):DriverOutput("dry-run", LIBRARY.parent/"missing.so")

    def test_old_mouse_preview_format_works_without_keys(self):
        self.output.pause()
        data = {"format":"mouse_preview_v0","sequence":1,"timestamp_ms":self.now,"enabled":True,
                "buttons":{"left":0,"right":0},"velocity":{"x":.5,"y":.5,"scroll":.5},
                "source":deepcopy(command(1,self.now)["source"])}
        self.output.submit(data,RUNTIME)
        data.update(sequence=2)
        data["buttons"]["right"] = 1
        self.output.submit(data,RUNTIME)
        self.assertEqual(self.output.counts[4],1)

    def target(self, x=.55, y=.45, speed=1, **updates):
        return self.send(pointer=dict(mode='target',x=x,y=y,speed=speed),**updates)

    def test_target_arrives_and_repeated_destination_stays_still(self):
        self.output.pause()
        self.target()
        deadline=time.monotonic()+2
        while not self.output.status().target_reached and time.monotonic()<deadline:
            time.sleep(.01);self.target()
        status=self.output.status()
        self.assertTrue(status.target_reached)
        self.assertAlmostEqual(status.pointer_position_x,.55,places=6)
        self.assertAlmostEqual(status.pointer_position_y,.45,places=6)
        self.output.collect();count=self.output.counts[1]
        for _ in range(12):
            time.sleep(.01);self.target()
        self.assertEqual(self.output.counts[1],count)
        self.assertTrue(self.output.snapshot()['target_reached'])

    def test_zero_speed_unknown_and_disabled_target_never_pull_to_center(self):
        self.output.pause()
        # A zero-speed target less than half a pixel away used to snap into place.
        self.target(.5001,.5,0)
        for _ in range(4):
            time.sleep(.01);self.target(.5001,.5,0)
        self.assertEqual(self.output.status().pointer_position_x,.5)
        self.target(.9,.9)
        time.sleep(.04)
        known=command(0,0)['known'];known['pointer']=False
        self.target(.5,.5,0,known=known)
        before=self.output.snapshot()['pointer_position']
        for _ in range(4):
            time.sleep(.01);self.target(.5,.5,0,known=known)
        self.assertEqual(self.output.snapshot()['pointer_position'],before)
        self.target(.5,.5,0,enabled=False)
        self.assertFalse(self.output.status().enabled)
        self.assertEqual(self.output.snapshot()['pointer_position'],before)

    def test_target_validation_mode_changes_and_watchdog_release(self):
        for pointer in (dict(mode='target',x=.7,y=.5),dict(mode='target',x=.7,y=.5,speed=1.1),
                        dict(mode='target',x=float('nan'),y=.5,speed=1)):
            self.output.pause()
            with self.assertRaises(DriverError):self.send(pointer=pointer)
        self.send()
        with self.assertRaises(DriverError):self.target()
        self.target()
        with self.assertRaises(DriverError):self.send()
        known=command(0,0)['known'];known['pointer']=False
        with self.assertRaises(DriverError):self.target(known=known)
        with self.assertRaises(DriverError):self.target(enabled=False)
        self.target()
        keys=command(0,0)['keys'];keys['w']=1
        self.target(keys=keys)
        deadline=time.monotonic()+2
        while self.output.status().enabled and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(self.output.status().timed_out)
        self.assertEqual(self.output.status().held_key_mask,0)
        with self.assertRaises(DriverError):self.target()


if __name__ == "__main__":
    unittest.main()
