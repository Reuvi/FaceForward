# Mouse lab integration, October 2026

[TONGUE_RETIREMENT.md](TONGUE_RETIREMENT.md) is current: no active tongue
path, pupil-only App pointer and detector presets v11. Earlier tongue requirements
below are historical; keep the two invalid v1 schema slots for compatibility.

Status: implemented for **native Vision → Processing → simulated mouse**.
This adopts the local Python handoff requested by the team. SignalFrame v1 is
unchanged. The earlier ControlFrame v1 remains a driver draft; the lab's separately
named `mouse_preview_v0` is not silently presented as that driver format.

## Accepted input and lifecycle

- App imports Vision's `mouse_demo_records`, `replay`, `read_ndjson`,
  `OpenCVCamera`, `MediaPipeDetector`, and externally driven `LabRuntime`. These are the adopted
  native producer interfaces; construction/import does not open hardware.
- All components use the same host's monotonic milliseconds. Capture time is
  preserved through inference/handoff. Replay rebases session time deliberately.
- App calls `Lab.ingest(frame)` in `external` mode, directly and synchronously.
  The separate Lab worker calls `tick` at a target of 100 Hz even without input.
- Sequences strictly increase within a session; capture timestamps are
  **nondecreasing**. A newer sample with the same timestamp replaces that axis
  interpolation point and advances no eye dwell time. Duplicate sequences or
  regressing capture times are rejected without refreshing freshness.
- The calibrated camera and detector demo use one logical `single-user` subject,
  automatically attached to the sole observation. Geometric tracker ID changes
  do not change the active person's calibration. Replay retains explicit subject
  selection for legacy recordings. Loss/restart disables output; reacquisition
  resumes detection but never arms the mouse preview.
- EOF, errors, explicit source stop, and application shutdown call
  `Lab.disconnect(reason)` immediately. Timeouts independently disable output.
  Re-enabling requires explicit Start preview and fresh neutral axes; each eye
  needs its own open baseline.
- Camera and detector-demo use the selected-face calibration workbench. Per-eye
  fits, head calibration and fresh tongue checks gate their respective measurements.
  Uncalibrated/unavailable channels remain invalid. Raw geometry is diagnostic;
  synthetic checks do not establish real-person accuracy.

Input meanings are still those in [SignalFrame v1](README.md): continuous positions,
`*_eye_open` bits with **1 = open**, confidence, and validity. Processing's
alternative raw one-hot format has **1 = closed** and is not used by the Vision
producer. App does not quantize continuous positions into a matrix/vector.

## Raw diagnostic side channel

`MouseSession.deliver(frame, observations=..., preview=..., inference_ms=...)`
adds optional diagnostics alongside, never inside the control measurements:

```text
observations[subject_id] = {
  eyes: {left/right: {openness, horizontal, vertical}},
  head_reference: {origin, right, down, width} or None,
  box: {x, y, width, height}
}
```

Eye values are dimensionless ratios from Vision geometry. Head reference uses
pixel origin/width and unit image-plane axes; tracker box coordinates are
image-normalized. None of these is head pitch/yaw, a confidence estimate, or a
validated gesture. `preview` is one in-memory PPM image encoded by the camera
worker and rendered by Tk. No queues/recordings/network transport are introduced.
`MouseSession.state()` reports source mode/status/error, measured delivery rate,
current frame, latest diagnostics/preview, and age. Stale displays are labeled.

## Provisional mouse output

```json
{
  "format": "mouse_preview_v0",
  "mode": "mouse",
  "sequence": 43,
  "timestamp_ms": 1050.0,
  "source": {
    "session_id": "source-run",
    "sequence": 12,
    "timestamp_ms": 1000.0,
    "subject_id": "selected-person"
  },
  "enabled": true,
  "buttons": {"left": 0, "right": 0},
  "velocity": {"x": 0.5, "y": 0.5, "scroll": 0.5}
}
```

Output sequence/time belong to the independent processing clock; `source`
preserves capture metadata. Both button states are independent 0/1 values.
Velocity is normalized: `signed = 2 * value - 1`, negative means left/up,
positive means right/down, and `0.5` means stopped. The simulated desktop
integrates signed velocity over time. Disabled output is all buttons 0 and
all axes 0.5. There is no middle-button press, keyboard, speech, or gamepad mode.

The driver's accepted units, maximum speed, fractional deltas/scroll accumulation,
button transitions, disconnect/watchdog behavior, and public callback/queue remain
pending. Adapt them in `Processing/mouse/output.py` after agreement; do not change
the detector or filtering algorithms to fit a serialization choice.

## Unified calibration and profile handoff (current increment)

The main chat now authorizes integrating detector calibration into App. App owns
one capture/inference worker for camera or `detector-demo` (synthetic pixels),
and invokes Vision's public `LabRuntime.ingest` and calibration commands. That
runtime is externally driven in App and does not start another worker. Calibrated
SignalFrame values pass directly to the existing `Lab.ingest` and 100 Hz processor.
Calibration collection and changes disarm the simulated preview. Tab changes do
not restart capture or arm output. Leaving an active guided eye sequence cancels it;
completed fits survive tab changes. The real driver is not wired.

`face_mouse_profile_v3` contains `format`, `source_kind` (`camera` or `synthetic`),
`detector`, `processing`, and `preview`; v1/v2 remain readable. Detector section
version 5 uses `color-tongue-tip-v5`, DetectionConfig, separate eye geometry
and checked per-frame wink models, a head fit, optional tongue color parameters,
`tongue_measurement: color_tip_mouth_width_v1` and `tongue_range`. Detector v1-v4
remain readable; compatible eyes/winks/head survive, but old tongue appearance
and ranges require retraining. See [TONGUE_TIP.md](TONGUE_TIP.md) and
[MOVEMENT_CALIBRATION.md](MOVEMENT_CALIBRATION.md) for measurement units,
shared raw diagnostics and guided movement checks.
Processing is MouseConfig; preview contains pointer/scroll speeds. No images, raw
training vectors, arming state or live tongue validation flags are saved. Wink
check counts are persisted with the fitted model. Old research/event models are
not frame classifiers and are not used by App. Old detector v1/v2 profiles need
new wink calibration before closures can activate buttons. See
[EYE_INTENT.md](EYE_INTENT.md) for the additive sampled intent and no-dwell path.
Processing owns atomic local JSON persistence and its settings validation; Vision
owns detector preset validation/export/import; App validates/binds both together.

Load requires a matching source kind, but no visible face or running camera.
It replaces the active single user's parameters, resets and disarms the processor,
and requires a fresh tongue absent + five-position recheck of the saved range.
Eye/head parameters apply to subsequent samples; the operator must recheck them.
Stop, stale input, loss, and same-source restart preserve completed calibration.
An interrupted capture/guide is cancelled; invalid observations never train it.
Changing source kind or explicitly resetting calibration clears the in-memory
fits. Restart invalidates live tongue checks but retains its appearance model.
No biometric identity matching occurs: the sole face is assumed to be the user.
Camera inference requests one face; injected multi-face input is treated as unavailable.
Files are
suggested under ignored `local-profiles/`; old Processing-only JSON import/export
continues to mean transfer settings, not a complete detector profile.

### Guided eye calibration increment

The geometry stage starts with five open poses (center, left, right, up, down),
both eyes gently closed, then a fresh reopen check. Each eye fits and validates
independently; no both-eye veto is introduced. Per-eye fits serialize `closed`,
`opened`, `threshold`, `closed_limit`, `open_limit`. The latter two are raw lid-gap /
eye-width ratios, both null for legacy fits or both finite ordered limits inside
the closed/open references. New guided fits emit invalid/null between the limits;
Processing already releases the affected button on invalid input. Named SignalFrame
polarity remains 1=open, while the dedicated scope/CSV closed bit is 1=closed.

Version 1 detector presets with algorithm `lid-gap-head-y-lab-color-v1` and three
original eye fields still load. They keep the original single-boundary behavior
until recalibrated, but cannot activate camera wink buttons without the new
appearance guide. New combined files use v3; legacy formats remain readable.
No training poses, images, sound state or guide progress are persisted.

Vision exposes `start_eye_guide`, `present_eye_step(index)` and `cancel` through
App's command allowlist. A new phase waits for the UI to present its instruction
before accepting captures. `DetectorWorkbench.calibrating` includes both legacy
collections and all active guided phases; App disarms throughout. Restart drops
both eye fits/samples but preserves unrelated head/tongue fits. Leaving the active
Eyes view cancels the guide; loss/staleness cancels only active collection and
preserves completed fits.


### Full-screen guide and unknown trace display

The eye guide uses a temporary native full-screen window owned by the existing Tk
application. Presentation acknowledgment waits for that window's target to be mapped
and painted. Completion, retry, cancellation, source loss and shutdown dismiss it;
Escape cancels. The same worker, fits and saved profile are used.

Plotting may hold a previous value in a darker color during an unknown interval.
This is presentation only, never a SignalFrame measurement or a Processing input.
Numeric values, validity, CSV, release/disarm behavior and all wire formats remain
unchanged. No inferred value is inserted into a trace row. Never promote a plotted
hold to a driver command.

### Eye sampling update

Processing now holds an unknown eye at its **previous numeric input**, with a
separate `known=false` flag. The per-capture `eye_sample_v1` is defined in
[the research handoff](RESEARCH_LAB.md#eye-samples-with-unknown-value-hold).
`Lab.state()["eye_sample"]` exposes the latest normalized eye input, including
held samples when the selected face is absent. Source observations and dark
unknown graph holds are retained. The unknown flag cancels eye timers and releases
held state; it cannot trigger a release-click or count as measured calibration data.
Missing-person frames continue to disable control, even while their held eye
samples are recorded. With no history an eye starts at 0; source, selected-person,
profile and calibration changes clear history. Head/tongue and output formats are unchanged.

### Guided eye rest intervals

Guided eye calibration inserts a rest before each pose after the first. Detector
setting `eye_rest_ms` defaults to 3000 ms (0–30000 ms; 0 skips rest); old settings
without this field load with the default. The Eyes panel edits this duration in
seconds when starting/restarting the guide, and profiles retain it.

Guide snapshots add `resting` and `phase` (`rest`, `prepare`, `capture`, `complete`).
`capture_start_ms`/`capture_end_ms` bound the accepted capture timestamps; both are
null until the pose is presented. Consumers must check these bounds so a delayed
rest frame cannot train a model after the UI switches to capture.
During rest, `target` is null, `preparing` is true, and no eye or expression-calibration
samples are retained. Capture and numeric input delivery continue normally; output
stays disarmed. Each rest and next pose waits for its prompt to be painted before
its timer starts. `present_eye_step(index, phase=None)` optionally checks the phase
so a delayed acknowledgment cannot start a different phase of the same pose.

Four low tones announce rest; after the closed pose, two high reopen tones precede
them. The next pose has its own ready/close/reopen cue, and three high tones mark
sampling. Cancellation/source loss still dismisses the same native popup. No
separate program, camera stream, recording, or dependency is introduced.
