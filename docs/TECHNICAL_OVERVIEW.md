# Final technical overview

**Face-controlled accessibility interface — presentation build, October 11, 2026.**
Implementation reference: `a51aace`. This document consolidates the working system;
older milestone guides describe earlier designs. It accompanies the
[project README](../README.md) and [presentation runbook](PRESENTATION_GUIDE.md).

## Purpose and current scope

The project explores computer control through a consumer webcam, microphone, and
comfortable facial movements. The current Presentation mapping combines relative
head-controlled pointer motion, continuous mouth braking, eye-operated mouse
buttons, and on-device speech-to-text. The intended demonstration is navigating
desktop applications and entering text into a focused field.

The full presentation path is implemented on macOS. Core synthetic processing and
driver dry-run checks do not require camera hardware. A Linux native mouse/keyboard
backend exists, but the dictation helper and this Unicode typing path are macOS
implementations. Game compatibility, clinical usability, and screen-gaze accuracy
are not established by the current tests.

## Architecture and timing

| Layer | Responsibility | Main implementation |
| --- | --- | --- |
| Vision | Capture images, infer facial landmarks/expressions, apply personal detector fits, report measurements and validity | [Vision](../Vision/), [workbench](../Vision/workbench.py) |
| Processing | Normalize head input, shape response, arbitrate gestures, reject stale input, produce device commands | [controller](../Processing/mouse/controller.py), [mappings](../Processing/mappings/) |
| Drivers | Validate commands and translate them into mouse/keyboard events | [Python adapter](../Drivers/output.py), [native code](../Drivers/src/) |
| App | Own source/output lifecycle, profiles, native UI, and speech orchestration | [runtime](../App/mouse_runtime.py), [dictation](../App/dictation.py) |
| LabUI | Draw shared traces; never provide held graph values as control input | [LabUI](../LabUI/) |

One camera capture worker runs OpenCV and MediaPipe Face Landmarker. App hands
frame dictionaries directly to Processing in the same process, under synchronized
access. Tk stays on the main thread; there is no browser or HTTP service in the
control path. Camera inference is independent of Processing's **100 Hz** output
clock and UI drawing. A 100 Hz control clock does not imply 100 camera frames per
second or a measured end-to-end latency.

Every capture retains a monotonic timestamp, stream session, and sequence number.
The timestamp is taken around camera acquisition before inference; it is not a
hardware sensor timestamp. Repeated output ticks retain that capture provenance
and cannot make an old observation fresh. In-memory traces and command history
are bounded. The driver has its own output worker and stale-input watchdog.

The calibrated camera path assumes one operator and attaches its sole face as
`single-user`. This is an operational assumption, not identity recognition.

## Measurements and calibration

| Signal | Measurement and preparation | Presentation use |
| --- | --- | --- |
| Head X | Yaw with guided left/neutral/right personal range | Horizontal velocity |
| Head Y | Pitch with guided up/neutral/down personal range | Vertical velocity |
| Left/right eye geometry | Independent open/closed calibration | Button gestures and both-eye toggle |
| Left/right wink intent | Optional same-eye appearance training, separate from geometry | Qualify individual eye actions when enabled |
| Mouth openness | MediaPipe `jawOpen`, normalized to `[0, 1]`; no separate calibration | Continuous pointer resistance |
| Pupils | Fixed-scale, eye-relative iris direction; no active pupil calibration | Unused by Presentation; retained for the gaming mapping |

Head fits map personal endpoints to 0 and 1, with neutral at 0.5. Valid readings
beyond an endpoint saturate rather than become unknown. Head X and Head Y fits
are independent. **Center head & start** captures a fresh comfortable resting
pose for pointer control; it does not replace the range guides.

Eye geometry and wink appearance are separate calibration steps. A calibrated
wink requires valid closed geometry and a matching same-eye appearance. That
classifier does not depend on opposite-eye closure, gesture speed, or a duration
threshold. Retrying wink training retains completed geometry; replacing eye
geometry invalidates its dependent appearance model.

Pupil outputs retain precise `gaze_x/y` plus an 11×11 one-hot inspection matrix.
They describe eye-relative direction, not a calibrated screen fixation. Tongue
detection, its worker, calibration, and UI are retired; required legacy schema
slots remain invalid for compatibility.

Invalid measurements remain invalid/null. Graphs may display a darker hold of the
last known height. The explicit previous-value eye input also carries
`known=false`; neither display holds nor held unknown numbers authorize actions.

## Pointer response and mouth resistance

Presentation uses **relative velocity**. Head direction sets movement direction;
distance from the resting center sets a base speed. A dead zone and hysteresis
stabilize rest, a nonlinear curve provides fine control near center, and smoothing
plus acceleration/deceleration limits shape transitions. Separate downward gain
compensates for the user's smaller usable downward movement.

[Head motion response](../Processing/mappings/head_pointer.py) estimates outward
or returning head speed from original captures over an 80 ms window. Fast outward
motion adds a bounded boost; return or reversal increases braking. This estimate
uses fractions of the personal head range per second, not degrees per second.
The transient expires after 150 ms and cannot be refreshed by repeated output
ticks without a new capture.

The built-in Presentation response starts from Mouse test's head response:

| Setting | Factory value |
| --- | --- |
| Pointer dead zone / hysteresis | 0.03 / 0.005 |
| Response exponent | 1.8 |
| Smoothing / interpolation delay | 20 ms / 0 ms |
| Pointer gain / downward gain | 1.4 / 3 |
| Acceleration / deceleration settings | 10 / 14 |
| Head-speed gain / return braking | 0.75 / 0.65 |
| Mouth brake onset / full brake / exponent | 0.08 / 0.65 / 1.5 |

These are settings in normalized control space, not physical speed or accuracy
measurements. A saved tuning profile or local personal default can override them.
Use `--factory-defaults` when a reproducible factory baseline is needed.

For mouth openness `m`, onset `a`, full-brake threshold `b`, and exponent `p`:

```text
brake = clamp((m - a) / (b - a), 0, 1) ** p
requested_velocity = head_velocity * (1 - brake)
```

[BrakedHeadFilter](../Processing/mappings/presentation.py) also reduces existing
velocity when resistance increases and strengthens deceleration. It applies the
change in resistance once, avoiding repeated multiplication on every tick. Full
brake zeros motion; closing the mouth restores movement through the normal head
response. Unknown mouth input stops the pointer without inventing a closed-mouth
reading. It does not disable otherwise valid eye actions.

## Eye actions and gesture arbitration

Presentation defaults to plain open/closed eye detection. A saved
**Require calibrated wink for eye actions** flag selects the optional wink path
for individual actions; both-eye dictation always uses anatomical closure.

| Gesture | Result and release rule |
| --- | --- |
| Left eye closes after an observed open baseline | Immediate left-button down when the selected plain/wink condition is valid; hold to drag |
| Left eye reopens | Left-button up and preparation for another press |
| Right eye closes and reopens | One right-click; plain mode defaults to 120 ms minimum closure, wink mode adds no dwell requirement |
| Both eyes remain known closed for 450 ms | One dictation toggle; both must reopen before another toggle |

Unknown or nonmatching left evidence releases an existing press. A new press then
requires an actual reopen. Uncertainty before the first press can preserve the
previous open baseline, but unknown data never presses. An uncertain right eye
does not veto a valid independent left press.

Both-eye closure releases left and suppresses individual actions. An uncertain
frame resets the entire both-closed timer. Brief simultaneous blinks do not toggle
dictation. If the left eye closes before the right, the immediate left press can
already have reached the application; the later both-eye gesture cannot undo it.
In plain mode, ordinary individual eye closures can also trigger button actions.

## Dictation and text submission

App starts a signed Swift helper using LaunchServices as a background app. Speech
and AVFoundation provide recognition and microphone capture. The helper requires
on-device recognition for the system locale and has no cloud fallback. Synthetic
and replay sources cannot start microphone capture.

The helper communicates through a private temporary Unix socket. Launching it as
its own app gives macOS a distinct Microphone/Speech permission identity; directly
launching the executable previously caused permission attribution failures.
The build stores the helper in a per-checkout cache under
`~/Library/Caches/FaceController/`, outside the repository.

The normal lifecycle is:

```text
idle → starting → listening → finalizing → sending → submitting → idle
```

1. A both-eye toggle starts recognition. The rising sound plays only after the
   microphone reports that it is listening. Partial text is visible in Signals.
2. A second toggle stops capture and requests finalization. The falling sound
   reports that recording stopped, not that typing has completed.
3. Successful, nonempty finalized text is sent through the driver one printable
   Unicode scalar every **35 ms**. Tabs and line breaks become spaces;
   non-printing characters and invalid scalar values are removed.
4. After the last character, a separate fresh output tick sends **exactly one main
   macOS Return**. A search field can submit; a multiline editor can insert a
   newline. The focused application's normal behavior determines the result.

Pointer and individual eye actions stay paused throughout speech and sending.
Head control resumes only after returning to center. The helper does not activate
another window; the user focuses the destination before dictating.

Recording is limited to 55 seconds. Recognition can finish early and enter a
captured state, but still waits for the explicit finish gesture before typing.
A 120-second unfinished interaction cancels. Errors, cancellation, and empty or
whitespace-only recognition never send Return. Stop, stale input, tracking loss,
or profile/output changes cancel unsent text and a pending Return, even after
the final character has been entered. Already-typed characters remain in the
target application. Late results from an earlier speech session are discarded.

The macOS driver uses Quartz Unicode key events and main Return key code `0x24`.
It supports Unicode scalars including characters requiring surrogate pairs. The
right eye is solely a right-click in this mapping; Return comes from completed
dictation. Some applications may not accept these injected events.

## Interfaces, persistence, and lifecycle

| Boundary or file | Current format | Important semantics |
| --- | --- | --- |
| Vision frame | `SignalFrame`, `schema_version: 1` | Session, sequence, monotonic capture timestamp, values, confidence, and validity |
| Calibrated eye extension | `eye_intent_v1` | Action intent is separate from anatomical eye openness |
| Processing → Drivers | `device_control_v1` | Bounded demands, known flags, enable state, and original capture provenance |
| Native driver API | C ABI v3 | Shared library loaded by Python `ctypes` |
| Combined face/response profile | `face_mouse_profile_v3` | Detector calibration, response settings, and source kind |
| Detector preset | v13, `raw-pupil-control-v13` | Compatible eye/head fits; no active pupil calibration or tongue detector |
| Mapping | `input_mapping_v9` | Mapping identity, response, bindings, eye mode, and Presentation parameters |
| Named tuning profile | `signal_tuning_profile_v1` | Mapping and response choices, including resting center |

Anatomical eyes use **1 = open, 0 = closed**. Processed action values use
**1 = active**. Valid driver-facing demands are finite in `[0, 1]`; pointer
neutral is `0.5`, converted to signed demand with `2 * value - 1`. Native relative
movement integrates velocity with elapsed time and retains fractional deltas.

The Presentation extension carries held-left state and per-eye validity.
Right-click uses the existing button channel. The adapter's `press_return()`
uses the existing native API after dictation; the legacy wire/API name `enter`
still denotes the main Return key. The historical generic ControlFrame proposal
is not the adopted command format for this App.

The adapter validates source and output sessions, sequence ordering, freshness,
known flags, and initial neutral activation. Processing and the App-configured
driver use a default **250 ms** stale cutoff. A separate driver watchdog releases
held input if App stalls; repeating old capture metadata cannot keep it alive.

Startup, profile loading, mapping/source/output changes, Stop, tracking loss,
and stale input disarm control and release held buttons/keys. Reacquisition does
not automatically re-arm. Per-signal uncertainty releases or stops the affected
control. Calibration survives brief loss and same-source restarts when compatible.
Loading a profile while capture is paused keeps capture paused. Legacy files are
validated before migration; incompatible retired calibration is discarded.

## Live tuning and the target game

**Live curves…** changes connected response sliders without restarting capture.
Mapping/profile changes and changing eye mode stop output. Named tuning profiles
save the response and eye-mode choice; they do not replace a camera calibration
profile containing eye geometry and optional wink training.

**Target game…** records actual cursor coordinates alongside head input. Trials
vary direction, distance, and target size across 16 conditions, using a 600 ms
target hold. Metrics include arrival and settling time, exits/re-entries, path
efficiency, overshoot, roughness, and hold accuracy.

Matched A–B–B–A rounds compare a baseline with one bounded adjustment. Invalid,
stale, or changed-setup trials cannot support tuning. Physical-mouse practice
does not update the head-control default. Valid comparisons can select a local
personal default, which Presentation can reuse. These are deterministic response
curves and comparison rules; no learned neural control policy is implemented.
The game is an engineering tuning tool, not a clinical study or standardized
throughput benchmark. See the [target-game contract](../Contracts/TARGET_GAME.md).

## Setup and runtime modes

Use the [README build commands](../README.md#build-and-run) from the repository
root. Python must include Tk for the UI; `python3 -m tkinter` checks it. Camera
requirements pin `mediapipe==0.10.35` and `opencv-contrib-python==4.13.0.92`.
CMake and a C++17 compiler build the driver; the speech helper additionally needs
macOS and Xcode command-line Swift tools.

The documented Face Landmarker bundle has this tested SHA-256:

```text
64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff
```

Check with `shasum -a 256 Vision/.local/face_landmarker.task`. The setup URL uses
`latest`, so a changed checksum needs model/landmark verification. Installation
downloads dependencies and the model; normal camera inference makes no runtime
download. On-device speech availability is checked during dictation setup.

| Output selection | Behavior |
| --- | --- |
| Preview | Internal visualization; no native library or OS events required |
| Driver dry run | Actual compiled driver with event logging; no live OS events |
| Live mouse + keyboard | Native OS output; Camera source and explicit connection/start required |

Camera and Accessibility permissions apply to the Python host/launcher.
Microphone and Speech Recognition permissions apply to **Face Controller
Dictation**. Restart the relevant app after changing permissions if needed.
Only one live controller should own the camera and OS output during a demo.

Use `--mapping presentation` explicitly. Without a mapping flag, startup can load
a local measured default or use the gaming mapping. `--factory-defaults` ignores
the local personal default. The two main tabs are Signals and Calibration;
launching or loading a profile alone does not start live control.

Models, environments, saved face profiles, and personal tuning remain local.
Rotating scalar diagnostics live in `.local/diagnostics/live-control.jsonl`;
target-game telemetry and defaults live in `.local/target-game/`. These paths
are ignored by Git. Diagnostics omit audio, transcripts, and saved face models.
The app displays speech text transiently but does not save dictation to disk.

## Verification evidence and reproducible checks

The [implementation handoffs](COORDINATION.md) record the following results for
`a51aace`: **225 Processing tests**, **27 compiled-driver Presentation integration
tests**, **10 diagnostics tests**, **22 driver connection tests** with one optional
skip, **19 native Tk Signals/curves tests**, and **5/5 CTest groups** passed.
A 490-frame synthetic run accepted every capture, emitted relative movement,
left down/up and right-click events, and ended disabled without held keys or
driver errors. These checks establish software behavior, not human accuracy.

Earlier controlled macOS checks at `a4f3524` verified LaunchServices permission
setup, on-device transcription of a generated phrase, microphone recognition of
a Mac-spoken test phrase, and real driver Unicode/Return events in temporary Tk
fields. That native check covered both newline insertion and one single-line
submit handler. The subsequent right-click/automatic-submit change was checked
with injected recognition and the compiled dry-run driver; it did not repeat a
human speech-to-browser trial.

After building Drivers, useful checks from the repository root are:

```bash
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/integration -p test_presentation_connection.py -v
python3 -m unittest discover -s tests/integration -p test_speech_transport.py -v
python3 -m unittest discover -s tests/integration -p test_live_diagnostics.py -v
ctest --test-dir Drivers/build --output-on-failure
python3 -m App --source demo --mapping presentation --factory-defaults \
  --output dry-run --headless --frames 490 --fps 30 --no-diagnostics
```

The synthetic command does not open a camera or microphone, type, or submit a
field. For an explicit **live OS-input** check in temporary local fields:

```bash
Vision/.venv/bin/python tools/check_native_text.py --live
```

That tool guards focus and aborts if another window takes it. Run it alone with
other live controllers and GUI tests stopped; it does not submit to a website.

## Known limits and next measurements

Calibration, lighting, face visibility, comfortable movement range, and speech
language support affect usable control. The mouth brake and response defaults
are adjustable engineering choices, not a demonstrated population-wide benefit.
Natural closures can trigger actions in plain-eye mode, and a later both-eye
gesture cannot retract an already-issued left press. Dictation requires the
intended field to remain focused.

The next useful evidence is repeated human target-game comparisons, unintended
gesture rates, camera-to-cursor latency, dictation completion rates, and tests in
the actual presentation applications. These measurements should guide further
tuning before adding more complex learned control. Scrolling currently uses
scrollbar dragging in Presentation; experimental pupil mapping remains separate.

For implementation details beyond this overview, start with the
[Presentation contract](../Contracts/PRESENTATION_MODE.md),
[driver boundary](../Contracts/DRIVER_CONNECTION.md), and
[raw pupil contract](../Contracts/RAW_PUPIL_CONTROL.md). Contribution and isolated
worktree rules remain in the [team workflow](TEAM_WORKFLOW.md).
