# App driver connection handoff

## Behavior

Reuvi requested connecting the finished Processing phase to the existing driver
and merging driverTest into main. Previously App stopped at command preview.
App now offers Preview, Driver dry run, and Live mouse + keyboard. Current gaming
eye activations produce one complete left/right click each; head directions hold
W/Space/Shift/S; precise pupils drive relative velocity. The existing mouse/scroll
mapping also connects. Mouse dragging is not implemented; this uses the existing
driver's click semantics, resolving the earlier plan's provisional held-mouse idea.

## Ownership and source

- Lane: integration, explicitly authorized App/Processing/Drivers handoff.
- Base main: `7175a89`; completed Processing implementation: `804f462`.
- Latest driverTest: `2e3e7349652af1eca2869ffd932738bde92133f9`, fetched and merged
  with its history intact. Shared connection contract landed first as `8b1679c`.
- Working branch: `work/reuvi/integration/gaming-signal-processing` in its existing
  isolated worktree. This handoff's introducing commit contains the connection.
- Changed paths: public driver bindings/adapter, additive C ABI functions and
  common emission path, App selection/lifecycle, Processing sink hook/UI, docs,
  tests and CI dry-run build. No Vision detection/calibration source changed.

## Contract impact

ABI v3 struct layouts and legacy `fid_submit` remain unchanged. `fid_abi_version`
allows validation before C struct access. `fid_submit_processed` consumes actions
immediately under the same mutex as the native worker, preserving ON/OFF and key
pulses between ticks. Invalid processed frames pause/release synchronously.
The C worker still drives motion and checks the no-frame watchdog independently.

`Drivers.binding` is shared with the standalone tester; `Drivers.output` validates
device_control_v1 and mouse_preview_v0 source age, ordering, origin, known flags,
finite ranges and lifecycle. Output ticks cannot renew source capture age. It
sets driver dwell/dead zone to zero after Processing shaping. Runtime pointer
speed maps directly to device units/second; scroll preview speed converts at
40 pixels per detent. Processing invokes the injected sink synchronously under
its lock; the UI journal is not a transport. Sink failures disarm Processing.

Native App output requires Camera and a fresh neutral command after Start; no
synthetic/replay native mode. Stop, source/mapping/settings/profile changes,
calibration, malformed/stale input and window close release output. Switching
away from Camera disconnects native output. No background service is installed;
no output choice/armed state is persisted. Escape works while App is focused.

## Verification actually performed

Tests used Python 3.12.5 and the compiled macOS backend in **dry-run mode**. No
camera was opened and no OS input was injected during verification.

| Command/check | Result |
| --- | --- |
| `cmake -S Drivers -B Drivers/build -DFID_NATIVE_BACKEND=ON -DCMAKE_OSX_DEPLOYMENT_TARGET=13.0` and `cmake --build Drivers/build -j 4` | Native macOS library and tests built successfully |
| `ctest --test-dir Drivers/build --output-on-failure` | 5/5 suites passed: control, C API, C header, standalone Python console, Processing adapter |
| `python3 -m unittest discover -s Drivers/tests -p test_output_adapter.py -v` | 8 adapter tests passed; also included in CTest |
| `python3 -m unittest discover -s tests/processing` | 98 tests passed |
| `RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration` | 113 tests passed, no skips, 61.324 seconds |
| `python3 -m App --headless --frames 490 --output dry-run` | 490/490 accepted at 30.00 Hz; 3 left + 3 right synthetic activation clicks, 4 key downs + 4 ups, 864 movement events; disabled/zero held keys at EOF |
| Same command with `--mapping mouse` | 490/490 accepted at 30.07 Hz; 2 left + 2 right clicks, 872 movement events, 8 scroll events; disabled/zero held keys at EOF |
| Ruff F, compileall, whitespace and integration scope checks | Passed |

The native integration suite covers UI output selection/status, short eye pulses
without periodic Processing ticks, combined held keys, source/mapping/settings
release, malformed input, simulated backend failure/disarming, synthetic-source
native rejection, Camera-to-demo native disconnect, and close/destroy. Adapter/C tests cover ordering, stale capture
provenance, independent real C watchdog, neutral arming, click latch behavior and
key event ordering. New CI builds the driver with native injection disabled before
running CTest and the Python integration suite.

## Run and remaining limits

From the main checkout after merge, follow [the connection guide](../docs/DRIVER_CONNECTION_GUIDE.md).
Build the library locally, start Camera, load/calibrate your profile, choose
Live mouse + keyboard → Connect output, then Start live control. Preview and
driver dry-run remain available. macOS requires existing Accessibility permission;
Linux uses the driver's existing uinput permissions. Permission errors stay visible
and leave output stopped. No permission/settings changes were made by this task.

Native code compiled on macOS; Linux backend source is unchanged. Human accuracy,
actual live OS/game behavior, Linux native input and permission-authorized camera
operation were not exercised. Dry-run event counts are synthetic software evidence.
Preserve other agents' checkouts and any later main changes when landing this branch.
