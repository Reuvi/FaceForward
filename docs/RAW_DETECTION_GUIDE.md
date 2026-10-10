# Raw detection status and where to test it

Current head/tongue update: use the [movement calibration guide](MOVEMENT_CALIBRATION_GUIDE.md)
for guided position fitting, raw graphs on camera setup and shared capture data.
Detector presets are now v5 (combined profiles remain v3). The
[tongue-tip guide](TONGUE_TIP_TESTING.md) covers the new visible front-boundary
measurement. v1-v4 tongue appearance/ranges require retraining; compatible
eye/wink/head fits survive. Saved v5 tongue ranges require **Recheck saved tongue
range** after loading/restarting. Eye classification is unchanged.


> Current calibrated camera eye workflow: [Eye calibration/testing guide](EYE_CALIBRATION_GUIDE.md).
> It supersedes eye dwell controls and Detection research instructions below.
> The historical raw/mock/replay examples retain their original timed behavior.

Current single-user update: calibrated camera/demo attaches the sole face automatically,
keeps calibration through motion/loss and same-source restart, and supports saved-file
loading while tracking is paused. Earlier explicit-selection/loss-reset descriptions
below are historical. See [the current test procedure](SINGLE_USER_TESTING.md).

Updated October 10, 2026: use **Detection calibration inside the combined App**.
The calibrated measurements now also reach the existing Processing scopes and
simulated mouse. Keep preview stopped to focus on detection only.

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task
```

For camera-free calibration use `--source detector-demo` instead. See the
[unified workflow/profile guide](../App/README.md) and
[detector measurements/runbook](../Vision/DETECTION_LAB.md). The standalone
`Vision.lab` is an optional developer tool using the same detector components.

| Required mouse input | Implemented in the detector lab | Evidence still needed |
| --- | --- | --- |
| Independent left eye | Live open/closed collection, robust personalized threshold, separate binary output, raw ratio and image gates | Real-person blink/wink accuracy, glasses/occlusion and threshold chatter |
| Independent right eye | Separate collection/classification and validity; no both-eye veto | Same tests for this anatomical eye independently |
| Head vertical | Calibrated up/neutral/down; default nose-bridge vertical image fraction, optional camera-frame pitch degrees | Neutral drift, comfortable repeatable range, pose and distance sensitivity |
| Tongue X/Y | Marked positive tissue + empty-mouth negatives, color segmentation, visible mask and front-edge midpoint; appearance plus personal range/fresh checks gate valid output | Real-person precision/recall, false positives on gums/lips, lighting sensitivity and usable movement range |

App connects valid v1 measurements directly to Processing. The real Drivers
connection remains pending. Gaze and horizontal head output remain invalid
in this calibrated path. The older iris/gaze mathematical helpers still exist; an iris position
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
   ├─ head Y: pitch degrees → personal up/neutral/down fit → full 0–1 position
   └─ tongue: padded mouth crop → calibrated pixel segmentation → visible front-edge midpoint
                              → new absent/visible exercises → normalized X/Y
All channels → native measurements / time scopes / local scalar CSV
Same calibrated values → Processing → existing Live lab (explicit Start preview)
```

Image gates check size, bounds, brightness, clipping, focus and plausible geometry.
Their quality scores are heuristic support, not calibrated probabilities. They do
not establish reliable occlusion recognition. Failed gates produce unavailable
measurements; they never fabricate a neutral tongue/head position. Selection and
calibration clear on stop, stale input, track loss, restart, or settings changes.

## First real session

1. Stop other camera consumers. Open App in camera mode, use the selected ID,
   then open Detection calibration.
2. In **1 Eyes**, collect open and closed for each eye; test all four combinations.
   Closed bits use 1=closed; named `*_eye_open` values use 1=open.
3. In **2 Head Y**, press **Start head pitch guide** and follow neutral/up/down,
   then repeat the fresh checks. Pitch is automatic: comfortable up = 0, neutral
   = .5, down = 1. Old image-position head profiles need this guide again.
4. In **3 Tongue**, capture an empty open mouth, freeze and mark tongue-only tissue,
   fit, then validate absent and visible on new frames. Inspect the green mask.
5. Save the active profile on the source tab; reload only for an explicitly selected
   face, recheck eyes/head and repeat tongue checks. Export a local trace. Record misses, false candidates and invalid frames instead
   of judging only whether numbers move. Follow the repeated-trial checklist in
   [the detector runbook](../Vision/DETECTION_LAB.md#tests-and-remaining-live-evidence).

The automated tests cover generated image evidence and lifecycle. Real-model smoke
loads the local model on blank frames; it does not measure live face accuracy.
The full real-person evaluation remains the team's next testing step.
