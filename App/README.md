# One native lab: detection calibration + mouse processing

Run **one `App` window** for the complete testing workflow. The original Processing
lab now contains **Detection calibration** as another tab. One camera/inference
worker supplies the calibrated measurements to both the detector view and the
existing input/output scopes and simulated desktop. Switching tabs keeps the source,
selected face, calibration, and Processing state.

The standalone detector was initially isolated because the team wanted to test
measurement before connecting Processing. That connection is now implemented.
`Vision.lab` and `Processing.mouse` remain optional component development tools;
you do not launch them alongside App. They reuse the same detector view/runtime
and Processing controller. There is no browser, JavaScript, HTTP server, remote
inference, or real OS mouse injection. The emulator connection remains pending.

## Launch and choose a source

From the repository root, with Python 3.10+ and Tk. For pixel/camera modes, install
[Vision's optional dependencies and local model](../Vision/README.md#install-the-optional-camera-dependencies).
The prepared `Vision/.venv` and model are machine-local and ignored by Git.

```bash
# Interactive calibration using generated pixels + landmarks. No camera or ML.
Vision/.venv/bin/python -m App --source detector-demo

# The same app using your local camera and MediaPipe model.
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30

# Original automatic 16-second mouse exercise. No optional packages required.
python3 -m App
```

| Source in the app | Purpose | Calibration/profile behavior |
| --- | --- | --- |
| Detector demo (synthetic pixels) | Manually test detection and Processing together | Select `subject-0`; calibrate using fake eye/tongue switches and sliders; saves synthetic profiles |
| Camera (live calibration) | Test your actual facial measurements | Select your face; calibrate or load a camera profile; validate on your current image |
| Vision demo (synthetic) | Automatic four-action Processing regression | Supplies prebuilt valid SignalFrames; no detector training or face profile |
| Vision replay (NDJSON) | Inspect recorded synthetic SignalFrame sequences | Select a subject; preserves input timing; no images or calibration collection |

Stop the current source before starting another. Only one app should own a physical
camera. Other agents can run synthetic sources in their separate worktrees.
The requested FPS takes effect on source start; actual Hz and capture age are shown.

## Calibrate, then use the original lab

1. On **Vision source & raw signals**, select your visible ID and press
   **Use selected subject**. A dropdown choice alone is not selection. A tracker ID
   is session-local, not biometric identity. Selection resets/disarms Processing.
2. Open **Detection calibration**. In **1 Eyes**, capture OPEN and CLOSED for the
   anatomical left eye, then independently for the right. Default capture gives
   one second to pose, then collects 1.8 seconds. Wait for the status result.
3. In **2 Head Y**, capture NEUTRAL, UP, DOWN. Default measurement is vertical
   position of the nose bridge divided by image height. For nodding, choose
   `head_mode: "pitch"` in detector Settings **before** selecting/calibrating; it
   uses degrees from the facial transform. Applying detector settings clears fits.
4. In **3 Tongue**, capture an EMPTY open mouth, freeze a visible tongue, mark
   tongue-only tissue, and fit the appearance model. Run **Validate ABSENT** with
   tongue hidden and **Validate VISIBLE** with it visible, using new frames. Both
   must pass before tongue X/Y becomes valid. Inspect the mask for false candidates.
5. On **Vision source & raw signals**, inspect valid values; or stay in calibration
   to examine the raw ratios, thresholds, masks and detector scopes. You may test
   one fitted channel while others remain unavailable.
6. Open **Live lab**, return your head/tongue to neutral and open both eyes, then
   press **Start preview**. Existing scopes show input, intermediate processing,
   and output. Mouse movement, scroll and click counters occur inside the lab.
7. Use **Transfer settings** for click dwell, dead zones, smoothing, sensitivity,
   acceleration and preview speed. Apply changes and start preview again. Use
   **Save active profile** in the source tab to save the applied settings and fits.

The preview is unmirrored: your left eye appears on the image's right. Both eye
classifiers and both Processing timers stay independent. Holding both can activate
both; short closures are filtered separately by each dwell threshold.

| Channel | Detector measurement | Processing result |
| --- | --- | --- |
| Left/right eye | Separate dimensionless lid-gap/width ratios → binary `*_eye_open` (`1=open`, `0=closed`) | Independent button states after dwell/release debounce |
| Head Y | Image-height fraction or pitch degrees → calibrated `[0,1]`: up 0, neutral .5, down 1 | Smoothed scroll velocity; .5 means stopped |
| Tongue X/Y | Color candidate centroid in the mouth frame; X toward anatomical right, Y down | Relative pointer velocity; .5 means stopped per output axis |

Gaze and head X remain unavailable in this calibrated path. Tongue absence is
unavailable input, never an invented center. The raw-mock adapter's eye bits use
`1=closed`; App's SignalFrame path has the opposite, explicitly named polarity.
All geometry, quality gates, thresholds, settings and limitations are documented
in [the detector runbook](../Vision/DETECTION_LAB.md). Transfer functions are in
[Processing's guide](../Processing/README.md) and [the engineering guide](../docs/ENGINEERING_GUIDE.md).

### Camera-free calibration exercise

In `detector-demo`, select `subject-0`. Leave Left closed unchecked for its OPEN
capture, check it for CLOSED, then uncheck. Repeat for the right eye. For head
captures, place the Head slider at about .5, .2, .8 for neutral/up/down respectively;
these are generator controls, not measured image fractions. Leave Tongue visible
unchecked for EMPTY. Check it, freeze, **Mark center patch**, fit; uncheck for
ABSENT validation, check for VISIBLE. Keep tongue sliders near .5 initially.

Start preview with neutral/open input. Hold Left closed beyond the default 320 ms;
then test Right closed and both. Move head and tongue sliders to see scrolling and
pointer velocity in Live lab. The synthetic source bypasses neural inference;
it proves wiring and deterministic behavior, not accuracy on real faces.

## Saved face + mouse profiles

**Save active profile** writes a versioned local JSON file, by default under ignored
`local-profiles/`. At least one fitted detector and a fresh selected face are
required. A left-eye-only profile is valid; it does not calibrate the other eye.

| Saved section | Contents |
| --- | --- |
| `format`, `source_kind` | `face_mouse_profile_v1`; camera or synthetic |
| `detector` | Version/algorithm, detector settings, independent eye fits, head mode and three-point fit, optional tongue color prototypes/radius/margin |
| `processing` | Applied mouse mapping, dwell, thresholds, smoothing, response and acceleration settings |
| `preview` | Simulated pointer and scroll speed |

It does **not** save pictures, raw training pixels, sample traces, tracking IDs,
selection, validation pass flags, armed state, or driver permission. Local files
are written atomically with private file permissions. They are not committed.
Saving does not activate anything; it records the current applied configuration.

To reuse: start the matching source → **Use selected subject** → **Load profile
for face**. App validates the whole profile before applying it, attaches it to that
currently selected face, restores Processing settings, and leaves preview stopped.
Camera and synthetic profiles cannot be mixed. Check eye/head readings again;
repeat tongue ABSENT and VISIBLE checks under current lighting. If those fail,
recollect tongue training. Loaded color prototypes do not retain training samples.

Stop, stale input, track loss, restart, selecting a face again, or detector settings
changes clear the active calibration binding. The saved file remains. Select again
and explicitly reload/recalibrate; a bystander never inherits it automatically.
The source tab shows the file name and whether it is attached to the current face.
After further edits, save again to preserve current values. Detector Settings
**Save JSON** saves only detector tunables; Transfer settings export saves only
Processing settings. Neither is a substitute for **Save active profile**.

## Stop and runtime boundaries

**Stop / Escape** immediately disables preview but keeps measurement running.
**Stop source** also stops capture and clears active calibration. Calibration
captures/changes and profile loading disarm preview. Tab changes do neither.
Close the window to shut down the source and Processing workers.

```text
One App worker: camera → MediaPipe OR synthetic image generator
    ↓ image + landmarks + original capture timestamp
Vision.LabRuntime.ingest → DetectorWorkbench: measurements/calibration
    ├─ latest image + raw features + trace → Detection calibration tab
    └─ calibrated SignalFrame v1 → App → Lab.ingest
                                         ↓ independent 100 Hz Processing clock
                                     existing Live lab / scopes / simulated mouse
```

The embedded runtime never starts its own worker or camera. The Tk thread reads
bounded snapshots; inference stays off Tk. Preview is capped near 10 Hz; Processing
keeps its own clock and stale-input watchdog. Locks are acquired session → lab.
There is no growing frame queue or JSON serialization in the sample handoff.
The standalone `Vision.lab` starts that runtime's worker only when run by itself.

- `App/mouse_runtime.py`: source ownership, detector commands, selection, profile
  binding, direct measurement handoff and stop/error/EOF behavior.
- `Vision/lab.py`, `lab_runtime.py`, `workbench.py`: reused UI, image runtime and
  detector algorithms. `Vision/presets.py` validates/serializes fitted parameters.
- `Processing/mouse/profiles.py`: bounded JSON reads and atomic file writes, with
  Processing settings validation. App calls Vision for detector validation.
- `Processing/mouse/controller.py`: input acceptance, independent output clock,
  immediate disconnect and bounded trace history.
- `Processing/mouse/output.py`: provisional `mouse_preview_v0` serialization.

A blocked native camera read cannot be forcibly interrupted. Stop disables output
immediately; close waits up to two seconds. Starting a second producer while the
first is still alive is rejected. `--no-preview` skips camera overlay encoding;
scalar diagnostics remain. Images stay in memory and are not recorded.

## Checks and remaining work

```bash
Vision/.venv/bin/python -m unittest discover -s tests/vision -v
Vision/.venv/bin/python -m unittest discover -s tests/processing -v
Vision/.venv/bin/python -m unittest discover -s tests/integration -v
python3 -m unittest discover -s tests/tooling -v
python3 -m App --headless --frames 490
```

New integration tests send generated pixels through real detector calibration and
Processing and verify all four outputs, independent eyes, disarming during capture,
profile round trips, fresh tongue checks, bad-profile rejection, stale/lost subjects,
and single-worker restart. CI runs these with optional image dependencies as well
as the dependency-free core suite. Real-model blank-image smoke does not establish
live gesture accuracy. Real-person testing, lighting/distance repeatability and
tongue false-positive measurement are still required.

The original automatic demo and replay still work; see [the testing companion](../docs/TESTING_GUIDE.md)
for their timeline and assertions. `--config` loads Processing tunables only;
combined profile loading is deliberately through the selected-face UI. The emulator
message format, units, transport and OS output remain the next Drivers handoff.
See [the adopted contract](../Contracts/MOUSE_MVP.md) and
[main chat coordination](../docs/COORDINATION.md) before changing those boundaries.
