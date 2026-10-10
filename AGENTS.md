# Agent working agreement

Build a camera-based accessibility controller: **Vision → Processing → Drivers**.
Read `docs/ORIGINAL_PROJECT_NOTES.md`, `README.md`, `docs/TEAM_WORKFLOW.md`, and
`Contracts/README.md` before editing. The original notes capture the team's intent;
the implementation plan and technical contracts add provisional design choices.
Later explicit team decisions take precedence over the original brief.
Read the `AGENTS.md` in every component you will touch, even if your session starts
at the repository root. User instructions take precedence over this agreement.

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
  output and release held buttons. Do not silently reassign control to another face.
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
