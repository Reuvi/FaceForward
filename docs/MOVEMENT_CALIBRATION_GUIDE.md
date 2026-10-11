# Head and tongue calibration, raw views, and the device boundary

> Current MVP: tongue has been removed from App and Vision lab. Use
> [App's current testing/profile guide](../App/README.md) and
> [pupil matrix testing](../docs/DIRECT_PUPIL_TESTING.md). Eyes and head axes remain;
> pupils are the pointer input, with no pupil calibration or sensitivity controls.
> Detector presets are v11; old tongue state is discarded on load. Any tongue
> setup, backend, recheck or mapping instructions below are historical.

Head X now has an independent yaw guide beside Head Y pitch. See
[horizontal head testing](HEAD_HORIZONTAL_TESTING.md) for current instructions
and detector preset v7. The vertical behavior below is preserved.

**Current camera update:** tongue uses local neural segmentation without background
capture or tissue clicks. A pupil-direction joystick and full-screen range guide
are also available. Follow [the tongue/pupil test guide](TONGUE_PUPIL_TESTING.md)
for current camera instructions, profile v6, model setup and limitations. Color
appearance instructions below now apply only to the legacy developer/synthetic
backend. Head pitch and the visible-boundary tip definition remain unchanged.


Use the same local Python/Tk App. **Vision source & raw signals** is the camera
setup tab. It now defaults to raw measurements and shows raw graphs before any
personal position calibration. **Detection calibration** uses that same capture
history; it does not start another detector or resample the data at UI speed.

From the repository root:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

For a synthetic exercise, use `--source detector-demo` instead, without model or
camera arguments. Generated input follows head/tongue guides automatically.
It also hides the tongue during an empty-mouth capture and shows it afterward
so you can freeze and mark the center patch. This is a wiring test, not ML accuracy.

## First inspect the camera tab

The **Raw measurements** panel and bottom graphs show:

| Raw measurement | Units and availability |
| --- | --- |
| Left/right eyelid gap / eye width | Dimensionless ratio; available before eye calibration |
| Head Y | Nodding pitch in degrees; no mode selection |
| Tongue front-edge midpoint X/Y | Signed mouth-width units about mouth midpoint; available after appearance training, before personal range calibration |
| Eye facial coefficients | Choose Left/Right facial features in the raw graph selector; same-side blink, squint, cheek and brow scores, 0–1 |

Tongue position cannot be measured before its appearance model exists. A blank
tip graph means unavailable, not centered. The candidate is experimental
color segmentation and can mistake similarly colored tissue for tongue.
Inspect the green mask, orange front boundary and cyan tip during calibration.
See [tongue-tip testing](TONGUE_TIP_TESTING.md) for detailed steps and rejection reasons.

The **Calibrated signals** subtab shows the actual SignalFrame values. These remain
unavailable until the relevant calibration is ready. Raw values and calibrated
values intentionally have different units; the labels separate them. Neither view
shows mouse speed, acceleration or screen position.

Both main tabs use the same workbench samples, sequence numbers and capture
timestamps. The displayed capture number identifies the current reading. Switch
tabs without resetting anything. The UI draws roughly ten times per second, but
the graphs retain every accepted captured sample from the last eight seconds.
The video preview is separately throttled; an image may be older than the current
numeric sample. A larger sample rate does not create extra calibration evidence
from duplicate timestamps.

## Calibrate vertical head movement

1. Open **Detection calibration → 2 Head Y**.
2. Keep the camera and your distance reasonably consistent. This guide always
   measures nodding pitch; it has no position/pitch selector.
3. Press **Start head pitch guide**. Follow neutral → comfortable up →
   comfortable down. Get into position during preparation and hold during capture.
4. Repeat the three positions for the fresh checks. These samples verify the fit;
   they do not change the learned references. The flow takes about 25 seconds
   with default preparation, capture and rest times.
5. Inspect the two bars: purple is pitch in degrees, scaled to your learned
   minimum/maximum; green is normalized position over the full 0–1 range. The
   orange line is the requested target during guidance. Your comfortable up limit
   maps to 0, neutral to .5, and down limit to 1, even when the raw pitch sign is
   reversed. The text below lists the actual learned angles and their outputs.

The two halves are normalized independently, so unequal up/down movement ranges
still reach both endpoints. For example, up −12°, neutral 4°, down 28° maps to
0, .5, 1; halfway angles −4° and 16° map to .25 and .75. Raw graphs retain degree
units and use the learned limits after calibration (before calibration: −45–45°).
Those initial display bounds never determine the normalized output.

Return to neutral repeatedly, then stop halfway toward each limit. Expect about
.25 and .75 at those halfway positions. Test comfortable motion while blinking and
speaking; record drift or unavailable readings. Head X is not implemented in this
mouse MVP. Image translation does not directly drive this pitch signal; pose
estimation can still drift with perspective, yaw, roll, blur or landmark errors.

## Calibrate tongue appearance and position

1. Open **Detection calibration → 3 Tongue**. Appearance controls scroll below the always-visible guide.
   Open your mouth with the tongue hidden, press **Capture background — tongue hidden**,
   and hold during its preparation/capture countdown.
2. Show your tongue, press **Freeze / retake tongue photo**, then click tissue wholly
   inside the tongue in the frozen crop. Avoid lips, teeth, gums and borders.
   The frozen image stays only in memory.
3. Press **Fit and inspect tongue color**. Inspect the live green candidate region:
   it should follow the visible tongue. If it follows other tissue, reset and
   recollect; a good-looking numerical position alone is insufficient.
4. Press **Start tongue position guide**. First hide the tongue with the mouth
   still open for the absence check. Then follow comfortable center → your left
   → your right → up → down, keeping mouth opening fairly steady.
5. Repeat those five positions for separate fresh checks. The 11-step guide takes
   as long as you need: each pose waits for **I'm in position — capture**. It stops with a reason if a
   collection or check fails. **Retry this pose** repeats only the failed pose,
   retaining the appearance model and preceding successful groups. If the absent
   check sees a green mask with the tongue hidden, recollect appearance instead.

The left position plane shows the **raw tongue tip in mouth widths**. Its purple rectangle is
the learned personal range once fitted. The right plane shows **personal position**,
with your learned neutral at (.5, .5). X increases toward your anatomical right;
Y increases down. The camera preview is unmirrored, so the displayed camera image
has the opposite horizontal appearance from this anatomical coordinate plot.
The orange circle is a requested calibration target, not a detection.

The visible front-boundary midpoint is estimated from the color mask in a padded
160×160 crop spanning 1.6 mouth widths. Both axes use mouth width; raw zero is the
mouth-corner midpoint, and the plot covers −.8 to +.8. The crop includes protrusion,
but lips covering the front, similar tissue colors, saliva/reflections, blur and
lighting can still cause misses or false tips. Comfortable positions must expose
a distinct, repeatable front edge. Unknown intervals hold the last plot position
in a darker color while the actual tongue signal stays null/invalid.

At every pose, first read the instruction and position your tongue comfortably,
then press **I'm in position — capture**. Hold through the capture countdown/tone,
relax during REST, and take your time preparing the next pose. The first pose needs
an open mouth with the tongue hidden. All following poses need the visible tongue
front past the lip. Left/right are YOUR sides; keep head still and the other tongue
axis near center. Checks repeat the same comfortable limits, not forced extremes.

**Reset tongue — start over** is always visible at the top. It also works during
tongue capture/position guidance or without a detected face. It clears background,
marks, model, range and checks; eye/head calibration remains. For a bad tissue click,
use **Clear tongue marks — keep background** instead. The yellow boxes mark your
actual clicks. Freezing another photo lets you add another view's tissue samples.
To redo all positions while keeping a good appearance model, use **Start tongue
position guide** again after a failure or Cancel. The live tip status beside the
guide explains missing detection without needing to scroll to the setup details.

## Inspect, retry, save

Below the position display, choose **Raw detector signals** or **Calibrated positions**
to inspect time traces. Raw graphs are the same renderer and capture rows as the
camera tab. Calibrated position traces use 0–1 and show no device transfer function.
Use **Export trace CSV** to save scalar measurements, confidence/validity,
calibration generation, raw candidate coordinates and personal positions.
No images are exported.

**Cancel** or leaving an active guide's tab cancels unfinished collection and
keeps preview stopped. Starting a new range calibration clears that channel's
previous range; completed unrelated eye/head/tongue fits remain. A brief face
loss during normal tracking preserves completed calibration. Rest/preparation
frames never train either range. Low tones mean rest, a rising pair means
prepare, three high tones mean capture, and success/retry have separate cues.
During rest, the guide title counts down and the next movement instruction stays
visible below it. Wait for the capture tones before holding that position.

Save using **Save active profile** in the camera tab. Detector preset v5 records
the color-tip measurement and its personal range; the enclosing
`face_mouse_profile_v3` is unchanged. v1-v4 detector files load compatible
eye/wink/head fits but discard old centroid-based tongue appearance/ranges.
Repeat both tongue appearance and position calibration for those files.
Saved **pitch** head fits remain compatible. Old **image-position** head fits
are removed on load, with a notice to run **Start head pitch guide**; compatible
eye/wink/tongue data follow their usual loading rules. A missing head mode in an
older file is treated as the old image-position default, never as degree data.

Loading works while stopped or without a face, and always leaves preview stopped.
After loading or restarting the source, use **Recheck saved tongue range**:
an absent check plus five position checks reuse the saved range without refitting
it. If these fail, recollect appearance/range under the current conditions.
Fits survive normal tab switches and brief motion/loss. Calibration files and
personal traces should remain in ignored local directories.

## Calibration rules and measurements

Head uses three robust reference groups. Tongue uses independent X and Y axis
fits from the five directional groups. Each axis maps linearly on either side of
the learned center, so unequal movement ranges on the two sides are supported.
Capture windows retain at most 512 distinct-timestamp samples. Training requires
at least `min_samples` usable frames and at least 80% availability.
Robust fitting rejects overlapping/unstable groups. Later position checks require
90% of captured samples to fall within `position_check_tolerance` of the requested
normalized target in every axis. Missing/out-of-range samples count as failures.
The tongue absence check permits at most 5% candidate detections in usable frames.
These are transparent MVP checks, not validated human accuracy claims.

| Setting | Default | Meaning |
| --- | --- | --- |
| `settle_ms` / `collect_ms` | 1000 / 1800 ms | Preparation and capture windows |
| `movement_rest_ms` | 1500 ms | Rest between movement steps |
| `min_samples` | 12 | Minimum usable distinct-timestamp samples |
| `head_pitch_separation` | 3° | Minimum adjacent pitch separation |
| `tongue_position_separation` | .04 | Minimum adjacent X/Y separation in mouth widths |
| `position_check_tolerance` | .2 | Maximum normalized error in a fresh target check |
| `endpoint_tolerance` | .05 | Small normalized overshoot clips to 0/1; larger overshoot is unavailable |

Advanced detector settings remain in **Settings**; applying the whole settings
JSON resets all fits. Head mode is fixed to pitch; starting its guide resets only
the head range and preserves eye/tongue fits. Legacy image-position settings are
accepted for file compatibility but cannot switch the live detector away from pitch.
These thresholds control calibration reliability; they are not mouse sensitivity,
dead zones, velocity or acceleration.

## General device workflow

```text
Camera frames
  → raw detector measurements + validity
  → personal calibration: positions and independent wink states
  → selected device's mappings and transfer functions
  → driver/emulator output
```

This increment implements the first two layers and their diagnostics. Calibration
describes the person and camera, so it can be reused by different device mappings.
For a mouse, later Processing work can turn head position into scroll velocity,
tongue position into relative pointer velocity, and wink samples into button
states. A future gamepad could map the same positions to joystick axes with its
own transfer settings. Selecting that device must select its mappings; it should
not redefine the raw signal or overwrite personal calibration.

The existing mouse preview remains available for regression testing, but no new
mouse transfer functions or real driver integration are added here.
See [the contract](../Contracts/MOVEMENT_CALIBRATION.md) for profile and signal semantics.

## Tongue research supplied during this work

The suggested pretrained segmentation model is a candidate for a separate detector
comparison; it is not running in this App yet. Its supplied 41.3 ms CPU inference
measurement excludes the rest of the pipeline and does not establish webcam
accuracy. See [the model evaluation plan](../Vision/TONGUE_MODEL_PLAN.md) for the
local integration design, crop/coordinate changes and concrete comparison metrics.
The current color mask remains visible so you can identify where it fails during
calibration instead of treating fitted positions as proof of detection quality.
