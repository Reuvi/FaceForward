# Screen destination pointer

The user requested that the cursor follow eye position and stop at a fixed gaze,
instead of continuing to move while the eyes are off center. This supersedes the
gaming pointer velocity behavior in RAW_PUPIL_CONTROL.md and DRIVER_CONNECTION.md.

The built-in gaming mapping now uses `target` pointer mode. The current fixed-scale
raw pupil X/Y supplies an **approximate** normalized primary-display destination;
it is not a calibrated estimate of screen gaze. No pupil calibration is introduced
by this change. Raw measurements, detector presets v13 and face profiles v3 stay
unchanged. Eye/head actions remain independent. Mouse test stays head-only velocity;
Mouse and scroll and imported older mappings keep their velocity behavior.

Processing smooths destination coordinates, then applies a small fixation dead
band around the last accepted destination. A steady off-center input must converge
to a finite destination, never integrate indefinitely. Keep position mode distinct
from center dead zones, velocity curves/boost and acceleration shaping. Pointer gain,
axis center/inversion, smoothing and a separate `target_jitter` control are supported.
The driver's existing bounded target speed controls travel speed. No prediction.

The existing `device_control_v1` discriminator gains the explicitly tagged variant
`pointer: {mode: "target", x: 0..1, y: 0..1, speed: 0..1}`. Velocity retains its
existing fields and semantics. Unknown or disabled target commands have speed 0
and coordinates .5/.5 as released control state, never as fabricated observations.
The adapter rejects unknown moving targets, malformed values and mode changes
without a stop. The C backend must perform no target movement when speed is zero.
Use the existing ABI v3 target fields; do not change any C struct layout.

Explicit Start plus a fresh capture and released eye/head actions permits target
control from any valid pupil position. Target coordinates have no neutral-center
arming gate; they are destinations. Velocity retains real-neutral startup. Missing
pupils stop travel immediately while independent actions can continue; face loss,
staleness, stop, source/mapping/profile/settings changes disarm/release output and
never auto-arm. A stale target cannot be kept alive by repeated output ticks.

Mapping files are `input_mapping_v4` (details below); v3 introduced `pointer_mode` and `target_jitter`.
Validate v1/v2 and preserve them as velocity on import. Face-profile loading keeps
the chosen mapping's mode and target dead band. Changing either stops output.
Signals/diagnostics identify destinations, driver position and arrival instead of
labeling target coordinates as velocity. Simulated preview respects the same mode.

Primary display is the driver's existing coordinate space: macOS and Linux X11
with the required display support. No Wayland target support or calibrated gaze
accuracy is claimed. Automated tests use synthetic input and the compiled dry-run
backend, including repeated-target arrival, no drift, unknown/stale stops, button
release, mode/persistence compatibility and unchanged head-only velocity behavior.

## Pupil reach and response update

The user requested stronger downward pupil movement, corner access and less
filtering, in the gaming pupil mapping, and then confirmed that Mouse test also needs
a stronger downward response.
The built-in mapping now uses 2× pointer gain and an additional 4× downward gain
(8× total below the configured pupil center), 20 ms position smoothing, zero
interpolation delay and a .002 fixation dead band. Downward amplification is
applied before axis inversion; upward response and raw Vision values are unchanged
apart from the shared 2× reach gain. Clamp each destination axis independently.
At a saturated target, settle exactly at that screen edge once the filtered axis
is within .002 normalized units, even if the fixation dead band would hold it
short. This permits every corner without radial normalization or ongoing drift.

Mapping files become `input_mapping_v4`, adding `pointer_down_gain` (1–8),
`target_smoothing_ms` (0–1000) and `target_interpolation_ms` (0–250). Fully validate
v1–v3 files and preserve their response: downward gain 1, prior response smoothing
and interpolation, prior pointer gain and fixation band; v1/v2 remain velocity.
Target smoothing/delay now belong to the mapping. Loading a face profile keeps
all these target settings, instead of restoring its old velocity filtering.
Expose separate target controls and log the effective filter and gain settings.
Mouse test uses a separate 3× downward pointer gain, .10 dead zone / .02 activation
margin, 20 ms smoothing, curve 1.2, acceleration 10/s and deceleration 14/s, with
zero interpolation delay. Apply downward gain before the pointer dead-zone/curve
and axis inversion, clamping each scaled input axis. Its actual center still maps
to zero. Its pointer response stays with the selected mapping when a face profile
loads. Other velocity defaults, independent eye/head actions, detector calibration,
freshness checks, unknown input and explicit arming rules are unchanged.
