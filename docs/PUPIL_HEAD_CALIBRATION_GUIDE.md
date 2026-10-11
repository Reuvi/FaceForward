# Pupil calibration with head-angle compensation

> Current behavior: [raw pupil control](../Contracts/RAW_PUPIL_CONTROL.md) supersedes pupil fitting/head compensation below. No pupil guide is required or exposed; old fits are retained as inactive data.

This replaces fixed pupil normalization. It defines **your** comfortable left,
right, up and down limits and learns how head turns change your iris readings.
The result is a directional joystick for the mouse, not absolute screen gaze.
No sensitivity slider, new camera, neural model or browser is involved.
Tongue remains removed; eye/wink and Head X/Y calibrations remain independent.

## Open and calibrate

Restart the app from the repository root:

```sh
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

Select **Detection calibration → 4 Pupils → Start / restart pupil guide**.
Use your normal screen, camera position and comfortable seating distance. A
native full-screen overlay appears and closes on success, failure or Escape.
The first screen and every rest screen explain the next movement. Listen for the
ready tone, then the capture tone. Hold steady during capture; rest between poses.
The 14-step guide takes about a minute at default timings (1 s preparation,
1.8 s capture, 1.5 s rest). It uses current shared movement timings in Settings.

1. **Center:** face the screen naturally and look at the center dot.
2. **Head left/right/up/down:** keep your EYES ON THE CENTER DOT while turning
   or nodding your HEAD about 10–15° in each prompted direction. Both eyes should
   remain visible. Avoid rolling your head sideways. These four samples learn
   pupil drift caused by head angle; they do not redefine your joystick limits.
3. **Eye left/right/up/down:** return your HEAD TO ITS ORIGINAL CENTER, then move
   ONLY YOUR EYES toward each dot. Use comfortable, repeatable limits; you do not
   have to strain to reach the dot. These samples define 0 and 1 on each axis.
4. **Fresh checks:** look at center while turning slightly right and down (about
   half the earlier turns), then repeat the four eye directions with your head
   centered. These samples only validate the fit; they do not train it.

The down direction gets its own measured range. A smaller reliable down movement
can reach 1.0 without increasing the up or horizontal responses.

## What to inspect

On **Vision source & raw signals**, raw iris X/Y and raw head angles remain visible
even before pupil calibration. The calibration tab reads the SAME captured
samples, not a separate camera or UI sampling loop.

On **4 Pupils** after success:

- The details show raw iris X/Y, yaw/pitch/roll, compensated iris X/Y, normalized
  X/Y, learned low/center/high values and trained head-angle ranges.
- The scope compares **Raw X/Y** with **Corrected X/Y** in eye-width units.
  Select **Normalized positions** to see the final 0–1 outputs with head axes.
- The position diagram shows compensated pupil coordinates and the learned limits.
- The **11×11 matrix** marks the discrete cell. The white dot is the continuous
  output used by Processing, which is not quantized to the cell.

Expected checks:

| Action | Expected reading |
| --- | --- |
| Look center, head neutral | X≈.5, Y≈.5; row 5, column 5 |
| Your chosen left / right | X≈0 / 1; leftmost / rightmost column |
| Your chosen up / down | Y≈0 / 1; top / bottom row |
| Move halfway toward a chosen limit | Approximately .25 or .75 on that axis |
| Look center; gently turn/nod within trained range | Corrected position stays near center while raw position can change |
| Close/cover an eye; lose face or head pose | Current sample invalid; dark display holds previous point |
| Return to visible, supported position | Fresh valid samples resume; preview does not auto-arm |

Try combined moderate yaw/pitch, then test eye directions with a modest head turn.
The built-in check validates one held-out diagonal pose; it does not prove accuracy
at every head/eye combination. If corrected values drift strongly, repeat the
calibration and export the CSV for comparison. Keep this phase detector-only;
mouse smoothing/dead zones are separate downstream controls.

**Export trace CSV** preserves original capture timestamp/sequence, raw per-eye
measurements, averaged `pupil_raw_x/y`, `pupil_pose_yaw/pitch/roll`,
`pupil_compensated_x/y`, continuous `gaze_x/y`, validity/reason and matrix cell.
No plot-held values enter the detector or controls. Unknown frame samples continue
at the capture cadence, with null/invalid pupil output.

## Retry, reset and save

**Retry failed step** repeats only that pose and preserves accepted earlier
captures. A failure involving poor head coverage or inconsistent center gaze may
require **Start / restart pupil guide** to repeat the earlier head poses.
**Escape** cancels unfinished work. **Reset pupils only** clears the pupil fit;
none of these actions clears eye/wink or Head X/Y fits. While replacing an existing
pupil fit, the old fit stays available until the new guide passes. Device preview
is disarmed during calibration. Leaving the tab, losing the face or stopping the
source cancels unfinished work and retains completed fits.

Use **Save active profile** on the source tab. Detector preset **v12** stores
pupil reference pose, regression coefficients, directional endpoints, trained
angle bounds and check results. Combined profiles remain v3. Loading disarms
preview and requires a new camera frame before any valid output. No face images
or training sequences are saved. Brief face loss and same-source restarts retain
completed fits. Switching camera/demo source kind or Reset all clears them.

Older detector v1–v11 files are fully validated, then migrated. Compatible
independent eyes/winks/head fits survive, but pupils require the new guide.
A legacy fixed mapping or old pupil range cannot supply head compensation.

## Engineering details

`Vision/pupil.py` still measures MediaPipe iris landmarks relative to each eye's
corners, in eye-width units. Existing visibility, eye-closure and supported-down
checks remain. Both usable eyes contribute to one raw X/Y measurement.
Raw measurement identity is `mediapipe_iris_direction_v3`.

For five center-gaze/head poses, `pupil_calibration.fit_pose` fits an affine model
using an equal-weight median per pose. For each output axis:

```text
raw_iris = center + yaw_slope × (yaw − reference_yaw)
                  + pitch_slope × (pitch − reference_pitch)
corrected_iris = raw_iris − learned_head_drift

value <= center: normalized = .5 + .5 × (value − center) / (center − low)
value >  center: normalized = .5 + .5 × (value − center) / (high − center)
```

X and Y each learn yaw AND pitch coefficients, allowing cross-axis effects.
Normalization uses corrected units and clamps valid endpoint overshoot to [0,1].
It does not subtract angles directly from coordinates. Existing NumPy performs
small fits only at guide step completion; inference is constant-size arithmetic
per frame, with no additional neural inference or worker. The existing camera
worker, Processing timer and Tk drawing cadences remain separate.

MediaPipe's [face transformation matrix](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)
provides canonical-to-detected face transforms, not screen-gaze coordinates.
Yaw/pitch/roll are derived from the existing same-frame rotation. The fitted model
compensates yaw/pitch. Eye-corner-relative geometry handles image-plane rotation;
roll beyond 12° from the reference is rejected, not learned. Camera distance,
translation, extreme rotations and nonlinear eye/head interactions are not modeled.
Recalibrate after moving the camera or materially changing seating position.

Current experimental acceptance rules (not universal physiological thresholds):

- At least `min_samples` clear frames per window (default 12) and 80% usable.
- Capture 10th–90th percentile spread ≤.045 eye widths and ≤6° per pose axis.
- Head coverage on both sides of reference: ≥4° yaw, ≥3° pitch; no >10° roll
  change across training medians; regression condition number ≤40.
- Head fit residual ≤.02 eye widths; coefficient magnitude ≤.03 eye widths/degree.
- Eye training head yaw/pitch within 5° of reference; each endpoint at least .015
  eye widths from center and in the correct direction.
- Fresh check: ≥90% of captured frames within `position_check_tolerance`
  (default .2 normalized units) on both axes. Diagonal check must move both head
  axes at least 2°. It can reveal a poor fit but is not a clinical accuracy measure.
- Runtime accepts trained yaw/pitch ranges plus a 3° margin. Beyond that, or when
  iris/pose is unavailable, output is invalid; no uncontrolled extrapolation.

`PupilGuide` shares the head guide's prompt acknowledgment, rest and capture-window
machinery. Preparation/rest frames and duplicate/out-of-order timestamps cannot
train it. The workbench swaps in a validated fit only after all fresh checks pass.
Saved models are structurally/numerically validated before any live state changes.
`gaze_measurement` becomes `head_compensated_iris_direction_v1`; SignalFrame v1 and
`pupil_matrix_v1` retain their shapes and original capture envelopes.

## Software tests

```sh
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_pupil_calibration.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p 'test_pupil*.py' -v
Vision/.venv/bin/python -m App --source detector-demo
```

Detector demo uses generated pixels with explicit head-dependent pupil drift and
follows the guide automatically. Tests cover asymmetric down limits, held-out head
poses, every matrix cell, unknown inputs, prompt/rest timing, retry/cancel/reset,
independent channel preservation, profile migration, validation and native UI.
These are software checks; camera accuracy still requires the live tests above.
