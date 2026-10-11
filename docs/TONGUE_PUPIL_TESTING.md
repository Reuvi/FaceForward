# Test the new tongue and pupil joysticks

> Current MVP: tongue has been removed from App and Vision lab. Use
> [App's current testing/profile guide](../App/README.md) and
> [pupil matrix testing](../docs/DIRECT_PUPIL_TESTING.md). Eyes and head axes remain;
> pupils are the pointer input, with no pupil calibration or sensitivity controls.
> Detector presets are v11; old tongue state is discarded on load. Any tongue
> setup, backend, recheck or mapping instructions below are historical.

**Current tongue workflow:** use [lip-boundary testing](LIP_BOUNDARY_HEAD_TESTING.md).
It supersedes the default neural backend described below. ONNX remains an explicit
comparison option; direct pupils remain current. New detector saves use v9.

The new [horizontal head guide](HEAD_HORIZONTAL_TESTING.md) is tab **3 Head X**;
Tongue is now **4 Tongue**, Pupils **5 Pupils**. New detector saves use v8 with direct pupil settings and independent yaw. Combined profiles remain v3.

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

1. Open **Detection calibration → 4 Tongue**. Camera mode now uses local tongue
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

## Pupils: direct MediaPipe direction

Pupils now work without a calibration guide or saved head pose. Open **5 Pupils**,
inspect the raw/normalized readings and the square 11×11 matrix. No sensitivity
controls or calibration are needed. See [direct pupil testing](DIRECT_PUPIL_TESTING.md) for steps, math and limits.
This supersedes the earlier full-screen pupil range guide.

## Use either input in the mouse preview

On **Vision source & raw signals**, choose **Pointer joystick input → Tongue tip**
or **Pupil direction**. Changing it stops preview. Tongue requires its position guide; pupils are direct.
Then press **Start preview** and open **Live lab**. This uses the existing mouse
velocity/dead-zone/smoothing settings. Center means no commanded motion; increasing
distance means more commanded motion. Left/right eye click inputs and head scroll
keep their existing mappings. No actual OS cursor injection is added here.

Save with **Save active profile**. Detector v8 stores tongue model identity/range,
independent head fits, eye/wink fits and direct pupil sensitivities. Old v1–v7
files remain validated/readable; compatible other fits survive and old pupil
fits are discarded. Only tongue requires fresh range checks after load/restart.
Profiles retain the selected pointer source. Brief face loss preserves fits,
stops output, and never auto-arms.

Every capture has its original timestamp and fresh measurements. Unknown numeric
pupil/tongue observations remain null/invalid; plots hold the last height in darker
colors only for display. CSV exports include per-eye raw pupils, combined raw
pupils, direct normalized gaze, tongue mask score/timing and validity. Eye-input numeric
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

Tongue inference now runs in a separate process with one CPU inference thread.
It no longer limits the camera/eye/head/pupil cadence. Read
[independent detector sampling](INDEPENDENT_DETECTOR_TESTING.md) for the timing
displays, capture-time expiry, calibration delivery grace, current measured rates
and a reproducible slow-model test. The earlier four-thread synchronous timing
is historical, not the current runtime architecture.
