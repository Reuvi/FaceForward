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

Press **Start dry run**, then open **Signal mapping**. This loads the compiled C
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
2. On **Vision source & raw signals**, choose **Output → Live mouse + keyboard**
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
twice. Driver pointer speed follows Transfer settings' pointer speed in device
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
