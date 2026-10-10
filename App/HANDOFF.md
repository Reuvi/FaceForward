# Native mouse MVP integration handoff

## Behavior

App combines the local Vision and Processing branches into one native Python/Tk
lab. Vision demo/replay and explicit camera diagnostics use the same direct
SignalFrame callback. The four mouse actions are exercised with continuous,
explicitly synthetic detector values. Camera overlay and raw eye geometry are
visible alongside validity-aware input and processed scopes. There is no browser,
JavaScript, server, remote inference, or OS input driver.

Integration fixes: display rejected frames and gaps instead of stale selected-face
readings; accept newer sequences with equal capture times; prevent mocks from
overriding the external producer; reject duplicate workers; disable output at
EOF/error/stop; keep diagnostics and output on separate clocks.

## Ownership

- Task: user-authorized Vision/Processing integration, local merge to main, push.
- Integration branch: `work/reuvi/integration/vision-mouse-mvp`.
- Starting main: `5e22272003b0684e84bd13d4d0740ea193bd9fe6`.
- Merged Vision: `9f51fb7` from `work/codex/vision/measurement-plan`, including its
  two local commits that had not yet been pushed.
- Merged Processing: `d4d3501` from `work/reuvi/processing/mouse-lab`.
- Work occurred in an isolated integration checkout. Component worktrees and
  their branch/index state were not changed.
- Changed integration areas: App, Processing integration hooks/UI, Vision mouse
  fixtures/overlay caption, shared documentation/contracts, integration tests, CI.
- Driver files, original project notes, and teammates' environments are untouched.

## Verification

- 9 integration tests: real Vision producer/replay into Processing; all four
  outputs; independent eye classification; no-face/bystander loss; equal timestamps;
  stale input; malformed data; camera diagnostic adapter; worker/EOF/error/stop.
- 34 Processing tests and 7 collaboration tooling tests.
- 45 Vision tests with the local MediaPipe model enabled, including blank-image
  inference and native model restart. The camera-free default skips that one
  optional model test.
- `python3 -m App --headless --frames 490`: 490/490 frames accepted, approximately
  30 Hz, all four actions observed, no source errors, disabled neutral output at EOF.
- Actual camera diagnostic smoke: 15 frames received without a capture/model
  error, approximately 11 Hz at requested 15 Hz on this Mac. No subject was selected
  in that bounded run, so no frames enabled output. This is acquisition/inference
  evidence, not a face-gesture accuracy measurement.
- Native UI inspection: source controls, readable raw measurement table,
  integrated lab with disabled mock overrides, and live camera/landmark preview.
- Camera frames stayed in memory. No images, face recordings, models, environments,
  or personal profiles are included in Git.
- The main checkout has its own ignored `Vision/.venv` and a checksum-verified
  copy of the already-downloaded model, ready for local diagnostics testing.
- Whitespace, compilation, and integration ownership checks completed before merge.

## Remaining work

Live camera controls remain invalid until a calibration collection flow and
quality gates are supplied. Head and tongue detectors are absent in the merged
Vision branch. Do not describe the synthetic four-action demo as fully working
face control. The hardware emulator's adapter and real OS events are also pending.
See [the runbook](README.md) for exact launch/setup commands, source limitations,
and the proposed eye → head → tongue → emulator iteration order.
