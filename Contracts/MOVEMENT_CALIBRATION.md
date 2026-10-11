# Head/tongue calibration and shared raw diagnostics

[JOYSTICK_DETECTION.md](JOYSTICK_DETECTION.md) adds pupil calibration and replaces
the camera tongue appearance backend with pinned neural masks/preset v6. The
color-only statements below describe the earlier developer baseline; head pitch
and range normalization are unchanged.

This increment belongs to Reuvi's integration task, base `482fa65`. The active
mode remains mouse testing, but detection calibration is independent of device
transfer functions. No mouse velocity, acceleration or driver-format change is
part of this increment.

One camera/workbench produces the raw features, calibration traces and normalized
SignalFrame for every capture. The camera setup tab and calibration tab consume
the same bounded capture history and envelope, not separate UI-sampled histories.
Raw graphs use physical/detector units; calibrated graphs use personal coordinates.
Tab changes do not change a measurement or recalibrate it. Active guided movement
collection pauses output and is cancelled if its instructions are hidden.

Head MVP is vertical Y from nod/pitch (degrees), with no measurement-mode choice
in the calibration UI or its settings editor. A guided neutral/up/down training
pass is followed by new neutral/up/down checks. Learned comfortable up=0,
neutral=.5, down=1 irrespective of pitch sign or unequal movement ranges. Each
half maps linearly to use the full normalized range; no fixed degree range sets
the output. Raw degree displays use the learned limits once available, while
normalized graphs stay 0–1. Small overshoot uses the existing endpoint tolerance;
larger out-of-range or unavailable measurements remain invalid.

Runtime/settings use pitch. Legacy position-mode presets are fully validated
before converting settings to pitch and removing only the incompatible head fit.
Compatible eyes/winks/tongue data are retained under their existing rules. Older
presets without an explicit mode are interpreted as the old position default.
New saves explicitly name pitch; preset v5 and combined profile v3 are unchanged.
Head X is now independently calibrated as yaw; see HEAD_HORIZONTAL.md, which
also defines detector preset v7. The pitch behavior above is unchanged.

Tongue appearance remains experimental local color segmentation with manual
tongue-only marking. The current measurement is the middle of its visible front
boundary, using an expanded crop and mouth-width units on both axes; see
[TONGUE_TIP.md](TONGUE_TIP.md). No tip is fabricated before appearance training,
while absent, or when its edge is ambiguous. A guided absent check precedes
center/left/right/up/down captures and separate fresh position checks. Independent
axis fits map comfortable endpoints to 0/1 and learned center to .5.

Calibrated frames emit `position_space: personal_tongue_tip_v1` and
`tongue_measurement: color_tip_mouth_width_v1`. `tongue_x/y` are personal positions,
not velocity. Raw tip coordinates are `tongue_tip_x/y` (also aliased by the older
`tongue_candidate_x/y` diagnostic names). Region centroid remains debug-only.
Generic legacy replay keeps its old schema.

Detector preset v5 retains validated v1-v4 loading while discarding incompatible
old tongue appearance/ranges; compatible eye/wink/head fits survive. Combined
profile v3 is unchanged. Completed fits persist through brief loss and restart;
loading/restart require a fresh absent + five-position recheck of a saved tip range.
Old tongue fits require both appearance and range training again.

Unknown numeric diagnostics remain null/invalid. Plot-only holds use darker
versions of the original colors, with no invented measurements or control input.
Calibration samples use original capture timestamps and only acknowledged capture
windows; rest/preparation, duplicates, missing features and stale input do not train.
Full source loss/cancel preserves completed fits and discards unfinished work.
Synthetic tests establish behavior, not real-person detector accuracy.

A later learned segmentation backend must explicitly version its coordinate space
and calibration. Changing the current color-mask tip measurement or crop requires
a coordinated contract and fresh calibration, even if both return X/Y.
See [the tongue model evaluation plan](../Vision/TONGUE_MODEL_PLAN.md).

## Head Y step correction (2026-10-10)

The Head Y guide now supports restarting its current capture/check and selecting
neutral/up/down captures or checks independently. Keep accepted captures for
other poses. Replacing a training reference clears dependent checks and requires
fresh neutral/up/down checks before adopting the candidate. A check-only retry
keeps the fitted references and already passed checks; it never trains the fit.

Keep the last completed pitch fit during a full restart, failed correction or
cancel. A loaded/completed fit supplies real saved scalar references when only
one pose is recaptured; do not invent camera samples or duplicate saved values to
satisfy sample-count rules. Actual new captures still need the normal sample and
stability gates. Other eye/wink/head-X/pupil fits remain untouched.

UI rest/preparation and original timestamp windows apply to every retry. Bump
prompt generation so late acknowledgments cannot start a replacement step.
Editing/retrying disarms App output and does not create a second camera. Preset
v12, normalized units, sign handling, ranges and SignalFrame remain unchanged.
