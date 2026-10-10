# Native mouse MVP: Vision + Processing

The local Vision and Processing implementations now run together in one native
Python application. This is a **mouse-only signal lab**: left button, right button,
vertical scrolling, and relative pointer movement. Output moves the simulated
desktop inside the lab. The hardware emulator is still a separate integration.

Keep the [testing companion](../docs/TESTING_GUIDE.md) open while experimenting.
The [engineering guide](../docs/ENGINEERING_GUIDE.md) explains the complete pipeline,
formulas, defaults, and diagnostic fields. Other agents should follow the
[main chat coordination guide](../docs/COORDINATION.md) for task claims and handoffs.

## Start here

From the repository root on `main`, with Python **3.10+** including Tk:

```bash
python3 -m App
```

No pip packages, model, browser, JavaScript, network, or camera are needed for the
default **Vision demo (synthetic)**. It runs Vision's SignalFrame producer through
the same callback used by camera/replay, then through the real Processing filters.
It does not use the Processing lab's one-hot mock generator.

1. The source starts automatically. Read its type and measured FPS in **Vision
   source & raw signals**. The default subject is the explicitly named fixture
   `mouse-demo-person`.
2. Click **Start preview**, then **Live lab**. If input is currently off-center,
   output waits for the next neutral period before enabling.
3. The 16-second repeating exercise contains a short blink (ignored at default
   dwell), a left wink, a right wink, both eyes held independently, a tongue/gaze
   circle, and head up/down. Neutral periods separate the exercises.
4. Compare raw detector values, delayed interpolation/dwell, and processed output
   on the five scopes. Watch left/right press counters and simulated page scroll.
5. Change **Transfer settings**, apply, then Start preview again. Settings are
   described in [Processing's tuning guide](../Processing/README.md). The source's
   FPS field takes effect on the next source start; Processing's mock input Hz
   setting does not change an external Vision source.
6. **Stop / Escape** disables output while leaving diagnostics running. **Stop
   source** also stops the producer and disables output. Close the window to stop
   both workers. To change source, stop it, select the new source, then Start source.

For manual one-hot matrices/vectors and eye switches, the original independent
tester remains available as `python3 -m Processing.mouse`. Those controls are
disabled when the integrated app owns input, preventing mocks from mixing with
Vision frames. Grid highlights in external mode visualize continuous position;
they do not quantize the values passed to Processing.

## What is working, and what is still missing

| Mouse behavior | Signal into Processing | Integrated demo/replay | Live camera today |
| --- | --- | --- | --- |
| Left click | `left_eye_open` | Independent dwell/release; tested | Raw left eye ratio visible; live calibration/quality collection pending |
| Right click | `right_eye_open` | Independent dwell/release; tested | Raw right eye ratio visible; live calibration/quality collection pending |
| Scroll wheel | `head_y` | Dead zone, smoothing, acceleration/boost; tested | Calibrated head-position detector pending |
| Pointer X/Y | `tongue_x/y` by default; optional `gaze_x/y` | Continuous 2D velocity processing; tested | Tongue detector absent; iris ratios visible, live gaze calibration pending |

**This merge does not make all four gestures detectable from a real face.** The
Vision branch had calibration primitives and raw eye geometry but no live
calibration collection/quality implementation, head-pose detector, or tongue
detector. Camera mode therefore retains its invalid control signals. The lab
displays those as unavailable instead of inventing neutral values or swapping
gaze in for tongue. This gives us one testable application in which to add each
detector incrementally.

The eyes never suppress one another. SignalFrame v1 uses **1 = open, 0 = closed**;
Processing converts those into internal closed states. Its separate raw one-hot
format uses **1 = closed**. See the clearly labeled raw table and input JSON;
do not invert values again between modules.

## Inspect real camera diagnostics

Install the optional dependencies and local model following
[Vision's setup](../Vision/README.md#install-the-optional-camera-dependencies).
After setup, `Vision/.venv/bin/python -m App` opens the demo with camera libraries
available for switching sources in the same window. The main checkout on Reuvi's
machine has this ignored environment and the verified local model prepared.
All inference is local. The camera opens only in explicit camera mode:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

Choose a detected subject in the source tab and press **Use selected subject**.
Selection always stops/reset filters. A tracker ID is not a recognized identity;
there is no automatic transfer to a bystander or newly detected person.

The native preview shows Vision's mirrored overlay. Raw anatomical left/right eye
openness, iris X/Y ratios, and image-reference width appear beside it. Three raw
ratio scopes use the latest observation at a 10 Hz diagnostic display cadence.
Their plot ranges are labeled; values outside the display range are clipped only
for drawing, while the numeric readout retains the actual ratio. SignalFrame
values/confidence/validity appear in the table. After stop/staleness the table and
preview explicitly show last-observed status; historical traces remain inspectable.

Raw eye ratios are geometry, not probabilities or normalized control signals.
The head reference drawn on the face is a 2D image frame, not calibrated pitch/yaw.
The demo/replay has no images or raw landmark ratios, so those panels remain empty
there; use **Live lab** for their input-versus-output plots.

`--no-preview` skips overlay encoding/drawing. The UI retains only the latest
preview in memory; no images, recordings, or personal calibration are saved.
Camera acquisition and inference run outside Tk's main thread. EOF, capture/model
errors, and stopping the source disable output immediately. The Processing
watchdog continues ticking through producer stalls.

## Replay and bounded checks

```bash
python3 -m App --source replay --replay tests/vision/fixtures/scenario.ndjson
python3 -m App --headless --frames 490
```

The existing six-frame Vision fixture is short and primarily exercises tracking
loss; it is not the full mouse gesture demo. Replay honors the file's intervals,
sequence gaps, and session changes, rebases times onto the local monotonic clock,
and stops at EOF. Select its subject explicitly in the UI, or use `--subject ID`.
Restart/re-arm deliberately to repeat. Long replay waits are interruptible.

The 490-frame headless demo lasts about 16.3 seconds and reports observed left,
right, pointer, and scroll output. It runs both real worker clocks without Tk or
OS events. `--frames N` limits headless runs. `--config profile.json` loads
Processing tunables; App continues to own the external source and subject.

## Runtime boundaries

```text
Vision demo / replay / explicit camera worker
    ↓ SignalFrame v1 dictionaries + capture timestamps
App.MouseSession.deliver(frame)
    ↓ synchronous Lab.ingest(frame), no network or growing frame queue
Processing 100 Hz worker → normalized mouse state / bounded trace history
    ↓ latest state and new trace rows
Native Tk main thread → raw table, plots, simulated pointer and scroll
```

- `Vision/mouse_demo.py`: deterministic continuous fixtures for all four actions.
- `App/mouse_runtime.py`: producer lifecycle, explicit selection, common clock,
  latest diagnostics/preview, EOF/error/stop handling.
- `App/desktop.py`: adds source and raw-diagnostic views to `DesktopLab`.
- `App/__main__.py`: native/headless launch and configuration.
- `Processing/mouse/controller.py`: serialized input handoff, independent output
  clock, immediate disconnect, settings, and a 2,000-row trace ring.
- `Processing/mouse/signals.py`: preserves continuous v1 positions and interprets
  its eye polarity; one-hot decoding remains a separate input adapter.
- `Processing/mouse/output.py`: provisional `mouse_preview_v0` serialization.

`MouseSession` uses a session lock before the lab lock. The UI never waits for an
inference result. There is one producer per session and one processing worker;
starting either worker twice is rejected. Stop disables output immediately even
if a platform camera read takes longer to return. A blocked native camera read
cannot be forcibly interrupted; the app waits up to two seconds on close and
never starts a second producer while the first is alive.

Public integration details and provisional output are recorded in
[the MVP contract](../Contracts/MOUSE_MVP.md). There is no live Drivers import.
Velocity remains normalized `[0,1]`, where **0.5 = stopped**; left/right button
values are states, not repeated click events. Driver update units/transport remain
to be agreed with the emulator teammate.

## Verification and incremental work

```bash
python3 -m unittest discover -s tests/integration -v
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/vision -v
python3 -m unittest discover -s tests/tooling -v
python3 -m App --headless --frames 490
```

The integration suite runs the Vision producer and timestamp-rebasing replay into
Processing, verifies all four outputs and short-blink rejection, tests the actual
Vision eye classifier with fixture calibration, and checks subject loss, stale
input, malformed frames, duplicate/equal timestamps, source EOF/error/restart,
and interruptible stop. Camera adapter tests preserve raw ratios while keeping
unsupported control signals invalid. Optional real-model tests use
`VISION_MODEL_PATH` as documented by Vision. These checks do not establish live
gesture accuracy.

Suggested next increments:

1. Collect open/closed eye samples for the explicitly selected face, assess live
   visibility/quality, bind the existing per-eye calibration, and tune dwell while
   observing false activations in this lab.
2. Implement calibrated head Y, verify up/down sign and neutral range, then tune
   scroll response. Keep image-reference geometry separate from pose.
3. Add and validate tongue detection; feed its continuous mouth-relative X/Y into
   the existing adapter. Gaze can be evaluated separately with explicit selection.
4. Agree the emulator's format and test `mouse/output.py` → driver with synthetic
   input before enabling real OS pointer events.
