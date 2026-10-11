# Gaming signal processing and preview

> Updated by [pupil quality and Mouse test](PUPIL_QUALITY_MOUSE_TEST.md): mapping JSON v2 adds head-only mode and adaptive pointer filtering; device_control_v1 is unchanged.

**Driver connection update:** [DRIVER_CONNECTION.md](DRIVER_CONNECTION.md)
supersedes the preview-only driver boundary below. Native output uses the existing
driver's one-click-per-eye-activation behavior (no dragging); the mouse fields
remain activation levels. Head keys are held states. Both formats connect through
an explicit runtime output choice with no extra driver dwell/dead zone.

User-authorized middle-phase implementation, based on 7175a89. Adopt the
Processing plan's gaming keyboard mouse mapping 1. Vision measurement semantics
are unchanged: consume personal, head-compensated gaze_x/y under
PUPIL_HEAD_CALIBRATION.md, independent calibrated head_x/y, and eye_intent_v1.
No detector or OS driver implementation changes belong to this increment.

## Named mapping

The built-in ID is gaming-keyboard-mouse-1 and its display name is
"gaming keyboard mouse mapping 1". Left/right recognized eye actions hold the
corresponding mouse button. Head down/up/left/right hold W/Space/left Shift/S.
Pupils request relative pointer velocity. Head axes and eyes are independent;
opposite directions on one axis cannot both hold. Scroll is neutral. Existing
mouse/scroll mode remains selectable and preserves mouse_preview_v0.

Processing owns mapping selection, thresholds, smoothing, gain and instructions.
Head defaults: signed displacement on=.30, off=.18, smoothing=40 ms, activation
confirmation=50 ms using distinct original captures; no release debounce.
Raw head positions 0/.5/1 map to signed -1/0/1. Invalid input clears that axis
immediately and requires actual neutral before reuse. New arming requires fresh
neutral usable axes and an independent open baseline for each eye.
Eye intent follows EYE_INTENT.md without timing or opposite-eye gating. A
SignalFrame lacking calibrated intent cannot silently activate gaming eye
buttons; explicitly labeled raw developer mocks retain legacy eye timers.
Pupil pointer uses continuous coordinates, radial dead zone/hysteresis, bounded
gain after the dead zone, interpolation, smoothing and acceleration limits.
No driver-side duplicate shaping. Pupil closure/loss stops movement without
vetoing independently valid eye/head actions. No plotted hold becomes evidence.

## Output

Gaming emits device_control_v1, distinct from ControlFrame v1 and mouse_preview_v0.
Fields: output_session_id, strictly increasing output sequence, monotonic
timestamp_ms, source {session_id, sequence, timestamp_ms, subject_id}, mapping_id,
mapping_revision, enabled, buttons {left_click,right_click}, complete keys
{w,a,s,d,space,left_shift}, pointer {mode:velocity,x,y}, scroll_y, and known
{left_click,right_click,head_x,head_y,pointer}. Buttons/keys are numeric 0/1;
axes are finite [0,1], with .5 neutral. Disabled output releases/neutralizes all.
Before any source, nullable source origin fields are allowed only while disabled.
Output_session_id changes on processor replacement; source provenance is never
retimestamped by filtering or the output clock. Mapping identity is configuration,
not identity recognition. Known=false means released/neutral output, not measured
neutral input. Both source capture and receipt age use the default 250 ms budget.

The native lab publishes a latest command and a bounded command-transition
journal. It evaluates fresh accepted captures as well as independent output ticks,
so a recognized eye ON/OFF between ticks is recorded. Journal entries contain an
increasing lab-wide ID and complete command at each enabled/button/key transition.
Polling does not drain it; a cursor older than retained entries reports a gap.
It is preview evidence, not a reliable driver transport: any future live consumer
must release/disarm on a gap and must not replay stale commands. Pointer velocity
uses the latest snapshot, never an accumulated queue of motion.

Stop, invalid whole frame/face, timeout, source change/restart, mapping/settings
changes, profile load and close release output and require explicit re-arming.
Duplicates/out-of-order input do not refresh freshness. Preserve detector fits.
Changing mappings records release before replacing the processor; old and new
mapping states cannot overlap. Source configuration changes preserve the selected
mapping but stop it. Calibration disarming applies to both mapping modes.

## Persistence and UI

Keep input_mapping_v1 files separate from strict face_mouse_profile_v3 files.
Mapping files contain ID, name, revision, MouseConfig-compatible response settings,
pointer gain, independent head settings and four head key bindings. Support named
copies, validated changes, import/export, and selection; never persist armed state,
observations or detector fits. Built-in mouse mode retains its own response config.
Face-profile load applies its existing response settings to the active mode and
disarms; it does not change the selected mapping or its head/key configuration.

Display raw normalized input, filtered value, activation/release settings and
readable held/released/waiting/unknown instructions in a native Signal mapping
tab. Distinguish preview from actual OS output. Export diagnostic traces without
fabricating unknown observations. Headless synthetic checks require no camera.

## Driver boundary

Reviewed driverTest at 2e3e734, ABI v3. It supports the requested held keys and
velocity input but mouse fields are dwell-qualified taps. This increment stops
at a validated Processing command/preview; it does not load the native library.
Held-mouse support, ordered delivery, public Python binding and a lifecycle/age
validating adapter remain prerequisites for live integration. Driver C frames
omit source metadata and enabled state; a future adapter must pause on faults.
No service installation or change to close/Stop behavior is included.
