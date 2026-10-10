# Vision lane

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Vision/**` and
`tests/vision/**`. Keep implementation, dependencies, example capture tools, and
lane documentation here. Put requests for shared changes in `interface-requests/`.

- Keep the runtime native, local, and efficient: no browser, JavaScript, web server,
  HTTP transport, remote inference, or runtime model downloads. Load MediaPipe
  models from local files and pass SignalFrame dictionaries directly in process.
- Processing's native Python/Tk lab accepts SignalFrame v1 via `Lab.ingest(frame)`
  in external-source mode. Keep Vision's continuous values and `*_eye_open`
  polarity (1 = open); its separate raw adapter uses 1 = closed. App owns wiring.
- That wiring now runs as `python3 -m App`; read `../App/README.md` and
  `../Contracts/MOUSE_MVP.md`. `mouse_demo.py` deliberately supplies synthetic
  values for all four mouse behaviors. Do not confuse that fixture with live
  head/tongue detection or calibrated camera signals.
- Keep inference off Tk's UI thread. Detection, processing, and drawing have
  separate cadences; preview work is optional. Avoid growing queues and measure
  overhead with `python3 -m Vision.benchmark` before adding runtime dependencies.
- Capture/sample at a configurable rate and report actual timing, not an assumed FPS.
- Camera inference requests one face. The calibration workbench emits at most one
  logical `single-user` observation, preserving fits across geometric reassociation,
  loss, stale frames and same-source restart. Generic v1/replay retains its legacy
  two-observation capacity. Emit calibrated measurements and explicit confidence/validity for every signal.
- Track gaze/pupils, tongue position when available, each eye's openness, and head
  horizontal/vertical bias. Mark unsupported/occluded features invalid; do not fake
  a detector. Keep detector feasibility and performance limitations visible.
- Own detection-calibration algorithms, overlay generation and the reusable
  `Vision.lab` calibration view. The user now authorized embedding it in App;
  read `DETECTION_LAB.md` and `../App/README.md`. App invokes `LabRuntime.ingest`
  without starting another worker. Keep the standalone developer entry point.
  Vision owns preset validation; Processing owns atomic profile persistence;
  App owns single-user profile lifecycle. Loading/exporting completed fits must not
  require a visible face; collecting new calibration still requires fresh evidence.
  Never auto-arm on load or restore tongue checks.
- Support synthetic/replay input so other lanes can work without owning the camera.
- The coordinated eye exception is `../Contracts/EYE_INTENT.md`: Vision owns
  independent per-frame wink appearance calibration/classification and the additive
  intent sample, while preserving raw anatomical openness. Do not map OS events or
  import Processing internals. Keep the unified guide, no time/opposite-eye features,
  separate validation windows, model uncertainty and per-eye failure visible.
- Before handoff, check no face, one/two faces, identity loss/reacquisition, missing
  features, orientation/mirroring, and sample timing. Document setup/run/test commands
  once code exists. Never commit real recordings or personal calibration data.

Read `../Contracts/MOVEMENT_CALIBRATION.md` for guided head/tongue ranges and
shared capture diagnostics. Detector presets are v5; combined profiles remain v3.
Use the same workbench trace in camera setup and calibration. No UI-sampled history
or second worker. Keep tongue raw mouth coordinates separate from personal ranges,
require fresh saved-range rechecks, and preserve invalid observations. Read `../Contracts/TONGUE_TIP.md`: the current expanded crop reports the middle
of the visible front boundary in mouth-width units. Invalid tips never fall back
to a centroid. v1-v4 tongue appearance/ranges require retraining. Future model/crop
changes also require a versioned contract and fresh calibration.
