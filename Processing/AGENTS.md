# Processing lane

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Processing/**` and
`tests/processing/**`. Keep profile logic, mappings, diagnostic UI, dependencies,
and lane documentation here. Put shared-change requests in `interface-requests/`.

- Consume SignalFrame v1 and emit a full ControlFrame v1. Use injected clocks and
  fixture streams so deterministic development needs neither camera nor OS driver.
- Implement calibration transforms, smoothing, per-signal confidence gates, dead
  zones, sensitivity curves, button dwell/debounce, and axis-to-velocity mappings.
- Persist local user/device profiles; keep detector parameters separate from device
  mappings. Coordinate any shared profile format with integration before adopting it.
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
