# Vision measurement plan

For the first implementation's run commands, verified behavior, and remaining
work, see [Vision/README.md](README.md) and [the handoff](HANDOFF.md).

This is a design plan, not an implemented tracker. Use OpenCV for frame capture,
image operations, and pose estimation; use MediaPipe Face Landmarker for face,
eye, iris, and lip landmarks. Tongue localization requires a separate detector.
Vision emits measurements, including binary eye-open classifications for this
MVP. Processing owns gesture activation thresholds, dwell, smoothing for controls,
dead zones, and mappings to actions.

## Existing files and scope

- Follow [Vision instructions](AGENTS.md) and the existing
  [SignalFrame v1 contract](../Contracts/README.md).
- At the inspected base, `Vision/` contains only `AGENTS.md`; no capture or
  measurement implementation exists.
- The primary checkout has a local, untracked `face_landmarker.task`. Its archive
  contains face detection, face landmark, geometry metadata, and blendshape assets.
  This does not verify its provenance, compatibility, accuracy, or tongue support.
  Load it through a configurable local model path; do not move or commit it as part
  of this documentation task. Run an explicit model-loading smoke check later.
- Write to the existing `Vision/` directory; do not create a second lowercase
  `vision/` directory. No shared contract changes are proposed.

## What we will track

“Eye left/right” covers both looking left/right and tracking the two anatomical
eyes separately. “Head Y” means looking up/down by nodding (pitch), not the face's
vertical position in the image and not rotation around the vertical axis (yaw).

| Output | Tracked feature | Reference | Meaning of 0 / 0.5 / 1 |
| --- | --- | --- | --- |
| `gaze_x` | Iris center in each usable eye; combine after individual calibration | That eye's corners and lid frame | User's left / calibrated center / user's right |
| `gaze_y` | Iris center vertically within each usable eye | That eye's local vertical axis and calibrated eye geometry | Up / calibrated center / down |
| `left_eye_open` | Anatomical left upper/lower eyelid separation | Left eye corner-to-corner width | Binary: 0 closed, 1 open; no 0.5 output |
| `right_eye_open` | Anatomical right upper/lower eyelid separation | Right eye corner-to-corner width | Binary: 0 closed, 1 open; no 0.5 output |
| `tongue_x` | Center of a confidently segmented visible tongue region | Head-aligned mouth corners and mouth center | User's left mouth boundary / mouth center / user's right boundary |
| `tongue_y` | Same tongue region center | Head-aligned upper/lower inner lip boundaries | Upper mouth boundary / mouth center / lower mouth boundary |
| `head_y` | Head pitch relative to a captured neutral orientation | Camera frame and user's neutral head pose | Comfortable up limit / neutral / comfortable down limit |
| `head_x` | Head yaw relative to neutral; secondary completeness task | Camera frame and user's neutral head pose | Comfortable left limit / neutral / comfortable right limit |

All eight keys remain present, including unsupported or uncalibrated signals as
invalid. Keep per-eye gaze estimates as internal diagnostics; v1 emits one gaze
pair. Tongue X/Y remain continuous in `[0, 1]`; do not quantize these measurements
into direction labels. Head X/Y retain their existing continuous definitions.
The v1 contract permits intermediate eye openness, but this MVP producer emits
only its valid endpoints, `0` or `1`. Consumers of other v1 producers must still
accept intermediate openness. No new public fields or shared schema are needed.

## Capture and coordinate conventions

1. Start with synthetic fixtures and replay. Enable `cv2.VideoCapture(camera_id)`
   only in explicit camera mode, with App owning startup and shutdown. Use
   `VideoCapture(video_path)` for local replay when needed.
2. Check every `read()` result. Convert BGR to RGB before MediaPipe inference.
   Process the unmirrored frame; mirror only the displayed preview and its overlay.
3. Request a configurable resolution and sample rate. Start evaluation at 640×480
   and a requested 30 FPS, then measure iris/mouth visibility and latency before
   increasing resolution. Requested FPS is not measured FPS.
4. Attach a session ID, increasing sequence, and App-supplied monotonic capture
   timestamp to the frame before inference. If only read-completion timing is
   available, document that approximation and measure buffering delay. Preserve
   the timestamp through asynchronous results; never replace it with inference
   completion time. Rebase replay timing to the shared clock while preserving
   relative sample intervals.
5. Avoid an unbounded inference queue: retain the newest pending frame and allow
   sequence gaps. MediaPipe live-stream mode can drop submissions while busy;
   associate each callback with its original capture envelope.
6. Track at most two faces with session-local IDs. Detection array order is not an
   identity. Associate observations using motion and geometric consistency; end
   a track on ambiguous association or loss rather than assigning another face its
   ID. App explicitly selects the subject/profile and handles reacquisition.

Use pixel coordinates for geometric calculations: convert normalized landmark X
by image width and Y by image height. Otherwise unequal image dimensions distort
ratios and angles. Left/right always means the user's anatomical perspective.
Verify landmark labels against the pinned model/API with an asymmetric test.

The OpenCV capture approach and MediaPipe input preparation follow their
[capture guide](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html)
and [Python guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python).

## Reference frame that moves with the face

Build a head-aligned image frame from stable upper-face landmarks:

- Origin: nose bridge, checked against both eye-corner midpoints.
- Horizontal unit vector: anatomical left eye midpoint toward anatomical right
  eye midpoint (user's right).
- Vertical unit vector: perpendicular, with its sign chosen toward the mouth
  (down).
- Scale: distance between the two eye-corner midpoints, not eyelid opening or jaw
  position.

Subtracting the origin removes image translation; projecting onto these axes
removes in-plane head roll; dividing by scale reduces camera-distance effects.
Derive eye/mouth frames from the same current observation. Do not subtract a
moving head estimate from a tongue measurement from a different timestamp.

This is approximate 2D compensation. Yaw and pitch change perspective, visibility,
and apparent feature size. Do not claim that subtracting a head center fully
removes those effects. Use pose checks and validation to limit the supported pose
range. A future pose-aware image warp needs its own validation, especially for
the nonplanar mouth and protruding tongue; monocular pixels do not supply true
tongue depth.

## Eyes: gaze and independent openness

For each eye, locate both corners, several upper/lower lid pairs, and the iris
center. Use corners to define an eye-local horizontal axis pointing toward the
user's right and an orthogonal downward axis. Let `W` be corner distance, `C` the
corner midpoint, and `I` the iris center:

```text
horizontal_iris_ratio = 0.5 + dot(I - C, eye_right_axis) / W
vertical_iris_offset = dot(I - C, eye_down_axis) / W
openness_ratio = median(upper_to_lower_lid_distances) / W
```

These are diagnostic ratios, not yet contract values. Eye-local references reduce
false gaze movement from head translation, scale, and roll. Do not use iris screen
X/Y as gaze, and do not divide vertical gaze by the changing eyelid gap: blinking
would amplify the result. Closed/occluded eyes make that eye's gaze unavailable.

Calibrate each eye separately while the user looks center, left, right, up, and
down with a comfortable neutral head. Fit endpoint/center transforms so gaze
center becomes `0.5`, left/up becomes `0`, and right/down becomes `1`. Validate
again with small head movements while the gaze target stays fixed. This is a
webcam gaze-direction proxy, not a validated screen-coordinate gaze estimator.

Combine valid calibrated eye estimates using their measured quality. A single
usable eye may supply gaze if that mode has passed calibration/validation. If
both usable eyes disagree beyond a validated tolerance, report affected gaze as
invalid instead of averaging contradictory estimates. Eye openness remains
independent so a unilateral closure does not falsely close both eyes.

For openness, collect comfortable open and closed samples for each eye. Keep the
continuous calibrated score internal and emit a binary classification:

```text
openness_score = clamp((openness_ratio - closed_ratio) /
                       (open_ratio - closed_ratio), 0, 1)
eye_open = 1 if openness_score >= calibrated_open_threshold else 0
```

Choose and validate the threshold per eye using those samples. There is no dwell
wait in this Vision classification; Processing decides whether a sequence of
closed/open states is a blink, wink, or held gesture. Evaluate near-threshold
chatter and let Processing debounce action activation. Vision does not trigger
clicks. Each valid `left_eye_open`/`right_eye_open` value must be numeric `0` or `1`,
never an intermediate fraction.

Reject a missing or degenerate calibration denominator. A visible closed lid can
produce a valid zero; an occluded or unreliable eye remains invalid/null. Clear
classification state on track loss or restart rather than reusing an old state.

## Tongue: use a mouth reference carried by the head

Track the center of the visible tongue segmentation mask, not the mouth center
as a substitute. Keep the chosen feature consistent: changing between centroid
and tip would change measurement meaning. A tip detector can be evaluated later
as a coordinated alternative.

Use the head frame to align the mouth crop, then use local mouth boundaries for
the final measurement. Let `L` and `R` be anatomical left/right mouth corners,
`M` their midpoint, and `T` the detected tongue centroid. The mouth-right axis
points from `L` to `R`; the perpendicular mouth-down axis agrees with head-down.
Let `U` and `D` be the central upper/lower inner-lip points:

```text
W = distance(L, R)
H = dot(D - U, mouth_down_axis)
tongue_x_raw = 0.5 + dot(T - M, mouth_right_axis) / W
tongue_y_raw = dot(T - U, mouth_down_axis) / H
```

Use a user-specific mouth/pose calibration to validate the geometry and sign.
These ratios directly express the v1 mouth-boundary convention: do not remap an
arbitrary resting tongue position to the mouth center. Processing can separately
choose gesture thresholds from the person's comfortable range.

When the head and tongue translate together, `T`, the mouth origin, and boundaries
move together; their relative coordinates should stay stable. Width normalization
also reduces changes caused by leaning toward the camera. This is why the
reference is the mouth attached to the head, not the camera's image origin.

Opening the jaw really changes mouth geometry, so mouth-relative tongue Y can
change even with successful head compensation. Calibrate and test at a comfortable
mouth opening, gate nearly closed mouths (`H` too small), and expose mouth opening
in the diagnostic overlay. If the user needs jaw-independent tongue motion, that
requires a different agreed measurement rather than silently changing v1.

Tongue detection is the largest feasibility dependency:

- Face landmarks and lip landmarks do not establish tongue location. The inspected
  local asset list contains no separately named tongue model; do not infer tongue
  coordinates from face landmarks or a facial-expression score.
- Prototype an OpenCV HSV/Lab color mask inside the aligned mouth region, followed
  by cleanup and candidate-region checks. Treat this as an experiment: lips, gums,
  lighting, and skin tones can cause false positives. Color alone is insufficient
  evidence for valid control.
- Evaluate against tongue-absent frames and varying light, pose, and mouth opening.
  If separation is unreliable, use a separately trained/validated tongue
  segmentation model; training data acquisition and model choice remain open.
- Until a detector meets the acceptance checks, emit both tongue signals invalid.
  Do the same for a hidden tongue, ambiguous candidate, closed mouth, or failed
  mouth/pose reference.
- A protruding tongue can lie outside the lip boundaries. For the MVP, mark those
  out-of-domain positions invalid instead of clamping them into false edge commands.
  Support beyond the mouth requires an explicitly agreed range convention.

## MVP direction zones and later velocity

Keep tongue coordinates continuous at the Vision boundary. Processing may map
them to left/center/right and up/center/down zones for simple MVP actions, using
calibrated thresholds and a neutral dead zone. This simplifies control decisions
without discarding the underlying measurements. Exact physical tongue position
is not required; the goal is a reliable mouth-relative position estimate.

Continuous versus discrete representation does not itself require waiting for
additional frames. Capture, inference, queues, smoothing windows, and gesture
dwell dominate latency. A zone threshold can delay activation until movement
crosses it; quantization is not an inherent latency improvement.

For a later motion-based mapping, Processing can estimate each tongue-axis
velocity from consecutive valid observations of the same selected subject:

```text
dt_seconds = (current.timestamp_ms - previous.timestamp_ms) / 1000
velocity = (current.value - previous.value) / dt_seconds
```

The unit is normalized mouth-range units per second, not pixels or physical
centimeters per second. Require positive elapsed time, the same session/subject,
and an acceptable sample gap. Reset history on invalid input, loss, a changed
calibration/profile, or stream restart. Skip the first sample after a reset; never
compare it with another person or session. Use capture times, including actual
gaps from dropped frames, rather than assuming a fixed FPS.

Two samples are needed to initialize velocity, so the first estimate comes on
the next valid frame; no extra buffering beyond the previous sample is necessary.
Differencing amplifies noise, and mouth/reference changes can contribute apparent
velocity, so validate any filtering and account for its added delay. Discrete-only
positions would yield zero velocity within zones and jumps at their boundaries.
This estimated tongue motion is distinct from the existing ControlFrame velocity
demand: Processing must still map it to bounded `[0, 1]` output if adopted.

## Head Y: calibrated pitch, independent of image translation

Estimate a rigid head pose using `cv2.solvePnP` with corresponding points from a
fixed canonical 3D face model and observed 2D landmarks. Prefer stable nose bridge,
eye corners, and upper-face points; avoid iris centers and moving lips/jaw as pose
anchors. Use enough well-spread, nondegenerate correspondences for the solver.
Use camera intrinsics and distortion calibration for the configured resolution;
approximate intrinsics are an exploratory fallback, not an accuracy guarantee.

OpenCV estimates rotation and translation from these correspondences; see its
[pose documentation](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html).
MediaPipe's optional face transformation matrix can be compared during evaluation,
but its axes/scale must be verified before treating it as equivalent pose.

Capture a neutral rotation `R0`. With head-to-camera rotation `R`, evaluate the
relative rotation `R0.T @ R` in a documented angle convention. Extract pitch around
the neutral head's lateral axis, then choose its sign so looking down is positive.
Verify signs using known up/down motions, not an assumed Euler-angle ordering.
Map comfortable up, neutral, and down samples to `0`, `0.5`, and `1` respectively.
Head X uses separately calibrated yaw with user's right positive.

Do not use nose pixel Y or `tvec.y` as `head_y`: moving the chair or translating the
head vertically would produce a false nod. Pose rotation separates that motion
approximately, subject to model and camera calibration errors. Keep raw pitch/yaw
in degrees as internal diagnostics only. Reject poor reprojection fits, degenerate
geometry, or unsupported pose rather than emitting a guessed angle.

## Calibration, quality, and output

1. App explicitly selects the subject/profile. Collect stable neutral head samples,
   comfortable head limits, eye gaze targets, and open/closed eye samples. Validate
   the tongue reference only when a real tongue detector is available.
2. Use robust sample statistics and reject outliers, overlapping endpoints, small
   ranges, and missing observations. Vision owns detection-coordinate calibration;
   Processing owns persistence and control-response calibration. Integration must
   agree any shared calibration/profile schema before cross-lane imports.
3. Assess quality separately for each measurement using available visibility,
   geometry, pose fit, image resolution, and detector evidence. MediaPipe task
   thresholds and expression scores are not per-signal confidence probabilities.
   Validate any derived quality score; do not hard-code high confidence.
4. Emit each supported calibrated value as `{value, confidence, valid}`. Valid eye
   openness values are `0` or `1`; tongue, gaze, and head coordinates are continuous
   in `[0, 1]`. Confidence stays continuous in `[0, 1]` for every signal, including
   binary eye states. All numeric values must be finite. Missing, uncalibrated, or
   rejected measurements are exactly `{value: null, confidence: 0, valid: false}`. Clip only
   small, validated endpoint noise; reject large out-of-domain errors.
5. Emit `faces: []` for a successfully processed frame with no faces. On capture
   failure, report stream failure through the agreed lifecycle and stop emitting
   fabricated observations. Never repeat the last valid face or tongue indefinitely.
   Processing and Drivers enforce staleness (initial v1 maximum age: 250 ms),
   disable/release on loss, and require deliberate re-arming as specified.

## Implementation order and acceptance checks

| Step | Deliverable | Check before advancing |
| --- | --- | --- |
| 1 | Synthetic/replay source, envelope timing, explicit OpenCV camera mode | Failed reads, irregular timing, restarts, and sequence gaps are handled |
| 2 | Face landmarks, subject association, overlay of reference axes | No/one/two faces; crossing faces and loss never silently transfer an ID |
| 3 | Binary per-eye openness and calibrated gaze | Valid openness is always 0/1; threshold boundaries checked; blinks invalidate gaze; unilateral closure stays independent |
| 4 | Head pitch/yaw calibration and pose quality | Up/down signs; translation does not masquerade as nodding; bad fits are invalid |
| 5 | Tongue detector feasibility and continuous mouth-relative coordinates | Intermediate positions are retained; tongue-absent cases are invalid; head motion alone does not create tongue motion |
| 6 | Full SignalFrame v1 emitter against logging/mocked consumers | All eight signals, envelope preservation, invalid cases, and subject loss match v1 |

For the head-compensation experiment, hold tongue position relative to the mouth
and vary head translation, roll, camera distance, then small yaw/pitch separately.
Repeat for gaze with fixed targets. Plot each measurement against head pose, report
residual drift, and define supported pose/quality limits from observed results.
Set numerical tolerances before enabling dependent controls; there are no measured
accuracy or latency claims yet.

Include synthetic tests for translation/rotation/scale invariance of the 2D
formulas, zero-width/height references, calibration endpoints, nonfinite data,
mirrored preview labels, and mixed valid/invalid signals. Synthetic geometry does
not establish real detector accuracy. Evaluate webcam behavior only in explicit
camera mode and keep any real recordings and calibration data outside Git.

No implementation, model inference, camera access, or OS output is performed by
this plan. Add exact environment/run/test commands under `Vision/` when those
modules exist. The existing shared interface remains unchanged.
