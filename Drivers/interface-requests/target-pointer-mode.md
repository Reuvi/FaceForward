# Processing → Drivers: explicit target pointer mode

Adopted for App by [SCREEN_POINTER.md](../../Contracts/SCREEN_POINTER.md).
The current JSON form is `pointer: {mode: "target", x, y, speed}`; this historical
proposal's `target_x/target_y` remain the ABI field names, not App JSON keys.

Status: proposed for the shared contract owner; implemented in the Drivers
prototype ABI as version 2. The shared `Contracts/README.md` was intentionally
left unchanged.

## Motivation

The existing pointer axes represent continuous normalized direction/speed
demands. They remain suitable for joystick or gaze-vector control. Some examples
and interaction styles also need a destination with a separate speed input. A
target must be explicit so its coordinates cannot be mistaken for velocity.

## Proposed frame extension

Keep current `axes.pointer_x` and `axes.pointer_y` semantics exactly as they
are. Add an optional pointer command with a velocity default for existing v1
producers:

```json
{
  "pointer": {
    "mode": "target",
    "target_x": 0.8,
    "target_y": 0.5,
    "speed": 0.6
  }
}
```

For `mode: "velocity"` or an omitted pointer mode, use the existing axes. For
`mode: "target"`, use normalized primary-display coordinates and a normalized
speed fraction `[0,1]`; map that speed to the driver's configured maximum. A
target is a point, not an unbounded cardinal direction. The driver moves toward
it at constant speed, clamps the last step, and reports arrival. Repeated target
frames may update the destination/speed and refresh the input watchdog.

The driver prototype represents this as `pointer_mode`, `target_x`, `target_y`,
and `target_speed` in `fid_frame`; velocity fields are left intact and ignored
for pointer movement when target mode is active. Drivers ABI v2 is distinct
from the shared `ControlFrame` schema version.

## Ownership and compatibility

- Processing selects the mode and emits normalized values. It owns facial
  mapping, signal filtering, and profile calibration. Agree whether response
  shaping stays in Processing or uses the current driver's configurable curve;
  do not apply it twice.
- Drivers owns OS display mapping, movement timing, endpoint clamping, target
  arrival telemetry, and native capability reporting.
- Existing producers that omit the optional mode keep velocity behavior.
- If the shared contract does not permit this optional addition within its
  current schema version, the contract owner should version it compatibly and
  coordinate rollout. Do not edit the shared file from the Drivers lane.
- Target coordinates currently refer to the primary display. Linux native
  target mode requires X11 and XRandR; pure Wayland target support is not claimed.
  Velocity mode remains available through relative uinput events.

## Integration checks

1. Confirm whether Processing wants target mode in the first demonstration or
   only as a tester/example mode.
2. Agree the serialized field names and whether target coordinates are relative
   to primary display, active display, or a future multi-display abstraction.
3. Keep `pointer_x/y` velocity tests unchanged; add same-target/different-speed
   and target-arrival tests for target mode.
4. Confirm the producer sends frames often enough to satisfy the driver
   watchdog and explicitly arms/disarms the device.
