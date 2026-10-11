# Native face mouse MVP

The app now tracks **independent eyes/winks, Head Y, Head X and pupils**.
Tongue detection has been retired: no tongue tab, calibration, graphs, mouth crop,
model or background worker runs. Pupils are the mouse pointer input. The application
is local Python/Tk; it does not use a browser or send real OS mouse events.

## Open and test

Run from the repository root:

```sh
# Live camera; local MediaPipe model required.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task

# Generated face pixels follow calibration prompts; no camera required.
Vision/.venv/bin/python -m App --source detector-demo

# Automatic four-action mouse exercise; no calibration required.
Vision/.venv/bin/python -m App --source demo
```

Restart an already-open app to get these changes. A sole visible face attaches as
`single-user`; there is no identity recognition. Stop the source before switching
camera/demo/replay. No second application is required.

1. **Vision source & raw signals** shows the image, actual capture rate, raw eye
   geometry, pitch/yaw degrees and pupil direction before device mapping. Its raw
   graphs and the calibration tabs share the same captured samples.
2. **Detection calibration → 1 Eyes**: run **Start eye open/closed**, then
   **Start wink action**. The separate full-screen guides provide dots, rest
   countdowns and sound cues. Restarting wink training keeps eye geometry.
   A recognized wink remains ON while held. Eyes are independent; there is no
   opposite-eye or duration gate. [Eye testing guide](../docs/EYE_CALIBRATION_GUIDE.md).
3. **2 Head Y**: run **Start head pitch guide**. Comfortable up/neutral/down map
   to 0/.5/1. Pitch controls vertical scroll in mouse mode.
4. **3 Head X**: run **Start head yaw guide**. Comfortable left/neutral/right map
   to 0/.5/1. **Retry this pose** keeps successful prior captures and a previous
   completed fit. Head X is observable but is not mapped to the mouse yet.
   [Head X testing](../docs/HEAD_HORIZONTAL_TESTING.md).
5. **4 Pupils**: press **Start / restart pupil guide**. Keep looking at center
   while turning/nodding your head, then center your head and follow the eye targets.
   Your chosen limits map to 0/.5/1 after learned head compensation. Fresh checks
   must pass before the new fit replaces an existing one. **Retry failed step**
   or **Reset pupils only** leave eyes and head fits intact. An **11×11 square
   matrix** highlights the cell; a white dot shows continuous position.
   [Full guide and engineering details](../docs/PUPIL_HEAD_CALIBRATION_GUIDE.md).
6. To exercise Processing, open **Live lab**, center your head/pupil direction,
   open both eyes, and press **Start preview**. Test left wink, right wink,
   pupil movement and head pitch separately. Movement is relative velocity,
   not an estimate of the screen location you are looking at.
7. **Transfer settings** changes mouse dead zones, smoothing, acceleration and
   preview speeds. These device response functions are separate from detection.
   Applying changes stops preview. Its pointer source is fixed to `gaze` (pupils).

Unknown plots hold the last displayed position in a darker color. Actual unknown
observations remain invalid. Unknown eye Processing samples hold the previous
number with `known=false`, releasing that button; reopening is required before a
new activation. Pupil closure/loss invalidates the matrix and stops pointer output.
Face loss, stale input, source stop and profile loading never auto-arm preview.

## Save or reuse calibration

Use **Save active profile** and **Load saved profile** on the source tab. Files
are private local JSON under ignored `local-profiles/` by default. Loading works
while stopped or without a face, but camera and synthetic profiles remain separate.
A pupil-only profile can save without any fitted eye/head detector. Pupil calibration
uses raw same-frame head angles; Head X/Y calibration is not a prerequisite.
Raw pupils remain visible before calibration, but normalized pointer values are invalid.

New combined files remain `face_mouse_profile_v3`; their detector section is
**v12**, `head-compensated-pupils-v12`. It stores independent eye geometry, wink
models, head pitch/yaw fits, settings, pupil endpoints and learned head compensation.
No tongue data/settings, images, trace history, tracking IDs or armed state are
saved. Profiles from detector v1–v11 are validated fully, then retired tongue
state and old pupil calibration/settings are discarded. Compatible eyes/winks
and head fits survive; run the new pupil guide before using the pointer. A legacy image-position head fit needs the pitch guide;
old geometry-only eye files need Wink action training for clicks.

Old `pointer_source: tongue` settings migrate to `gaze`, including imported
Processing settings and `--config`. Other mouse response settings are retained.
Loading disarms output; inspect readings and explicitly start preview again.
Save the migrated profile to preserve the new format. Existing files are not
rewritten automatically.

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
                                  scopes / simulated mouse preview
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
every capture. Driver-facing `mouse_preview_v0` is still provisional.

`Vision/legacy_presets.py` validates old files. Retired tongue algorithm modules,
notices and unit tests remain for historical compatibility/developer use; they
are not imported by a fresh current runtime or current-profile round trip.
The standalone Processing developer library still accepts legacy tongue replays.
Read [the retirement contract](../Contracts/TONGUE_RETIREMENT.md) before modifying
these compatibility boundaries. Drivers integration and human accuracy testing
remain pending.

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
