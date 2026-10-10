# Drivers lane

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Drivers/**` and
`tests/drivers/**`. Preserve the existing `readme.MD`. Keep adapters, dependencies,
manual slider tools, and lane documentation here. Put shared requests in
`interface-requests/`.

- Accept ControlFrame v1 and start with a logging/mock adapter plus synthetic input.
  The driver must be testable independently of Vision and Processing.
- Accept finite normalized `[0, 1]` magnitudes. Map neutral axes at `0.5` to zero
  velocity. Interpret buttons consistently with the contract, tracking prior state.
- Support pointer movement, vertical scroll, left/right click, Delete, Insert, and
  a speech-to-text trigger. OS key/scroll details belong in platform adapters.
- Treat speech-to-text as a rising-edge request to an injected speech service;
  do not invent a speech engine or credentials. Gamepad emulation is a later adapter.
- Default to logging. Live output requires explicit runtime enablement, a calibrated
  selected profile, and a stop control. A driver watchdog runs even if no more frames
  arrive, releasing held inputs on disable, disconnect, timeout, or shutdown.
- Reject malformed, nonfinite, out-of-range, duplicate, and out-of-order input
  appropriately; invalid input disables output. Never leave a held button stuck.
- Check boundaries `0`, `0.5`, `1`, press/hold/release transitions, duplicate frames,
  stale/no-frame timeouts, stop, and cleanup without injecting real events in tests.
  Document supported OS, required permissions, and setup/run/test commands.
