# Main chat and agent coordination hub

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

## Next increments: candidates, not active assignments

| Candidate task | Owning lane | Reviewable acceptance evidence |
| --- | --- | --- |
| Live independent eye calibration and quality | Vision, then App handoff | Explicit selected-face collection; independent valid binary eyes; invalidation on poor visibility/loss; no bystander inheritance |
| Head Y measurement | Vision | Calibrated continuous neutral/up/down values, orientation/quality evidence, invalid on loss; head-reference overlay alone does not count |
| Tongue measurement | Vision | Actual centroid detector supplying mouth-relative X/Y, occlusion/absence invalidation, recorded accuracy limits |
| Per-person transfer tuning | Processing | Comparable synthetic/then-live traces, saved settings, dwell and motion behavior, unchanged public signal meanings |
| Mouse emulator adapter agreement | Drivers with integration | Exact accepted message/example, units/signs, event transitions, timing and release-all/watchdog behavior |
| Connect first validated detector | Integration after Vision handoff | Raw → valid measurement → processed state visible in the lab, deterministic regression test plus explicit live observations |
| Connect emulator | Integration after driver agreement | Synthetic pipeline first; bounded real movement and stop/release checks only in explicit driver mode |

Serialize overlapping Vision work or claim different files first. A candidate is
not assigned until a human/agent claims it in the shared conversation. Keep a
short active task list in that conversation; this repository document should not
pretend to be a synchronized task database.
