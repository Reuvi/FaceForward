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
| Detector demo (synthetic pixels) | Automatically exercise guided eye calibration | Single user attaches automatically; Start eye calibration; the fixture follows the guide, then cycles independent closures; saves synthetic profiles |
| Camera (live calibration) | Test your actual facial measurements | Face attaches automatically; calibrate or load a camera profile; validate on your current image |
| Vision demo (synthetic) | Automatic four-action Processing regression | Supplies prebuilt valid SignalFrames; no detector training or face profile |
| Vision replay (NDJSON) | Inspect recorded synthetic SignalFrame sequences | Select a subject; preserves input timing; no images or calibration collection |

Stop the current source before starting another. Only one app should own a physical
camera. Other agents can run synthetic sources in their separate worktrees.
The requested FPS takes effect on source start; actual Hz and capture age are shown.

## Calibrate, then use the original lab

1. On **Vision source & raw signals**, start Camera or Detector demo. Your face
   attaches automatically as **single-user**. No face selection is needed. The app
   assumes one operator; it does not identify people.
2. Open **Detection calibration → 1 Eyes**, set rest time, try **Test sound**,
   then **Start eye calibration**. The temporary full-screen guide covers open
   poses, gentle closed/reopen geometry, natural blinks, three winks per eye,
   then separate checks with new blinks and two winks per eye. Rest and sound cues
   separate movements. The 21-step flow takes about 2½ minutes at default timings.
   Follow [the eye testing guide](../docs/EYE_CALIBRATION_GUIDE.md) for exact cues,
   acceptance rules, measurements and troubleshooting. Restart discards bad eye
   training without clearing head/tongue fits. Focus on eyes before proceeding.
3. In **2 Head Y**, capture NEUTRAL, UP, DOWN. Default measurement is vertical
   position of the nose bridge divided by image height. For nodding, choose
   `head_mode: "pitch"` in detector Settings **before** calibrating; it
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
7. Use **Transfer settings** for motion dead zones, smoothing, sensitivity,
   acceleration and preview speed. Apply changes and start preview again. Use
   **Save active profile** in the source tab to save the applied settings and fits.

Unknown detector observations and graph/CSV evidence stay invalid. The explicit
Processing eye input holds its previous numeric value with known=false on every unknown captured
frame; that flag releases the affected output and never counts as intentional reopening.
A new source/person/profile/calibration starts each eye at 0 until a known value arrives.
A dark held trace is not a new measurement or a continued button press. Channels with no prior known
value stay blank; source/subject resets start a new history.

The preview is unmirrored: your left eye appears on the image's right. Both eye
classifiers stay independent. A recognized wink is ON while held and OFF on
reopening; recognized natural blinks stay OFF. There is no duration gate or release
delay in the calibrated camera path. Following arming or unknown, an actual open
eye is required before that eye can activate. Both intentional winks can activate.

| Channel | Detector measurement | Processing result |
| --- | --- | --- |
| Left/right eye | Anatomical `*_eye_open` unchanged; added `eye_intent` from independent calibrated facial appearance | Per-frame wink states: 1 while held, 0 for open/blink; no dwell |
| Head Y | Image-height fraction or pitch degrees → calibrated `[0,1]`: up 0, neutral .5, down 1 | Smoothed scroll velocity; .5 means stopped |
| Tongue X/Y | Color candidate centroid in the mouth frame; X toward anatomical right, Y down | Relative pointer velocity; .5 means stopped per output axis |

Gaze and head X remain unavailable in this calibrated path. Tongue absence is
unavailable input, never an invented center. The raw-mock adapter's eye bits use
`1=closed`; App's SignalFrame path has the opposite, explicitly named polarity.
All geometry, quality gates, thresholds, settings and limitations are documented
in [the detector runbook](../Vision/DETECTION_LAB.md). Transfer functions are in
[Processing's guide](../Processing/README.md) and [the engineering guide](../docs/ENGINEERING_GUIDE.md).

### Camera-free calibration exercise

In `detector-demo`, press **Start eye calibration** in
Detection calibration. The generated pixels and landmarks follow all 21 steps
without manual switches; after completion the fixture cycles left, right and both
closures. Start preview to inspect the resulting clicks in Live lab. This exercises
wiring, not real-face accuracy. Mock checkboxes/sliders are removed from calibration; the old mock eye checkboxes
are also hidden in App’s Live lab. Standalone Processing retains its developer controls.
Developer scripts can still set `LabRuntime.demo_controls`; tests retain manual
head/tongue fixtures. For the automatic four-action mouse exercise, use `python3 -m App`.

## Saved face + mouse profiles

**Save active profile** writes a versioned local JSON file, by default under ignored
`local-profiles/`. At least one completed detector fit is required; saving works
while stopped or while your face is unavailable. A left-eye-only profile is valid; it does not calibrate the other eye.

| Saved section | Contents |
| --- | --- |
| `format`, `source_kind` | `face_mouse_profile_v3` (v1/v2 readable); camera or synthetic |
| `detector` | Version/algorithm, detector settings, independent eye fits including raw closed/open uncertainty limits and appearance models/check counts, head mode and three-point fit, optional tongue color prototypes/radius/margin |
| `processing` | Applied motion settings; legacy raw/replay eye settings retained but bypassed for camera wink samples |
| `preview` | Simulated pointer and scroll speed |

It does **not** save pictures, raw training pixels, sample traces, tracking IDs,
selection, live tongue validation flags, armed state, or driver permission. Local files
are written atomically with private file permissions. They are not committed.
Detector presets now use version 3. Version 1/2 files restore geometry and other
settings but require the new eye guide before camera wink buttons are available.
New files omit research settings, images and raw wink training vectors.
Saving does not activate anything; it records the current applied configuration.

To reuse: choose/start the matching Camera or Detector demo source, then click
**Load saved profile** and choose your JSON. Loading also works after stopping the
source or while your face is unavailable. App validates the whole profile, applies
it to the single user, restores Processing settings, and leaves preview stopped.
Camera and synthetic profiles cannot be mixed. Check eye/head readings again;
repeat tongue ABSENT and VISIBLE checks under current lighting. If those fail,
recollect tongue training. Loaded color prototypes do not retain training samples.

Head motion, brief loss, stale frames, Stop source and restart of the same source
retain your completed eye/wink/head/tongue fits in memory. Detection resumes
when the face returns; click **Start preview** separately to resume mouse testing.
An unfinished calibration capture is cancelled. Restart requires fresh tongue
checks but keeps their models. Changing source kind, applying detector Settings,
or **Detection calibration → Settings → Reset all calibration** clears the fits.
Closing the app clears memory: save a JSON first and load it next time.
The source tab shows the saved profile name independently of tracking status.
Only one person should use the camera; there is no identity recognition or automatic
profile choice for different people. Load the appropriate file when changing users.
After further edits, save again to preserve current values. Detector Settings
**Save JSON** saves only detector tunables; Transfer settings export saves only
Processing settings. Neither is a substitute for **Save active profile**.

## Stop and runtime boundaries

**Stop / Escape** immediately disables preview but keeps measurement running.
**Stop source** also stops capture and retains completed calibration. Calibration
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
combined profile loading is through **Load saved profile** in the source tab. The emulator
message format, units, transport and OS output remain the next Drivers handoff.
See [the adopted contract](../Contracts/MOUSE_MVP.md) and
[main chat coordination](../docs/COORDINATION.md) before changing those boundaries.

## Current eye workflow

The separate Detection research tab and its per-frame runtime are removed. Useful
blink/wink learning and checking now live in Detection calibration. Its lower scope
selects wink samples, same-eye facial features or raw eyelid ratios; CSV export
retains all eight features, model scores and capture timestamps. See the
[eye testing guide](../docs/EYE_CALIBRATION_GUIDE.md) and
[sampled intent contract](../Contracts/EYE_INTENT.md). Legacy research modules remain
for developer tests and old-profile validation; they do not run in the active App.
