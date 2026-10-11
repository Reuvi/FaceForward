**Current presentation mode:** `--mapping presentation` adds head movement, continuous mouth braking, left-eye click/drag, right-eye Enter and both-eyes dictation. Plain open/closed eyes are the default. [Complete setup and controls](../docs/PRESENTATION_GUIDE.md). Build the driver and local macOS speech helper before use; output still needs Connect and Start.

# Native face mouse and keyboard preview

The app now tracks **independent eyes/winks, mouth open, Head Y, Head X and pupils**.
Tongue detection has been retired: no tongue tab, calibration, graphs, mouth crop,
model or background worker runs. Gaming uses pupils for the mouse pointer; Mouse test uses head X/Y. The application
is local Python/Tk. Output is selectable: Preview, Driver dry run, or Live mouse +
keyboard. Native output is explicitly enabled with the Camera source; Stop and
closing App release it. [Build and live-output instructions](../docs/DRIVER_CONNECTION_GUIDE.md).
Without a measured personal default, the default is **gaming keyboard mouse mapping 1**: left/right eye actions →
left/right mouse, head down/up/left/right → W/Space/Shift/S, pupils → an approximate
screen destination where the cursor stops. **Mouse test** combines calibrated head X/Y into relative pointer movement: left eye → held W, right eye → one left click, mouth open → held Space. Pupils, head-direction keys and scroll are ignored. Mouth needs no calibration; eyes use your saved wink/plain-closure choice. [New button layout and relative mode](../docs/MOUTH_BUTTON_GUIDE.md). The previous **Mouse and scroll** mode remains selectable. See
[the Processing runbook](../Processing/mappings/README.md) for tuning and saved mappings.

## Measured target game

Open **Signals → Target game…** with Camera, Mouse test and Live mouse + keyboard
connected. Move between targets and hold for 600 ms; the game records travel,
small-target exits/re-entries, accuracy and roughness. A → B → B → A rounds test
one supported adjustment and save the winner as a local personal default. Native
output still requires explicit Start. A physical-mouse Practice mode cannot tune.
[Game instructions and recorded data](../docs/TARGET_GAME_GUIDE.md).
If a round cannot start from the previous resting pose, use **Recenter & continue**
inside the game. Saved rounds remain available; changed setups are labeled and
excluded from unmatched automatic comparisons. No suggested adjustment still
allows more baseline data collection.

Normal startup and `--mapping mouse-test` use a valid saved personal default;
explicit other mappings override it. `--factory-defaults` ignores it for this run.
The default file contains response settings, not face calibration or armed state.

## Live curve editor

Open **Signals → Live curves…** to adjust the active mapping with connected sliders.
See actual response curves/live markers and a synthetic ramp/settling preview.
Pointer velocity/target, head-key gates and scroll expose the controls they use;
calibrated winks show independent binary click states. Live response edits preserve
running control. **Save as…**, **Load…**, **Personal default** and **Factory defaults** manage local
tuning files; loading/defaults stop output. Uncheck **Require calibrated wink for eye actions**
for immediate plain open/closed input; ordinary blinks also click. Changing the flag
stops output. **Center head & start** captures a new resting center in Mouse test
and starts the connected output. Face calibration stays separate.
[Editor, timing and profile guide](../docs/LIVE_CURVE_EDITOR_GUIDE.md).

## Open and test

Run from the repository root:

```sh
# Live camera; local MediaPipe model required.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task

# Generated face pixels follow calibration prompts; no camera required.
Vision/.venv/bin/python -m App --source detector-demo

# Automatic gaming command exercise; no calibration required.
Vision/.venv/bin/python -m App --source demo

# Head mouse and button layout (load/calibrate Head X and Head Y, then Start live control).
Vision/.venv/bin/python -m App --source camera --output native --mapping mouse-test

# Previous mouse/scroll exercise.
Vision/.venv/bin/python -m App --source demo --mapping mouse

# Exercise the compiled driver without sending OS events.
Vision/.venv/bin/python -m App --source demo --output dry-run
```

Restart an already-open app to get these changes. A sole visible face attaches as
`single-user`; there is no identity recognition. Choosing a source stops the old
worker before starting the new one. No second application is required. The
default is a labeled synthetic demo; choose **Camera** to open your camera.

1. **Signals** combines the camera preview, source/profile/output controls,
   normalized input → filtered signal → command table, and graphs. Choose raw
   detector graphs, Head processing or Pointer processing from the graph picker.
   Raw graphs and calibration share the same captured samples. The App has only
   two main tabs: **Signals** and **Calibration**. The standalone Processing lab
   retains its developer playground, full transfer settings and JSON inspector.
2. **Calibration → 1 Eyes**: run **Start eye open/closed**, then
   **Start wink action**. The separate full-screen guides provide dots, rest
   countdowns and sound cues. Restarting wink training keeps eye geometry.
   A recognized wink remains ON while held. Eyes are independent; there is no
   opposite-eye or duration gate. [Eye testing guide](../docs/EYE_CALIBRATION_GUIDE.md).
3. **2 Head Y**: run **Start head pitch guide**. Comfortable up/neutral/down map
   to 0/.5/1. Pitch controls Space/W in gaming mode or scroll in mouse mode. **Retry current step**
   repeats a capture/check; choose a pose beside **Redo selected step** to redo
   just neutral, up or down, including from a loaded profile. Other references and
   the last working fit stay intact; changed references require fresh checks.
   [Head Y retry instructions](../docs/HEAD_Y_RETRY_GUIDE.md).
4. **3 Head X**: run **Start head yaw guide**. Comfortable left/neutral/right map
   to 0/.5/1. **Retry this pose** keeps successful prior captures and a previous
   completed fit. Gaming maps left/right to Shift/S independently of pitch.
   [Head X testing](../docs/HEAD_HORIZONTAL_TESTING.md).
5. **4 Pupils** shows live raw iris X/Y and the **11×11 matrix**. No pupil
   calibration is needed: a fixed scale maps eye-relative direction to 0–1.
   There is no trained head-angle restriction or head compensation. A white dot
   shows the continuous value. Keep both pupils visible; adjust mouse gain,
   fixation dead band and smoothing in **Signals → Mapping settings…**.
6. Open **Signals**, center your head and release eye actions,
   and press **Start**. Inspect raw → filtered → instruction for each
   input. **Mapping settings…** opens Head X/Y activation/release thresholds,
   smoothing, confirmation, key bindings and pointer response controls. Use
   **Copy as…** to make another named mapping; **Export mapping** saves it locally.
   **Screen destination** moves to a point and stops, using raw pupil X/Y as
   approximate screen coordinates. No pupil-center startup gate is needed.
   This has not been calibrated to the actual point you are looking at;
   [behavior and accuracy limits](../docs/SCREEN_POINTER_GUIDE.md).
7. **Mapping settings… → Pointer behavior** chooses Screen destination or Relative movement.
   Destination mode exposes position smoothing (20 ms), delay (0 ms), downward
   boost (4×), pointer gain (2×) and a fixation dead band (.002). Velocity exposes the original central dead zone,
   activation margin, response curve, acceleration and deceleration. Applying changes
   stops output. The pointer uses pupils in gaming or head X/Y in Mouse test. **Adaptive pointer smoothing (1€)** reduces stationary jitter and responds faster to deliberate motion; uncheck it to compare the fixed filter. In Mouse test, unused dwell/key settings are hidden; its Enable eye button actions checkbox is in Head movement response. Detector setup remains
   independent in Calibration. Mouse test also offers **Speed-aware acceleration
   and return braking**: fast outward turns accelerate, returning toward neutral
   brakes, and holding a position keeps its usual speed. Uncheck it to compare
   the response without transient boost/braking. Small movements now give much slower precision speed; larger turns still reach full speed. [Head pointer tuning](../docs/HEAD_POINTER_GUIDE.md).
8. To control the OS, build Drivers and choose **Output → Live mouse + keyboard →
   Connect output** on Signals, then **Start live control**. Mapped mouse buttons
   produce one complete click per activation (no dragging); keyboard actions stay held
   until their input releases or becomes invalid. **Driver dry run** exercises the actual library without
   OS input. Any driver error stops output and remains visible in the UI.

**Mouse test setup:** choose **Signals → Active mapping → Mouse test**, load a
profile with both head fits (or complete **Calibration → 2 Head Y** and **3 Head X**),
connect **Live mouse + keyboard**, hold a comfortable pose and choose **Center head
& start**. It uses the next fresh capture, so no movement is sent from an old frame.
Normal **Start live control** instead waits for the saved center. The status now
identifies that blocker and offers recentering; restarting the driver is unnecessary.
Head movement needs no eye/pupil calibration. For clicks, enable **Mapping settings →
Head movement response → Enable eye button actions**. Use **Live curves → Require calibrated wink
for eye actions** to select trained wink actions (checked) or plain eye open/closed
(unchecked). Plain mode requires only eye geometry; ordinary blinks also click.
Left-eye activation holds W; right-eye activation clicks once until reopening. Mouth opening holds Space until closed, with no guide or adjustable threshold. Both calibrated head inputs must
be valid; raw yaw alone is insufficient. Changing mappings or eye mode stops output.

Pupils use raw direction without a guide or personal pupil fit. They can use completed guided eye geometry as additional evidence for naturally narrow open eyes. Without it, generic checks still work. Raw coordinates and saved pupil/head fits are unchanged; closure, ambiguous iris evidence and missing input still stop motion. See [quality changes and measured software comparison](../docs/PUPIL_QUALITY_GUIDE.md).

Unknown plots hold the last displayed position in a darker color. Actual unknown
observations remain invalid. Unknown eye Processing samples hold the previous
number with `known=false`, releasing that button; reopening is required before a
new activation. Pupil closure/loss invalidates the matrix and stops pointer output.
Face loss, stale input, source stop and profile loading never auto-arm preview.

## Save or reuse calibration

Use **Save profile…** and **Load profile…** on Signals. Files
are private local JSON under the checkout's ignored `local-profiles/` by default.
Loading validates the entire file before changing source, selects Camera or
Detector demo to match the file, and disarms output. If the previous source was
running, switching starts the matching source after the old worker closes.
If already stopped, loading stays stopped and needs no face or camera. Press
**Start camera** to resume capture, then explicitly Start control. Camera and
synthetic profiles remain separate; one never calibrates the other source.

**Camera settings…** contains camera ID, requested FPS and the local model path.
The default model and profile folder resolve from the checkout, even when launched
from another directory. Startup errors remain visible beside the preview. If the
camera cannot open, check camera permissions for the launching app and close other
camera apps. Dependencies must be installed in the Python environment running App.
Pupil movement works without any eye/head calibration or profile. Eye clicks
and head keys still require their own independent guides or compatible saved fits.

New combined files remain `face_mouse_profile_v3`; detector presets are now
**v13**, `raw-pupil-control-v13`. Old detector v1–v12 files are validated fully.
Compatible eyes, wink models and head fits survive; validated v12 pupil fits are
stored as inactive legacy data and never alter raw control. Older tongue and
obsolete pupil settings remain retired. No images, trace history, tracking IDs or
armed state are saved. A legacy image-position head fit needs the pitch guide;
old geometry-only eye files need Wink action training for wink-mode clicks; plain
open/closed mode uses compatible geometry alone.

Old `pointer_source: tongue` settings migrate to `gaze`, including imported
Processing settings and `--config`. Other mouse response settings are retained.
Loading disarms output; inspect readings and explicitly start preview again.
Save the migrated profile to preserve the new format. Existing files are not
rewritten automatically.

Gaming names, head thresholds, key bindings and pointer gain use separate
`input_mapping_v8` files (v1/v2 import as velocity; old mappings retain their response and original eye-click assignments, with mouth unassigned; v1–v5 head mappings keep eye actions off) exported from **Signals → Mapping settings…**. Mode, gains and target filtering belong to the mapping. Face profiles continue
to contain detector fits and the existing mouse response settings. Loading a face
profile applies its response to the selected mapping and stops output; it keeps
that mapping's name, head settings, bindings, gains and target filtering. Mouse test
also retains its pointer response and delay, including the new 3× downward boost
and 20 ms smoothing. The head motion response, saved head center, eye-click enable and wink/closure choice also
belong to the mapping. Export mapping settings separately
after tuning them; named copies are otherwise held only for the current app session.

Brief face loss and same-source restarts keep completed fits. Switching source
kind, applying detector settings, or **Reset all calibration** clears them.
Closing the app clears memory, so save first. Leaving a running guide cancels its
unfinished capture; completed fits remain.

## Runtime and agent handoff

```text
One source worker: camera → MediaPipe OR synthetic face generator
    ↓ captured image + landmarks + capture timestamp
Vision.LabRuntime → DetectorWorkbench: eyes/winks + pitch/yaw + pupils
    ├─ shared capture trace → source screen / calibration / CSV
    └─ SignalFrame v1 → MouseSession → Processing.Lab.ingest
                                       ↓ independent 100 Hz Processing clock
                                  named mapping / scopes / command preview
```

Tk draws snapshots separately; camera overlays are capped near 10 Hz. No tongue
crop or worker is scheduled. The standalone `python -m Vision.lab --demo` reuses
this detector UI without Processing and likewise contains no active tongue path.

SignalFrame v1 keeps required `tongue_x/y` slots null/invalid for compatibility.
Current producers emit no `tongue_sample` or tongue coordinate metadata. App uses
continuous `gaze_x/y`; the additive `pupil_matrix_v1` is available for inspection,
without quantizing mouse movement. `gaze_measurement` is now
`mediapipe_iris_direction_v3`, identifying fixed-scale raw iris direction.
Legacy compensated trace columns stay null, never fabricated. Independent `eye_intent_v1` samples remain on
every capture. Gaming emits `device_control_v1` with held keys/buttons, explicit target or velocity mode,
validity and original capture provenance. Mouse mode preserves `mouse_preview_v0`.
See [the command boundary](../Contracts/GAMING_MAPPING.md) and
[driver connection](../Contracts/DRIVER_CONNECTION.md). Driver commands are sent
synchronously on captures and output ticks, preserving short eye activations.
The bounded UI transition journal is diagnostic only and is never replayed to
the driver. Close stops/destroys the driver; no background service is installed.

`Vision/legacy_presets.py` validates old files. Retired tongue algorithm modules,
notices and unit tests remain for historical compatibility/developer use; they
are not imported by a fresh current runtime or current-profile round trip.
The standalone Processing developer library still accepts legacy tongue replays.
Read [the retirement contract](../Contracts/TONGUE_RETIREMENT.md) before modifying
these compatibility boundaries. Human accuracy and live OS/game behavior still
need operator testing; automated evidence uses the compiled driver's dry-run mode.

## Software checks

```sh
Vision/.venv/bin/python -m unittest discover -s tests/vision -v
Vision/.venv/bin/python -m unittest discover -s tests/processing -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -v
Vision/.venv/bin/python -m App --source demo --headless --frames 490
```

Synthetic tests check software behavior, not real-person accuracy. No camera is
opened by the default tests. The real MediaPipe blank-image smoke test is optional
via `VISION_MODEL_PATH`; no tongue model is needed to use the app.

### Live-control diagnostics

Signals displays the exact pointer blocker beside the camera: unavailable pupils,
confidence/freshness rejection, axes waiting for neutral, or the dead-zone radius.
The header preserves the stop/error reason. Starting while looking away, then
centering, now clears pre-enable interpolation history so the driver's first
command reflects the actual neutral input. Held eye actions must release first.

App saves bounded scalar/error observations to
`.local/diagnostics/live-control.jsonl` (three rotating 1 MB files; ignored by Git,
owner-only permissions). No camera images, landmarks or saved calibration models
are stored. `--diagnostic-log PATH` changes the path; `--no-diagnostics` disables
logging. The log samples at 5 Hz plus observed state changes and is not a full
capture replay. See [diagnosis and filter values](../docs/DRIVER_CONNECTION_GUIDE.md#if-the-pointer-stays-stopped).
