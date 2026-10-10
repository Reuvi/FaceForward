# Face input driver — phase 1

C++17 userspace input library for Linux and macOS. Processing submits named
controls in `[0,1]`; this library generates mouse/keyboard events. See
[`passoff.md`](passoff.md) for actual verification and remaining work.
Windows and Dictation are outside phase 1.

For teammate setup, named test commands, expected results, and Python/C++ calling
examples, start with [the testing README](testing/README.md). This document is the
detailed driver reference.

## Build and run

From the `Drivers/` directory (`cd Drivers` from the repository root):

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --clean-first -j 4
ctest --test-dir build --output-on-failure
./build/driver_demo
python3 examples/python_ctypes.py
```

After pulling driver updates, rebuild the shared library before running the
tester or an application that loads it. This is required for ABI changes such
as v3, which changed the public C structure layouts. From `Drivers/`, rerun the
configure/build/test commands above; `--clean-first` removes old compiled
objects before rebuilding. The resulting library is
`build/libface_input_driver.so` on Linux or `build/libface_input_driver.dylib`
on macOS, and the Python tester uses that path by default. Build separately on
each OS; never reuse the other OS's library. If you use a different build
directory, pass its library path with `--library`.

Default demonstrations use **dry-run** and log generated actions without
injecting OS input. The C++ demo exercises all actions; Python demonstrates
pointer movement and calling the C API. Add `--rate 30` to test a 30 Hz producer.

Native dependencies: CMake, a C++17 compiler, and libevdev development headers
plus pkg-config on Linux. On macOS, install Xcode Command Line Tools and CMake;
the Apple frameworks are part of the SDK. The macOS backend requires 10.15+.
Build separately on each OS; a Linux build does not validate Apple APIs.

If libevdev is unavailable, compile portable logic/examples only:

```sh
cmake -S . -B build-dry -DFID_NATIVE_BACKEND=OFF
cmake --build build-dry -j 4
ctest --test-dir build-dry --output-on-failure
```

Enable native input explicitly:

```sh
./build/driver_demo --native --probe
./build/driver_demo --native
python3 examples/python_ctypes.py --native
```

`--probe` creates the backend, reports capabilities, and exits while paused;
on Linux it briefly creates virtual devices but emits no actions. The native
C++ demo provides a three-second delay, then moves/clicks and sends Delete and
Insert. Focus a disposable text document beforehand. Ctrl-C stops the synthetic
demo. Normal exit, exceptions in Python, and library teardown stop the worker.

For another build directory, Python accepts `--library /absolute/path/to/library`.
Linux builds produce `libface_input_driver.so`; macOS builds produce `.dylib`.
The default library lookup is anchored to this component's `build/` directory,
independent of the checkout name and terminal working directory. From the
repository root, `cmake -S Drivers -B Drivers/build` builds the same component.

### Run the interactive tester

From `Drivers/`, start in dry-run mode:

```sh
python3 examples/python_ctypes.py --interactive
```

Dry-run reports generated actions and does not move the real pointer or send
keys. To send input to the desktop, opt in to native mode:

```sh
python3 examples/python_ctypes.py --interactive --native
```

Native mode requires the OS setup and permissions described below. It allows
three seconds to focus the target app before each trial. Velocity and action
commands stream for one second by default; target commands stream until arrival
(up to 30 seconds). Each trial then pauses. Use `--duration`, `--delay`, or
`--rate` to change velocity/action length, focus delay, or producer rate. Type
`help` for commands; `status` reports output and target telemetry, `stop` cancels
a trial, and `quit`, EOF, or Ctrl-C pauses output and exits.

At `test>`, `move SPEED X Y` moves toward a destination. All values are in
`[0,1]`: X/Y are normalized primary-display coordinates (`0,0` top-left,
`1,1` bottom-right, and `0.5,0.5` center); SPEED is a fraction of configured
maximum target speed (default 600 display units/second). For example,
`move 0.1 0.8 0.5` and `move 0.6 0.8 0.5` use the same destination at different
speeds. The driver moves along a straight line, clamps the last step to avoid
overshoot, and stops on arrival. Target trials end on arrival, with a 30-second
safety limit. Send another `move` command to travel back to a previous point.
For a fair speed comparison, start each trial from the same cursor position.

Use `velocity X Y` for the original continuous axes intended for future joystick
or gaze input. Their neutral value is `0.5`: X below it moves left and above it
moves right; Y below it moves up and above it moves down. The default dead zone
is `0.45`–`0.55`. `velocity 0.65 0.5` moves right at about 133 pointer units per
second with defaults, and `velocity 0.9 0.5` at about 467 units per second. Such
velocity trials run for the configured duration. The axis meanings are unchanged
by target mode; each frame explicitly selects which interpretation to use.

Dry-run target movement starts at the simulated center of a 1920×1080 display.
Native macOS uses the main display. Native Linux target movement is supported
only when built with X11/XRandR and run in an X11 session; on Wayland, target
commands report unsupported while `velocity` continues to use uinput. Linux
velocity values are relative mouse counts; macOS values use Quartz coordinate
units. Neither scale is guaranteed to equal visible physical pixels. See
[`architecture.md`](architecture.md) for mode rationale and Processing handoff.

For other actions, `scroll 0.8` scrolls down and `scroll 0.2` up; `0.5` is
neutral. `click left` / `click right` send one click, and `key delete` /
`key insert` send one key tap. Button commands activate the control for one
trial and produce one tap after the configured dwell. The full command list,
OS-specific setup, permissions, and troubleshooting are in the
[testing guide](testing/README.md). Use `python3 examples/python_ctypes.py
--native --probe` to check backend access without emitting actions.

## Call the C API from Python

The C++ library exports a C-compatible ABI declared in
[`include/face_input_driver.h`](include/face_input_driver.h). Python's `ctypes`
loads the built `.so` (Linux) or `.dylib` (macOS), declares Python structures
with the same field order and types as the C structs, and calls the exported
functions through pointers. The included
[`python_ctypes.py`](examples/python_ctypes.py) defines those layouts and
function signatures; keep them aligned with the header and ABI version.

A minimal use from `Drivers/` looks like this:

```python
import ctypes as ct
import time
from examples.python_ctypes import Config, Frame, Status, load_driver

lib = load_driver("build/libface_input_driver.so")  # Use .dylib on macOS.
config = Config()
lib.fid_default_config(ct.byref(config))  # Safe dry-run default.
handle = ct.c_void_p()
def check(result):
    if result != 0:
        raise RuntimeError(lib.fid_result_string(result).decode())
check(lib.fid_create(ct.byref(config), ct.byref(handle)))
try:
    check(lib.fid_enable(handle))
    frame = Frame()
    lib.fid_neutral_frame(ct.byref(frame))  # Neutral axes/buttons; velocity mode.
    status = Status()
    while True:  # In an application, run this producer at about 30–60 Hz.
        check(lib.fid_submit(handle, ct.byref(frame)))
        check(lib.fid_get_status(handle, ct.byref(status)))
        if not status.awaiting_neutral:
            break
        time.sleep(1 / 60)
    # Set a target explicitly, and keep refreshing it until the endpoint is reached.
    frame.pointer_mode = 1  # FID_POINTER_TARGET from the C header.
    frame.target_x, frame.target_y, frame.target_speed = 0.8, 0.5, 0.6
    while True:
        check(lib.fid_submit(handle, ct.byref(frame)))
        check(lib.fid_get_status(handle, ct.byref(status)))
        if not status.enabled or status.target_reached:
            break
        time.sleep(1 / 60)
finally:
    lib.fid_pause(handle)
    lib.fid_destroy(handle)
```

`fid_create` returns an opaque handle; `fid_enable` arms it, and repeated
`fid_submit` calls provide current levels. Submit neutral button values until
`awaiting_neutral` clears, then keep submitting frames while the driver is in
use. Check each result, inspect status for asynchronous errors, and pause and
destroy the handle when finished. The helper also declares each function's
`argtypes` and `restype`, which lets `ctypes` pass pointers and interpret return
values correctly. See the [testing guide](testing/README.md) for the fuller
integration example and C++ linking instructions.

## Linux setup

Uses libevdev and the existing kernel
[`uinput` interface](https://docs.kernel.org/input/uinput.html), with separate
virtual pointer and keyboard devices for velocity mode. That path does not
depend on X11 and is intended for Wayland or X11 desktops. Absolute target mode
additionally needs X11 plus XRandR primary-display geometry and is rejected on
Wayland; CMake treats these development files as optional. Actual compositor
acceptance needs live testing.
The keyboard advertises standard key capabilities so udev can classify it as a
keyboard, but this MVP only emits Delete/Insert. See the
[udev classification source](https://github.com/systemd/systemd/blob/main/src/udev/udev-builtin-input_id.c).

The host must expose `/dev/uinput` and grant the calling account read/write
access. Containers may need the device passed through by the host. An
administrator can load the existing `uinput` module if necessary:

```sh
sudo modprobe uinput
ls -l /dev/uinput
```

For persistent local-desktop access, an administrator can install a udev rule
such as the following in `/etc/udev/rules.d/70-face-input-uinput.rules`, then
reload rules and retrigger the device (or reboot):

```udev
SUBSYSTEM=="misc", KERNEL=="uinput", TAG+="uaccess", OPTIONS+="static_node=uinput"
```

```sh
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --sysname-match=uinput
```

`uaccess` relies on an active local login session. Systems without that setup
need an administrator-managed dedicated group and restrictive device access.
Do not use world-writable permissions as the default or run all processing as
root. These are setup instructions; the library does not change host permissions.
Missing devices return `FID_BACKEND_UNAVAILABLE`; denied access returns
`FID_PERMISSION_DENIED`; other device/write failures return `FID_IO_ERROR`.

Allow the desktop to discover newly created devices before the first live
test. The C++ synthetic demo's three-second delay provides a practical buffer;
there is no compositor-ready acknowledgment in this API.

Relative Linux motion units are mouse counts, subject to desktop acceleration;
they are not guaranteed screen pixels. Scroll uses conventional wheel detents.
Tune speeds on the target desktop.

## macOS setup

Uses [Quartz Event Services](https://developer.apple.com/documentation/coregraphics/quartz-event-services).
Native creation checks event-posting access and requests it if absent. If
creation returns `FID_PERMISSION_DENIED`, grant the host access in System
Settings → Privacy & Security → Accessibility, then relaunch and probe again.
The process hosting the library needs permission: `driver_demo` for C++, the
Python executable for ctypes, or the application's executable when integrated.
CLI permissions may also depend on the terminal/launcher; check the actual host.
Keep the binary in a stable location while testing permissions.

Pointer velocity uses Quartz coordinates. Target mode reads the cursor and moves
to normalized coordinates on the main display, at a constant fraction of the
configured maximum speed. Speed is in coordinate units/sec rather than physical
display pixels.
Delete sends forward Delete (`0x75`). Insert sends the macOS Help/Insert-position
key (`0x72`) and sets `FID_CAP_INSERT_LIMITED`: it does **not** promise a
Windows-style overwrite toggle. Verify its behavior in the intended app.

Posting a Quartz event has no application-consumption acknowledgment. Logged
events mean the backend posted them, not that the focused application accepted
them. Live tests remain necessary. No Dictation trigger is implemented.

## Input contract

Public header: [`include/face_input_driver.h`](include/face_input_driver.h).
Use the header's exact layouts and `FID_ABI_VERSION`; the included ctypes
example mirrors ABI version 3. ABI v2 added explicit pointer mode, target inputs,
target speed configuration, and pointer telemetry. ABI v3 adds complete
held-key state and key transition events. This is not a stable cross-version
serialization format; rebuild every C, C++, or Python ctypes consumer against
this header after updating.

| Frame field | Meaning |
|---|---|
| `pointer_x` | In velocity mode, `<0.5` left, `>0.5` right; distance from neutral controls speed |
| `pointer_y` | In velocity mode, `<0.5` up, `>0.5` down |
| `pointer_mode` | `FID_POINTER_VELOCITY` uses those axes; `FID_POINTER_TARGET` uses the target fields below |
| `target_x`, `target_y` | Normalized primary-display endpoint, used only in target mode |
| `target_speed` | Fraction `[0,1]` of `config.target_max_speed`, used only in target mode |
| `scroll` | `<0.5` scroll up, `>0.5` scroll down |
| `left_click`, `right_click` | Dwell-triggered complete click |
| `delete_key`, `insert_key` | Dwell-triggered complete key tap |
| `keys_down` | Complete held-state bitmask using `FID_KEY_W`, `_A`, `_S`, `_D`, `_SPACE`, and `_LEFT_SHIFT`; set bits are held, cleared bits are released |

All scalar input values are finite and within `[0,1]`; `keys_down` may contain
only the named key bits. Invalid frames
return `FID_INVALID_ARGUMENT` and do not refresh the watchdog; previous valid
input may continue until it expires. A valid neutral frame stops motion sooner.
Only one selected user's controls should reach a driver instance; processing
owns facial mappings, confidence handling, smoothing, calibration, and arbitration.

Defaults:

| Setting | Default |
|---|---|
| Backend | Dry-run |
| Worker | 60 Hz; configurable 10–1000 Hz |
| Producer | Recommended 30–60 Hz |
| Input-loss timeout | 250 ms |
| Axis neutral / dead-zone half width | `0.5` / `0.05` |
| Pointer X/Y maximum speed | 600 units/sec each |
| Scroll maximum speed | 12 detents/sec |
| Button activation / release | Strictly `>0.7` / strictly `<0.3` |
| Button dwell | 150 ms each |

The neutral point is temporary. Each axis has configurable neutral, dead-zone
half width, maximum speed, and inversion; each button has its own thresholds and
dwell. Set configuration before create; changing it requires pause, destroy,
and recreate. When customizing neutral points, submit those custom values;
`fid_neutral_frame` always supplies the default `0.5` axis centers.

Inside the dead zone velocity is zero. Outside it, velocity scales linearly
to the configured speed at each endpoint. X/Y limits are independent, so
diagonal movement is faster in total. Fractional motion/scroll accumulates
between ticks; neutral or reversal clears residuals. A scheduler stall integrates
at most 100 ms of motion and skips missed ticks instead of replaying them.

The worker samples the latest frame. Brief pulses between ticks can be missed;
send sustained levels through the dwell interval. One activation emits one
press/release. Keeping a button high does not repeat; dip strictly below its
release threshold before activating again. Dropping to or below activation
threshold before dwell completes resets the dwell. Held keys use `keys_down`
state as documented below and do not use button dwell thresholds.

## Lifecycle and status

```cpp
fid_config config;
fid_default_config(&config); // Set config.backend = FID_NATIVE for live input.
fid_driver* driver = nullptr;
if (fid_create(&config, &driver) != FID_OK) { /* report error */ }
else {
    if (fid_enable(driver) == FID_OK) {
        fid_frame frame;
        fid_neutral_frame(&frame);
        // Submit a fresh frame with neutral buttons and keys for a worker tick.
        // Then continuously submit processing frames at 30–60 Hz.
        fid_submit(driver, &frame);
    }
    // Before resuming from a timeout, explicitly enable and rearm again.
    fid_pause(driver);
    fid_destroy(driver);
}
```

The snippet demonstrates ownership, not a complete producer loop; use the
examples for continuous submission. Check every return value in application code.

Creation starts paused. Enabling discards pre-enable frames and waits for all
four button values to be below their release thresholds and `keys_down` to be
zero. The arming tick emits no output. Submit a fresh neutral frame after
enabling, and retain it until `awaiting_neutral` is false. Calling enable while
already enabled is idempotent. Motion and held keys can be used once armed.

No valid frame for the timeout period latches output paused, even before the
first frame. Fresh input does not resume it: explicitly enable and rearm.
Async backend errors also pause output; inspect `last_error`, resolve the cause,
and enable again. Pause, timeout, backend errors, and destroy release any
library-owned held keys and buttons.

For keys, `keys_down` is the complete desired state: a set bit means stay held
and a cleared bit means release. Supported keys are W/A/S/D, Space, and left
Shift. Repeated frames with W set produce no repeated key-downs. A frame that
clears W emits one key-up. Shift goes down before other keys and up after them.
The driver does not synthesize keyboard auto-repeat; the desktop or application
may repeat a held key according to its own settings.

For example, Processing can hold W with Shift, release only W, then release
both by submitting these snapshots:

```cpp
frame.keys_down = FID_KEY_W | FID_KEY_LEFT_SHIFT; // W and Shift down
fid_submit(driver, &frame);
frame.keys_down = FID_KEY_LEFT_SHIFT;             // W up; Shift stays down
fid_submit(driver, &frame);
frame.keys_down = 0;                              // Shift up
fid_submit(driver, &frame);
```

API operations are internally serialized. Do not destroy a handle while other
threads call it. No C++ exceptions cross the ABI. This MVP is not hard real-time;
OS scheduling and application handling determine end-to-end latency.

`fid_get_status` reports output state, capabilities, asynchronous errors,
accepted/rejected frames, emitted events, and dropped journal records.
`fid_drain_events` destructively reads a bounded 1024-record journal on both
backends. Slow readers lose oldest records; output itself is not replayed or
queued for them. Dry-run capabilities represent modeled controls, not OS support.
For `FID_EVENT_KEY_DOWN` and `FID_EVENT_KEY_UP`, `fid_event.x` contains the
single `FID_KEY_*` bit that changed; `fid_status.held_key_mask` reports the
current logical held state.

For simple external testing, `driver_demo --stdin` accepts one complete frame
per line in the field order above (seven space-separated numbers). Stream at
30–60 Hz and begin with neutral-button frames; typing isolated lines manually
will trigger the 250 ms watchdog. The shared library remains the primary integration.

## Phase 2

Add a distinct native Dictation trigger with a configured shortcut and live
validation, initially on macOS. Linux is optional where a compatible speech
service exists. Do not add speech transcription to this input library. Windows,
camera processing, oscilloscope UI, controller emulation, release packaging, and
multi-monitor refinement remain separate future work.
