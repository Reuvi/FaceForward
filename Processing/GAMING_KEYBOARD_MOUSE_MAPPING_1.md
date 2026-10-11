# gaming keyboard mouse mapping 1

Status: original design record; the Processing middle phase is now implemented.
Use [the implementation runbook](mappings/README.md) and
[adopted contract](../Contracts/GAMING_MAPPING.md) for current behavior. Current
pupils use personal endpoints and head-angle compensation; older fixed-pupil
assumptions below are superseded by PUPIL_HEAD_CALIBRATION.md. Native driver
injection remains pending. The original plan was requested by Reuvi on
2026-10-10. Processing lane; branch `work/reuvi/processing/gaming-mapping-plan`.
Base: `63fb5d3590d040bb82be7b9962c225c26405adbd`.

Fetched `origin` and reviewed the latest `origin/driverTest` at
`2e3e7349652af1eca2869ffd932738bde92133f9`, including its
[connection notes](https://github.com/app0cal/hackathon26/blob/2e3e7349652af1eca2869ffd932738bde92133f9/docs/connecting.md),
[driver guide](https://github.com/app0cal/hackathon26/blob/2e3e7349652af1eca2869ffd932738bde92133f9/Drivers/readme.MD),
public C header, control loop, macOS backend and interface requests. The branch
was inspected and built separately; it was not merged into main or this plan's
branch. The concurrent pupil-detection work is a dependency, not part of this task.

## Mapping and behavior

Use stable ID `gaming-keyboard-mouse-1`, display name exactly
**gaming keyboard mouse mapping 1**, and initial mapping revision `1`.

| Input, from the user's anatomical perspective | Readable instruction | Output |
| --- | --- | --- |
| Left eye's recognized closed action | Hold left mouse button | Left button down; release on OFF/unknown |
| Right eye's recognized closed action | Hold right mouse button | Right button down; release on OFF/unknown |
| Head down, positive pitch position | Hold W | `w` |
| Head up, negative pitch position | Hold Space | `space` |
| Head left, negative yaw position | Hold left Shift | `left_shift` |
| Head right, positive yaw position | Hold S | `s` |
| Pupils away from center | Move pointer in that direction | Continuous X/Y velocity; farther means faster |

Pupil velocity and held buttons/keys are provisional interaction choices, pending
the user's optional clarification. They fit the current pupil-direction data and
existing Processing button semantics. Absolute screen positioning would require
a separate screen-gaze design; direct iris direction is not a screen coordinate.
Tap behavior, if requested, must be explicit per binding, never an accidental
effect of the present driver's mouse implementation.

Pitch and yaw are independent: down+left produces W+Shift; up+right produces
Space+S. Opposite directions on the same axis are mutually exclusive. Eyes remain
independent of each other and of head controls. This preset leaves A, D, scroll,
Delete, Insert and speech inactive. The existing mouse/scroll preset remains
available separately; selecting this mapping must not silently alter that preset.

## Responsibilities and reusable mappings

```text
Vision: timestamped measurements, validity, calibrated eye intent and head axes
   → Processing: quality gates → noise filters → activation rules → action state
   → Python driver adapter: validate provenance/lifecycle → matching C ABI
   → Drivers: held-state transitions + velocity integration → OS events
```

The "signal section" is Processing. Its output should say which keys/buttons are
held and the pointer's direction/strength, rather than exposing driver bitmasks
to the user. Vision continues to report what it observed, independent of mappings.

Store named mappings separately from detector calibration. A small versioned
mapping registry should support create/copy/rename/select, with explicit bindings
and validated settings. A single active mapping owns output; loading/switching or
editing it releases all output, clears filter/latch state, and requires Start again.
Changing a label alone need not retrain detectors. Never persist armed state.

First storage proposal: a separate `input_mapping_v1` file holding ID, revision,
bindings and Processing response settings. Existing `face_mouse_profile_v3` is
strictly validated and accepts only MouseConfig today; do not insert new keys into
it. Bundling multiple mappings with a face profile needs a coordinated format
revision and migration later. Detector preset v11 and the pupil algorithm identity
remain independent. Preserve source-kind separation for personal/synthetic fits.

Implement this as a small typed gaming configuration/processor alongside the
existing mouse mode, sharing proven input validation, eye gates and pointer math
through explicit Processing interfaces. Avoid a generic scripting engine.
`MouseConfig.mode` currently accepts only `mouse`; `Sample` decodes head Y into
`scroll` and drops head X. The new path must carry independently valid `head_x`
and `head_y`, not reuse an already filtered scroll velocity as head position.
Keep legacy mocks/replays and `mouse_preview_v0` usable.

## Signal processing and initial tuning

These are proposed development starting values, not measured human thresholds.
Tune with the user's live neutral/movement traces after pupils are ready. Controls
belong under mapping response settings, not Vision's fixed pupil detector settings.
Apply confidence/validity and original capture freshness before any filtering.
Never let gain or smoothing make an unknown measurement valid.

### Head directions to keys

Consume calibrated head positions: left/up=0, neutral=.5, right/down=1.
Raw pitch/yaw degrees remain diagnostic. With center .5, signed displacement is
`d = 2*p - 1`; personal range fitting already supplies the useful amplification.
Keep separate filters/state for X and Y, with optional per-direction thresholds.

| Setting | Proposed starting value | Effect |
| --- | --- | --- |
| Minimum measurement confidence | .5 | Match the current Processing quality gate initially |
| Input smoothing | 40 ms exponential time constant | Reduce small capture-to-capture jitter |
| Direction activation | Signed displacement magnitude >= .30 | About 30% of neutral-to-comfortable-limit movement |
| Direction release | Same-direction displacement <= .18 | Separate release boundary prevents chatter |
| Activation confirmation | 50 ms of fresh qualifying captures | Reject an isolated head spike |
| Release confirmation | 0 ms | Release on the first qualifying return capture |

At the default center, W activates at filtered `head_y >= .65`, Space at
`head_y <= .35`, Shift at `head_x <= .35`, and S at `head_x >= .65`.
W/S release at `p <= .59`; Space/Shift release at `p >= .41` on their own axes.
These are normalized personal-range positions, not degrees or raw facial ratios.

Use `alpha = 1-exp(-capture_dt_ms/40)` for smoothing. Seed from fresh neutral
after arming or invalid input; no old history crosses an unknown interval.
The 50 ms confirmation starts on the first filtered threshold crossing and needs
a later distinct capture at/after 50 ms, with intervening captures qualifying.
Falling below activation before qualification cancels the candidate. New sequences
at equal timestamps can replace evidence but add no elapsed confirmation time.
Output ticks, interpolation and repeated source samples cannot qualify a key.

Once active, apply the lower release threshold without another dwell. A reversal
releases the old key first, then independently qualifies the new direction; it
never presses both opposing keys. Invalid/stale input bypasses smoothing and
immediately releases that axis's two keys. After channel loss, require a fresh
neutral sample (`abs(d) <= .18`) before that axis can activate again. Whole-face
or stream loss requires explicit re-arming of the entire mapping.

Keep amplification after the noise boundary: for binary keys, threshold crossing
already converts deliberate movement to full 0/1 action. Lower a direction's
threshold deliberately if movement is limited; do not multiply noisy raw head
values before the dead zone or amplify a key beyond 1.

### Pupils to pointer movement

Use precise `gaze_x/y`, never the quantized 11×11 display matrix. Require both
coordinates valid and fresh. Keep detector normalization unchanged, including any
new identity/validity behavior agreed with the agent finishing raw pupil detection.

Start with the existing radial response: signed X/Y offsets around .5;
start moving at radius > .19, stop targeting motion at radius <= .16, exponent
1.6, interpolation 50 ms, output smoothing 90 ms, acceleration 5 and deceleration
8 signed normalized velocity units/s. Disable jump boost initially (`boost_gain=0`)
so isolated changes are not amplified. These inherited latency settings are a
baseline to measure and reduce for gaming, not a claim of low end-to-end latency.

For active radius `r`, the response strength is
`min(1, gain * ((min(r,1)-.16)/(1-.16))**1.6)`, initially gain=1.
Scale the unit direction by that strength, smooth/rate-limit, then encode each
signed velocity `v` as `(v+1)/2`. Cap radial strength so diagonals are no faster.
Future gain adjustments act after the dead zone. At rest, sub-threshold jitter
cannot start motion; after deliberate movement, normal centering has a bounded
deceleration tail that must be measured. Invalid input and Stop bypass that tail.

Drivers should use neutral=.5, dead_zone=0, inversion=false, equal X/Y maximum
speeds (initially its existing 600 units/s). Processing owns dead zones, curves and
orientation; Drivers own elapsed-time integration and fractional OS units. The
driver's default extra .05 dead zone would otherwise suppress already shaped
small commands. Driver units are OS-dependent, not guaranteed physical pixels.

Current pupils require both usable eyes: an eye closure can stop pointer movement
while its click remains active. Aim-then-click is possible; moving/dragging while
an eye stays closed is not guaranteed. Preserve this visible limitation rather
than inventing single-eye input or reusing stale pupil coordinates. On valid pupil
recovery within a still-active session, accept only new evidence, reset motion
history and resume normal filtering; face/stream loss still requires Start.

### Eyes to mouse buttons

Use each fresh `eye_intent_v1` sample under the existing
[eye contract](../Contracts/EYE_INTENT.md): recognized closed geometry plus that
eye's learned action appearance. Partial/uncertain closure must not become a click
merely because its numeric value moved. The trained geometry/appearance boundaries
provide the eye threshold; binary intent has no meaningful continuous gain.

After a fresh open baseline, known ON means down, known OFF means up, and unknown
means immediate up and require actual reopening before the next activation.
Do not add eye dwell, release debounce, smoothing, an opposite-eye veto or a pupil
validity gate. Unknown Processing eye numbers may hold history with `known=false`;
they are never button evidence. Legacy raw/replay timing stays confined to its
existing compatibility path; missing camera intent cannot silently select it.

The current classifier does not guarantee natural-blink rejection: a matching
blink may activate. This is a detector limitation to measure, not something this
plan silently changes through a duration threshold.

## Readable signal panel

Add a native Processing view with one row per binding, plus two pointer axes:
input value/known status, filtered value, start/release boundaries, readiness,
current instruction, and output state. Example messages:

- `Head down .72 → W held`
- `Head left .48 → neutral; Shift released`
- `Pupils → right 24%, up 8%`
- `Left eye unknown → left button released; waiting for reopen`

Show the active mapping name and separate Preview/Driver status. Use explicit
"unknown", "below threshold", "waiting for neutral", "confirming movement" and
"held" labels so a stopped output has an explanation. Raw, filtered and command
plots use the same source provenance; dark graph holds stay presentation-only.
Keep a bounded timestamped transition log/CSV for tuning; no camera images or
personal recordings in Git. Event logs show what was requested/emitted, not proof
that the game accepted it.

## Driver connection findings and required changes

ABI v3 already supports held W/A/S/D/Space/left Shift through `keys_down`.
This mapping uses W=1, S=4, Space=16, Shift=32; W+Shift is mask 33. Repeated
complete snapshots produce no repeated key-downs. Both pointer velocity and
explicit target mode exist; choose `FID_POINTER_VELOCITY` for this plan.

Three integration issues must be resolved before calling the mapping complete:

1. **Mouse state mismatch.** `left_click/right_click` currently produce a complete
   tap after >.7 for 150 ms, rearmed below .3. There is no held-mouse field or
   mouse-down/up event. Setting dwell=0 removes delay but still cannot hold/drag.
   Request explicit held-mouse support, capability reporting and compatible ABI
   versioning from Drivers. Preserve existing tap examples as a separate mode.
2. **Envelope and watchdog mismatch.** `fid_frame` carries no capture timestamp,
   sequence, subject, validity or enabled flag. A Python adapter must validate the
   full command envelope and pause on disabled/lost/stale/malformed input or any
   C API error. The driver rejects malformed frames but may keep its previous
   valid command until timeout; rejection alone is not an immediate stop.
3. **Independent output timing.** Processing emits at 100 Hz while the driver
   recommends a 30–60 Hz producer and runs a 60 Hz worker. Preserve source capture
   age even when output is resampled. Use latest motion, but preserve accepted
   button transitions: the current latest-frame worker can lose an ON/OFF pair
   between ticks. The new held-mouse path must deliver transitions in order without
   adding a minimum wink duration or stretching unknown input into a hold.

The companion [interface proposal](interface-requests/gaming-keyboard-mouse-1.md)
defines the proposed envelope, driver lifecycle and ownership. Adopt it through
integration before dependent cross-lane implementation. Do not relabel current
`mouse_preview_v0` as the draft `ControlFrame v1`.

The driver's connection notes also propose a background service that outlives its
UI. That is a separate runtime feature, not necessary for this mapping. Keep the
current App close/Stop behavior releasing output; do not install a service here.

## Implementation sequence and completion evidence

| Order | Owner and deliverable | Evidence needed |
| --- | --- | --- |
| 1 | Integration adopts output/timing/held-key contract; Drivers agrees held-mouse ABI | Reviewed examples and compatibility rules |
| 2 | Processing adds named preset, head X/Y decoding, independent head gates and action snapshots | Synthetic threshold, combination and validity tests |
| 3 | Processing adds readable preview/settings and separate mapping persistence | Save/copy/switch round trips; selection releases all state |
| 4 | Drivers adds held-mouse transitions and public Python binding; App wires dry-run | End-to-end synthetic trace agrees with driver event journal |
| 5 | App uses the finalized pupil source; tune neutral noise and comfortable ranges | Actual capture rate, false activations, response/release latency |
| 6 | Explicit native driver session on target OS/game | Key/button holds, direction, stop/loss, modifier and pointer-lock checks |

Implement step 2 against an agreed mock sink while Drivers completes step 4;
existing mouse-only behavior remains regression coverage. Future file locations:
`Processing/mappings/` for config/registry/gates/serialization, `tests/processing/`
for deterministic fixtures, `Drivers/` for public binding/ABI/backend work and
`App/` for lifecycle/selection. Share existing eye/filter logic rather than forking
its semantics. Any shared extraction requires focused regressions.

Acceptance cases must include:

- No action from steady neutral noise; exact activation/release boundaries;
  isolated head spike rejected; threshold jitter does not chatter; 10/30/60 Hz
  capture streams use elapsed time, not counts; equal timestamps add no dwell.
- All seven requested bindings; W+Shift and Space+S; independent eyes including
  both ON; rapid direction reversal with release before the other key; no scroll.
- Known eye ON/OFF preserved even between driver ticks; unknown releases without
  delay; unknown numeric holds never trigger; fresh reopening required.
- Each missing head axis releases only its own pair; pupil loss stops motion;
  camera eye closure can invalidate pupils without vetoing clicks/head keys.
- Whole-face/stream loss, stale/future frames, malformed envelopes, duplicate and
  regressing source/output sequences, output stalls, source restart, settings or
  mapping changes, Stop and close all obey release/disarm/re-arm rules.
- Repeated output ticks with old source timestamps cannot keep control fresh;
  bridge error calls pause immediately; no frame backlog replays after a stall.
- Full key snapshots release omitted keys; no repeat downs; finite bounded axes;
  gain cannot defeat dead zones; equal diagonal speed; driver shaping applied once.
- Profile/mapping schema rejects unknown or nonfinite settings; old face profiles
  retain compatible detector fits and old mouse behavior; no tongue restoration.

Measure neutral false actions, intended misses, time from original capture to
command/driver transition, and pointer settling at each setting. Software tests
and native compilation are not evidence of facial accuracy or game compatibility.

See [the task handoff](GAMING_MAPPING_PLAN_HANDOFF.md) for checks actually run.
