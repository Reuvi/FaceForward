# Horizontal head calibration

Reuvi integration, base 43b3005, branch
`work/reuvi/integration/horizontal-head`. This activates the existing SignalFrame
`head_x` slot for the calibrated single-user camera path. Vertical `head_y`
remains the working pitch detector. Device mappings/Drivers are unchanged.

Measure horizontal rotation (yaw), not image translation, from the same
MediaPipe face transformation already used for pitch. Raw yaw is
`degrees(atan2(R[0][2], R[2][2]))`; reject missing/degenerate forward direction,
unsupported rear-facing poses and failed face-image quality. No additional
model, camera, blocking inference or dependency is required.

Provide a separate Head X guide: neutral/left/right training, then new
neutral/left/right validation captures, with existing prepare/rest countdowns
and sound cues. Directions refer to the user's own left/right, regardless of
camera mirroring or raw angle sign. Fit each half of the personal range:
left=0, neutral=.5, right=1. Use learned endpoints, existing endpoint tolerance,
and a configurable minimum separation (head_yaw_separation, initially 3 degrees).
Only original, fresh capture-window observations train/check a fit.

Head X and Head Y fits are independent. Starting/retrying/cancelling horizontal
calibration must preserve completed pitch/eye/pupil/tongue fits. Reset Head X
clears only that fit. Missing/stale/uncalibrated/out-of-range yaw stays invalid;
unknown graph intervals use dark display holds, never fabricated controls.

Expose raw yaw degrees/quality/reason and normalized head_x in the same capture
trace used by camera setup and calibration. Show a horizontal position indicator,
raw and calibrated scopes and learned left/neutral/right references. Raw degree
displays use learned limits where available; normalized displays stay 0–1.

New detector saves use preset v7, algorithm `independent-head-axes-v7`, retaining
v6 fields plus nullable `head_x` AxisCalibration. Existing `head` remains pitch.
Read and fully validate v1–v6; preserve compatible fits and leave horizontal
uncalibrated when absent. v7 requires pitch-mode settings and validates yaw
limits within ±90 degrees, minimum separation and matching endpoint tolerance.
Combined profile remains v3. Loading works without a face and never arms output.
Head fits survive normal single-user loss/restart under existing rules.

The active mouse mapping continues using head_y for vertical scroll. Horizontal
detection is available for the later device/transfer-function stage; no implicit
horizontal scroll or cursor remapping is introduced.
