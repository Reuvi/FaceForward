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
