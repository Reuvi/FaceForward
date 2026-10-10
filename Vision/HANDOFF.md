# First Vision implementation handoff

## Behavior

The previously documentation-only Vision lane now has a runnable synthetic/replay
producer and an explicit MediaPipe/OpenCV camera diagnostic path. Every emitted
frame follows SignalFrame v1 with all eight measurements. Replay preserves capture
intervals and sequence gaps while changing runtime sessions.

Face association is independent of detection order and ends tracks on loss,
overlap/ambiguity, large motion/scale change, and stale gaps. Eye/gaze geometry and
calibration are implemented in memory; binary eyes and validity handling are
tested. Calibration is bound explicitly to a session and subject and clears on
loss/restart. Live diagnostics remain invalid for control until calibration and
quality validation are supplied. Tongue geometry is continuous, but there is no
tongue detector. Head-pose estimation remains pending.

## Ownership

- Lane / task: Vision / first executable capture, replay, and measurement foundation.
- Branch: `work/codex/vision/measurement-plan`.
- Base commit: `38fd0bd1a3cf0c82b6d87707fe663d74ff484b4a`; pulled before editing.
- Changed paths: `Vision/**` and `tests/vision/**` only. Runtime modules, setup and
  handoff documentation, an integration proposal, synthetic fixtures, and tests.
- Shared interfaces changed: none; existing v1 dictionaries/NDJSON.
- Dependent work: integration agreement for lifecycle, profile persistence
  representation, and quality/calibration handoff. See
  [the proposal](interface-requests/runtime-calibration.md).
- Commit: the commit containing this handoff; local only, not pushed.

## Verification

- `VISION_MODEL_PATH=Vision/.local/face_landmarker.task Vision/.venv/bin/python -m unittest discover -s tests/vision -q`:
  **45 tests passed**, including real model loading, blank-frame inference, and
  native model reset across sessions.
- Core tests also ran on the system Python without optional dependencies.
- `python3 -m Vision replay tests/vision/fixtures/scenario.ndjson`: all six frames
  accepted by a logging/validation mock; face counts `0,1,1,2,1,0`, sequence gaps,
  fresh session ID, and irregular capture intervals preserved.
- `python3 -m Vision synthetic --frames 3 --fps 100`: valid no-face fixture output.
- `Vision/.venv/bin/python -m pip check`: no broken requirements.
- `git diff --check` and staged whitespace review: passed after removing extra
  blank lines at EOF.
- `python3 tools/check_scope.py --base 38fd0bd1a3cf0c82b6d87707fe663d74ff484b4a --lane vision`:
  Vision-only scope.
- Rendered and visually inspected a synthetic landmark/reference overlay;
  source pixels were unchanged and anatomical labels remained readable.

Tests cover invalid/nonfinite data, no/one/two faces, detection reordering,
crossing ambiguity, loss/reacquisition, old/duplicate frames, failed camera reads,
cleanup, session restart, actual capture intervals, BGR conversion, preview
mirroring, independent eyes, threshold boundaries, gaze disagreement, and
translation/roll/scale invariance. These synthetic checks do not establish
real-world detector performance or verify biometric identity.

No physical camera or live OS input was used. No real recordings, profiles, or
model binaries were committed. The official model and private environment are in
ignored Vision-local directories. The README records the model source/checksum.

## Handoff

- Tested environment: Python 3.12.5, Apple Silicon macOS, MediaPipe 0.10.35,
  OpenCV contrib 4.13.0.92.
- Ready now: synthetic/replay consumption, landmark diagnostics, calibration
  algorithms, and Vision-local programmatic eye/gaze binding.
- Remaining: a live calibration collection flow, per-signal quality/pose/occlusion
  validation, camera buffering measurement, calibrated head pose, and a validated
  tongue detector. Recorded-video image capture is also not yet implemented;
  current replay reads SignalFrame NDJSON.
- App must own the physical camera and selected subject/profile. Processing owns
  persistence, mappings, and its diagnostic UI. Drivers/App must handle EOF/error/
  stop and watchdog expiry with disarm/release; this Vision component sends no OS
  events.
- Integrate the existing replay output first. Agree shared lifecycle/profile
  representation before importing the local calibration API across lanes.

## Local runtime and efficiency follow-up

Behavior: recorded the user's native/local runtime requirement and added a
repeatable standard-library benchmark. Runtime processing behavior is unchanged.
The Processing desktop was inspected read-only; it already supports a direct
in-process SignalFrame handoff.

Ownership: Vision lane, based on `eb9d361`, same Vision branch. Changed
`Vision/AGENTS.md`, `Vision/README.md`, `Vision/benchmark.py`, this handoff,
and `Vision/interface-requests/runtime-calibration.md`. No shared interfaces
or Processing files changed. This follow-up is committed locally, not pushed.

Verification on Python 3.12.5 / macOS arm64:

- `python3 -m Vision.benchmark --faces 1`: 5,000 synthetic samples, geometry/
  pipeline mean **229.27 µs**, p95 **268.75 µs**.
- `python3 -m Vision.benchmark --faces 2`: 5,000 synthetic samples, geometry/
  pipeline mean **445.25 µs**, p95 **513.42 µs**.
- Optional JSON encoding averaged 7.10 µs / 10.92 µs respectively; direct
  application calls do not need this encoding.
- Read-only `Lab.ingest(frame)` probe: accepted the synthetic Vision frame;
  continuous gaze, independent eye polarity, and capture time were preserved.
  Bytecode writes were disabled for that inspection; no GUI or worker was started.
- `git diff --check` and
  `python3 tools/check_scope.py --base eb9d361 --lane vision`: passed.

These timings exclude neural inference, camera capture, UI, and Drivers; they
are not an end-to-end latency or real-world frame-rate claim. The remaining
dependencies above still apply. App should invoke the detector away from Tk's
main thread and hand dictionaries to Processing's external-source controller.
The inspected Processing code is active, uncommitted work; the integration owner
must use its final published API.
