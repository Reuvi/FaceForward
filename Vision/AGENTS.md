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
  import Processing internals. Keep two independent guide stages in the same eye tab, preserving geometry on
  wink-action retry/cancel/failure. Show rest countdown and next instruction together.
  Keep no time/opposite-eye features,
  separate validation windows, model uncertainty and per-eye failure visible.
- Before handoff, check no face, one/two faces, identity loss/reacquisition, missing
  features, orientation/mirroring, and sample timing. Document setup/run/test commands
  once code exists. Never commit real recordings or personal calibration data.

Read `../Contracts/MOVEMENT_CALIBRATION.md` for guided head/tongue ranges and
shared capture diagnostics. Detector presets are v5; combined profiles remain v3.
The lab is pitch-only for head Y, with learned up/neutral/down mapped to 0/.5/1.
Do not reintroduce a position/pitch choice. Validated legacy position fits are
dropped on load; compatible other fits survive. Raw degree plots use learned limits.
Use the same workbench trace in camera setup and calibration. No UI-sampled history
or second camera owner. Keep tongue raw mouth coordinates separate from personal ranges,
require fresh saved-range rechecks, and preserve invalid observations. Read `../Contracts/TONGUE_TIP.md`: the current expanded crop reports the middle
of the visible front boundary in mouth-width units. Invalid tips never fall back
to a centroid. v1-v4 tongue appearance/ranges require retraining. Future model/crop
changes also require a versioned contract and fresh calibration.

Current short guide: open/left/right training then fresh open/left/right checks,
with no natural-blink class, blink counts, or mandatory surrounding-muscle contrast.
The tongue guide waits for the user to acknowledge each pose, supports retrying a
failed pose, and has an always-visible reset that cancels only tongue work.
Clear tongue marks preserves background samples; frozen overlays show actual marks.

## Neural tongue and pupil joystick update

Read Contracts/JOYSTICK_DETECTION.md (relative to repository root) and
docs/TONGUE_PUPIL_TESTING.md. Camera tongue now uses pinned local ONNX masks with
no color calibration; synthetic/developer fixtures retain the legacy color path.
Pupil calibration produces eye-relative direction, not screen gaze; both eyes
must be usable. Head pitch remains unchanged and known to work for the user.
Detector v6 stores neural model identity/pupil range/head reference; v1–v5 remain
readable. Tongue and pupil loaded/restarted ranges require fresh checks. Keep one
camera and a shared trace with independent neural model scheduling, no runtime
downloads, no stale mask reuse, and
no fallback from neural detection to color. Pointer source is explicitly chosen
in App and changing it stops preview. See Vision/TONGUE_MODEL_NOTICE.md for license.

## Independent scheduling update

Read Contracts/ASYNC_DETECTION.md relative to the repository root. It supersedes
older same-worker/no-second-worker instructions for neural tongue inference.
Keep one camera and shared trace; isolate independent models in bounded workers,
preserve original sample timestamps, and never wait for tongue on the fast path.

## Horizontal head update

Read Contracts/HEAD_HORIZONTAL.md relative to the repository root. Add independent
yaw/head_x beside pitch/head_y; the pitch-only measurement-mode rule remains for
vertical detection. Guides and fits are separate. New detector presets are v7,
with v1–v6 readable; combined profiles remain v3. No implicit device remapping.

## Direct pupil update

Read Contracts/DIRECT_PUPILS.md relative to the repository root. It supersedes
pupil fitting/rechecks above: normalize MediaPipe iris direction directly on every
usable capture. No pupil guide or calibrated pose/eye gate. New detector presets
are v8 with sensitivity settings; fully validate then discard legacy pupil fits.
Combined profiles remain v3; all other detector calibration remains independent.
