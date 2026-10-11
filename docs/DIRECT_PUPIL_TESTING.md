# Direct MediaPipe pupil testing

Restart the native App from the repository root:

```bash
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

1. Start the camera and face it with both eyes visible. No pupil calibration,
   eye calibration, dot guide, saved range or head-pose reference is required.
2. Open **Detection calibration → 5 Pupils**. Look left/right/up/down. The raw dot
   shows iris displacement; the normalized dot shows the direct 0–1 output.
   Directions refer to your body: left/up lower the value, right/down raise it.
   Eye-corner center maps to (.5,.5); it need not equal your natural resting gaze.
3. Select **Raw detector signals** to see the four per-eye traces, then
   **Normalized positions** to see Pupil X/Y with the other normalized channels.
   The source tab's combined raw pupil graph uses the same captured samples.
4. If the output barely moves, increase the corresponding **sensitivity**. If it
   reaches an edge too early, decrease it. Press **Apply pupil sensitivity**.
   Defaults are 1; the range is .25–4. **Restore default sensitivity** resets only
   these two scales. Applying stops mouse preview and preserves other detector fits.
5. Blink/wink or cover an eye. Pupil output becomes unavailable while a reliable
   two-eye estimate is missing. Graphs hold the prior position in the darker color;
   unavailable observations do not drive the mouse. Reopening gives fresh samples.
6. Move out of view, return, stop/restart the source, and load an old profile.
   Pupils should resume without training. Preview never automatically re-arms.
7. To test the existing simulated mouse, choose **Pupil direction** under
   **Pointer joystick input** on the source tab, then open **Live lab**. If needed,
   use Processing's **Calibrate current neutral** with a fresh resting gaze before
   **Start preview**. That centers the mouse transfer function; it does not train
   pupil detection. Click/wink and head-scroll calibrations remain independent.

Save active profile to retain pupil sensitivities and other settings. Detector
preset v8 stores direct settings instead of pupil fits; combined profiles stay
v3. v1–v7 are validated before loading; old pupil ranges/head references are then
ignored, with direct sensitivity defaulting to 1. Other compatible fits survive.
A profile can now be saved even when only direct pupils are in use.

## Measurements

The existing local MediaPipe inference supplies four iris-ring landmarks per eye.
Their average estimates the iris center. Project displacement from the eye-corner
midpoint onto that eye's horizontal/down axes and divide by eye width. Combine
both usable eyes, then apply:

```text
x = clip(.5 + raw_x * horizontal_sensitivity / .4, 0, 1)
y = clip(.5 + raw_y * vertical_sensitivity / .2, 0, 1)
```

Default endpoints are ±.2 eye widths horizontally and ±.1 vertically. These are
fixed engineering scales, not learned anatomical limits. There is no temporal
min/max, automatic centering, smoothing or division by changing lid opening in
this detector. Existing Processing settings handle device response separately.

Both eyes must pass image quality, fixed open-eye checks (lid ratio at least .16,
MediaPipe eyeBlink below .4), iris-radius bounds .025–.25 eye widths, supported
iris position and agreement within .18 eye widths. Eye/wink fits do not gate
pupils. Missing head-pose matrices do not block otherwise usable iris geometry.
Head turns can still move the signal: this measures eye-relative direction, not
compensated screen gaze. Those limits require live user testing.

Each frame keeps its original timestamp/sequence, gaze_x/y validity/confidence,
and `gaze_measurement: mediapipe_iris_direction_v2`. CSV includes that measurement
identifier, raw per-eye/combined iris coordinates, normalized gaze, and both
sensitivity settings. No extra model, camera, download or inference pass is added;
tongue processing remains independent.

See [the contract](../Contracts/DIRECT_PUPILS.md). Synthetic tests cover scale,
polarity, clipping, invalid eyes, geometry transforms, old-profile validation,
sensitivity changes, lifecycle, shared traces and the native interface; they do
not establish real-person tracking accuracy.

Implementation verification: 301 tests passed (129 Vision, 97 integration with
native Tk, 75 Processing), plus the complete 490-frame mouse demo.
