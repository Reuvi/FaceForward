"""Binary mouth measurement uses existing capture evidence, without training."""
from copy import deepcopy
import importlib.util
from types import SimpleNamespace
import unittest

from Vision.mouth import mouth_open
from Vision.signals import Envelope, invalid, make_face, measurement, validate_frame


class MouthSignalTests(unittest.TestCase):
    def test_fixed_threshold_and_missing_values_preserve_source(self):
        for score, expected in ((0, 0), (.49, 0), (.5, 1), (1, 1),
                                (None, None), (True, None), (float('nan'), None), (2, None)):
            obs = SimpleNamespace(expressions={'jawOpen': score}, points=[(30, 30)]*478)
            result = mouth_open(obs, 100, 100)
            self.assertEqual(result['value'], expected)
            self.assertEqual(result['valid'], expected is not None)
            self.assertEqual(obs.expressions.keys(), {'jawOpen'})
        self.assertEqual(mouth_open(SimpleNamespace(expressions={}, points=[]), 100, 100), invalid())

    def test_off_frame_or_missing_mouth_is_unknown(self):
        obs = SimpleNamespace(expressions={'jawOpen': .8}, points=[(30, 30)]*478)
        for index in (61, 291, 13, 14):
            bad = deepcopy(obs);bad.points[index] = (-1, 30)
            self.assertEqual(mouth_open(bad, 100, 100), invalid())
        obs.points = []
        self.assertEqual(mouth_open(obs, 100, 100), invalid())

    def test_optional_signal_preserves_legacy_schema_and_validates_binary(self):
        validate_frame(Envelope('old', 1, 1000).frame([make_face('person')]))
        face = make_face('person', {'mouth_open': measurement(1, 1)})
        self.assertEqual(face['signals']['mouth_open']['value'], 1)
        with self.assertRaises(ValueError):make_face('person', {'mouth_open': measurement(.2, 1)})

    @unittest.skipUnless(all(importlib.util.find_spec(n) for n in ('cv2', 'numpy')), 'Vision pixel dependencies')
    def test_workbench_emits_without_calibration_and_keeps_capture_time(self):
        from Vision.capture import CapturedImage
        from Vision.demo_detection import demo_image
        from Vision.workbench import DetectorWorkbench
        now = 1000.
        bench = DetectorWorkbench(clock=lambda: now)
        self.addCleanup(bench.close)
        image, observations = demo_image()
        for seq, score in enumerate((.1, .9, None)):
            now += 20
            observations[0].expressions['jawOpen'] = score
            frame = bench.process(CapturedImage(Envelope('mouth-test', seq, now), image), observations)
            expected = None if score is None else int(score >= .5)
            self.assertEqual(frame['faces'][0]['signals']['mouth_open']['value'], expected)
            self.assertEqual(frame['timestamp_ms'], now)
            self.assertEqual(bench.trace[-1]['mouth_open'], expected)
            self.assertFalse(frame['faces'][0]['signals']['head_y']['valid'])
        now += 20
        frame = bench.process(CapturedImage(Envelope('mouth-test', 4, now), image), [])
        self.assertFalse(frame['faces'])
        self.assertIsNone(bench.trace[-1]['mouth_open'])
