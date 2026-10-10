# Vision development

**Unified calibration and mouse lab:** run `Vision/.venv/bin/python -m App --source camera`
with `--model Vision/.local/face_landmarker.task`, or use `--source detector-demo`
for generated pixels/landmarks. Select the face, use **Detection calibration**, then
inspect the same measurements in **Live lab**. [App's guide](../App/README.md)
explains the shared stream, profile save/load and mouse workflow.
[DETECTION_LAB.md](DETECTION_LAB.md) specifies the algorithms, units and live testing.
The optional `Vision.lab` developer entry point reuses that calibration view but
runs without Processing. The source CLI described below remains uncalibrated.

This is the first runnable slice of [the measurement plan](vision.md): synthetic
and NDJSON replay, explicit OpenCV camera capture, MediaPipe landmarks, conservative
two-face association, a reference overlay, and in-memory eye/gaze calibration.
It produces SignalFrame v1 dictionaries or newline-delimited JSON. No Processing
or Drivers imports are required. Python 3.10+ is required; tested with Python
3.12.5 on Apple Silicon macOS.

## Native, local runtime

Runtime inference uses the model already on disk. There is no browser, JavaScript,
web server, HTTP transport, remote inference, or runtime download. The dependency
installation and optional model download below are setup steps only.

The inspected `work/reuvi/processing/mouse-lab` worktree runs a native Python/Tk
desktop: its processing clock is 100 Hz, readouts up to 20 Hz, and scopes 10 Hz.
It accepts SignalFrame v1 through its documented `Lab.ingest(frame)` API in
external-source mode. App now passes frame dictionaries from a detector worker
directly into that controller; Tk remains on the main thread. No serialization,
server, or transport is needed for that path.

Preserve continuous gaze/tongue values and the v1 eye convention (1 = open,
0 = closed). Processing's alternative one-hot/raw format uses different eye
polarity and does not require Vision to change its contract. Select gaze as the
pointer source when testing calibrated eye/gaze output; tongue and head controls
remain unavailable until their detectors are implemented.

## Measure overhead

```bash
python3 -m Vision.benchmark --faces 1
python3 -m Vision.benchmark --faces 2
```

This uses synthetic 478-point meshes, in-memory calibration, and 200 warmup frames
before measuring 5,000 iterations. It reports mean/p95/max for pixel geometry,
association, calibration, and frame construction, and reports optional JSON
serialization separately. It requires only the standard library and opens no UI
or camera. Neural inference, camera buffering, rendering, and drivers are excluded;
these numbers cannot establish live frame rate or end-to-end latency.

Keep the hot path independent of UI rendering and avoid introducing a frame
backlog. The current optional OpenCV debugging preview draws synchronously and
should be disabled for detector throughput measurements. App's native UI should
consume current diagnostics on its own drawing cadence.

## Run without hardware

Run commands from this worktree's root:

```bash
python3 -m Vision synthetic --frames 120 --fps 30
python3 -m Vision replay tests/vision/fixtures/scenario.ndjson
python3 -m unittest discover -s tests/vision -v
```

Synthetic input includes no faces, an independently closed left eye, two faces,
loss of the first person while a bystander remains, and complete tracking loss.
It is test data, not detector accuracy evidence. All eight signal keys are always
present. Synthetic confidence scores describe the fixture only.

Replay accepts streaming SignalFrame v1 NDJSON, validates it, gives every recorded
session a fresh runtime session ID, and rebases capture times onto the injected
monotonic clock. It preserves irregular intervals and sequence gaps. Slow
consumers receive the original rebased capture time, so they cannot mistake old
records for fresh measurements. Malformed or out-of-order input stops the stream.
Intermediate eye openness from other v1 producers is accepted when replaying;
this implementation's eye classifier emits only numeric 0/1.

## Install the optional camera dependencies

Use this worktree's private environment:

```bash
python3 -m venv Vision/.venv
Vision/.venv/bin/python -m pip install -r Vision/requirements.txt
mkdir -p Vision/.local
curl --fail --location \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task \
  --output Vision/.local/face_landmarker.task
shasum -a 256 Vision/.local/face_landmarker.task
```

The tested official model SHA-256 is:

```text
64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff
```

Run the optional blank-image inference and stream-restart smoke test without
opening the camera:

```bash
VISION_MODEL_PATH=Vision/.local/face_landmarker.task \
  Vision/.venv/bin/python -m unittest discover -s tests/vision -v
```

The upstream URL uses `latest`; a different checksum needs another model smoke
check and landmark-label verification. Models, environments, and local capture
data stay in ignored local directories. The original plan's mentioned model file
was not present at its documented path; the official bundle was downloaded into
`Vision/.local/` instead.

MediaPipe's Python setup, synchronous video mode, and model bundle are documented
in the [official Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)
and [model overview](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker).
The anatomical landmark groups were checked against the
[official connection definitions](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/python/solutions/face_mesh_connections.py).

## Explicit camera diagnostics

For the older uncalibrated CLI preview, explicitly open a camera with:

```bash
Vision/.venv/bin/python -m Vision camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 \
  --width 640 --height 480 --fps 30 --preview
```

Use `q` in the preview or Ctrl-C to stop. `--frames 100` bounds a run.
`--unmirrored-preview` changes only display orientation; inference always
receives the unmirrored image. Output NDJSON goes to stdout, status and measured
rate/latency go to stderr. Do not redirect real observations into tracked paths.
Coordinate ownership of the camera with other local processes.

The preview displays the face mesh, head-relative axes, subject ID, and separate
anatomical eye ratios. Camera output is deliberately **uncalibrated**: faces are
reported, but all eight control measurements stay invalid until an application
explicitly binds validated calibration and a quality assessor. Head and tongue
control signals are not implemented by this first slice. This command is useful
for landmark/geometry evaluation, not live device control.

Capture is synchronous and has no Python inference queue. Requested resolution,
FPS, and buffer size may be declined by the backend. The timestamp is taken
immediately after `read()`, before inference; it approximates acquisition time
and does not measure camera buffering latency. Summary FPS is calculated from
actual read-completion intervals, not the requested rate. Model VIDEO timestamps
are rounded to strictly increasing integers internally; the original floating
point capture timestamp and sequence remain unchanged in SignalFrame.

A failed camera read raises `CaptureError`, releases the camera, and stops the
stream. It never repeats the last observation or fabricates an empty successful
frame. Normal no-face inference does produce `faces: []`. CLI EOF/error/stop must
be handled by App as a disconnect, with downstream disarming/release and a
watchdog; the integration lifecycle is still to be agreed.

## Vision-local APIs

- `CaptureSession(clock)` stamps session/sequence/capture time; `restart()`
  changes the session. The clock returns monotonic milliseconds.
- `OpenCVCamera(..., clock=...)` is a context manager returning
  `CapturedImage(envelope, bgr)` from `read()`.
- `MediaPipeDetector(model_path)` is a context manager. `detect(captured)`
  returns at most one landmark observation and uncalibrated eye ratios.
- `VisionPipeline.process(captured, observations)` assigns IDs and returns
  a complete SignalFrame. Array order never defines identity.
- `AxisCalibration.fit(low, center, high, min_separation=...)` fits robust
  per-target samples. It rejects small/overlapping ranges and excessive outliers.
- `EyeCalibration.fit(closed, opened, min_separation=..., gaze_x=..., gaze_y=...)`
  fits each eye independently. `calibrated_eye()` invalidates that eye's gaze
  when closed or unavailable. No gesture dwell or action mapping occurs here.
- `VisionPipeline.bind(EyeBinding(...))` binds calibration to an explicitly
  selected session and subject. A validated quality-assessment callback is
  required; MediaPipe detection thresholds are not per-measurement confidence.
  Missing or invalid scores cannot make valid control signals.
- `tongue_ratios()` implements continuous mouth-relative geometry for a real
  detector's centroid. It rejects degenerate mouth geometry and out-of-mouth
  positions. The calibrated workbench instead uses the color-mask front-edge midpoint in
  mouth-width units; see [tongue-tip testing](../docs/TONGUE_TIP_TESTING.md).

The legacy pipeline binding is memory-only. App can save the new detector fits in
a versioned local profile and load them for the single user, even without a visible
face. The App workbench preserves these fits through tracking loss and restart.
The legacy developer pipeline (separate from that workbench) clears its binding on loss, ambiguous
reassociation, a long gap, or session change. Reacquisition requires a deliberate
new binding. A bystander cannot inherit the missing person's binding. The
geometric tracker is conservative but not a biometric identity verifier; a
visually indistinguishable replacement between frames cannot be ruled out by
bounding boxes. Real crossing/occlusion tests remain necessary.

Single-eye gaze defaults to unavailable until explicitly enabled following
calibration. Two usable eyes must agree within an explicitly supplied tolerance;
otherwise the affected gaze axis is invalid. Default positional normalization
rejects out-of-range values. Small endpoint clipping is available only through
an explicit calibration tolerance.

The legacy types above remain local APIs. The adopted detector preset and combined
profile format are defined in [the MVP contract](../Contracts/MOUSE_MVP.md) and
[App's profile guide](../App/README.md#saved-face--mouse-profiles).

## Status against the plan

| Plan step | Current status |
| --- | --- |
| Capture/replay and timing | Implemented; mocked capture failures and replay timing tested |
| Landmarks, association, overlay | Implemented; official model blank-image smoke check passed; live faces untested |
| Independent binary eyes | One-button five-open-pose guide, sound cues, independent fits, uncertainty gaps and binary scopes; real-person accuracy pending |
| Calibrated gaze | Legacy fitting primitives exist; current App calibration does not emit gaze |
| Head Y | Image-position or transform-pitch calibration implemented; live range/sign/repeatability testing pending; head X invalid |
| Tongue detection | Experimental color segmentation and validation implemented; real-person false positives/recall pending |
| SignalFrame emitter | Complete v1 records; native App/Processing integration implemented |

No camera, real face recording, or OS input was used during initial Vision verification.
The later integration checks are recorded in [App's handoff](../App/HANDOFF.md) and
[the shared MVP runbook](../App/README.md).
No real-world accuracy, false-activation, pose-range, or end-to-end latency claim
has been established. Next steps are real-person quality/accuracy evaluation,
per-person tuning and the emulator handoff.
