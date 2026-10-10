# Mouse processing prototype

A playable, mouse-only prototype with synthetic detector input, independent eye
click filters, smooth pointer/scroll velocities, and five live oscilloscope traces.
It is a **native Python/Tk desktop app**, with no JavaScript, browser, web server,
or network connection. It uses Python's standard library and emits no real OS mouse
events. The driver's final message format is deliberately still pending.

For **Vision + Processing together**, run `python3 -m App` from the repository
root. See [the integrated MVP runbook](../App/README.md). The standalone command
below remains useful for manual one-hot mock tuning. App now embeds detector
calibration, and its Save active profile button stores detector fits and applied
Processing settings together. `mouse/profiles.py` owns local atomic persistence;
Vision validates detector fits and App handles explicit selected-face binding. App's external-source mode
disables those mock controls and displays actual Vision input, including rejected
frames, without changing filtering or eye polarity.

## Run it

From the root of the **processing worktree**, using Python 3.9 or newer:

```bash
python3 -m Processing.mouse
```

This opens the **Mouse Signal Lab — Native Python** window. Close the window to
stop its background processing thread. Python must include Tkinter; check with
`python3 -m tkinter` if needed. It is available in this workspace's Python 3.12.5
installation (Tk 8.6.14). No pip dependencies, camera, model, API key, or hardware
driver are needed. Separate app instances keep separate state.

1. Click **Start preview** with the grid/vector centered and the eyes open.
2. Click or drag the 2D grid to move the simulated pointer; use **Center inputs &
   open eyes** to return to neutral. Holding an offset produces continuing movement.
3. Select a head-vector position above/below center to scroll up/down. Watch the
   acceleration, boost decay, and settled velocity in the Scroll Y scope.
4. Try **Blink 120 ms**: the default 320 ms dwell ignores it. Try **Left wink**
   or **Right wink**, then try holding the two eye checkboxes independently.
5. Compare raw steps (blue), interpolated position or eye dwell (amber), and
   processed output (green). The scopes show the last eight seconds. Freeze them
   for inspection, or export up to the latest 20 seconds as CSV.
6. Open **Transfer settings**, change settings, click **Apply settings**, center
   the inputs, and start again. Export/import JSON to save configurations. The
   **Calibrate current neutral** button supports a manual calibration experiment.

Press **Escape** or **Stop** to neutralize the preview immediately. **Pause input
stream** tests missing samples; after the timeout, output stops and stays stopped
until you resume the input, center it, and explicitly start the preview again.

## What maps to what

| Input | Mouse behavior | Main tunables |
| --- | --- | --- |
| Left eye, `1 = closed` | Left button down after sustained closure; up after reopening | Independent left dwell/release |
| Right eye, `1 = closed` | Right button down after sustained closure; up after reopening | Independent right dwell/release |
| Tongue matrix (or selectable gaze matrix) | Relative pointer velocity in X/Y | Center, radial dead zone, curve, smoothing, acceleration, boost |
| Vertical head vector | Vertical scroll velocity | Center, dead zone, curve, smoothing, acceleration, boost |

**The eyes are independent.** There is no combined-eye suppression. Two sufficiently
long closures can hold both mouse buttons. Each eye has its own timer and first
needs an open baseline. A held signal produces one down transition, then one up
transition when released; it does not generate repeated clicks. The preview counts
down transitions. Actual OS click and drag behavior belongs to the driver adapter.

The current interpretation of “middle mouse” is **scroll wheel movement**, not a
middle-button press. Keyboard, speech, gamepad, and automatic facial calibration
are outside this prototype.

## Sampled input and transfer functions

The mock source defaults to **30 Hz**, independently of the **100 Hz** output clock.
The lab can sample at 5–120 Hz. The processing worker runs separately from Tk's
main thread; the scope targets **10 redraws/second** (cursor/readouts up to 20) and
skips rendering hidden tabs. Trace history is bounded to 2,000 entries, and interpolation history to 512
samples per axis. Scheduling is best effort rather than hard real time. Every
sample carries a timestamp and sequence; missed samples are not fabricated.

For a one-hot vector of length N, index i becomes `p = i / (N - 1)`. For a matrix,
column becomes X and row becomes Y, with the top-left at `(0, 0)`. Any rectangular
matrix is accepted (2–256 rows/columns); a vector may be flat, a single row, or a
single column. Exactly one value must be 1 and every other value 0. Zero or multiple
active cells, ragged arrays, NaN, and unsupported heatmaps are invalid, not neutral.
The mock UI uses odd dimensions to represent an exact center cell.

Position processing:

1. Decode the location, then interpolate between **already received** samples at
   `now − interpolation_ms` (default 50 ms). Beyond the newest sample, hold it until
   it becomes stale. There is no future prediction. At low sample rates, increasing
   this delay makes interpolation more continuous but adds response latency.
2. Subtract the calibrated center and normalize each half-range to signed `[-1, 1]`.
   Optional axis inversion corrects the detector's orientation.
3. Apply a radial pointer dead zone (scalar for scroll). Activation requires
   magnitude greater than `deadzone + hysteresis`; once active, it ends at the
   dead-zone boundary. Radial normalization caps diagonal pointer speed.
4. Above the dead zone, map magnitude with
   `((min(magnitude, 1) − deadzone) / (1 − deadzone)) ** exponent`.
5. A discrete position jump above `jump_threshold` adds a bounded speed multiplier:
   `boost = min(boost_max, jump_distance / sample_dt_seconds * boost_gain)`.
   It decays exponentially with `boost_decay_ms`. Setting `boost_gain = 0` disables
   it. An offset continues driving a steady velocity after the boost expires.
6. Smooth velocity using `alpha = 1 − exp(−dt / smoothing_time)` and limit its
   per-tick change by `acceleration * dt` or `deceleration * dt`. These rates are
   signed normalized velocity units per second. Centering smoothly decelerates;
   invalid/stale input immediately neutralizes the affected output.
7. Encode signed velocity as `(v + 1) / 2`. Thus **0.5 means stopped**, 0 is full
   left/up, and 1 is full right/down. The driver will integrate velocity over elapsed
   time or receive converted deltas through the eventual adapter.

Eye signals are discrete and are **never interpolated**. Dwell/release advance only
on fresh eye samples, using elapsed time. Their threshold can be crossed only when
a confirming sample arrives, so timing has sample-period granularity. A 320 ms
dwell is a starting setting, not proof of reliable intentional-blink detection.

The default 250 ms freshness timeout applies to capture time and receipt time.
Duplicates/out-of-order samples do not refresh it. Stream restarts, subject changes,
malformed envelopes, and excessive input/output clock gaps disarm the processor.
Re-arming requires fresh neutral axis input; eyes individually require open baselines.
One invalid eye or position channel neutralizes only its corresponding output.

## Python integration

```python
import time
from Processing.mouse import MouseConfig, MouseProcessor
from Processing.mouse.mocks import raw_frame
from Processing.mouse.output import mouse_message

processor = MouseProcessor(MouseConfig(), subject_id="mock-person")
processor.arm()
timestamp = time.monotonic() * 1000
processor.accept(raw_frame(0, timestamp), received_ms=timestamp)
snapshot = processor.tick(timestamp)
print(mouse_message(snapshot))
```

In a real runtime, call `accept(frame, received_ms)` whenever a detector frame arrives
and `tick(now_ms)` on a separate regular output clock, including when frames stop.
Serialize these calls on one thread or protect them with a lock; the lab does that.
Use the same host monotonic millisecond timebase across producer/processor. Newer
sequences with equal capture timestamps replace the interpolation point without
advancing dwell time; regressing times remain invalid. Never
mix browser `performance.now()`, Unix timestamps, and Python monotonic timestamps.
For a new host/session, build an explicit clock adapter. No server or transport is
needed when all three components are Python modules in the same process.

The processor accepts the new `raw_mouse_v1` shape and the repository's existing
SignalFrame v1 through `signals.py`. The latter retains its original `*_eye_open`
convention (0 = closed, 1 = open), regardless of raw input polarity. It uses the
selected face only and checks confidence on v1 measurements. The binary raw adapter
currently has no confidence field; uncertainty must be represented by null or an
invalid channel until the detector team agrees on a richer wrapper.

For a local detector thread, the lab controller exposes `Lab.ingest(frame)`:

```python
from Processing.mouse.controller import Lab

lab = Lab()
lab.settings({"runtime": {"source": "external", "subject_id": "selected-person"}})
lab.start()
lab.action({"action": "arm"})
# In the detector callback: lab.ingest(frame)
# In the consumer: lab.state()["message"]
# When finished: lab.close()
```

The controller serializes detector calls and processing with a lock. Attach the
same controller to `DesktopLab(root, lab)` to inspect an in-process producer; let
the desktop start its worker instead of calling `lab.start()` yourself. Its
**Sample source = external** setting disables mocks. Selecting external mode in a
standalone window waits for a producer; it does not create a hidden network service.
`lab.state(after_trace_id)` retrieves only new trace rows for a renderer.

See [the adopted native handoff](../Contracts/MOUSE_MVP.md) and
[the original input/output proposal](interface-requests/mouse-prototype.md) for
the complete raw example and driver decisions still to make. The final driver
format belongs in `mouse/output.py`; filtering code should remain unchanged.

## Configuration and code map

Settings live in immutable, validated dataclasses and round-trip to JSON. Defaults
are in [the example profile](mouse/example-profile.json). Profile files are local
configuration experiments, not trained identity models. The UI can export both
processing and lab settings. `--config path/to/settings.json` loads the processing
and lab simulation settings at startup. Import/export uses native file dialogs.

| File | Responsibility |
| --- | --- |
| `mouse/config.py` | Per-eye/per-axis configuration and validation |
| `mouse/signals.py` | Raw one-hot and SignalFrame v1 adapters |
| `mouse/engine.py` | Deterministic state machines and transfer functions |
| `mouse/output.py` | Provisional output serialization; driver integration seam |
| `mouse/mocks.py` | Synthetic matrices/vectors, eye inputs, repeatable scenarios |
| `mouse/controller.py` | Background processing clock, local callbacks, trace history |
| `mouse/desktop.py` | Native Tk controls, simulated desktop, scopes, settings |
| `mouse/benchmark.py` | Headless CPU measurement without GUI/detector/driver |

## Checks

From the processing worktree root:

```bash
python3 -m unittest discover -s tests/processing -v
python3 -m Processing.mouse.benchmark
python3 tools/check_scope.py --base origin/main --lane processing
git diff --check
```

Tests cover independent eye timing and simultaneous holds, short blinks, invalid
channels, matrix/vector orientation and shape, sample/output rate changes, dead
zones, boost decay, bounds, stale/duplicate input, session changes, settings, and
local detector/controller integration. Native-window checks cover the desktop
layout and independent eye input/output.
The detector's actual noise/latency and the emulator's accepted message semantics
still need end-to-end testing with the teammates' implementations.

The 10,000-tick synthetic benchmark on this Mac (Python 3.12.5) measured about
43 microseconds mean / 57 microseconds p95 for decoding plus processing per tick.
That excludes UI rendering, detector inference, OS scheduling, and driver latency.
Re-run the benchmark on the target device; these are measurements, not timing guarantees.
