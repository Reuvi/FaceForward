# Native face mouse and keyboard preview

The app now tracks **independent eyes/winks, Head Y, Head X and pupils**.
Tongue detection has been retired: no tongue tab, calibration, graphs, mouth crop,
model or background worker runs. Pupils are the mouse pointer input. The application
is local Python/Tk. Output is selectable: Preview, Driver dry run, or Live mouse +
keyboard. Native output is explicitly enabled with the Camera source; Stop and
closing App release it. [Build and live-output instructions](../docs/DRIVER_CONNECTION_GUIDE.md).
The default is **gaming keyboard mouse mapping 1**: left/right eye actions →
left/right mouse, head down/up/left/right → W/Space/Shift/S, pupils → pointer
velocity. The previous **Mouse and scroll** mode remains selectable. See
[the Processing runbook](../Processing/mappings/README.md) for tuning and saved mappings.

## Open and test

Run from the repository root:

```sh
# Live camera; local MediaPipe model required.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task

# Generated face pixels follow calibration prompts; no camera required.
Vision/.venv/bin/python -m App --source detector-demo

# Automatic gaming command exercise; no calibration required.
Vision/.venv/bin/python -m App --source demo

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
5. **4 Pupils**: press **Start / restart pupil guide**. Keep looking at center
   while turning/nodding your head, then center your head and follow the eye targets.
   Your chosen limits map to 0/.5/1 after learned head compensation. Fresh checks
   must pass before the new fit replaces an existing one. **Retry failed step**
   or **Reset pupils only** leave eyes and head fits intact. An **11×11 square
   matrix** highlights the cell; a white dot shows continuous position.
   [Full guide and engineering details](../docs/PUPIL_HEAD_CALIBRATION_GUIDE.md).
6. Open **Signals**, center your head/pupil direction, open both eyes,
   and press **Start**. Inspect raw → filtered → instruction for each
   input. **Mapping settings…** opens Head X/Y activation/release thresholds,
   smoothing, confirmation, key bindings and pointer response controls. Use
   **Copy as…** to make another named mapping; **Export mapping** saves it locally.
   Pupil movement requests relative velocity, not the
   screen location you are looking at.
7. **Mapping settings…** also changes pupil dead zone, activation margin,
   smoothing, response curve, acceleration and deceleration. Applying changes
   stops output. Pointer input stays fixed to pupils. Detector setup remains
   independent in Calibration.
8. To control the OS, build Drivers and choose **Output → Live mouse + keyboard →
   Connect output** on Signals, then **Start live control**. Native eyes
   produce one complete click per activation (no dragging); head keys stay held
   until neutral/invalid. **Driver dry run** exercises the actual library without
   OS input. Any driver error stops output and remains visible in the UI.

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
A pupil-only profile can save without any fitted eye/head detector. Pupil calibration
uses raw same-frame head angles; Head X/Y calibration is not a prerequisite.
Raw pupils remain visible before calibration, but normalized pointer values are invalid.

New combined files remain `face_mouse_profile_v3`; their detector section is
**v12**, `head-compensated-pupils-v12`. It stores independent eye geometry, wink
models, head pitch/yaw fits, settings, pupil endpoints and learned head compensation.
No tongue data/settings, images, trace history, tracking IDs or armed state are
saved. Profiles from detector v1–v11 are validated fully, then retired tongue
state and old pupil calibration/settings are discarded. Both historical v10
pupil measurement identities (v2 and v3) are accepted before discarding that old
pupil setting. Compatible eyes/winks
and head fits survive; run the new pupil guide before using the pointer. A legacy image-position head fit needs the pitch guide;
old geometry-only eye files need Wink action training for clicks.

Old `pointer_source: tongue` settings migrate to `gaze`, including imported
Processing settings and `--config`. Other mouse response settings are retained.
Loading disarms output; inspect readings and explicitly start preview again.
Save the migrated profile to preserve the new format. Existing files are not
rewritten automatically.

Gaming names, head thresholds, key bindings and pointer gain use separate
`input_mapping_v1` files exported from **Signals → Mapping settings…**. Face profiles continue
to contain detector fits and the existing mouse response settings. Loading a face
profile applies its response to the selected mapping and stops output; it keeps
that mapping's name, head settings and bindings. Export mapping settings separately
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
`head_compensated_iris_direction_v1`; raw iris measurements remain
`mediapipe_iris_direction_v3`. Independent `eye_intent_v1` samples remain on
every capture. Gaming emits `device_control_v1` with held keys/buttons, velocity,
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
