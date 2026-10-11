# Fixed pupil direction and square matrix

> Latest pupil behavior: [personal endpoints and head-angle compensation](PUPIL_HEAD_CALIBRATION_GUIDE.md).
> Run the pupil guide; fixed/no-calibration instructions below are historical.
> Detector presets now save v12. Tongue remains retired.

Current pupil update: no calibration, no sensitivity controls, and an **11×11
square matrix**. Downward response is stronger; left/right/up retain their prior
default mapping. This supersedes adjustable pupil settings from detector v8/v9.
Restart the native app from the repository root:

```sh
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

## Live test

1. Start the camera with both eyes visible, then open
   **Detection calibration → 4 Pupils**. There is no pupil setup or training step.
   Other eyes/winks/head calibrations are independent and can be loaded.
2. Look left, center, right, up and down while keeping your head comfortable and
   fairly still. The cyan square marks the matrix cell; the small white dot is the
   precise position. Matrix center is **row 5, column 5**. Top/left is index 0;
   bottom/right is index 10. Left/right mean your own body, not the camera image.
3. Pay particular attention to down. Positive vertical movement now reaches 1
   with .065 eye widths of iris displacement rather than .1. You should need less
   downward travel; up is unchanged. The raw graph remains in the original units.
   No min/max learning, automatic centering or user sensitivity setting is involved.
4. Inspect the per-eye readings below the matrix (scroll if needed): lid gap,
   blink score, down-look score and the validity reason. A narrower eye opening
   can remain usable when both its iris and MediaPipe down-look signal agree.
   Unsupported narrowing, poor image quality and actual closure remain unavailable.
5. Blink/wink and briefly leave the frame. Unknown graphs and the matrix display
   hold the previous position in a darker color with **UNKNOWN display hold**.
   The actual matrix becomes null/invalid, and unknown input cannot move the mouse.
   Reopening/returning resumes fresh samples without retraining or auto-arming.
6. Compare **Vision source & raw signals** with this tab: the source page shows
   the same matrix row/column and capture data. Use **Raw detector signals** for
   raw per-eye traces and **Normalized positions** for Pupil X/Y. Export CSV to
   inspect the raw signals, quality/reasons and matrix indices while testing down.
7. To test the existing simulated mouse, open **Live lab** and press **Start
   preview** with neutral inputs. Pupils are already the pointer input; there is
   no source selector. Processing receives precise X/Y, with mouse response
   settings separate from detection. No new OS driver is added.

Eye-corner center maps to (.5,.5), which need not match natural resting gaze.
Head movement can affect this eye-relative direction; it is not calibrated screen
look position. The new down-look thresholds and scale are fixed experimental
choices. Generated tests verify the logic, not accuracy on every person's eyes.
If down still fails, compare **barely moves** (raw Y small), **unavailable** (read
per-eye reason), and **wrong direction** (check raw Y sign); these are distinct.

## Measurement and downward checks

Reuse the same MediaPipe inference and four iris-ring landmarks per eye. Project
their center relative to the eye-corner midpoint onto horizontal/down axes, then
divide by eye width. Average both usable eyes. No additional model or inference.

```text
x = clip(.5 + raw_x / .4, 0, 1)
y = clip(.5 + raw_y / .2, 0, 1)    when raw_y <= 0
    clip(.5 + raw_y / .13, 0, 1)   when raw_y > 0
```

Left/right endpoints are ±.2 eye widths, up −.1 and down +.065. There are no
configurable multipliers, rolling extrema, learned endpoints, smoothing or
changing eyelid-gap denominators in this detector. Device response remains in
Processing.

The normal open-eye gate is lid gap / eye width ≥.16. A narrow down-looking eye
may pass at ≥.10 only if raw iris Y>.015, MediaPipe eyeLookDown≥.2 and
(eyeLookDown−eyeLookUp)≥.1. The exception requires valid blink/up/down scores.
The existing eyeBlink<.4, image quality, iris radius .025–.25 eye widths, supported
iris position and two-eye disagreement ≤.18 eye widths still apply. No wink/eye
calibration fit can gate or change this pupil detector; click classification is
unchanged. The down-look score supports validity, not replacement coordinates.

## Matrix data for other agents

Every calibrated workbench capture emits an additive `pupil_matrix`, including
captures with missing/closed eyes or no face. Valid samples have an 11×11 array
of integer zeros with exactly one 1, in `values[row][column]`:

```python
sample = frame["pupil_matrix"]
if sample["valid"]:
    matrix = sample["values"]
    row, column = sample["row"], sample["column"]
    assert matrix[row][column] == 1
```

`column=floor(gaze_x*10+.5)`, `row=floor(gaze_y*10+.5)`. Quantization error is at
most .05 per axis. An 11×11 odd-sized grid has an exact center cell. The format is
`pupil_matrix_v1`; size, subject, confidence and original session/sequence/time
are included. Invalid samples have null values/row/column, confidence 0 and
valid=false. A displayed dark hold never enters this payload.

Existing `gaze_x/y` stay continuous in SignalFrame v1; Processing continues using
them. Its existing one-hot matrix parser can read the new `values` explicitly in
a future adapter. This change does not silently quantize the current mouse driver
input or change device transfer functions. CSV stores size, row, column and
validity plus raw/continuous fields, rather than duplicating 121 cells per row.
`gaze_measurement` is now `mediapipe_iris_direction_v3`.

New detector presets are **v11**, `eyes-head-pupils-v11`, with pupil metadata
`{"measurement":"mediapipe_iris_direction_v3"}` only. Old v1–v10 files validate
fully before their pupil fits/sensitivities and retired tongue data are discarded.
Compatible eye/wink/head fits survive. Combined profiles remain v3, and pupil-only
profiles can save without fitted detectors. See [the current App guide](../App/README.md)
and [retirement contract](../Contracts/TONGUE_RETIREMENT.md).

## Developer checks

```sh
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_joystick_detectors.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_pupil_joystick.py -v
```

Tests cover fixed directional scales, supported narrowed eyes versus closures,
missing/malformed expression support, all 121 grid cells, capture identity,
unknown/stop/load/stale matrices, continuous mouse input, profile migration and
native square/dark-hold drawing without sensitivity controls. The remaining camera measurements keep their per-capture sampling.

Earlier pupil-only validation is recorded in [coordination history](COORDINATION.md).
