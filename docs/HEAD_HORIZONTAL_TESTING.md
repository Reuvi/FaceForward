# Test horizontal head detection

Current profile/UI update: [direct pupil testing](DIRECT_PUPIL_TESTING.md) uses detector v8 and the scope label **Normalized positions**. Head calibration is unchanged.

Restart the native app from the repository root:

```bash
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

1. On **Vision source & raw signals**, make sure one face is visible. The shared
   raw graphs now include **Raw head yaw · degrees**, alongside vertical pitch.
   Slowly turn your head toward your own left and right. This raw measurement
   works before calibration; normalized `head_x` stays unavailable until fitted.
2. Open **Detection calibration → 3 Head X**. Click **Start head yaw guide**.
   The guide automatically runs neutral, left and right captures, then repeats
   those positions with fresh samples to check the fit. Follow the preparation
   countdown, hold the pose during capture tones, and relax during rest tones.
   Rest screens include the countdown and next instruction.
3. For **neutral**, face the camera in your comfortable resting position.
   For **left/right**, turn your nose toward your own corresponding shoulder
   only as far as comfortable while keeping your face visible. Avoid sideways
   tilt. Directions refer to your body, regardless of the unmirrored preview.
4. After the guide passes, check the green horizontal indicator:
   your learned left limit = **0**, neutral = **0.5**, right limit = **1**.
   The two halves use their own learned ranges, so unequal mobility is supported.
   Amber shows raw yaw in degrees. Learned references are printed beside it.
5. Select **Normalized positions** for the normalized Head X scope, or
   **Raw detector signals** for raw yaw/pitch and the other inputs. Camera setup
   and calibration read the same captured samples.
6. Nod vertically while holding horizontal neutral, then turn left/right while
   keeping vertical neutral. Check both axes. Head Y still uses the existing
   pitch calibration; Head X is a separate fit.
7. Use **Save active profile** in the main app to retain both fits. Restart or
   load the file to check that they return. Older compatible profiles retain
   their existing fits and require the new horizontal guide once.

To redo horizontal calibration, press **Start head yaw guide** again. To clear it,
press **Reset Head X only**. Both preserve completed vertical/eye/pupil/tongue fits.
Cancelling, leaving the Head X tab or losing the face discards unfinished
horizontal training. A completed fit survives ordinary face loss and same-source
restart. Calibration commands stop the mouse preview; they never auto-arm it.

The default guide uses 1 second of preparation, 1.8 seconds of capture per pose,
and 1.5 seconds of rest between poses. Each capture requires at least 12 usable
distinct samples and at least 80% usable observations. Fresh checks require at
least 90% within the configured normalized tolerance (default .2).
Comfortable left/neutral/right angles must be separated by at least
`head_yaw_separation` (default 3 degrees per side). These are experimental
settings, not a claim of real-person accuracy. Editing detector settings clears
calibration under the existing Settings behavior.

## Measurements and implementation

Horizontal detection reuses the current MediaPipe face transformation:

```text
yaw_degrees = degrees(atan2(R[0][2], R[2][2]))
```

This measures the face's forward direction in the camera's horizontal plane.
It is rotation, not the face's position in the image. Calibration determines which
raw direction means your left/right. No additional model or inference pass is
added, and tongue inference remains in its independent process.

For raw yaw u, with learned left L, neutral C and right R, the appropriate half
of the range maps linearly:

```text
left half:   x = 0.5 * (u - L) / (C - L)
right half:  x = 0.5 + 0.5 * (u - C) / (R - C)
```

This works for either raw sign. Existing endpoint tolerance permits small
overshoot (default .05 normalized), clamped to 0 or 1. Larger excursions,
uncalibrated yaw, failed face-image quality, missing transformations,
degenerate forward direction and unsupported rear-facing poses remain invalid.
Unknown graph segments hold the last plotted height in a darker color; that
display hold never replaces unavailable detector measurements.

The fast SignalFrame now supplies calibrated `head_x` in its existing slot on
every processed capture. CSV adds `head_x_raw` (degrees), `head_x_quality`,
`head_x_reason`, `head_x_raw_units`, and normalized `head_x` with its validity
and confidence. All use the frame's original sequence/timestamp.

New detector presets are **v7**, algorithm `independent-head-axes-v7`.
`head` still stores vertical pitch; nullable `head_x` stores horizontal yaw.
Versions 1–6 remain readable and are fully validated before changing state.
Combined files remain `face_mouse_profile_v3`; loading can occur without a face.
Invalid preset data does not partially overwrite the active calibration.

The current mouse still uses Head Y for vertical scrolling. Head X is now ready
for a later transfer-function/device mapping; it does not silently add horizontal
scrolling or change pointer control.

See [the contract](../Contracts/HEAD_HORIZONTAL.md) and
[independent model scheduling](INDEPENDENT_DETECTOR_TESTING.md).

## Developer checks

```bash
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_head_yaw.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_horizontal_head.py -v
```

The generated-input tests check combined yaw/pitch/roll math, face-quality and
missing-pose rejection, asymmetric/reversed ranges, rest/sample boundaries,
separate axis resets, shared traces/CSV, v1–v6 migration, v7 round trips and
atomic rejection, and the native guide/indicator. Actual webcam stability,
comfortable usable range and partial-face visibility still need your live test.

Implementation verification: 127 Vision tests (including local model smoke
checks), 94 integration tests with native Tk enabled, and 75 Processing tests
passed. The 490-frame headless mouse demo accepted every frame, observed all four
mouse actions, and ended disabled with buttons released.
