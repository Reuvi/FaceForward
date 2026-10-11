from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from Processing.mappings.config import GAMING_ID, HeadConfig, Mapping, read_mapping, write_mapping
from Processing.mappings.engine import GamingProcessor, HeadGate
from Processing.mouse.controller import Lab
from Processing.mouse.output import control_message
from gaming_fixtures import frame


class HeadThresholds(unittest.TestCase):
    def gate(self, **settings):
        gate = HeadGate(HeadConfig(smoothing_ms=0, **settings))
        gate.sample(.5, 0, True)
        return gate

    def test_exact_boundaries_hysteresis_and_capture_confirmation(self):
        for direction in (1, -1):
            gate = self.gate()
            gate.sample(.5+direction*.15, 10, True)
            self.assertEqual(gate.direction, 0)
            gate.sample(.5+direction*.15, 59, True)
            self.assertEqual(gate.direction, 0)
            gate.sample(.5+direction*.15, 60, True)
            self.assertEqual(gate.direction, direction)
            gate.sample(.5+direction*.10, 70, True)
            self.assertEqual(gate.direction, direction)
            gate.sample(.5+direction*.09, 80, True)
            self.assertEqual(gate.direction, 0)

    def test_same_timestamp_spike_and_reversal(self):
        gate = self.gate()
        for _ in range(20):
            gate.sample(.8, 10, True)
        self.assertEqual(gate.direction, 0)
        gate.sample(.5, 20, True)
        gate.sample(.8, 40, True)
        gate.sample(.8, 90, True)
        self.assertEqual(gate.direction, 1)
        gate.sample(.2, 100, True)
        self.assertEqual(gate.direction, 0)
        gate.sample(.2, 150, True)
        self.assertEqual(gate.direction, -1)

    def test_invalid_requires_neutral_not_just_valid_again(self):
        gate = self.gate(confirmation_ms=0)
        gate.sample(.8, 10, True)
        gate.sample(None, 11, True)
        gate.sample(.8, 20, True)
        self.assertFalse(gate.ready)
        self.assertEqual(gate.direction, 0)
        gate.sample(.5, 30, True)
        gate.sample(.8, 40, True)
        self.assertEqual(gate.direction, 1)

    def test_capture_rates_use_time(self):
        for hz in (10,30,60):
            gate = self.gate()
            period = 1000/hz
            gate.sample(.8, period, True)
            i = 1
            while not gate.direction:
                i += 1
                gate.sample(.8, i*period, True)
            self.assertGreaterEqual((i-1)*period, 50)
            self.assertLess((i-1)*period, 50+period+1e-9)

    def test_equal_timestamp_replaces_filter_evidence(self):
        gate = HeadGate(HeadConfig())
        gate.sample(.5, 0, True)
        gate.sample(.9, 20, True)
        gate.sample(.5, 20, True)
        self.assertAlmostEqual(gate.filtered, 0)


class GamingMappingTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.sequence = 0
        config = Mapping(pointer_mode="velocity", head_x=HeadConfig(smoothing_ms=0), head_y=HeadConfig(smoothing_ms=0))
        self.core = GamingProcessor(config, subject_id="person")
        self.core.arm()
        self.feed()

    def feed(self, dt=20, **values):
        self.now += dt
        self.sequence += 1
        result = self.core.accept(frame(self.sequence, self.now, **values), self.now)
        self.assertTrue(result["accepted"], result)
        return self.core.tick(self.now)

    def test_all_directions_and_simultaneous_head_axes(self):
        for x,y,expected in ((.2,.8,{"w","left_shift"}),(.8,.2,{"s","space"})):
            self.feed(head_x=x,head_y=y)
            snap = self.feed(dt=60,head_x=x,head_y=y)
            self.assertEqual({k for k,v in snap["keys"].items() if v},expected)
            self.assertEqual(snap["scroll_y"],.5)
            self.feed()

    def test_starting_deflected_does_not_press_until_neutral(self):
        self.core.arm()
        for _ in range(10):
            self.assertFalse(self.feed(head_x=.8)["enabled"])
        self.assertTrue(self.feed()["enabled"])
        self.feed(head_x=.8)
        self.assertEqual(self.feed(dt=60,head_x=.8)["keys"]["s"],1)

    def test_independent_eye_states_no_dwell_and_unknown_reopen(self):
        both = self.feed(dt=1,left="wink",right="wink",x=None,y=None)
        self.assertEqual((both["left_click"],both["right_click"]),(1,1))
        one = self.feed(dt=1,left="unknown",right="wink")
        self.assertEqual((one["left_click"],one["right_click"]),(0,1))
        self.assertEqual(self.core.eye_sample["left"],{"value":1.,"known":False})
        self.assertEqual(self.feed(left="wink")["left_click"],0)
        self.feed()
        self.assertEqual(self.feed(dt=1,left="wink")["left_click"],1)

    def test_instructions_never_report_held_while_waiting_for_neutral(self):
        self.core.arm()
        self.feed(x=.9)
        self.feed(x=.9,head_y=.8)
        snap = self.feed(dt=60,x=.9,head_y=.8)
        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["keys"]["w"],0)
        instruction = next(row["instruction"] for row in snap["instructions"] if row["id"]=="down")
        self.assertEqual(instruction,"W: waiting for neutral; released")

    def test_camera_without_intent_does_not_fall_back(self):
        self.now += 100
        bad = frame(self.sequence+1,self.now,left="wink")
        del bad["eye_intent"]
        self.assertTrue(self.core.accept(bad,self.now)["accepted"])
        snap = self.core.tick(self.now)
        self.assertFalse(snap["known"]["left_click"])
        self.assertEqual(snap["left_click"],0)

    def test_invalid_axis_releases_its_pair_only_and_requires_neutral(self):
        self.feed(head_x=.2,head_y=.8)
        self.feed(dt=60,head_x=.2,head_y=.8)
        snap = self.feed(head_x=None,head_y=.8,left="wink",x=None)
        self.assertEqual(snap["keys"]["w"],1)
        self.assertEqual(snap["keys"]["left_shift"],0)
        self.assertEqual(snap["left_click"],1)
        self.assertEqual(snap["pointer_x"],.5)
        self.assertFalse(snap["known"]["head_x"])
        self.feed(head_x=.2,head_y=.8)
        self.assertEqual(self.feed(dt=100,head_x=.2,head_y=.8)["keys"]["left_shift"],0)

    def test_precise_pupils_not_matrix_and_invalid_bypasses_smoothing(self):
        for _ in range(20):
            snap = self.feed(x=.623,y=.512)
        self.assertEqual(snap["diagnostics"]["raw_pointer"],[.623,.512])
        self.assertGreater(snap["pointer_x"],.5)
        stopped = self.feed(x=None)
        self.assertEqual((stopped["pointer_x"],stopped["pointer_y"]),(.5,.5))

    def test_neutral_jitter_stays_still_even_with_gain(self):
        self.core = GamingProcessor(replace(Mapping(pointer_mode="velocity"),pointer_gain=4),subject_id="person")
        self.core.arm()
        self.feed()
        for i in range(50):
            offset = .03 if i%2 else -.03
            snap = self.feed(x=.5+offset,y=.5-offset,head_x=.5+offset,head_y=.5-offset)
            self.assertFalse(any(snap["keys"].values()))
            self.assertEqual((snap["pointer_x"],snap["pointer_y"]),(.5,.5))

    def test_source_metadata_and_output_clock_cannot_refresh_source(self):
        snap = self.feed(left="wink")
        source = control_message(snap)["source"]
        for step in range(1,26):
            snap = self.core.tick(self.now+step*10)
            self.assertEqual(control_message(snap)["source"],source)
        snap = self.core.tick(self.now+251)
        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["left_click"],0)

    def test_duplicates_future_and_restart_disarm_rules(self):
        duplicate = frame(self.sequence,self.now)
        self.assertFalse(self.core.accept(duplicate,self.now)["accepted"])
        future = frame(self.sequence+1,self.now+1)
        self.assertFalse(self.core.accept(future,self.now)["accepted"])
        self.assertFalse(self.core.armed)
        self.core.arm(); self.feed()
        snap = self.feed(session="restarted")
        self.assertFalse(snap["enabled"])
        self.assertFalse(snap["armed"])

    def test_key_bindings_can_share_a_key_without_early_release(self):
        mapping = replace(Mapping(),head_x=HeadConfig(smoothing_ms=0,confirmation_ms=0),
                          head_y=HeadConfig(smoothing_ms=0,confirmation_ms=0),bindings=("w","space","w","s"))
        self.core = GamingProcessor(mapping,subject_id="person")
        self.core.arm(); self.feed()
        self.assertEqual(self.feed(head_x=.2,head_y=.8)["keys"]["w"],1)
        self.assertEqual(self.feed(head_x=.5,head_y=.8)["keys"]["w"],1)
        self.assertEqual(self.feed()["keys"]["w"],0)


class MappingControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.sequence = 0
        self.lab = Lab(clock=lambda:self.now)
        self.addCleanup(self.lab.close)
        self.lab.settings({"runtime":{"source":"external","subject_id":"person"}})
        self.lab.select_mapping(GAMING_ID)
        self.lab.action({"action":"arm"})
        self.feed()

    def feed(self, **values):
        self.now += 1
        self.sequence += 1
        return self.lab.ingest(frame(self.sequence,self.now,**values))

    def test_short_eye_transition_journal_without_a_periodic_tick(self):
        cursor = self.lab.command_id
        self.feed(left="wink")
        self.feed(left="open")
        state = self.lab.state(after_command=cursor)
        self.assertEqual([item["command"]["buttons"]["left_click"] for item in state["commands"]],[1,0])
        self.assertEqual([item["command"]["source"]["sequence"] for item in state["commands"]],[2,3])
        self.assertEqual(self.lab.state(after_command=state["command_id"])["commands"],[])

    def test_switch_records_release_keeps_responses_separate_and_disarms(self):
        self.feed(left="wink")
        self.lab.settings({"config":replace(self.lab.processor.config,interpolation_ms=25).to_dict()})
        self.lab.select_mapping("mouse")
        self.assertEqual(self.lab.state()["message"]["format"],"mouse_preview_v0")
        self.assertEqual(self.lab.processor.config.interpolation_ms,50)
        self.lab.select_mapping(GAMING_ID)
        self.assertEqual(self.lab.processor.config.interpolation_ms,25)
        self.assertFalse(self.lab.processor.armed)
        self.assertTrue(all(v==0 for v in self.lab.commands[-2]["command"]["buttons"].values()))

    def test_registry_copy_rename_and_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"mapping.json"
            self.lab.copy_mapping("Gaming test two")
            self.assertEqual(self.lab.mapping_id,"gaming-test-two")
            self.lab.export_mapping(path)
            expected = self.lab.state()["mapping"]
            self.lab.select_mapping(GAMING_ID)
            self.lab.import_mapping(path)
            self.assertEqual(self.lab.state()["mapping"],expected)
            self.assertFalse(self.lab.processor.armed)
            broken = deepcopy(expected);broken["head_x"]["release"] = 1
            with self.assertRaises(ValueError):self.lab.update_mapping(broken)
            self.assertEqual(self.lab.state()["mapping"],expected)

    def test_bounded_journal_reports_gap_and_copies_entries(self):
        for i in range(530):self.feed(left="wink" if i%2 else "open")
        state = self.lab.state(after_command=0)
        self.assertEqual(len(state["commands"]),512)
        self.assertTrue(state["command_gap"])
        state["commands"][-1]["command"]["keys"]["w"] = 9
        self.assertEqual(self.lab.commands[-1]["command"]["keys"]["w"],0)

    def test_stop_loss_and_close_have_released_commands(self):
        for action in ("stop","loss","close"):
            self.lab.action({"action":"arm"}); self.feed(); self.feed(left="wink")
            if action=="stop":self.lab.action({"action":"stop"})
            elif action=="loss":self.lab.disconnect("Source lost")
            else:self.lab.close()
            result = self.lab.state()["message"]
            self.assertFalse(result["enabled"])
            self.assertFalse(any(result["buttons"].values()))
            self.assertFalse(any(result["keys"].values()))


class MappingValidation(unittest.TestCase):
    def test_bad_values_rejected_and_old_mouse_profile_untouched(self):
        baseline = Mapping().to_dict()
        for field,value in (("pointer_gain",float("nan")),("pointer_gain",True),("revision",True),("id","mouse")):
            data = deepcopy(baseline);data[field] = value
            with self.assertRaises(ValueError):Mapping.from_dict(data)
        data = deepcopy(baseline);data["head_y"]["mystery"] = 1
        with self.assertRaises(ValueError):Mapping.from_dict(data)
        data = deepcopy(baseline);data["bindings"]["left"] = "alt"
        with self.assertRaises(ValueError):Mapping.from_dict(data)
        self.assertEqual(Mapping.from_dict(baseline).to_dict(),baseline)

    def test_private_atomic_file_and_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"map.json"
            write_mapping(path,Mapping())
            self.assertEqual(read_mapping(path),Mapping())
            self.assertEqual(path.stat().st_mode & 0o077,0)
            path.write_text(" "*65537)
            with self.assertRaises(ValueError):read_mapping(path)
            path.write_text(json.dumps({"format":"input_mapping_v1"}))
            with self.assertRaises(ValueError):read_mapping(path)


if __name__ == "__main__":
    unittest.main()
