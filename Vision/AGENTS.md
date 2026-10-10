# Vision lane

Read the root `AGENTS.md` and `Contracts/README.md`. Own only `Vision/**` and
`tests/vision/**`. Keep implementation, dependencies, example capture tools, and
lane documentation here. Put requests for shared changes in `interface-requests/`.

- Capture/sample at a configurable rate and report actual timing, not an assumed FPS.
- Emit SignalFrame v1 with no more than two faces, stable session-local subject IDs,
  calibrated measurements, and explicit confidence/validity for every signal.
- Track gaze/pupils, tongue position when available, each eye's openness, and head
  horizontal/vertical bias. Mark unsupported/occluded features invalid; do not fake
  a detector. Keep detector feasibility and performance limitations visible.
- Own detection-calibration algorithms and overlay generation. Processing owns
  profile persistence and the diagnostics UI; expose public inputs/results for it.
- Support synthetic/replay input so other lanes can work without owning the camera.
- Do not select gestures for clicks, send OS input, or import Processing internals.
- Before handoff, check no face, one/two faces, identity loss/reacquisition, missing
  features, orientation/mirroring, and sample timing. Document setup/run/test commands
  once code exists. Never commit real recordings or personal calibration data.
