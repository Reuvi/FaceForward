# Agent working agreement

**Current screen pointer decision:** read `Contracts/SCREEN_POINTER.md`.
Gaming defaults to an approximate primary-display destination from raw pupils;
it arrives and stops. No pupil calibration is added. Mapping v4 supports target
and velocity; v1/v2 import as velocity and v3 retains its saved mode. Mouse test
stays head velocity. Both mappings have independent downward boosts and lighter
filters; preserve mapping pointer tuning when loading face calibration.
Keep target position filtering/dead band separate from velocity shaping, with
zero-speed holds on unknown input. Driver ABI stays v3; face/detector files stay v3/v13.

**Current raw pupil decision:** follow `Contracts/RAW_PUPIL_CONTROL.md` (repository root).
Pupils use fixed-scale raw iris X/Y with no pupil guide, learned endpoints or
head-pose compensation gate. Prior calibrated-pupil requirements below are
superseded. Keep adaptive Processing, visibility checks, independent eye/head
calibration and head-only Mouse test. Presets v13 preserve validated old fits
as inactive data; combined profiles stay v3.

**Current pupil / Mouse test update:** read `Contracts/PUPIL_QUALITY_MOUSE_TEST.md`.
Gaming retains calibrated pupils, with personal open-eye evidence and adaptive
velocity smoothing. The built-in Mouse test mapping uses calibrated head X/Y only,
ignoring eyes/pupils/keys/clicks/scroll. Mapping files are v2 (v1 readable); detector
v12 and combined profile v3 remain unchanged. This supersedes pupil-only App
pointer instructions for the explicitly selected Mouse test mapping.

**Current driver connection:** read `Contracts/DRIVER_CONNECTION.md` and
`docs/DRIVER_CONNECTION_GUIDE.md`. App connects the merged ABI v3 driver through
public Python bindings and an injected Processing sink. Native output is an
explicit Camera-only mode; Stop/close release it. Eye activations produce single
clicks, head controls hold keys, and pupils request velocity. Preview remains the
default. This supersedes older statements that Drivers integration is pending.

**Latest pupil update:** follow `Contracts/PUPIL_HEAD_CALIBRATION.md` (relative to repository root). Personal pupil endpoints and head-angle compensation supersede fixed/no-calibration mapping below. Tongue remains retired.

**Current user decision — tongue retired:** read [Contracts/TONGUE_RETIREMENT.md](Contracts/TONGUE_RETIREMENT.md).
App and Vision lab have no tongue detection, worker, calibration, graphs or input
choice. App uses calibrated pupils for pointer movement; preserve independent eyes and
head axes. Detector presets v12 migrate older files without restoring tongue.
This supersedes historical tongue requirements below.

Build a camera-based accessibility controller: **Vision → Processing → Drivers**.
Read `docs/ORIGINAL_PROJECT_NOTES.md`, `README.md`, `docs/TEAM_WORKFLOW.md`, and
`Contracts/README.md` before editing. The original notes capture the team's intent;
the implementation plan and technical contracts add provisional design choices.
Later explicit team decisions take precedence over the original brief.
Read the `AGENTS.md` in every component you will touch, even if your session starts
at the repository root. User instructions take precedence over this agreement.

Current executable baseline: `python3 -m App` opens the native Vision + Processing
mouse MVP. Read `App/README.md` and `Contracts/MOUSE_MVP.md` for actual capabilities
and adopted local interfaces. Keep all four mouse mappings independent, preserve
invalid detector values, and keep simulated sources explicitly labeled. App now embeds
Vision's calibration UI and uses one capture worker for calibrated eyes, head Y and
experimental tongue segmentation. Read `Vision/DETECTION_LAB.md` and `App/README.md`.
The camera/detector lab is single-user: automatically attach its sole face as
`single-user`, preserve completed calibration across motion/loss/staleness and
same-source restarts, and pause output on missing input. Profiles can load while
tracking is paused; loading disarms output and requires fresh tongue validation.
Real-person accuracy and Drivers integration remain pending.
The standalone tools are optional developer entry points; preserve their independence.

Reuvi's main integration conversation is the coordination hub for other agents.
Read `docs/COORDINATION.md` before claiming work and return its handoff template
to that conversation. Read `docs/ENGINEERING_GUIDE.md` for implementation details
and `docs/TESTING_GUIDE.md` for expected test behavior. These documents describe a
dated baseline; check current code and commits before assuming an item is unchanged.
Update relevant documentation when behavior, settings, or interfaces change.

Eye calibration now opens a temporary native full-screen dot guide and returns to
the lab on completion/cancel. `LabUI` owns shared display helpers: unknown plot
intervals hold the previous known height in a darker color. This is presentation
only; preserve null/invalid observations and immediate control release. The current
user-requested eye exception is an explicit previous-value Processing input
with known=false on every unknown capture (0 only before any history).
Raw/calibration data and dark graph holds remain separate. See
Contracts/EYE_INTENT.md. Never feed a plotted hold into control.

Guided eyes now have configurable rest intervals (default 3 seconds), separate rest,
ready and capture cues, and phase-aware prompt acknowledgments. Rest/preparation
frames never train eye geometry or facial coefficients; gate by the original capture
timestamp and guide capture window. Camera/input sampling continues during rest.

## Start every task

1. Run `git status --short --branch` and `git worktree list`. Preserve existing work.
2. Use one branch and one worktree per active agent. Never share an active checkout,
   including between two agents belonging to the same person. Never change another
   agent's branch, index, environment, or files.
3. Use `python3 tools/new_worktree.py <lane> <developer> <task> --base <ref>` to
   create a worktree. Lanes: `vision`, `processing`, `drivers`, `integration`.
   An already isolated checkout may be used directly if its lane and ownership fit.
4. State your lane, task, writable paths, and base commit before changing code.
   Claim the task in the team's shared issue/PR or conversation; an unpushed local
   file is not a cross-computer lock. Do not message external services unless the
   user has authorized that action.

## Ownership

| Lane | Writable paths |
| --- | --- |
| vision | `Vision/**`, `tests/vision/**` |
| processing | `Processing/**`, `tests/processing/**` |
| drivers | `Drivers/**`, `tests/drivers/**` |
| integration | Shared contracts, application wiring, root configuration, tools, CI, shared documentation, integration tests |

The team has roughly one person per section: Vision, Processing, and Drivers.
Each person's agents stay within that section unless a handoff is coordinated.
Integration is a rotating responsibility, not a required fourth teammate. Only one
integration task may change shared files at a time. The integration lane can edit
component code only as part of an explicitly coordinated handoff or integration fix.

Keep component dependencies, examples, notes, and tests in the owning paths. For a
shared-file/interface change, write a proposal under your component's
`interface-requests/` directory and have the integration owner land it first. Use
the existing contract and mocks while waiting. Do not independently rename keys,
change units, or edit another lane's files. An explicitly assigned cross-lane task
can use an integration branch with the affected owners coordinated.

## Interface and runtime rules

- `Contracts/README.md` defines the initial v1 interfaces. Examples are synthetic.
- Vision emits measurements; Processing applies calibration and mappings; Drivers
  adapt control state to OS/device APIs. Never import one lane's internals into another.
- Start development with fixture/replay inputs and a logging driver. Real camera
  access and live OS input are explicit runtime modes.
- Driver-facing magnitudes are finite values in `[0, 1]`, including the endpoints.
  Missing measurements are invalid/null, never fabricated neutral measurements.
- Tracking loss, invalid control input, stale frames, and a stop action must disable
  output and release held buttons. Reacquisition must never auto-arm output.
  The single-user calibrated path assumes
  the sole observed face is the operator; it does not recognize identity.
- Keep real camera recordings, face profiles, transcripts, credentials, and local
  calibration data out of Git. Synthetic fixtures belong in the owning test folder.

## Finish every task

- Run relevant component checks and `git diff --check`. Do not claim unrun checks pass.
- Run `python3 tools/check_scope.py --base <agreed-base-ref> --lane <lane>`; it checks
  committed, staged, unstaged, and untracked paths relative to the base.
- Review `git diff` and `git status`. Stage explicit paths, excluding others' work.
- Deliver a focused commit/PR with files changed, behavior, commands/results,
  contract impact, and remaining dependencies. Use `.github/pull_request_template.md`.
- Merge shared interface changes before dependent feature work. The integration
  owner merges one PR at a time and checks the complete mock pipeline.
- Never force-push a shared branch, reset/clean other people's work, or bulk-format
  unrelated files. Use feature branches by default; direct updates to main are
  allowed when explicitly authorized by the user, after fetching and preserving
  teammates' changes. Publish only within the user's authorized scope.
  Instructions and the scope checker are coordination
  aids, not a filesystem sandbox or a guarantee of conflict-free merges.

## Current eye calibration contract

Read `Contracts/EYE_INTENT.md` and `docs/EYE_CALIBRATION_GUIDE.md`. Detection research
is removed from the unified App; its retained modules are legacy/developer code.
Two separately started full-screen guides collect eye open/closed geometry and
open/closed-action appearances with fresh checks. Retrying/cancelling/failing wink-action training
retains completed eye geometry. New geometry clears dependent wink models, and
provisional geometry cannot seed wink training before its reopen check. Rest screens
show the countdown and upcoming instruction together. Same-eye facial features classify each
captured frame. No duration/speed, opposite-eye gate, dwell or release delay may
control the calibrated wink path. ON requires valid closed geometry and matching action appearance; open and
supported closed non-actions are OFF; unknown is held numeric input with known=false and released
output. Actual reopening re-arms an eye after unknown. Keep raw anatomical eye
fields unchanged and emit the additive `eye_intent` sample for every capture.
New combined profiles are v3, detector presets v5, with checked appearance models;
old v1/v2 files load but require new wink calibration. Tests with synthetic faces
are software checks, not measured human accuracy.

Read Contracts/MOVEMENT_CALIBRATION.md and docs/MOVEMENT_CALIBRATION_GUIDE.md before
changing head/tongue. Shared raw graphs use original workbench captures across tabs.
Head and tongue guides fit personal ranges then check new captures.
Head calibration always uses pitch: no mode selector/settings choice. Map learned
up/neutral/down to 0/.5/1, and scale raw degree displays to learned limits. Loading
legacy position-mode head fits clears only the incompatible head fit; compatible
other calibration survives. Keep raw degrees separate from normalized position.
Tongue needs appearance plus a personal range; saved ranges need fresh rechecks on load/restart.
Read Contracts/TONGUE_TIP.md and docs/TONGUE_TIP_TESTING.md. The color detector now
reports the visible front-edge midpoint in mouth-width units. Reject ambiguous
tips; never substitute the region centroid. v1-v4 profiles discard old tongue
appearance/range and preserve compatible eye/wink/head fits. New tongue models/crops must version
their coordinate space and invalidate incompatible fits; see Vision/TONGUE_MODEL_PLAN.md.
Device-specific transfer functions and Drivers remain downstream.

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
