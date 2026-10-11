# Tongue segmentation and pupil joystick detection

Reuvi's integration task `work/reuvi/integration/tongue-pupil-joysticks`, based on
4b8b25d, replaces the active camera's color-only tongue setup with local ONNX
segmentation and adds a calibrated pupil-direction joystick. This supersedes the
color-only requirement in TONGUE_TIP.md for the camera backend. Head pitch and
independent eye/wink semantics are unchanged. Drivers remain simulated.

Tongue: a pinned local YOLOv8n-seg model predicts a mask on each usable mouth crop.
No background color training or tissue clicking is required. Reuse the 160px,
1.6-mouth-width crop and visible front-boundary midpoint estimator. Missing,
ambiguous, clipped or unsupported masks/tips remain invalid. Emit
`onnx_tip_mouth_width_v1`; changing backend/model hash invalidates only tongue
range/checks. Retain the legacy color backend for synthetic/developer fixtures;
never silently fall back to color on a failed model. Show backend, mask, confidence,
reason and inference time. Native capture worker runs bounded inference; every
capture emits one fresh frame, with no cached prediction relabeled as fresh.
There is no runtime download or remote inference. Model license/provenance and
setup instructions must be documented; weights stay ignored outside Git.

Pupil: use MediaPipe iris position relative to each eye's corner axis, normalized
by eye width. Raw X is horizontal-.5 (anatomical right positive); raw Y is downward
eye-width displacement. Both eyes must pass image, iris-geometry and open-eye gates
and agree within a documented tolerance. Show independent raw eyes and combined
raw position. Do not use an occluded eye or switch automatically to a different
single-eye baseline. Center/left/right/up/down capture and fresh checks fit each
axis to 0/.5/1, exactly like a joystick. These are direction coordinates, not screen
gaze or cursor coordinates; head rotation remains a limitation, explicitly gated
outside a modest calibrated head-pose envelope. No fabricated head compensation.
Expose calibrated `gaze_x/y` in existing SignalFrame fields plus additive
`gaze_measurement: personal_pupil_joystick_v1`. Invalid gaze releases pointer
movement. Raw and calibrated scopes use the same capture history across tabs;
dark unknown holds are display only.

Detector preset v6 adds pupil fits/head reference and backend/model identity.
Validate old profiles fully, preserve compatible eyes/head, and require fresh
checks for restored pupil/tongue ranges. Never reinterpret color ranges as neural
segmentation ranges. Combined profile v3 and existing Processing pointer_source
choices (`tongue`, `gaze`) remain: App exposes an explicit source selector that
stops preview before switching and preserves separate input measurements.
Calibration remains detection-only; downstream transfer functions are unchanged.

Scheduling and delayed-sample semantics are superseded by ASYNC_DETECTION.md.
