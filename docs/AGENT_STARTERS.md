# Agent starter prompts

Create/open a separate worktree first. Replace the bracketed fields, then paste
one prompt into the agent working in that worktree. Multiple agents in a lane need
distinct task scopes, branches, and worktrees.

## Vision

```text
You own the vision lane for task [task]. Work only in [absolute worktree path] on
branch [branch], based on [base commit/ref]. Read AGENTS.md, Vision/AGENTS.md,
docs/TEAM_WORKFLOW.md, and Contracts/README.md before editing. Writable paths:
Vision/** and tests/vision/**. Preserve other changes. Implement [acceptance scope].
Start with synthetic/replay input and emit SignalFrame v1. Keep camera access,
detector calibration, signal confidence/validity, and overlay generation in Vision.
Do not implement mappings or OS drivers. Record shared-interface requests under
Vision/interface-requests/ rather than editing shared files. Run relevant checks,
the scope checker, and git diff --check. Hand off changed paths, test results,
limitations, dependencies, and commit/PR. Do not publish without authorization.
```

## Processing

```text
You own the processing lane for task [task]. Work only in [absolute worktree path]
on branch [branch], based on [base commit/ref]. Read AGENTS.md,
Processing/AGENTS.md, docs/TEAM_WORKFLOW.md, and Contracts/README.md before editing.
Writable paths: Processing/** and tests/processing/**. Implement [acceptance scope]
using SignalFrame fixtures and a logging ControlFrame sink. Own user/device profile
logic, signal transforms, thresholds/dwell, configurable mappings, and diagnostics
UI within Processing. Do not acquire the camera or send live OS events. Record
interface requests under Processing/interface-requests/. Check neutral, invalid,
stale, and two-face inputs and timing independent of frame rate. Run relevant
checks, the scope checker, and git diff --check. Hand off changed paths, test
results, limitations, dependencies, and commit/PR. Do not publish without authorization.
```

## Drivers

```text
You own the drivers lane for task [task]. Work only in [absolute worktree path] on
branch [branch], based on [base commit/ref]. Read AGENTS.md, Drivers/AGENTS.md,
docs/TEAM_WORKFLOW.md, and Contracts/README.md before editing. Writable paths:
Drivers/** and tests/drivers/**. Implement [acceptance scope]. Start with a logging
adapter and manual/fixture normalized values; no Vision dependency is needed.
Preserve the existing Drivers/readme.MD. Handle ControlFrame v1, duplicate/stale
frames, disable/stop, and release of held inputs. Keep platform-specific behavior
behind an adapter. Record interface requests under Drivers/interface-requests/.
Run relevant checks, the scope checker, and git diff --check. Hand off changed
paths, test results, target OS, limitations, dependencies, and commit/PR. Do not
publish without authorization.
```

## Integration (one active task at a time)

```text
You coordinate integration for [task] in [absolute worktree path] on [branch].
Read AGENTS.md, docs/TEAM_WORKFLOW.md, and Contracts/README.md. Coordinate shared
files and contracts before modifying them; preserve each lane's ownership. Own
App wiring, root dependencies, CI, shared docs/contracts, and integration tests.
Implement [acceptance scope]. Use mock adapters first. Merge/review one component
change at a time within the user's authorization. Read each lane's handoff and
verify fixture → processor → logging driver, tracking loss, timeouts, and release
behavior. Report changed files, commands/results, contract versions, and remaining
dependencies. Do not change component internals without a coordinated handoff.
```
