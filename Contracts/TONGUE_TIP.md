# Experimental color-mask tongue tip

Current calibration usability update: keep **Reset tongue** visible outside the
scrolling setup controls. It cancels tongue collection/position guidance and clears
appearance, training colors/marks, range, checks and current tip without requiring
a face. It preserves completed eye/head fits. It must not cancel unrelated active
eye/head work. Clearing tongue marks keeps the empty-mouth background so a bad
positive click can be retried. Show the actual clicked patches on the frozen image,
not a fixed center marker. Numbered instructions and prerequisite-aware controls
guide background → tongue photo/marks → appearance fit/inspection → position guide.
No segmentation or coordinate algorithm changes are implied by this UI update.
Tongue position capture is user-paced: after each rest, instructions remain visible
until **I'm in position — capture** acknowledges that pose. Failure offers retry
of that pose, retaining preceding successful groups and the appearance model;
only a fully checked range enables normalized output. Head guidance is unchanged.

Authorized integration task: Reuvi, base `0123b8d`, branch
`work/reuvi/integration/tongue-tip`. Keep native local Python and the existing color
segmentation approach. No pretrained network or Processing/driver change.

Replace the current control measurement (region centroid) with the midpoint of the visible front color boundary. Select the front arc
using the mask geometry, fit its middle, and anchor it to the observed front
boundary; do not average the tongue body.
Use a padded mouth-aligned square with side length 1.6 mouth widths,
covering protrusion. Raw tip coordinates are signed mouth-width units about the
mouth-corner midpoint: anatomical right +X, down +Y. Both axes use mouth width,
not mouth opening. Domain is [-0.8, 0.8] on both axes. Normalized tongue_x/y still
use personal comfortable limits (0/1) and learned neutral (.5).

Color calibration collects non-tongue tissue throughout this larger crop. A marked
positive patch must contain only tongue. A component must connect to the central
inner-mouth region. Estimate its free end using distance through its mask, distal
shape separation, and a local front-edge fit. Shape ambiguity, clipping, short
extension, bad image evidence or a sudden unsupported jump gives an invalid tip.
The mouth attachment is a geometric cue, not an observed anatomical root. This is
an experimental 2D visible-tip estimate, not a guaranteed anatomical landmark or
3D tongue tracking. Never substitute the region centroid when tip estimation fails.

Emit each captured frame as before. Add `tongue_measurement: color_tip_mouth_width_v1`
and use `position_space: personal_tongue_tip_v1` in calibrated frames. Diagnostics
include raw tip X/Y, candidate-region center for debugging only, attachment cue,
quality/reason and mask. Candidate-present checks must count segmented regions
with rejected tips; an ambiguous region must not pass as tongue-absent.
Dark graph holds are display only; actual unknown tip values remain null/invalid.

Detector preset v5 identifies the new tongue measurement and saves only current
color parameters and tip ranges. v1-v4 profiles are validated, then their old tongue
appearance/range is discarded because the crop and measurement changed. Preserve
compatible eye/wink/head fits and explain tongue recalibration in the UI. Combined
profile format remains v3. New tip profiles require fresh absence/range checks on
load/restart. Live temporal history is never saved.

The lab must display the expanded mask, attachment marker, estimated tip marker,
raw tip graphs and personal positions. Calibration keeps the existing guided
center/four-direction/fresh-check flow. Synthetic elongated/curved/ambiguous masks
and generated images validate software behavior; real camera accuracy is pending.
