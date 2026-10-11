# Face-controlled accessibility interface

Measured tuning: **Signals → Target game…** measures head-controlled travel speed,
small-target re-entry, precision and smoothness. Repeated baseline/adjustment rounds
select a local personal default; physical-mouse practice cannot tune. [Play and inspect results](docs/TARGET_GAME_GUIDE.md).

Latest recovery: **Mouse test → Center head & start** captures your current resting pose. In **Live curves**, uncheck **Require calibrated wink for clicks** for plain open/closed eye clicks (ordinary blinks also click). Save the choice and center in a tuning profile.

Current editor: **Signals → Live curves…** adjusts response curves and timing with connected sliders. Save/load named tuning profiles or restore the tuned defaults. [Live curve editor guide](docs/LIVE_CURVE_EDITOR_GUIDE.md).

Current update: Gaming uses raw pupils to choose an approximate **screen destination**; the cursor arrives and stops. **Mouse test** uses precise head X/Y velocity with faster large/quick turns and matching left/right calibrated wink clicks. See [head movement and clicks](docs/HEAD_POINTER_GUIDE.md), [screen pointer setup and limits](docs/SCREEN_POINTER_GUIDE.md) and [run instructions](App/README.md).

Current MVP: **eyes/winks, Head Y, Head X and pupils**. Tongue detection has been
removed from the live app, calibration and graphs. Pupils control the pointer with
personal directional calibration, head-angle compensation and an 11×11 matrix
display. Saved eye/head calibration remains reusable; detector presets now save v12. Start with the
[current testing and profile guide](App/README.md).

A hackathon prototype for controlling a computer through a consumer webcam and
comfortable facial movements. The pipeline separates measurement, personalized
signal processing, and device output so three teammates can develop independently.

**Repository status:** one native lab with detector calibration and Processing
in the same window. **gaming keyboard mouse mapping 1** maps independent eyes
to mouse buttons, head down/up/left/right to W/Space/Shift/S, and pupils to pointer
velocity. The Signals tab shows raw values, filters, thresholds and readable
commands, with named mapping copies and local import/export. Saved face profiles
keep detector fits and mouse response settings together. The merged driver now
connects through selectable Preview, Driver dry run and Live mouse + keyboard
output. [Build and run live output](docs/DRIVER_CONNECTION_GUIDE.md). Human accuracy
and live game behavior still need operator testing.

## Calibrate and test in one window

```bash
# Interactive fake face: calibrate, then open Signals.
Vision/.venv/bin/python -m App --source detector-demo

# Same workflow using the camera.
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

Follow [the unified workflow and saved-profile guide](App/README.md).
[Horizontal head testing](docs/HEAD_HORIZONTAL_TESTING.md) covers the new independent
Head X yaw guide, raw/normalized graphs and saved horizontal ranges.
The [pupil testing guide](docs/PUPIL_HEAD_CALIBRATION_GUIDE.md) explains personal
direction ranges, head compensation and the square matrix. Historical tongue guides
are superseded by the [retirement contract](Contracts/TONGUE_RETIREMENT.md).
The [detector runbook](Vision/DETECTION_LAB.md) specifies measurements and thresholds.
Optional camera dependencies/model setup are in [Vision setup](Vision/README.md).
The standalone component tools are for developers; App requires no second program.

## Run the combined native lab

From this repository root, with Python 3.10+ and Tk:

```bash
python3 -m App
```

The default is a labeled synthetic Vision gaming demo. Click **Start preview**,
then **Signals** to watch independent left/right mouse commands, pointer
motion and W/Space/Shift/S. Use `--mapping mouse` for the previous scroll mode.
The same **Signals** page shows the camera, input/filtered/command values and
graphs. **Calibration** holds the independent guides; **Mapping settings…** opens
thresholds, pointer tuning and bindings. Choosing Camera switches sources in one
action; loading a profile selects its matching source. There is no
browser, JavaScript or network service. Real OS input requires Camera plus the
explicit Live mouse + keyboard output choice and Start.

Read [the complete MVP runbook](App/README.md),
[Processing tuning instructions](Processing/README.md),
[Vision camera setup](Vision/README.md), and
[the gaming Processing runbook](Processing/mappings/README.md), and
[the adopted command handoff](Contracts/GAMING_MAPPING.md).

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

The native app learns **closed-eye actions in a short six-pose wink guide**.
Separate full-screen guides calibrate eye open/closed geometry and wink actions.
Retrying the second retains the first. Rest screens show a large countdown and
the upcoming instruction together. Recognized
winks produce ON samples while held, with no duration threshold. Detection research
has been removed from the app. See [the eye calibration/testing guide](docs/EYE_CALIBRATION_GUIDE.md).
All output remains a simulated preview.
