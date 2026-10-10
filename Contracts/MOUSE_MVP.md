# Mouse lab integration, October 2026

Status: implemented for **native Vision → Processing → simulated mouse**.
This adopts the local Python handoff requested by the team. SignalFrame v1 is
unchanged. The earlier ControlFrame v1 remains a driver draft; the lab's separately
named `mouse_preview_v0` is not silently presented as that driver format.

## Accepted input and lifecycle

- App imports Vision's `mouse_demo_records`, `replay`, `read_ndjson`,
  `OpenCVCamera`, `MediaPipeDetector`, and `VisionPipeline`. These are the adopted
  native producer interfaces; construction/import does not open hardware.
- All components use the same host's monotonic milliseconds. Capture time is
  preserved through inference/handoff. Replay rebases session time deliberately.
- App calls `Lab.ingest(frame)` in `external` mode, directly and synchronously.
  The separate Lab worker calls `tick` at a target of 100 Hz even without input.
- Sequences strictly increase within a session; capture timestamps are
  **nondecreasing**. A newer sample with the same timestamp replaces that axis
  interpolation point and advances no eye dwell time. Duplicate sequences or
  regressing capture times are rejected without refreshing freshness.
- Processing selects the exact subject. The named demo fixture is selected by
  default; replay/camera require explicit selection. Loss/restart disables output
  and never auto-binds another face. Changing selection resets/disarms filters.
- EOF, errors, explicit source stop, and application shutdown call
  `Lab.disconnect(reason)` immediately. Timeouts independently disable output.
  Re-enabling requires explicit Start preview and fresh neutral axes; each eye
  needs its own open baseline.
- Live Vision has no validated calibration collector, head detector, or tongue
  detector yet. Those measurements remain invalid. Raw geometry is diagnostic.

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
