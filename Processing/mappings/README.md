# Named mouse and keyboard mappings

The middle phase is implemented: current Vision measurements feed independent
filters and action gates, then readable keyboard/mouse commands. App can connect
these to the merged C driver with explicit Preview, Driver dry run and
Live mouse + keyboard choices. See [build and live-output setup](../../docs/DRIVER_CONNECTION_GUIDE.md).

| Input | Command |
| --- | --- |
| Left eye's calibrated closed action | One left click on activation; OFF/unknown resets |
| Right eye's calibrated closed action | One right click on activation; OFF/unknown resets |
| Head down | Hold W |
| Head up | Hold Space |
| Head left | Hold left Shift |
| Head right | Hold S |
| Pupils away from center | Continuous pointer velocity; farther is faster |

Both head axes can act together (down + left = W + Shift). Eyes remain independent.
A and D are available for edited bindings but inactive in the built-in mapping.
Scroll stays neutral. Head keys are held states. The existing driver's mouse
behavior is one complete click per activation; a sustained eye action does not
repeat clicks or drag. The raw command button fields remain activation levels.

## Mouse test

Select **Mouse test** on Signals, or pass `--mapping mouse-test`. Calibrated head X/Y form one pointer vector: turn left/right and nod up/down; both can move together diagonally. All eyes, pupils, buttons, keyboard actions and scroll are ignored. Both head axes must be valid. Center your head and explicitly Start; either missing axis stops the pointer immediately. Face loss/staleness and Stop require another Start.

Copies retain this head-only mode. Pointer settings and gain apply; keyboard bindings and key thresholds are hidden. The driver connection and permissions are identical to gaming mode.

## Try it

From the checkout containing this change:

```sh
# Hardware-free synthetic command exercise.
python3 -m App --source demo

# Calibrated camera input, after installing Vision's local dependencies/model.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task

# Previous mouse/scroll behavior.
python3 -m App --mapping mouse
```

In App, use **Signals**. In the standalone Processing lab, use **Signal mapping**. Center your head and pupil direction, open both eyes, and
press **Start preview**. The eight rows show the usable raw normalized value,
filtered value, threshold and instruction. Unknown stays unknown in the numeric
readout; a darker plot hold is display history only. The graph picker shows raw detector, head or pointer processing traces. The standalone
Processing lab retains its simulated pointer playground and developer tabs.

For camera use, load a compatible profile or finish the independent eye action,
head X/Y and pupil guides. Partial calibration is supported: an unavailable
channel is released while other usable channels can work. Pupil direction needs
the current personal endpoint/head-compensation fit. Processing uses precise
`gaze_x/y`, never the 11×11 matrix or uncalibrated raw iris ratios.

The synthetic demo cycles every 16 seconds: neutral, immediate labeled eye
actions, pupil circle, head up+right (Space+S), head down+left (W+Shift), neutral.
Its eye labels and added yaw are explicitly synthetic; they are not generated
from camera frames or used to infer real-person wink accuracy.

## Noise thresholds and gain

Head positions use 0 = up/left, .5 = neutral, 1 = down/right. Each head axis has
its own settings. Defaults are activation .30 and release .18 of its calibrated
half-range from neutral: positive motion turns on at .65 and off at .59;
negative motion turns on at .35 and off at .41. Hysteresis avoids repeated
press/release chatter around one threshold. A capture-timed exponential filter
uses 40 ms smoothing; a direction must persist for 50 ms of captured evidence
before activation. Reversal releases the old direction before qualifying the new.
Invalid input releases immediately, bypassing smoothing, and that axis must
return to actual neutral before another activation.

Pupils use the existing radial dead zone: start above .19 signed displacement,
release at .16 with default settings. **Signals → Mapping settings…** exposes the response
curve, smoothing and acceleration limits; standalone **Transfer settings** also
exposes interpolation (50 ms by default) and other developer settings.
Gaming and Mouse test default to adaptive **1€** velocity smoothing, followed by acceleration/deceleration limits. It uses a shared two-axis speed estimate and the Smoothing ms setting; raw inputs and neutral-start checks remain unchanged. Uncheck **Adaptive pointer smoothing (1€)** to use the earlier fixed filter. Unknown input resets history immediately. Mouse test defaults to zero interpolation delay; imported face-profile response settings retain their values. See [method, benchmark and limitations](../../docs/PUPIL_QUALITY_GUIDE.md).

**Mapping settings… → Pointer gain** scales only the motion beyond the dead zone
(.1–4×, capped at full velocity). A gain increase cannot amplify neutral jitter
past the threshold. Jump boost is disabled by default in gaming mode. These
defaults are starting values for personal tuning, not measured human accuracy.

Calibrated eye intent is already a per-frame action classification. Processing
does not add eye dwell, opposite-eye suppression, or release debounce. Unknown
releases that eye, and actual reopening is required before a new activation.
Missing calibrated intent in a SignalFrame never falls back to anatomical
closure timers. Only explicit `raw_mouse_v1` developer mocks use legacy eye timers.

**Stop / Escape**, lost face, stale input, source stop/restart and malformed
frames release all output. The capture and receipt age limit defaults to 250 ms.
Resumed input does not auto-arm. Mapping, settings and profile changes also stop
preview. Calibration fits survive these output lifecycle changes.

## Save more mappings

In **Mapping settings…**, choose **Copy as…**, give the copy a name, change the four head bindings and
independent filter settings, then **Apply settings**. Bindings support
W/A/S/D/Space/left Shift/none. Multiple directions assigned to the same key are
combined as a held state. Pointer and independent mouse-button bindings remain
fixed within each mapping family. Mouse test always has all key bindings set to none. Apply increments the mapping revision and
requires a new Start preview.

**Export mapping / Import mapping** writes strict `input_mapping_v2` JSON (v1 remains readable), including input mode and adaptive-filter selection alongside
name, stable ID, revision, response settings, pointer gain, head thresholds and
bindings. Import validates the whole file before replacing/selecting it. Files
contain no detector fits, observations or armed state. Export uses an atomic
private local write. Copies live in memory until exported. Importing an existing
ID replaces that mapping; use Copy as… first to preserve another variant.

The separate face profile format remains `face_mouse_profile_v3` with detector
v12. Its existing mouse response settings apply to the active mapping on load;
head settings and bindings stay with the mapping. The Mouse and scroll mode
keeps its own independent response settings.

## Python boundary

```python
from Processing.mouse.controller import Lab
from Processing.mappings.config import GAMING_ID

lab = Lab()
lab.select_mapping(GAMING_ID)
lab.settings({"runtime": {"source": "external", "subject_id": "single-user"}})
lab.start()  # Independent 100 Hz tick; keeps checking age when captures stop.
lab.action({"action": "arm"})
# Each current Vision callback: lab.ingest(signal_frame)
state = lab.state(after_command=0)
print(state["message"])  # device_control_v1; latest pointer velocity
print(state["commands"])  # Bounded preview transitions, complete command per entry
lab.close()  # Disarms and records the release before joining the worker.
```

App already owns this connection through `MouseSession`; do not start a second
producer or camera to use it. Calls are serialized by the lab's lock. Capture
and output clocks must share monotonic milliseconds. Output sequence/session
are separate from the original source origin so ticks cannot renew old input.

Every accepted capture evaluates actions immediately as well as on ticks. The
512-entry transition journal preserves recognized ON/OFF pairs between ticks.
`command_gap` reports an expired consumer cursor. This is diagnostic evidence,
not a reliable live transport: a future driver consumer must stop on gaps, reject
old sources, never replay stale commands, and use only the latest pointer demand.
See [device_control_v1](../../Contracts/GAMING_MAPPING.md) for complete fields.

`driverTest` ABI v3 is now merged and connected via `Drivers.output.DriverOutput`.
The adapter validates source age/order and disabled/unknown states, disables the
extra driver dwell/dead zone, and uses synchronous `fid_submit_processed` to
preserve action edges. The C worker retains its independent watchdog. Mouse
commands are clicks, not dragging. App close releases output and destroys the
driver. See [the connection contract](../../Contracts/DRIVER_CONNECTION.md).

## Checks

```sh
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/integration -v
# With Vision image dependencies and local Tk/display:
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -v
python3 -m App --source demo --headless --frames 490
python3 -m App --source demo --headless --frames 490 --mapping mouse
```

Gaming's full demo should report both mouse buttons, pointer and all four keys
observed; scroll is false by design. Mouse mode should report both buttons,
pointer and scroll; keys remain false. Both end disabled and fully released.
The CLI reports evidence; it exits nonzero on source error, not on a missing
observed flag. Tests assert the expected actions, threshold boundaries, capture
timing, partial invalidity, stale/restart behavior, persistence and current
calibrated pupil/head input. Synthetic checks do not establish live accuracy.
