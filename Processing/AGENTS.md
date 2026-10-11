# Processing lane

**Current screen pointer:** read `../Contracts/SCREEN_POINTER.md`.
Gaming defaults to target position filtering and a fixation dead band, without
the velocity center gate/curve/acceleration. Target and velocity commands must
remain explicitly tagged; unknown targets have speed 0. Map files v4 retain v1/v2
as velocity and preserve v3 tuning. Both gaming and Mouse test have separate
downward boosts and lighter filters. Face profiles cannot restore old target
filtering or overwrite Mouse test pointer tuning. Face profiles stay v3.

**Current user decision — tongue retired:** read [../Contracts/TONGUE_RETIREMENT.md](../Contracts/TONGUE_RETIREMENT.md).
App and Vision lab have no tongue detection, worker, calibration, graphs or input
choice. App uses fixed pupils for pointer movement; preserve independent eyes and
head axes. Detector presets v11 migrate older files without restoring tongue.
This supersedes historical tongue requirements below.

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Processing/**` and
`tests/processing/**`. Keep profile logic, mappings, diagnostic UI, dependencies,
and lane documentation here. Put shared-change requests in `interface-requests/`.

- The current task is the mouse-only prototype in `mouse/`; read `README.md` here
  and `interface-requests/mouse-prototype.md`. Accept raw one-hot matrices/vectors
  and independent eye bits (`1 = closed`) through an adapter; SignalFrame v1 is
  also supported. Keep per-eye state independent, with no combined-eye gate. Calibrated camera
  `eye_intent` uses instantaneous sampled state without dwell/release timing;
  read `../Contracts/EYE_INTENT.md`. Legacy inputs retain their old timers.
- Keep the tester native and local: Python/Tk, no JavaScript, browser, or web server.
  Processing runs independently of drawing; preserve bounded histories and measure
  performance with the headless benchmark before adding runtime dependencies.
- App now integrates Vision through `Lab.ingest`; see `../App/README.md` and
  `../Contracts/MOUSE_MVP.md`. Preserve source ownership, actual rejected-input
  diagnostics, immediate `disconnect`, and equal-timestamp/new-sequence handling.
  `DesktopLab` remains usable independently; source-specific UI belongs to App.
- Output is currently `mouse_preview_v0`, pending the emulator teammate's format.
  Preserve `mouse/output.py` as the serialization boundary. Independent output
  sampling differs from the original draft ControlFrame v1; do not silently change
  shared contracts. Use injected clocks and fixtures without camera/OS dependencies.
- Implement calibration transforms, smoothing, per-signal confidence gates, dead
  zones, sensitivity curves, button dwell/debounce, and axis-to-velocity mappings.
- Persist local user/device profiles; keep detector parameters separate from device
  mappings. The adopted `face_mouse_profile_v3` (v1/v2 readable) is documented in
  `../Contracts/MOUSE_MVP.md`: Processing owns storage/top-level validation,
  Vision owns detector validation, App owns single-user profile application and disarming;
  camera reacquisition
  retains calibration, while loading may occur without a current face.
  Coordinate further shared profile changes with integration.
- Buttons are states, not repeated clicks. For legacy raw/replay only, use elapsed milliseconds for dwell; a
  frame count must not change behavior when sampling rate changes.
- Only process the subject/profile supplied by App (`single-user` for calibrated
  camera/demo; explicitly selected IDs for legacy replay). Invalid or stale required
  signals disable affected output; loss of the selected subject disables all output.
- Own oscilloscope traces and configuration screens; consume Vision's overlay via
  its public interface. App owns startup, camera lifecycle, and final wiring.
- Do not acquire camera hardware, import detector internals, or send OS/device events.
- Check threshold crossings, dwell/release, neutral dead zones, variable frame rate,
  out-of-order samples, missing signals, subject switching, and profile round trips.
  Add exact setup/run/test commands when implementation exists.

Read ../Contracts/ASYNC_DETECTION.md for neural tongue sample origins. Never
refresh a tongue observation using an enclosing fast frame's timestamp; accept
distinct origins once and expire the pointer independently of eye/head samples.
