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
cmake --build build -j 4
ctest --test-dir build --output-on-failure
./build/driver_demo
python3 examples/python_ctypes.py
```

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
three seconds to focus the target app before each trial. Each command streams
for one second by default, then pauses. Use `--duration`, `--delay`, or `--rate`
to change trial length, focus delay, or producer rate. Type `help` for commands;
`status` reports mode and output state, `stop` cancels a trial, and `quit`, EOF,
or Ctrl-C pauses output and exits.

At `test>`, enter `move X Y` using values from `0` to `1`. The default neutral
point is `0.5` on each axis: X below `0.5` moves left and above it moves right;
Y below `0.5` moves up and above it moves down. Values are direction and speed
controls, not screen coordinates. The default dead zone is `0.45`–`0.55`, so
`move 0.5 0.5` is still, and values just outside that band move slowly. For
example, `move 0.65 0.5` moves right at about 133 pointer units per second with
default settings; `move 0.9 0.5` moves faster, about 467 units per second. A
trial lasts one second, so the approximate total movement also depends on the
trial duration and desktop handling. Linux units are relative mouse counts and
macOS units are Quartz coordinate units; neither is guaranteed to equal visible
screen pixels.

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
    frame = Frame(0.5, 0.5, 0.5, 0, 0, 0, 0)  # Neutral axes; buttons inactive.
    status = Status()
    while True:  # In an application, run this producer at about 30–60 Hz.
        check(lib.fid_submit(handle, ct.byref(frame)))
        check(lib.fid_get_status(handle, ct.byref(status)))
        if not status.awaiting_neutral:
            break
        time.sleep(1 / 60)
    # Continue submitting current processing values at 30–60 Hz.
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
virtual pointer and keyboard devices. It does not depend on X11 and is intended
for Wayland or X11 desktops. Actual compositor acceptance needs live testing.
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

Pointer motion uses Quartz coordinates and is constrained to the primary
display. Speed is in coordinate units/sec rather than physical display pixels.
Delete sends forward Delete (`0x75`). Insert sends the macOS Help/Insert-position
key (`0x72`) and sets `FID_CAP_INSERT_LIMITED`: it does **not** promise a
Windows-style overwrite toggle. Verify its behavior in the intended app.

Posting a Quartz event has no application-consumption acknowledgment. Logged
events mean the backend posted them, not that the focused application accepted
them. Live tests remain necessary. No Dictation trigger is implemented.

## Input contract

Public header: [`include/face_input_driver.h`](include/face_input_driver.h).
Use the header's exact layouts and `FID_ABI_VERSION`; the included ctypes
example mirrors ABI version 1. It is not a stable cross-version serialization
format.

| Frame field | Meaning |
|---|---|
| `pointer_x` | `<0.5` left, `>0.5` right; distance from neutral controls velocity |
| `pointer_y` | `<0.5` up, `>0.5` down |
| `scroll` | `<0.5` scroll up, `>0.5` scroll down |
| `left_click`, `right_click` | Dwell-triggered complete click |
| `delete_key`, `insert_key` | Dwell-triggered complete key tap |

All seven fields are current levels, finite and within `[0,1]`. Invalid frames
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
threshold before dwell completes resets the dwell. Dragging/held keys are deferred.

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
        // Submit fresh neutral-button frames for at least one worker tick.
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
four button values to be below their release thresholds. The arming tick emits
no output. Submit a fresh neutral-button frame after enabling, and retain it
until `awaiting_neutral` is false. Calling enable while already enabled is
idempotent. Motion can use nonneutral axes once armed.

No valid frame for the timeout period latches output paused, even before the
first frame. Fresh input does not resume it: explicitly enable and rearm.
Async backend errors also pause output; inspect `last_error`, resolve the cause,
and enable again. Pause/destroy release any library-owned Linux keys/buttons.
No OS event is intentionally held between ticks.

API operations are internally serialized. Do not destroy a handle while other
threads call it. No C++ exceptions cross the ABI. This MVP is not hard real-time;
OS scheduling and application handling determine end-to-end latency.

`fid_get_status` reports output state, capabilities, asynchronous errors,
accepted/rejected frames, emitted events, and dropped journal records.
`fid_drain_events` destructively reads a bounded 1024-record journal on both
backends. Slow readers lose oldest records; output itself is not replayed or
queued for them. Dry-run capabilities represent modeled controls, not OS support.

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
