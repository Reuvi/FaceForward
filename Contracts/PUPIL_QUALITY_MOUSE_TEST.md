# Pupil quality and Mouse test

> Current behavior: [raw pupil control](RAW_PUPIL_CONTROL.md) supersedes pupil fitting/head compensation below. No pupil guide is required or exposed; old fits are retained as inactive data.

User-requested integration update, 2026-10-11. Extends the pupil/head calibration
and driver contracts; source signals and device_control_v1 do not change.

## Pupil handling

Preserve raw iris coordinates, personal pupil ranges/head compensation, both-eye
visibility, capture timestamps, and explicit invalid observations. When completed
guided eye geometry positively identifies that same eye as open, use it as
additional aperture evidence instead of rejecting solely on population-wide lid
and blink thresholds. No eye fit is required; missing/legacy fits retain existing
checks. Strong blink evidence, failed image/iris checks and uncertain narrow eyes
remain unavailable. This does not change wink classification or calibration data.

Gaming pointer velocity uses a 1€ adaptive low-pass filter with a shared 2D speed
estimate: stronger stationary smoothing and less lag on deliberate motion, followed
by existing acceleration limits. Raw observations/arming gates remain unfiltered;
invalid input resets all filter history and releases immediately. No prediction,
held unknown values or automatic rearming. The legacy fixed filter remains an
explicit mapping option. Human accuracy requires live validation; synthetic noise
and step-response measurements are engineering evidence only.

## Mouse test

A built-in named mapping `mouse-test` / `Mouse test` uses calibrated head_x and
head_y together as a two-dimensional relative mouse velocity request. Left/up
are negative velocity, right/down positive; neutral .5/.5 stops. Radial dead zone,
response curve, gain, smoothing and acceleration apply to the combined vector.
Both head measurements must be valid/fresh. Either unavailable measurement stops
the pointer immediately. Eyes/pupils do not gate arming or output; clicks, keyboard
and scroll always stay released. Existing loss/stale/Stop/explicit Start behavior
and the driver's first-real-neutral requirement apply.

Mapping JSON v2 adds input_mode (`gaming` / `head-mouse`) and adaptive_pointer
(boolean). Valid v1 files load as gaming with adaptive filtering. Mouse test copies
retain head-only behavior; bindings must be all none. Mapping/settings/profile
changes stop output. Detector profiles stay v12 and combined profiles stay v3;
face-profile response settings apply to the chosen mapping without changing mode.
