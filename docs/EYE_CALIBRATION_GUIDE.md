# Eye geometry and short wink-action calibration

The native app learns two independent things: eye open/closed geometry, then the
facial appearance you use for a closed-eye action. The action guide no longer
collects or counts natural blinks or tries to distinguish their intent. A natural
blink may activate if it matches your learned action. Each eye remains independent.

## Start

From the repository root:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

For a software-only check, use `--source detector-demo` without camera/model flags.
Its generated face follows the prompts; this is not a test of real-person accuracy.

1. Confirm the camera is running in **Vision source & raw signals**. The sole face
   attaches automatically. The preview is unmirrored: your left eye appears on the
   image's right.
2. Open **Detection calibration → 1 Eyes**. If good eye geometry is already loaded,
   skip directly to **Start wink action**.
3. Otherwise use **Start eye open/closed**. Follow the dot with comfortably open
   eyes, gently close when prompted, then reopen. This unchanged seven-step guide
   checks open poses and establishes each eye's open/closed range. The popup closes.
   You can save this geometry before continuing.
4. Press **Start wink action**. Its first pass has just three poses: comfortably
   open → your left closed-eye action → your right closed-eye action. Use the
   movement you actually want to use; no exaggerated squint or blink comparison
   is required. Hold the named pose during capture, then relax at the rest tone.
5. Repeat those three poses once for a fresh check. Check captures do not retrain
   the model. With only one calibrated eye, the guide skips the other side.
6. The popup closes. Read each eye's result and test the scopes.

The action guide has **six captures, about 32 seconds** with default 1-second
preparation, 1.8-second capture and 3-second rests. One eye uses four captures.
**Rest between steps** stays adjustable. These durations schedule calibration
samples; there is no minimum runtime wink hold time, release delay or cooldown.

## Cues, retry and saving

Four low tones mean REST. The large countdown and **Next:** instruction stay
visible together. No rest/preparation frames enter training. A rising pair means
prepare, three high tones mean capture. The geometry guide has separate close and
reopen tones. Completion/retry also have distinct cues.

**Escape/Cancel** stops the active guide. **Restart wink action** clears only the
wink models/training, preserving completed eye geometry, head and tongue fits.
**Restart eye open/closed** clears geometry and its dependent wink models.
Loading or starting a guide leaves the mouse preview stopped.

Use **Save active profile** on the source tab to keep detector fits with mouse
settings. Geometry-only profiles work. Detector preset v5 / combined profile v3
remain compatible: old appearance models still load, but use the new short guide
if their recognition was poor. No video or calibration images are saved in a profile.

## Verify the live signals

The anatomical scope shows **1 closed, 0 open**. **Wink samples** shows the
closed-eye action: **1** requires valid closed geometry and a matching appearance;
**0** means open or a supported closed non-match. Uncertain geometry, unsupported
appearance or missing evidence is unknown. A strong appearance score cannot turn
an uncertain/open eye into an action.

| Try | Expected |
| --- | --- |
| Comfortable open eyes | Anatomical closed bits and action bits are 0 |
| Left action held, then reopen | Left action is 1 while recognized, then 0 |
| Right action held, then reopen | Right action responds independently |
| Both learned actions together | Each eye may be on; neither gates the other |
| Missing/covered eye | Dark held graph value, unknown sample; affected output releases |
| Natural blink | No separate blink label or guaranteed rejection; observe whether it matches the action |

Select **Left/Right facial features** or **Eye ratios** to inspect the evidence.
The `blink` feature name means MediaPipe's eye-closure coefficient; it is not a
natural-blink classification. The model score is a decision score, not a verified
probability or measurement of intent.

Every accepted camera capture still sends a sample. Unknown plots hold the previous
height in a darker color. Processing also holds the previous numeric eye input
with `known=false` (startup 0), while releasing actual output. After unknown or
arming, a fresh anatomical open sample re-arms that eye; a closed non-action does
not re-arm it. Independent source freshness/watchdogs still apply.

## What is learned

Each eye uses its own lid gap/eye width, eye-closure/squint/cheek/brow/wide
coefficients and brow/cheek landmark distances normalized by eye width. These
are visible shape measurements, not direct muscle activity. A small local linear
classifier learns open versus closed action. Valid open frames alone label the
open prompt; valid closed frames alone label the action prompt. No open-to-closed
transition count, opposite-eye feature, closure duration or blink comparison is
required. Starting a hold before capture does not invalidate it.

Each prompt needs clear, distinct-timestamp samples. Separate check windows must
recognize at least 90% of action frames and 80% of open frames with no false action
in the open check. An unreliable eye fails independently. Rejected windows explain
missing evidence, too few matching open/closed frames or overlapping appearances.
These small calibration checks establish software behavior, not broad human accuracy.

For head and tongue, use [the movement guide](MOVEMENT_CALIBRATION_GUIDE.md).
