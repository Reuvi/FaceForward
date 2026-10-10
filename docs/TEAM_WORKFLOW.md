# Working together without overwriting one another

## Three lanes, one integration owner

Use Vision, Processing, and Drivers as the three parallel work streams, with
roughly one person responsible for each section and their agents working within it.
Select one person to coordinate shared interfaces and merges. That responsibility can rotate.
Reuvi has identified Processing as his section and the main integration
conversation as the coordination hub. Confirm the current Vision and Drivers
owners there; do not infer their assignments from names or GitHub handles.
Use [COORDINATION.md](COORDINATION.md) for the baseline, current decisions, task
claims, and handoffs. It is a guide, not a synchronized task registry.

| Lane | Owns | Develop independently using |
| --- | --- | --- |
| vision | `Vision/`, `tests/vision/` | Recorded/synthetic frames and emitted SignalFrame fixtures |
| processing | `Processing/`, `tests/processing/` | SignalFrame fixtures and the native mouse preview |
| drivers | `Drivers/`, `tests/drivers/` | Agreed control fixtures/manual sliders, no camera dependency |
| integration | Shared paths and app composition | All three public interfaces |

Keep lane-specific requirements, lockfiles, tooling, and README instructions inside
that lane until the integrator deliberately consolidates a shared environment.
The integrator owns root dependency files, CI, `Contracts/`, and application wiring.
The current mouse lab emits `mouse_preview_v0`; ControlFrame v1 remains a driver
draft. Read [the adopted handoff](../Contracts/MOUSE_MVP.md) before wiring output.
Put cross-lane questions in `<Component>/interface-requests/<task>.md` and reference
them in the handoff. Changing a shared contract is a separate coordinated task.

## Shared starting point

The collaboration setup is on `main`. Fetch the latest `origin/main` before
starting a new task, and read `docs/ORIGINAL_PROJECT_NOTES.md` for the original
brief. A local commit is not visible to other computers until it is published.

The initial local bootstrap worktrees still belong to their respective agents.
When ready, each owner should fetch and merge `origin/main` inside their own clean
worktree to pick up updated notes. Do not switch, reset, or update another agent's
active worktree. New agents should start from the latest `origin/main`.

## New agent / new task

On each teammate's machine, clone once into a private local folder. In a checkout
containing these tools:

```bash
git fetch origin
python3 tools/new_worktree.py vision aria capture --base origin/main
python3 tools/new_worktree.py processing reuvi thresholds --base origin/main
python3 tools/new_worktree.py drivers teammate mock-output --base origin/main
```

These are examples, not assigned roles. Replace developer and task slugs. The
resulting branch is `work/<developer>/<lane>/<task>` and the directory is
`.worktrees/<developer>-<lane>-<task>` beneath the primary checkout. Open only the
specific worktree in that agent's editor/session. Do not open the primary checkout
as a shared writable workspace for several agents.

The helper refuses dirty starting checkouts, unresolvable bases, reused
names, and branches outside its naming pattern. It creates a new branch from a
commit and never copies uncommitted files. Run it sequentially when several
worktrees are needed. Existing branches/worktrees are left intact.

If another agent is already editing that checkout, do not stage, stash, switch,
reset, clean, or commit its files. Create your own checkout from a clean base.
Use one private environment, build/cache output directory, and dev-server port per
worktree. Coordinate camera access: only one process should own a physical camera;
other agents use replay. Only one live driver process should control OS input.

## Claim and hand off work

Agree on a task in a shared issue/PR or the team's existing conversation before
coding. Record: task, human owner, lane, branch, exact writable paths, base commit,
acceptance check, dependencies, and status. A document edited in separate clones
does not provide a real-time lock. Worktree isolation also does not prevent two
people from changing the same conceptual interface.

Keep each task small. If two tasks need the same file, serialize them or split the
file ownership in advance; merely using two branches does not solve that collision.
Do not change another lane's implementation to make your own test pass. Mock the
agreed interface and report the mismatch with a fixture or a minimal reproducer.

Return the handoff to the main coordination chat. At handoff, include:

```text
Lane / task / branch:
Base commit:
Changed paths:
What works:
Checks run and exact results:
Contract changes or dependencies:
Remaining limitations:
Commit or PR:
```

## Check, review, integrate

From the feature worktree, after fetching the latest base:

```bash
python3 tools/check_scope.py --base origin/main --lane vision
git diff --check
git status --short
```

Substitute your lane and agreed base. Stage only your task's paths. Use a focused
PR and the repository template. The GitHub workflow checks component path ownership
using the source branch naming convention. Integration branches are explicitly
exempt from component restrictions and require human coordination/review. These
checks are advisory until the repository owner configures branch protection; a
branch name is not authentication or authorization.

The integration owner lands contract changes first, then one component PR at a
time. Keep `main` runnable. Check fixtures → processor → logging driver before
trying a camera or live OS output. Review unknown values, tracking loss, two faces,
button release, calibration, and stale-input behavior at each integration.

Update a feature branch only from inside its own clean worktree. Prefer merging
the agreed base into already shared branches. Rebase only unpublished work; never
force-push over a teammate's commits. Run the affected checks again after resolving
a conflict. Delete worktrees only after their owner confirms all work is retained.

## How instructions load

`AGENTS.md` is the common entry point. Folder-specific `AGENTS.md` files describe
lane boundaries; agents launched at the root are explicitly told to read the files
for components they edit. Other assistants should be told to read these same files.
This follows the [official Codex instructions guide](https://developers.openai.com/codex/guides/agents-md).
