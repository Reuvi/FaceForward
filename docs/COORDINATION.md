# Main chat and agent coordination hub


## Pupil quality and Mouse test handoff

- Lane / task: Reuvi integration, `codex/integration/pupil-quality-mouse-test`.
  Base `201dcf4`; isolated worktree `reuvi-integration-pupil-quality-mouse-test`.
  Explicit user assignment spans Vision pupil quality, Processing mappings/filter,
  App selection/diagnostics, related tests and shared docs. Contract first:
  `b85f128`, [PUPIL_QUALITY_MOUSE_TEST.md](../Contracts/PUPIL_QUALITY_MOUSE_TEST.md).
- Behavior: optional completed same-eye guided open geometry supports narrow open
  pupils without changing coordinates or stored fits. Strong closure, image/iris
  failures and binocular disagreement still invalidate. Gaming uses a coupled
  1€ velocity filter; the earlier fixed filter remains selectable. Mouse test
  combines calibrated head X/Y and ignores all eyes/pupils/keys/clicks/scroll.
  Both axes must be valid; invalid input neutralizes immediately. Mapping changes,
  stale input, Stop and source loss retain explicit rearming and driver release.
- Interfaces: new mapping JSON v2 fields `input_mode` and `adaptive_pointer`;
  strict v1 migration supported. SignalFrame/device_control_v1, detector v12,
  combined profile v3 and driver ABI v3 unchanged. Diagnostics identify selected
  pointer input and head rejection reasons. Personal data remains untracked.
- Verification: 109 Processing tests passed; 138 integration tests passed with
  Tk enabled and the compiled driver in dry-run; Vision ran 158 tests, 156 passed,
  two optional skips, with the local model smoke enabled. Both 490-frame demos
  accepted 490 frames and ended disabled with no held inputs or driver error.
  Mouse test emitted 509 movement events and no other event types; gaming emitted
  movement, 3 left/3 right clicks and 4 key downs/4 key ups covering W/Space/Shift/S.
  Synthetic adaptive comparison: velocity noise std .004048→.003265; 90% step
  response 210→90 ms. The 10k-tick base Processing benchmark measured mean 47.18µs,
  p95 65.83µs. Ruff F, compilation, whitespace and integration scope checks passed.
- Remaining evidence: real-person pupil availability/accuracy and adaptive tuning
  require a live trial. No camera recording, new model, dependency or OS driver
  implementation change. Saved `best3.json` already contains guided eye geometry
  and both head fits (local metadata checked read-only). Restart App for new code;
  select Mouse test, load/calibrate both head axes, center head, Start live control.


## Current quick wink / tongue reset task

Claim: Reuvi integration, `work/reuvi/integration/quick-winks-tongue-reset`, base
`8f13166`. Scope: Vision wink training/model/UI and tongue reset/setup UI, App
commands/copy, Processing's additive OFF-state decoder, relevant tests/contracts/docs.
Shorten wink learning to open/left/right plus fresh checks, drop natural-blink
training, require valid closed-eye geometry for action, retain independent samples.
Fix reset during tongue capture and clarify all setup steps. Preserve other fits.
Contracts land first: EYE_INTENT.md and TONGUE_TIP.md.

Implementation handoff:

- Wink action uses six captures (open/left/right to learn, then fresh checks),
  about 32 seconds at defaults; four captures when only one eye has geometry.
  Removed natural-blink prompts/counts, repeated attempts and mandatory muscle
  contrast with blinks. The same small per-eye appearance model learns the action.
  Valid closed geometry is now required for ON; uncertain geometry cannot be
  overridden by a positive appearance score. No runtime duration or opposite-eye
  gate. Existing geometry survives action-guide retries.
- OFF samples can use `closed`, accepted by the Processing adapter alongside
  historical `blink`. The new producer never claims to identify a natural blink.
  Natural blinks may match the learned action. Saved model shapes and profile
  formats are unchanged; minimum fresh-check counts follow the shorter guide.
- Tongue position prompts wait for **I'm in position — capture** at every pose.
  Rest stays timed. Live tip reason is visible beside instructions. **Retry this
  pose** retains successful groups/appearance and rechecks only the failed pose;
  a complete passing guide is still required for normalized output.
- Reset stays visible above scrolling setup, works during tongue capture/guide
  and without a face, clears stale mask/tip/marks/colors/range/checks, and retains
  eye/head fits. Unrelated active calibration still blocks it. **Clear tongue
  marks — keep background** recovers from a bad tissue click. Frozen overlays
  show actual clicked patches; click coordinates account for image placement.
  Numbered appearance controls enable as prerequisites are collected and show
  preparation/capture countdowns. No color segmentation/tip algorithm was replaced.
- Current instructions: [eye/action guide](EYE_CALIBRATION_GUIDE.md),
  [movement guide](MOVEMENT_CALIBRATION_GUIDE.md), and
  [tongue tip testing](TONGUE_TIP_TESTING.md). Actual camera accuracy remains to
  be tested by the user; synthetic checks are software evidence.

Validation: **253 unique tests passed**: 110 Vision (local-model smoke run
separately), 73 integration (21 calibration, 14 movement, 10 native calibration
window, 28 remaining) and 70 Processing. Native tests cover pause-before-capture,
visible reset, failed-pose retry, actual marks/clear, button prerequisites and
unchanged eye geometry. The headless 490-frame mouse demo accepted every frame,
observed left/right/pointer/scroll and released at EOF. Changed Python files pass
Ruff F checks; whitespace and integration scope checks pass against `8f13166`.
Contracts landed first in `1bd209a` and `ad62462`.

## Previous head pitch range handoff (8f13166)

Claim: Reuvi integration, `work/reuvi/integration/head-pitch-range`, base
`d539a78`. Scope: Vision head configuration/calibration/preset migration/display,
App command wiring, relevant tests and documentation. Remove the head measurement
choice; use pitch and show learned up/neutral/down as 0/.5/1. Preserve unrelated
fits and migrate old position presets without treating image fractions as degrees.
Contract first: [MOVEMENT_CALIBRATION.md](../Contracts/MOVEMENT_CALIBRATION.md).

Implementation handoff:

- The native lab always uses transform pitch. Removed the position/pitch selector
  and mode-switch command; mode and legacy position separation are absent from
  editable settings. Old settings cannot re-enable image-position measurement.
- `Start head pitch guide` learns comfortable up/neutral/down, then checks new
  captures. The existing piecewise linear normalization maps these references to
  0/.5/1, including unequal ranges and reversed pitch signs. Small overshoot keeps
  the existing tolerance; large overshoot/missing transform stays unavailable.
- Shared raw pitch graphs and the purple bar now use learned degree limits;
  normalized graphs/green bar remain 0–1. The panel labels each learned angle
  and its corresponding output. Raw samples and CSV units remain degrees.
- Fully validated legacy position-mode presets (including missing mode) migrate
  to pitch settings and discard only their incompatible head fit. Compatible
  eyes/winks/tongue survive under existing version rules. Saved pitch fits load
  unchanged; detector v5 and combined profile v3 are unchanged.
- Updated [movement testing instructions](MOVEMENT_CALIBRATION_GUIDE.md). Real
  camera accuracy/comfort still requires the user's trial; no Processing transfer
  functions or Drivers changed.

Validation: **177 unique tests passed**: 109 Vision, including the separately run
local-model smoke, and all 68 integration tests (20 calibration, 11 movement,
9 calibration-window checks, 28 remaining). Opt-in native checks were enabled
for their separate runs. New checks cover asymmetric/reversed ranges and exact
endpoints, image translation versus pitch, missing transforms, repeated guides,
legacy/malformed preset migration, and native bar endpoints/labels with no mode
selector. The 490-frame headless mouse demo accepted all frames, exercised all
four outputs and released at EOF. Ruff F, whitespace and integration scope checks
passed against `d539a78`. Contract landed first in `ed2d3b6`.

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

## Active tongue replacement + pupil joystick — October 10

Reuvi integration, branch `work/reuvi/integration/tongue-pupil-joysticks`, base
4b8b25d. Scope: Vision detector/calibration/UI/profile, App selector/lifecycle,
contracts, guides and relevant tests. User reports color segmentation unusable
and requests pupil direction as a second joystick. Preserve working head pitch.
Contract: JOYSTICK_DETECTION.md, landed before implementation. No Drivers changes.

### Tongue/pupil joystick handoff

- Contract landed first as d9403ca. Camera uses the pinned local YOLOv8n-seg backend;
  its mask feeds the existing visible front-boundary midpoint estimator. Neural
  setup removes color background capture, patch clicks and pixel-recall gating.
  Color fixtures remain available for developer tests, with no camera fallback.
- Added both-eye iris-direction measurement, full-screen center/four-direction
  guide with Space-to-capture, rests/sounds, retry, fresh checks, normalized 0–1
  output, raw per-eye scopes and camera-setup plots using one capture history.
- Explicit App pointer selector uses existing Processing `pointer_source` and
  preserves all other settings while stopping preview. No transfer-function or
  Drivers changes. Head pitch detector/calibration/normalization is preserved.
- Detector v6 persists model identity and pupil fits/head reference. Old files are
  validated; incompatible color ranges are removed when neural mode is active.
  Eyes/head survive. Restored pupil/tongue ranges require rechecks. Unknown control
  inputs remain invalid; dark held values are display-only.
- 268 unique tests pass: 118 Vision (including real local MediaPipe and tongue model
  smoke checks), 80 integration (native Tk enabled), 70 Processing. The 490-frame
  headless demo accepted every capture, observed all four actions and finished
  disabled/released. Focused tests cover decoder/NMS/errors, missing-model absence
  rejection, pupil direction/closure/loss, range normalization, old-profile migration,
  persistence/rechecks, source selection/settings preservation and native popup keys.
- Changed Python passes Ruff F; whitespace and integration scope checks pass.
  Warmed tongue inference on generated crop: median43.74ms/p95 46.60ms, 20 calls,
  ONNX Runtime1.31.0 CPU/four threads. This excludes camera/MediaPipe/UI.
- Model/dependency installed locally on Reuvi's machine, not committed. Runtime
  remains offline. Source/license/setup: Vision/TONGUE_MODEL_NOTICE.md.
- Testing instructions: docs/TONGUE_PUPIL_TESTING.md. Remaining: actual camera
  tongue precision/tip quality, pupil drift under head motion, end-to-end FPS and
  personal usability; no synthetic-test claim of live human accuracy.

## Independent detector workers — active October 10

Reuvi integration, branch `work/reuvi/integration/independent-detector-workers`,
base `0d1db08`. User requires tongue latency to stop blocking other detectors.
Writable paths: Vision worker/workbench/calibration/UI, App lifecycle, Processing
channel freshness, corresponding tests, contracts and documentation.
Contract: `Contracts/ASYNC_DETECTION.md`, landed before implementation.
Head/eye/pupil measurements and Drivers behavior remain otherwise unchanged.

### Independent detector workers handoff

- Contract landed first as `492da72`. Neural tongue loading, ONNX inference, mask
  decoding and front-edge extraction now run in a spawned local process with one
  inference thread. Camera/Tk use a short-lock handoff: one active crop, one
  replaceable pending crop, and the latest completed reply. No camera wait on tongue.
- Eye/head/pupil features still share MediaPipe and every fast capture emits its
  own sample. Tongue results retain source session/sequence/capture time through
  additive `tongue_sample_v1`; Processing deduplicates history and expires only
  that pointer channel on its own clock. Transfer functions/driver format unchanged.
- Reset/load/loss/restart discard old jobs. Calibration counts unique inference
  results inside the original capture window with bounded delivery grace; a hung
  model cannot keep a pose pending forever. Masks overlay their original crop,
  never the newer full-camera image. Shared scopes use dark holds between results.
- Runtime displays fast Hz, tongue Hz, result age and pending replacements. Worker
  timeouts/crashes remain tongue-only errors, recoverable by source restart.
  Stop drops queued evidence; close reaps the process with bounded waits.
- Verification: 284 tests pass: 122 Vision (including real local MediaPipe, direct
  tongue and spawned tongue inference), 87 integration (native Tk enabled),
  75 Processing. New tests cover blocked/crashed/timed-out workers, lifecycle,
  capture identity/freshness, calibration windows/rests and matching overlays.
  The 490-frame mouse demo accepted all captures, observed all four actions and
  ended disabled with buttons released. Ruff F, whitespace and scope checks pass.
- Generated-input scheduling benchmark (3 seconds/run, target30 Hz): baseline
  29.99 Hz; artificial500 ms tongue inference29.94 Hz; local ONNX29.96 Hz. Each
  produced90 fast samples. Tongue itself completed about2 Hz/6.74 Hz respectively.
  This measures scheduling, not live camera/MediaPipe FPS or recognition accuracy.
- Runbook/architecture/benchmark commands: `docs/INDEPENDENT_DETECTOR_TESTING.md`.
  Profiles remain detectorv6/combinedv3. Shared CPU/memory/thermal contention can
  still influence rates; independent processes remove the blocking dependency.
  Live user testing and emulator integration remain separate next steps.

## Horizontal head detection — active

Reuvi integration, branch `work/reuvi/integration/horizontal-head`, base `43b3005`.
Scope: Vision features/calibration/presets/shared UI/trace, App calibration command
wiring, relevant Vision/integration tests, contracts, runbooks and agent notes.
Implement independent yaw calibration and normalized head_x beside working pitch.
Contract: `Contracts/HEAD_HORIZONTAL.md`, committed before implementation.
Keep fast per-capture sampling and independent tongue worker; no mouse mapping or
Drivers change. Acceptance: left/neutral/right normalized endpoints, saved-profile
compatibility, matching views, invalid input, independent fits and native tests.

### Horizontal head handoff

- Contract landed first as `2a74bb1`. Horizontal yaw reuses the existing face
  transformation and image-quality checks; no new model, inference pass or wait.
  Head Y pitch and independent tongue scheduling remain intact.
- Added **3 Head X**, an automatic neutral/left/right training and fresh-check
  guide with preparation/rest countdowns and sound cues. Personal left/neutral/right
  map to 0/.5/1, including unequal ranges or reversed raw signs. Retrying/resetting
  yaw preserves pitch and other completed fits. Face loss retains completed fits.
- Raw camera and calibration graphs share yaw in degrees and the same capture
  trace. Horizontal raw/normalized indicators, learned references, Head X scope
  and CSV fields expose the result. Unknown plots dark-hold prior values while
  unavailable control measurements remain invalid.
- New detector presets are v7 (`independent-head-axes-v7`), adding nullable
  `head_x` while preserving vertical `head`. Versions 1–6 remain readable;
  loading validates everything before mutating state. Combined profiles remain
  v3. Existing mouse mapping/transfer functions and Drivers are unchanged.
- Runbook: `docs/HEAD_HORIZONTAL_TESTING.md`. Remaining: user webcam validation
  of comfortable range, cross-axis stability and partial-face visibility; a
  future explicit Processing/device mapping for Head X.
- Verification: 296 tests pass: 127 Vision (local MediaPipe, direct tongue and
  spawned tongue model smoke checks included), 94 integration (native Tk enabled),
  and 75 Processing. The 490-frame mouse demo accepted all captures, observed
  both clicks, scrolling and pointer movement, and finished disabled/released.
  Changed Python passes Ruff F; whitespace and integration scope checks pass.
  Synthetic fixtures verify software behavior, not human detection accuracy.

## Direct pupil direction — complete

Reuvi integration, branch `work/reuvi/integration/direct-pupils`, base `fe95527`.
User requests MediaPipe-only pupil directions without the failing range guide.
Scope: Vision measurement/normalization/native UI/profile, App command/lifecycle,
relevant tests, contracts, documentation. Contract: DIRECT_PUPILS.md, committed
before implementation. Keep other detectors and independent tongue scheduling.

### Direct pupil handoff

- Contract `d8f508c` landed first. Existing MediaPipe iris geometry now feeds fixed
  eye-width normalization on every usable capture, with no pupil guide, learned
  range, eye-fit gate or saved head-pose reference. Both open eyes must remain usable.
- Replaced the full-screen pupil wizard with live raw/normalized readings and
  horizontal/vertical sensitivity controls. Changing scales stops preview and
  preserves other detector fits. Unknown graph holds remain display-only.
- Detector presets v8 store direct sensitivities; old v1–v7 validate completely
  before loading. Legacy pupil fits are ignored; compatible other fits survive.
  Direct-pupil-only profiles can save without fitted eye/head/tongue detectors.
  Combined profiles remain v3; source selection and mouse transfer functions unchanged.
- Runbook: docs/DIRECT_PUPIL_TESTING.md. Head-pose compensation and measured human
  accuracy remain outside this change; check those limits with live camera input.
- Verification: 301 tests pass: 129 Vision (local model smoke checks included),
  97 integration (native Tk enabled), and 75 Processing. The 490-frame mouse demo
  accepted all frames, observed all four actions and finished disabled/released.
  Changed Python passes Ruff F; whitespace and integration scope checks pass.

## Lip-boundary tongue + Head X reliability — complete

Reuvi integration, branch `work/reuvi/integration/lip-boundary-head-reliability`, base
`06a9e80`. User requests color extension beyond tracked lips and better Head X reliability. Latest
clarification keeps Head X calibration; the proposed direct-yaw change is cancelled. Scope: Vision features/crop/backend/worker,
calibration UI/profile/lifecycle; App wiring; relevant tests, contracts and docs.
Contract: LIP_BOUNDARY_HEAD_RELIABILITY.md, committed before implementation. Preserve
working head Y, eye/wink behavior, direct pupils and independent tongue scheduling.

### Lip-boundary / Head X handoff

- Contracts landed first (`8d7848e`, corrected by `644b328` and `efdfcb5`). Final
  behavior keeps Head X calibration: a valid yaw outside learned endpoints saturates
  at 0/1; genuinely missing yaw stays invalid. Completed fits survive retry/cancel/
  failure/loss. A failed horizontal pose can retry independently. Live lab presence/
  tracking floors are .35, initial face detection .5; image-quality gates remain.
- Added `Vision/lip_boundary.py`: local LAB color extension outside MediaPipe's
  outer lips, with attachment/ambiguity/clipping/contrast checks and an outer-front
  boundary midpoint. No appearance clicks or tongue weights for the default camera
  backend. This is an experimental proxy, not anatomical tongue recognition.
- Reused the bounded independent tongue process with an explicit backend field.
  Fast eye/head/pupil captures never wait for tongue; delayed overlays retain their
  original crop/time/sequence. UI shows outer-lip outline, accepted exterior mask,
  front boundary and point. The existing personal tongue guide/fresh checks remain.
- ONNX stays an explicit local comparison, with its own incompatible range. v9
  presets restore explicit backend identity; validated v1–v8 neural files migrate
  to the built-in backend with their old tongue range removed. Compatible eye,
  wink, head and pupil settings survive. Combined profile v3/mouse mappings unchanged.
- Testing guide: `docs/LIP_BOUNDARY_HEAD_TESTING.md`; linked from App, Vision and
  root docs. Direct pupil instructions stay in `docs/DIRECT_PUPIL_TESTING.md`.
- Verification: 139 Vision cases (138-case full run plus new color-guide case),
  104 integration cases including native Tk (103 passed in the full run; corrected
  a Tcl-state comparison in the new test, then all five cases in that module passed),
  and 75 Processing cases. The 490-frame mouse demo accepted every frame, observed
  all four actions, and ended stopped/released. Changed Python passes Ruff F;
  whitespace and integration-lane scope checks pass.
- Remaining live validation: actual yaw loss/reacquisition under motion and blur,
  lip-outline accuracy/contrast, false tongue candidates while smiling/talking,
  comfortable repeatable tongue ranges, and measured concurrent camera/model rates.
  No camera was opened and no personal samples/profile data were committed.

## Fixed pupil matrix and downward response — complete

Reuvi integration, branch `work/reuvi/integration/pupil-matrix-down`, base
`b5e0001`. Scope: Vision pupil measurement/UI/profile/frame/trace, App command
wiring, component/integration tests and contracts/docs. Remove pupil sensitivity
configuration, improve downward usability, add an 11×11 pupil matrix without
changing continuous Processing inputs. Preserve other detectors and scheduling.
Contract: PUPIL_MATRIX.md, landed before implementation.

### Fixed pupil matrix handoff

- Contracts `3b611ff` and `91a4d46` landed first. Removed pupil sensitivity UI,
  runtime command and mutable settings. No pupil fitting or hidden auto-calibration.
  v10 metadata identifies `mediapipe_iris_direction_v3`; old valid fits/settings
  are discarded. Compatible eye/wink/head/tongue state survives, including explicit
  v9 tongue backend choice. Combined profiles remain v3.
- Kept raw iris geometry and default left/right/up scales; downward full scale is
  +.065 eye widths instead of +.1. Narrow eyes can pass only with geometric iris
  down displacement, valid down/up blendshape support, blink<.4 and remaining
  image/iris/two-eye checks. No change to wink/click classification or inference.
- Every workbench capture carries `pupil_matrix_v1`: fixed 11×11 one-hot array,
  validity/confidence, row/column and original subject/session/sequence/time.
  Unknown values are null, including stop/load/stale/loss; actual continuous
  gaze_x/y remain the mouse processor's input. No transfer-function/driver change.
- Native pupil tab displays a square grid/precise dot without setup controls.
  Dark holds are display-only with readable unknown text. Raw and normalized
  position panels are square too. Source tab and CSV report matching matrix indices;
  per-eye diagnostics expose lid gap/blink/down-look support for live debugging.
- Verification: all 321 tests pass — 140 Vision (local model smoke checks included),
  106 integration (native Tk enabled), and 75 Processing. All 121 matrix cells,
  migration, capture provenance and downstream continuous values covered. The
  490-frame demo accepted every frame, observed all four mouse actions and ended
  disabled/released. Changed Python passes Ruff F; whitespace/scope checks pass.
- Runbook: docs/DIRECT_PUPIL_TESTING.md. Remaining: user live check of downward
  usable range versus tracking loss and blink rejection. Fixed scale/gates are
  experimental engineering defaults; generated fixtures do not measure human accuracy.
  No camera or personal recordings/profile data used for verification.

## Tongue retirement — complete

Reuvi integration, branch `work/reuvi/integration/remove-tongue`, base `d36cb18`.
User authorizes removing tongue from the MVP. Writable paths: App, Vision,
shared contracts/docs and integration tests; narrowly scoped Processing UI wiring
if needed to prevent the embedded App selecting a retired input. Drivers untouched.
Contract: `Contracts/TONGUE_RETIREMENT.md`. Preserve eyes/winks and head axes;
use fixed pupils for pointer. Validate legacy files then discard tongue state.


Handoff:
- Contract landed first as `af37f20`. App/Vision runtime now samples only eyes,
  head axes and pupils; removed tongue methods/crops/worker setup, UI, graphs,
  settings, CSV fields and obsolete tongue setup/worker-benchmark entry points.
- App fixes pointer source to gaze, including imported settings and old profiles.
  Processing's standalone library/legacy replay support is retained. Continuous
  pupil coordinates drive its pointer; the 11×11 matrix stays diagnostic.
- New detector v11 omits tongue data. Read-only v1–v10 validation keeps compatible
  eye/wink/head fits, discards tongue and old pupil fits/settings, and never starts
  a retired model. Required SignalFrame v1 tongue slots remain null/invalid.
- Verified: 139 Vision tests (137 passed, 2 optional retired tongue model smoke
  tests skipped; real local MediaPipe smoke passed); 83 existing integration tests
  passed with native Tk; 7 new removal/migration/native UI tests passed separately;
  75 Processing tests passed. Total: 302 passed, 2 optional skips.
- 490-frame headless demo accepted all 490 at ~30 Hz, observed left/right clicks,
  pupil pointer and head scroll, ended disabled with released buttons and neutral
  velocity. Ruff F, whitespace and integration scope checks passed.
- Obsolete active-tongue integration cases were removed; remaining eye/head/pupil
  regressions were adapted to the new pointer and preset contract. Isolated legacy
  algorithm tests remain. No live camera or human accuracy claim; Drivers pending.
- User runbook: `App/README.md`. Restart the app; Detection calibration now has
  1 Eyes, 2 Head Y, 3 Head X, 4 Pupils, Settings. No pupil setup is required.

## 2026-10-10 — pupil calibration with head-angle compensation

- Owner: Reuvi integration conversation; branch `work/reuvi/integration/pupil-head-calibration`.
- Base: `63fb5d3590d040bb82be7b9962c225c26405adbd`.
- Scope: coordinated Vision/App calibration, persistence, diagnostics, contracts,
  tests and documentation. Preserve independent eyes/head and tongue retirement.
- Contract: `Contracts/PUPIL_HEAD_CALIBRATION.md`; supersedes fixed pupil mapping.
- Implementation: 14-step native guide learns center drift across yaw/pitch,
  then four comfortable pupil endpoints, then independent validation captures.
  Per-frame compensation is constant-size arithmetic. Raw/compensated/normalized
  traces, learned references and the continuous dot/11×11 matrix share one source.
- Independent pupil restart, failed-step retry, reset, loss/restart retention and
  v12 preset round trips preserve eye/wink/head fits. v1–v11 migrate with pupils
  uncalibrated; no tongue restoration. Invalid/out-of-supported-pose output stays
  null, with dark previous-value plots only. App calibration always disarms output.
- Runbook/technical detail: `docs/PUPIL_HEAD_CALIBRATION_GUIDE.md`; entry point is
  Detection calibration → 4 Pupils → Start / restart pupil guide.
- Remaining: live camera evaluation of head compensation and downward range.
  This is a personal directional model, not screen gaze or measured human accuracy;
  large roll, head translation/distance changes and nonlinear pose effects are
  outside the fit. Drivers remain unchanged.
- Verification: 146 Vision tests (144 passed, 2 optional legacy tongue-model
  skips; local MediaPipe smoke passed), 95 integration tests with native Tk,
  and 75 Processing tests. Total 314 passed, 2 optional skips. New tests cover
  asymmetric pupil endpoints, cross-axis compensation, fresh held-out head poses,
  profile validation/migration, timing, retry/reset and the full-screen lifecycle.
- Headless mouse demo: all 490 frames accepted at ~30 Hz; all four actions observed;
  final output disabled, buttons released, velocities neutral. Changed Python
  passes Ruff F; whitespace and integration scope checks pass. No camera opened.

## Head Y individual step retries — complete

- Owner: Reuvi integration conversation; branch `work/reuvi/integration/head-y-step-retry`.
- Base: `54558656fd323e5e0121e4c4e379edde3820062d`.
- Scope: Vision guide/workbench/native UI, App command allowlist, tests and docs.
- Contract: Head Y step correction in `Contracts/MOVEMENT_CALIBRATION.md`.
- Goal: redo one reference or check while keeping other poses and the last working
  fit; fresh validation after changing a reference. Preserve all other channels.

Handoff:
- Contract landed first as `976e709`. Head Y has Retry current step plus explicit
  neutral/up/down capture/check selection, including from loaded profiles.
- `HeadPitchGuide` retains other captures/saved scalar references, clears dependent
  checks after reference edits, and prevents bypassing failed required checks.
  Saved values never count as captured samples. A failed attempt/full restart/cancel
  retains the last completed pitch fit. Other detector channels remain untouched.
- Native controls use existing rest/countdown/sound and generation-aware prompt
  acknowledgments. App routes edits through its disarming calibration commands.
  Preset v12, signal formats, raw pitch and normalization behavior are unchanged.
- Verification: 154 Vision tests (152 passed, 2 optional legacy model skips; local
  MediaPipe smoke passed), 100 integration tests including native Tk. Total 252
  passed, 2 optional skips. All 490 mouse-demo frames accepted at ~30 Hz, all four
  actions observed, final output disabled/released/neutral. Ruff F, whitespace and
  integration scope checks passed. No live camera opened; no accuracy claims.
- User instructions: `docs/HEAD_Y_RETRY_GUIDE.md`. Restart App, select Detection
  calibration → 2 Head Y. Cancel/loss still discards unfinished captures, retaining
  completed fits; a first-ever incomplete guide has no saved references to reuse.

## Gaming signal processing — implementation handoff

- Task/lane: user-authorized middle phase, integration. Branch
  `work/reuvi/integration/gaming-signal-processing`, worktree
  `.worktrees/reuvi-integration-gaming-signal-processing`, base `7175a89`.
- Contract first: `ba1f76b`; full handoff and runtime commit lookup:
  [Processing/mappings/HANDOFF.md](../Processing/mappings/HANDOFF.md).
- App now defaults to **gaming keyboard mouse mapping 1**. Existing calibrated
  raw input feeds independent head filters (down/up/left/right → W/Space/Shift/S),
  instantaneous eye intent → mouse states, precise pupils → pointer velocity.
  Mouse/scroll remains separately selectable. Vision and Drivers code unchanged.
- Signal mapping shows raw/filtered/threshold/instruction rows, head scopes,
  bounded action transitions, settings, named copies and local mapping files.
  Stop/loss/staleness/settings/source/profile changes release and require re-arm.
- Interfaces: additive `device_control_v1` and `input_mapping_v1`; original
  SignalFrame v1, face profile v3, detector v12 and mouse_preview_v0 preserved.
- Checks: 98 Processing + 105 integration tests passed, including native Tk;
  both 490-frame gaming/mouse demos accepted every frame, showed all their mapped
  actions and ended disabled/released. Native layout inspected. Benchmarks and
  exact commands are in the handoff. No camera or real OS input opened.
- Remaining dependency: latest driverTest still `2e3e734`; held mouse support,
  ordered action delivery and source-age/lifecycle adapter are required before
  native output. Current output is explicitly a preview. Human tuning untested.
- Run in this checkout: `python3 -m App --source demo`, then Signal mapping and
  Start preview. Read [the runbook](../Processing/mappings/README.md). No main
  merge/push or changes to other active checkouts were performed.

## Driver connection and main merge — user-authorized follow-up

- Reuvi explicitly requested connecting the existing driver and merging driverTest
  into main. Latest `origin/driverTest` at `2e3e734` merged cleanly into the existing
  integration branch after Processing `804f462`; base main was `7175a89`.
- Shared connection contract first: `8b1679c`. Implementation and full verification
  handoff: [Drivers/APP_CONNECTION_HANDOFF.md](../Drivers/APP_CONNECTION_HANDOFF.md).
- App now connects via a synchronous Processing sink, public ctypes ABI v3 binding
  and metadata-validating adapter. Existing driver click behavior is one click per
  eye activation; head keys are held. Pupil motion uses processed velocity. The
  provisional dragging/held-mouse proposal is not part of this connection.
- Additive `fid_abi_version`/`fid_submit_processed` preserve ABI struct layouts and
  standalone tools, prevent short action loss, and retain the C watchdog. Stop,
  calibration, loss, settings/mapping/source/profile changes and close release output.
- UI/CLI expose Preview, Driver dry run and explicit Camera-only Live output.
  No background service. [Setup and use](DRIVER_CONNECTION_GUIDE.md).
- Verified: native macOS build, 5/5 CTest suites (including 8 adapter tests), 98
  Processing tests and 113 integration tests including Tk; both complete 490-frame
  demos ran through the compiled driver, emitted all expected actions and ended
  released. No camera or OS injection was used; human/game behavior remains untested.
- Landing includes the completed Processing mapping and the teammate's driver
  history. Other active worktrees and detector code are preserved.

## Camera/profile recovery and combined Signals — complete

Task / lane / branch: Reuvi integration, `work/reuvi/integration/simple-signals-camera`.
Worktree: `.worktrees/reuvi-integration-simple-signals-camera`, based on `c7bd26d`.
Final commit: find `Fix camera profile startup and combine App signal views` in history.

Changed paths: App lifecycle, native UI, asset paths and instructions; shared
Processing desktop shell and mapping view; Vision's read-only v10 validator;
integration tests, MOUSE_MVP contract and current runbooks. Drivers unchanged.

Before → after:
- Selecting Camera previously left the synthetic worker running until manually
  stopped; the UI now releases/stops it and waits asynchronously before switching.
  Stop cancels a pending switch. Camera ID/FPS/model controls are in Camera settings.
- Profile loading previously rejected a valid camera file when the demo source was
  selected. The UI validates the full file before selecting its matching source.
  A running source switch resumes capture; paused loading stays paused, needs no
  face, and preserves fits on subsequent same-source startup. Output stays disarmed.
- Historical v10 iris v2 profiles failed against the newer v3 constant. Both known
  historical identities now validate before old pupil state is discarded. Eye/head
  fits survive; unknown identities still fail without changing calibration.
- Signals combines camera, source/profile/output controls, input/filtered/command
  rows and raw/processed graphs. Calibration is the only other main tab. Mapping
  tuning opens a dialog with independent head gates/bindings and pupil response.
  The standalone Processing developer tabs remain available. Startup errors remain
  visible, and local asset paths resolve from the checkout rather than launch cwd.

Run: `Vision/.venv/bin/python -m App --source camera`; load a profile on Signals,
then choose output and explicitly Start. Older profiles may need the pupil guide.

Checks actually run with the existing Vision venv and main's compiled library:
- `RUN_TK_TESTS=1 FID_LIBRARY=<main>/Drivers/build/libface_input_driver.dylib <venv-python> -m unittest discover -s tests/integration -v`: **125 passed**.
- `<venv-python> -m unittest discover -s tests/processing`: **98 passed**.
- `<venv-python> -m unittest discover -s tests/vision`: **154 run, 151 passed, 3 optional skips**.
- `<venv-python> -m App --source demo --headless --frames 490 --output dry-run --driver-library <main>/Drivers/build/libface_input_driver.dylib`: **490/490 accepted**, both clicks and W/S/Space/Shift observed, driver ended disabled with held-key mask 0. 3 left/3 right clicks, 4 key downs/4 ups; no OS events.
- Native Tk checks cover pending-switch cancellation, paused/running profile load,
  malformed-file preservation, missing-model errors, visible errors/all eight rows
  at 1280×850, dialog application and Stop on settings changes. Synthetic native
  preview inspected visually; standalone developer window constructed/refreshed.
- All four existing local user files loaded read-only with output stopped; none
  were changed or committed. Initial hardware diagnosis opened the actual camera
  for five frames without errors (~11.4 Hz), with no recording or OS output.
- Ruff F, compile checks, `git diff --check`, and integration scope check passed.

Contract impact: additive idle source selection/lifecycle, unchanged profile and
command formats, signal values/units/validity and detector/Processing algorithms.
Remaining: operator comfort and live OS/game behavior; automated output checks
use the actual driver's dry-run mode. No teammate checkout or personal data changed.

## Live pointer diagnosis and startup correction

Lane / task / branch: Reuvi integration / live-control-diagnostics /
`codex/integration/live-control-diagnostics`. Base `8199a50`.
Writable paths: App diagnostics/UI/launch, Processing arming/diagnostic snapshots,
integration tests and relevant shared docs. Drivers and Vision algorithms unchanged.

Confirmed a reproducible handoff failure: Start off-center, then center within the
interpolation interval. Processing enabled from the newest neutral sample but
computed movement from older deflected samples; the driver rejected the first
non-neutral command. Reset axis interpolation/motion to the latest real neutral
sample at enable. Also wait for active eye actions to release before enabling.
Retain strict driver validation and explicit Start after loss/errors.

Signals now preserves stop reasons and distinguishes invalid pupils, confidence,
staleness, head/pupil neutral waits and actual dead-zone suppression. App logs
bounded local scalar observations/errors at 5 Hz plus observed state changes,
outside capture/Processing threads. No images, landmarks or saved models are
written; files remain ignored and owner-only. No control/profile/driver ABI changes;
Processing diagnostic snapshots add pointer radius/active and head neutral fields.

User explicitly authorized live driver inputs. Native adapter test measured cursor
+127/-114 pixels without errors; corrected Processing → native driver test measured
+68 pixels, neutral enable, no keys/clicks, and paused output on completion. These
prove OS cursor movement in the tested Python launch context. Default filter sweep:
X=.55/.59 stops; X=.60 ≈7 px/s, .65 ≈51 px/s, .75 ≈212 px/s after settling, Y=.5,
speed 900. Thresholds and saved profiles were not changed. A separate brief camera
sample produced no valid pupil inputs; detector visibility/support gates blocked
those observations. This does not establish gesture accuracy or the exact cause
of every prior user-reported error. Personal scalar evidence stays outside Git.

Validation on the final implementation:
- `RUN_TK_TESTS=1 FID_LIBRARY=<main>/Drivers/build/libface_input_driver.dylib <Vision-venv-python> -m unittest discover -s tests/integration`: **133 passed**.
- `<Vision-venv-python> -m unittest discover -s tests/processing`: **98 passed**.
- 490-frame App dry-run: **490 accepted**, both clicks, pointer and W/S/Space/Shift;
  865 movement events, 3 clicks per side, 4 key downs/ups; final disabled, held keys 0.
- Native bounded movement evidence above; no automated test injects OS events.
- Synthetic Processing benchmark: 10,000 ticks, mean 46.29 μs, p95 66.29 μs;
  excludes camera/UI/driver time. Current host/runtime measurements only.
- Ruff F checks, module compilation, whitespace and integration scope check passed.
- Log rotation, owner-only files, omitted images/profile contents and nonfatal disk
  errors checked. Headless log contained 82 sample rows, no errors and session end.

Remaining dependency: the user's next live camera trial with the visible per-eye
pupil rejection reason. No claim that synthetic driver success validates real
pupil/wink recognition, all launchers' permissions, or game behavior.

## Raw pupils without calibration — user-requested integration

Lane / task / branch: Reuvi integration / raw-pupil-default /
`codex/integration/raw-pupil-default`, based on `8691e7a`.
Writable paths: Vision pupil/workbench/preset/UI wiring, App profile messaging and
command boundary, integration tests and relevant shared/component documentation.
Contract-first commit: `6d1ccf7`, [RAW_PUPIL_CONTROL.md](../Contracts/RAW_PUPIL_CONTROL.md).

Gaming now uses current raw eye-relative iris X/Y through the existing fixed
normalization, without a pupil fit, head-pose estimate, trained pose range or
pupil guide. The live pupil view contains readings, plots and the matrix, with
no calibration controls. Both-eye visibility and iris quality checks still apply;
Processing gain, dead zone, adaptive smoothing and invalid/stale-input stops are
unchanged. Eye clicks, head keys and head-only Mouse test remain independent.

Detector presets are v13 (`raw-pupil-control-v13`). Old v1–v12 files fully validate
before migration; compatible eye/head fits survive and validated v12 pupil fits
remain inactive archival data. Combined profiles stay v3 and mappings v2. Current
gaze identity is `mediapipe_iris_direction_v3`; compensated trace columns stay null.
No driver ABI or Processing algorithm changes, dependencies or runtime downloads.

Verification on the final code:
- Vision venv, `VISION_MODEL_PATH=<main>/Vision/.local/face_landmarker.task`,
  `-m unittest discover -s tests/vision -q`: **158 run, 156 passed, 2 optional skips**.
- `python3 -m unittest discover -s tests/processing -q`: **109 passed**.
- `RUN_TK_TESTS=1 FID_LIBRARY=<main>/Drivers/build/libface_input_driver.dylib`
  with the Vision venv, `-m unittest discover -s tests/integration -p <module> -q`
  for every `test_*.py` in a fresh process: **139 passed**, no skips or cleanup
  warnings. A preceding all-in-one run aborted in Tk garbage collection on a
  background thread (`Tcl_AsyncDelete`); module isolation avoided accumulated
  destroyed windows. No application behavior was changed to mask that test issue.
- New checks cover no-fit/no-pose pupil → Processing → compiled dry-run driver,
  diagonal motion, closure release, missing/stale capture disarm, inert archived
  fits including out-of-range head angles, atomic migration and guide-free UI.
- 490-frame App gaming dry run: **490 accepted**, 850 movement events, 3 clicks
  per side, 4 key downs/ups, no errors, final disabled and held-key mask 0.
- All four existing local profiles loaded read-only while paused and disarmed;
  v5, v10 and v12 migrated in memory to v13. No personal files were rewritten.
- Ruff F, module compilation, `git diff --check` and integration scope check passed.

Remaining: restart App for the next human camera trial. Raw direction is a
joystick input; resting gaze/head movement may bias its center. Software checks
do not establish human tracking accuracy. No camera or native OS input was used
for this follow-up, and other active checkouts were preserved.

## Screen destination pointer — user-requested integration

Lane / task / branch: Reuvi integration / gaze-target-control /
`codex/integration/gaze-target-control`, based on `6180643`.
Changed paths: Processing mapping/filter/preview/UI, Drivers adapter and zero-speed
target guard, App diagnostics, Vision pupil help text, component/integration tests,
contracts and runbooks. Contract-first commit: `1cd7f9f`.

The user wants the cursor to settle at the eye-directed location. Gaming now uses
the existing driver's target mode: bounded normalized primary-display coordinates
plus travel speed. The previous no-pupil-calibration choice is retained, so raw
pupils produce an explicitly approximate destination, not calibrated screen gaze.
See [setup and accuracy limits](SCREEN_POINTER_GUIDE.md). Mouse test stays head-only
velocity; legacy mouse/scroll and imported v1/v2 mappings retain velocity.

Processing smooths positions, holds a small fixation dead band around the last
accepted destination and never integrates a stationary pupil observation as speed.
Target startup allows any fresh pupil position after explicit Start, while known
eye actions/head keys must release. Unknown pupils emit speed 0 immediately; face
loss/staleness/Stop/settings changes disarm and release. Added a C guard so a
zero-speed target cannot cause even a sub-pixel correction. Diagnostic state/logs
now distinguish target mode, destination, actual driver position and arrival.

Interfaces: `device_control_v1` gains explicit `{mode:"target",x,y,speed}`;
velocity fields are unchanged. ABI v3 layouts are unchanged. Mapping v3 stores
pointer mode and `target_jitter`; face profiles v3 and detector presets v13 are
unchanged. Loading a face profile preserves the chosen mapping mode/dead band.
Targets use the driver's existing primary display; native support is macOS/Linux
X11 with its display dependencies, not pure Wayland. No model/dependency downloads.

Checks on the final code:
- `python3 -m unittest discover -s tests/processing -q`: **116 passed**.
- `RUN_TK_TESTS=1 FID_LIBRARY=Drivers/build/libface_input_driver.dylib` with the
  existing Vision venv, `-m unittest discover -s tests/integration -p <module> -q`
  for each module in a fresh process: **143 passed**, no skips or Tk warnings.
- `cmake -S Drivers -B Drivers/build`, `cmake --build Drivers/build -j 4`,
  `ctest --test-dir Drivers/build --output-on-failure`: **5/5 suites passed**,
  including **11 Python adapter tests** against the actual compiled library.
- A full synthetic pupil → Processing → compiled driver check reaches (.8,.25),
  stays there during ±.002 input jitter, emits no further movement after arrival,
  and holds position on closure. Direct driver tests also verify zero-speed holds,
  mode-change validation and independent watchdog/key release. No OS events.
- 490-frame gaming App dry run: **490 accepted**, no errors, 931 movement events,
  3 clicks per side, 4 key downs/ups; final disabled, held keys 0, target speed 0.
- All four existing local profiles loaded read-only, paused/disarmed, retaining
  screen-destination mode and fixation dead band. No personal files changed.
- Ruff F, Python compilation, whitespace and integration scope checks passed.

Remaining: restart App after updating the compiled driver and evaluate with the
user's camera. Real-person gaze accuracy and live target movement were not measured
in this task. A screen-dot fit would be separate work for actual screen alignment;
this release changes destination control while keeping raw pupil detection.

## Downward pointer reach and lighter filtering — user-requested integration

Lane / task / branch: Reuvi integration / pupil-reach-response /
`codex/integration/pupil-reach-response`, based on `cf75ab2`.
Changed paths: Processing mapping/filter/settings UI, App profile application and
diagnostics, component/integration tests, current agent notes and runbooks.
Contract-first commits: `11363ba` and `bcbe20e`; the second reflects the user's
follow-up that Mouse test also needs improved downward control. Drivers/Vision
source and personal calibration files are unchanged.

Gaming defaults now use 2× pointer gain, a further 4× downward boost, 20 ms position
smoothing, zero interpolation delay and .002 fixation dead band. Position axes
saturate independently and settle exactly at edges, avoiding a fixation hold just
short of a corner. Mouse test has separate 3× downward boost, 20 ms smoothing,
zero delay, .10 dead zone / .02 activation margin, exponent 1.2, acceleration 10/s
and deceleration 14/s. Downward scaling precedes inversion; raw values and independent
head-key/eye actions stay intact. Missing input still immediately stops movement.

Mapping format is now v4; strict v1–v3 migration preserves previous gains, mode,
smoothing/delay and dead band. Target smoothing/delay are mapping settings, so a
face-profile load cannot restore old filtering. Mouse test similarly retains its
pointer response. Mapping settings exposes the boost and mode-specific filters;
logs record the effective smoothing, delay, downward gain and fixation band.
Incoming profile freshness is validated against target delay before detector fits
are replaced. No C ABI or SignalFrame changes; face/detector versions remain v3/v13.

Verification:
- `python3 -m unittest discover -s tests/processing -q`: **120 passed**.
- `RUN_TK_TESTS=1 FID_LIBRARY=<main Drivers/build/libface_input_driver.dylib>` with
  the Vision venv, each integration test module in a fresh process: **147 passed**
  across the full run and focused reruns of the three subsequently updated modules.
  No skips. Includes native Tk controls, version migration, gain/inversion,
  unknown/stale stops, independent actions, profile persistence and atomic failure.
- Synthetic raw iris → Processing → compiled dry-run target backend reaches all
  four exact corners and emits no further moves on fixed input. Small downward
  head input (.53) now emits positive-Y movement events through the compiled
  velocity driver, with no X movement/clicks/keys/scroll. Dry-run velocity does not
  update its simulated absolute position, so that test checks emitted deltas.
- Four existing local face profiles loaded read-only in both mappings (**8 loads**),
  keeping 20 ms smoothing and their independent downward gains; all stayed paused,
  opened no camera and retained identical file hashes.
- `Vision/.venv/bin/python -m App --source demo --headless --frames 490 --output
  dry-run --driver-library <main library>`: **490 accepted**, no errors, 987 mouse
  moves, 3 clicks per side, 4 key downs/ups; final disabled, held keys 0, target speed 0.
- `python3 -m Processing.mouse.benchmark`: 10,000 ticks, mean **47.69 µs**, p95
  **67.75 µs**; synthetic CPU measurement only.
- Ruff F checks, `git diff --check` and integration scope check against `cf75ab2`
  passed. Driver binary did not require rebuilding.

Handoff: restart App to use the new built-in defaults. Mapping settings can tune
the gains/filters further; export custom mappings to persist them across restarts.
Old imported mappings intentionally keep their tuning. No human-camera accuracy
or native OS cursor injection was measured in this follow-up. Stronger gain also
amplifies noise; these are adjustable starting values based on the user's report
and the compressed downward range in existing scalar logs, not a gaze calibration.

## Head-speed acceleration and return braking — user-requested integration

Lane / task / branch: Reuvi integration / head-motion-response /
`codex/integration/head-motion-response`, based on `65013f0`.
Changed paths: Processing head pointer filter, mapping persistence/settings,
App scalar diagnostics, component/integration tests, current agent notes,
contracts and runbooks. Contract-first commit: `a51fb1c`.

The user reports that head X/Y control feels smooth and substantially better than
pupils, and asked for speed-aware acceleration/deceleration. Mouse test now enables
an optional head movement response: fast outward motion adds up to 75% speed/ramp
boost, and fast returns reduce requested speed by up to 65% while increasing the
deceleration limit. Existing adaptive smoothing, steady deflection response,
dead zone, 3× downward gain and detector calibration remain intact. The off switch
uses exactly the previous AxisFilter. Other mapping families are unaffected.

The estimator uses original capture times, an 80 ms window and latest-capture
direction/speed evidence in unamplified personal head coordinates. Tiny jitter,
stationary evidence, return and reversal cannot sustain an outward boost. A stalled
capture stream fades the transient response after 80 ms and clears it at 150 ms;
normal freshness/unknown/Stop handling still releases immediately as appropriate.
Mapping files v5 add validated head_motion settings; v1–v4 migrate with the feature
off. Copies, exports and face-profile loading retain the toggle/strengths. No Vision
or Drivers code, ABI, SignalFrame, detector-preset or face-profile version changes.

Checks:
- `python3 -m unittest discover -s tests/processing -q`: **129 passed**, including
  nine head-response cases covering slow/fast turns, steady hold, return/reversal,
  X/Y/diagonals/inversion/downward gain, jitter, different camera/output rates,
  duplicate timestamps, stalled captures, loss/rearm and exact disabled parity.
- `RUN_TK_TESTS=1 FID_LIBRARY=<main compiled library>` with Vision's venv, each
  `tests/integration/test_*.py` module in a separate process: **148 passed**, no
  skips. Includes settings visibility/toggle, mapping persistence, profile loading,
  diagnostics and actual compiled-driver delta output during outward/return motion.
  The driver emits no extra moves after settling, and no reverse drift/clicks/keys.
- Full App demo, Mouse test, 490 frames with the compiled dry-run library:
  **490 accepted**, no errors, **662 movement events**, no clicks/keys/scroll;
  final disabled, neutral velocity and held keys 0.
  Command: `Vision/.venv/bin/python -m App --source demo --mapping mouse-test
  --headless --frames 490 --output dry-run --driver-library <main library>`.
- 10,000-tick synthetic HeadMouseProcessor benchmark (33.3 Hz input / 100 Hz output):
  response off mean **58.32 µs**, p95 **79.67 µs**; on mean **81.64 µs**, p95
  **107.29 µs**. Excludes detector/GUI/driver latency and is not a timing guarantee.
- Ruff F, whitespace and integration scope checks against `65013f0` passed.

Handoff: restart App, select Mouse test, load the usual face profile, center and
Start live control. Mapping settings → Head movement response exposes the toggle,
Movement boost and Return braking. Export custom mapping settings for persistence.
See [head pointer tuning](HEAD_POINTER_GUIDE.md). Synthetic checks establish the
software path; no real-camera comfort study or native OS injection was performed.
