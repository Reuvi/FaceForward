# Input driver handoff

Last updated: 2026-10-10. Owner of this update: repository implementation agent.

## Latest change — ABI v3 held-key state

- Goal: add continuous W/A/S/D, Space, and left Shift state to the Driver so
  Processing can hold/release keys by sending complete snapshots. No dictation,
  Windows support, or Xbox/gamepad emulation was added.
- Public ABI is now v3. `fid_frame.keys_down` uses `FID_KEY_*` bit flags;
  `fid_status.held_key_mask` reports current logical state; event types 7/8 are
  key-down/key-up and carry the key bit in `fid_event.x`.
- Repeated frames with an unchanged key mask produce no transitions. Shift goes
  down before other keys and up after them. The frame must be key-neutral to
  arm. Pause, watchdog expiry, backend errors, and destroy release active keys.
  The driver does not generate keyboard repeat.
- Linux maps to evdev/uinput codes; macOS maps to Quartz virtual key codes. The
  Python tester supports finite `hold w shift` trials and reports held keys.
  `examples/wasd_w_hold_test.py` waits five seconds, sends 180 W-down frames at
  60 Hz by default (about three seconds), then sends release state and pauses. Use `--native` for a
  Roblox test; dry-run is the default. It confirms Driver transitions, not that
  Roblox consumed the events.
  Dry-run tests cover held, clear, repeat-free, pause-release, validation, and
  ordering behavior. Linux native backend compiled successfully in this turn;
  live input was not tested. macOS source was not compiled on an Apple host.
- ABI v2 C structure consumers are incompatible: rebuild the library and all
  ctypes/C/C++ callers together. The Python tester now rejects non-v3 libraries.
- Shared `Contracts/README.md` remains untouched. The proposed binary `keys`
  snapshot and integration semantics are recorded in
  `interface-requests/held-key-state.md`; integration must agree before cross-
  component adoption.
- Verification: the W test passed in dry-run and the terminal tester
  suite passes with its short W-hold integration check. Dry-run and
  Linux-native Debug builds each passed all four CTest suites. Python syntax
  compilation passed with bytecode redirected to
  `/tmp` because the workspace cache path is read-only. No commit or push was made.

### Next work

1. Rebuild and run on macOS to verify Quartz key events, especially left Shift,
   with Accessibility permission; then test Linux live key holds where uinput
   access is available.
2. Have Processing/integration owners approve field naming and complete-snapshot
   semantics; update the shared contract only through its owner.
3. Test held keys in a harmless text editor or browser page before any game.
4. Keep ABI v3 consumers synchronized; do not load an ABI v2 library into the
   updated Python tester.

### Mistakes and boundaries

- Do not model held WASD/Shift as repeated taps. A set bit holds; a cleared bit
  releases. A stable set bit must not generate repeated key-down events.
- Do not assume synthetic dry-run or successful compilation proves a desktop or
  game accepts the key events.
- Do not edit `Contracts/README.md` from the Drivers lane; the request document
  is the handoff point.
- Do not stage, commit, or push unless the user explicitly asks.

## Previous change — explicit pointer target mode

- User objective: add an endpoint command with independent speed while retaining
  continuous velocity axes for joystick/gaze, clarify the Processing→Drivers
  interface, and focus this work on the driver component.
- Implemented ABI v2 in `include/face_input_driver.h`: `fid_frame.pointer_mode`
  selects velocity or target mode. Existing `pointer_x/pointer_y` continue to
  mean velocity axes. Target fields are normalized primary-display
  `target_x/target_y` plus normalized `target_speed`; default max target speed is
  600 display units/second. Status now reports current position, target,
  requested speed, measured step velocity, and arrival.
- Target movement is straight-line constant speed, clamps the final step, and
  stops at the endpoint. A later frame can update target/speed, and another
  target moves back. Compare different speeds from the same starting position.
- Native macOS target movement uses Quartz main-display geometry. Linux target
  mode requires X11 + XRandR and an X11 session; pure Wayland is explicitly
  unsupported for absolute target mode. Linux relative uinput velocity stays
  available there. Dry-run simulates a 1920×1080 display centered initially.
- Tester commands are now `move SPEED X Y` for target mode and `velocity X Y`
  for the original continuous axes. Target trials stream until arrival (30 s
  safety limit), print position/target/speed/velocity, then pause. Velocity and
  action trials retain the duration setting. `testing/README.md` and
  `readme.MD` describe syntax, values, OS support, and the ABI.
- Added `Drivers/architecture.md` to explain why controller/joystick axes keep
  velocity semantics, plus `Drivers/interface-requests/target-pointer-mode.md`
  proposing shared-contract fields. `Contracts/README.md` remains untouched;
  integration ownership belongs to the contract lane.
- Open interface decision: the current `control.cpp` still applies the
  configurable dead zone and linear response curve on velocity axes, while the
  shared contract assigns value shaping to Processing. Team must agree on one
  owner before integrating; do not apply the response curve in both places.
- Verification so far: Linux native-enabled Debug build succeeded in
  `/tmp/fid-build`; all four CTest suites passed (control, C API, C header,
  Python tester). This host is Wayland and has no `/dev/uinput`, so native live
  movement was not tested. macOS compile/live validation remains pending.
- A review caught that re-emitting an absolute target step as relative uinput
  would move twice. Target steps now write to the backend's absolute path and
  enter the event journal without being emitted a second time.
- No stage, commit, push, or live GitHub update was performed.

### Next work

1. On macOS, compile and test target movement, velocity, and event posting with
   Accessibility permission; record OS and host app results.
2. On Linux X11 with XRandR, test pointer query/warp and target arrival on a
   live desktop. On Wayland, confirm target commands return unsupported while
   velocity output still works after uinput is available.
3. Ask the Processing/contract owners to agree field names and response-curve
   ownership. The proposed contract is in `interface-requests/`.
4. Keep all C ABI/ctypes consumers on the current ABI v3. This ABI prototype is not a
   stable wire format.
5. Add/verify same-destination speed comparison from a controlled start
   position during live desktop testing. Buttons remain threshold/dwell taps;
   align that separately with the shared held-state button contract.

### Keep these boundaries

- Do not reinterpret `pointer_x/pointer_y` as screen coordinates. Keep the mode
  explicit so future joystick/gaze axes remain velocity controls.
- Do not edit the integration-owned `Contracts/README.md` from Drivers; send
  shared field changes through the proposal and coordinate with that owner.
- Do not claim native target movement works on Wayland. Do not claim live OS
  behavior from dry-run or compile-only checks.
- Dictation stays in phase 2; Windows and gamepad emulation are not part of this
  implementation.

## Goals and direction

Phase 1: a C++17 userspace library for Linux and macOS that accepts normalized
controls and emits pointer, vertical scroll, left/right click, forward Delete,
and Insert-position key events. Phase 2: native Dictation activation later.
Windows is outside both MVP phases. Keep processing/CV independent of OS code.


## Item 2 testing usability — completed

- Authorized scope: Drivers only, named terminal commands and a teammate testing
  README. Item 1, GUI work, shared-contract integration, Dictation, and Xbox
  emulation remain excluded. No staging, commits, or publishing authorized.
- Lane: Drivers. Existing private branch: `work/dog/drivers/repair-layout`.
  Base remains `5e22272`; remote history was fetched before this work.
- Backup and prepared changes: `/tmp/driver-item2-02m3qm7u`. `before` holds the
  previous component source and `manifest.json` records baseline hashes.
- Added move/scroll/click/key commands, help/status/stop/quit, retained numeric
  frames, and a background finite-trial producer. Stop cancels during a trial or
  focus delay; active trials reject additional trials rather than queue them.
- Default output remains dry-run. Each trial starts with neutral frames, streams
  for one second, settles neutral, then pauses. Native trials allow three seconds
  to focus an application. Existing duration/delay/rate/library overrides remain.
- Added readable setup failures and a Python `--probe` so the actual Python host
  can check backend readiness without emitting actions. Added readable direction,
  click/key counts, capabilities, frame/action counters, and trial/error status.
- Teammate quick start: `Drivers/testing/README.md`. Covers separate Linux/macOS
  setup/run instructions, permissions, named commands, expected results,
  troubleshooting, and calling the same C-compatible library from Python/C++.
  `Drivers/readme.MD` remains the detailed reference and links the quick start.
- Driver core/backends/header are unchanged. The current prototype fid_frame
  API is not the complete shared ControlFrame envelope; no new contract or
  facial-mapping proposal was implemented as part of item 2.
- Added 15 dry-run Python checks for parsing, nonfinite/range rejection, control
  commands, readable errors, motion at 30/60 Hz, button rearming, concurrent-trial
  rejection, stop during activity/focus delay, EOF/quit/probe, and Ctrl-C cleanup.
  CMake includes these as `testing_console` when Python 3.9+ is available.
- Final verification passed: native-enabled Debug and dry-run-only Release
  builds each passed all four CTest suites, including the 15 Python tester checks.
  Python probes from root/Drivers, interactive help/status/stop/quit, the existing
  automatic Python demo, and the existing C++ dry-run demo all passed.
  Runtime core/backends/header and original tests match the baseline hashes.
  Driver scope and whitespace checks passed; the index remains empty.
  Live Linux/macOS acceptance remains a manual target-host check.

## Item 3 recovery — completed

The recovery revision covered item 3 only. Item 2 is now separately authorized
and recorded below; item 1 remains pending.

- Lane: Drivers. Task: repair layout. Local branch:
  `work/dog/drivers/repair-layout`. Base: remote main at `5e22272`.
- User instruction: no staging, local commits, pushes, or publishing during
  recovery. Main was fast-forwarded to existing remote commits, not rewritten.
- Complete pre-recovery checkout backup:
  `/tmp/driver-item3-backup-p4mx5i10/checkout`. Original local source and root build
  caches also preserved under `displaced-local-work` in that backup directory.
  The source/document manifest verified 17 files before changes.
- Restored all driver source from the verified backup while retaining the remote
  `Drivers/AGENTS.md`. The remote shared `.gitignore`, docs, contracts, and tooling
  remain intact. No component behavior or shared-contract implementation changed.
- CMake project/testing setup moved into `Drivers/CMakeLists.txt`; driver ignore
  rules are in `Drivers/.gitignore`; this handoff moved into `Drivers/passoff.md`.
  There is no driver-generated root CMake project or handoff file anymore.
- Python's default shared library is relative to its own component directory:
  `Drivers/build/libface_input_driver.so` or `.dylib`. `--library` is retained.
- Build commands from repository root: `cmake -S Drivers -B Drivers/build`,
  `cmake --build Drivers/build -j 4`,
  `ctest --test-dir Drivers/build --output-on-failure`.
  Or change into Drivers and use `cmake -S . -B build` etc.
- Checkout moved to `/home/dog/Projects/hackathon` (one level up). Reopen the
  editor/workspace at this location; the former nested checkout no longer exists.
  The empty original wrapper is retained at
  `/home/dog/Projects/hackathon-item3-container`. Archived CMake caches were not
  reused; fresh native-enabled and dry-run-only builds are under Drivers.
- Local branch tracks `origin/main`; use `git pull --ff-only` for explicit
  fast-forward updates. Current local main, driver branch, and fetched origin/main
  all point to existing commit `5e22272`. No staging, commits, or pushes occurred.
  Driver edits intentionally remain unstaged/untracked for review.
- A `.vscode/settings.json` appeared during recovery with the old absolute CMake
  source directory. Its original contents are backed up as
  `vscode-settings-before-move.json` in the backup directory. The local setting
  now points to `/home/dog/Projects/hackathon/Drivers` and is excluded through
  `.git/info/exclude`; shared `.gitignore` was not changed.
- Recovery verification passed: native-enabled Debug build (3/3 CTest suites),
  standalone dry-run-only Release build (3/3 suites), and four manual trial/library
  lookup checks (repository root, Drivers directory, unrelated directory, and
  explicit alternate library). Each trial generated exactly one dry-run left
  click. The C++ dry-run probe also passed while paused.
- `python3 tools/check_scope.py --base origin/main --lane drivers` passed with
  16 driver-owned changed paths; `git diff --check` passed; the index is empty.
  Shared files match origin/main. Verification details are also recorded in
  `item3-verification.json` inside the backup directory.
- Historical verification below refers to the old layout. Item 3 is complete.
  The named-command tester was a separate item 2 change and has since been
  updated with target and velocity commands; the shared contract remains owned
  by its integration lane.

## Current implementation status

- Implemented the C-compatible ABI in `Drivers/include/face_input_driver.h`.
  It can be called directly from C++ or through Python ctypes. ABI version 3;
  consumers need the matching current header and ctypes layouts.
- Implemented the shared control core, 60 Hz worker, validation, configurable
  thresholds/dead zones/speeds, one-tap activations, pause/watchdog/rearming, and
  bounded event journal. Configuration is immutable for an instance.
- Implemented Linux libevdev/uinput velocity and held-key mode, optional
  X11/XRandR target mode, and macOS Quartz velocity/target/held-key backend
  source. macOS source has not been compiled on an Apple host.
- Added CMake builds, C++ synthetic/stdin/probe demo, Python ctypes example,
  dry-run backend, and automated control/C API/C header tests.
- Tester commands are `move SPEED X Y` (target) and `velocity X Y` (continuous
  axes), plus scroll/click/key. Target trials run until arrival with a 30-second
  limit; velocity/action trials use the duration setting and then pause.
- Added teammate and technical guides in `Drivers/testing/README.md` and
  `Drivers/readme.MD`. `Drivers/architecture.md` explains the two modes;
  `Drivers/interface-requests/target-pointer-mode.md` proposes shared fields.
- Linux native-enabled Debug and dry-run-only Release builds passed all four
  CTest suites, including same-target/different-speed arrival checks and Python
  tester tests. Scope and whitespace checks passed. Linux live movement and
  macOS compilation/live movement remain unverified on target hosts.

## Main integration parts

- API: `fid_default_config`, `fid_create`, `fid_enable`, `fid_submit`,
  `fid_pause`, `fid_get_status`, `fid_drain_events`, `fid_destroy`.
- Frames: explicit `FID_POINTER_VELOCITY` (existing X/Y speed axes) or
  `FID_POINTER_TARGET` (normalized destination plus normalized speed), scroll,
  left/right click, Delete, Insert. All numeric levels are finite `[0,1]`. No
  Dictation field yet.
- Default axis neutral `0.5` is temporary/configurable; dead zone `0.45–0.55`.
  Smaller values mean left/up, larger right/down. Pointer 600 units/sec per
  axis; scroll 12 detents/sec; target max 600 primary-display units/sec. Linux
  velocity units are relative counts subject to acceleration; target mode uses
  X11 display coordinates. macOS uses Quartz display coordinates.
- Button defaults: strictly above `0.7` for 150 ms triggers one tap; strictly
  below `0.3` rearms. Individual button settings can differ.
- Creation starts paused/dry-run. Explicit enable discards older frames. Submit
  fresh neutral-button frames until status no longer awaits neutral; then stream
  frames at 30–60 Hz. The worker uses the latest frame, so do not send brief pulses.
- 250 ms without valid input pauses until explicit enable and rearming. A late
  frame cannot erase an expired watchdog before the worker notices it.
- Processing selects one active user and owns face detection/calibration/mapping.
  Do not merge frames from two people into OS output.
- Linux creates separate virtual mouse/keyboard devices; `/dev/uinput` is
  required. macOS requires event-posting permission for the process hosting the
  library. Check all synchronous return values and asynchronous status errors.

## Verification

Environment: Linux 6.18.13-arch1-1, Wayland; GCC 15.2.1, CMake 4.2.3,
libevdev 1.13.6. `/dev/uinput` is absent. No Mac is accessible in this workspace.

- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug`
- `cmake --build build -j 4`
- `ctest --test-dir build --output-on-failure`
- Final Linux native-enabled Debug build passed, including the watchdog,
  keyboard-classification, and exact dead-zone boundary fixes. All three CTest
  suites passed: control (73 checks), C API/worker/watchdog, C header linkage.
- `cmake -S . -B build-dry -DFID_NATIVE_BACKEND=OFF -DCMAKE_BUILD_TYPE=Release`
  followed by build and CTest also passed all three suites.
- `./build/Drivers/driver_demo --rate 30` and `--rate 60` passed. Each produced
  exactly one left click, right click, Delete, and Insert; both logged 108 total
  horizontal units and six downward scroll detents in this run. Synthetic
  event totals were 59 each; accepted frames were 128 and 252 respectively.
- `python3 Drivers/examples/python_ctypes.py` passed through the shared library:
  120 accepted frames and 60 movement events in this run.
- Interactive tester checks passed: malformed/NaN input rejected; movement,
  scroll, left/right click, Delete, and Insert trials produced expected actions;
  repeating the same left-click command produced a second click through neutral
  rearming. Seven trial commands passed. EOF and Ctrl-C during an active trial
  exited cleanly and destroyed the driver handle. Native tests remain pending.
- `./build/Drivers/driver_demo --native --probe` returned the expected
  `FID_BACKEND_UNAVAILABLE` failure with `/dev/uinput` absent; no live actions.
- `git diff --check` passed. Build artifacts are ignored and uncommitted.
- Temporary example logs are in `/tmp/face-driver-demo-30.log`,
  `/tmp/face-driver-demo-60.log`, and `/tmp/face-driver-python.log` on this host.
  They are not portable handoff artifacts; results above are the durable record.
- Portable control/C ABI checks do not prove that a compositor or Mac application
  accepts actual input.

| Capability | Implemented | Verified |
|---|---|---|
| Shared core / dry-run / C ABI | Yes | Automated Linux checks |
| Linux native backend | Yes | Compilation and unavailable-device error; live events pending |
| macOS native backend | Source written | Mac compile/live tests pending |
| Python ctypes | Yes | Linux dry-run integration passed |
| Dictation / Windows | No | Intentionally excluded |

## Mistakes and resolutions

- First Linux build relied on a transitive initializer-list include. Replaced
  the braced range with an explicit array; build then passed.
- Review found a late submit could refresh the watchdog before a delayed worker
  observed expiry. Submission now latches the expired state; regression added.
- Review found minimal keyboard capabilities could affect desktop classification.
  Advertise the standard key block for udev identification, while only emitting
  Delete/Insert. Actual desktop discovery still needs live verification.
- Review found floating-point subtraction could make the exact `0.55` dead-zone
  boundary yield a tiny velocity. Compare against explicit lower/upper bounds;
  both boundary tests now require exactly zero.
- The original `--stdin` stream was impractical for a human typing between
  frames: the 250 ms watchdog expires. Added a finite-trial interactive tester
  that supplies a 30/60 Hz stream during trials and pauses while waiting for
  input. The library's watchdog and original streaming contract are unchanged.

## To dos

1. On a Mac, build with the Apple SDK, grant Accessibility access to the actual
   host, probe, and test pointer/scroll/click/Delete in ordinary applications.
   Record macOS version, architecture, host process, and application results.
2. On Linux with host `/dev/uinput` access, probe and test on the target desktop.
   Record distro/session type, device discovery, pointer/scroll direction, and
   key delivery. Do not mark live support verified from compilation alone.
3. Verify macOS Help/Insert-position behavior in the intended application. It is
   labeled `FID_CAP_INSERT_LIMITED`; do not promise an overwrite toggle.
4. Connect the processing producer through C++ or ctypes, check frame cadence,
   initial neutral gating, invalid values, input loss, and explicit resume.
5. Tune settings for the demo user and rehearse against disposable documents.

## To not dos

- Do not implement Windows or Dictation during phase 1.
- Do not write custom kernel drivers or mix face tracking into this library.
- Do not change normalized mapping without updating the header/docs/examples.
- Do not add repeating clicks, automatic Delete repetition, dragging, or held
  keys to phase 1 without revisiting activation and release behavior.
- Do not substitute paste for literal Insert or hide macOS limitations.
- Do not use world-writable uinput permissions as the default setup.
- Do not claim live OS support based on dry-run tests or silently resume after
  a timeout. Do not destroy a handle while other threads still use it.

## Future work

Phase 2: a distinct native Dictation shortcut action, macOS first; optional
Linux activation only where a suitable speech service exists. Transcription
stays outside the driver. Later: richer device configuration, dragging/held
controls, multi-monitor behavior, packaging, and controller emulation.

## Update convention

Each member's agent should update this record after meaningful changes,
verification, or failed approaches: timestamp/author, completed behavior, exact
commands/results, remaining blockers, and next action. Preserve resolved mistakes
as useful context. Distinguish source written, compiled, dry-run tested, and
live tested. Do not put credentials or private user data in this file.
