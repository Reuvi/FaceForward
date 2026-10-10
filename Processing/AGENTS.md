# Processing lane

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Processing/**` and
`tests/processing/**`. Keep profile logic, mappings, diagnostic UI, dependencies,
and lane documentation here. Put shared-change requests in `interface-requests/`.

- The current task is the mouse-only prototype in `mouse/`; read `README.md` here
  and `interface-requests/mouse-prototype.md`. Accept raw one-hot matrices/vectors
  and independent eye bits (`1 = closed`) through an adapter; SignalFrame v1 is
  also supported. Keep per-eye timing/state independent, with no combined-eye gate.
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
  mappings. The adopted `face_mouse_profile_v1` is documented in
  `../Contracts/MOUSE_MVP.md`: Processing owns storage/top-level validation,
  Vision owns detector validation, App owns fresh selected-face binding and disarming.
  Coordinate further shared profile changes with integration.
- Buttons are states, not repeated clicks. Use elapsed milliseconds for dwell; a
  frame count must not change behavior when sampling rate changes.
- Only process the explicitly selected subject/profile. Invalid or stale required
  signals disable affected output; loss of the selected subject disables all output.
- Own oscilloscope traces and configuration screens; consume Vision's overlay via
  its public interface. App owns startup, camera lifecycle, and final wiring.
- Do not acquire camera hardware, import detector internals, or send OS/device events.
- Check threshold crossings, dwell/release, neutral dead zones, variable frame rate,
  out-of-order samples, missing signals, subject switching, and profile round trips.
  Add exact setup/run/test commands when implementation exists.
