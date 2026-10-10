# Detection research lab — implementation and testing guide

This is the implemented companion to [the reliability design](DETECTION_RELIABILITY_PLAN.md).
Open **Detection research** in the existing native App window. It shares the selected
face, capture worker and saved profile with Detection calibration. It is not another
program. Everything runs locally in Python/Tk; model fitting uses NumPy in a background
worker. There is no web server, network inference or OS mouse injection.

The original **Live lab** remains the four-control mouse baseline. **Start research
preview** enables the new gesture/mapping experiment; the header **Start preview**
returns to the original behavior and stops research. **Stop / Esc** stops both.
The research graphs and trial measurements work while the preview is stopped.

## Start here: eyes, then measure blinks and winks

From the repository root:

```bash
# Synthetic fixture, no camera or inference; useful for understanding the interface.
Vision/.venv/bin/python -m App --source detector-demo

# Actual camera, using the already installed local model.
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --fps 30
```

1. On **Vision source & raw signals**, choose the visible face and press **Use selected
   subject**. Merely selecting a dropdown entry does not bind the subject.
2. On **Detection calibration → 1 Eyes**, choose **Rest between steps (seconds)**
   (default 3), test the sound, then start eye calibration.
   The full-screen dot guide collects natural open states at several gaze directions,
   closed states, and a fresh reopening check. Each eye has an independent fit. Follow
   the audible close/reopen/completion cues. Between poses, four low tones and a
   REST screen let you blink or relax; no eye or blink-coefficient training samples
   are taken. A rising pair cues the next open pose; three high tones mark capture.
   After closing, the reopen cue precedes rest. Default duration is about 40 seconds.
   Restart discards the previous eye data;
   Escape/cancel exits the popup. This sequence now also fits each available MediaPipe
   blink coefficient from its own open/closed observations.
   Rest can be set to 0–30 seconds; changing it applies on Start/Restart and is saved
   in the face profile. Existing profiles without this setting use the 3-second default.
3. On **Detection research → Measurements & preview**, select **Eyes / timing**.
   Check that each eye's closure goes toward **0 when open, 1 when closed**. Brief
   natural blinks should produce short candidates; a comfortable deliberate wink
   should last longer. The original calibration tab still shows separate sampled
   open/closed binary scopes. A continuous closure score in the research tab is a
   different measurement from the detector's conservative binary classification.
4. Open **Trials & evidence**. Choose a label, **train**, and intended repetitions.
   Press **Record trial**, begin with eyes open, perform only that labeled gesture,
   reopen, and wait for its completed event before **Finish trial**. Several separated
   repetitions can share a trial; do not mix natural blinks with intended winks in a
   wink-labeled trial. Labels describe what you attempted; the program cannot verify intent.
5. Start with about 30 natural blinks, 20 left winks, 20 right winks, 10 deliberate
   simultaneous closures, and ordinary activity such as talking, smiling, looking
   down and moving the tongue. Use **natural_blink** for ordinary bilateral blinks,
   **both_intentional** for intended bilateral closure, and **long_closure** for a
   comfortable prolonged closure that should not click. Use repetitions **0** for
   ordinary negative activity. Rest when needed; counts are a collection suggestion.
6. Press **Suggest duration**. With at least five training blinks and five winks per
   eye, the lab compares blink p95 against wink p05. If the distributions overlap it
   reports that timing alone does not separate them. Otherwise it fills a suggested
   minimum between them. Suggestions do not change active settings until **Apply settings**.
7. Record **new validation trials** after choosing settings. Keep whole trials separate;
   do not turn neighboring samples from the same gesture into train/test examples.
   Include enough ordinary activity to measure accidental decisions per minute.
8. Start research preview to see accepted clicks counted. By default an intentional
   closure must reopen before it produces one ordered click. Keep both eyes open
   briefly before another gesture. Inspect the decision reason in the event table.
9. Export scalar data regularly, then save the applied profile from the source tab.
   Exporting records and saving a profile serve different purposes.

Detector demo uses generated pixels/landmarks and fake expression coefficients. Its
post-guide cycles exercise closures; it is not evidence of ML accuracy and does not
automatically supply trustworthy human trial labels. Gaze target collection requires
actual changing iris observations; the default cartoon does not follow gaze targets.

## Graphs and event measurements

| Measurement | Meaning / units |
| --- | --- |
| Raw eyelid ratio | Eyelid separation divided by eye width; lower means more closed |
| Continuous closure | Per-eye calibrated ratio mapped/clipped to 0 open → 1 closed |
| Raw blink, squint, cheek, brow, smile, jaw | MediaPipe expression coefficients, 0–1; not probabilities or measured muscle force |
| Calibrated blink | Independent `(raw − open)/(closed − open)` fit for each eye |
| Brow/cheek gap | Landmark distance from eye center, divided by that eye's width |
| Closure elapsed | Milliseconds since the first activation sample; includes waiting to confirm reopening |
| Completed duration | First activation sample to first reopening sample, milliseconds |
| Closing/reopening speed | Maximum sampled positive/negative derivative in the candidate, closure units/second; last event maximum remains visible between candidates |
| Peak / area | Maximum closure; accumulated closure × elapsed seconds |
| Qualified | The minimum time has elapsed; this is not an emitted click |
| Synchronization | `sync_lag_ms` = first observed opposite-eye onset minus this onset; `overlap_ms` = sampled time with both above activation; inspection only in independent mode |
| Decision latency | Decision capture time minus onset, including the reopening confirmation |
| Sample age | Processing clock minus capture timestamp; distinct from gesture latency |
| Head pose | Yaw/pitch/roll in radians, `R = Rz(roll) Ry(yaw) Rx(pitch)`, unmirrored camera axes |
| Angular speed | Maximum absolute sampled change across pose axes, radians/second |
| Face X/Y, scale | Face-box center as image fractions; natural log of normalized face width (not centimeters) |
| Iris X/Y | Eye-local coordinates divided by eye width; not screen gaze |
| Gaze X/Y | Learned normalized point in the calibration viewport; never a velocity |

**Trials & evidence** contains separate eye duration histograms and a selectable
scatter plot of duration against peak, speed, facial support, synchronization or
head motion. The table includes rejected short closures too. Trial counts compare
requested versus matching/wrong-side decisions, negative decisions per minute,
invalid eye frames, and median decision latency. Counts summarize completed trials;
aborted trials are excluded from action-rate summaries. They describe eye decisions
under the settings recorded with each trial, not ground-truth accuracy of every mapping.
More accepted actions than requested can indicate repeated actions; fewer can indicate
misses, but check your labels and attempts before attributing the difference to detection.

Unknown plot intervals hold the last known height in a **darker version of the same
color**. No previous known sample means no invented line. Raw observation columns retain nulls/empty cells. Explicit eye input columns now
hold the previous numeric input with unknown flags, as detailed in the eye input
update below. Display holds and line interpolation never feed timers, models or control. Source/subject/calibration boundaries prevent cross-person plot holds.

## Temporal recognizer and settings

The causal state machine uses captured timestamps, not frame counts:

`WAIT_OPEN → READY → CANDIDATE → QUALIFIED → reopening → COOLDOWN → READY`

A prolonged release-mode closure is rejected. Missing/invalid samples cancel the
candidate. Duplicate/out-of-order captures, tracking loss, stale gaps, source changes,
profile loads, calibration and Stop disarm output. Reopening must be observed again;
interpolated or held graph samples cannot complete a gesture.

| Setting | Default | Purpose |
| --- | --- | --- |
| `policy` | independent | Each eye works independently; explicit `strict` also requires the other eye reliably open throughout |
| `click_mode` | release | One click after reopening; optional `hold` exposes a held button after the minimum and releases on open/loss |
| `activation`, `release` | 0.75, 0.35 | Hysteresis thresholds on normalized closure |
| `left_min_ms`, `right_min_ms` | 320, 320 | Independent minimum deliberate-closure times; experimental starting values |
| `max_ms` | 1200 | Long-closure rejection in release mode; hold mode deliberately allows longer holds |
| `open_ms`, `cooldown_ms` | 80, 200 | Fresh-open confirmation and post-decision refractory time |
| `stale_ms` | 250 | Maximum capture age/gap; stale input does not keep a press alive |
| `motion_limit`, `recovery_ms` | 3 rad/s, 100 ms | Fast-pose-motion veto followed by a settling interval |
| `pose_gate` | false | Optional supported-pose bounds learned from `open_pose` training |
| `model` | rules | Optional validated `geometry`, `blink`, or `face` completed-event classifier |
| `left_source`, `right_source` | left_eye, right_eye | Each action can instead use both_eyes, smile, brow, dwell, or disabled |
| `pointer_mode` | tongue | Existing tongue mouse velocity; optional head-relative pointer or absolute gaze point |
| `scroll_enabled` | true | Existing head-Y scrolling; must be false with head/gaze pointer modes |
| `dwell_ms`, `dwell_radius` | 900, 0.025 | Dwell time and radius in normalized preview coordinates; move outside to rearm |
| `head_center_x/y` | 0.5, 0.5 | Head-pointer neutral; **Set head neutral**, then Apply |
| `head_range`, `head_deadzone` | 0.15, 0.12 | Image-fraction movement range and normalized dead zone |
| `gaze_radius_px` | 80 | Maximum fresh-validation p95 pixel error for preview eligibility |
| `gaze_smoothing_ms` | 70 | Causal time-based gaze smoothing; 0 disables it |

All are experimental controls, not universal physiological constants. Natural blinks
can be long, intentional winks short, and facial control differs between people.
Duration alone cannot establish intent. At low/variable FPS, durations and speeds are
sampled estimates: threshold crossings occur between frames. Click latency also
includes waiting for reopening. **Independent mode may accept two sufficiently long
simultaneous closures as two clicks**, as requested; strict policy is an explicit choice.
The thresholds apply to separately calibrated eyes, never a shared raw eye baseline.

## Test whether additional features help

**Compare 3 models** fits small class-balanced, regularized logistic regressions:

1. Geometry/timing: duration, peak, area, peak closing and reopening speed.
2. Geometry plus calibrated blink and squint coefficients.
3. Those features plus cheek/brow coefficients, geometric brow/cheek distances and pose speed.

All comparisons use the same complete held-out events. Missing support features are
excluded, not zero-filled. The report includes event and distinct trial counts plus
TP/FP/FN/TN for each eye. Opposite-eye synchronization is deliberately excluded from
these independent classifiers. Rules remain the default. Models require at least six
positive and six negative training events and two of each for a comparison. Preview
eligibility additionally requires at least ten positive and ten negative validation
events, zero false positives in that set, and at least 95% event recall. These are
configurable-in-code MVP acceptance criteria, not statistical proof of safety.

A selected model is an **additional** release-event gate after timing/quality rules.
The comparison report evaluates each classifier's completed-event decisions; the
live rules-plus-model pipeline can reject more. Undetected closures never create
events, so event-only recall is not end-to-end recall: use trial attempt counts and
ordinary-activity false decisions/minute too. A higher-performing feature set on one
small validation set may overfit that choice. Record another untouched validation set
before relying on it, and keep ordinary activity in that set. Neural/appearance models
and pose-conditioned nonlinear thresholds remain data-driven follow-ups if this
implemented small-model experiment is insufficient.

## Facial asymmetry and alternative controls

Each eye has separate geometric and blink-coefficient fits. Overlapping open/closed
or rest/active distributions are rejected rather than amplified into a reliable signal.
An unavailable eye does not invalidate the other eye in independent mode.

In **Capabilities & settings**, choose a reliable source for each action or **disabled**.
For smile/brow, record TRAIN trials labeled **rest**, **smile**, **brow**, then press
**Fit expressions / pose**. At least 12 clear rest and active samples with separated
95th/5th percentiles are required. Smile currently requires both smile coefficients;
the larger normalized side drives the candidate. Validate normal smiling/talking before
assigning it. Alternatives use the same duration/reopen/cooldown rules. One source
cannot drive two actions; bilateral mapping cannot coexist with individual-eye mappings.

For pose gating, record **open_pose** with open eyes over comfortable head positions,
then fit expressions/pose and enable `pose_gate`. Bounds are observed extrema plus a
small margin; they are a rejection envelope, not proof of accurate detection throughout
that region. Bounds use retained training rows. Do not stretch beyond comfortable
movement just to satisfy a prompt.

Head pointer uses face-center translation, a neutral/dead zone, bounded velocity and
acceleration; it is not head-rotation gaze. Choose head mode, disable scroll, set neutral,
then apply and start. Dwell follows the fresh tongue/head/gaze preview cursor, fills a
progress indicator and emits once per target region. Unknown intervals reset uncompleted
time; after a click, brief invalid data cannot rearm it without leaving the target.
For a person unable to wink, disable difficult eye actions and test a comfortable
alternative or dwell. Software cannot supply a movement the person cannot perform.

## Head-compensated gaze experiment

This is optional and independent of finishing the tongue-pointer MVP. First calibrate
eyes, then open **Head-compensated gaze** in Detection research:

1. **Collect gaze targets** opens a temporary full-screen native guide on the primary
   display. Nine target positions are crossed with neutral/left/right/up/down head poses,
   followed by another shuffled pass: 90 fixations, roughly 3–4 minutes without rests.
   Look at the dot while holding only a comfortable version of the indicated pose.
2. Each prompt must be painted before its 700 ms settling and 1500 ms sampling period.
   Tones mark targets/completion. Pause/resume, retry previous, skip, cancel and Escape
   are available. Minimizing cancels the guide. Unclear fixations need ≥8 valid samples
   and ≥80% valid frames; otherwise they are skipped. Skip unsupported head positions.
3. **Fit / compare gaze** compares eye-only, eye-plus-pose and interaction regressions.
   Every fixation contributes one median feature vector, so long/high-FPS episodes do
   not dominate. Ridge strength is tuned within whole training episodes; the second
   pass compares variants. The selected pose model saves normalization and coefficients.
4. **Fresh validation targets** collects a new 45-fixation sequence. **Evaluate validation**
   is required before gaze preview: at least nine episodes, all nine targets represented,
   complete predictions, none outside the trained domain, and p95 error within the chosen
   pixel radius. The training sequence cannot pass this check. Skipping poses restricts
   the model's supported range; passing is not unrestricted head-motion support.
5. Set `pointer_mode=gaze`, `scroll_enabled=False`, Apply and Start research preview.
   Error reports use predictions before clamping, preventing edge clipping from hiding
   error. Gaze stays invalid with missing/closed iris measurements, out-of-domain inputs
   or fast motion. There is no uncalibrated single-eye fallback.
6. A wink latches the last fresh cursor target at onset. The accepted release event
   contains that target; a fresh valid gaze estimate is needed at commitment. Absolute
   points remain distinct from tongue/head velocity outputs. Dwell uses fresh valid
   points only. Loaded profiles need fresh validation; display-size changes invalidate it.

The input vector is binocular eye-local iris X/Y, yaw/pitch/roll, face center X/Y,
log face width, plus iris-X×yaw and iris-Y×pitch in the interaction variant. Pose
compensation is learned, not `iris − yaw`. Instructed target positions are labels,
not independent verification that the user actually looked at the target. Screen
points currently describe the calibration viewport only; multi-monitor/physical-pixel
OS mapping still belongs to the future driver agreement.

## Data, profiles, architecture and limitations

**Export scalar data** creates a local directory with `frames.csv`, `events.csv`,
`trials.csv`, and `report.json` (settings/fits/models, latest gaze episodes and report).
No camera frames or audio are recorded. Store exports under ignored `data/private/`.
Retention is bounded: 9000 frame rows (~5 min at 30 Hz), 2000 events, 400 trials and
256 ordered clicks. Export before earlier frame data rolls off. Trial IDs/labels attach
at candidate onset; ordinary unlabeled activity is not silently used for fitting.
Profile/source/face resets clear experiment data; export first if you want to keep it.

The applied v2 face profile adds a `research` section to the detector, Processing and
preview sections; v1 profiles still load. Research stores settings, expression fits,
pose bounds and validated model coefficients. It does not store recordings, trials,
event queues, selected identities or armed state. Loading validates before changing
active state, binds to the current fresh selected subject, and disarms previews.
Synthetic and camera profile restrictions continue to apply. Save **after Apply**.

| Owner / path | Responsibility |
| --- | --- |
| `Vision/landmarks.py`, `research_features.py` | Optional expression coefficients, quality-gated eye/face/iris/pose scalar observations |
| `Vision/gaze_research.py` | Fixation-level regression, domain checks, pre-clamp pixel error |
| `Processing/research/` | Config validation, causal gestures/features, logistic comparisons, mappings, dwell and preview events |
| `App/research_runtime.py` | Exact capture joins, trials, calibration collection, fitting worker, profile and export coordination |
| `App/research_view.py` | Native scopes, histograms/scatter, trial/config controls and temporary gaze guide |
| `Contracts/RESEARCH_LAB.md` | New additive measurement, profile and research-preview boundaries |

SignalFrame v1 and mouse_preview_v0 are unchanged. Research uses `face_features_v1`
with exact session/sequence/capture time/selected subject/calibration generation and
finite-or-null values. `ResearchProcessor.preview(after_click)` returns the separately
named `research_preview_v1`, ordered click IDs, a consumption cursor and `click_gap`
when a reader falls behind its bounded queue. A future consumer must deduplicate IDs
and reset on a gap. Relative velocity uses 0.5 neutral; absolute position explicitly
uses viewport fractions. No real hardware consumer has been attached.

Camera inference stays on its existing worker; fitting uses a separate bounded job,
plots refresh at 10 Hz and hidden research tabs skip drawing. The original mouse
processor retains its 100 Hz clock. The research recognizer runs only on new capture
samples; interpolation is display/pointer smoothing, never invented eyelid samples.

Deterministic checks cover temporal independence, release/hold/cooldown, synchronization,
stale/invalid/context resets, dwell, mapping conflicts, saved-model validation, capture
joins, profiles, plots/popup lifecycle, and synthetic head compensation. A local arm64
Python 3.12 run over 10,000 synthetic rule-processing samples measured median **16.75 µs**,
p95 **22.25 µs** per sample. This excludes camera/inference/UI and is not a live FPS
promise. No real-person accuracy study has been completed; the lab is built to collect
that evidence. Tongue segmentation remains the earlier experimental detector.

```bash
Vision/.venv/bin/python -m unittest discover -s tests/processing -v
VISION_MODEL_PATH="$PWD/Vision/.local/face_landmarker.task" \
  Vision/.venv/bin/python -m unittest discover -s tests/vision -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -v
python3 -m unittest discover -s tests/tooling -v
Vision/.venv/bin/python -m Processing.research.benchmark
```

## Eye input update: unknown holds the previous input, every frame

For the current eye-focused MVP, every fresh captured frame supplies two explicit
numeric eye inputs. An unknown/ambiguous eye **keeps its previous input value**, with
**`known=false`** retained. Consecutive unknown frames continue holding that value;
the next known observation replaces it. Each eye has its own history. Before any
history, an eye starts at **0 = open/no action**. A source/session, selected-person,
profile or calibration change clears history; Stop alone does not. This includes
frames where the selected face is unavailable: inputs hold, output stops,
and the app never switches control to another person. There is no dropped frame just
because an eye is unknown; a stopped camera cannot supply new frames.

The normalized sample is `eye_sample_v1`, with the original capture session, sequence
and timestamp. Read it from `Lab.ingest(frame)["eye_sample"]` or
`Lab.state()["eye_sample"]`; research exposes the latest sample through
`ResearchProcessor.preview()["eye_sample"]`. Original mouse samples are binary;
research samples contain calibrated closure strength. Both use 0=open, 1=closed.
The original SignalFrame's raw `*_eye_open` convention stays 1=open and its unknown
observation stays null/invalid. Transported fallback values do not overwrite evidence.

In **Detection research → Measurements & preview**, the bottom readout shows the last
captured eye input and whether it is known or **unknown / held**. The scopes keep their
colors and darker held segments. The numeric input now also holds its own previous
value. Frames with an ambiguous binary classification hold the previous input even
if a new geometric closure score is available. Graph values and input values can
differ between the binary mouse path and continuous research path.

CSV separates `left_input`/`right_input` (numeric values every frame),
`left_input_known`/`right_input_known` (flags), and measured/graph data. Research
`*_measured_closure` retains the calculated geometry score when available;
`*_closure` is null for unknown/gated eye input so plots remain dark. A no-face row has
held numeric inputs and unknown flags, without invented measurements. Original mouse
CSV is sampled at the 100 Hz output clock and identifies its latest captured eye
sample with `eye_sample_sequence` and `eye_sample_timestamp_ms`; research frame CSV
has one row per fresh capture. Repeated values remain separate samples. A higher
sequence at an equal capture timestamp adds a sample but advances no timer.
Before the first capture, output-clock CSV rows leave eye inputs and capture IDs
empty; that startup interval does not invent camera samples.

The unknown flag immediately releases a held eye action and cancels any pending
wink. It **does not count as a real reopening and cannot complete a release-click**.
A measured open baseline is still required before another gesture. Calibration and
learned feature models never train on held inputs. Malformed, duplicate,
out-of-order and stale frames do not refresh valid input; face-loss samples remain
non-controlling even though their numeric eye records are present.

This policy is deliberately specific to eyes. Future head, tongue, pupil and other
face-component calibrations must choose their own neutral value and validity rules;
no global fallback for missing measurements has been introduced.

To test the hold: start with a known closed eye (input 1), then briefly obstruct its
view while still capturing frames. Once the reading is unknown, its readout should
stay 1 with `unknown / held`, and every fresh capture should retain its own sequence
and timestamp. There should be no click and no held output button. A known open
observation should then set the input to 0. Repeat after a known open reading and
with the other eye; only that eye's history should apply. A full tracking loss stops
preview and requires selection/profile reattachment, which clears history. Use the
CSV `*_input` and `*_input_known` fields to distinguish held input from evidence.
