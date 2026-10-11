# Gaming signal processing handoff

## Behavior

App now selects **gaming keyboard mouse mapping 1** by default. Current calibrated
Vision eye intent, head X/Y and continuous head-compensated pupil directions reach
Processing through the existing single `MouseSession`/`Lab.ingest` connection.
Previously App exposed mouse/scroll output only. It now produces held W/Space/
left Shift/S, independent mouse states and pointer velocity, with head filtering,
hysteresis, confirmation and pupil gain after the dead zone. Mouse/scroll mode
remains available. The native Signal mapping tab explains each input, exposes
head thresholds/bindings/gain, and supports named copies and local JSON persistence.

## Ownership

- Lane/task: integration, gaming-signal-processing; authorized by Reuvi's request
  to implement the middle phase after the pupil work completed.
- Branch: `work/reuvi/integration/gaming-signal-processing`.
- Worktree: `.worktrees/reuvi-integration-gaming-signal-processing`.
- Base: `7175a89b7d3269c3230cd62af206ccc1d851d29e` (completed pupil/head retry work).
- Plan imported as `fbef43f`; shared contract landed first as `ba1f76b`.
- Runtime commit: the commit introducing this handoff; resolve with
  `git log -1 --format=%H -- Processing/mappings/HANDOFF.md`.
- Changed paths: `Processing/mappings/**`, `Processing/mouse/**`, App wiring/UI,
  `Contracts/GAMING_MAPPING.md`, related READMEs/guides/coordination, Processing and
  integration tests. Vision and Drivers source files are unchanged.
- Driver dependency: latest remote `driverTest` verified at
  `2e3e7349652af1eca2869ffd932738bde92133f9`; the plan inspected/built that revision
  separately without merging its native driver implementation into this branch.

## Verification

Run these from this worktree. On this Mac, `PY` below denotes the existing
`/Users/reuviisraeli/Desktop/Hackathon fall 26/Vision/.venv/bin/python` (Python 3.12.5).
No camera or OS input injection was opened for these checks.

| Command / check | Actual result |
| --- | --- |
| `"$PY" -m unittest discover -s tests/processing` | 98 tests passed |
| `RUN_TK_TESTS=1 "$PY" -m unittest discover -s tests/integration` | 105 tests passed, no skips, 65.069 seconds |
| `"$PY" -m App --headless --frames 490` | 490/490 accepted, about 29.92 Hz; both mouse states, pointer and all four keys observed; scroll neutral; disabled/released at EOF |
| `"$PY" -m App --headless --frames 490 --mapping mouse` | 490/490 accepted, about 30.04 Hz; both mouse states, pointer and scroll observed; all keys inactive; disabled/released at EOF |
| `"$PY" -m Processing.mouse.benchmark` | 10,000 steps: 46.44 µs mean, 65.75 µs p95 |
| Same benchmark with `benchmark.MouseProcessor = GamingProcessor` | 10,000 steps: 58.93 µs mean, 83.75 µs p95; synthetic decoding/core only, excludes capture/UI/driver |
| Native visual inspection | Signal mapping rows, thresholds, head scopes, transitions and preview-only label fit the default window |
| Ruff `--select F`, compileall, `git diff --check` | Passed for changed Python/files |
| `python3 tools/check_scope.py --base 7175a89 --lane integration` | Passed; 30 paths across plan, contract and implementation, all within the coordinated scope |

New tests cover exact head boundaries, jitter/hysteresis, capture-rate timing,
equal timestamps, reversal, partial invalidity and neutral recovery, immediate
independent eye intent, loss/staleness/restarts, pointer precision and gain, short
ON/OFF transitions between ticks, bounded journal gaps, named files/mode isolation,
generated pixels through the current calibrated detector, profile v12 reuse, and
native panel settings/mapping switching. Synthetic results do not measure human
gesture accuracy. No full Vision suite was rerun because detector code is unchanged;
the integration suite exercises the current detector path and profiles.

## Contract and lifecycle

`device_control_v1` adds complete six-key state, independent buttons, normalized
velocity, known flags, mapping ID/revision, output session/sequence and unchanged
source provenance. Eye semantics are instantaneous calibrated intent, with unknown
release and actual reopening to rearm. Head and pupil unknowns remain null in
diagnostics. Stop, face loss, malformed envelope, stale source, restart, mapping/
settings/profile changes and close release output; reacquisition cannot auto-arm.

`input_mapping_v1` is separate from unchanged `face_mouse_profile_v3`. Mapping
changes never mutate detector fits. A face-profile load applies existing response
settings to the active mapping, preserves its head/key settings, and disarms it.
The 512-entry command-transition journal records between-tick action edges but
does not promise live transport reliability. A future consumer must reject stale
origins and stop on gaps. Motion uses only the latest command.

## Remaining dependencies and reproduction

Use `python3 -m App --source demo` in this checkout, then Signal mapping and Start
preview. For camera input follow [the runbook](README.md); load or finish the
independent detector guides first. Export mapping settings separately from the
face profile. The generated demo has synthetic eye intent/yaw only in demo mode;
camera/replay frames are never decorated.

Native Drivers integration remains pending: driverTest mouse fields currently
emit dwell-qualified taps, not held buttons, and its C ABI omits enable/source-age
metadata. Live output requires held-mouse support, ordered action delivery and a
validated Python lifecycle adapter. No native library is loaded here. Real-person
threshold tuning and actual gaming/device behavior remain untested.

No merge/push was performed. The integration branch contains all work; the original
checkout and other active worktrees remain preserved. This is the implementation
handoff to Reuvi's coordination conversation.
