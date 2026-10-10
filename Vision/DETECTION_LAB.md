# Native detection lab: calibration, measurements, and test procedure

The main application now embeds this calibration view inside the original
Processing lab. One source supplies both views; calibrate first, then use **Live
lab** for the simulated mouse. The detector implementation originated in the
`vision-calibration-detectors` increment; `unified-calibration-lab` connects it.
No real driver events are sent. Real-person accuracy remains to be measured.

## Open it in the shared app

From the repository root, after [Vision setup](README.md#install-the-optional-camera-dependencies):

```bash
Vision/.venv/bin/python -m App --source detector-demo
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

Requires Python 3.10+, Tk and `Vision/requirements.txt`; tested on Python 3.12.5,
Apple Silicon macOS, MediaPipe 0.10.35 and OpenCV 4.13.0. Tk comes with Python,
not pip. Stop other camera consumers before camera mode. Inference stays local.

1. On **Vision source & raw signals**, start the source. The single visible face
   attaches automatically; there is no manual subject selection for camera testing.
2. Open **Detection calibration** and work through **1 Eyes**, **2 Head Y** and
   **3 Tongue**. Focus on eyes first; head/tongue testing can wait.
3. Watch prepare countdown → usable/rejected counts → fit result. Default capture
   is one second preparation plus 1.8 seconds sampling; hold the entire target.
4. Keep preview stopped while inspecting detections. To test the mapping, open
   **Live lab**, center/open, then **Start preview**. Calibration changes disarm it.
5. Use **Save active profile** on the source tab to save fits plus Processing settings.
   Motion/loss and same-source restart retain completed fits. Use **Load saved
   profile** to restore a JSON, including while stopped or without a visible face.
   Loading/restarting requires fresh tongue absent/visible checks. See [profile semantics](../App/README.md#saved-face--mouse-profiles).

For isolated Vision development only, `python -m Vision.lab --demo` or
`python -m Vision.lab --camera --model Vision/.local/face_landmarker.task` opens the
same view with its own source worker and no Processing. With neither flag it opens
with camera off. Its automatic single-user attachment, **Stop (keep calibration)**,
and source controls replace
App's source tab. Its tunables export is not a full profile; use App for profiles.
Do not launch both camera entry points together.

The preview is unmirrored: **your left eye is on the image's right**. Anatomical
labels never depend on display orientation. Mock checkboxes/sliders have been removed
from this view. The detector demo follows the eye guide automatically. Selection,
fitting, model/mask logic and all units below are
shared by the embedded and standalone views.

## 1. Independent eye calibration

Press **Test sound**, then **Start eye calibration**. No individual capture buttons
are needed. A temporary **full-screen native guide** opens over the lab, with a
large target, centered instructions, countdown and Cancel button. Keep your head
comfortable and follow the dot with both eyes naturally
open: center → left → right → up → down. Do not exaggerate or squint. The guide then
asks you to close **both** eyes gently, and finally reopen for a fresh check. Using
both eyes for the training pose does not couple their fits or runtime decisions.
Between poses, the screen says **REST** and hides the dot. Blink, close your eyes,
or relax your gaze naturally; these frames do not enter calibration. Set **Rest
between steps (seconds)** before Start/Restart: the default is 3 seconds, with
0–30 seconds supported (0 skips rest). The setting is saved with the active profile.
This is only the seven-step geometry portion. It is followed automatically by
natural blink/relaxed-face captures, three wink attempts per eye and separate
checks with two new winks per eye. The whole guide is 21 steps, about 2½ minutes.
See [current eye calibration instructions](../docs/EYE_CALIBRATION_GUIDE.md) before
testing. Collection times schedule samples; they never gate runtime wink ON/OFF.

| Cue | Action |
| --- | --- |
| One start tone | Calibration has begun; follow the dot |
| Four low tones | Rest your eyes; no calibration samples are collected |
| Two rising tones | Rest has ended; look toward the next dot and get ready |
| Three high tones | Sampling has started; hold the instructed pose |
| Two descending tones | Close both eyes gently; hold until the reopen cue (about 3.3 seconds by default) |
| Two high tones | Reopen both eyes; keep them comfortably open for the final check |
| Three rising tones | Both eye fits passed; watch the scopes while testing |
| Three low tones | Open your eyes; one or both fits need a retry; read the per-eye result |
| Two high tones then a low tone | Capture cancelled/lost; open your eyes and inspect the screen |

After the closed pose, two high reopen tones come **before** the four low rest tones,
so you do not have to keep your eyes shut through the rest period. The final reopen
pose has its own preparation cue after that rest. During capture, the three-high-tone
cue means hold the pose already shown; it does not mean reopen during the closed pose.

The guide fills the primary screen reported by Tk, using a temporary borderless
window; it does not resize the lab or create a second program/camera stream. It
returns to the same lab automatically after success or a retry result. **Escape**
or **Cancel calibration** exits immediately. On a multi-monitor setup, use the
primary display for this guide; per-monitor target selection is not implemented.

Instructions are centered above the target and the countdown below it. Sound is played locally, using
short generated WAV tones via macOS `afplay`, asynchronous `winsound` on Windows,
or counted system bells elsewhere. Speaker volume/mute controls still apply; test
sound first. On the bell fallback, use the visible instruction to distinguish cues.
There is no audio recording or speech service. If no reopen sound occurs, open your
eyes after the displayed duration and inspect the screen; source loss cancels capture.

**Restart eye calibration** discards the current eye training and both previous eye
fits, then starts from center. It leaves head/tongue fits alone. **Cancel** stops the
sequence without restoring old eye fits and closes the popup. Leaving the Eyes tab or minimizing the window cancels an active
sequence so unseen instructions cannot collect mislabeled samples. Completed fits
survive normal tab changes, track loss and Stop source. Applying detector Settings
or Reset all calibration clears fits. Preview stays disarmed during every guided phase.

The program waits for each full-screen rest/target prompt to be mapped and painted
before starting that phase's clock. Rest uses `eye_rest_ms`, records no geometry or
blink-coefficient training data, and is followed by a separately acknowledged pose.
Most poses allow `settle_ms` preparation followed by `collect_ms` sampling;
close/reopen allow at least 1500 ms preparation. Each eye needs `min_samples` usable
captures and at least 80% usable frames per phase. At most 512 distinct capture
timestamps are evaluated per eye per phase. A failed eye remains unavailable; the
other eye can pass independently. The final reopen check uses new frames and needs
at least 90% of its usable samples classified open. It is a session check, not an
accuracy score. The guide cannot verify that you actually followed the dot or used
the correct pose; labels come from the instructions you follow.

The raw measurement is the median distance of three upper/lower eyelid pairs,
divided by the corner-to-corner eye width, all calculated in pixel coordinates:

```text
r_eye = median(distance(upper_i, lower_i)) / distance(corner_left, corner_right)
```

It is a dimensionless ratio, not pixels, probability, or a gaze coordinate. The new
lid calculation does not depend on iris visibility, which helps when the eye closes.
The original iris/gaze helpers remain unchanged for later work.

Samples pass image/geometry gates. Each open-position group is trimmed **separately**
around its median using `3 × 1.4826 × MAD` (minimum radius `1e-9`). At least five
points and 80% of each group must remain. Trimming positions together would discard
legitimate low-open lids, such as looking down, so the guide never pools before
trimming. The closed group is trimmed in the same way.

Let `C` be the highest retained closed ratio and `O` the lowest retained open ratio
across all five positions. Require `G = O − C >= eye_separation` (default 0.015).
Otherwise reject the fit instead of inventing a dividing line. At runtime:

```text
ratio <= C + 0.2 G  → closed
ratio >= O − 0.2 G  → open
between those limits → uncertain / invalid (no binary decision)
```

For example, closed samples at 0.04 and a lowest open pose at 0.12 yield a closed
limit of 0.056 and an open limit of 0.104. Looking down at 0.12 remains open; 0.08
is uncertain. This is calibrated threshold classification over MediaPipe landmarks,
not retraining MediaPipe or a new neural eye model. It cannot distinguish two poses
that produce the same measured ratio, and it does not prove live accuracy.

| Display / field | Meaning |
| --- | --- |
| `left/right_raw` | Dimensionless eyelid gap / eye width |
| `left/right_closed_bit` | **1 closed, 0 open**, null if uncertain or unavailable |
| `left/right_eye_open` | SignalFrame convention: **0 closed, 1 open** |
| `left/right_quality` | Heuristic image support score, 0–1; not probability of correctness |
| `left/right_closed_limit_raw`, `left/right_open_limit_raw` | Guided classification limits in raw ratio units |
| `left/right_threshold_raw` | Midpoint retained for diagnostics/legacy compatibility; new classification uses the two limits |

The two dedicated eye scopes show the last eight seconds as sampled steps, without
interpolating binary values. A missing/uncertain reading or a stale-sized time gap
holds the previous known height in a **darker version of that eye's color**. The
next valid value resumes the bright trace with a jump at its capture time. There
is no ramp through an unknown interval. A changed subject/session/calibration clears
that visual hold; a never-observed channel stays blank. The current label still
says UNKNOWN, and CSV/control values remain null/invalid. A dark line at 1 therefore
does **not** mean the eye is classified closed or that a button stays down.

Analog scopes use the same dark-hold convention. For raw geometry, a failing image
quality gate counts as unknown for plotting, while the numeric/CSV raw value remains
available as diagnostic evidence. The renderer can seed a hold from retained history
before the left edge of the graph (at most twenty extra original rows in a snapshot,
from the existing bounded 9,000-row history). It never modifies a capture or adds
synthetic control samples. Stopping capture freezes its historical time axis.

After calibration, look around while keeping eyes open, then test open/open,
closed/open, open/closed and closed/closed. Both closures classify independently.
Brief blinks appear as `1` pulses in the anatomical scope. The separate calibrated
wink classifier uses surrounding facial features to keep recognized natural blinks
OFF in the wink scope. Processing follows this per-frame intent without dwell or
release debounce. Unknown intent releases only the affected button. No detector
hysteresis or temporal wink feature is used.
If an open pose still shows closed, export a trace and restart with representative
comfortable poses; the learned ratio bands cannot resolve every occlusion or gaze angle.

New detector presets use version 3 with geometry and independently checked wink
models. Version 1/2 presets remain readable but need the new guide to enable wink
buttons. The combined App saves `face_mouse_profile_v3` without research settings;
v1/v2 files remain readable. See the [profile guide](../docs/EYE_CALIBRATION_GUIDE.md#save-load-and-maintain).
The legacy per-eye `collect()` API remains for developer regression tests, not UI use.

## 2. Vertical head movement

Two explicit measurements are supported. Default **position** matches movement
of the tracked point up/down in the image. To test nodding instead, set
`"head_mode": "pitch"` in **Settings**, click **Apply settings**, and
recalibrate. Applying settings clears all channels, so choose the mode first.

| Mode | Raw measurement and units | What changes it |
| --- | --- | --- |
| `position` | Landmark 168 nose-bridge Y / camera image height; image-height fraction | Translating the face vertically; camera movement, distance/perspective, and nodding can also affect it |
| `pitch` | `atan2(-R[1,2], hypot(R[0,2], R[2,2])) × 180/pi`; approximate degrees | Camera-frame pitch from MediaPipe's optional facial transform; yaw/roll can affect this proxy |

For pitch, the transform's 3×3 component is normalized by SVD to remove approximately
uniform scale. Degenerate, reflected, nonfinite, or strongly anisotropic matrices
are rejected. Translation in the transform is ignored. This is a camera-relative
pose proxy; it is not a camera-intrinsics-calibrated physical angle measurement.

Capture **NEUTRAL**, **UP**, and **DOWN**, at comfortable, repeatable positions.
The labels define direction even if a raw angle increases in the opposite order.
The robust groups must be ordered, nonoverlapping, and separated by at least
0.02 image-height fraction in position mode, or 3 degrees in pitch mode.

The medians map to `head_y`: up **0**, neutral **0.5**, down **1**. Linear mapping
is applied separately on each side of neutral. A default normalized endpoint
overshoot up to 0.05 is clipped to 0/1; farther outside the range is invalid.
Try the midpoint of each half: it should read roughly 0.25 or 0.75. Return to
neutral several times and note drift. Keep the camera stationary and head distance
consistent. This output is position, **not scroll velocity or acceleration**.

## 3. Tongue appearance detector — experimental

MediaPipe supplies mouth landmarks, not a tongue landmark. This module detects an
actual colored pixel region inside the open mouth; it never substitutes a lip or
head point for the tongue. It is calibrated classical image segmentation, **not a
pretrained semantic tongue network**. A matching gum/lip patch can still fool it.
Use the visible mask and a separate live validation exercise to identify that.

1. Open the mouth with the tongue hidden. Click **Capture EMPTY open mouth** and
   keep this pose. Teeth, dark interior, gums, and other visible non-tongue tissue
   form the negative class. A closed mouth is rejected, not accepted as training.
2. Make the tongue visible, click **Freeze visible tongue**, and click a patch
   wholly inside actual tongue tissue. Avoid edges, teeth, gums, and lips.
   Alternatively, if tongue tissue fills the yellow center square, use
   **Mark center patch**. The frozen image is held only in memory.
3. Repeat freeze/mark on another representative tongue patch if needed. Then click
   **Fit appearance model**. A failed color-separation check requires recollection;
   do not label non-tongue pixels just to make a fit pass.
4. Hide the tongue while keeping the mouth open; click **Validate ABSENT**.
5. Show it again on new frames; click **Validate VISIBLE**. Move within a modest,
   comfortable range. Both checks must pass before `tongue_x/y` become valid.
6. Repeatedly hide/show it and move it in both axes. Watch whether the green mask
   actually stays on the tongue. Refit if lighting or mouth appearance changes.

Pipeline:

```text
mouth corners + upper/lower inner lip
 → affine mouth crop, 128×96 pixels, anatomical X direction, downward Y
 → inner-lip polygon mask eroded by 2 pixels
 → weighted CIELAB features (0.35×L, a, b)
 → nearest positive vs negative color prototypes
 → distance/radius gate + 3×3 morphology
 → largest unambiguous connected component
 → centroid / mouth width and opening height
 → quality gates + passed held-out frame exercises → normalized X/Y
```

Training uses up to 4,000 positive pixels from marked patches and 12,000 negative
pixels, at most 3 positive and 8 negative deterministic k-means prototypes, and
at most 12 iterations. A fifth of each pixel set is withheld to check fit quality:
positive recall must be at least 75%, false positives at most 2%. That pixel holdout
is correlated with training images and **is not independent accuracy evidence**.
The separate, newly captured absent/visible exercises provide a session check:
no more than 5% detections while absent and at least 80% while visible. These are
manually labeled exercises, not automatic verification of your pose. Both require
at least `min_samples` usable frames and at least 80% usable collection frames.
Changing marked pixels, refitting, resetting, or recollecting negatives invalidates
previous checks. Re-running either validation removes its previous pass first.

| Measurement | Definition |
| --- | --- |
| Mouth width | Distance between anatomical mouth corners 291 and 61, pixels |
| Opening ratio | Projected inner-lip height / mouth width, dimensionless |
| Candidate area | Connected-component pixels / eroded inner-mouth pixels, fraction |
| Candidate X | Centroid column / 127; 0 user's left mouth corner, 1 user's right |
| Candidate Y | Centroid row / 95; 0 upper inner-lip level, 1 lower inner-lip level |
| `tongue_x/y` | The same continuous coordinates, valid only after both exercises pass |

X/Y refer to the visible region's **centroid, not the tongue tip**. The crop follows
mouth translation, scale, and in-plane rotation. Mouth opening changes Y's scale;
keep the opening fairly consistent while testing. Lips/teeth covering the tongue,
a tongue extending outside the mouth domain, similar colors, changing lighting,
and extreme pose can cause a miss or a false candidate. Tongue absence stays
unavailable; it does not become a fake centered position. Calibration here learns
appearance; it does not stretch personal movement endpoints to fill the whole
mouth domain. Future Processing tuning can handle comfortable ranges.

## Image gates and every tunable

All numeric settings are finite and range-checked by `DetectionConfig`.
Settings JSON contains only the following tunables, not learned face calibration.

| Setting | Default | Units / role |
| --- | --- | --- |
| `settle_ms` | 1000 | Preparation countdown, milliseconds |
| `collect_ms` | 1800 | Target sample window, milliseconds |
| `eye_rest_ms` | 3000 | Rest between eye poses, milliseconds; 0 skips, maximum 30000; editable in seconds on Eyes tab |
| `min_samples` | 12 | Minimum distinct usable capture timestamps per target |
| `stale_ms` | 250 | Max capture age and tracker gap, milliseconds |
| `min_face_px` | 80 | Minimum face-box width in pixels |
| `min_eye_px` | 12 | Minimum corner-to-corner eye width in pixels |
| `min_focus` | 12 | Minimum grayscale Laplacian variance, intensity²/pixel-kernel units |
| `min_brightness`, `max_brightness` | 20, 235 | Mean grayscale intensity on 0–255 scale |
| `max_clipped_fraction` | 0.5 | Maximum fraction with gray <5 or >250 |
| `eye_separation` | 0.015 | Minimum separation of retained open/closed raw ratio groups |
| `endpoint_tolerance` | 0.05 | Allowed head normalized endpoint overshoot |
| `head_mode` | `position` | `position` or `pitch` |
| `head_position_separation` | 0.02 | Minimum adjacent head-target image-height fraction separation |
| `head_pitch_separation` | 3 | Minimum adjacent head-target separation, degrees |
| `min_mouth_px` | 28 | Minimum corner-to-corner mouth width, pixels |
| `min_mouth_opening` | 0.07 | Minimum mouth opening / width ratio |
| `tongue_margin` | 4 | Minimum negative-distance minus positive-distance in weighted Lab units |
| `tongue_min_area` | 0.025 | Minimum component fraction of inner-mouth region |
| `tongue_max_area` | 0.8 | Maximum component fraction |
| `tongue_ambiguity` | 0.35 | Reject when second component exceeds this fraction of largest |

The face crop and each eye crop must be in bounds, bright enough, sharp enough,
and not excessively clipped. Eye crops are centered on the corners, width 1.4×eye
width and height 0.9×eye width. Lid ratios outside 0–0.65 are rejected. After fitting,
legacy single-threshold fits additionally reject a ratio above
`max(1.8×open_median, open_median+0.04)`. Guided fits use the feature gate’s 0–0.65
range, so a high-open pose is not rejected merely because the pooled median is lower. A shared bad
face image can invalidate both eyes; their calibration and state decisions remain
independent. These image gates cannot reliably distinguish all occlusions or model
hallucinations. In particular, glasses glare and a covered eye need live evaluation.

Passing image score is `min(1, focus/(4×min_focus), (1-clipped_fraction)/0.8)`.
Tongue score is the minimum of image score, color contrast support, and area support.
A quality score of 1 means these heuristic gates have support, **not 100% accuracy**.
There is no claimed calibrated confidence probability.

## Timing, diagnostics, and data

One worker owns capture and synchronous CPU inference; Tk runs on the main thread.
There is no Python frame backlog. The camera requests 640×480 and the selected FPS;
backends may decline those requests. The capture timestamp is taken immediately
after the read, before inference. It approximates acquisition and does not account
for hidden camera buffering. The status shows actual inter-sample Hz, inference
milliseconds, feature-processing milliseconds, and capture age at processing.

The UI/preview draw at about 10 Hz independently of input sampling. Alongside the
two binary eye scopes, three analog scopes
show raw eye ratios, raw head measurements, and normalized head/tongue values.
X uses actual monotonic capture time; lines between samples are display-only.
There is no detector interpolation, fabricated new sample, or Processing filter.
The displayed raw scope ranges are 0–0.4 for eyes, 0–1 for image head position,
−45–45 degrees for pitch, and 0–1 for normalized values. Numeric readings/CSV retain
values outside those display limits. Invalid normalized measurements are dark
holds for display only; they remain invalid/null in the data.

**Export trace CSV** writes at most the last 9,000 scalar samples (about five minutes
at 30 Hz), initially suggesting ignored `data/private/`. It includes envelope,
selected subject, calibration generation, head units, raw values, per-channel
quality, image gate metrics, eye decision thresholds, uncertainty limits and closed bits, mouth geometry,
tongue candidate/area, validation flags, normalized outputs, validity and reasons.
It saves no images. Raw geometry can remain visible when quality fails; inspect
quality/valid flags before interpreting it. Historical trace rows survive Stop;
current measurements do not. Trace export is explicit, and real traces must stay
out of Git. Settings save/load handles tunables only. App's separate Save active
profile persists fitted parameters; frozen images and raw training pixels remain
in session memory. Real camera video recording/replay is not implemented.

Stop clears outputs immediately. A still-stopping camera worker blocks another
start until it exits; closing waits at most two seconds for backend cleanup.
No-face, source failure, or age beyond `stale_ms` clears current measurements and
cancels unfinished capture, while retaining completed calibration. The sole face
automatically resumes detection on return. Same-source restart keeps learned fits
but clears tongue validation; preview remains disarmed. Geometric movement does not
change the logical `single-user` slot. MediaPipe requests one face; this assumes one
operator and is not identity recognition. Load a different profile or reset for a
different person. See [the single-user test guide](../docs/SINGLE_USER_TESTING.md).

## Tests and remaining live evidence

```bash
VISION_MODEL_PATH=Vision/.local/face_landmarker.task \
  Vision/.venv/bin/python -m unittest discover -s tests/vision -v
Vision/.venv/bin/python -m Vision.benchmark_detection --frames 500
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/integration -v
python3 -m unittest discover -s tests/tooling -v
```

Guided-eye increment: **136 tests passed** (73 Vision, 36 Processing, 20 integration,
7 tooling), including the local-model blank-image smoke. New checks cover multiple
open poses, rejected overlaps, uncertainty bands, independent partial fits, fresh
reopen failure, prompt acknowledgment, duplicate samples, scope gaps, restart/cancel,
profile v1/v2 compatibility, and per-eye button release on uncertain input. The
original unified baseline passed 127 tests.

Native UI inspection with generated pixels covered one-button completion, independent
binary scopes, the Test sound control, leaving the Eyes tab to cancel, and restarting.
No physical camera or real OS mouse input was used. Live-person accuracy, whether
the cues are comfortably audible for the tester, and real gaze variation still need
user testing. Sound playback remains local and asynchronous on macOS.

The detector tests exercise generated pixels, geometry, independent calibration,
both closures, both head modes, failed/repeated collection, dark/blurred input,
tongue absent/present/ambiguous components, transformed mouth geometry, withheld
validation, bystander loss, stale frames, restart, worker stop/error, and CSV export.
Optional real-model smoke uses blank images with transformation matrices enabled;
it does not open a camera. CI installs optional dependencies in a separate job so
pixel tests are not silently skipped there.

On the development Mac, 500 synthetic feature iterations after 50 warmups averaged
**1.91 ms**, p95 **2.38 ms**. This measures image gates, mouth warp and tongue model
only. It excludes neural inference, capture, tracking, frame construction, UI,
and OS output. It cannot establish live FPS. The older `Vision.benchmark` measures
a different geometry/pipeline path and should not be compared as an end-to-end test.

Before treating the detectors as reliable, test a real person in steady and changed lighting.
For each eye, repeat open/closed targets at least ten times and record errors and
invalid frames; include ordinary blinks and both eyes closed. For head Y, record
neutral spread and repeatability of up/down. For tongue, inspect masks during at
least ten absent/visible cycles and both-axis movement, including teeth-only views.
Repeat after moving camera distance and changing glasses/lighting. Save scalar
traces locally, and report false positives, misses, unavailable time, sample Hz,
and latency. Automated synthetic success does not supply these human measurements.

## Module map and handoff

- `features.py`: validated tunables, lid/head measurements, image-quality evidence.
- `tongue.py`: mouth geometry, color training, segmentation and candidate centroid.
- `workbench.py`: subject/session-bound live collection, independent fits and validity.
- `lab_runtime.py`: single source worker, lifecycle, preview and bounded trace export.
- `lab.py`: reusable native calibration view; embedded in App or standalone.
- `presets.py`: versioned fitted-parameter validation/serialization; App coordinates storage.
- `demo_detection.py`: labeled synthetic pixels/landmarks; fake inputs remain a developer API.
- `guided_eyes.py`: geometry stage; `wink_guide.py`: the complete 21-step guide.
- `wink_model.py`: independent per-frame facial appearance features, models and fresh checks.
- `eye_view.py`: temporary full-screen target, sound cues and guide lifecycle; no inference on Tk.
- `eye_scope.py` and `../LabUI/traces.py`: shared display-only unknown holds; no changes to measurement validity.
- `landmarks.py`: optional MediaPipe facial transform extraction; default legacy API unchanged.

No SignalFrame keys were renamed. The workbench marks its internal diagnostics
`diagnostic_only: true`; that label is not an access-control mechanism. App explicitly
forwards a copy to Processing after coordinating source/subject/calibration and
sets that diagnostic flag false. Vision has no Processing/Drivers imports.
`gaze_x/y` and `head_x` remain invalid. The emulator format is still pending.

Primary references: [MediaPipe Face Landmarker Python](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python)
for the local VIDEO task and optional transform;
[OpenCV morphology](https://docs.opencv.org/4.13.0/d9/d61/tutorial_py_morphological_ops.html)
for the mask opening/closing operations. Our thresholds, gates, and validation
criteria above are prototype engineering choices, not claims from those sources.

### Full-screen / unknown-display regression evidence

This later UI increment passed 150 tests: 74 Vision including the local-model smoke,
36 Processing, 33 integration and 7 tooling. The integration total includes five
native Tk tests enabled with `RUN_TK_TESTS=1`; headless CI skips those five unless a
display is explicitly provided. They cover completion and return, Escape/restart,
source loss, cancellation before prompt acknowledgment, and dark trace rendering.
The new trace checks cover unknown holds, initial blanks, context resets, stale
intervals, nonfinite values, bounded historical seeds and unchanged input values.

```bash
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover \
  -s tests/integration -p test_calibration_window.py -v
```

The combined synthetic GUI completed the guide, returned with both fits ready and
showed a dark held trace for an unknown left eye while the right remained valid.
The 490-frame combined demo still exercised all four mouse actions and released
output at EOF. Human testing of the wider target positions is still required.

## Research measurements in the combined App

App requests MediaPipe expression coefficients alongside landmarks/pose. The active
Eyes guide consumes same-eye blink, squint, cheek, brow and wide coefficients plus
normalized geometry. It emits `eye_intent` alongside the unchanged raw eye signals.
The old Detection research UI/runtime is no longer attached to App. Its feature and
gaze modules remain developer utilities; synthetic checks do not establish live
accuracy. See [the current eye guide](../docs/EYE_CALIBRATION_GUIDE.md).
