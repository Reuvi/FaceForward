# Direct MediaPipe pupil direction

> Pupil mapping update: [PUPIL_HEAD_CALIBRATION.md](PUPIL_HEAD_CALIBRATION.md)
> supersedes fixed/no-calibration pupil behavior. Tongue stays retired, matrix
> shape stays 11×11, and detector presets now save v12.

User-requested replacement for the calibrated pupil section of
JOYSTICK_DETECTION.md. Active camera/detector-demo pupils require no capture guide,
learned range, eye calibration, saved head pose or recheck. Reuse the current
MediaPipe iris landmarks and eye-corner coordinate frames on every fast capture.
No additional model, camera, inference or temporal fitting is added.

Keep raw iris offsets in eye-width units: X positive toward the user's right,
Y positive down, zero at the eye-corner midpoint. Average the two usable eyes.
Normalize with explicit fixed scale, not learned endpoints:

```
x = clip(0.5 + raw_x * x_sensitivity / 0.4, 0, 1)
y = clip(0.5 + raw_y * y_sensitivity / 0.2, 0, 1)
```

Default sensitivity is 1 on each axis; allowed 0.25–4. At default scale, raw
X ±0.2 and Y ±0.1 eye widths reach the endpoints. These are engineering defaults,
not universal anatomical limits or screen-gaze calibration. No rolling min/max,
automatic recentering, or division by changing eyelid opening. Head movement
can still change observed iris direction; this mode does not compensate it.

Require both eyes' image quality, usable iris geometry and the existing fixed
open-eye checks (lid ratio >= .16 and MediaPipe blink score < .4). Learned wink/
eye fits cannot gate pupils. Reject missing/closed/distorted/disagreeing eyes;
unknown control samples remain invalid, while graphs dark-hold previous values.
Emit every capture's existing gaze_x/y fields with gaze_measurement
`mediapipe_iris_direction_v2`. Show raw per-eye/combined data and direct normalized
output from the same trace in the native lab. No pupil training/reset-fit controls.
Sensitivity edits stop preview, clear old normalized pupil evidence and preserve
all other detector fits; fresh frames resume direct measurements, never auto-arm.

Detector presets v8, algorithm `direct-mediapipe-pupils-v8`, replace the pupil
fit/pose field with `{measurement, x_sensitivity, y_sensitivity}`. Allow saving a
direct-pupil profile without any fitted detector. Fully validate v1–v7, then ignore
legacy pupil fits/pose and default direct sensitivity. Preserve compatible other
fits. New saves never retain legacy pupil models. Combined profiles remain v3.
Processing's explicit pointer_source='gaze' and all transfer functions are unchanged.
