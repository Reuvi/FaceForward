# Detection reliability: gesture intent, personal capabilities and head-compensated gaze

Proposal dated 2026-10-10, based on runtime commit `6ed296e`. This is an engineering
plan, not implemented behavior or a claim of live-person accuracy. It responds to
Reuvi's research notes in the main coordination chat. Keep the native Python/Tk
App, one local capture/inference worker, the existing calibration profile, and the
current mouse MVP while evaluating the additions below.

The two main additions are **recognizing deliberate actions over time** and
**estimating gaze despite head motion**. Facial asymmetry and limited motor control
belong in the personal calibration/mapping layer shared by both. Improving eye
calibration does not establish gesture intent or screen gaze accuracy.

## 1. Starting point and research interpretation

| Area | Already implemented | Proposed addition |
| --- | --- | --- |
| Eye state | Per-eye lid-gap/width geometry, five open poses, closed sample, fresh reopen check, uncertain band, image gates and separate binary scopes | Optional blendshape observations, pose-aware reliability, labeled gesture trials |
| Mouse eye mapping | Independent `EyeGate` objects; 320 ms closure dwell and 60 ms open/release debounce by default; held button states | Explicit gesture recognition policy, optional single-click-on-release mode, maximum duration and cooldown |
| Head | Transformation matrix requested in camera mode; rotation retained; optional pitch in degrees and default nose Y/image height | Documented yaw/pitch/roll plus translation/scale proxies and motion quality |
| Iris/gaze | Eye-relative iris geometry helpers; calibrated App `gaze_x/y` remain unavailable | Separately trained and validated screen-gaze estimator |
| Profiles | `face_mouse_profile_v1`, detector preset v2; stored fits and Processing settings | Capabilities, enabled inputs, gesture policy, alternative mappings and a separately versioned gaze section |
| Lab | One window, guided target/sounds, binary/raw scopes, CSV, simulated mouse | Gesture timelines, trial labeling, evidence comparison, gaze target/error view |

Code inspected: [landmarks](../Vision/landmarks.py), [guided eyes](../Vision/guided_eyes.py),
[calibration](../Vision/calibration.py), [workbench](../Vision/workbench.py),
[Processing engine](../Processing/mouse/engine.py), [settings](../Processing/mouse/config.py),
[profiles](../Processing/mouse/profiles.py). The present lid measure is EAR-like;
it is not the exact two-pair EAR formula from the 2016 paper.

Soukupová and Čech support analyzing eyelid changes across time rather than only
thresholding a frame. Their classifier detects blinks; it does not establish intent
for our users. Its 13-frame window includes six future frames. At 30 Hz that means
about 200 ms of look-ahead, so copying it directly would add latency. Use a causal
window or explicitly wait for reopening instead. [Original paper, 2016](https://cmp.felk.cvut.cz/ftp/articles/cech/Soukupova-CVWW-2016.pdf).

MediaPipe exposes expression coefficients and optional facial transforms. Its
`eyeBlink*` coefficients are not calibrated probabilities that a click was intended,
and facial deformation is not a direct muscle measurement. Our current adapter
requests transforms but does not request blendshapes. With `num_faces=2`, do not
assume the task's built-in single-face smoothing is active. [Official Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

The cited gaze papers address changing eye appearance with head movement through
image synthesis or bias compensation. They motivate the experiment below; they do
not validate a MediaPipe-landmark regression or imply we inherit their accuracy or
calibration time. [Lu et al., 2015](https://phi-ai.buaa.edu.cn/publications/papers/Gaze%20Estimation%20from%20Eye%20Appearance%20A%20Head%20Pose-Free%20Method%20via%20Eye%20Image%20Synthesis.pdf),
[Lu et al., 2014](https://www.sciencedirect.com/science/article/abs/pii/S0262885614000171).
Google also explicitly distinguishes iris tracking from knowing where someone is
looking. [MediaPipe Iris explanation](https://research.google/blog/mediapipe-iris-real-time-iris-tracking-depth-estimation/).

## 2. Deliberate eye actions versus blinks

### Measurements and supporting facial features

Keep raw eye-state detection independent for each eye. Add an optional observation
path for the following candidates, keeping quality/validity separate from values:

| Feature | Proposed role | What must be tested |
| --- | --- | --- |
| Lid-gap/width and normalized closure | Primary geometry and personalized state | Downward gaze, partial lids, squint, yaw/pitch, asymmetry |
| `eyeBlinkLeft/Right` | Second closure representation | Does it improve failures of geometry on held-out trials? |
| `eyeSquintLeft/Right`, `cheekSquintLeft/Right` | Possible eyelid/cheek involvement in a deliberate action | Smiles, laughter and ordinary blinks can also alter these |
| `browDownLeft/Right`, `browInnerUp` | Possible brow movement associated with a user's gesture | Habitual brow motion, concentration and talking |
| Normalized brow-to-eye/upper-cheek landmark displacement | Inspectable geometric counterpart | Pose/scale stabilization and landmark jitter |
| `mouthSmileLeft/Right`, jaw/mouth activity | Context or alternative gesture candidates | Speech, smiling and overlap with tongue control |
| Capture time, image quality, head pose and angular speed | Reliability and timing context | Blur, occlusion, frame gaps, lighting, fast motion |

These coefficient names are available in the
[official Face Landmarker source](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/face_landmarker.py)
and were checked against the locally installed MediaPipe 0.10.35 enum.
Start with the small relevant subset, not all 52 inputs in a small training set.

A forced wink may have a repeatable cheek/brow pattern for a particular user; this
is a hypothesis to measure, not a universal required signature. Users must not have
to strain their face. Missing cheek movement must not invalidate a reliable gentle
wink. Do not call two features independent confirmation simply because they have
different names: geometry and blendshapes originate from the same image/model path.

Run three comparisons on identical held-out trials: geometry alone; geometry plus
blink coefficient; then geometry plus coefficients and cheek/brow features. Keep
an extra feature only if it lowers unintended actions without unacceptable misses,
latency or effort. If representations strongly disagree, allow an uncertain result;
do not OR noisy features together or overwrite missing geometry with a guessed bit.

### Personal normalization and eye-state reliability

For a blendshape score increasing with closure, evaluate the proposed normalization:

```text
closure_blend = clip((score - open_baseline) / (closed_baseline - open_baseline), 0, 1)
```

For our geometry, whose ratio decreases with closure, the direction is reversed:

```text
closure_geometry = clip((open_ratio - ratio) / (open_ratio - closed_ratio), 0, 1)
```

Reject an inadequate/reversed range before dividing. A normalized number is an
intensity coordinate, not a probability. Use all open-pose distributions and their
spread when selecting limits; two medians alone discard the low-open lids that the
current guide was added to handle. The current two-limit uncertain band remains the
baseline. Optional temporal state hysteresis must never retain a CLOSED decision
through missing/invalid observations and thereby keep a button down.

Add a short comfortable open-eye head-pose check after the existing eye guide.
Evaluate open-state drift under yaw/pitch, talking and smiling. First expose a valid
pose range and fail outside it; fit pose-conditioned eye limits only if measurements
show that this is needed and supported. Do not silently update an open baseline
from unlabeled live frames: that can learn a fatigued/closed eye as the new normal.

### Separate gesture policy from observed eye state

The earlier team choice was independent eyes, including simultaneous closures.
The proposed `right_eye_open` condition changes that behavior. Unless Reuvi opts
into a different default, retain independence and offer an explicit **strict wink**
policy. Calibration, raw bits and individual quality remain independent in either
policy. Display the active policy in the lab and store it in the profile.

| Policy | Evidence permitted to confirm an action | Effect of opposite-eye failure |
| --- | --- | --- |
| Independent eye action, current preference | Own eye's reliable temporal pattern; opposite side can be logged for analysis but cannot veto it | A reliable eye remains usable |
| Strict unilateral wink, optional | Own eye closes deliberately while the other remains reliably open during the candidate interval | Cancel candidate; unknown is not open |
| Explicit bilateral gesture, optional later | A separately calibrated two-eye sequence assigned to one action | Both required inputs must be reliable |

Under strict wink mode, accept neither an early unilateral prefix of a bilateral
blink nor the leftover tail when one eye reopens first. Once a bilateral/ambiguous
interval occurs, require a new stable baseline before recognizing another wink.
Under independent mode, duration and personal features can reduce false activations,
but the opposite eye cannot be used as a hidden veto. Prolonged fatigue closure and
an intended closure can look identical; the system cannot guarantee intent from
appearance alone. If distributions overlap, disable that action or change its mapping.

### Candidate state machine and click semantics

For a new **single-click** profile, recommend evaluating click-on-reopening first:

```text
DISARMED / INVALID
    → own required inputs stably open → READY
    → reliable closure onset → CANDIDATE
    → within personal duration/shape bounds → QUALIFIED
    → stable reopening → emit ONE click action → COOLDOWN
    → cooldown elapsed AND required open baseline → READY

Candidate too brief / too long / invalid / stale / wrong subject
    → no action; wait for a new reliable open baseline
```

Waiting for reopening allows a too-long closure to be rejected before a click is
sent; a click already emitted at the minimum duration cannot be retracted when the
closure later proves prolonged. The tradeoff is higher perceived latency. Preserve
an explicit **hold/drag** policy for the existing press-after-dwell/release-on-open
behavior. Do not convert a long hold into repeated click events.

Use actual capture milliseconds, never counts of UI ticks or assumed 30 Hz. Preserve
sample gaps and reset affected candidates on unreliable samples. Rates/derivatives
must be calculated within valid contiguous segments. Do not interpolate binary eye
states or create synthetic observations to satisfy a dwell threshold.

| Parameter | Initial experiment, not validated defaults |
| --- | --- |
| Closure activation/release score | Compare 0.75/0.35 only on calibrated closure intensity; tune per eye from pose distributions, not raw EAR or raw MediaPipe values |
| Minimum closure | Keep existing 320 ms baseline; compare 250/320/400 ms only where comfortable |
| Maximum closure for single click | Start around 1200 ms; tune or disable the gesture if intentional and prolonged closures overlap |
| Open baseline/rearm | Compare existing 60 ms with 100–150 ms stable open |
| Cooldown | Start at 200 ms after the action; reopening is also required, and later double-click needs its own evaluation |
| Strict bilateral timing | Evaluate onset/offset synchrony in milliseconds; choose tolerance from observed blinks, not exact same-frame equality |

These timers must form one gesture decision path. Do not put a new 320 ms gesture
gate in front of the existing 320 ms EyeGate and accidentally double latency.

Processing should emit an internal action with a unique event ID for click-on-release.
The preview should count that event once. The eventual driver adapter must consume
it once and produce an ordered press/release; a one-input-frame pulse can otherwise
be missed by a differently clocked consumer. Keep the existing button-state contract
for hold/drag. This needs a documented integration handoff, not a silent change to
`mouse_preview_v0` or `*_eye_open` semantics.

## 3. Asymmetry, limited control and alternative inputs

Keep independent fits and quality results, and add per-input enable flags. The setup should evaluate
which comfortable gestures are repeatable, not diagnose a person's medical condition
or require everyone to pass a wink test. Offer skip, rest and retry for each trial.
One failed eye must not prevent a working eye from being used.

After eye state calibration, collect examples of the user's actual intended action.
A gentle bilateral close used for state calibration need not have the same dynamics
as that person's wink. Present a capability summary: usable, needs more testing,
disabled by choice, or unreliable in this session, with measured reasons.

Possible substitutes are smile, brow raise, a calibrated bilateral gesture, or dwell.
They are candidates for user selection, not automatic replacements. `mouthSmileLeft`
does not itself mean a deliberate smile command. Train each selected substitute
against ordinary expressions, talking, the other assigned actions and the tongue
movement used for the pointer. Avoid putting required actions on inseparable signals.

Dwell is a Processing interaction policy over a stable pointer position; head pose
alone does not detect a dwell click. Require fresh usable samples throughout, a
bounded position/velocity region, visible progress, a cancellation path and rearm
by leaving the region. Invalid/frozen/stale gaze must not accumulate dwell time.
A person unable to wink can use a validated head pointer plus dwell, but head-pointer
motion and head-Y scrolling need separate modes or a deliberate scroll control.

Profile extension proposal: save each signal's fit/model identifier, calibration
quality summary, enabled state, chosen action, gesture policy and timing, plus
explicit pointer/scroll mode selection. Keep prior profiles readable and disarmed
on load. New mappings require versioned validation across Vision, Processing and
App; adding fields to today's strict JSON schema without migration will fail.
Do not save recordings, event histories, selected identities or armed state in a profile.

## 4. Head motion and screen gaze

This is a distinct estimator. It is not needed to finish the present tongue-pointer
MVP, but its pose diagnostics also help test eye closure reliability.

### Establish units and supported observations

- Keep each eye's iris center in its corner-based coordinate frame, divided by eye
  width. Existing local axes already remove much image translation/scale and in-plane
  roll; they do not remove the effect of out-of-plane yaw/pitch.
- Extract yaw, pitch and roll from the validated rotation with a documented camera
  axis convention and rotation order. Use radians inside feature interactions and
  degrees in the lab. Test signs with synthetic known rotations and unmirrored input.
- Include nose/face center divided by image width/height and log(face width/image
  width) as translation/scale proxies. A canonical-face transform is not proof of
  calibrated centimeter distance or an eyeball gaze vector. Actual metric screen
  intersection would require additional camera/screen geometry.
- Evaluate `eyeLookIn/Out/Up/Down` as optional coefficients, not screen coordinates.
  Disable iris features while the eye is closed, occluded or poorly resolved. A
  single-eye fallback must have its own calibration and validation; do not silently
  switch a binocular model to a different input distribution during a wink.

### Guided target and head-motion calibration

Use another step inside the same native calibration view, sharing source/profile.
The current five-dot eye guide labels OPEN state; it is not gaze training data.
A gaze target supplies an instructed fixation label, not independent proof that the
user was looking there. Provide retry/skip, stable targets and audible cues.

1. Show a 3×3 grid of known target positions within a chosen viewport. Randomize
   target order, allow settling, and collect fresh visible-eye samples at each point.
2. Repeat target positions under small comfortable left/right yaw and up/down pitch;
   include modest translation/distance changes if the intended use permits them.
   Cross target position with pose: training only center while moving the head
   cannot identify all target/pose interactions. A full nine-target/five-pose grid
   is 45 fixation episodes; use short blocks and rest, not a forced long session.
3. Balance contribution by fixation episode and pose, rather than letting a long
   high-FPS dwell dominate the fit. Train on one set of episodes, tune on separate
   episodes, and validate on another target order/session.
4. Start with the actually sampled comfortable domain. Sparse calibration must lead
   to a restricted supported range, not an assertion of unrestricted head movement.

### Small model first, comparison before promotion

Start with standardized features and ridge regression for both screen axes:

```text
inputs: left/right iris x,y; yaw,pitch,roll; image center x,y; log face scale
selected interactions: iris-x × yaw, iris-y × pitch (expand only if justified)
outputs: viewport_x, viewport_y, normalized to the chosen viewport
```

Fit both outputs from the feature vector; yaw/pitch can affect both axes. Compare
an eye-only baseline, eye-plus-pose linear model, then the small interaction model.
Choose regularization using held-out fixation groups. Use stable least-squares/SVD
solves and save normalization parameters with coefficients. Only consider a larger
appearance model if the small model demonstrably fails and more training evidence
is feasible; it is not part of the first MVP increment.

During testing, compute error before clamping predictions into the viewport, so edge
clipping cannot hide bad estimates. Reject inputs outside the calibrated pose/scale
support or with poor image/eye quality. Recover from fast motion only after fresh
stable samples; never extrapolate a control command through invalid intervals.
Use a causal, time-based light filter only after assessing the unfiltered prediction:
smoothing can reduce noise but cannot correct a systematic head-related bias.

### Gaze output is not mouse velocity

Predicted `(viewport_x, viewport_y)` is a point. The current Processing pointer takes
normalized positions and turns displacement from center into relative velocity.
Sending absolute gaze positions into that path would produce continuous motion when
looking away from center. Plan a separately named `GazeEstimate` and explicit pointer
mode; do not silently reinterpret existing `gaze_x/y` or driver values.

First show only the predicted dot, target and error in the lab. An eventual absolute
pointer adapter needs a defined viewport/monitor, pixel mapping, display scale, and
an agreed driver contract. Window/display/camera changes require a validation check
and possibly recalibration. Keep tongue pointer mode working throughout.

Winking changes the available eye observations. In gaze-click mode, evaluate latching
the last stable pointer target at gesture onset, then committing at that location
on accepted reopening. Reject a click with no recent valid target. This belongs to
the interaction policy, not to eye measurement. Likewise, head motion for gaze
compensation must not automatically become scrolling; choose a separate scroll mode
or a deliberate activation gesture when that combination is used.

## 5. Evidence collection and pass criteria

### Pilot trials

The suggested 30 natural blinks, 20 left winks, 20 right winks and 10 bilateral
closures are a useful pilot, with skips/rests for unsupported actions. Add short,
long and partial closures, squints, looking down, smiling, talking, brow movement,
tongue movement, head translation/rotation, glasses/lighting changes and rapid motion.
Collect natural blinks during passive reading/viewing, not only on a "blink now"
prompt. Label intended actions from the trial/user/helper, not from our own detector.

Use local scalar traces with capture timestamp/sequence, trial and session ID,
intended label, features, validity/reasons, state transitions, events and latency.
Optional face video for independent annotation is a separate explicit opt-in; this
plan does not turn recording on. Keep all real trials under ignored private paths.

Do not randomly split neighboring frames from one blink across training and test.
Split complete events/fixations, then separate sessions; report results per user,
eye and condition. Calibration and validation trials must differ. Additional facial
features need an ablation comparison at matched false-click rates or matched recall.

### What the lab should report

| Experiment | Metrics and failure checks |
| --- | --- |
| Gesture recognition | False click actions per minute/hour of ordinary activity; intended-action recall; wrong-button rate; repeated events per gesture; event-level confusion matrix |
| Responsiveness | Median/p95 capture-to-decision latency, gesture-onset-to-click latency and reopen-to-click latency; actual capture rate and invalid time |
| Independent mode | Opposite eye missing does not veto a reliable action; simultaneous intended actions remain possible |
| Strict mode | Bilateral blinks, one-eye timing tails and invalid opposite eye cannot produce a wink |
| Quality/lifecycle | Blur, lighting failure, identity loss, bad profiles and stale/gapped streams cancel candidates and release output |
| Gaze fixed target / head moves | Raw versus compensated drift, median/p95 pixel and normalized-viewport error, dropout fraction and recovery |
| Gaze fixed head / eyes move | Target coverage, especially corners; compensation must not merely force every prediction to center |
| Gaze combined movement | Held-out poses, translations/distances and another session; also errors during clicks and after reopening |
| Timing robustness | Identical recorded event behavior at varied sample rates; dropped/duplicate/out-of-order frames cannot invent actions |

Proposed first lab gate: zero unexpected actions in a 15-minute ordinary-activity
exercise, no repeats per accepted gesture, and at least 95% recall in a separate set
of comfortable intended-action trials, reported as exact counts with uncertainty.
These are prototype targets, not established accessibility requirements or proof
of reliability. Twenty trials per eye are not enough to establish a precise 95% rate.

A zero-error observation is not a zero-error rate. For illustration, under a
stationary Poisson event model, zero events over T minutes gives an approximate
one-sided 95% upper rate of `3/T` events/minute. Zero in 15 minutes is therefore
compatible with roughly 0.2/minute; demonstrating much rarer errors needs much
longer held-out use and representative conditions. Do not pool all users to hide
one person's failure rate.

For gaze, choose a target radius R pixels before testing. Require the p95 validation
error, including the head-motion exercise, to fit inside that target's radius and
report dropout separately. If it does not, use larger targets, relative control or
a different supported input. This gives a useful task-specific gate instead of a
pixel accuracy promise detached from the display and user's needs.

## 6. Architecture, ownership and implementation order

```text
Single camera + local MediaPipe inference
    → Vision: geometry, optional coefficients, head pose, quality, calibrated eye state
    → App: selected-face binding + matching capture envelope
    → Processing: causal gesture policy / mappings / dwell / relative or future absolute mode
    → simulated preview; later the agreed driver adapter

Same observations and states → native diagnostic scopes + guided trial/evaluation view
```

Initially keep extra observations inside Vision diagnostics. Before a classifier in
Processing consumes them, define a versioned feature envelope with exact feature
names/units, availability and the same subject/session/sequence/capture timestamp as
SignalFrame. App must reject mismatched joins. Do not put degree-valued angles into
existing normalized signal fields. The current SignalFrame binary eye measurements
and invalid semantics remain intact; the additional handoff must be coordinated.

| Increment | Owning lane and concrete deliverable | Acceptance / dependency |
| --- | --- | --- |
| A. Instrumentation + labeled trials | Vision adds optional coefficients, pose and quality traces; App adds a native trial view | Missing-feature/mirroring/unit tests; baseline live scalar traces; no output behavior change |
| B. Intent policy prototype | Processing adds separate candidate/action state machine and diagnostics | Timestamp/rearm/invalid/repeat tests; compare current dwell on held-out trials; contract first |
| C. Capability-aware profiles | App/Processing add explicit enabled inputs, policy and chosen alternatives; Vision supplies per-feature calibration | Partial capability and legacy-profile migrations; chosen alternatives pass hard negatives |
| D. Gaze feasibility | Vision fits the small target/pose model; App shows target/prediction/error | Held-out fixed-target rotation and corner coverage beat eye-only baseline within supported domain |
| E. Pointer integration | Integration/Processing coordinate an explicit gaze pointer mode and event handoff with Drivers | Coordinate/monitor semantics, wink target stability, scroll conflict and disconnect behavior |

A and B should come first. Build pose diagnostics in A, but defer full gaze control
until click behavior has convincing live evidence. Head-Y and tongue reliability
can then be tested incrementally in the existing mode; gaze remains an optional
capability, not a replacement for the requested tongue-pointer MVP.

Keep inference off Tk. Use bounded time histories and small feature vectors; measure
the extra MediaPipe blendshape cost separately from temporal rules/regression. An
initial engineering budget is under 5 ms p95 for added feature/gesture work excluding
camera and neural inference, subject to measurement on the target consumer machine.
Preserve the two-face limit and explicit selected subject; performance must not be
improved by silently removing multi-person tracking safeguards.

No new detector, gesture, alternative mapping or gaze algorithm is implemented by
this document. The current runbook remains [Vision/DETECTION_LAB.md](../Vision/DETECTION_LAB.md).
