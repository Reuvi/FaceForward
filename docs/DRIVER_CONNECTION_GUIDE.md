# Run the connected mouse and keyboard driver

The App now connects the current Vision → Processing pipeline to the driver's
native macOS/Linux mouse and keyboard backend. It uses the driver merged from
`driverTest` (`2e3e734`) with an additive synchronous submission API. Preview is
still the default; choose live output explicitly after calibrating.

## Build once after pulling

From the repository root:

```sh
cmake -S Drivers -B Drivers/build -DFID_NATIVE_BACKEND=ON
cmake --build Drivers/build -j 4
ctest --test-dir Drivers/build --output-on-failure
```

For recent Xcode versions that warn about the original macOS 10.15 deployment
target, add `-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0` to the configure command. Linux
native builds require the existing libevdev/pkg-config dependencies described in
[Drivers setup](../Drivers/readme.MD). For a hardware-free build on CI, use
`-DFID_NATIVE_BACKEND=OFF`. Never copy a compiled library between OS/architectures.

The default library is `Drivers/build/libface_input_driver.dylib` on macOS or
`Drivers/build/libface_input_driver.so` on Linux. App accepts an alternate path
with `--driver-library PATH`. A clear rebuild message appears if the library is
missing, has the wrong ABI, or lacks processed-submission support.

## Verify the actual library without moving the desktop

```sh
python3 -m App --source demo --output dry-run
# Bounded full cycle with driver event counts:
python3 -m App --source demo --output dry-run --headless --frames 490
```

Press **Start dry run**, then open **Signals**. This loads the compiled C
library and executes its control loop, click/key transitions and watchdog with
the dry-run backend. The panel shows actual driver event counts. Both eye clicks,
all four gaming keys and mouse movement should appear. End-of-source output is
disabled and all held keys are released. Synthetic frames never drive native
input through App.

## Use the camera and live output

```sh
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

1. Load your saved camera profile or complete the independent eye action, head
   X/Y and pupil guides. Inspect the valid raw/normalized values first.
2. On **Signals**, choose **Output → Live mouse + keyboard**
   and press **Connect output**. This connects while stopped.
3. Center your head and pupil direction, open your eyes, then press **Start live
   control**. The panel must say **LIVE MOUSE + KEYBOARD** and running. Preview
   and Driver dry run are available in the same selector.
4. **Stop**, Escape while App is focused, source stop, or window close releases
   output. Mapping/settings/profile changes and calibration also stop output.
   A lost face, invalid input or timeout stops it; returning input never auto-arms.

Alternatively, `--output native` chooses live output at launch with `--source
camera`; the desktop still requires Start. Source changes away from Camera
disconnect native output. Output choice and armed state are never saved in profiles.

macOS uses the driver's existing Accessibility permission. If Start reports
permission denied, grant access to the Python host/launcher in System Settings →
Privacy & Security → Accessibility, restart App, and Start again. Linux requires
the existing per-user `/dev/uinput` access. App reports setup/backend errors and
stays stopped. It does not change permissions or install a background service.

## What each action does

| Input | Real driver behavior |
| --- | --- |
| Left recognized eye action | One complete left click when activation begins |
| Right recognized eye action | One complete right click when activation begins |
| Head down/up | Hold W / Space; release on neutral or invalid input |
| Head left/right | Hold left Shift / S; independent of vertical motion |
| Pupils away from neutral | Continuous relative mouse movement |

A held eye activation produces one click, not repeated clicks or dragging.
Reopening/OFF/unknown resets the driver's click latch; Processing still requires
actual reopening after unknown. Short recognized activations are not lost between
driver ticks. Head down+left holds W+Shift; keys release independently. Other named
gaming copies use their configured bindings. Mouse and scroll mode also connects,
with no keyboard keys.

Processing owns thresholds, gain, noise filtering and eye intent. The adapter
sets the driver's additional dead zone and dwell to zero to avoid applying these
twice. Driver pointer speed follows the profile's pointer speed in device
units/second; mouse-mode scroll speed converts the preview's pixels/second to
detents/second at 40 pixels per detent. Gaming scroll stays neutral. Pupils are a
direction/speed control, not absolute screen gaze.

## Developer handoff

`Processing.Lab.set_output(sink)` injects the connection. Under the lab lock,
each capture/tick sends a complete command directly to `DriverOutput.submit`;
the UI journal is diagnostic only. Original capture metadata is validated before
conversion, so repeated output ticks cannot refresh stale observations. Disabled
commands pause immediately. Any driver failure disarms Processing and leaves an
error visible until explicit Start. No queued motion or past clicks are replayed.

`Drivers.binding` shares ABI definitions with the standalone console. The
`fid_abi_version` handshake precedes C struct reads. `fid_submit_processed` uses
the same locked control/emission path as the worker, synchronously consuming
zero-dwell clicks and key transitions. Legacy `fid_submit` remains unchanged.
The independent C worker continues movement and releases held keys if submissions
stop for 250 ms. See [the contract](../Contracts/DRIVER_CONNECTION.md).

Checks require no OS event injection:

```sh
ctest --test-dir Drivers/build --output-on-failure
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/integration -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -v
```

Set `FID_LIBRARY` when tests should load a non-default build. The native backend
is compiled on this Mac, but automated event evidence uses dry-run. Real-person
gesture accuracy, game behavior and a live permission-authorized session still
need testing with the operator.

## If the pointer stays stopped

The Signals camera panel now shows the reason directly. `Pointer unavailable`
means the calibrated pupil values were rejected (eye visibility, head calibration
support, confidence or freshness); reducing the pointer dead zone cannot recover
missing measurements. Raw iris graphs can still change while calibrated pupils
are unavailable. `Waiting to start` identifies axes that need centering.
`Pointer inside dead zone` shows the actual signed radial displacement and the
activation threshold. The header retains the actual stop/error reason.

With default settings and Y centered, pupil X must pass approximately .405 or
.595 to start. A settled X=.60 requests about 7 pixels/s, X=.65 about 51 pixels/s,
and X=.75 about 212 pixels/s at pointer speed 900. The 50 ms interpolation buffer
and 90 ms smoothing add response time; they do not make input unknown. Tune under
Mapping settings only after valid pupil input and Running are visible.

A startup bug could report `Driver needs a fresh neutral command before output`
when Start was pressed off-center and pupils were then centered: interpolation
still contained pre-start movement. Processing now discards older interpolation
history when a real fresh neutral input enables output. Active eye actions must
also release before enabling. Subsequent clicks/movement remain independent;
this does not synthesize a neutral input, weaken the driver check, or auto-rearm.

App writes `.local/diagnostics/live-control.jsonl` by default (ignored by Git).
It contains sampled scalar pupil validity/reasons, selected eye quality indicators,
head gate state, filter settings, pointer requests, output errors and event counts.
No camera images, landmarks or saved calibration models are logged.
Observations are sampled at up to 5 Hz plus visible state changes, outside the
capture/Processing threads; this is not a complete frame replay. Logs rotate at
1 MB, keeping two backups, with owner-only file permissions. Use
`--diagnostic-log PATH` to choose a local path or `--no-diagnostics` to disable.
A logging failure is displayed and cannot arm, stop or alter control.

The user-authorized macOS investigation on October 10, 2026 verified actual cursor
position changes using bounded native velocity demands: +127 and -114 pixels
through DriverOutput, and +68 pixels through the corrected Processing → driver
path. No clicks/keys were requested; both tests ended paused with held-key mask 0.
This verifies the tested launch context, not every app/game or real-person accuracy.
Automated regression tests still use the compiled driver's dry-run backend.
