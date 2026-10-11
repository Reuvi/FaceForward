# Gaming mapping planning handoff

## Behavior

Reuvi requested a plan for **gaming keyboard mouse mapping 1** while another
agent finishes pupil detection. The plan specifies left/right eye actions for
left/right mouse buttons, head down/up/left/right for W/Space/left Shift/S, and
pupils for the pointer. It adds proposed noise thresholds, response shaping,
readable action diagnostics, named mapping persistence and an implementation order.
There is no runtime behavior change and no new selectable mapping yet.

## Ownership

- Task / lane / branch: gaming mapping plan / Processing /
  `work/reuvi/processing/gaming-mapping-plan`.
- Worktree: `.worktrees/reuvi-processing-gaming-mapping-plan` beneath the repository.
- Base: `63fb5d3590d040bb82be7b9962c225c26405adbd` (fetched main).
- Driver reference: fetched `origin/driverTest` at
  `2e3e7349652af1eca2869ffd932738bde92133f9`.
- Changed paths: `Processing/GAMING_KEYBOARD_MOUSE_MAPPING_1.md`,
  `Processing/interface-requests/gaming-keyboard-mouse-1.md`,
  `Processing/GAMING_MAPPING_PLAN_HANDOFF.md`, `Processing/README.md`.
- No shared contracts, detector code, driver code, runtime settings or pupil
  worktree changed. No merge/push or external teammate message was performed.

## Verification

Checks performed on 2026-10-10 local date:

| Command/check | Result |
| --- | --- |
| `git fetch origin` | Succeeded; inspected the driverTest commit above |
| Native-enabled driver configure/build from an isolated archive of that commit | Succeeded with AppleClang 21.0.0; macOS backend compiled |
| `ctest --test-dir build --output-on-failure` in the driver snapshot | 4/4 suites passed: control, C API, C header, Python testing console; 10.09 seconds |
| Plan Markdown relative links and synthetic JSON example | Checked for local targets and parsable finite/binary values |
| `git diff --check` | Passed |
| `python3 tools/check_scope.py --base 63fb5d3590d040bb82be7b9962c225c26405adbd --lane processing` | Passed; only Processing documentation |

The build used `/tmp/face-driver-plan.24MUUG`, extracted via `git archive` from
the pinned driver commit. From that snapshot root, the commands were:

```sh
cmake -S Drivers -B build -DCMAKE_BUILD_TYPE=Debug -DFID_NATIVE_BACKEND=ON
cmake --build build -j 4
ctest --test-dir build --output-on-failure
```

The SDK warned that the driver's default macOS 10.15 deployment target is no
longer supported by its libc++; build/tests still succeeded on this host. This
does not establish compatibility with old macOS releases. No dependencies or
system permissions were changed. Tests used dry-run output; no camera or native
input session was opened, and no OS mouse/keyboard events were sent. Existing
Processing/integration runtime suites were not rerun for this documentation-only
change. This is driver baseline verification, not testing an implemented mapping.

## Handoff

The reviewed ABI v3 already supports held W/S/Space/Shift and velocity control.
Its mouse fields still generate dwell-qualified taps; held mouse state and
reliable short-transition delivery need a Drivers change. A Python adapter must
validate timestamps/sequence/subject/enabled/known state, since C frames omit them,
and must call pause immediately on errors rather than rely on rejected input.
Processing owns signal shaping; configure the driver's extra dead zone off.

Shared contract impact: none landed. The proposed `device_control_v1` introduces
held-key snapshots, held-mouse requirements, an independent output session/clock,
preserved source provenance, mapping identity and availability. Integration owns
adoption/versioning. A separate `input_mapping_v1` store avoids changing existing
strict face/mouse v3 files during the first implementation.

Remaining dependencies: agreement/implementation of the shared handoff and held
mouse ABI; final pupil measurement contract; actual user tuning; explicit native
target OS/game validation. The plan assumes continuous pupil velocity and held
buttons/keys pending the optional user preference. Current pupils need both eyes,
so a closed eye can stop pointer motion while clicking. No new eye dwell or
unverified natural-blink rejection is promised.

Next action: integration reviews the
[interface proposal](interface-requests/gaming-keyboard-mouse-1.md), then
Processing implements the preset and preview against a mock output while Drivers
adds held mouse support. Preserve the concurrent pupil agent's branch/worktree.
The planning commit is reported in the task's final response; this branch is a
local handoff and has not been published to other computers.
