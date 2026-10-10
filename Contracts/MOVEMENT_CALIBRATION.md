# Head/tongue calibration and shared raw diagnostics

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

Head MVP is vertical Y. An explicit selector chooses whole-head image translation
(nose bridge Y / image height) or nod/pitch (degrees). Changing this choice clears
only head calibration. A guided neutral/up/down training pass is followed by new
neutral/up/down checks. Up=0, neutral=.5, down=1 irrespective of pitch sign.
Head X is reserved and remains unavailable.

Tongue appearance remains experimental local color segmentation, with manual
tongue-only marking. Raw candidate X/Y is the visible region centroid in a
mouth-relative coordinate system, not the tongue tip or a verified tongue label.
No candidate is fabricated before appearance training or while absent.
A guided absent check precedes center/left/right/up/down captures and separate
fresh position checks. Independent axis fits map comfortable endpoints to 0/1
and the learned center to .5. Failed/missing/overlapping data cannot enable output.

In the calibrated camera path, `tongue_x/y` now represent that learned personal
range, instead of the earlier full-mouth coordinates. The unchanged raw mouth
coordinates stay in `tongue_candidate_x/y` diagnostics. Emit additive
`position_space: "personal_range_v1"` on calibrated frames to make that meaning
explicit. These are positions, not mouse velocity demands; Processing mappings
remain a later/device-specific stage. Generic legacy replay keeps its old schema.

Detector preset v4 adds `tongue_range` and retains v1/v2/v3 loading. Combined
profile v3 remains unchanged. Completed fits persist through brief loss and source
restart; loading/restart require a fresh absent + five-position recheck of the saved range. Old profiles
without a tongue movement range require the new position guide before tongue
output can be valid. Stored ranges are never guessed from the full mouth.

Unknown numeric diagnostics remain null/invalid. Plot-only holds use darker
versions of the original colors, with no invented measurements or control input.
Calibration samples use original capture timestamps and only acknowledged capture
windows; rest/preparation, duplicates, missing features and stale input do not train.
Full source loss/cancel preserves completed fits and discards unfinished work.
Synthetic tests establish behavior, not real-person detector accuracy.

A later learned segmentation backend must explicitly version its coordinate space
and calibration. The current raw domain excludes tongue protrusion outside the
inner lips. Changing crop/scaling or centroid to tip requires a new coordinated
contract; do not load current color-based ranges onto those new measurements.
See [the tongue model evaluation plan](../Vision/TONGUE_MODEL_PLAN.md).
