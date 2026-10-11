# Application integration

**Current user decision — tongue retired:** read [../Contracts/TONGUE_RETIREMENT.md](../Contracts/TONGUE_RETIREMENT.md).
App and Vision lab have no tongue detection, worker, calibration, graphs or input
choice. App uses fixed pupils for pointer movement; preserve independent eyes and
head axes. Detector presets v11 migrate older files without restoring tongue.
This supersedes historical tongue requirements below.

This directory belongs to the integration owner. Read the root `AGENTS.md` and
`Contracts/README.md`. Wire public Vision, Processing, and Drivers interfaces;
do not duplicate their logic. Own lifecycle, selected subject/profile, camera
ownership, clock/timebase, configuration assembly, and stop/shutdown behavior.

Begin with fixture → processor → logging driver. Make replay/mock mode explicit
and available without hardware permissions. Ensure only one live input driver is
enabled, and disable/release output before switching subjects or profiles.
Add whole-pipeline checks under `tests/integration/` when implementation begins.

The native MVP is implemented: read `README.md` and `Contracts/MOUSE_MVP.md`.
`MouseSession` owns the single Vision worker and connects dictionaries directly
to `Lab.ingest`. `IntegratedDesktop` extends the existing Tk lab. Keep input,
processing, and drawing clocks independent; no browser/JS/HTTP transport. Stop,
EOF, and errors must call `Lab.disconnect` immediately. Preserve source ownership
and the single-user lifecycle in Contracts/MOUSE_MVP.md.
The camera/detector demo automatically attaches one logical subject; geometric
tracking changes and brief loss must not erase calibration. Keep explicit subject
selection only for legacy replay. Camera and detector-demo use Vision's externally
driven `LabRuntime.ingest`; never start its worker inside App. Embed the same
calibration view and preserve source/subject when changing tabs. Versioned profiles
combine separately validated detector and Processing settings; loading works while
stopped/without a face, disarms preview and clears tongue
validation. Same-source restart preserves learned detector/wink fits; switching
source kind or explicit Reset all calibration clears them. Never auto-arm on return.
Collection also disarms preview. Preserve invalid controls until each detector is calibrated.
Do not report synthetic success as live detector accuracy or driver completion.

The active App has one preview and no Detection research tab/session. Embed the
separate Eye open/closed and Wink action guides in Detection calibration.
Blink retries must preserve completed geometry; both start commands disarm and
reset Processing eye history. Persist geometry-only profiles without requiring winks. Read `../Contracts/EYE_INTENT.md`.
Hide legacy eye timer controls in App; legacy component/replay formats retain them.
Save profile v3 without research; accept validated v1/v2 files without reviving their
research runtime. Never restore old event models as frame classifiers.

Read `../Contracts/MOVEMENT_CALIBRATION.md` for guided head/tongue ranges and
shared capture diagnostics. Detector presets are v5; combined profiles remain v3.
Use the same workbench trace in camera setup and calibration. No UI-sampled history
or second camera owner. Keep tongue raw mouth coordinates separate from personal ranges,
require fresh saved-range rechecks, and preserve invalid observations. Read `../Contracts/TONGUE_TIP.md`: the current expanded crop reports the middle
of the visible front boundary in mouth-width units. Invalid tips never fall back
to a centroid. v1-v4 tongue appearance/ranges require retraining. Future model/crop
changes also require a versioned contract and fresh calibration.

Current short guide: open/left/right training then fresh open/left/right checks,
with no natural-blink class, blink counts, or mandatory surrounding-muscle contrast.
The tongue guide waits for the user to acknowledge each pose, supports retrying a
failed pose, and has an always-visible reset that cancels only tongue work.
Clear tongue marks preserves background samples; frozen overlays show actual marks.

## Neural tongue and pupil joystick update

Read Contracts/JOYSTICK_DETECTION.md (relative to repository root) and
docs/TONGUE_PUPIL_TESTING.md. Camera tongue now uses pinned local ONNX masks with
no color calibration; synthetic/developer fixtures retain the legacy color path.
Pupil calibration produces eye-relative direction, not screen gaze; both eyes
must be usable. Head pitch remains unchanged and known to work for the user.
Detector v6 stores neural model identity/pupil range/head reference; v1–v5 remain
readable. Tongue and pupil loaded/restarted ranges require fresh checks. Keep one
camera and a shared trace with independent neural model scheduling, no runtime
downloads, no stale mask reuse, and
no fallback from neural detection to color. Pointer source is explicitly chosen
in App and changing it stops preview. See Vision/TONGUE_MODEL_NOTICE.md for license.

## Independent scheduling update

Read Contracts/ASYNC_DETECTION.md relative to the repository root. It supersedes
older same-worker/no-second-worker instructions for neural tongue inference.
Keep one camera and shared trace; isolate independent models in bounded workers,
preserve original sample timestamps, and never wait for tongue on the fast path.

## Horizontal head update

Read Contracts/HEAD_HORIZONTAL.md relative to the repository root. Add independent
yaw/head_x beside pitch/head_y; the pitch-only measurement-mode rule remains for
vertical detection. Guides and fits are separate. New detector presets are v7,
with v1–v6 readable; combined profiles remain v3. No implicit device remapping.

## Direct pupil update

Read Contracts/DIRECT_PUPILS.md relative to the repository root. It supersedes
pupil fitting/rechecks above: normalize MediaPipe iris direction directly on every
usable capture. No pupil guide or calibrated pose/eye gate. New detector presets
are v8 with sensitivity settings; fully validate then discard legacy pupil fits.
Combined profiles remain v3; all other detector calibration remains independent.

## Lip boundary and head X reliability update

Read Contracts/LIP_BOUNDARY_HEAD_RELIABILITY.md relative to the repository root.
The user reversed the proposed no-calibration Head X change: keep its guide and
fit, saturate valid measurements past endpoints, and retain a working fit across
failed retries. Head Y stays unchanged. Camera tongue defaults to an experimental
local color extension outside MediaPipe's outer lips, in the independent worker;
ONNX remains an explicit option. Presets v9 validate/migrate older files, preserving
compatible other fits. Combined files stay v3.

## Fixed pupil matrix update

Read Contracts/PUPIL_MATRIX.md relative to the repository root. Pupil detection
requires no calibration or adjustable sensitivity. Presets v10 validate and
discard old pupil settings, retaining compatible other fits. Add an 11×11
one-hot pupil matrix on every capture while retaining precise gaze_x/y for
Processing. Unknown matrix values are null; dark display holds are presentation
only. Preserve independent eyes/winks, head axes and tongue scheduling.
