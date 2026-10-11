# Raw pupil control — current user decision

> [SCREEN_POINTER.md](SCREEN_POINTER.md) updates downstream gaming movement to approximate screen destinations. The no-calibration raw detector behavior here remains current; the velocity-only Processing behavior below is historical.

The user requested skipping pupil calibration and using raw eye-relative iris
position for mouse direction. This supersedes the pupil guide, learned endpoints
and head-pose compensation requirements in PUPIL_HEAD_CALIBRATION.md.

App and Vision lab directly normalize the current raw iris X/Y using the fixed
scale in Vision.pupil: center 0 eye-width units → .5, X ±.2 → 0/1,
Y −.1/+ .065 → 0/1, with valid overshoot saturated. This is a directional joystick,
not screen gaze. No pupil fit, head pose, head guide, saved pose range or fresh
pupil checks are required. Raw eye-width measurements remain available separately;
continuous gaze_x/y and the 11×11 matrix use this same fixed normalization. Mark
frames with gaze_measurement=mediapipe_iris_direction_v3, never compensated space.

Keep both-eye visibility, image/iris quality and binocular agreement checks. The
optional positive open-eye evidence from guided eye geometry remains; no eye fit
is required. Unknown/occluded/stale input remains invalid and releases pointer
motion immediately. Processing keeps gain, radial dead zone, adaptive smoothing,
acceleration limits and explicit Start/Stop. Gaming eye clicks/head keys and the
head-only Mouse test mapping remain independent.

Remove the active pupil guide controls and commands; retained pupil fitting/guide
modules are legacy code for validation/tests. Detector v13 identifies raw pupil
control. Read and validate v1–v12 before migration, preserving compatible eyes,
winks and head fits. Preserve validated v12 pupil fits as inactive stored data;
never apply them to current output. Combined profiles remain v3 and mappings v2.
Loading disarms output. No personal profile files are modified by the migration
until the user explicitly saves. No extra camera, model, dependency or OS changes.
