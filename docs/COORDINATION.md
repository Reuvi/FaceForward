# Main chat and agent coordination hub

## Current head pitch range task

Claim: Reuvi integration, `work/reuvi/integration/head-pitch-range`, base
`d539a78`. Scope: Vision head configuration/calibration/preset migration/display,
App command wiring, relevant tests and documentation. Remove the head measurement
choice; use pitch and show learned up/neutral/down as 0/.5/1. Preserve unrelated
fits and migrate old position presets without treating image fractions as degrees.
Contract first: [MOVEMENT_CALIBRATION.md](../Contracts/MOVEMENT_CALIBRATION.md).

## Previous separate eye guides handoff (d539a78)

Claim: Reuvi integration, `work/reuvi/integration/separate-eye-guides`, base
`f4eb12c`. Authorized scope: Vision's eye geometry/appearance guides and rest UI,
App command wiring, tests, shared contracts and documentation. Separate eye
open/closed calibration from blink/wink training; retries of the latter retain
geometry. Show a central rest countdown together with the next instruction.
Contract first: [EYE_INTENT.md](../Contracts/EYE_INTENT.md). Keep one worker,
independent sampled eye intent, saved fits and capture-timestamp gating.

Implementation handoff:

- Two separately started native guides: `1  Start eye open/closed` (7 steps) and
  `2  Start blinks & winks` (14 steps). Geometry completion returns to the lab;
  it does not automatically start appearance training.
- Blink/wink failure, cancellation, restart and tracking loss preserve completed
  eye geometry and head/tongue fits. Restarting geometry clears dependent wink
  models. Provisional geometry is not promoted until the reopen check completes.
- Geometry-only profiles can be saved and loaded before starting wink training.
  Detector preset v5 and combined profile v3 remain unchanged; compatible saved
  geometry and wink models still load without retraining for this UI change.
- Rest screens show a large decreasing countdown beside the next movement
  instruction. Head/tongue rest panels also show the countdown and upcoming pose.
  Rest/preparation captures remain excluded from training. Eye prompt acknowledgments
  carry the source generation so an old popup cannot acknowledge a new guide.
- Test procedure: [EYE_CALIBRATION_GUIDE.md](EYE_CALIBRATION_GUIDE.md). Per-frame
  independent wink classification, Processing transfer functions and Drivers are
  unchanged. Real-person accuracy and comfort have not been remeasured.

Validation: **250 unique tests passed**: 109 Vision (including the local MediaPipe
blank-image smoke), 65 integration (20 calibration tests plus 45 remaining tests,
including 9 native Tk checks), 69 Processing and 7 tooling. Native checks verify
countdown changes, readable non-overlapping instructions, separate stage buttons,
Escape/cancel and retained geometry. Integration covers failed wink training,
retry, cancellation, loss, geometry-only save/load, stale acknowledgments and
rejection of incomplete geometry. Native teardown cancels test-owned timers.

The 490-frame headless mouse demo accepted all frames, observed left/right/pointer/
scroll and released output at EOF. Changed Python files pass Ruff F checks;
whitespace and integration scope checks pass against `f4eb12c`. Contract landed
first in `433da90`; retain the feature branch when fast-forwarding main.

## Previous tongue-tip handoff (f4eb12c)

Claim: Reuvi integration, `work/reuvi/integration/tongue-tip`, base `0123b8d`.
Scope: Vision crop/color/tip estimator/calibration/profiles, App raw labels, shared
contracts/docs and tests. User authorized trying a visible-tip estimate with the
current color segmentation. Contract first: [TONGUE_TIP.md](../Contracts/TONGUE_TIP.md).
Keep eye/head fits, one capture stream, local execution and invalid-input release.

Implementation handoff:

- `Vision/tongue.py` uses the existing color model over a 160×160 padded crop,
  including protrusion and negative examples on surrounding lips/skin.
  `tongue_tip.py` selects a unique front edge attached to the mouth and reports
  its middle anchored to an observed boundary pixel. Region centroid is debug-only.
- Curved ends use local direction; ambiguous, clipped, short, unsupported and
  sudden-jump tips are unavailable. Mask search has a fixed work bound. Rejected
  tips still count as color candidates during absence checks.
- Raw X/Y use signed mouth-width units, domain −.8 to +.8. Personal coordinates
  still map comfortable limits to 0/1 and neutral to .5. Frames identify
  `color_tip_mouth_width_v1` and `personal_tongue_tip_v1`.
- The camera tab and calibration share tip graphs and original capture rows.
  Overlays show green mask, orange front edge, cyan midpoint and purple attachment.
  Exports include raw tip, debug region center, candidate presence and failure reason.
  Unknown display holds remain dark; tongue controls remain invalid on unknown.
- Detector preset v5 is inside unchanged combined profile v3. Validated v1-v4
  profiles retain compatible eyes/winks/head but discard incompatible tongue
  appearance/ranges. New saved tip ranges require rechecks after load/restart.
- Test procedure and measurement details: [TONGUE_TIP_TESTING.md](TONGUE_TIP_TESTING.md).
  Real camera detection accuracy, comfort and end-to-end latency remain unmeasured;
  matching lip/gum colors and occluding lips can defeat the geometric estimate.
  No new pretrained model, Processing transfer function or driver integration.



Validation: **246 tests passed**: 109 Vision (including local MediaPipe blank-image
smoke), 69 Processing, 61 integration (native Tk checks enabled), and 7 tooling.
Synthetic masks cover straight/diagonal/curved/flat fronts, shape ambiguity,
clipping, insufficient attachment, mouth-opening scale and sudden-jump rejection.
Integration covers the full tongue guide, v4 migration preserving wink/head fits,
failed absence on a region with an invalid tip, shared traces and CSV nulls.
The 490-frame headless mouse demo accepted all frames, observed left/right/pointer/
scroll, and released at EOF. Changed Python files pass Ruff F checks; whitespace
and integration scope checks pass. A broader Ruff scan reported the pre-existing
unused `Path` import in `tests/integration/test_research_lab.py`, left untouched.

Commands: `VISION_MODEL_PATH=<local task file> Vision/.venv/bin/python -m unittest
discover -s tests/vision -q`; `RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest
discover -s tests/integration -q`; Processing/tooling `unittest discover`;
`python3 -m App --headless --frames 490`; `python3 tools/check_scope.py --base
0123b8d --lane integration`; `git diff --check`.

500 synthetic frames in `Vision.benchmark_detection`: **6.24 ms mean / 7.09 ms p95**
for selected-face feature extraction + mouth crop/color/tip work on this machine.
This excludes capture, neural inference, tracking, frame construction, UI and OS
output; it is not end-to-end performance or live accuracy evidence. Contract landed
first in `f05d87d`; feature branch is retained when fast-forwarding main.

## Previous head/tongue calibration and raw views handoff (0123b8d)

Claim: Reuvi integration, `work/reuvi/integration/movement-calibration`, base
`482fa65`. Authorized scope: Vision head/tongue calibration/UI/profiles, App's
camera setup view and shared capture snapshots, contracts/docs and relevant tests.
User requests guided head/tongue calibration, position visualization, basic raw
graphs on the camera tab, and consistent data across tabs. Device-specific transfer
functions and driver integration remain the next stage. Contract lands first:
[MOVEMENT_CALIBRATION.md](../Contracts/MOVEMENT_CALIBRATION.md).

Implementation handoff:

- Head guide: choose image Y or pitch, train neutral/up/down, then check new frames.
  The dedicated mode selector resets only head calibration.
- Tongue: current color appearance training plus absent/center/four-directions
  guide, independent fresh position checks, personal X/Y range, and saved-range
  recheck. Raw candidate, mask and calibrated position planes remain distinct.
- Camera setup defaults to raw measurements and shared raw time graphs. Calibration
  reads the same capture rows, generation, sequence and timestamp. There is one
  worker; UI redraws do not create samples. Plot-only unknown holds stay dark.
- Detector preset v4 adds tongue ranges; combined profile v3 is unchanged. v1/v2/v3
  detector loading is preserved. Older appearance-only tongue profiles need a new
  range; source restart/loading requires fresh absent + five-position checks.
- Added `position_space: personal_range_v1` on calibrated camera frames. Tongue
  outputs now use comfortable endpoints and learned neutral; legacy replay keeps
  its existing interpretation. Eye behavior and Processing/Drivers are unchanged.
- Supplied research reviewed against `Vision/tongue.py` and the existing local
  research benchmark. Current color segmentation excludes protruding tissue and
  measures centroid, not tip. No pretrained model is active. See
  [TONGUE_MODEL_PLAN.md](../Vision/TONGUE_MODEL_PLAN.md) for local model evaluation,
  timing caveats, coordinate/version requirements and recording-session holdouts.
- Testing instructions: [MOVEMENT_CALIBRATION_GUIDE.md](MOVEMENT_CALIBRATION_GUIDE.md).
  Start with detector-demo to exercise the guides, then test actual camera accuracy.

Validation: **235 tests passed**: 101 Vision (including local-model blank-image
smoke), 69 Processing, 58 integration (including 8 opt-in native Tk checks), and
7 tooling. The 490-frame headless mouse exercise accepted all captures, observed
left/right/pointer/scroll and released output at EOF. Native source-view inspection
showed raw graphs before calibration. Synthetic tests cover asymmetric/reversed
ranges, independent repeat checks, unavailable/overlapping input, profile migration,
failed validation, hidden-tab cancellation, late prompt acknowledgments and shared
snapshot consistency. Real-person detection/comfort/latency remain unmeasured.
Ruff F checks, whitespace and integration scope checks pass. The feature branch is retained for the handoff; other agents
should branch from updated main and keep their own worktrees.

## Current simplified wink calibration task

Reuvi asks to remove Detection research and train blink-versus-wink appearance in
the eye calibration flow, without duration-based recognition. Confirmed: per-frame
ON while holding a recognized wink, OFF on reopening; eyes remain independent.
Claim: integration, `work/reuvi/integration/wink-calibration`, base `e5d0daa`.
Scope: Vision calibration/features/models/UI, Processing intent adapter/gate and
profile compatibility, App wiring/UI, their tests and shared documentation.
Contract: `Contracts/EYE_INTENT.md`, committed before implementation. This supersedes
the default research/dwell workflow below; Drivers remain unchanged.

Completed implementation:
- One 21-step full-screen guide: geometry, labeled blinks/relaxed movements,
  three training winks per side, then separate checks with two new winks per side.
  Existing rest/capture sounds and capture-timestamp boundaries remain.
- Eight same-eye appearance features train independent bounded logistic models.
  Missing/overlapping evidence fails the affected eye. No duration/speed or
  opposite-eye feature; no camera click dwell, release delay or cooldown.
- Additive per-capture `eye_intent_v1`; raw eye polarity and driver output unchanged.
  Unknown numeric input holds previous with known=false; output releases.
  Actual fresh opening is required after arming/unknown before activation.
- Removed App's research tab/session/worker work. Added wink scopes, supporting
  feature/ratio graphs, trace fields, per-eye check counts and hidden legacy timing
  controls. Research modules remain for developer tests/old-profile validation.
- New profile/preset v3 stores checked wink parameters, without images or raw
  training vectors. Old v1/v2 load other settings but require the new eye guide.
- Current operator/engineering guide: [EYE_CALIBRATION_GUIDE.md](EYE_CALIBRATION_GUIDE.md).

Validation: 223 tests across Vision (96, including local MediaPipe blank-image
smoke), Processing (69), integration (51, including eight opt-in native Tk checks)
and tooling (7). Relevant tests were rerun after model, graph and UI corrections.
The original headless 490-frame mouse demo accepted all frames, observed all four
actions and ended released. Ruff F checks, diff whitespace and integration scope
checks pass. A synthetic two-eye classification microbenchmark measured ~4 µs per
capture over 10,000 iterations on this machine; it excludes feature extraction,
camera/MediaPipe and UI. This is not a camera FPS or human-accuracy claim.
Pending: real-person blink/wink testing, representative lighting/pose robustness,
then head/tongue calibration testing and the driver's final format.

## Current single-user lifecycle change (October 10)

Reuvi requests one subject instead of simultaneous people, preservation of
calibration through rapid head motion/loss, and saved-file loading. This supersedes
the explicit tracker selection/recalibration-on-loss rules in earlier entries.
Claim: integration, `work/reuvi/integration/single-subject`, base `86f8e17`.
Authorized paths: Vision workbench/capture/UI, App lifecycle/UI, their tests,
contracts and shared documentation/agent instructions. Drivers and transfer
functions are unchanged. Contract lands first; acceptance covers motion/absence,
restart, profile loading without a face, and safe preview release/rearming.

Reuvi designated the conversation that integrated the mouse MVP as the **main
coordination chat**. Use it to collect testing observations, resolve shared
interface decisions, and review changes from the other agents. Component agents
work in their own tasks/worktrees and bring focused handoffs back here.

This file records the agreement and a dated baseline. It is not a live task lock
or automatic view of other conversations. A local edit does not notify another
computer. Put active claims in the shared conversation before coding; bring back
the commit/PR and handoff when ready. Do not send messages to external services
without user authorization.

## Read in this order

1. [Root AGENTS.md](../AGENTS.md), then each component's `AGENTS.md` you will touch.
2. [Testing companion](TESTING_GUIDE.md) for expected current behavior and checks.
3. [Engineering guide](ENGINEERING_GUIDE.md) for formats, algorithms, configuration,
   clocks, diagnostic meanings, and known limits; [raw detection guide](RAW_DETECTION_GUIDE.md)
   for detector implementation status, ML, and camera-only testing.
4. [Adopted MVP interfaces](../Contracts/MOUSE_MVP.md) and
   [original v1 contracts](../Contracts/README.md). The driver output is still a draft.
5. [Team workflow](TEAM_WORKFLOW.md), [agent starters](AGENT_STARTERS.md), and
   [original project notes](ORIGINAL_PROJECT_NOTES.md).

Later explicit user decisions override the original notes. Preserve these already
settled decisions unless the user changes them:

- Local native Python application; no browser/JavaScript/server requirement.
- Mouse-only MVP: independent left/right eyes, head Y scroll, tongue X/Y pointer.
- Each eye is independent, including simultaneous long closures. No both-eye veto.
- Raw mock 1 means closed; Vision's named `*_eye_open` 1 means open.
- Position becomes relative velocity; normalized velocity 0.5 means stopped.
- Gaze is an explicit alternative, not a hidden replacement for tongue.
- Invalid measurements remain unavailable; selected-face loss never transfers control.
- Emulator format remains to be agreed; simulated success is not live face control.

## Baseline and ownership

At the documentation checkpoint, main/origin main included runtime baseline
`481fd34`. It incorporates Vision `9f51fb7` and Processing `d4d3501`; integration
code is `8e9eaa6`. The integration took place on
`work/reuvi/integration/vision-mouse-mvp`. Branch pointers are historical context;
**fetch current main before starting new work**. Older feature worktrees were
preserved, and their owners must update them in their own worktrees.

| Lane | Current human context | Writable paths / responsibility |
| --- | --- | --- |
| Vision | Teammate responsible for AI detection; confirm current task owner in chat | `Vision/**`, `tests/vision/**` |
| Processing | Reuvi is working on this section | `Processing/**`, `tests/processing/**` |
| Drivers | Teammate building the emulator; confirm current task owner in chat | `Drivers/**`, `tests/drivers/**` |
| Integration | Coordinated through this main chat; one active shared-file task | `App/**`, `Contracts/**`, root configuration, shared docs/tools/CI, integration tests |

The team has roughly one person per section. Integration is a responsibility,
not a fourth person. Names/handles are not inferred for unconfirmed assignments.
Two agents in the same lane still need disjoint scopes and separate checkouts.
Different branches alone do not prevent conflicts in the same file or interface.

Only the owning agent edits its worktree/index/environment. Shared camera access
must be coordinated; use synthetic/replay input when another process owns it.
Keep each worktree's dependencies and generated files private. No main-chat agent
should reset, switch, stash, or clean a teammate's active checkout.

## Start and claim a task

From a clean checkout, fetch then create an isolated task, substituting real slugs:

```bash
git fetch origin
python3 tools/new_worktree.py processing your-name tune-dwell --base origin/main
```

Open the directory printed by the helper. Record the **resolved commit**, not only
the moving name `origin/main`. An existing isolated worktree can be reused when
its ownership fits and it is clean; coordinate that reuse first. Claim in chat:

```text
Task and intended behavior:
Human / agent / lane:
Branch and absolute worktree:
Base commit:
Exact writable paths:
Acceptance check:
Shared-interface dependencies:
Status: claimed / working / ready for review / merged / blocked
```

This chat serializes shared-file changes and merges. Component agents propose
interface changes under their own `interface-requests/` directory, with a small
synthetic example. Continue against the agreed interface while the proposal is
reviewed. Do not independently rename keys, flip signs, change clock semantics,
or alter another lane just to make a local test pass.

## Handoff to this chat

Use this at completion, or when blocked on a specific interface decision:

```text
Task / lane / branch / worktree:
Base commit and final commit or PR:
Changed paths:
Concrete behavior before → after:
How to run and reproduce it:
Checks actually run, with exact results:
Contract impact (keys, units, polarity, timing, lifecycle):
What remains mocked, invalid, or untested:
Dependencies / requested decision:
Conflicts or uncommitted files to preserve:
```

Do not say “done” based only on a window opening or a mock producing numbers.
State whether evidence is synthetic, model-only, live camera, or real device
output. Update the owning component's README/handoff with behavior and commands.
Changes to shared semantics also need the contract and integration guide updated.

## Integration procedure

1. Inspect the handoff and diff. Confirm the branch contains only the claimed
   scope, the original base is known, and dependent interface changes are agreed.
2. Fetch remote updates. Merge one component change at a time in an integration
   worktree, preserving teammate commits. Resolve conflicts with the owning lane's
   intent; never force-push or discard their work.
3. Run the affected component checks and integration checks. For processing/source
   changes, exercise the four mouse controls, invalid channels, subject loss,
   freshness, independent eyes, and immediate stop/release. Run the full core
   suites when the changes affect multiple layers. Documentation-only changes
   need accurate examples/links, scope review, and whitespace checks.
4. Use `python3 tools/check_scope.py --base <agreed-base> --lane <lane>` and
   `git diff --check`. Stage explicit paths. Review committed and uncommitted scope.
5. Update behavior documentation and evidence. Merge/push within the user's
   authorization. Main-chat integration and this documentation update were
   authorized for main; individual agents should hand off feature commits rather
   than treating that as blanket permission for unrelated publication.
6. Report the merged commit, checks, launch command, and remaining limitations
   here. The component owner then updates their own worktree from current main.

## Detector implementation checkpoint

The main chat authorized `work/reuvi/integration/vision-calibration-detectors`
from `dcd2e74` to implement native detector calibration in `Vision/**`, its tests,
shared docs and CI. [The detector runbook](../Vision/DETECTION_LAB.md) records the
new independent eyes, head Y and experimental tongue segmentation.

The main chat then authorized `work/reuvi/integration/unified-calibration-lab`
from `b712a73`: App now embeds the same calibration view, drives it from one source
worker and feeds valid values to Processing. Profiles combine detector fits and
mouse settings, bind only after fresh explicit face selection and require new
tongue checks. [App's guide](../App/README.md) is the user workflow. The driver is
still disconnected. Human accuracy/false-positive validation remains pending.
The first three rows below refer to validation/refinement of that implementation.

## Next increments: candidates, not active assignments

| Candidate task | Owning lane | Reviewable acceptance evidence |
| --- | --- | --- |
| Live independent eye calibration and quality | Vision, then App handoff | Explicit selected-face collection; independent valid binary eyes; invalidation on poor visibility/loss; no bystander inheritance |
| Head Y measurement | Vision | Calibrated continuous neutral/up/down values, orientation/quality evidence, invalid on loss; head-reference overlay alone does not count |
| Tongue measurement | Vision | Current color-tip detector supplies mouth-width X/Y and invalidates ambiguous/absent tips; see TONGUE_TIP.md for remaining live validation |
| Per-person transfer tuning | Processing | Comparable synthetic/then-live traces, saved settings, dwell and motion behavior, unchanged public signal meanings |
| Mouse emulator adapter agreement | Drivers with integration | Exact accepted message/example, units/signs, event transitions, timing and release-all/watchdog behavior |
| Validate connected detectors | Vision + Processing in the main chat | Synthetic integration is tested; collect real-person raw → valid measurement → processed-state evidence and tune thresholds |
| Connect emulator | Integration after driver agreement | Synthetic pipeline first; bounded real movement and stop/release checks only in explicit driver mode |

Serialize overlapping Vision work or claim different files first. A candidate is
not assigned until a human/agent claims it in the shared conversation. Keep a
short active task list in that conversation; this repository document should not
pretend to be a synchronized task database.

## Guided eyes handoff — 2026-10-10

Reuvi's main chat requested an easier eye-first guide, open-pose coverage, independent
on/off scopes, removal of mock controls, and audible start/close/reopen/end cues.
Implemented on `work/reuvi/integration/guided-eye-calibration` from `14fce9c`, scoped
to Vision, App wiring, detector/profile contract, tests and documentation.

- `Vision/guided_eyes.py` owns the seven capture-timed steps and per-eye fit/check.
- `calibration.py` learns closed/open raw limits; ambiguous ratios remain invalid.
- `eye_view.py` owns native target/countdown/sounds; `eye_scope.py` draws sampled bits.
- App remains one local Python/Tk program and one image worker; all guide phases
  disarm Processing. Changing tabs only cancels an unfinished guide.
- Detector preset v2 adds limits; v1 remains readable. No SignalFrame/driver changes.
- GUI mock controls are removed; developer fixtures remain. The detector demo now
  follows the eye guide automatically; after fitting it cycles independent closures.
- Follow [the eye testing procedure](../Vision/DETECTION_LAB.md#1-independent-eye-calibration)
  before further head/tongue testing. Synthetic checks do not establish human accuracy.

Future agents must preserve independent channels, explicit face selection, unknown
readings and invalidation/release semantics. A failed eye must not invalidate the
other eye's successful fit. The raw ratio alone cannot distinguish every real pose;
collect user testing observations before expanding head/tongue work.

Validation: 136 tests passed (73 Vision including local model smoke, 36 Processing,
20 integration, 7 tooling). Native synthetic UI completed the guide, plotted both
binary channels, and cancelled/restarted correctly. No live-person accuracy claim.

## Proposed detection reliability work — 2026-10-10

Read [DETECTION_RELIABILITY_PLAN.md](DETECTION_RELIABILITY_PLAN.md) before changing
blink/wink semantics, adding facial substitutes, or implementing head-compensated
gaze. This proposal was checked against runtime `6ed296e` and primary research.
It is documentation only: current independent eye gates, tongue pointer and
head-Y scroll are unchanged. Gesture policy remains a user/profile decision;
strict wink mode must not silently become an opposite-eye veto in the default.

Recommended order: observe/labeled trials → temporal intent prototype → capability
profiles → gaze feasibility → explicit pointer/Drivers handoff. Keep all work in
owning lanes and coordinate feature/profile/event contracts before integration.


## Full-screen eye guide and unknown trace display — 2026-10-10

Main-chat implementation on `work/reuvi/integration/fullscreen-eye-guide`, based on
`93d4ddd`. Scope: Vision guide/scopes and snapshot display history, Processing graph
renderer, App window cleanup/raw graph context, shared `LabUI` presentation helpers,
regression tests and documentation. This is an explicitly coordinated integration
change across those UI surfaces.

- Start eye calibration opens a temporary full-screen native dot guide; sound cues,
  the seven existing phases and independent fitting remain. Escape/Cancel exits;
  completion/retry/loss/shutdown closes the popup and returns to the lab.
- Sample timing waits for the displayed full-screen prompt. No extra camera or web UI.
- Unknown graph intervals use a darker channel color at the previous known height.
  Current values stay unknown and CSV stays null; control invalidation/release is
  unchanged. `LabUI.traces` is presentation only and must never feed Drivers.
- No profile/schema, classifier threshold, gesture policy or hardware mapping changes.

See [testing steps](../Vision/DETECTION_LAB.md#1-independent-eye-calibration).

Validation for this increment: **150 tests passed** — 74 Vision (including the
local-model blank-image smoke), 36 Processing, 33 integration (including five
opt-in native Tk checks), and 7 tooling. The 490-frame demo accepted all frames,
observed all four mouse actions and ended disabled with neutral/released output.
Native synthetic UI inspection confirmed the full-screen target, automatic return,
and a dark held eye trace alongside an unavailable numeric reading. Scope/whitespace
checks passed. No live-person calibration accuracy or real driver output was tested.

## Detection research implementation — 2026-10-10

- Owner/lane: Reuvi integration; task `work/reuvi/integration/gesture-research-lab`, base `baaf8c5`.
- Authorized cross-component handoff: Vision scalar/pose observations and gaze fitting; Processing temporal gesture/model/mapping experiments; App native research tab, labeled data and profiles. Drivers untouched.
- Contract landed first: `Contracts/RESEARCH_LAB.md`. SignalFrame v1 and original mouse preview unchanged; additive feature packet, research preview and profile v2 (v1 readable).
- Defaults: independent eyes, release click, 320 ms minimum per eye, 80 ms open confirmation; strict policy and learned gates explicit. No actual OS input.
- Read `docs/DETECTION_RESEARCH_GUIDE.md` for calibration/trials, exact settings, ownership and test commands. Export human data only to ignored private paths.
- Follow-up dependencies: real-person held-out evidence, comfortable per-user control mapping and final Drivers delivery/monitor-coordinate agreement. Synthetic tests are implementation evidence only.

## Eye-only neutral sample handoff — 2026-10-10 (superseded below)

User requested unknown eye input default to no action while keeping dark graph holds
and sending a sample each frame. Branch `work/reuvi/integration/eye-neutral-samples`,
base `e7dfc75`, coordinates Vision uncertainty flags, Processing eye adapters/gates,
App research handling and tests/docs. Every fresh capture exposes `eye_sample_v1`: numeric
closure 0 with known=false for unknown. Raw/calibration observations remain invalid.
The unknown flag cancels a pending wink; it must never complete a release click or
teach an open baseline. Missing-person captures carry neutral samples while control
stays disabled. No generic head/tongue fallback; future components need their own policy.
See the updated research contract and guide for sample/CSV fields and clock semantics.

Validation: 191 tests passed (59 Processing, 82 Vision, 43 integration with native
Tk enabled, 7 tooling). New coverage checks per-frame unknown samples, independent
eye uncertainty, loss-of-face samples, release-click cancellation, held-button
release, equal timestamps, retained raw evidence and CSV startup/export. Real-model
blank-image initialization passed; real-person detection accuracy still needs live
testing. Changed runtime modules/new tests pass Ruff; compilation, whitespace and
integration scope checks pass. Head/tongue and the Drivers handoff remain unchanged.

## Unknown eye input hold — 2026-10-10

User superseded the numeric-open fallback: unknown eyes now retain each eye's
previous numeric input, still flagged unknown and emitted on every fresh capture.
Integration branch `work/reuvi/integration/eye-held-samples`, base `3024796`, owns
the Processing eye sample/cache, App readout/lifecycle, affected tests and docs.
No prior input starts at 0. Source, selection, profile and calibration boundaries
clear history. Unknowns still cancel timers/release button output; held input is not
new measurement evidence. Dark plot holds remain. Vision observations, Drivers and
other facial components keep their existing contracts.

Validation: 108 relevant tests pass (64 Processing and 44 integration, including
native Tk). Coverage includes closed/open and fractional holds, independent recovery,
unknown cancellation of clicks, no-face frames, ordering, CSV output, profile load,
and restarting the full-screen eye guide. Changed checked runtime modules pass Ruff;
compilation, whitespace and integration scope checks pass. No live accuracy claim.
The research readout now says `unknown / held`; see the research guide's updated
eye-input section for manual testing.

## Rest between guided eye poses — 2026-10-10

User requested eye rest with distinct rest/resume sounds during calibration.
Integration branch `work/reuvi/integration/eye-calibration-rest`, base `cfc8737`,
owns Vision guided-eye timing, sounds/UI/config, App expression-sample gating,
related tests and documentation. Default rest is 3 seconds between the seven poses,
editable before Start; rest frames never train either eye geometry or blink fits.
Live capture/input sampling continues and previews remain disarmed. Preserve
independent eye fits, profile compatibility and the existing unknown-value hold.

Validation: 131 detector/integration tests pass (84 Vision, 47 integration with
native Tk enabled). Tests cover all six rests, sample exclusion including delayed
frames, separate prompt acknowledgment, sound transitions, cancel/restart during
rest, duration validation, old-profile defaults and continued per-frame input.
Compilation, whitespace and integration scope checks pass. Real-model blank-image
initialization passes; no live-person accuracy claim is made. See
`Vision/DETECTION_LAB.md` for the cue table and adjustable rest control.

## Rest-duration field contrast — 2026-10-10

Integration branch `work/reuvi/integration/rest-field-contrast`, base `05d7251`,
fixes the shared Vision eye-guide spinbox's light-on-light inherited colors.
Scoped `EyeRest.TSpinbox` styling uses dark text/caret/arrows on a light field,
with explicit readable disabled and selected colors. Calibration behavior and
other controls are unchanged. Writable paths: `Vision/eye_view.py`, this handoff.
Verification: all 6 existing native calibration-window tests pass; the App's `clam`
theme resolves dark text/arrows on light fields in normal, focused, active and
disabled states. Compilation, whitespace and integration scope checks pass.


## Single-user calibration handoff (October 10)

- Lane/task/branch: integration; persistent single-user detection;
  `work/reuvi/integration/single-subject`; base `86f8e17`.
- Contract commit: `38abdc6`. This explicitly supersedes earlier tracker-bound
  selection and calibration-clear-on-loss behavior at Reuvi's request.
- Changed: Vision camera options, workbench lifecycle and calibration displays;
  App single-user attachment, source/research/profile lifecycle and native UI;
  Vision/integration regressions, active guides, and agent instructions.
- Implemented: one-face MediaPipe inference, stable logical `single-user`, retained
  eye/head/tongue/research fits across movement/absence/staleness/restart, automatic
  detection recovery with preview still stopped, saved-profile loading/export
  without a current face, and explicit Reset all calibration. Replay retains its
  legacy selector. Unknown eye holds and per-capture known flags are preserved.
- Verified: 85 Vision tests including the local model smoke check; 51 integration
  tests including native Tk; 64 Processing tests; 7 tooling tests. All 207 pass.
  Changed Python files pass Ruff F checks; integration scope and diff whitespace
  checks pass. Test commands are the existing unittest discovery commands with
  `VISION_MODEL_PATH` for Vision and `RUN_TK_TESTS=1` for integration.
- Runbook: `docs/SINGLE_USER_TESTING.md` covers camera testing, persistence boundaries,
  save/load, reset, and the implementation. Restart keeps models but requires fresh
  tongue/gaze validation; changing source kind intentionally clears in-memory fits.
- Remaining: real-person camera accuracy still needs user testing. The one-person
  assumption does not identify different people. No OS driver or format changes.
