# Test the mouse and keyboard driver

This is the teammate quick start. No camera or processing component is needed.
The driver is C++ with a C-compatible API; the terminal tester uses Python's
standard-library `ctypes` to call that same library.

Start in **dry-run**: it reports generated actions without moving the real mouse
or sending keys. **Live mode** (`--native`) sends input to the desktop/focused app.
The tester starts paused and pauses again after each trial.

## 1. Build on your operating system

All commands below start inside `Drivers/`. From the repository root, run
`cd Drivers` once. Build on the OS where you will run the tester; Linux `.so`
files cannot be used on macOS, which builds a `.dylib`.

### Linux

You need CMake, a C++17 compiler, pkg-config, libevdev development headers, and
Python 3.9+. Example dependency commands (choose your distribution):

```sh
# Ubuntu/Debian
sudo apt install build-essential cmake pkg-config libevdev-dev python3 acl

# Arch Linux
sudo pacman -S --needed base-devel cmake pkgconf libevdev python acl
```

Ubuntu provides the headers in [libevdev-dev](https://packages.ubuntu.com/noble/libevdev-dev);
Arch includes them with [libevdev](https://archlinux.org/packages/extra/x86_64/libevdev/).

Build and check:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j 4
ctest --test-dir build --output-on-failure
python3 examples/python_ctypes.py --interactive
```

Dry-run requires no `/dev/uinput` access. To check the live backend:

```sh
python3 examples/python_ctypes.py --native --probe
```

This creates temporary virtual devices and exits while paused; it does not emit
input actions. If `/dev/uinput` is missing, an administrator can load the host's
existing module:

```sh
sudo modprobe uinput
ls -l /dev/uinput
```

If access is denied, grant only your account temporary read/write access:

```sh
sudo setfacl -m "u:$(id -un):rw" /dev/uinput
python3 examples/python_ctypes.py --native --probe
```

Run the tester as your regular user. This temporary permission can disappear
after reboot/device recreation. Persistent udev setup and container requirements
are in [the driver reference](../readme.MD#linux-setup). These setup commands are
manual; the tester does not install packages or alter permissions.

When the probe succeeds:

```sh
python3 examples/python_ctypes.py --interactive --native
```

The backend uses the kernel input path for Wayland/X11. The actual desktop must
discover and accept the virtual devices; live verification is still required.

### macOS

You need macOS 10.15+, Xcode Command Line Tools, CMake, and Python 3.9+.
Install Apple's tools if needed:

```sh
xcode-select --install
```

Apple documents the [Command Line Tools installation](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools/).
If you already use Homebrew, install CMake and Python with:

```sh
brew install cmake python
```

CMake is available as a [Homebrew formula](https://formulae.brew.sh/formula/cmake.html).
Build and check:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j 4
ctest --test-dir build --output-on-failure
python3 examples/python_ctypes.py --interactive
python3 examples/python_ctypes.py --native --probe
```

For a permission error, grant Accessibility access in **System Settings → Privacy
& Security → Accessibility** (older macOS: System Preferences → Security & Privacy).
Permission belongs to the process loading the library: Python for this tester,
your executable for C++, and possibly the terminal/launcher. Relaunch and repeat
the probe. Keep the host executable in a stable location while testing.

Then run:

```sh
python3 examples/python_ctypes.py --interactive --native
```

Pointer movement is restricted to the primary display. Insert is the macOS
Help/Insert-position key and may have no overwrite behavior in your application.
The status command labels that limitation. Mac compilation/live results must
be recorded on a Mac; a passing Linux build does not verify them.

## 2. Try named commands

At `test>`, type one command and press Enter:

| Command | Expected result |
| --- | --- |
| `move 0.65 0.5` | Move right at a moderate speed |
| `move 0.35 0.5` | Move left |
| `move 0.5 0.2` | Move up |
| `move 0.5 0.8` | Move down |
| `move 0.5 0.5` | Neutral; no movement |
| `scroll 0.8` / `scroll 0.2` | Scroll down / up |
| `click left` / `click right` | Exactly one complete click |
| `key delete` | Exactly one forward Delete |
| `key insert` | One Insert-position key; behavior varies on macOS |
| `status` | Mode, trial/output state, capabilities, counters, and errors |
| `stop` | Cancel the trial or focus delay immediately and pause output |
| `help` | Show commands and examples |
| `quit` | Stop the producer, close the library, and exit |

Axis values are **0–1**, with **0.5 neutral**. The current driver's default dead
zone is 0.45–0.55. Smaller values mean left/up; larger values mean right/down.
These are velocity levels, not coordinates. Commands activate button values at
1; 0 is inactive. The tester does not interpret eye openness or facial gestures.

Each trial runs for **one second**, then pauses automatically. You can enter
`status` or `stop` while it runs. A second trial is rejected while another is
active; commands are not queued. Repeating `click left` after completion produces
another click because each trial first sends neutral button levels.

In live mode there is a **three-second focus delay** before every trial. After
Enter, switch to the target app, then return to the terminal when the trial ends.
For scroll, place the pointer over the scrollable area. For Delete/Insert, focus
a disposable text document. Ctrl-C stops output and exits, including during the
focus delay or trial; Ctrl-D/EOF also exits.

Change trial settings at launch:

```sh
python3 examples/python_ctypes.py --interactive --duration 2 --rate 30
python3 examples/python_ctypes.py --interactive --native --duration 1 --delay 5
```

Duration is 0.2–10 seconds; delay is 0–30 seconds; rate is 30 or 60 Hz. The tester
supplies frames continuously during a trial and pauses while you type; the
driver's independent 250 ms watchdog is unchanged.

Advanced input remains available:

```text
frame 0.65 0.5 0.5 0 0 0 0
0.65 0.5 0.5 0 0 0 0
```

The seven fields are X, Y, scroll, left click, right click, Delete, and Insert.
All must be finite and in `[0,1]`. Named commands fill unrelated fields with
neutral/inactive levels so you only specify the action being tested.

## 3. Evaluate the results

Example dry-run result:

```text
Trial: Left click. Duration: 1 seconds.
Finished: Left click — left click: 1. Output paused.
```

Movement summaries show direction and total units; scroll shows direction and
detents. Timing can change the exact totals. Linux pointer units are relative
mouse counts subject to desktop acceleration; macOS uses Quartz coordinates.

`Accepted frames` counts valid input samples, not tests passed. `Emitted actions`
counts generated movement/scroll/click/key actions. A trial can accept many frames
while producing only one click. Rejected frames count invalid submissions.

In dry-run, results prove that the library generated actions. In live mode, the
backend reports posted/written events; it cannot confirm that the target app
consumed them. Confirm the visible behavior yourself. This tester exercises the
current prototype `fid_frame` API; it does not yet consume the full shared
`ControlFrame` envelope. Shared-contract integration is a separate task.

### Troubleshooting

| Message/symptom | Next step |
| --- | --- |
| Shared library not found | Build inside Drivers, or pass `--library /absolute/path/to/library` |
| Could not load / wrong architecture | Rebuild on this OS; use the same architecture as Python |
| Linux backend unavailable | Check host `/dev/uinput`; load the module or expose the device to the container |
| Input permission denied on Linux | Check `ls -l`/`getfacl`, then account-specific access as above |
| Input permission denied on macOS | Grant the actual Python host Accessibility access and relaunch |
| Backend unsupported in this build | Reconfigure with `-DFID_NATIVE_BACKEND=ON` and rebuild |
| Dry-run prints actions but nothing moves | Expected; use explicit `--native` for real OS input |
| Live actions logged but no visible effect | Check target focus, permissions, device discovery, and the app's key behavior |
| Trial already running | Wait for completion or use `stop`; then send the next command |
| Output stopped / watchdog timed out | Read `status`; stop, resolve the cause, then start a new trial to rearm |
| Insert does nothing on macOS | The mapping is limited; check the target app rather than treating it as paste |

For a dry-run build without libevdev, use:

```sh
cmake -S . -B build-dry -DFID_NATIVE_BACKEND=OFF
cmake --build build-dry -j 4
ctest --test-dir build-dry --output-on-failure
python3 examples/python_ctypes.py --interactive --library "$PWD/build-dry/libface_input_driver.so"
```

On macOS, change the last filename to `libface_input_driver.dylib`.

## 4. Call the same library from your component

The implementation is C++, exported with a C-compatible ABI. You can call it
from C++ or Python without running the terminal tester. No pip dependency is
needed for ctypes. The library is built as `.so` on Linux or `.dylib` on macOS.

The lifecycle is **default config → create → enable → send fresh neutral frames
until armed → stream frames → pause → destroy**. Check every return value and
asynchronous status error; never destroy a handle while a producer still uses it.

### C++

Include [face_input_driver.h](../include/face_input_driver.h) and link the
`face_input_driver` CMake target. If your own CMake project includes this
component, use `add_subdirectory(path/to/Drivers)` and
`target_link_libraries(your_target PRIVATE face_input_driver)` with the correct
relative path in your project. The target supplies the public include directory.
The [C++ example](../examples/demo.cpp) shows continuous submission and cleanup.

### Python

Add `Drivers/examples` to your Python module path and import these helpers from
[python_ctypes.py](../examples/python_ctypes.py):

```python
import ctypes as ct
from python_ctypes import Config, Frame, Status, load_driver

lib = load_driver("/absolute/path/to/Drivers/build/libface_input_driver.so")
# Use .dylib on macOS.

def check(code):
    if code:
        raise RuntimeError(lib.fid_result_string(code).decode())

config = Config()
lib.fid_default_config(ct.byref(config))  # Dry-run unless backend is changed.
handle = ct.c_void_p()
check(lib.fid_create(ct.byref(config), ct.byref(handle)))
try:
    check(lib.fid_enable(handle))
    frame = Frame()
    lib.fid_neutral_frame(ct.byref(frame))
    # Submit fresh neutral frames at 30–60 Hz until awaiting_neutral is false.
    # Then keep sending your processing frames; a single submission is not a loop.
    check(lib.fid_submit(handle, ct.byref(frame)))
    status = Status()
    check(lib.fid_get_status(handle, ct.byref(status)))
finally:
    lib.fid_pause(handle)
    lib.fid_destroy(handle)
```

This snippet demonstrates API ownership, not a complete producer loop. See the
example's automatic demo or terminal session for the loop. The current `fid_frame`
fields, exact ABI layouts, defaults, and limitations are documented in
[the driver reference](../readme.MD#input-contract). Contract changes and Xbox-style
controller support remain separate future work.
