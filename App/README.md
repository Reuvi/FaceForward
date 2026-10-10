# One native lab: detection calibration + mouse processing

Run **one `App` window** for the complete testing workflow. The original Processing
lab now contains **Detection calibration** as another tab. One camera/inference
worker supplies the calibrated measurements to both the detector view and the
existing input/output scopes and simulated desktop. Switching tabs keeps the source
and completed calibration. Leaving an active guided eye sequence cancels it, because
its instructions would no longer be visible.

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
| Detector demo (synthetic pixels) | Automatically exercise guided eye calibration | Select `subject-0`; Start eye calibration; the fixture follows the guide, then cycles independent closures; saves synthetic profiles |
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
2. Open **Detection calibration → 1 Eyes**. Press **Test sound**, then **Start eye
   calibration**. A temporary full-screen native window opens. Follow the dot with
   eyes naturally open through five positions across the screen.
   Close both gently at the descending tones, reopen at two high tones, and wait
   for three rising completion tones. Each eye is fitted independently. Watch
   separate binary scopes: **0 open, 1 closed; darker segments hold the last known
   value while the current reading is unknown**. This is display only. The popup
   closes automatically when finished; **Escape** or **Cancel calibration** exits
   early and returns to the same lab window.
   Use **Restart eye calibration** to discard bad eye samples and repeat.
   Focus on this eye test before proceeding to head/tongue.
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

Unknown detector observations and graph/CSV evidence stay invalid. The explicit
Processing eye input holds its previous numeric value with known=false on every unknown captured
frame; that flag cancels eye timers and never counts as intentional reopening.
A new source/person/profile/calibration starts each eye at 0 until a known value arrives.
A dark held trace is not a new measurement or a continued button press. Channels with no prior known
value stay blank; source/subject resets start a new history.

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

In `detector-demo`, select `subject-0`, then press **Start eye calibration** in
Detection calibration. The generated pixels and landmarks follow all seven steps
without manual switches; after completion the fixture cycles left, right and both
closures. Start preview to inspect the resulting clicks in Live lab. This exercises
wiring, not real-face accuracy. Mock checkboxes/sliders are removed from calibration; the old mock eye checkboxes
are also hidden in App’s Live lab. Standalone Processing retains its developer controls.
Developer scripts can still set `LabRuntime.demo_controls`; tests retain manual
head/tongue fixtures. For the automatic four-action mouse exercise, use `python3 -m App`.

## Saved face + mouse profiles

**Save active profile** writes a versioned local JSON file, by default under ignored
`local-profiles/`. At least one fitted detector and a fresh selected face are
required. A left-eye-only profile is valid; it does not calibrate the other eye.

| Saved section | Contents |
| --- | --- |
| `format`, `source_kind` | `face_mouse_profile_v2` (v1 readable); camera or synthetic |
| `detector` | Version/algorithm, detector settings, independent eye fits including raw closed/open uncertainty limits, head mode and three-point fit, optional tongue color prototypes/radius/margin |
| `processing` | Applied mouse mapping, dwell, thresholds, smoothing, response and acceleration settings |
| `preview` | Simulated pointer and scroll speed |

It does **not** save pictures, raw training pixels, sample traces, tracking IDs,
selection, validation pass flags, armed state, or driver permission. Local files
are written atomically with private file permissions. They are not committed.
Detector presets now use version 2; version 1 is accepted with its original single
eye threshold. Recalibrate legacy eye profiles to add open-pose coverage.
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
captures/changes and profile loading disarm preview. Leaving an active guided Eyes
sequence cancels it; completed fits survive tab changes.
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

## Detection research in this window

The **Detection research** tab shares this capture worker and selected profile. It adds temporal blink/wink recognition, feature and duration graphs, labeled trials, optional event models, alternative gestures/dwell/head control and an optional gaze-calibration experiment. **Start research preview** runs these settings; header **Start preview** returns to the original preview. Stop/Escape stops both. See [Detection research guide](../docs/DETECTION_RESEARCH_GUIDE.md) for exact controls, measurements, limits and validation steps. Saved profiles now use v2 with an additive research section; existing v1 profiles remain readable.

Eye input details: [every-frame held eye samples](../docs/DETECTION_RESEARCH_GUIDE.md#eye-input-update-unknown-holds-the-previous-input-every-frame). Unknown graph colors are unchanged; explicit numeric inputs/known flags appear in the research readout and exports.
