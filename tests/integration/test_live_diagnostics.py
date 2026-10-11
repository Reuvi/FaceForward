import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from App.diagnostics import DiagnosticLog, pointer_status
from App.mouse_runtime import MouseSession
from Processing.mappings.config import GAMING_ID
from Processing.mappings.demo import gaming_demo_frame
from Vision.mouse_demo import mouse_demo_records


class LiveDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.
        self.session = MouseSession(clock=lambda:self.now)
        self.addCleanup(self.session.close)
        self.lab = self.session.lab
        self.lab.select_mapping(GAMING_ID)
        self.seq = 0

    def feed(self, x=.5, confidence=1):
        self.now += 20
        self.seq += 1
        base = next(mouse_demo_records(count=1))
        base.update(sequence=self.seq,timestamp_ms=self.now)
        frame = gaming_demo_frame(base,30)
        for key,value in (("gaze_x",x),("gaze_y",.5 if x is not None else None)):
            frame["faces"][0]["signals"][key].update(value=value,valid=value is not None,
                                                     confidence=confidence if value is not None else 0)
        self.assertTrue(self.session.deliver(frame)["accepted"])
        return self.session.state(),self.lab.state()

    def test_invalid_pupils_explain_detector_reason_not_filters(self):
        source,lab = self.feed(None)
        source["detector"] = {"reasons":{"pupil":"Head angle outside pupil calibration"}}
        self.assertIn("Head angle outside",pointer_status(source,lab))
        self.assertNotIn("dead zone",pointer_status(source,lab))

    def test_head_mouse_status_and_logs_name_head_input_instead_of_pupils(self):
        self.lab.select_mapping("mouse-test")
        source,lab=self.feed(None)
        self.assertIn("Head X/Y input available",pointer_status(source,lab))
        source['frame']['faces'][0]['signals']['head_x'].update(value=None,valid=False,confidence=0)
        lab['snapshot']['diagnostics']['raw_pointer']=None
        source['detector']={'reasons':{'head_x':'Run guided horizontal head calibration'}}
        self.assertIn('Head X: Run guided horizontal',pointer_status(source,lab))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'head.jsonl'
            log=DiagnosticLog(path);log.record(source,lab);log.close()
            row=json.loads(path.read_text().splitlines()[1])
            self.assertEqual(row['mapping_id'],'mouse-test')
            self.assertEqual(row['pointer_input'],'head')
            self.assertIsNone(row['processed_pupils'])
            self.assertIn('head_x',row['head_reasons'])
            self.assertTrue(row['head_wink_clicks'])
            self.assertTrue(row['require_wink'])
            self.assertFalse(row['head_center_pending'])
            self.assertIn('ready',row['eyes']['left'])
            self.assertIn('phase',row['head_motion'])
            self.assertEqual(row['head_motion']['multiplier'],1)

    def test_confidence_gate_and_staleness_have_distinct_messages(self):
        source,lab = self.feed(confidence=.2)
        self.assertIn("confidence 0.20 is below 0.50",pointer_status(source,lab))
        self.now += 300
        self.lab.step(self.now)
        self.assertIn("fresh",pointer_status(self.session.state(),self.lab.state()))

    def test_stopped_center_wait_deadzone_and_filter_delay(self):
        mapping = self.lab.state()['mapping'];mapping['pointer_mode'] = 'velocity'
        self.lab.update_mapping(mapping)
        self.assertIn("Press Start",pointer_status(*self.feed()))
        self.lab.action({"action":"arm"})
        self.assertIn("center pupils",pointer_status(*self.feed(.8)))
        self.assertIn("dead zone",pointer_status(*self.feed()))
        self.assertIn("filtering",pointer_status(*self.feed(.8)))
        for _ in range(6):
            state = self.feed(.8)
        self.assertIn("Relative pointer request",pointer_status(*state))

    def test_head_start_blocker_points_to_recenter_and_distinguishes_missing_face(self):
        self.lab.select_mapping('mouse-test')
        source,lab=self.feed()
        lab['snapshot'].update(armed=True,enabled=False)
        lab['snapshot']['diagnostics']['pointer_radius']=.6
        text=pointer_status(source,lab)
        self.assertIn('0.600',text);self.assertIn('0.030',text)
        self.assertIn('Center head & start',text)
        self.lab.action({'action':'center_head_start'})
        text=pointer_status(self.session.state(),self.lab.state())
        self.assertIn('fresh center capture',text)
        lab['snapshot']['diagnostics']['raw_pointer']=None
        source['frame']['faces']=[]
        text=pointer_status(source,lab)
        self.assertIn('face to return',text)
        self.assertNotIn('calibrat',text)

    def test_driver_error_is_retained_and_log_has_no_images_or_profiles(self):
        source,lab = self.feed()
        source["preview"] = b"private-camera-image"
        source["profile_label"] = "private-profile.json"
        lab["output"]["error"] = "Driver needs a fresh neutral command before output"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"control.jsonl"
            log = DiagnosticLog(path)
            log.record(source,lab)
            log.close()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows[1]["driver_error"],lab["output"]["error"])
            self.assertIn("neutral command",rows[1]["pointer_status"])
            self.assertEqual([r["event"] for r in rows],["session_start","sample","session_end"])
            self.assertNotIn("private-",path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_screen_destination_status_has_no_center_velocity_gate(self):
        self.lab.action({'action':'arm'})
        source,lab=self.feed(.8)
        message=pointer_status(source,lab)
        self.assertIn('screen destination',message)
        self.assertIn('100.0%',message)
        self.assertNotIn('dead zone',message)
        lab['output'].update(mode='dry-run',target_reached=True,pointer_position=[.8,.5])
        self.assertIn('arrived',pointer_status(source,lab))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'target.jsonl'
            log=DiagnosticLog(path);log.record(source,lab);log.close()
            row=json.loads(path.read_text().splitlines()[1])
            self.assertEqual(row['pointer_mode'],'target')
            self.assertEqual(row['driver_position'],[.8,.5])
            self.assertTrue(row['target_reached'])
            self.assertEqual(row['pointer_filter']['smoothing_ms'],20)
            self.assertEqual(row['pointer_interpolation_ms'],0)
            self.assertEqual(row['pointer_down_gain'],4)
            self.assertEqual(row['target_jitter'],.002)

    def test_logs_rotate_and_logging_failure_is_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"control.jsonl"
            log = DiagnosticLog(path)
            log.handler.maxBytes = 160
            for _ in range(12):
                log.record_error("synthetic error "*5)
            self.assertLessEqual(len(list(Path(directory).iterdir())),3)
            with patch.object(log.handler,"shouldRollover",side_effect=OSError("disk full")):
                log.record_error("still stopped")
            self.assertIn("disk full",log.error)
            log.record_error("logging disabled")
            log.close()

    def test_dictation_logs_codes_but_never_transcript_or_provider_message(self):
        source,lab=self.feed()
        lab['snapshot']['dictation']=dict(state='error',error_code='speech_permission',
            listening=False,remaining=0,sent=0,text='private-words',message='private-error')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dictation.jsonl'
            log=DiagnosticLog(path);log.record(source,lab);log.close()
            row=json.loads(path.read_text().splitlines()[1])
            self.assertEqual(row['dictation']['error_code'],'speech_permission')
            self.assertFalse(row['dictation']['listening'])
            self.assertNotIn('private-',path.read_text())

    def test_gesture_counts_and_wink_status_logged_without_face_features(self):
        source,lab=self.feed()
        lab['snapshot']['diagnostics']['eye_gesture']={
            'status':'Left eye closed — waiting for calibrated wink',
            'counts':{'left_action_frames':1,'clicks':1}}
        source['detector']={'wink_readings':{'left':dict(calibrated=True,known=True,
            state='wink',score=.9,features=['private-face-features'])}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'wink.jsonl'
            log=DiagnosticLog(path);log.record(source,lab);log.close()
            row=json.loads(path.read_text().splitlines()[1])
            self.assertEqual(row['eye_gesture']['counts']['left_action_frames'],1)
            self.assertEqual(row['wink_detection']['left'],dict(calibrated=True,known=True,state='wink',score=.9))
            self.assertNotIn('private-face-features',path.read_text())


if __name__ == "__main__":
    unittest.main()
