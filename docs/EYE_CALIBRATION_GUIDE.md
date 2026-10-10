# Eye calibration and testing

Current head/tongue update: use the [movement calibration guide](MOVEMENT_CALIBRATION_GUIDE.md)
for guided position fitting, raw graphs on camera setup and shared capture data.
Detector presets are now v5 (combined profiles remain v3). The
[tongue-tip guide](TONGUE_TIP_TESTING.md) covers the new visible front-boundary
measurement. v1-v4 tongue appearance/ranges require retraining; compatible
eye/wink/head fits survive. Saved v5 tongue ranges require **Recheck saved tongue
range** after loading/restarting. Eye classification is unchanged.


This is the current eye workflow in the local Python/Tk App. The separate
Detection research tab has been removed. Two separately started guides learn
eye open/closed geometry, then natural blinks versus intentional winks. The second
stage can fail, be cancelled or restarted without repeating the first. Both stages
include fresh checks. Existing saved eye geometry can seed blink/wink training.
An intentional wink produces **1 while held**, and reopening produces **0**.
A recognized natural blink stays **0**. There is no minimum wink duration,
release delay, cooldown or opposite-eye gate in this calibrated camera path.
Both intentional winks may be on together; neither eye requires the other to open.

## Start

From the repository root:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

For a camera-free wiring check, substitute `--source detector-demo` and omit the
model/camera arguments. Its generated face follows the guide automatically.
It verifies the software connection, not accuracy on a real person.

1. In **Vision source & raw signals**, confirm the camera is running and
   **single-user** is attached. The preview is unmirrored: your left eye is on
   the image's right.
2. Open **Detection calibration → 1 Eyes**. Set **Rest between steps** (default
   3 seconds), try **Test sound**, then press **Start eye open/closed**.
3. A temporary full-screen window opens. Follow the dot with comfortably open
   eyes at five positions, gently close both eyes when instructed, then reopen.
   This establishes a separate open/closed geometry range for each eye and checks
   reopening on new frames. The popup closes. You may save this geometry-only
   profile with **Save active profile** before continuing.
4. Press **Start blinks & winks**. Follow the **Learn blink/wink** prompts: blink gently several times, then
   keep a relaxed face while smiling/talking/looking slightly around. Perform
   three separate left winks and three right winks when prompted.
5. Follow **Check on new movements**: repeat natural blinks and relaxed movements,
   then two new winks on each side. These frames test the fitted model; they do
   not train or adjust it.
6. The popup closes automatically. Read each eye's result and inspect its scopes.
   Only an eye that passes is enabled for wink recognition.

The first guide has seven steps (about 40 seconds); the second has fourteen
(about two minutes), including rests at default timings. They do not start each
other automatically. The blink/wink button requires at least one completed eye
geometry fit. Each eye remains independently enabled only when its checks pass.
During each wink prompt, begin with both eyes open, wait for the three high
capture tones, wink the named eye once, briefly hold, then reopen naturally
within that capture window. Holding briefly provides several training images;
there is no runtime minimum hold time. Natural-blink windows need at least
three observed blinks in training and two in checking. Do not force or exaggerate
these blinks to imitate a wink.

Four low tones mean **REST**: blink or relax freely; nothing is collected. A large
central countdown shows the seconds left, with **Next:** and the upcoming movement
directly beneath it. Read that instruction while resting; wait for preparation
and capture cues before doing it. The same countdown also appears in the lab panel.
A rising pair means prepare; three high tones mean capture. The geometry phase's
descending cue means close gently, and two high tones mean reopen. Completion
and retry have distinct cues. Read the next movement during preparation; the
timer starts only after its instruction is displayed. Capture continues while
resting, but rest/preparation images never enter training. Preview stays stopped.
Escape/Cancel exits the active guide. If blink training went wrong, press
**Restart blinks & winks**: it clears only wink models/training and keeps completed
eye geometry, head and tongue fits. Cancel or face loss during that stage also
keeps eye geometry. Failed wink models stay unavailable until their checks pass.
**Restart eye open/closed** is for bad geometry; it clears both geometry and the
wink models that depend on it. Cancelling incomplete geometry does not promote
provisional fits before the fresh reopen check. Head/tongue fits remain.
Both start actions stop preview and reset the Processing eye-input history.

## Verify before enabling preview

The top scope shows anatomical eyelids: **1 closed, 0 open**. The lower scope
defaults to **Wink samples**: **1 intentional wink, 0 open or recognized blink**.
Use its selector for **Left/Right facial features** or **Eye ratios**. Facial
graphs show blink, squint, cheek, brow and the learned wink score over eight
seconds. The score is a model decision score, not a calibrated probability.

| Try | Expected |
| --- | --- |
| Several comfortable natural blinks | Eyelid traces pulse to 1; wink samples remain 0 |
| Left wink, then reopen | Left wink becomes 1 while held, then 0; right stays independent |
| Right wink, then reopen | Same behavior for the right eye |
| Smile, speak and look around normally | No accidental wink ON samples |
| Briefly cover one eye or leave the image | Unavailable readings are dark, and affected output releases |

Repeat these checks beyond the guided samples. A passed guide is only a small
personal calibration check, not evidence of general accuracy. If blinks trigger
ON, use **Restart blinks & winks** and repeat with comfortable, representative movements and clear
lighting. If the appearances cannot be separated reliably, the eye should remain
unavailable. Do not compensate by exaggerating movements beyond comfort.

Unknown graphs hold the preceding height in a darker version of their color.
Processing also records the previous numeric eye input for every unknown capture,
with **known=false** (startup value 0). This never holds the actual mouse button:
unknown releases the affected output. After arming or unknown, an actual observed
open eye is needed before that eye can activate again. A recognized blink's OFF
state alone does not count as reopening. Total face loss/staleness stops preview;
returning to the camera retains calibration but does not re-arm.

When ready, open your eyes, go to **Live lab**, and press **Start preview**.
Wink samples drive the existing simulated buttons directly. Holding does not
generate repeated presses. This app still does not inject OS mouse input.
Head/scroll and tongue/pointer behavior are unchanged; test them separately later.

**Export trace CSV** stores captured scalar samples, including raw lid ratios,
all eight model features, wink score/bit and capture timestamps, without images.
The display uses interpolation for continuous features and steps for binary
signals; classification uses actual captured frames only. Keep personal traces
and profiles in ignored local directories.

## What is learned

Each eye has a small independent logistic classifier with eight inputs:

| Feature | Measurement |
| --- | --- |
| `lid_ratio` | Vertical eyelid gap divided by eye width; dimensionless |
| `blink`, `squint`, `cheek`, `brow`, `wide` | Same-side MediaPipe eyeBlink, eyeSquint, cheekSquint, browDown and eyeWide scores, 0–1 |
| `brow_gap`, `cheek_gap` | Landmark distance from the eye-corner midpoint divided by eye width; dimensionless |

These are visible shape estimates, not measured muscle force or proof of intent.
No duration, closing speed, frame count, opposite-eye measurement or clock value
is a classifier input. The two eyes can have different baselines and models.
Open/closed geometry and all feature scales are personalized.

The guide labels only closed portions of blink/wink attempts; open surrounding
frames are not labeled winks. Each blink/wink window must contain observed open
to closed transitions, adequate sample counts, and at least 80% available feature
frames. Training uses equal class and prompt weights, a regularized linear model,
300 bounded optimization steps, and at most 512 feature vectors per eye/window.
The decision bands are fitted only on training windows. A surrounding-eye difference from closed natural blinks is required; differences
from relaxed open eyes alone do not qualify. Overlapping patterns
fail training instead of being forced into ON/OFF. Unsupported feature ranges
or scores between the two decision bounds are unknown.

The later check requires no false ON frames in either negative window, at least
90% recognized wink frames in **each** wink attempt, and at least 80% recognized
OFF frames in **each** negative window. Unknown counts against recognition.
These are MVP acceptance rules, not clinically validated accuracy requirements.
The small test set cannot exclude rare false activations. A frame-only model
cannot distinguish intentions that look identical; do not claim it can.

## Save, load and maintain

Use **Save active profile**, then **Load saved profile** in the source tab.
Completed models survive head motion, temporary loss and same-source restarts.
Files can load while stopped or without a face; loading leaves preview stopped.
New files use `face_mouse_profile_v3` and detector preset v5, storing per-eye
geometry, model parameters and check counts, with Processing/head/tongue settings.
They contain no images or raw training vectors. A geometry-only profile is valid;
load it and start Blinks & winks without repeating the dot guide. Recheck under
current lighting.
Tongue validation still has to be repeated after loading.

Old v1/v2 profiles remain readable, but they have no per-frame wink models.
They restore their other settings; run the new eye guide before using wink
buttons. Old research event models are not used. Legacy raw/mock/replay inputs
without `eye_intent` retain their old Processing dwell behavior for compatibility;
those timing controls are hidden in the unified App.

Implementation: `Vision/wink_guide.py` owns the sequence, `wink_model.py` owns
features/training/checking, `workbench.py` emits a sample per capture, and
`Processing/mouse/signals.py` and `engine.py` consume those states.
The additive [eye intent contract](../Contracts/EYE_INTENT.md) preserves the
raw SignalFrame eye meaning and the existing driver serialization boundary.
