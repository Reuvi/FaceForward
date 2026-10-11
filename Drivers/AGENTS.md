**Current presentation mode:** read [../Contracts/PRESENTATION_MODE.md](../Contracts/PRESENTATION_MODE.md). A separate mapping adds head movement, continuous mouth braking, left-eye click/drag, right-eye Enter and both-eyes dictation. Plain open/closed is its default; combined gesture timing supersedes independent instant eyes only in this explicit mode. Older maps are unchanged. Mapping v9 and additive ABI v3 APIs preserve old formats.

**Current button layout:** read [Mouth buttons and relative movement](../Contracts/MOUTH_BUTTON_RELATIVE.md). Mouse test maps left eye → W, right eye → left click, mouth open → Space, and head X/Y → relative mouse movement. Mapping v8 preserves older imported assignments; mouth needs no calibration.

# Drivers lane

**Current screen pointer:** `../Contracts/SCREEN_POINTER.md` adopts the existing
ABI v3 target mode for App. The adapter validates explicit target coordinates,
speed, freshness and mode transitions. Speed 0 must never call the movement
backend. Report normalized primary-display position and arrival; keep velocity
behavior, independent watchdog and held-key release intact.

App now uses the public `binding.py` and `output.py`; read
`../Contracts/DRIVER_CONNECTION.md`. Preserve ABI v3 struct layouts and the legacy
`fid_submit` tools. The additive `fid_submit_processed` path consumes processed
click/key transitions synchronously with zero extra dwell/dead zone configured
by the adapter. Both paths retain the independent C watchdog. Default App output
is preview; native is explicit and stops on App close. Test through dry-run.

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
