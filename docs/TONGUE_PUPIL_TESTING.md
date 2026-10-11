# Test the new tongue and pupil joysticks

Restart the native app to load this update. Head pitch and its calibration are
unchanged. Load your saved profile to recover eyes/head. Old color tongue ranges
cannot be applied to the new detector; calibrate tongue positions again.

```sh
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

The local model and ONNX dependency have been installed on Reuvi's machine.
Other machines follow [model setup](../Vision/TONGUE_MODEL_NOTICE.md). Missing
weights produce an explicit tongue error and leave the other detectors working.
All video stays local and in memory; no real mouse driver is enabled.

## Tongue: inspect before calibrating

1. Open **Detection calibration → 3 Tongue**. Camera mode now uses local tongue
   segmentation. It does not ask you to capture a background, mark color patches,
   or pass pixel recall. The old workflow remains only for developer color fixtures.
2. Open your mouth and expose the tongue's front edge past the lip. **Green** is
   the predicted tongue mask; **orange** is the selected front boundary;
   **cyan** is its midpoint/tip; **purple** is the mouth attachment cue.
3. Move slowly left/right/up/down. The mask must stay on tongue tissue and the
   cyan point must follow the visible front edge. Read the rejection reason if
   there is no cyan point. Do not calibrate around a mask on lips/gums.
4. Hide your tongue, including while opening your mouth, smiling and speaking.
   The mask should disappear. A high-confidence ambiguous/rejected candidate
   still counts as present for the absence check; a model error cannot pass it.
5. Press **Start tongue position guide**. Hide tongue for the first check, then
   expose it at center and comfortable left/right/up/down limits. Each pose waits
   for **I'm in position — capture**. Keep head still and the other axis centered.
   A second pass checks the five positions. Retry repeats only a failed pose.
6. On success, the personal position plot should show center (.5,.5), left X=0,
   right X=1, up Y=0, down Y=1. Between center and a limit, expect intermediate values.

**Reset tongue** cancels its guide and clears its range/checks, retaining the loaded
neural model and all other completed calibrations. **Load local tongue segmentation
model…** can reload the supported ONNX file if installation/loading failed.
Camera preview is unmirrored: YOUR right appears toward image left. Position plots
use YOUR right as positive X. Raw tongue axes are mouth widths, centered between
the mouth corners, spanning −.8 to +.8; the personal plot is 0–1.

## Pupils: an alternative joystick

1. Open **Detection calibration → 4 Pupils**. Look straight ahead. Check both
   independent eye readings and the raw dot. Eye open/closed calibration is useful
   if your natural eye opening varies; wink-action training is not required here.
2. Press **Start pupil position guide**. A temporary full-screen dot appears.
   Keep your head comfortably still, look at the dot, and press **Space** when ready.
   Hold through PREPARE/CAPTURE. Relax during the rest countdown. The guide collects
   center/left/right/up/down and repeats them as fresh checks. Escape cancels.
3. The popup closes on completion or failure. **Retry this pose** keeps previous
   captures after a failed pose. **Reset pupil calibration** clears only pupil fits.
4. Inspect the raw and personal plots. Center is (.5,.5). Comfortable endpoints are
   0 or 1, with linear interpolation on each side of center. Raw scopes show each
   eye separately; camera setup shows the combined raw direction from the same frames.
5. Blink or wink: pupil control must become unavailable while either eye is closed.
   It must not jump to a one-eye estimate. Reopening restores current measurements.
6. Look at a fixed target and turn your head. This is **not** compensated screen-gaze
   estimation: some movement within the accepted pose range can still change the
   signal. Larger turns invalidate the calibrated output; return toward the pose
   used at calibration. Head scrolling and pupil control need this live check.

[MediaPipe’s iris documentation](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/iris.md) distinguishes iris landmarks from where a person looks.
Our feature is an iris-center proxy for pupil direction, not exact pupil center or screen gaze. We average each four-point iris ring, project onto the eye's
corner axes, and divide both axes by that eye's width. Raw center X=horizontal−.5;
Y is downward displacement from the corner midpoint. Both open eyes must pass
image/geometry gates; their directions must agree within .18 eye widths.
No independent-eye switching occurs. Without eye geometry fits, openness must be
at least .16 eye widths; with fits, the eye must classify OPEN. eyeBlink must be
below .4. Iris radius must be .025–.25 eye widths. These are experimental gates.

Pupil range fitting requires at least .015 eye-width separation on either side of
center, stable nonoverlapping groups, ≥80% usable captures, then ≥90% of fresh
check samples within .2 normalized units of the target (existing configurable
position tolerance). Output also requires head pose within yaw/pitch ±18° and
roll ±25° of the calibration pose. These gates reject unsupported observations;
they are not head-pose compensation or validated population limits.

## Use either input in the mouse preview

On **Vision source & raw signals**, choose **Pointer joystick input → Tongue tip**
or **Pupil direction**. Changing it stops preview. Calibrate the chosen detector,
then press **Start preview** and open **Live lab**. This uses the existing mouse
velocity/dead-zone/smoothing settings. Center means no commanded motion; increasing
distance means more commanded motion. Left/right eye click inputs and head scroll
keep their existing mappings. No actual OS cursor injection is added here.

Save with **Save active profile**. Detector v6 stores the segmentation model hash,
tongue/pupil fits and pupil head reference; it stores no camera images. Old v1–v5
files remain validated/readable and compatible eye/head fits survive. Restoring a
pupil or neural tongue range requires its **Recheck saved … range** before output.
Profiles retain the selected pointer source. A source restart also requires fresh
range checks. Brief face loss preserves fits, stops output, and never auto-arms.

Every capture has its original timestamp and fresh measurements. Unknown numeric
pupil/tongue observations remain null/invalid; plots hold the last height in darker
colors only for display. CSV exports include per-eye raw pupils, combined raw
pupils, calibrated gaze, tongue mask score/timing and validity. Eye-input numeric
holds retain their separate established semantics.

## What to record during the live test

- Tongue hidden: any false green masks/cyan tips, especially on lips/gums/teeth.
- Tongue visible: tip follows the front edge, availability during slow diagonals,
  stability while holding still, return to center, failures near each direction.
- Pupils: correct directions, stable center, repeatable endpoints, no motion from
  closed-eye estimates, and drift while using head pitch for scroll.
- Real source FPS, inference milliseconds, and capture age. The first neural call
  includes loading/warmup. Do not equate a high score or passing synthetic tests
  with measured accuracy on your face.

Measured on this machine: 20 warmed local neural calls on a generated mouth crop,
median 43.74 ms, p95 46.60 ms (ONNX Runtime 1.31.0, CPU, four threads). This includes
resize and mask decoding but excludes MediaPipe, camera and UI. End-to-end FPS will
be lower than its ~23 FPS inference ceiling. The model correctly ran on those
inputs; this timing exercise does not validate tongue recognition.
