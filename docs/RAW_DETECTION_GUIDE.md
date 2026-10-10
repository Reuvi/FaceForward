# Raw detection status and where to test it

Updated October 10, 2026: use the **new detector-only Vision lab** for live
calibration. The original combined `python -m App` camera path still exposes its
uncalibrated baseline. Synthetic mouse behavior in App is not live detector evidence.

```bash
Vision/.venv/bin/python -m Vision.lab --camera \
  --model Vision/.local/face_landmarker.task
```

For a camera-free walkthrough, replace the camera arguments with `--demo`.
For a window that starts with the camera off, omit both source flags.
Read [the full detector runbook](../Vision/DETECTION_LAB.md) for installation,
buttons to press, all measurements/units, every setting, testing, and implementation.

| Required mouse input | Implemented in the detector lab | Evidence still needed |
| --- | --- | --- |
| Independent left eye | Live open/closed collection, robust personalized threshold, separate binary output, raw ratio and image gates | Real-person blink/wink accuracy, glasses/occlusion and threshold chatter |
| Independent right eye | Separate collection/classification and validity; no both-eye veto | Same tests for this anatomical eye independently |
| Head vertical | Calibrated up/neutral/down; default nose-bridge vertical image fraction, optional camera-frame pitch degrees | Neutral drift, comfortable repeatable range, pose and distance sensitivity |
| Tongue X/Y | Marked positive tissue + empty-mouth negatives, color segmentation, visible mask and actual candidate centroid; separate absent/visible checks gate valid output | Real-person precision/recall, false positives on gums/lips, lighting sensitivity and usable movement range |

The new workbench is **not connected to Processing or Drivers**. It displays v1
normalized detector values locally; the later integration task will connect these
once the team has evaluated them. Gaze and horizontal head output remain invalid
in this lab. The older iris/gaze mathematical helpers still exist; an iris position
proxy is not a calibrated screen gaze estimator.

## What ML and image processing run?

The local MediaPipe Face Landmarker bundle provides face detection and landmark
estimation. The adapter converts image BGR to RGB, runs synchronous CPU VIDEO
inference for at most two faces, preserves capture timestamps, and assigns
conservative session-local geometric IDs. The new lab additionally requests facial
transformation matrices for optional head pitch. It does not request blendshape
scores, fine-tune a neural network, or train a new deep eye/tongue network.
See the [official task guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

Eye classification uses each eye's geometric lid-gap/width ratio and separately
captured open/closed targets. Head normalization fits three robust target medians.
The tongue prototype trains small color-prototype sets on marked tongue pixels and
other open-mouth pixels, then applies geometry, distance, morphology, area and
ambiguity gates. It is actual pixel segmentation, but has no semantic understanding
that guarantees a matching region is tongue. Inspect its mask while testing.

```text
Local camera → face landmarks (+ optional transform) → explicit subject selection
   ├─ each eye: lid ratio → independent open/closed calibration → binary measurement
   ├─ head Y: image position or pitch → up/neutral/down fit → normalized position
   └─ tongue: mouth crop → calibrated pixel segmentation → candidate centroid
                              → new absent/visible exercises → normalized X/Y
All channels → native measurements / time scopes / local scalar CSV
No connection to mouse processing in this increment
```

Image gates check size, bounds, brightness, clipping, focus and plausible geometry.
Their quality scores are heuristic support, not calibrated probabilities. They do
not establish reliable occlusion recognition. Failed gates produce unavailable
measurements; they never fabricate a neutral tongue/head position. Selection and
calibration clear on stop, stale input, track loss, restart, or settings changes.

## First real session

1. Stop other camera consumers. Open the Vision lab, start Camera and select your ID.
2. In **1 Eyes**, collect open and closed for each eye; test all four combinations.
   Closed bits use 1=closed; named `*_eye_open` values use 1=open.
3. In **2 Head Y**, capture neutral/up/down. Default means vertical face movement.
   For nodding, select `head_mode: pitch` in Settings before calibration.
4. In **3 Tongue**, capture an empty open mouth, freeze and mark tongue-only tissue,
   fit, then validate absent and visible on new frames. Inspect the green mask.
5. Export a local trace. Record misses, false candidates and invalid frames instead
   of judging only whether numbers move. Follow the repeated-trial checklist in
   [the detector runbook](../Vision/DETECTION_LAB.md#tests-and-remaining-live-evidence).

The automated tests cover generated image evidence and lifecycle. Real-model smoke
loads the local model on blank frames; it does not measure live face accuracy.
The full real-person evaluation remains the team's next testing step.
