# Face-controlled accessibility interface

A hackathon prototype for controlling a computer through a consumer webcam and
comfortable facial movements. The pipeline separates measurement, personalized
signal processing, and device output so three teammates can develop independently.

**Repository status:** one native mouse lab with live detector calibration and
Processing in the same window. Independent eyes, head Y and experimental tongue
measurements feed the existing scopes and simulated mouse. Saved local profiles
keep detector fits and mouse settings together. Live accuracy validation and the
real Drivers connection remain pending.

## Calibrate and test in one window

```bash
# Interactive fake face: calibrate, then open Live lab.
Vision/.venv/bin/python -m App --source detector-demo

# Same workflow using the camera.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

Follow [the unified workflow and saved-profile guide](App/README.md).
The [head/tongue calibration guide](docs/MOVEMENT_CALIBRATION_GUIDE.md) covers guided
position fitting, raw graphs on camera setup, shared readings and saved profiles.
The [tongue model plan](Vision/TONGUE_MODEL_PLAN.md) incorporates the supplied
segmentation research and distinguishes the current color baseline from future models.
The [detector runbook](Vision/DETECTION_LAB.md) specifies measurements and thresholds.
Optional camera dependencies/model setup are in [Vision setup](Vision/README.md).
The standalone component tools are for developers; App requires no second program.

## Run the combined native lab

From this repository root, with Python 3.10+ and Tk:

```bash
python3 -m App
```

The default is a labeled synthetic Vision demo. Click **Start preview**, then
**Live lab** to watch independent left/right clicks, pointer motion, scrolling,
and input/output scopes. **Vision source & raw signals** shows measurements,
validity, actual source timing, and optional camera diagnostics. There is no
browser, JavaScript, network service, or real OS mouse injection.

Read [the complete MVP runbook](App/README.md),
[Processing tuning instructions](Processing/README.md),
[Vision camera setup](Vision/README.md), and
[the adopted native handoff](Contracts/MOUSE_MVP.md).

## Read while testing and developing

The app now uses one person: calibration survives head motion, brief loss and same-source
restart. See [single-user testing and saved-profile instructions](docs/SINGLE_USER_TESTING.md).

- [Raw detection guide](docs/RAW_DETECTION_GUIDE.md): which facial detectors exist,
  how the ML and calibration work, what is missing, and camera-only diagnostics.
- [Testing companion](docs/TESTING_GUIDE.md): step-by-step exercises, expected
  readings, demo timeline, tuning experiments, CSV fields, and troubleshooting.
- [Engineering guide](docs/ENGINEERING_GUIDE.md): architecture, signal formats,
  eye state machines, transfer-function math, every setting, clocks, and limits.
- [Main chat coordination](docs/COORDINATION.md): settled decisions, ownership,
  agent task claims/handoffs, merge procedure, and the next incremental work.

## Start here

1. Read [the original project notes](docs/ORIGINAL_PROJECT_NOTES.md),
   [the coordination hub](docs/COORDINATION.md),
   [the team workflow](docs/TEAM_WORKFLOW.md), and [agent instructions](AGENTS.md).
2. Pick a lane and create a separate worktree for every active agent:

   ```bash
   git fetch origin
   python3 tools/new_worktree.py vision your-name signal-reader --base origin/main
   ```

   The helper prints the exact directory to open. It requires Python 3.9+ and Git.
   The collaboration setup is available on `main`; fetch before creating a worktree.
3. Open that worktree and paste the matching [agent starter](docs/AGENT_STARTERS.md).
4. Implement against the [v1 contracts and fixtures](Contracts/README.md) and
   [the mouse MVP integration](Contracts/MOUSE_MVP.md). Use `python3 -m App` for
   combined work and `python3 -m Processing.mouse` for independent mock tuning.

## Work areas

| Path | Purpose | Owner |
| --- | --- | --- |
| `Vision/` | Capture, face signals, detection calibration, landmark overlay | Vision lane |
| `Processing/` | Profiles, thresholds, smoothing, mappings, oscilloscope/settings UI | Processing lane |
| `Drivers/` | Mock output, mouse/keyboard, speech trigger, later gamepad adapter | Drivers lane |
| `App/` | Composition, lifecycle, active-subject selection, camera/driver startup | Integration owner |
| `LabUI/` | Shared display-only trace rendering helpers; never control input | Integration owner |
| `Contracts/` | Versioned message semantics and synthetic examples | Integration owner |
| `tests/<lane>/` | Component-owned tests | Corresponding lane |
| `tests/integration/` | Full mock-pipeline checks | Integration owner |
| `tests/tooling/` | Isolation/scope helper checks | Integration owner |
| `docs/`, `tools/`, `.github/` | Shared plan, collaboration tools, review/CI | Integration owner |

The team is split roughly one person per section. Agree who owns each lane and
who is integrating before starting. The same person can cover integration in a
separate worktree. Each teammate clones the repository on their own computer;
worktrees isolate concurrent agents on one computer.

See [the original project notes](docs/ORIGINAL_PROJECT_NOTES.md) for the team's
source brief and [the project plan](docs/PROJECT_PLAN.md) for organized milestones
and proposed implementation choices. The current lab uses native Python/Tk;
the optional local camera backend uses MediaPipe/OpenCV.

## Checks

```bash
python3 tools/new_worktree.py --help
python3 tools/check_scope.py --help
python3 -m unittest discover -s tests/tooling -v
python3 -m unittest discover -s tests/vision -v
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/integration -v
python3 -m App --headless --frames 490
git diff --check
```

CI runs component/integration tests without camera dependencies. The optional
model test is enabled with `VISION_MODEL_PATH`; see Vision's README. Scope CI
checks lane ownership separately. Driver files have not been changed by this MVP.

The native app now learns **blinks versus intentional winks inside eye calibration**.
A single full-screen guide trains and checks each eye independently. Recognized
winks produce ON samples while held, with no duration threshold. Detection research
has been removed from the app. See [the eye calibration/testing guide](docs/EYE_CALIBRATION_GUIDE.md).
All output remains a simulated preview.
