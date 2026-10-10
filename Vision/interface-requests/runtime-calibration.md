# Proposed Vision runtime and calibration handoff

Status: proposal for the integration owner; no shared contract changes.

The implementation emits the existing SignalFrame v1 dictionaries/NDJSON and can
be consumed with mocks immediately. New Python entry points under Vision are
local until the integrator chooses application wiring. Processing owns profile
persistence, diagnostic settings, control thresholds, and mappings.

Please agree the following before a dependent cross-lane implementation:

1. App supplies one monotonic millisecond clock to Vision capture/replay,
   Processing, and Drivers, owns the camera context manager, and handles
   CaptureError/CLI EOF as disconnect. Stop/disconnect must disarm/release output;
   the independent driver watchdog remains necessary.
2. App explicitly binds a selected session/subject to loaded detection calibration.
   Vision's current EyeBinding carries per-eye open/closed calibration and
   per-axis gaze transforms, a validated quality-assessment callback, a gaze
   disagreement tolerance, and an explicit single-eye-mode choice.
3. Keep that binding session-local; never look up profiles automatically by
   tracker ID. Tracking loss/restart clears it. A reappearing person requires
   deliberate re-selection/rebinding.
4. Agree a serializable persistence representation separately. Python callbacks
   must not be serialized into profiles. Validation should establish pose,
   visibility, and minimum-size gates before valid live control measurements.
5. Raw observation ratios and overlay pixels currently remain outside SignalFrame.
   Agree a diagnostic channel/schema before the Processing UI imports them.

Synthetic/replay consumers need no new keys and no camera dependencies. Head and
tongue values remain invalid in live diagnostics while their detectors/calibration
are pending. No automatic profile selection, gesture mapping, or live OS output
is introduced.

## Native Processing compatibility inspection

The active local `work/reuvi/processing/mouse-lab` checkout was inspected read-only
on 2026-10-10, including its uncommitted implementation. Its documented
`Lab.ingest(frame)` API already accepts SignalFrame v1 when source is
`external`. A headless, in-process probe accepted a synthetic Vision frame and
preserved continuous gaze, independent eye polarity, and capture timestamp.
No Processing files or shared contracts were changed by this inspection.

Use direct Python calls from a detector worker. Keep Tk on its main thread and
leave the lab's independent output clock running through camera stalls so its
freshness handling can operate. The lab draws readouts up to 20 Hz and scopes at
10 Hz while processing at 100 Hz; detector cadence need not equal either rate.
Vision's NDJSON CLI is a diagnostic/replay option, not a required IPC layer.

The current Processing adapter requires strictly increasing capture timestamps
within a session; v1 only explicitly requires increasing sequence numbers.
Real camera samples have distinct monotonic times, but same-timestamp synthetic
or replay samples will be rejected by this consumer. Preserve original capture
times and agree this edge case rather than manufacturing new timestamps.

The lab's `mouse_preview_v0` output and independent output clock are provisional
Processing/Drivers integration work. Vision keeps its existing SignalFrame v1
boundary; it does not adopt that output format or convert continuous coordinates
to one-hot matrices.
