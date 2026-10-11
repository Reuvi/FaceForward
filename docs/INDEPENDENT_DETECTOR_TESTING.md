# Independent detector sampling

Restart the native app to load this change:

```bash
cd "/Users/reuviisraeli/Desktop/Hackathon fall 26"
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task --fps 30
```

Keep using the same camera setup and Detection calibration tabs, saved profiles,
eye guides, head guide, tongue guide and pupil guide. No second app is needed.

## What changed

The camera/MediaPipe path measures both eyes, head pitch and pupils for each
processed capture. Neural tongue inference runs in a separate local Python
process, with one ONNX CPU inference thread and one OpenCV thread. This includes
mask decoding and tip extraction, so their Python work cannot hold the fast path's
interpreter lock. The process never opens another camera.

Submitting a crop does not wait for inference or model startup. There is one
active tongue job and one pending job; a newer crop replaces the pending crop.
Completed results are read on the next fast capture. No unbounded queue builds up.
Tk still draws independently, and Processing still ticks at its configured rate
(100 Hz by default).

The eyes/head/pupils share MediaPipe's face model. Their cadence therefore still
depends on that common model and the camera. Tongue no longer adds its inference
time to that loop. Independent scheduling cannot eliminate contention for the
same CPU, memory or thermal budget; actual rates are displayed.

## What to look at

1. Start the camera and inspect the raw eye/head/pupil plots on camera setup.
   Move these features while showing/hiding your tongue. The plots and per-frame
   eye samples should continue even while tongue inference loads, runs slowly,
   fails or produces no mask.
2. On Detection calibration, read `sample_hz` for the fast capture rate and
   `tongue_hz` for completed tongue results. These rates can differ.
   `inference_ms` remains the face-model duration; the tongue panel reports its
   own inference duration/age. `features_ms` excludes background inference.
   `tongue_replaced` counts superseded pending crops; an increasing count is
   expected when tongue inference is slower than the camera.
3. Inspect the tongue crop. The mask/tip overlays use the image that actually
   produced that result. They are deliberately absent from the newer full-camera
   image. The panel shows result age. A result older than the detector's
   `stale_ms` (default 250 ms) is invalid.
4. Use the tongue position guide as before. Only distinct completed tongue
   inferences count as samples. The guide allows up to `stale_ms` after a
   capture window to accept delayed results captured inside it. Rest, preparation
   and previous-pose samples cannot train the next pose. A failed/hung model
   finishes with insufficient samples instead of leaving the guide stuck.
   If actual tongue Hz is too low to collect the minimum (default 12) during
   `collect_ms` (default 1800 ms), increase capture duration in detector settings
   and recalibrate, or retry after model warmup. Held values never pad the count.
5. Reset tongue, load a profile, briefly leave the camera, and restart the source.
   Old pending results must not repopulate cleared live evidence. Completed fits
   retain the existing persistence rules; loaded/restarted tongue ranges need
   their fresh checks.

If a child process crashes or a request/startup takes over 10 seconds, tongue
reports a worker error; stop/start the source to retry. Fast inputs keep running.
Stop discards queued work and invalidates any running reply. The worker can remain
warm and idle while the source is stopped. Closing App terminates/reaps it with a
bounded wait; it does not wait for a hung model to return.

## Samples, scopes and Processing

Every fast capture still emits one SignalFrame. Its `tongue_sample` describes
the original crop's session, subject, sequence and capture time. Before the first
result, sequence/time are null. Repeated values retain that same origin.

Processing inserts each new tongue origin into pointer history once, interpolates
using its capture time, and expires it on its own output clock. Fast eye/head
frames cannot refresh an old tongue value. A stale/invalid tongue stops only the
tongue pointer channel; independent click and scroll inputs continue. This does
not change pupil-source, legacy-input, transfer-function or driver formats.

Both tabs read the same trace. Bright tongue points appear when a new usable
result is delivered; intermediate/missing points use the existing dark hold.
The trace's horizontal axis is the fast capture/delivery timeline. CSV includes
`tongue_sequence`, `tongue_timestamp_ms`, `tongue_age_ms` and `tongue_new`
so source timing can be analyzed separately from arrival. `tongue_new` marks a
new timely inference, including an invalid/no-tip result; inspect quality and
validity too. Graph holds never become training samples or fresh controls.

The additive wire contract is [ASYNC_DETECTION.md](../Contracts/ASYNC_DETECTION.md).
Profile versions are unchanged (detector v6, combined profile v3).

## Repeatable local scheduling test

No camera, profile, network or OS mouse access:

```bash
Vision/.venv/bin/python -m Vision.benchmark_workers --seconds 3 --tongue-delay-ms 500 \
  --model Vision/.local/tongue_seg.onnx
```

Measured on this machine, generated face pixels/landmarks, 30 Hz target, 90
captures per run:

| Tongue workload | Fast capture Hz | Fast feature step median / p95 | Tongue results |
| --- | ---: | ---: | --- |
| Disabled | 29.99 | 1.10 / 1.66 ms | none |
| Artificial 500 ms per result | 29.94 | 1.19 / 1.58 ms | 5; about 1.99 Hz after startup |
| Local ONNX, one inference thread | 29.96 | 1.10 / 1.48 ms | 18; about 6.74 Hz at end |

All three produced 90 trace rows. This verifies scheduling with controlled inputs;
it excludes live camera acquisition and MediaPipe inference and does not measure
recognition accuracy. The old four-thread synchronous model benchmark is historical
and no longer caps the fast-input rate.

Focused tests:

```bash
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_tongue_worker.py -v
Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_independent_detectors.py -v
python3 -m unittest discover -s tests/processing -p test_async_pointer.py -v
```

Tests cover a blocked/crashed/timed-out process, bounded pending work, shutdown,
real local-model execution (when `TONGUE_MODEL_PATH` is set), original timestamps,
reset/load/loss/session invalidation, independent control expiry, matching image
overlays, distinct calibration evidence and capture-window/rest boundaries.

Implementation: `Vision/tongue_worker.py` owns process/IPC/lifecycle;
`tongue_async.py` associates results with capture evidence; `workbench.py`
owns calibration and samples; `lab_runtime.py` owns common snapshots;
`Processing/mouse/signals.py` and `engine.py` consume timestamped pointer input.

Full validation for this change: 284 passing tests (122 Vision, 87 integration
with native Tk, 75 Processing), plus a 490-frame mouse demo exercising all four
actions and releasing output at the end. Local model smoke checks ran with
`VISION_MODEL_PATH` and `TONGUE_MODEL_PATH` pointing to installed models.
