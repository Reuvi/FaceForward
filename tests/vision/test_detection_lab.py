"""Deterministic pixel and lifecycle evidence; not a live-human accuracy study."""

from dataclasses import replace
import importlib.util
import math
import tempfile
import time
from types import SimpleNamespace
import unittest
from pathlib import Path

AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))
if AVAILABLE:
    import cv2
    import numpy as np
    from Vision.capture import CapturedImage
    from Vision.demo_detection import demo_image
    from Vision.features import DetectionConfig, analyze_features, image_quality, pitch_degrees, rotation_from_matrix
    from Vision.lab_runtime import LabRuntime
    from Vision.landmarks import MediaPipeDetector
    from Vision.signals import Envelope, validate_frame
    from Vision.tongue import TongueModel, mouth_crop, sample_colors
    from Vision.workbench import DetectorWorkbench


@unittest.skipUnless(AVAILABLE, "Install Vision/requirements.txt for pixel/calibration lab tests")
class PixelTests(unittest.TestCase):
    def setUp(self):
        self.config = DetectionConfig()

    def crop(self, **kwargs):
        bgr, observations = demo_image(**kwargs)
        return mouth_crop(bgr, observations[0], self.config)[0]

    def model(self):
        return TongueModel.fit(sample_colors(self.crop(tongue=True), xy=(.5, .5)), sample_colors(self.crop()))

    def test_eyes_independent_and_no_iris_required(self):
        bgr, observations = demo_image(left_closed=True)
        observations[0].points = observations[0].points[:468]
        values = analyze_features(bgr, observations[0], self.config)
        self.assertLess(values["left"].value, .05)
        self.assertGreater(values["right"].value, .2)
        self.assertGreater(values["left"].quality, 0)
        # The opposite eye can be unavailable without suppressing this eye.
        points = list(observations[0].points)
        points[33] = points[133]
        observations[0].points = tuple(points)
        values = analyze_features(bgr, observations[0], self.config)
        self.assertGreater(values["left"].quality, 0)
        self.assertEqual(values["right"].quality, 0)

    def test_image_gates_reject_dark_blur_clipping_and_border(self):
        for pixels in (np.zeros((40,40,3),np.uint8), np.full((40,40,3),100,np.uint8), np.full((40,40,3),255,np.uint8)):
            self.assertEqual(image_quality(pixels,(0,0,40,40),self.config).quality,0)
        bgr, obs = demo_image()
        self.assertEqual(image_quality(bgr,(-1,0,50,50),self.config).quality,0)
        dark=analyze_features(np.zeros_like(bgr),obs[0],self.config)
        self.assertEqual(dark["left"].quality,0)
        self.assertIsNotNone(dark["left"].value)  # Raw evidence is still inspectable.

    def test_pose_units_and_translation_scale_invariance(self):
        angle=math.radians(17)
        matrix=np.eye(4)
        matrix[:3,:3]=((1,0,0),(0,math.cos(angle),-math.sin(angle)),(0,math.sin(angle),math.cos(angle)))
        self.assertAlmostEqual(pitch_degrees(rotation_from_matrix(matrix)),17)
        matrix[:3,3]=(50,-20,100);matrix[:3,:3]*=2
        self.assertAlmostEqual(pitch_degrees(rotation_from_matrix(matrix)),17)
        matrix[0,0]*=3
        self.assertIsNone(rotation_from_matrix(matrix))
        self.assertIsNone(rotation_from_matrix(np.zeros((4,4))))
        self.assertIsNone(rotation_from_matrix(np.full((4,4),np.nan)))
        mirror=np.eye(4);mirror[0,0]=-1
        self.assertIsNone(rotation_from_matrix(mirror))

    def test_pose_adapter_attaches_only_matching_transforms(self):
        bgr,obs=demo_image(head=.75)
        landmarks=[SimpleNamespace(x=x/640,y=y/480) for x,y in obs[0].points]
        matrix=np.eye(4);matrix[:3,:3]=obs[0].rotation
        result=SimpleNamespace(face_landmarks=[landmarks],facial_transformation_matrixes=[matrix])
        detector=MediaPipeDetector(__file__,include_pose=True)
        detector.cv2=cv2
        detector.mp=SimpleNamespace(Image=lambda **kwargs:kwargs,ImageFormat=SimpleNamespace(SRGB="rgb"))
        detector.landmarker=SimpleNamespace(detect_for_video=lambda *_:result)
        detected=detector.detect(CapturedImage(Envelope("pose",0,1000),bgr))
        self.assertAlmostEqual(pitch_degrees(detected[0].rotation),10)
        result.facial_transformation_matrixes=[]
        detected=detector.detect(CapturedImage(Envelope("pose",1,1025),bgr))
        self.assertIsNone(detected[0].rotation)

    def test_tongue_presence_absence_and_anatomical_coordinates(self):
        model=self.model()
        self.assertIsNone(model.detect(self.crop(),self.config).xy)
        for x,y in ((.35,.5),(.65,.5),(.5,.65)):
            result=model.detect(self.crop(tongue=True,tongue_x=x,tongue_y=y),self.config)
            self.assertIsNotNone(result.xy)
            self.assertAlmostEqual(result.xy[0],x,delta=.025)
            self.assertAlmostEqual(result.xy[1],y,delta=.025)
        shifted=self.crop(tongue=True,head=.8)
        result=model.detect(shifted,self.config)
        self.assertAlmostEqual(result.xy[0],.5,delta=.02)
        self.assertAlmostEqual(result.xy[1],.5,delta=.02)
        center=shifted.image_point(result.xy)
        self.assertAlmostEqual(center[0],320,delta=2)
        self.assertAlmostEqual(center[1],350,delta=2)

    def test_tongue_closed_mouth_and_ambiguous_components(self):
        bgr,obs=demo_image(tongue=True)
        points=list(obs[0].points);points[14]=points[13];obs[0].points=tuple(points)
        self.assertIsNone(mouth_crop(bgr,obs[0],self.config)[0])
        crop=self.crop()
        cv2.ellipse(crop.bgr,(44,52),(10,9),0,0,360,(115,100,215),-1)
        cv2.ellipse(crop.bgr,(84,52),(10,9),0,0,360,(115,100,215),-1)
        result=self.model().detect(crop,self.config)
        self.assertIsNone(result.xy)
        self.assertIn("ambiguous",result.reason)

    def test_tongue_geometry_under_rotation_and_scale(self):
        model=self.model()
        bgr,obs=demo_image(tongue=True,tongue_x=.6,tongue_y=.55)
        transform=cv2.getRotationMatrix2D((320,240),12,.8)
        image=cv2.warpAffine(bgr,transform,(640,480))
        obs[0].points=tuple(tuple(float(v) for v in transform@np.array([x,y,1])) for x,y in obs[0].points)
        crop,reason=mouth_crop(image,obs[0],self.config)
        self.assertIsNotNone(crop,reason)
        xy=model.detect(crop,self.config).xy
        self.assertIsNotNone(xy)
        self.assertAlmostEqual(xy[0],.6,delta=.03)
        self.assertAlmostEqual(xy[1],.55,delta=.03)

    def test_color_overlap_and_invalid_patch_rejected(self):
        pixels=sample_colors(self.crop(tongue=True),xy=(.5,.5))
        with self.assertRaises(ValueError):TongueModel.fit(pixels,pixels)
        with self.assertRaises(ValueError):sample_colors(self.crop(),xy=(0,0))
        with self.assertRaises(ValueError):sample_colors(self.crop(),xy=(float('nan'),.5))

    def test_settings_validate_before_use(self):
        for key,value in (("stale_ms",float('nan')),("min_samples",True),("head_mode","unknown"),("oops",1)):
            with self.assertRaises(ValueError):DetectionConfig.from_dict({key:value})
        self.assertEqual(DetectionConfig.from_dict(self.config.to_dict()),self.config)


@unittest.skipUnless(AVAILABLE, "Install Vision/requirements.txt for detector workbench tests")
class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.sequence=0
        self.session="test-session"
        self.core=DetectorWorkbench(DetectionConfig(settle_ms=0,collect_ms=400,min_samples=8),clock=lambda:self.now)
        self.feed()
        self.core.select(self.core.frame["faces"][0]["subject_id"])

    def feed(self, *, blank=False, dark=False, **controls):
        self.now+=25
        bgr,observations=demo_image(**controls)
        if dark:bgr[:]=0
        self.sequence+=1
        frame=self.core.process(CapturedImage(Envelope(self.session,self.sequence,self.now),bgr),[] if blank else observations)
        validate_frame(frame)
        return frame["faces"][0]["signals"] if frame["faces"] else {}

    def collect(self,target,**controls):
        self.core.collect(target)
        while self.core.job is not None:
            self.feed(**controls)

    def eyes(self):
        for side in ("left","right"):
            self.collect(side+"_open")
            self.collect(side+"_closed",**{side+"_closed":True})

    def tongue(self):
        self.collect("tongue_absent")
        self.feed(tongue=True)
        self.core.freeze_mouth()
        self.core.mark_tongue(.5,.5)
        self.core.fit_tongue()

    def test_all_four_channels_and_independent_simultaneous_closures(self):
        self.eyes()
        self.collect("head_up",head=.15)
        self.collect("head_neutral",head=.5)
        self.collect("head_down",head=.85)
        self.tongue()
        signals=self.feed(tongue=True)
        self.assertFalse(signals["tongue_x"]["valid"])
        self.collect("validate_absent")
        self.collect("validate_visible",tongue=True)
        signals=self.feed(left_closed=True,right_closed=True,tongue=True,tongue_x=.65,head=.675)
        self.assertEqual(signals["left_eye_open"]["value"],0)
        self.assertEqual(signals["right_eye_open"]["value"],0)
        self.assertAlmostEqual(signals["head_y"]["value"],.75)
        self.assertAlmostEqual(signals["tongue_x"]["value"],.65,delta=.025)
        self.assertTrue(signals["tongue_y"]["valid"])
        self.assertFalse(signals["gaze_x"]["valid"])
        self.assertFalse(self.feed()["tongue_x"]["valid"])
        self.assertEqual(len(self.core.trace),self.sequence)

    def test_single_eye_does_not_require_other_calibration(self):
        self.collect("left_open");self.collect("left_closed",left_closed=True)
        signals=self.feed(left_closed=True)
        self.assertTrue(signals["left_eye_open"]["valid"])
        self.assertFalse(signals["right_eye_open"]["valid"])
        signals=self.feed(left_closed=True,right_closed=True)
        self.assertEqual(signals["left_eye_open"]["value"],0)

    def test_pitch_mode_and_outside_range(self):
        self.core.configure(dict(self.core.config.to_dict(),head_mode="pitch"))
        self.feed();self.core.select(self.core.frame["faces"][0]["subject_id"])
        for target,value in (("up",.2),("neutral",.5),("down",.8)):
            self.collect("head_"+target,head=value)
        self.assertAlmostEqual(self.feed(head=.35)["head_y"]["value"],.25)
        self.assertFalse(self.feed(head=1)["head_y"]["valid"])

    def test_tongue_validation_failure_recheck_and_model_change(self):
        self.tongue()
        self.collect("validate_absent",tongue=True)
        self.collect("validate_visible",tongue=True)
        self.assertFalse(self.feed(tongue=True)["tongue_x"]["valid"])
        self.collect("validate_absent")
        self.assertTrue(self.feed(tongue=True)["tongue_x"]["valid"])
        self.core.freeze_mouth();self.core.mark_tongue(.5,.5)
        self.assertFalse(self.feed(tongue=True)["tongue_x"]["valid"])
        self.assertEqual(self.core.validation,{})

    def test_no_face_staleness_and_new_session_clear_selection(self):
        self.eyes();self.feed(blank=True)
        self.assertIsNone(self.core.selected)
        self.assertFalse(self.core.eyes)
        self.feed();self.core.select(self.core.frame["faces"][0]["subject_id"])
        self.now+=251
        self.assertIsNone(self.core.state()["selected"])
        self.feed();self.core.select(self.core.frame["faces"][0]["subject_id"])
        self.session="new-session"
        self.feed()
        self.assertIsNone(self.core.selected)

    def test_poor_visibility_and_failed_recapture_never_reuse_old_fit(self):
        self.eyes()
        self.assertFalse(self.feed(dark=True)["left_eye_open"]["valid"])
        self.assertTrue(self.feed()["left_eye_open"]["valid"])
        self.collect("left_open",dark=True)
        self.assertNotIn("left_open",self.core.samples)
        self.collect("left_closed",left_closed=True)
        self.assertFalse(self.feed()["left_eye_open"]["valid"])
        self.assertTrue(self.feed()["right_eye_open"]["valid"])

    def test_failed_overlap_no_partial_fit_and_atomic_bad_settings(self):
        self.collect("left_open");self.collect("left_closed")
        self.assertNotIn("left",self.core.eyes)
        self.assertIn("rejected",self.core.notice)
        selected=self.core.selected
        with self.assertRaises(ValueError):self.core.configure({"head_mode":"bad"})
        self.assertEqual(self.core.selected,selected)

    def test_insufficient_usable_fraction_rejects_collection(self):
        self.core.collect("left_open")
        for i in range(16):self.feed(dark=i<4)
        self.assertNotIn("left_open",self.core.samples)
        self.assertIn("Rejected",self.core.notice)

    def test_selected_loss_does_not_transfer_to_bystander(self):
        self.eyes()
        bgr,obs=demo_image()
        first=obs[0]
        first.box=replace(first.box,x=.05,width=.35)
        bystander=replace(first,box=replace(first.box,x=.65,width=.3))
        # New session explicitly selected with two non-overlapping boxes.
        self.session="two-faces";self.now+=25;self.sequence+=1
        self.core.process(CapturedImage(Envelope(self.session,self.sequence,self.now),bgr),[first,bystander])
        subject=self.core.frame["faces"][0]["subject_id"]
        self.core.select(subject)
        self.now+=25;self.sequence+=1
        self.core.process(CapturedImage(Envelope(self.session,self.sequence,self.now),bgr),[bystander])
        self.assertIsNone(self.core.selected)
        self.assertTrue(all(not item["valid"] for item in self.core.frame["faces"][0]["signals"].values()))

    def test_recalibration_invalidates_immediately_and_blocks_mixed_tongue_jobs(self):
        self.eyes()
        self.core.collect("left_open")
        signals=self.core.state()["frame"]["faces"][0]["signals"]
        self.assertFalse(signals["left_eye_open"]["valid"])
        self.assertTrue(signals["right_eye_open"]["valid"])
        with self.assertRaises(ValueError):self.core.freeze_mouth()
        self.core.cancel()

    def test_duplicate_envelope_clears_and_raises(self):
        self.eyes()
        bgr,obs=demo_image()
        with self.assertRaises(ValueError):
            self.core.process(CapturedImage(Envelope(self.session,self.sequence,self.now),bgr),obs)
        self.assertIsNone(self.core.selected)
        self.assertFalse(self.core.eyes)


@unittest.skipUnless(AVAILABLE,"Install Vision requirements for source lifecycle tests")
class RuntimeTests(unittest.TestCase):
    def wait_for(self,predicate):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.015)
        self.fail("worker did not reach expected state")

    def test_demo_stop_restart_error_and_csv(self):
        runtime=LabRuntime()
        try:
            runtime.start(demo=True)
            self.wait_for(lambda:bool(runtime.snapshot()["frame"]))
            first=runtime.snapshot()["frame"]
            runtime.command("select",first["faces"][0]["subject_id"])
            with self.assertRaises(ValueError):runtime.start(demo=True)
            self.wait_for(lambda:len(runtime.snapshot()["trace"])>=3)
            with tempfile.TemporaryDirectory() as directory:
                file=Path(directory)/"trace.csv"
                self.assertGreater(runtime.export_trace(file),0)
                self.assertIn("timestamp_ms",file.read_text())
            runtime.stop()
            self.assertIsNone(runtime.snapshot()["selected"])
            self.wait_for(lambda:not runtime.worker.is_alive())
            runtime.start(demo=True)
            self.wait_for(lambda:runtime.snapshot()["frame"]["session_id"]!=first["session_id"])
            runtime.stop();self.wait_for(lambda:not runtime.worker.is_alive())
            runtime.start(model="missing-local-model.task")
            self.wait_for(lambda:runtime.source.startswith("Error"))
            self.assertIsNone(runtime.snapshot()["selected"])
        finally:
            runtime.close()
