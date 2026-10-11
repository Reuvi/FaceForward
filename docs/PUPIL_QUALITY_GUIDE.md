# Pupil quality update and Mouse test

The current code retains the local MediaPipe model and uses fixed-scale raw
eye-relative iris direction, without pupil calibration or head compensation.
The quality and filtering changes improve availability and pointer response;
they do not establish measured screen-gaze accuracy or replace the camera model.

## What changed

- Pupil visibility previously required lid gap ≥.10, blink score <.40, and either
  lid gap ≥.16 or supported downward gaze. Completed guided eye geometry now
  provides an additional, same-eye open test, accounting for a person's narrow
  open lids. This path requires gap ≥.04 and blink <.80, plus the existing image,
  iris shape, geometry and binocular agreement checks. These are heuristic
  safeguards, not calibrated probabilities. The generic path remains available
  without an eye fit; legacy non-guided fits do not override aperture checks.
- Raw iris coordinates, binocular averaging, matrix, capture time, and invalid/null
  data remain unchanged. Saved v12 profiles still load into v13; their pupil fits
  are retained as inactive data. No head-pose estimate is needed for pupil output.
  Neither eye can provide the other's open evidence. Actual closure
  and uncertain narrow eyes remain unavailable. Wink classification is unchanged.
- Gaming and Mouse test now use a **1€ adaptive filter** on the two-dimensional
  pointer velocity target before acceleration limiting. A shared smoothed speed
  controls both axes' cutoff. At rest, minimum cutoff is
  `1000 / (4π × smoothing_ms)` Hz; beta is 4 and derivative cutoff is 1 Hz in
  signed normalized-velocity units. Smoothing 0 bypasses the filter. Invalid input,
  Stop and start reset history. No prediction or stale-point reuse occurs.
- Mapping settings include **Adaptive pointer smoothing (1€)** for comparing the
  prior fixed filter. The interpolation setting remains separate and preserved.
  Head key filters and instantaneous calibrated eye actions are unchanged.
- **Mouse test** combines Head X and Head Y into one radial mouse vector. It emits
  only movement; eyes, pupils, clicks, keys and scroll have no effect. Both axes
  require their own calibrated valid measurements. Missing either stops motion.

## Why these choices

[Google's MediaPipe Iris description](https://research.google/blog/mediapipe-iris-real-time-iris-tracking-depth-estimation/)
explains the iris/eye-contour pipeline and distinguishes iris localization from
estimating a screen gaze point. More smoothing cannot remove a biased calibration.
The user chose raw directional control for simpler operation. Fixed-scale raw
values can be biased by resting gaze or head movement; filtering does not remove
that bias. Old learned correction and head-angle restrictions are no longer used.
[EyeTrax](https://github.com/ck-zhang/EyeTrax) similarly combines webcam features,
personal calibration and filtering; it is not evidence that substituting the
same landmark detector alone would improve this app.

The [1€ paper and authors' tuning guide](https://gery.casiez.net/1euro/) describe
speed-adaptive low-pass filtering to trade less jitter at rest against less lag
in movement. This implementation follows those equations in velocity space and
couples the axes using speed magnitude. Constants are starting settings, not
claimed universal optima. No additional inference model or package was installed.

## Reproducible software comparison

Run `python3 tests/processing/test_adaptive_pointer.py` with the repository on
`PYTHONPATH` (for example `PYTHONPATH=. python3 tests/processing/test_adaptive_pointer.py`).
The seeded fixture holds input X=.75 with uniform ±.008 noise at 30 Hz, evaluates
output at 90 Hz and excludes warmup. A separate center→X=.85 step measures time to
90% target with 10 ms ticks. Both use the same default response, no boost and no
interpolation delay to isolate filtering.

| Check | Fixed filter | Adaptive filter |
| --- | --- | --- |
| Stationary signed velocity standard deviation | .004048 | .003265 |
| 90% step response | 210 ms | 90 ms |

This fixture gives approximately 19% less velocity jitter and a 120 ms shorter
step response. It excludes camera inference and configured interpolation latency;
it is not a human accuracy measurement. Tests also check 10/30/60/100 Hz, direction
symmetry, output bounds, missing input, true-neutral startup and resets.

## Live check

Restart App. Load a compatible saved profile. If pupil rejection persists for
naturally narrow open eyes, redo **Eye open/closed** while following all open-eye
targets, then redo the dependent wink-action guide. There is no pupil guide.
**4 Pupils** displays the raw measurements and direction matrix. Old pupil fits
are ignored.
Compare steady fixation and deliberate directions with adaptive smoothing on/off,
using the same lighting, camera distance and profile. Inspect pupil reasons and
per-eye aperture source in local diagnostics; invalid samples are never filtered
into usable input. Measure actual availability, drift and latency before calling
this an accuracy improvement for a particular person.

To isolate the driver from pupil quality, choose **Signals → Active mapping →
Mouse test**, load/calibrate **2 Head Y** and **3 Head X**, center your head, then
press **Start live control**. No eye or pupil guide is required for Mouse test.
