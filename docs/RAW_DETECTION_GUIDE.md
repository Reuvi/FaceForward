# Raw facial detection: status, ML pipeline, and native testing

Code audit: October 10, 2026, baseline `5d87e2c`. The local Vision branch
`work/codex/vision/measurement-plan` at `9f51fb7` is already included in main and
had no uncommitted changes during this audit. This guide concerns **detection
before mouse mapping**. The synthetic mouse demo does not establish live detection.

## 1. Which of the four mouse inputs exist?

| Required input | Implemented now | Missing before usable live output | Current camera output |
| --- | --- | --- | --- |
| Left eye open/closed → left click | Left eyelid/iris landmarks, raw openness ratio, per-eye calibration fitting and binary classifier, tests | Live open/closed sample collection, validated per-eye quality assessment, and binding that calibration to the selected face | Raw ratio visible; `left_eye_open` remains invalid |
| Right eye open/closed → right click | Separate right-eye landmarks, ratio, calibration and classifier; independent of left click logic | Same live collection/quality/binding work, separately for this eye | Raw ratio visible; `right_eye_open` remains invalid |
| Head up/down → scroll | Face landmarks and a 2D reference drawn on the face | A defined/calibrated head-Y measurement, quality checks, and emission into `head_y` | `head_y` invalid; there is no live scroll detector |
| Tongue X/Y → pointer | Mouth-relative coordinate math accepting an externally supplied tongue centroid | Actual tongue detection/segmentation, presence/occlusion checks, calibration and live wiring | `tongue_x/y` invalid; no tongue centroid is detected |

**Two of the four have live raw measurement foundations; zero of the four are
currently enabled as calibrated live control signals in the shipped camera path.**
The two eyes are the closest to completion. Head and tongue movement in the demo
are synthetic values from [mouse_demo.py](../Vision/mouse_demo.py).

The original plan also includes pupil/gaze tracking. **Raw iris X/Y ratios exist**
for each eye, plus calibration and gaze-combination functions. Live calibration
and quality binding are missing there too. There is no implemented screen-point
gaze estimator. The current code uses iris landmarks as a position proxy, not a
separate pupil-center detector. MediaPipe's iris documentation also distinguishes
iris tracking from determining where a person is looking.
[MediaPipe Iris reference](https://chuoling.github.io/mediapipe/solutions/iris.html).

## 2. What ML is actually running?

The local model is MediaPipe **Face Landmarker**, loaded from
`Vision/.local/face_landmarker.task`. Google's bundle contains face detection,
face-mesh landmark estimation, and an optional expression/blendshape stage. Its
mesh output has 478 landmarks; optional outputs include 52 blendshape scores and
facial transformation matrices.
[Official model overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).

Our implementation consumes `face_landmarks` only. It does **not** request the
optional blendshape or transformation-matrix outputs. It converts landmark X/Y
to pixels and currently discards model Z for the measurement calculations.
There is no custom neural network training, fine-tuning, tongue model, or separate
learned blink classifier in this repository. Calibration fits numerical thresholds
and ranges; it does not retrain the neural model.

```text
Camera image
  → OpenCV capture + capture timestamp
  → BGR-to-RGB conversion
  → pretrained MediaPipe face/landmark inference (local CPU)
  → anatomical eye landmarks + iris positions + face reference
  → geometric ratios, tracker ID, overlay
      ├─ raw diagnostics → native numbers and scopes (working)
      └─ per-person calibration + observation quality + explicit binding
           → valid eye/gaze SignalFrame measurements (live wiring missing)

Head measurement: not yet produced from landmarks
Tongue centroid: not yet detected
```

The adapter uses synchronous `VIDEO` mode and `num_faces=2`; App runs this on its
Vision worker, outside Tk's drawing thread. Only one inference is in flight. The
Python API's video call waits for a result; timestamps are required.
[Official Python runtime guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

Google documents built-in landmark smoothing only when `num_faces=1`. Our
two-face configuration should therefore not be described as receiving that
smoothing. Processing's later velocity filter is a different stage.
[Face Landmarker configuration](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker#configurations_options).

Current verified local environment:

| Item | Value |
| --- | --- |
| Python | 3.12.5 in the prepared local environment |
| `mediapipe` | 0.10.35 |
| `opencv-contrib-python` | 4.13.0.92 |
| Model SHA-256 | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` |
| Capture request | 640×480, configurable FPS; actual rate must be measured |
| Runtime | Native/local; no remote inference, browser, JavaScript, or runtime model download |

These dependencies/model are ignored local files, not included in a clone.
Teammates use [Vision's setup instructions](../Vision/README.md#install-the-optional-camera-dependencies).

## 3. How each measurement is calculated

### Independent eyes and iris movement

[landmarks.py](../Vision/landmarks.py) selects separate anatomical left/right
corner, eyelid, and iris groups. It averages four iris-rim points per eye to
estimate that eye's iris center. Pixel coordinates preserve image aspect ratio.

[geometry.py](../Vision/geometry.py) builds a local eye frame: the line between
eye corners gives the horizontal axis and eye width `w`; a perpendicular gives
down; the corner midpoint is the origin. For iris offset `d`:

| Diagnostic | Calculation | Interpretation |
| --- | --- | --- |
| Openness | Median of three upper/lower eyelid distances divided by `w` | Dimensionless lid gap; usually smaller when closed; not an open probability |
| Iris X | `0.5 + dot(d, right) / w` | Relative horizontal iris position |
| Iris Y | `dot(d, down) / w` | Relative vertical iris position; can be negative; not normalized screen Y |

Degenerate/off-image geometry and an eye narrower than four pixels are rejected.
These basic geometry checks are **not** a validated confidence model for blur,
occlusion, lighting, glasses, or reliable open/closed classification.

[calibration.py](../Vision/calibration.py) can fit separate open and closed sample
sets. Each target needs at least five finite values. Median/MAD outlier filtering
must retain at least five and 80% of the group. Open and closed groups must be
separated by an explicitly chosen minimum; overlapping groups are rejected.
The threshold lies between the retained closed/open groups, then classification
emits `0=closed`, `1=open`. This is the **SignalFrame `*_eye_open` convention**.
Processing's independent mock bit format instead uses `1=closed`.

`EyeBinding` in [pipeline.py](../Vision/pipeline.py) attaches left/right calibration
and a quality-assessor callback to one explicit session and subject. Missing or
unusable quality must not be replaced with a fabricated score of 1. The current
camera constructors never install a binding, so the functions tested with
synthetic calibration do not automatically classify a real face.

Eye classification answers “open or closed.” The later Processing dwell timer
answers “has this closure lasted long enough to request a click?” Keep those
separate. Both eyes can close independently or simultaneously; there is no
both-eyes click suppression.

### Head movement

The available `head_reference` is an origin and two directions in the **2D image
plane**, based on eyes/nose/mouth. The overlay follows this geometry. No pitch/yaw
estimator or normalized displacement signal is implemented, and the reference
is not converted into `head_x/y`.

Before implementing head Y, make its meaning explicit: the original brief allows
a tracked point's relative vertical position; the Vision plan discusses pose.
Vertical translation relative to neutral and pitch angle are different inputs.
Choose and document one, collect a neutral/comfortable range, validate orientation
and quality, then emit continuous `head_y` from 0 (up) through 0.5 to 1 (down).
The existing one-hot head vector is a Processing test representation, not a
detector already producing these values.

### Tongue movement

`tongue_ratios()` accepts mouth corners, lip boundaries, and a **real tongue
centroid supplied by another detector**. It divides horizontal displacement by
mouth width and vertical displacement by mouth-opening height. Degenerate mouths
and points outside the mouth domain are rejected.

That coordinate helper is implemented and tested; the detector that finds the
tongue is absent. No training dataset, trained tongue weights, segmentation
implementation, or live centroid producer is present. A mouth-opening landmark
cannot stand in for a tongue. The next implementation needs a chosen detection
method and visible/absent/occluded behavior before its X/Y can be judged usable.

## 4. Native testing environment: inspect detection only

Run from the repository root. On Reuvi's prepared checkout:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

If the combined window is already open with its prepared environment, use it:

1. Press **Stop / Esc** to leave mouse preview disabled.
2. Open **Vision source & raw signals** and press **Stop source**.
3. Select **Camera diagnostics (uncalibrated)**. Use **Choose model** if necessary
   to select the local `face_landmarker.task`, then **Start source**.
4. Choose the detected subject and press **Use selected subject**. A dropdown
   option alone is not a selection. Do not press Start preview for this exercise.
5. Read the raw eye ratios, preview landmarks, and three raw-ratio scopes. These
   remain available while mouse preview is stopped.

Only one process should own the camera. The model and camera libraries must be
available in the Python environment that launched the existing window. If it
reports a missing dependency, close that window and launch with the command above.

| Panel | What you should see today |
| --- | --- |
| Camera/source preview | Mirrored face landmarks, subject labels, raw eye openness labels, image reference axes |
| Raw camera ratios / selected subject | Independent left/right `open`, `X`, `Y` geometry, and face span |
| Openness scope | Left blue, right amber; vertical display range 0–0.5 |
| Iris X scope | Left blue, right amber; display range 0–1 |
| Iris Y scope | Left blue, right amber; display range −0.3–0.3 |
| Vision measurement table | All eight normalized control measurements unavailable in the current unbound camera path |
| Source status | Requested versus actual timing context, received/accepted counts, age, and errors |

Those plotting ranges are display choices, not validated physiological limits.
Out-of-plot-range ratios remain visible numerically. Camera scopes sample the
latest observation at up to 10 Hz and are not a lossless camera-rate recording.
The Processing **Live lab** scopes are a different view; they cannot show valid
camera controls until detection calibration/wiring exists.

**Calibrate current neutral** changes Processing's center offsets. It does not
collect open/closed samples or enable Vision classification. Synthetic/replay
sources also cannot supply a real raw camera image or landmark ratios.

### Vision-only alternative

This opens the existing OpenCV diagnostic window without importing Processing:

```bash
Vision/.venv/bin/python -m Vision camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 \
  --width 640 --height 480 --fps 30 --preview
```

Press `q` in that window or Ctrl-C to stop. Add `--frames 100` for a bounded run.
It shows landmarks, subject labels, and raw openness on the image, but not the
three scope panels. Stdout contains SignalFrame NDJSON, whose normalized signals
are currently invalid; it is **not a raw-ratio CSV exporter**. Timing/error
summaries go to stderr. Preview mirroring changes display only.

## 5. Detection experiments before connecting a mouse

These are manual observation protocols, not automated tests already implemented.
Use comfortable movements and record conditions so results can be compared.

| Experiment | Inspect now | What it will establish |
| --- | --- | --- |
| Neutral face, eyes open for about 10 seconds | Raw ratio ranges, jitter, missing geometry, actual FPS | Baseline noise and usable visibility |
| Close/reopen left several times, then right | Each anatomical openness trace separately | Whether open/closed distributions appear separable; correct eye labeling |
| Close both, then reopen one | Separate raw traces | Whether one eye can remain observable without inventing the other eye's state |
| Look left/right/up/down with head approximately still | Iris X/Y traces per eye | Direction/sign and available dynamic range; not screen gaze accuracy |
| Small head changes, normal distance/lighting variations, glasses if normally used | Ratios and tracker IDs | Sensitivity to conditions and landmark dropout |
| Leave view and return; optionally a second person | Missing selected subject, new IDs, raw gaps | No silent selection/calibration transfer |
| Move head up/down | Overlay follows geometry, `head_y` remains invalid | Confirms the missing head measurement; this is not a passed head-detector test |
| Move tongue | `tongue_x/y` remain invalid | Confirms no tongue detector is running |

After implementing calibration, measure false open/closed transitions during
neutral periods, missed intentional closures, transition latency, and invalid
sample fraction for **each eye separately**. For head/tongue, additionally measure
neutral jitter, sign, monotonic response, range, and invalidation on loss. Set
acceptance thresholds from observed data; none have been established as reliable
for live use yet.

The current CSV export contains Processing trace fields, not the camera ratio
history or images. A full-rate raw-ratio export/evaluation tool remains work to
add if quantitative camera analysis needs it. Do not interpret sampled scope
screens as a complete dataset. Keep any personal data under ignored
`data/private/` or `local-profiles/`; the app does not record camera video.

## 6. Existing verification and the next implementation boundary

The last run on this baseline passed **45 Vision tests**, including the optional
local-model blank-image/restart test, and **9 integration tests**. Those establish
geometry/calibration logic, tracking and lifecycle behavior, and diagnostic
delivery. The model smoke uses blank images; it does not measure facial accuracy.
Earlier camera preview/smoke checks established acquisition and visible geometry,
not calibrated gesture reliability. See [test evidence](TESTING_GUIDE.md#7-replay-automated-checks-and-known-evidence).

To repeat detector tests without opening a camera:

```bash
VISION_MODEL_PATH=Vision/.local/face_landmarker.task \
  Vision/.venv/bin/python -m unittest discover -s tests/vision -v
```

The next bounded task should finish **live, independent eye detection**: select a
subject, collect open/closed samples per eye, assess quality, fit/bind calibration,
show the resulting bits alongside the raw traces, and invalidate on loss/restart.
Keep mouse preview stopped while validating this. Then add a defined head-Y
measurement and the actual tongue detector as separate Vision tasks.

This is a proposed sequence, not a claim those features were added by this audit.
The Vision agent owns detection/calibration code; App integration owns the
collection/selection wiring and shared interfaces. Use the
[coordination handoff](COORDINATION.md#handoff-to-this-chat) to agree that boundary.
