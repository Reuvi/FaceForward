# Shared contracts — initial v1

These language-neutral messages are the starting agreement for independent work.
The integration owner serializes changes here. The examples are synthetic data,
not recordings, and are not a functioning pipeline or complete validation suite.
Choose an implementation language and transport separately; ordinary objects,
JSON, or newline-delimited JSON can represent the same semantics.

The native Vision + Processing mouse lab now adopts the in-process interfaces in
[`MOUSE_MVP.md`](MOUSE_MVP.md). It consumes SignalFrame v1 and uses the separately
named `mouse_preview_v0` output with its own sampling clock. ControlFrame v1 below
remains a driver draft until the emulator teammate agrees on the adapter.

## Common rules

- `schema_version` is integer `1`. Required keys must exist; consumers can ignore
  additive optional keys. Incompatible changes require a new major schema version
  and coordinated producer/consumer updates.
- Values are finite numbers in the inclusive range `[0, 1]`. Confidence is also
  `[0, 1]`; it is a detector quality score, not a probability guarantee.
- `timestamp_ms` is the monotonic capture time in milliseconds on the same host.
  App supplies a common clock/timebase to all stages. Replay rebases timestamps to
  the current clock. Wall time and cross-machine clocks are not valid substitutes.
- `session_id` changes on stream restart. `sequence` is a nonnegative integer,
  strictly increasing within a session (gaps are allowed). Processing preserves
  capture timestamp/session/sequence so Drivers can reject old work. For the MVP,
  emit at most one ControlFrame per input SignalFrame.
- Consumers reject future/expired timestamps and ignore already-seen or older
  sequence numbers. Ignored duplicates do not refresh a watchdog. A new session
  first disables output, clears state, and requires explicit re-arming.
- Initial configurable maximum age is **250 ms**, a development default to tune
  from measurements. Both Processing and Drivers gate stale data. A driver timer
  also disables output when no fresh frames arrive; it cannot depend on callbacks.

## Vision → Processing: SignalFrame

See [`examples/signal-frame.json`](examples/signal-frame.json).

| Field | Meaning |
| --- | --- |
| `schema_version`, `session_id`, `sequence`, `timestamp_ms` | Common envelope above |
| `faces` | Array of 0–2 face observations |
| `faces[].subject_id` | Unique, stable tracker ID within the session; not a verified identity |
| `faces[].signals` | All eight named measurements listed below |

Every measurement is `{ "value": number-or-null, "confidence": number, "valid": boolean }`.
`valid: true` requires a finite `[0, 1]` value. An unavailable/invalid measurement
uses `value: null`, `confidence: 0`, `valid: false`. Never substitute `0` for
missing measurements: zero is a real extreme/closed state.

| Signal | 0 | 0.5 | 1 |
| --- | --- | --- | --- |
| `gaze_x` | User's left | Calibrated center | User's right |
| `gaze_y` | Up | Calibrated center | Down |
| `tongue_x` | User's left mouth boundary | Mouth center | User's right boundary |
| `tongue_y` | Upper mouth boundary | Mouth center | Lower mouth boundary |
| `left_eye_open` | Closed | Intermediate openness | Open |
| `right_eye_open` | Closed | Intermediate openness | Open |
| `head_x` | Comfortable left limit | Neutral head position | Comfortable right limit |
| `head_y` | Comfortable up limit | Neutral head position | Comfortable down limit |

Left/right refers to the user's perspective and anatomical eye, independent of
preview mirroring. Normalize positional signals using that user's calibrated
reference/range. Uncalibrated positional signals are invalid for control. Store
raw landmarks/angles as optional diagnostics, with explicit units if introduced.

App selects a `subject_id` and loaded profile explicitly and passes that context
to Processing. A tracker ID alone must not load a person's saved profile or
silently transfer control. Missing selected subject means disabled output even
when another face remains visible. Reacquisition/selection must be deliberate.

## Processing → Drivers: ControlFrame

See [`examples/control-frame.json`](examples/control-frame.json).

| Field | Meaning |
| --- | --- |
| Common envelope | Preserved from the source SignalFrame |
| `subject_id` | Selected subject ID, or null when none is selected |
| `enabled` | Whether this frame may drive output; driver also requires local arming |
| `buttons` | Full state for `left_click`, `right_click`, `delete`, `insert`, `speech_to_text` |
| `axes` | Full state for `pointer_x`, `pointer_y`, `scroll_y` |

Processing emits button values `0` or `1` after dwell/debounce. The driver's manual
test input also accepts intermediate values; its initial down threshold is `>= 0.5`.
Keep that adapter threshold separate from per-person gesture thresholds.

Left/right mouse buttons transition down once, remain held, and transition up once.
Delete, Insert, and speech-to-text are one-shot actions on the rising edge; held
state does not repeat them. Delete/Insert use a complete key press and release.
Speech starts an injected speech flow; text transcription/insertion is a separate
implementation decision. Mouse dragging can later reuse held state.

Axes represent velocity demand, not screen coordinates: `2 * value - 1` gives
signed normalized velocity. Neutral is `0.5`. Negative pointer X/Y moves left/up;
negative scroll Y means up. Drivers translate these conventions to their OS API
and integrate velocity over elapsed time so sample rate does not set movement speed.
Profile dead zones and response curves are applied in Processing; Drivers apply
platform-specific maximum speeds and event quantization.

When disabled, use all buttons `0` and all axes `0.5`. Drivers release held input
and stop motion regardless of other values in a disabled frame. On malformed data,
expired input, missing selected subject, stop, or disconnect, disable/release and
require deliberate re-arming. A first enabled frame after arming must be neutral;
ignore activation until controls have returned to neutral to prevent surprise presses.

For a configured output whose required signal is invalid, neutralize that output
and release any held state. If the selected face, profile, or entire stream is
invalid, disable all output. Never reuse a last active sample indefinitely.

## Public component boundaries

- Vision: configurable capture/replay source producing SignalFrame; calibration
  routines and optional overlay data. It does not own persistence or device mappings.
- Processing: SignalFrame + selected subject/profile + clock → ControlFrame;
  profile loading/saving, mappings, and diagnostic views.
- Drivers: ControlFrame + clock + explicit local arm/disarm → adapter output;
  logging adapter, independent watchdog, and release-all/close lifecycle.
- App: owns composition and lifecycle. Concrete function names and shared profile
  or overlay schemas must be agreed by integration before cross-lane imports.

Future gamepad controls should extend/version the contract deliberately. Do not
reuse pointer-axis keys with different meanings in another lane.

The additive [local detection research interface](RESEARCH_LAB.md) defines selected-face scalar features, experimental ordered preview events and profile v2. It preserves the original SignalFrame and mouse-preview contracts.
