# Mouse prototype: detector and emulator handoff

Status: **implemented within Processing; shared contract revision pending**.
Native Vision integration is now implemented by App and recorded in
`Contracts/MOUSE_MVP.md`. The driver format remains pending. The raw one-hot
alternative described here remains supported; current Vision uses continuous v1.
This records the latest team discussion and the prototype's assumptions. It does
not overwrite `Contracts/README.md` or imply that another teammate has accepted a
message format. Reuvi requested mouse-only experimentation and independent eyes.

## Detector input

The new detector discussion describes 2D matrices for tongue/gaze, two independent
eye bits (`1 = closed`), and a one-hot head-position vector. The prototype assumes
the 2D matrix is also one-hot. A heatmap/weighted matrix needs an explicit agreed
decoding rule before integration; it is rejected today.

This complete synthetic frame has centered positions, left eye closed, right eye open:

```json
{
  "format": "raw_mouse_v1",
  "session_id": "detector-run-1",
  "sequence": 12,
  "timestamp_ms": 1000.0,
  "subject_id": "selected-person",
  "left_eye": 1,
  "right_eye": 0,
  "tongue": [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
  "gaze": [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
  "head_vertical": [0, 0, 1, 0, 0]
}
```

Replace the example timestamp with capture time from the same host monotonic
millisecond clock. Sequence must increase strictly; capture timestamps must not
decrease. Equal capture times replace the interpolation point without adding dwell.
Use a new session ID when the detector restarts. Subject selection is explicit.
Null channel values represent missing detection; absent/invalid selected subject
disables the stream. The default pointer source is tongue; gaze is selectable.
Head horizontal is currently ignored in mouse mode.

Rows increase downwards, columns rightwards; coordinates are from the user's
perspective. Confirm whether the detector mirrors its output; per-axis inversion
is configurable. Matrix/vector dimensions may differ. Normalize index by `N - 1`
so both boundaries are representable, including even dimensions.

Existing SignalFrame v1 is also accepted via a separate adapter. Its eye fields
are named `left_eye_open`/`right_eye_open`, so their bit polarity remains the
opposite of this raw format. That distinction is intentional and tested.

## Provisional output

`mouse/output.py:mouse_message()` produces a lab-only envelope:

```json
{
  "format": "mouse_preview_v0",
  "mode": "mouse",
  "sequence": 43,
  "timestamp_ms": 1050.0,
  "source": {
    "session_id": "detector-run-1",
    "sequence": 12,
    "timestamp_ms": 1000.0,
    "subject_id": "selected-person"
  },
  "enabled": true,
  "buttons": {"left": 0, "right": 0},
  "velocity": {"x": 0.5, "y": 0.5, "scroll": 0.5}
}
```

This represents full current state. Buttons are 0/1 states; the emulator should
derive down/up transitions. Each eye can hold its button independently. Axes are
normalized velocity demands: `signed_velocity = 2 * normalized_value - 1`.
Neutral is `0.5`, not zero. Pointer speed and scroll speed in physical units belong
to the eventual driver profile; the lab's pixels-per-second values affect only
the simulated desktop.

**This is not ControlFrame v1.** That provisional shared contract specified one
output per input and preserved its sequence. Interpolation now needs an independent
output sequence/time at 100 Hz, plus source capture metadata for freshness checks.
The shared contract should be revised deliberately once the emulator requirements
are known. No driver implementation has been added or modified here.

## Decisions for the emulator teammate

- Does the emulator want normalized velocity, signed velocity, or integer movement
  deltas per update? Retain signed velocity internally; adapt only at the boundary.
- What update cadence and local interface will it accept: direct calls or a queue?
  The native lab uses in-process Python calls and has no web/network dependency.
- What are the maximum pointer speed and scroll units? Which sign scrolls up on
  its OS API? How should subpixel and fractional scroll remainders accumulate?
- Will the driver consume held button state and derive transitions, or explicit
  press/release events? Do not repeatedly click for every sample with value 1.
- What watchdog, disconnect/release-all, and explicit enable behavior does it need?
  Driver-side timeout handling is still necessary if the processing process dies.

The MVP includes vertical wheel scrolling, not a middle-button gesture. Clicking,
scrolling, and pointer motion can run concurrently. No keyboard/gamepad mapping is
included. The next integration step is an agreed output adapter and mock-to-driver
test before live detector-to-mouse testing.
