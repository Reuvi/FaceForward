# Pointer modes and Processing handoff

The driver exposes two explicit pointer modes, introduced in ABI v2 and retained
in ABI v3. Processing chooses
the mode for each frame; the driver never guesses whether a pair of values means
an axis or a destination.

## Continuous velocity mode

`FID_POINTER_VELOCITY` keeps the existing `pointer_x` and `pointer_y` contract.
Each is a normalized direction/speed axis: the configured neutral value (0.5 by
default) means zero velocity, values below it mean left/up, and values above it
mean right/down. The driver samples the latest levels at its worker rate and
emits relative motion. This mode fits a joystick or continuously updated gaze
vector, where the signal says which way and how quickly to move now. It does
not select an endpoint.

This behavior stays separate so a future controller cannot accidentally turn a
stick deflection into a screen coordinate. The field names and their meaning
remain unchanged when target mode is selected; those fields are ignored for
pointer movement in target mode.

## Target mode

`FID_POINTER_TARGET` uses `target_x`, `target_y`, and `target_speed`:

- `target_x` and `target_y` are normalized positions on the primary display;
  `(0,0)` is top-left, `(1,1)` bottom-right, and `(0.5,0.5)` is the center.
- `target_speed` is a normalized fraction of `fid_config.target_max_speed`,
  600 display units/second by default. A value of 0 holds the current position;
  a positive value moves toward the target at constant speed.
- Movement follows a straight line, clamps its final step to the destination,
  and stops there without overshoot. Repeated frames refresh the watchdog and
  may replace the active target or speed. To return, Processing submits a new
  target for the return location.

This mode is useful for manual examples such as `move 0.1 0.8 0.5` versus
`move 0.6 0.8 0.5`: both specify the same destination, while the second should
arrive sooner. It is a separate convenience/control choice, not a replacement
for continuous velocity input. For a fair speed comparison, start both trials
from the same cursor position; after one reaches its target, submit the original
starting location as another target before comparing the other speed.

The tester reports the current normalized position, destination, requested
speed, measured per-tick velocity, and arrival state. Dry-run uses a simulated
1920×1080 primary display. Native macOS uses the Quartz main display. Native
Linux target mode requires an X11 session and XRandR primary-display geometry;
Wayland sessions and builds without those development files return
`FID_UNSUPPORTED` for target frames. Linux relative velocity mode continues to
use uinput and remains available on Wayland.
On macOS, velocity events carry Quartz relative mouse deltas while target mode
continues to move to an absolute Quartz display position.

## Processing integration request

The driver consumes normalized values and performs OS event generation. It does
not detect faces, choose facial gestures, arbitrate multiple people, or infer a
target from velocity. Processing should send one selected user's current frame
at a steady 30–60 Hz, continue neutral button values for arming, and keep
refreshing the frame while enabled so the watchdog does not pause output.

The current prototype applies a configurable dead zone and linear speed curve
to velocity axes in `control.cpp`. The shared contract also assigns Processing
responsibility for shaping control values, so the exact owner of that curve
needs agreement before integration; do not apply the same response curve in
both components. Target mode's speed is a separate normalized fraction of the
driver's configured maximum.

The shared `Contracts/README.md` is integration-owned and has not been edited.
See [`interface-requests/target-pointer-mode.md`](interface-requests/target-pointer-mode.md)
for the proposed contract fields, compatibility treatment, and open integration
decisions. Drivers should not silently reinterpret the existing axis fields.

## ABI and compatibility

ABI v2 added a pointer-mode selector and target fields to `fid_frame`, a target
speed setting to `fid_config`, and position/velocity telemetry to `fid_status`.
ABI v3 adds a complete held-key bitmask to `fid_frame`, held-key telemetry to
`fid_status`, and key-down/up events. The C++ demo, C header test, Python
`ctypes` layouts, and downstream consumers must use the v3 header. This
prototype ABI is not a stable wire format. Existing velocity-axis values retain
their prior meaning and response settings.

For held keys, Processing sends the complete desired key state on every frame:
`W=1` means keep W down, and clearing its bit means release W. Supported keys
are W/A/S/D, Space, and left Shift. Repeated frames with an unchanged bitmask
produce no extra key-downs; the driver does not synthesize key repeats. Pause,
watchdog timeout, backend failure, or destroy releases all active keys.
The tester offers `hold w shift` for a finite hold trial.

Dictation remains out of scope for this phase. Button-state differences between
the current threshold/dwell tap implementation and the shared held-state
contract remain a separate integration request.
