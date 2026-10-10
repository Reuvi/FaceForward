"""Optional real-model inference test; never acquires a physical camera."""

import os
import unittest

from Vision.capture import CapturedImage
from Vision.landmarks import MediaPipeDetector
from Vision.pipeline import VisionPipeline
from Vision.signals import Envelope


@unittest.skipUnless(os.environ.get("VISION_MODEL_PATH"), "set VISION_MODEL_PATH to test the local model")
class ModelSmokeTests(unittest.TestCase):
    def test_blank_inference_and_native_restart_preserve_envelopes(self):
        import numpy as np
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        pipeline = VisionPipeline()
        with MediaPipeDetector(os.environ["VISION_MODEL_PATH"], include_pose=True, include_expressions=True) as detector:
            self.assertEqual(detector.options.num_faces, 1)
            for envelope in (Envelope("one", 0, 1000.2), Envelope("one", 3, 1027.8),
                             Envelope("two", 0, 2000.5)):
                captured = CapturedImage(envelope, image)
                observations = detector.detect(captured)
                self.assertEqual(pipeline.process(captured, observations), envelope.frame([]))


if __name__ == "__main__":
    unittest.main()
