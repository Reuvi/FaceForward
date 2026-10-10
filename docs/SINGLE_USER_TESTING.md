# Single-user calibration: testing and lifecycle

Current head/tongue update: use the [movement calibration guide](MOVEMENT_CALIBRATION_GUIDE.md)
for guided position fitting, raw graphs on camera setup and shared capture data.
Detector presets are now v4 (combined profiles remain v3). Saved tongue ranges
require **Recheck saved tongue range** after loading/restarting; older presets
without ranges need the new tongue guide. Eye classification is unchanged.


The calibrated camera and detector demo now assume **one person**. The app uses
the logical subject `single-user`; geometric tracking IDs no longer decide which
calibration to keep. MediaPipe requests one face per inference. This is not face
recognition: if a different person uses the camera, load their saved profile or
reset and recalibrate. Legacy NDJSON replay still has its own subject selector.

## Test in the native app

From the repository root:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --fps 30
```

1. On **Vision source & raw signals**, your face connects automatically. There is
   no camera subject selector. Open **Detection calibration → 1 Eyes** and run the
   guide, or use **Load saved profile** on the source tab to choose an existing JSON.
2. Watch each eye's fit and open/closed scope. Turn or move your head, briefly move
   outside the camera view, and return. Completed calibration should remain present
   and detection should resume without selecting a new face or recalibrating.
3. During unknown captures, each eye input holds its previous number with
   `known=false`. The raw observation remains unavailable; the scope keeps a darker
   horizontal hold. Unknown data never counts toward a wink or calibration.
4. If testing the simulated mouse, loss releases buttons and stops preview.
   After returning, press **Start preview**, open your eyes and center the inputs
   before trying another wink. Reacquisition does not automatically rearm controls.
5. Choose **Save active profile**, name a JSON (normally under `local-profiles/`),
   then **Stop source**. Fits remain visible and can still be saved or loaded.
   **Start source** with the same source mode should keep the calibration.
6. To test recovery across app launches, save, close the app, reopen with the matching
   source, and choose **Load saved profile**. Loading works even if your face is not
   yet visible or you have stopped capture. The next usable frames use those fits.

For a camera-free check, substitute `--source detector-demo` with no model argument.
The generated face follows the eye guide automatically. Its profiles are marked
synthetic and cannot be loaded into live camera mode.

## What survives

| Event | Completed detector/wink fits | Active capture and preview |
| --- | --- | --- |
| Large geometric movement, face still usable | Kept | Normal detection continues |
| Missing face, stale capture or invalid frame | Kept | Capture cancelled; output paused/released |
| Face returns | Kept; automatically reused | Detection resumes; preview needs Start |
| Stop / same-source restart | Kept | Unfinished work cancelled; fresh tongue validation needed on restart |
| Load saved JSON | Replaced by file contents | Disarmed; fresh tongue/gaze checks needed |
| Switch source kind / apply detector Settings | Cleared in memory | Recalibrate or load matching profile |
| Settings → Reset all calibration | Cleared in memory; saved files unchanged | Recalibrate or load a profile |
| Close application | Memory ends; saved files remain | Load a saved profile on next launch |

Starting a new eye calibration deliberately replaces the eye fits; if interrupted,
restart that guide. Unrelated completed head/tongue fits remain. An aborted partial
calibration is never silently completed using later frames.

## Engineering details

`Vision/workbench.py` validates capture ordering through the existing pipeline,
then assigns the sole observation to a stable operator slot. It separates completed
fits from current face/measurement/capture state. Disconnect no longer erases fits;
explicit reset and profile replacement do. Injected multi-face frames are unavailable.

`App/mouse_runtime.py` passes that stable ID to Processing, binds saved-profile status
to source mode and calibration generation, and disarms on capture loss/gaps/restart.
`ResearchSession.restart_source` retains learned parameters and completed trials,
but resets live gesture/eye state and invalidates pending fitting results and gaze
validation. Stream session IDs still change on restart; samples keep real timestamps.

Profiles retain existing v1/v2 compatibility. They store settings and fitted
parameters, not camera images, tracker IDs, active gestures or validation pass flags.
They are local files, saved atomically and excluded from Git. No driver protocol,
transfer-function math, eye polarity, or independent-eye policy changed.

Automated regression checks use generated pixels/landmarks to cover large box jumps,
loss/recovery, held unknowns, safe rearming, stale gaps, interrupted calibration,
restart, source changes, and saved-file loading before any capture. They establish
lifecycle behavior, not real-person recognition accuracy; use the camera steps above
to evaluate your own calibration.

For the current blink/wink training sequence and saved v3 models, use the
[eye calibration guide](EYE_CALIBRATION_GUIDE.md). Detection research is no longer
in the app; independent wink models share this same single-user lifecycle.
