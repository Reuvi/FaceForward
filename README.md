# Face-controlled accessibility interface

A hackathon prototype for controlling a computer through a consumer webcam and
comfortable facial movements. The pipeline separates measurement, personalized
signal processing, and device output so three teammates can develop independently.

**Repository status:** collaboration scaffold and proposed v1 interfaces. The
camera detector, processor, desktop UI, and live drivers are not implemented yet.
The original `Drivers/readme.MD` is preserved.

## Start here

1. Read [the team workflow](docs/TEAM_WORKFLOW.md) and [agent instructions](AGENTS.md).
2. Pick a lane and create a separate worktree for every active agent:

   ```bash
   git fetch origin
   python3 tools/new_worktree.py vision your-name signal-reader --base origin/main
   ```

   The helper prints the exact directory to open. It requires Python 3.9+ and Git.
   During initial setup, use `--base chore/team-agent-setup` locally until the
   setup commit has been published and incorporated into the shared base.
3. Open that worktree and paste the matching [agent starter](docs/AGENT_STARTERS.md).
4. Implement against the [v1 contracts and fixtures](Contracts/README.md).

## Work areas

| Path | Purpose | Owner |
| --- | --- | --- |
| `Vision/` | Capture, face signals, detection calibration, landmark overlay | Vision lane |
| `Processing/` | Profiles, thresholds, smoothing, mappings, oscilloscope/settings UI | Processing lane |
| `Drivers/` | Mock output, mouse/keyboard, speech trigger, later gamepad adapter | Drivers lane |
| `App/` | Composition, lifecycle, active-subject selection, camera/driver startup | Integration owner |
| `Contracts/` | Versioned message semantics and synthetic examples | Integration owner |
| `tests/<lane>/` | Component-owned tests | Corresponding lane |
| `tests/integration/` | Full mock-pipeline checks | Integration owner |
| `tests/tooling/` | Isolation/scope helper checks | Integration owner |
| `docs/`, `tools/`, `.github/` | Shared plan, collaboration tools, review/CI | Integration owner |

The three lanes do not assign people automatically. Agree who owns each lane and
who is integrating before starting. The same person can cover integration in a
separate worktree. Each teammate clones the repository on their own computer;
worktrees isolate concurrent agents on one computer.

See [the project plan](docs/PROJECT_PLAN.md) for scope, milestones, and undecided
implementation choices. No application framework or detector model has been selected.

## Scaffold checks

```bash
python3 tools/new_worktree.py --help
python3 tools/check_scope.py --help
python3 -m unittest discover -s tests/tooling -v
git diff --check
```

Component owners add their own setup and test commands when implementation starts.
The scope CI check validates changed paths for lane branches; it is not an app test.
