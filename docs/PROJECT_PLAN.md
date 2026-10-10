# Project plan

## Intended experience

Build a non-contact human–computer interface for people with severe movement
impairments, using a consumer camera and computer. Setup has two stages: calibrate
reliable facial measurements for a person's features and comfortable range of
motion, then configure how those signals control a chosen device. Save a local
profile and support continuous background sampling after setup.

The detector may track at most two faces, but one explicitly selected person
controls an output device in the MVP. Switching users must disable output until
the newly selected profile is ready. Two independent simultaneous controllers are
outside the first milestone.

## Signals and controls

Track pupil/gaze position, tongue position, each eye's openness, and vertical and
horizontal head direction/bias. Report uncertainty and unavailable signals. Tongue
tracking needs a feasibility spike; the architecture must work when it is unavailable.
Use comfortable movements selected per user, with per-signal detection validation
and tuning to reduce false positives.

Processing converts these into three primitives:

- Buttons: on/off with activation dwell, release behavior, and debouncing.
- Scroll: one axis with neutral dead zone and displacement-to-velocity mapping.
- Joysticks: two axes with calibrated neutral position, direction, and intensity.

Profiles configure confidence thresholds, sensitivity, dead zones, smoothing,
activation duration, and mappings. Do not hardcode one gesture per function. Use
monotonic time for durations so behavior stays consistent as sample rate changes.
Interpolation may smooth valid continuous samples; it must not turn missing data
into a confident signal or bridge tracking loss.

The development UI should show a camera/landmark preview and oscilloscope-like
signal traces, validity/confidence, actual FPS, latency, thresholds, current mapped
control values, and adjustable sampling settings. Vision owns overlay generation;
Processing owns the diagnostic UI and settings; App wires them together.

## MVP milestones and acceptance checks

1. **Independent mocks:** Vision emits the v1 signal fixture, Processing consumes it
   and produces a neutral ControlFrame, Drivers logs the control fixture. No camera
   or OS permissions are necessary for this milestone.
2. **First complete path:** Track one selected head/gaze axis and an available button
   gesture, calibrate it, view the traces, and exercise the logging mouse adapter.
   Losing the person or stream disables output and releases held buttons.
3. **Personalized controls:** Add the remaining supported signals, profile persistence,
   dwell/dead-zone tuning, and explicit subject selection with up to two detected faces.
   Unsupported signals remain visibly unavailable.
4. **Desktop demonstration:** Explicitly enable live mouse movement, scroll, left/right
   click, Delete, Insert, and a speech-to-text trigger. Drivers can first accept values
   from manual sliders in `[0, 1]`. A visible stop control releases all held inputs.
5. **Stretch:** Map the same button/axis primitives to a virtual Xbox-style controller.

Measure actual sample rate, dropped frames, capture-to-output latency, false
activations, CPU/memory use, and supported/unsupported signals on a target laptop.
Choose numerical performance targets after the first measurement. No benchmark or
accessibility validation has been completed by this scaffold.

## Decisions to make at kickoff

- Which person owns each lane and who integrates first?
- Which operating system is the live driver demo targeting?
- Which language/framework, camera backend, and detector model fit that target?
- Which comfortable, reliably detectable gesture should demonstrate the first button?
- Does “Insert” mean the Insert key or a text-insertion operation? The initial driver
  contract treats it as the Insert key until clarified.
- Which local or hosted speech engine should the speech trigger start, and how
  should recognized text be committed? The initial contract only triggers that flow.

The v1 numerical conventions in `Contracts/README.md` are initial coordination
defaults. They can be revised by the integration owner with dependent lanes updated.
