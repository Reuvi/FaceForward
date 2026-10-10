# Mouse MVP testing companion

**Unified lab update (October 10, 2026):** detector calibration is now a tab in
`App`, using its single source. Calibrated eyes/head/tongue feed the existing lab.
Start with [App's workflow and profile guide](../App/README.md); see
[the detector runbook](../Vision/DETECTION_LAB.md) for measurements and limitations.

Keep this open while testing. It covers the native application at runtime baseline
`481fd34` from October 10, 2026. Read the
[engineering guide](ENGINEERING_GUIDE.md) for signal meanings, formulas, all default
settings, and recovery behavior. Use [the coordination hub](COORDINATION.md) to
bring observations and agent handoffs back to the main chat.

## 1. Start the right tester

Run commands from the repository root, not from inside `App/` or `Processing/`.

| Test | Command | What it opens |
| --- | --- | --- |
| Detector calibration + Processing | `Vision/.venv/bin/python -m App --source detector-demo` | Same window with manual generated image controls |
| Combined Vision → Processing | `python3 -m App` | Native app with a repeating synthetic Vision source |
| Manual matrices/vectors/eye switches | `python3 -m Processing.mouse` | Independent native Processing lab |
| Combined app ready for camera switching on Reuvi's prepared checkout | `Vision/.venv/bin/python -m App` | Same native app with optional camera libraries available |
| No window; full synthetic mouse cycle | `python3 -m App --headless --frames 490` | About 16.3 seconds of input, then a JSON report |

Use Python 3.10+ with Tk for the combined app. Default demo/manual tests require no
pip packages or camera. The prepared `Vision/.venv` and model exist only on this
local checkout; a teammate follows [Vision setup](../Vision/README.md#install-the-optional-camera-dependencies).
Check Tk separately with `python3 -m tkinter` if a window cannot open.

Only one process should own a physical camera. Other agents can use synthetic or
replay input concurrently in their own worktrees. Neither tester sends real OS
mouse events: inspect the pointer and page **inside the playground**.

## 2. First combined test: all four controls

1. Launch `python3 -m App`. Confirm **Vision demo (synthetic)** is selected and
   received/accepted counts increase. The known fixture `mouse-demo-person` is
   selected automatically. The source starts; output starts only when requested.
2. Click **Start preview**, then **Live lab**. If it says it is waiting for neutral,
   allow the cycle to reach its centered period. Mock input controls are disabled
   here because the Vision source owns input.
3. Watch at least one complete 16-second cycle after output becomes enabled.
   Compare the press counters and green output traces to the timeline below.
4. Open **Vision source & raw signals** to see the source measurements. Demo
   confidence is 1 and signals are valid. There are no camera images or raw
   eye-ratio traces in this source; that is expected.
5. Press **Stop / Escape** during motion. All outputs should immediately stop;
   source counters and diagnostics should continue. Start preview again to resume.
6. Press **Stop source**. Output must disable even if it was holding a button.
   Source restart requires a new Start preview.

### Integrated demo timeline

Times are relative to each 16-second source cycle, not the moment Start preview
was clicked. This is distinct from the standalone lab's eight-second scenarios.

| Source time | Synthetic input | Expected default output after arming |
| --- | --- | --- |
| 0–1.5 s | Neutral positions, eyes open | Velocities 0.5, buttons 0; baseline established |
| 1.5–1.62 s | Both eyes briefly closed | Dwell rises then resets; no presses |
| 2–2.7 s | Left eye closed | One left down after at least 320 ms; release after open debounce |
| 3–3.7 s | Right eye closed | One right down; left remains independent |
| 4–4.7 s | Both closed | Both buttons can hold; one extra press per eye |
| 5–9 s | Tongue/gaze circle, radius 0.32 around center | Both pointer velocity axes change; continuing relative movement |
| 9–10 s | Neutral | Pointer settles to stop |
| 10–11.5 s | `head_y=0.2` | Scroll output below 0.5, upward demand |
| 11.5–13 s | `head_y=0.8` | Scroll changes smoothly toward above 0.5, downward demand |
| 13–16 s | Neutral | Scroll settles to stop; ready for another cycle |

A full cycle enabled from its initial neutral phase gives **two left and two right
presses**, including the both-eyes hold. Startup halfway through a cycle, changed
thresholds, or late arming changes those counts. The pointer may reach the
playground boundary; continuing nonneutral velocity there is expected.

## 3. Manual Processing tests

Launch `python3 -m Processing.mouse`. Use defaults initially. Select **Manual
controls**, press **Center inputs & open eyes**, then **Start preview**. After
changing settings, repeat that centering/arming sequence. Run one test at a time.

| Test | Action | What to check |
| --- | --- | --- |
| Short blink | Press **Blink 120 ms** | Blue closure pulse; amber dwell below 1; neither green button activates |
| Left / right separately | Press **Left wink**, then **Right wink** | Only the corresponding output/counter changes |
| Sustained closure | Hold the left-eye checkbox for over 1 second | One down transition after dwell, held state, no repeated press counts |
| Debounced release | Open that eye again | Dwell clears immediately; held state releases after default 60 ms of confirmed open samples |
| Independence | Hold both eye checkboxes, then open only the left | Both can activate; right stays held while left releases |
| Start with an eye closed | Stop; close left; Start preview; keep it closed | Left does not activate until it has reopened long enough and a new closure qualifies |
| Pointer orientation | Select right, left, above, below center in the grid | X above/below 0.5 means right/left; Y below/above 0.5 means up/down |
| Continuous velocity | Hold an off-center grid cell | Pointer continues moving; it is not an absolute screen-position command |
| Centering | Press **Center inputs & open eyes** during motion | Smooth decay to output 0.5 rather than an endless drift |
| Scrolling | Select head-vector positions above, then below center | Scroll below, then above 0.5; no middle-button event |
| Immediate stop | Press Escape during motion/held buttons | Buttons 0 and axes exactly 0.5 without waiting for smoothing |
| Missing samples | During motion, press **Pause input stream** | Within the default 250 ms freshness budget plus scheduling delay, output disables |
| Recovery | Resume input after timeout | It stays stopped; center/open and explicitly Start preview again |

Use built-in scenarios for repeatability:

| Scenario label | What it exercises |
| --- | --- |
| Blink vs independent winks | Short blink, separate holds, simultaneous holds |
| Pointer orbit | Quantized matrix samples versus interpolated position and velocity |
| Scroll flick and settle | Rapid displacement, boost decay, sustained offset, reversal |
| Small input jitter | Small synthetic motions near center; quantization can move a sample across a threshold |
| Stream dropout | Scroll motion with no delivery from 2–3.2 s of its eight-second cycle; explicit re-arm required after loss |

Selecting a scenario automatically requests arming and starts its cycle. Use
**Manual controls** and center/open to return to direct input. At default 9×9
resolution, one grid step is 0.125 raw position or 0.25 centered signed offset;
it exceeds the pointer's 0.19 activation threshold. Do not expect every visually
small one-cell movement or quantized jitter scenario to be suppressed. Increase
grid resolution when examining finer dead-zone behavior.

## 4. Read and export the scopes correctly

| View | Blue / raw | Amber | Green / output |
| --- | --- | --- | --- |
| Pointer X, Pointer Y, Scroll Y | Latest usable decoded position, held between inputs | Delayed/interpolated position | Normalized velocity: 0.5 stopped |
| Independent eye scopes | Closed state: 1 closed, 0 open | Closure dwell progress | Button held state 0/1 |
| Camera raw-ratio scopes | Anatomical eye geometry; see each legend | Not the processing transfer-function plot | Not mouse output |

The Vision table uses **eye open = 1**, but the processing eye scopes use
**eye closed = 1**. This is an intentional adapter conversion. Raw position 0.75
does not imply output velocity 0.75. **Darker segments mean unknown input, held at
the last known height for display only.** Valid data resumes in the normal color;
a never-observed channel stays blank. Zero is a valid measurement, never a missing
data marker. Numeric readouts and CSV keep unknowns empty/invalid; Processing still
releases invalid buttons and neutralizes affected motion. A dark raw-eye line at 1
must not be read as a continued click.

**Freeze scope** freezes the displayed Processing history, not the producer or
output. Use Stop if you want output disabled. **Export CSV** saves the frozen
history when frozen; otherwise it saves the current history (up to 2,000 rows,
about 20 seconds). Plots show the latest eight seconds of that history.

CSV fields:

| Fields | Meaning |
| --- | --- |
| `id`, `t`, `sample` | Trace-row ID; seconds since lab creation; latest source sequence |
| `raw_x`, `raw_y`, `raw_scroll` | Usable decoded positions on each Processing tick |
| `interp_x`, `interp_y`, `interp_scroll` | Positions evaluated at the delayed clock |
| `target_x`, `target_y`, `target_scroll` | Velocity targets after curve/boost, normalized to `[0,1]` |
| `out_x`, `out_y`, `out_scroll` | Actual filtered normalized velocity |
| `left_raw`, `right_raw` | Converted closed bits, or blank when unavailable |
| `left_dwell`, `right_dwell` | Independent timer progress |
| `left_out`, `right_out` | Independent held-button states |

This CSV is a Processing-clock trace, so several rows can refer to the same input
sample. It does not export the camera's ratio scopes, images, full frame envelope,
enabled/status fields, or configuration. Save the JSON settings and record source,
subject, status, and commit with each experiment. After a settings reset, history
is cleared; row IDs and elapsed lab time need not restart at zero.

## 5. Tune one variable at a time

Use **Transfer settings → Export JSON** to save the baseline, change one setting,
**Apply settings**, center/open, then Start preview. Compare the same scenario.
Use **Import JSON** to restore it. Export/import uses native file dialogs.
Save local profiles in ignored `local-profiles/`; keep personal trace data in
ignored `data/private/` rather than tracked source directories.

| Observation | First experiment | Tradeoff to observe |
| --- | --- | --- |
| Short closures cause unwanted presses | Raise that eye's dwell | Slower intentional click |
| Intentional closure feels too long | Lower only that eye's dwell | More short-closure activations |
| Button drops on brief open noise | Increase that eye's release time | Slower intended release |
| Motion begins too near center | Increase dead zone; check calibrated center | More movement needed to start |
| Motion toggles at threshold | Increase hysteresis | Larger activation offset |
| Small deliberate offsets are too fast | Increase exponent | Softer near-center response |
| Response lags | Reduce smoothing or interpolation separately | Less noise suppression or visible sample steps |
| Starting/reversing is abrupt | Lower acceleration | Slower velocity changes |
| Returning to center glides too long | Raise deceleration and/or reduce smoothing, separately | Sharper stops |
| A fast jump overshoots | Set boost gain to 0 for comparison | Removes jump-speed enhancement |
| Jumps should have longer influence | Increase boost decay time | More time above base velocity |
| All pointer motion is too fast | Lower playground pointer speed | Changes simulated scale, not filter output |
| Direction is reversed | Toggle the appropriate inversion | Confirm anatomical/source orientation first |

The full [settings reference](ENGINEERING_GUIDE.md#6-configuration-reference)
includes units and allowed bounds. **Calibrate current neutral** changes only
Processing's center offsets from fresh valid input and stops preview. It does not
replace the Vision calibration flow on Detection calibration. Avoid using an extreme matrix cell
as center: centers must be between 0.05 and 0.95.

For sample-rate experiments, change standalone **Input Hz** from 30 to 10, then
60. Dwell should remain based on milliseconds; its confirmation becomes coarser
at 10 Hz. Fixed 50 ms interpolation cannot always span two samples 100 ms apart,
so more holds are expected. In the combined app change source **FPS** and restart
the source instead; the mock Input Hz field does not control Vision.

## 6. Live camera diagnostics: what to test now

For the per-detector implementation status, ML explanation, and detection-only
experiment checklist, use [RAW_DETECTION_GUIDE.md](RAW_DETECTION_GUIDE.md).

After optional [camera setup](../Vision/README.md#install-the-optional-camera-dependencies):

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

1. Confirm a camera image and landmark overlay appear; read **actual** source Hz
   and source errors rather than assuming the requested FPS was achieved.
2. Choose a currently detected subject and press **Use selected subject**. Merely
   displaying a dropdown option does not bind Processing to it.
3. Test **eyes first** in Detection calibration → 1 Eyes: **Test sound**, then
   **Start eye calibration**. A temporary full-screen guide opens. Follow five
   open-eye dot positions; close gently at
   descending tones, reopen at two high tones, and wait for completion tones.
   Read [the guided procedure](../Vision/DETECTION_LAB.md#1-independent-eye-calibration).
   Look around with eyes open: both scopes should stay at **0**. Close one eye at
   a time, then both: each respective trace should reach **1** independently.
   Unknown readings produce a darker hold of the previous height, not a new
   closed bit. Completion returns to the lab automatically; Escape or the popup
   Cancel button exits early. If any pose is labeled
   incorrectly, **Restart eye calibration** clears bad eye training without changing
   head/tongue fits. Leaving this active guide cancels it. Later test head targets
   and tongue training/checks using the same runbook.
4. Verify each channel becomes valid only after its requirements pass. Open Live
   lab and explicitly Start preview with neutral/open input. Compare raw versus
   processed values; missing channels remain unavailable. Save active profile on
   the source tab, then test restart → select → load → fresh tongue checks.
5. Move out of view, then return. Check the selected subject is missing or the
   tracker creates a new ID. Select deliberately; another face must not silently
   take control. Test with at most two faces when ready.
6. Stop the source. The view labels retained values/frame as last observed; source
   stop disables output. Add `--no-preview` to compare throughput without overlay
   generation/drawing; it does not change calibration requirements.

The preview is unmirrored: anatomical left appears on image right. Bounding-box
IDs are not recognized people. Loading a profile requires explicit selection and
never starts output. Record actual false clicks, missed gestures and unavailable
frames; synthetic integration tests do not establish live accuracy.

## 7. Replay, automated checks, and known evidence

```bash
python3 -m App --source replay --replay tests/vision/fixtures/scenario.ndjson
python3 -m App --headless --frames 490
python3 -m unittest discover -s tests/integration -v
python3 -m unittest discover -s tests/processing -v
python3 -m unittest discover -s tests/vision -v
python3 -m unittest discover -s tests/tooling -v
```

The existing replay fixture is only six frames, mainly for loss/subject behavior.
It is not the full mouse exercise. Camera/replay need explicit subject selection
(or `--subject ID` at launch); replay may finish before you can select in the UI.
EOF should immediately disable output. Recorded sessions get fresh runtime IDs
and rebased timestamps; sequence gaps and sample intervals are preserved.

For the **490-frame demo with defaults**, inspect the JSON report: all four
`observed` flags should be true, `error` null, and final output disabled with both
buttons 0 and all velocities 0.5. The CLI returns nonzero on source error, but
**does not turn a false observed flag into a failing exit code**. Read the report;
the integration test suite provides assertions for all four behaviors. The
default 120-frame headless run is too short to cover pointer and scroll phases.

Optional model test, without opening a camera:

```bash
VISION_MODEL_PATH=Vision/.local/face_landmarker.task \
  Vision/.venv/bin/python -m unittest discover -s tests/vision -v
```

Recorded integration evidence, not a claim that these checks run continuously:

| Check at baseline | Result / scope |
| --- | --- |
| Integration suite | 9 passed: four actions, independent eye classifier path, missing subject, timestamps, dropout, invalid data, lifecycle, raw camera adapter |
| Processing suite | 34 passed: adapters, filters, independence, timing, bounds, settings, controller |
| Vision suite with local model | 45 passed, including blank-image inference and model restart; default dependency-free run skips that optional test |
| Worktree/scope tooling suite | 7 passed |
| Combined real-clock demo | 490/490 accepted at about 30 Hz; all four actions seen; disabled neutral output at EOF |
| Actual camera smoke | 15 frames without capture/model error, about 11 Hz at requested 15 on this Mac; no selected subject, no enabled controls |
| Native UI inspection | Source/raw table, processing lab, camera overlay and raw ratios inspected |

The 95-test total includes the optional model test. No end-to-end live gesture
accuracy or hardware-emulator success has been established. The repository
[CI workflow](../.github/workflows/mouse-mvp.yml) runs the four core suites on
main pushes and PRs without camera dependencies; inspect the actual run status
before describing a particular remote build as passing. Historical details are
in [App/HANDOFF.md](../App/HANDOFF.md).

## 8. Troubleshooting while testing

| Symptom | Check first |
| --- | --- |
| No real desktop pointer movement | Expected: this is the simulated playground; driver connection is pending |
| Waiting for fresh neutral input | Center valid axes; provide fresh samples; each eye needs its own open baseline |
| Camera overlay but no clicks | Select your face, calibrate or load a profile, then inspect validity and arm preview |
| All camera values unavailable | Select the subject explicitly; normalized controls still remain invalid today |
| Received increases but accepted does not | Read latest input reason; check selected subject, capture age, and frame validity |
| Source FPS setting seems ineffective | Restart source; camera backend may not deliver requested rate |
| Output stops at low FPS | Compare sample interval/inference delay to `stale_ms`; inspect actual timestamps |
| External-source controls cannot be clicked | Mocks are intentionally disabled in App; use standalone Processing for manual input |
| Stop did not stop graphs | Stop affects output; use Stop source to halt Vision, or Freeze scope to inspect history |
| Replay instantly ends | The supplied fixture is short; restart/re-arm or use a longer synthetic fixture |
| Old camera image remains after stop | It is labeled last observed, not fresh control data |
| Imported standalone settings fail in App | A mock source conflicts with App's external source; use Processing-only config at launch |

## 9. Bring a useful result back to the main chat

Copy this into the main coordination conversation. Attach a small **synthetic**
reproducer if possible; keep personal camera data local.

```text
Test / date / tester:
Commit, branch, and worktree:
Launch command, Python version, OS:
Source (Vision demo / manual mock / replay / camera):
Selected subject, requested and actual Hz:
Settings file or exact differences from defaults:
Steps and time within the source cycle:
Expected output:
Observed values, enabled/status, accepted/rejected counts:
Result: pass / fail / unavailable feature
Local CSV/profile paths or synthetic reproducer:
Suggested owning lane and next experiment:
```

Repeatable settings and capture/source timing make it possible to tell a detector
problem from a Processing filter or future driver problem. Record what was
observed, including unavailable features, rather than marking the entire pipeline
as working because one layer succeeded.

## Temporal detection research increment

See [Detection research testing guide](DETECTION_RESEARCH_GUIDE.md) for blink/wink trial labels, duration histograms, supporting-feature ablations, alternative mappings and gaze evaluation. Native research UI checks are included under `RUN_TK_TESTS=1`. The new benchmark is `python3 -m Processing.research.benchmark`; like other synthetic checks it excludes camera/inference/UI.
