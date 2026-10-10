# Mouse MVP engineering guide

This describes the implementation integrated on October 10, 2026, at runtime
baseline `481fd34` (integration code in `8e9eaa6`). It explains what the application
does today. Future features are identified explicitly. Use the
[testing guide](TESTING_GUIDE.md) alongside the app and the
[coordination hub](COORDINATION.md) when assigning or handing off work.

For the current detector-by-detector ML status and how to inspect raw camera
signals before mouse mapping, see [RAW_DETECTION_GUIDE.md](RAW_DETECTION_GUIDE.md).

## 1. Scope and current capabilities

The application runs locally in Python with a native Tk window. The four controls
are **left button, right button, vertical scroll, and relative pointer movement**.
“Middle mouse” currently means the scroll wheel, not a middle-button press.
Keyboard, speech-to-text, gamepad, background service installation, and the full
personal setup wizard remain future work.

| Layer | Engineered and available | Still needed |
| --- | --- | --- |
| Vision | Synthetic/replay sources, camera capture, local face landmarks, up to two tracked faces, anatomical eye/iris geometry, overlay, calibration primitives, SignalFrame output | Live calibration collection and validated measurement quality; calibrated head movement; actual tongue detector |
| Processing | Both input adapters, independent eye timers, interpolation, dead zones, response curves, smoothing, acceleration limits, decaying jump boost, freshness checks, configurable settings | Tuning against real users and detector noise; agreed emulator serialization |
| Native lab | Combined source controls, explicit subject selection, raw diagnostics, five processing scopes, simulated desktop, settings import/export, trace CSV | Full user setup flow and real device feedback |
| Drivers connection | A named provisional output object and documented integration boundary | Connection to the teammate's emulator, final units/transport, actual OS input tests |

The complete four-action pipeline works with **synthetic input**. The integrated
camera path currently emits invalid control measurements while exposing real
landmarks and raw eye ratios. Seeing an overlay does not mean a live click or
tongue signal is available. No actual OS mouse events are emitted by this app.

## 2. Architecture and ownership

```text
Vision worker: demo / NDJSON replay / explicit camera + model
    │ SignalFrame v1; optional raw observations + latest preview image
    ▼
App.MouseSession.deliver(frame)
    │ direct Python call, common monotonic clock
    ▼
Lab.ingest(frame) → MouseProcessor.accept(frame, receipt_time)
    │ decoded samples, per-eye state, bounded axis history
    ▼
Lab's independent 100 Hz worker → MouseProcessor.tick(now)
    │ normalized mouse state + diagnostic trace rows
    ├─ mouse_message(snapshot) → mouse_preview_v0 (provisional)
    └─ Tk main thread → scopes + simulated pointer / scroll / press counters

Future: agreed output adapter → teammate's hardware/OS emulator
```

| Responsibility | Main code |
| --- | --- |
| Launch options and headless smoke run | [App/__main__.py](../App/__main__.py) |
| Source lifecycle, selection, clock, diagnostics | [App/mouse_runtime.py](../App/mouse_runtime.py) |
| Integrated native source/raw view | [App/desktop.py](../App/desktop.py) |
| Synthetic mouse exercise | [Vision/mouse_demo.py](../Vision/mouse_demo.py) |
| Capture, landmarks, calibrated measurements, tracking | [Vision API map](../Vision/README.md#vision-local-apis) |
| Input format decoding and channel validity | [signals.py](../Processing/mouse/signals.py) |
| Pure processing state machines and filters | [engine.py](../Processing/mouse/engine.py) |
| Immutable settings and validation | [config.py](../Processing/mouse/config.py) |
| Processing thread, lock, settings, trace buffer | [controller.py](../Processing/mouse/controller.py) |
| Manual mocks, native playground, scopes | [mocks.py](../Processing/mouse/mocks.py), [desktop.py](../Processing/mouse/desktop.py) |
| Provisional output serialization | [output.py](../Processing/mouse/output.py) |

Vision measures; Processing maps measurements into actions; Drivers will translate
actions into device events. App owns composition and lifecycle. Components use
adopted public interfaces, not another lane's private implementation. See
[MOUSE_MVP.md](../Contracts/MOUSE_MVP.md) for the current shared agreement.

There is one producer thread, one Processing thread, and Tk's main thread. The
producer delivers dictionaries synchronously; there is no network transport,
JSON serialization in the hot path, or growing frame queue. The session lock is
acquired before the lab lock. Tk consumes snapshots; inference never runs inside
a Tk drawing callback. Only the latest preview image is retained.

## 3. Signal formats: three different meanings of “raw”

### Vision's SignalFrame v1

Each frame has `schema_version: 1`, `session_id`, increasing `sequence`, monotonic
capture `timestamp_ms`, and `faces` containing zero to two observations. Each face
has a stable session-local `subject_id` and eight `signals`:

| Measurement | Mouse use | Meaning |
| --- | --- | --- |
| `left_eye_open` | Left button | **0 = closed, 1 = open** |
| `right_eye_open` | Right button | **0 = closed, 1 = open** |
| `tongue_x`, `tongue_y` | Default pointer source | Continuous mouth-relative X/Y in `[0,1]` |
| `gaze_x`, `gaze_y` | Explicit alternative pointer source | Continuous calibrated X/Y in `[0,1]` |
| `head_y` | Vertical scroll | 0 = comfortable up limit, 0.5 = neutral, 1 = down limit |
| `head_x` | Unused in mouse MVP | Retained in the Vision contract |

Each measurement is `{ "value": 0.5, "confidence": 1.0, "valid": true }`, for
example. Missing/unsupported data is `{ "value": null, "confidence": 0,
"valid": false }`. Confidence must meet Processing's configured minimum.
Both X and Y must be usable for a 2D pointer sample. Tongue never silently falls
back to gaze. Left/right denotes the person's anatomical perspective, independent
of display mirroring.

The general v1 contract permits intermediate eye openness. **This mouse adapter
requires binary 0/1 eye classifications**; an intermediate value is unavailable
to its eye gate. Vision's implemented calibrated eye classifier produces binary
values. Processing must not guess an eye threshold from a fractional value.

See the [full envelope](../Contracts/README.md) and
[synthetic example](../Contracts/examples/signal-frame.json). App preserves
continuous positions; it does not turn them into one-hot arrays.

### Processing's `raw_mouse_v1` mock format

This separately named format implements the team's matrix/vector idea:

- `left_eye` and `right_eye`: separate bits, **1 = closed by default**. Only this
  format uses configurable `closed_value` polarity.
- `tongue` or `gaze`: a rectangular matrix, exactly one numeric 1, all others 0.
- `head_vertical`: a one-hot vector; flat, single-row, or single-column forms work.
- `session_id`, `sequence`, `timestamp_ms`, and the exact selected `subject_id`.

For vector index `i` of length `N`, position is `i / (N - 1)`. Matrix column maps
to X and row to Y: top-left `(0,0)`, bottom-right `(1,1)`. A center cell in a 9×9
matrix is `(0.5,0.5)`; the next column to its right is X `0.625`.

Adapters allow 2–256 elements per dimension. The manual UI limits dimensions to
odd values 3–31 so there is an exact center. Ragged arrays, multiple/no active
cells, nonfinite values, and heatmaps are unavailable channels. This format has
no confidence field. See the [raw format proposal/example](../Processing/interface-requests/mouse-prototype.md).

### Camera geometry diagnostics

The camera side channel contains eye openness and iris horizontal/vertical ratios,
an image-plane head reference, and a bounding box. Eye ratios are dimensionless
geometry, **not** normalized mouse inputs or confidence scores. Head-reference
origin/width are pixels; its axes are image-plane directions, not pitch/yaw.
The tracker box is image-normalized. These values can be visible while all control
measurements are unavailable. They never bypass calibration/validity checks.

### How the current Vision implementation obtains those measurements

[capture.py](../Vision/capture.py) requests a 640×480 camera image by default,
stamps it after the read, and releases the device on failure. A failed capture
terminates the source; a successful inference that sees no face emits `faces: []`.
These are different conditions. Importing a module does not open the camera.

[landmarks.py](../Vision/landmarks.py) uses the local MediaPipe model on CPU in
synchronous VIDEO mode, at most two faces and one inference in flight. It converts
OpenCV BGR to RGB. The model's private integer timestamp is made strictly
increasing, while the original floating-point capture timestamp remains intact.
A new capture session recreates the model's stream state.

Geometry uses pixel coordinates, so non-square images do not distort eye ratios.
The face mesh needs at least 468 points; iris-based eye diagnostics require 478.
Anatomical eye landmark groups are separate. Off-image/degenerate references or
an eye width below four pixels prevent the affected geometry from being used;
these checks are not a calibrated confidence estimate.

In [geometry.py](../Vision/geometry.py), the corner-to-corner eye vector defines
the right axis, its perpendicular defines down, and the midpoint is the origin.
With iris displacement `d` and eye width `w`:

- Horizontal ratio: `0.5 + dot(d, right) / w`.
- Vertical ratio: `dot(d, down) / w` (not divided by changing eyelid opening).
- Openness ratio: median of the three eyelid-pair distances, divided by `w`.

The face reference uses eye centers and a nose origin. These local frames reduce
dependence on image translation, scale, and roll; they are not a 3D pose solution.
The existing `tongue_ratios()` can transform a real centroid into mouth-relative
X/Y using mouth width and opening height. It rejects an out-of-mouth centroid.
It does not detect a tongue, and no current camera path supplies that centroid.

[calibration.py](../Vision/calibration.py) provides in-memory fitting primitives:
each target needs at least five finite observations. A median/MAD outlier rule
must retain at least five samples and 80% of the target group. Axis low/center/high
groups must have an explicitly supplied minimum separation; normalization maps
their medians to 0/0.5/1, allowing either raw orientation. Out-of-range values are
invalid unless an explicit endpoint tolerance (at most 0.1 normalized units)
permits limited clipping. Eye fitting separately checks closed/open separation,
places its threshold halfway between the retained groups' nearest boundaries,
and emits a binary classification. No click dwell occurs in Vision.

Closed or unavailable eyes contribute no gaze. With two usable eyes, gaze must
agree within an explicit tolerance per axis; accepted values are confidence-
weighted, with combined confidence equal to the lower eye confidence. Single-eye
gaze is off unless explicitly enabled. These gaze rules do not couple the two
independent click inputs.

[tracking.py](../Vision/tracking.py) associates bounding boxes through reciprocal
unique candidates, limited by center motion and scale change. Defaults are a
250 ms gap, motion up to 0.6 times the smaller box diagonal, and scale ratio up
to 1.5. Missing, overlapping/ambiguous, or expired tracks are retired. An ID is
not a biometric identity; visually similar replacements need real-world testing.
[pipeline.py](../Vision/pipeline.py) binds eye calibration to an explicit session
and subject, and clears it on loss, ambiguity, restart, or assessor failure.

The missing bridge is a live collection flow plus a validated per-eye quality
assessor and deliberate binding. App currently constructs an unbound pipeline,
so none of these primitives silently enable live controls. Processing's neutral
button is a separate operation and cannot supply this bridge.

## 4. Independent eye state machines

Each eye owns its own open timer, closure timer, dwell progress, readiness, and
held-button state. Neither gate reads the other. The user's later instruction
supersedes the earlier both-eyes suppression idea: **both long closures can hold
both buttons at once**.

1. After Start preview, an eye must establish its own continuously open baseline
   for `release_ms` (default 60 ms). Starting with an eye closed cannot click it.
2. On the first closed sample, start that eye's closure timer.
3. While closed, progress is `min(1, elapsed_closed_ms / dwell_ms)`.
4. A fresh confirming sample at or beyond `dwell_ms` (default 320 ms) sets the
   corresponding button state to 1. It stays held; it is not a click every frame.
5. Reopening resets closure progress. The button releases after continuously open
   samples span `release_ms`. Closing again before release completes resets the
   open timer and keeps the button held.
6. An invalid eye resets/releases only that eye. Whole-stream loss releases both.

Eyes are never interpolated. Timers use capture timestamps and advance only on
accepted samples. At 30 Hz, threshold confirmation has roughly 33 ms granularity,
plus scheduling latency; the first detected closed sample starts the timer. A
120 ms blink is rejected at default dwell. Increasing the output clock alone
cannot make a click qualify between camera samples.

The playground's press counter increments on a 0→1 transition. It does not prove
that a real OS click or drag was generated. The future driver must convert held
state into exactly one down event and a later up event.

## 5. Position-to-velocity processing

The tongue/gaze offset requests **velocity**, not an absolute screen location.
Holding right of center keeps moving right. Returning to center decelerates to a
stop. The same idea controls head-driven scrolling in one dimension.

For each output tick, `dt` is elapsed seconds and `now` is monotonic milliseconds.
The same `AxisFilter` implements the 2D pointer and 1D scroll:

1. **Interpolate received positions.** Evaluate at `now - interpolation_ms`
   (default 50 ms). Between two received samples use linear interpolation; beyond
   the newest sample hold its position until stale. No future prediction is used.
   This intentionally adds delay in exchange for smoother sampled positions.
2. **Recenter and orient.** For position `p` and center `c`, signed offset is
   `(p-c)/c` below center and `(p-c)/(1-c)` otherwise. Optional inversion changes
   its sign. Scroll uses `center_y`/`invert_y`; its X settings have no effect.
3. **Dead zone with hysteresis.** Let `m` be signed-offset magnitude (Euclidean
   length for pointer, absolute value for scroll). An inactive axis activates
   only when `m > deadzone + hysteresis`. Once active it stays active while
   `m > deadzone`. This avoids repeated toggling at the boundary.
4. **Response curve.** Active strength is
   `((min(m, 1) - deadzone) / (1 - deadzone)) ** exponent`. Direction is the signed
   vector divided by `m`. Radial magnitude limiting avoids faster diagonals.
5. **Jump boost.** At each distinct-timestamp input, compare consecutive centered
   positions. If their distance reaches `jump_threshold` and the new position is
   outside the dead zone, update boost to the larger of its current value and
   `min(boost_max, jump_distance / sample_dt_seconds * boost_gain)`. Neutral
   input clears boost. Each output tick multiplies it by
   `exp(-dt * 1000 / boost_decay_ms)`. Target strength becomes
   `min(1, strength * (1 + boost))`. It is a bounded speed multiplier, not an
   unbounded acceleration impulse; an offset retains base velocity after decay.
6. **Smooth and limit acceleration.** Use
   `alpha = 1 - exp(-dt * 1000 / smoothing_ms)` and
   `desired = previous_velocity + alpha * (target - previous_velocity)`.
   Zero smoothing sets alpha to 1. Limit the vector change to `rate * dt`, using
   deceleration when desired magnitude decreases and acceleration otherwise.
   An inactive velocity smaller than `0.0001` snaps to exactly zero.
7. **Encode.** `normalized_velocity = (signed_velocity + 1) / 2`.
   **0.5 = stop**, 0 = full left/up, 1 = full right/down. Disabled output is
   immediately neutral; it does not wait for smoothing to decay.

Example: pointer position `(0.75,0.5)` with default centers becomes signed offset
`(0.5,0)`. Ignoring temporary boost and settling time, strength is
`((0.5-0.16)/(1-0.16))^1.6 ≈ 0.235`. Output X settles near `0.618`, Y at `0.5`.
At the default simulated maximum 900 px/s, that is about 212 px/s to the right.
It does not place the pointer at 75% of the screen.

## 6. Configuration reference

Exact defaults and validation live in [config.py](../Processing/mouse/config.py).
[example-profile.json](../Processing/mouse/example-profile.json) contains the
complete Processing defaults. Export a full profile, edit it, and import it for
repeatable comparisons; settings are configuration, not a trained face model.

### General and eyes (`config`)

| Key | Default | Accepted range / meaning |
| --- | --- | --- |
| `mode` | `mouse` | Only implemented mode |
| `pointer_source` | `tongue` | `tongue` or explicit `gaze` |
| `closed_value` | `1` | Integer 0 or 1; raw mock format only |
| `left_eye.dwell_ms`, `right_eye.dwell_ms` | 320 each | 50–3000 ms; independently configurable |
| `left_eye.release_ms`, `right_eye.release_ms` | 60 each | 0–500 ms; open baseline and release debounce |
| `interpolation_ms` | 50 | 0–250 ms; must be less than `stale_ms` |
| `stale_ms` | 250 | 80–2000 ms; capture, receipt, and output-gap checks |
| `min_confidence` | 0.5 | 0–1; SignalFrame measurement gate |

### Axis settings (`config.pointer` and `config.scroll`)

| Key | Pointer default | Scroll default | Accepted range / effect |
| --- | --- | --- | --- |
| `deadzone` | 0.16 | 0.22 | 0–0.8; centered signed magnitude |
| `hysteresis` | 0.03 | 0.03 | 0–0.15; extra magnitude to activate |
| `exponent` | 1.6 | 1.8 | 0.2–5; larger softens motion near center |
| `smoothing_ms` | 90 | 90 | 0–1000 ms; response time constant |
| `acceleration` | 5 | 5 | 0.1–100 normalized velocity units/s |
| `deceleration` | 8 | 8 | 0.1–100 normalized velocity units/s |
| `jump_threshold` | 0.25 | 0.25 | 0–2; distance between centered input samples |
| `boost_gain` | 0.04 | 0.04 | 0–1; jump-speed multiplier; 0 disables boost |
| `boost_max` | 0.5 | 0.5 | 0–3; maximum boost contribution |
| `boost_decay_ms` | 350 | 350 | 1–2000 ms; exponential time constant |
| `center_x`, `center_y` | 0.5 each | 0.5 each | 0.05–0.95; normalized neutral reference |
| `invert_x`, `invert_y` | false | false | Boolean; scroll uses only Y |

### Lab settings (`runtime`)

| Key | Default | Accepted range / effect |
| --- | --- | --- |
| `sample_hz` | 30 | 5–120 Hz; standalone mock source only |
| `rows`, `columns` | 9, 9 | Odd integers 3–31; mock matrix resolution |
| `vector_size` | 11 | Odd integer 3–31; mock head resolution |
| `pointer_speed` | 900 | 50–2500 simulated pixels/s at full demand |
| `scroll_speed` | 450 | 20–1500 simulated pixels/s at full demand |
| `source` | `mock` in standalone | `mock` or `external`; App locks to external |
| `subject_id` | `mock-person` in standalone | Nonempty string, at most 128 characters; App owns selection |

App's source FPS defaults to 30 and accepts 1–120; it takes effect on source
restart. It does not change Processing's output rate. Very low source rates can
exceed the default 250 ms timeout. Choose a freshness budget consciously when
testing them; increasing that budget also delays stale-input shutdown.

Applying/importing settings replaces the processor, clears trace/filter history,
and stops preview. Start again with neutral inputs. JSON numbers must be finite,
unknown keys are rejected, and inversion flags must be booleans. The desktop
exports `{config, runtime}`; the core profile may also be a bare config object.
`App --config` loads **Processing config only** and keeps App's input ownership;
it does not load exported lab speed/source settings. UI imports can apply runtime
settings, but a conflicting mock source is rejected in App.

**Calibrate current neutral** copies current valid pointer/scroll positions into
Processing center settings and resets the processor. It does not fit eye
thresholds, train a detector, establish identity, or collect a Vision calibration.

## 7. Clocks, freshness, and recovery

All stages share `time.monotonic() * 1000`. Capture time is preserved through
inference. Receipt time is recorded separately. Replay maps recorded sessions
onto new runtime sessions and the local clock, preserving intervals and gaps.

| Situation | Implemented behavior |
| --- | --- |
| Start preview | Reset filters; wait for a fresh usable signal and neutral valid axes; each eye needs its own open baseline |
| One unavailable/low-confidence eye | Reset/release that eye only |
| Missing pointer X or Y | Clear pointer motion; other controls can continue |
| Invalid head Y | Clear scroll motion; other controls can continue |
| Missing/ambiguous selected face, malformed envelope, future/expired frame | Disable all output; explicit re-arm required |
| Duplicate sequence or backwards capture time | Reject without refreshing freshness; watchdog can expire |
| New sequence at the same capture timestamp | Accept; replace axis point, no zero-time derivative, no elapsed eye dwell |
| Capture/receipt gap above timeout, or output clock gap while armed | Disable all output; do not carry dwell or motion across the gap |
| New stream session | Reset/disarm; do not inherit active gestures |
| Stop / Escape | Release/neutralize output; source diagnostics continue |
| Source EOF, error, stop, or app close | Disconnect and release/neutralize immediately, without waiting for timeout |
| Tracking returns / source restarts | No automatic resume or transfer to another person |

Invalid axes count as neutral for arming, but contribute no motion. At least one
usable axis or ready eye is needed to enable output. This allows testing one
implemented channel without inventing values for missing channels.

The watchdog runs on the independent Processing clock, even when Vision stops
delivering frames. Stop disables output before waiting for the producer to exit.
Close uses bounded thread joins; a native camera read blocked inside a backend
cannot be forcibly interrupted. Starting a second producer while one is alive
is rejected.

## 8. Diagnostics, performance, and local data

- Processing targets 100 Hz; readouts/playground update up to 20 Hz; processing
  scopes and the camera diagnostics view target 10 Hz. These are best-effort
  schedules, not hard real-time guarantees.
- The 2,000-row Processing trace holds about 20 seconds at target rate. Scopes
  display the latest eight seconds. Axis history is capped at 512 samples each.
  Raw camera scope history is separately bounded to 1,200 displayed observations.
- Blue position traces are decoded raw positions; amber traces are delayed
  positions; green traces are **velocities**. They share a normalized plot range
  but are different quantities. Eye blue is converted **closed state**, amber is
  dwell progress, and green is held-button state.
- Camera ratio plots are a diagnostic display sampled at up to 10 Hz, not a
  lossless camera-rate recorder. Their displayed range may clip a line; the
  numeric ratio remains unchanged. The raw table shows Vision validity/confidence;
  a Vision-valid measurement can still be rejected by Processing's confidence or
  binary-eye rules.
- CSV exports Processing trace rows, not camera images, raw landmark-ratio
  history, or every original detector frame. Missing values appear as blank
  fields/gaps. Source stop leaves historical evidence visible and labeled.
- Actual source Hz uses recent delivery times (up to 60). Capture timestamps are
  taken after camera `read()`, before inference; camera buffering is not measured.
  Requested FPS can differ substantially from delivered FPS.
- Prior local core benchmark: approximately 43 µs mean / 57 µs p95 over 10,000
  synthetic processing iterations. It excludes inference, drawing, scheduling,
  and drivers. See [benchmark details](../Processing/README.md#checks).

No camera frame is persisted by the integrated runtime. Environments/models stay
under ignored `.venv/` and `.local/` directories. Save personal profiles or
exports under ignored `local-profiles/` or `data/private/`; CSV files elsewhere
are not automatically ignored. Commit only deliberately synthetic fixtures.

## 9. Driver handoff still to agree

The lab serializes `mouse_preview_v0`: independent output sequence/timestamp,
source session/sequence/capture time/subject, `enabled`, button states, and
normalized X/Y/scroll velocity. The complete example is in
[MOUSE_MVP.md](../Contracts/MOUSE_MVP.md#provisional-mouse-output).

`ControlFrame v1` in the original contract is a **driver draft**, not the message
currently emitted by the lab. In particular its proposed one-output-per-input
clock differs from the implemented independent output clock. Do not relabel one
format as the other without an agreed adapter.

Before connecting the emulator, agree on velocity versus delta input, maximum
physical speeds, elapsed-time integration, fractional movement/scroll accumulation,
axis signs, down/up transitions, output transport, and an independent driver
watchdog/release-all behavior. At full stop: `enabled=false`, buttons 0, velocities
0.5. A driver should not treat normalized 0 as stopped. Keep serialization changes
at the output boundary rather than changing detector or filtering meanings.

The [testing guide](TESTING_GUIDE.md) records what has been verified and what each
next test should show. [Coordination](COORDINATION.md) lists the next independent
tasks and the evidence each agent should bring back.
