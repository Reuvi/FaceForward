# Selectable eye closure and head-center recovery

The user requested an optional plain eye open/closed click path and diagnosis of
stopped movement. This supersedes the wink-only restriction when explicitly
selected. It does not change Vision measurements or the driver API.

Mapping v7 adds `require_wink` (boolean, default true). Fully validate v1–v6 and
migrate with true, preserving their behavior and all response settings. False
uses each eye's anatomical open/closed signal, ignoring appearance `eye_intent`.
SignalFrame open=1/closed=0; legacy raw polarity remains configurable. Accept only
valid, confident discrete measurements. Closure is immediate ON, open is OFF;
ordinary blinks also activate clicks. Each eye requires its own fresh reopening
at startup/after unknown. Unknown releases, never acts on a held numeric value.
No dwell, opposite-eye gate, repeated held clicks or wink training is required in
plain mode. Eye geometry calibration remains required where Vision requires it.
Mouse test's existing `head_wink_clicks` field still enables/disables eye clicks;
its name stays compatible even when the selected eye source is plain closure.

Expose Require calibrated wink in Live curves. Changing this structural input
option releases and stops output; it never reprocesses a cached frame or arms.
Save/copy/export/load and tuning defaults preserve this choice. Live analog sliders
retain their existing hot-update behavior. Face profiles and detectors are unchanged.

The observed pointer stall was an armed controller waiting for its saved head
center, not a driver error. Add an explicit Center head & start action for head
mouse mappings. Stop/release first, then establish the center from the next fresh,
accepted capture with both axes valid and known eye actions released. Unknown
eyes do not block movement. Centers must be within existing .05–.95 bounds; at a
range limit, remain stopped and explain that the user must move away from it.
Keep raw head measurements, learned detector ranges and precise movement dead zone
unchanged. Save the new Processing center in the mapping/tuning profile. The first
enabled driver command must be neutral. Stop, loss, staleness, source restart and
mapping/settings changes cancel this request; reacquisition cannot auto-arm.
Normal Start retains its saved-center behavior.

Show waiting-for-center separately from running, identify the recovery action,
and log the eye mode, per-eye validity/rearming and pending center capture. Missing
face/input must not be described as missing calibration without evidence. Verify
both paths with injected captures, native UI callbacks and the compiled dry-run
driver; synthetic tests do not measure tracking accuracy or OS permissions.
