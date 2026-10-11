# App → native driver connection

> Current: [SCREEN_POINTER.md](SCREEN_POINTER.md) also connects explicit screen targets through the existing ABI v3. It supersedes pupil velocity-only behavior and the center arming gate for target mode; velocity startup still requires neutral input.

Reuvi explicitly requested merging driverTest and connecting the completed gaming
Processing phase to that driver. This supersedes the preview-only boundary in
GAMING_MAPPING.md. Keep the driver's existing ABI v3 struct layouts and independent
developer tools. Default runtime output remains preview; dry-run and native are
explicit choices. App permits native output only with the calibrated camera source.

The native behavior is the existing driver's: one complete left/right click for
each corresponding recognized eye activation, with no repeated click while held.
Reopening/OFF/unknown resets the activation. Mouse dragging is not implemented.
This resolves the original plan's provisional held-mouse choice in favor of the
driver the user requested. Head directions hold W/Space/left Shift/S and release
independently. Pupils supply continuous velocity, not absolute screen coordinates.

Processing sends each complete command synchronously to an injected output sink
under the lab lock, on both capture and output ticks. No polling/journal replay
is used for delivery. Drivers owns a public Python binding and validating adapter;
App owns creation, selection and lifecycle. Processing imports no Drivers internals.
Legacy mouse_preview_v0 is also accepted with no keys. Unknown values remain
invalid in Vision/Processing; released/neutral driver demands are control state.

The adapter checks complete fields, finite bounds, output ordering/session,
capture age, source ordering/session/subject, known flags and enabled state before
conversion. Repeated source samples cannot renew capture freshness. Stop or invalid
commands pause immediately. Driver failures/timeouts disarm Processing and require
an explicit new Start. Source/mapping/settings/profile changes record a disabled
command before replacement. A new enabled session requires a real neutral command;
the adapter never invents a neutral arming frame. Output changes and close pause
and destroy the old handle; changing away from camera disconnects native output.

Add fid_submit_processed without changing ABI v3 layout or legacy fid_submit.
It consumes an already-processed state immediately under the driver mutex using
the same control tick and emission path as the worker. Thus zero-dwell clicks and
key down/up pairs between worker ticks are delivered in order. The worker continues
movement and the independent no-frame watchdog; no action queue replays old input.
The adapter sets button dwell to zero and axis dead zones to zero because Processing
already applies the eye classification and pointer shaping. Driver speed converts
normalized demand to device units. Rejected processed frames pause/release output.

UI clearly labels Preview, Driver dry run, or LIVE mouse + keyboard; Stop and window
close always stop output (no service/background lifetime change). Expose driver
status/errors and events for diagnostics. No output selection/armed state is saved
in face profiles. Native macOS requires its existing Accessibility permission;
Linux requires the driver's existing uinput setup. Automated tests use the compiled
dry-run backend, including events, short pulses, staleness, stop and watchdog release.

Startup correction: once a genuinely fresh neutral input passes Processing's
arming gates, discard older pre-enable axis interpolation history and reset
motion before emitting the first enabled command. Do not replace the latest
observation, relax driver validation or fabricate a neutral arming frame. Active
eye actions must release before enabling. Steady-state independent eye actions,
head keys, dead zones, freshness and explicit rearming remain unchanged. App's
bounded local diagnostic log is an observational side channel, never control input.
