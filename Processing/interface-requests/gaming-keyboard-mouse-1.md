# Gaming keyboard/mouse command handoff proposal

Status: proposed, not adopted or emitted by current code. Processing lane,
base `63fb5d3`; reviewed Drivers ABI v3 at `driverTest` commit `2e3e734`.
User requirements and filter rules are in
[gaming keyboard mouse mapping 1](../GAMING_KEYBOARD_MOUSE_MAPPING_1.md).

## Proposed output boundary

Introduce a separately named `device_control_v1`, keeping the existing
`mouse_preview_v0` and draft ControlFrame v1 distinguishable. Integration owns
the final name/schema and must land the shared contract before implementation.
This is an independent output-clock snapshot, with complete binary mouse/key
state, normalized velocity and original source provenance. Example is synthetic:

```json
{
  "format": "device_control_v1",
  "output_session_id": "synthetic-output-1",
  "sequence": 100,
  "timestamp_ms": 1050.0,
  "source": {
    "session_id": "synthetic-camera-1",
    "sequence": 30,
    "timestamp_ms": 1033.0,
    "subject_id": "single-user"
  },
  "mapping_id": "gaming-keyboard-mouse-1",
  "mapping_revision": 1,
  "enabled": true,
  "buttons": {"left_click": 1, "right_click": 0},
  "keys": {"w": 1, "a": 0, "s": 0, "d": 0, "space": 0, "left_shift": 1},
  "pointer": {"mode": "velocity", "x": 0.5, "y": 0.5},
  "scroll_y": 0.5,
  "known": {"left_click": true, "right_click": true, "head_x": true,
            "head_y": true, "pointer": false}
}
```

This requests left mouse held and W+Shift, with stopped pointer output because
pupils are unavailable. `known=false` is not measured neutral: raw invalid values
remain null upstream; neutral/released values here are safe output commands.
The example's left closed eye can account for unavailable two-eye pupil input.

Rules:

- All axes finite [0,1], .5 stopped; mouse and key levels exactly numeric 0/1.
  Directions are user's left/up negative and right/down positive. No screen
  location interpretation; target mode requires a separate explicit extension.
- Keys follow the driver's proposed complete-state semantics: an omitted key is
  released; absent `keys` releases all. This producer sends all six keys every
  time. Reject unsupported names, booleans, nonbinary and nonfinite levels.
- Mouse buttons are held states, never dwell-qualified tap requests. Send both
  fields. Reject a driver without explicit support; do not silently emulate holds
  using repeated taps or ignore the missing feature.
- `known=false` requires the dependent output released/neutral. In this preset
  head X controls Shift/S, head Y controls W/Space, pupils control both axes and
  each eye controls its corresponding button. Future mappings derive dependencies
  from the validated mapping registry. Whole-session validity is separate.
- `enabled=false` overrides every action: release everything and call driver
  pause, rather than merely transmitting a neutral frame that leaves it armed.
- Output sequence strictly increases within a new output session. Output and
  source timestamps share host monotonic milliseconds. A source capture may be
  referenced by multiple output snapshots as filtering advances; this never
  changes its capture age. Same source sequence must retain the same provenance.
  New source sequences may have equal capture timestamps, but not regress them.
- Reject future/expired envelopes and older output/source work. Duplicate input
  does not refresh a watchdog. Create a new output session and disarm on processor
  reset, source/person/mapping change; no counters or pending actions cross it.
- Start with a 250 ms maximum capture age, independently enforced by Processing
  and the adapter. Even fresh output timestamps cannot rehabilitate old capture
  time. Keep the driver's independent receipt watchdog at 250 ms for producer
  stalls; do not claim that receipt freshness proves capture freshness.

## Driver API mapping and gaps

Use the public C API through a Drivers-owned reusable ctypes module, with the
header's exact layouts and all argument/return declarations. The current
`Drivers/examples/python_ctypes.py` is a reference/tester; promote a deliberate
public binding rather than importing CLI trial orchestration into App/Processing.
Rebuild the local library and matching binding together and validate ABI before
creating/submitting; reject stale ABI versions explicitly.

| Proposed command | Existing ABI v3 field |
| --- | --- |
| `pointer.mode=velocity` | `pointer_mode=FID_POINTER_VELOCITY` |
| `pointer.x/y` | `pointer_x/y` |
| `scroll_y` | `scroll` (always .5 in this preset) |
| Complete `keys` | OR the matching `FID_KEY_*` bits into `keys_down` |
| Held `buttons` | **No compatible v3 field**; needs driver extension |
| `enabled=false`, fault, stop/loss | `fid_pause` |
| Source metadata, `known`, mapping identity | Validate in Python; not present in `fid_frame` |

Initialize unused target coordinates to .5, target speed=0, Delete/Insert=0 and
the legacy tap fields=0 when using a future held-mouse path. Do not send NaNs or
uninitialized values in ignored fields; v3 validates those too.

Drivers change request: version explicit held-mouse levels and down/up events,
report capability and current held state, release on pause/timeout/error/close,
and emit proper drag motion where the platform requires it. Keep legacy tap
behavior distinct. The Python adapter must fail closed on capability mismatch.
Ordering must retain every accepted mouse-state transition even if ON and OFF
arrive between worker ticks; a bounded ordered transition path or synchronous
state application may implement this. Overflow is a fault that releases/disarms,
not a reason to replay a growing queue. Do not extend closed/unknown durations
just to make the worker notice an event. Specify and test this in the new API.

Keep Processing's response curve/dead zone/inversion as the sole signal shaping
stage. Configure driver axes to .5 neutral, zero dead zone, no inversion, equal
pointer speed limits. Drivers retain OS conversion, integration and fractional
residuals. Key levels use no driver dwell or repeat logic; OS/game repeat is
outside this mapping's event generation.

## Lifecycle and cadence

1. App creates the explicitly selected dry-run/native backend paused. Default
   is preview/dry-run. Processing does not acquire a camera or inject OS events.
2. Explicit Start clears old state. Require actual fresh neutral evidence for
   every available axis before enabling motion/keys, and a fresh open baseline
   independently for each eye. Unavailable channels stay unavailable/released
   and cannot later activate a head key without their own neutral baseline.
3. Call `fid_enable`; submit a completely neutral frame and retain it until
   `awaiting_neutral` clears. The driver itself checks only buttons/keys for arm,
   so Python must also enforce neutral axes. Handshake frames do not fabricate
   measurement evidence. Require at least one usable channel to start a session.
4. Sample Processing on its existing independent clock. Send latest velocity
   at 60 Hz initially and publish discrete changes promptly in order. The new
   driver transition path must preserve them. Never poll GUI redraw state as
   the control transport; avoid lock contention with Tk/inference and frame queues.
5. Check original capture age on every adapter tick, including repeated source
   references. An invalid channel immediately releases its dependencies; an
   invalid face/stream/envelope calls `fid_pause` and latches disarmed. Check every
   synchronous result and poll `enabled`, `timed_out`, `last_error` and held-state
   status for asynchronous failures. A rejected C frame alone does not release.
6. Stop/Escape, source EOF/error/stop, calibration/profile/mapping changes or App
   close pause immediately before joining workers. Stop submitters before
   `fid_destroy`. Source recovery or receipt of fresh data never calls enable
   automatically after a whole-session fault. Preserve completed detector fits.

The driver watchdog only runs while its process is alive. Abrupt process death
and target application's handling of injected state remain native acceptance
checks, not guarantees from the dry-run event journal. A persistent background
service and a global stop shortcut are separate coordinated runtime work; current
Tk Escape only applies when its window receives that key.

## Ownership and merge order

Integration adopts this proposal in Contracts and owns App mode/driver lifecycle.
Processing owns mapping configuration, typed raw-to-action state, diagnostics and
serialization. Drivers owns public bindings, ABI and native transitions. Vision's
existing head/eye/pupil semantics remain intact; coordinate the finalized pupil
identity/validity with the active detection task before integration.

Land the shared agreement first, then component implementations with logging
fixtures, then App's dry-run connection. Validate release/freshness/ordering before
an explicitly enabled native session. Test Shift combinations and locked-cursor
movement in the intended game on each target OS; compilation cannot establish
that injected modifier flags or relative deltas are consumed correctly.
