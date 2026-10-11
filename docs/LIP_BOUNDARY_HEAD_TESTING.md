# Lip-boundary tongue detection and Head X recovery

> Current MVP: tongue has been removed from App and Vision lab. Use
> [App's current testing/profile guide](../App/README.md) and
> [pupil matrix testing](../docs/DIRECT_PUPIL_TESTING.md). Eyes and head axes remain;
> pupils are the pointer input, with no pupil calibration or sensitivity controls.
> Detector presets are v11; old tongue state is discarded on load. Any tongue
> setup, backend, recheck or mapping instructions below are historical.

Current change: detector presets v9 (`lip-boundary-head-reliability-v9`), combined
profiles v3. Native Python/Tk only. Head X **keeps its calibration**. Head Y,
independent eye/wink behavior, direct MediaPipe pupils and mouse mappings retain
their existing implementations. Restart App to use the changes:

```sh
Vision/.venv/bin/python -m App --source camera --model Vision/.local/face_landmarker.task
```

Load your saved profile to restore compatible eye/wink/head/pupil settings.
Older ONNX tongue profiles switch to the new built-in detector and discard their
incompatible tongue range. New v9 profiles remember an explicit backend choice.
No tongue weights or ONNX inference are needed for the default camera backend.

## Test Head X first

1. On **Vision source & raw signals**, turn slowly left/right. Watch raw yaw and
   the face outline. Both must remain visible for a usable measurement. The Head X
   status now distinguishes calibrated-limit saturation from actual missing input.
2. In **Detection calibration → 3 Head X**, load a working fit or press
   **Start head yaw guide**. Use neutral, then small comfortable left/right turns
   (roughly 10–20 degrees). Keep both eyes visible. Do not turn toward a shoulder.
   The guide supplies preparation, capture and rest cues and repeats fresh checks.
3. A failed pose offers **Retry this pose**. It keeps good captures, so repeat only
   the failed pose and remaining checks. Starting, cancelling or failing a retry
   retains the last completed Head X fit; only a successful guide replaces it.
   **Reset Head X only** explicitly clears it. Head Y is independent.
4. Once passed, left = 0, neutral = .5, right = 1, including unequal or reversed
   raw-angle ranges. Turn slightly beyond a learned endpoint while staying visible:
   normalized X stays at 0 or 1 and reports **tracking remains valid**.
5. Move briefly out of view or cover the face, then return. Genuine missing yaw
   stays unavailable and plots hold the previous position in a darker color.
   The saved calibration survives; fresh yaw resumes without retraining. Mouse
   preview stays stopped until explicitly started again.
6. Compare the same raw/normalized trace across tabs and export CSV. Inspect
   `head_x_raw`, `head_x_quality`, `head_x_reason`, `head_x_saturated`, `head_x`,
   `head_x_valid`, capture sequence and timestamp. Raw yaw uses degrees.

The lab uses experimental MediaPipe face-presence and tracking confidence floors
of .35 (formerly .5); initial face detection remains .5. They appear as
`face_presence_floor` and `face_tracking_floor` in calibration diagnostics.
This allows lower-confidence tracked faces through MediaPipe, but can also admit
less reliable geometry. Existing image-quality/pose checks still apply. These
settings are not a measured accuracy improvement, cannot recover hidden facial
features or severe motion blur, and never substitute held values for real poses.
Generic non-lab detector defaults stay .5. If raw yaw still drops, report whether
its reason is missing pose, poor sharpness/lighting, or no face; calibration alone
cannot fix those cases.

## Inspect tongue detection before learning its range

1. Open **Detection calibration → 4 Tongue**. The default is **Lip-boundary color
   extension · experimental**. If comparing with an old backend, press
   **Use lip-boundary color detection**. Switching stops preview and clears only
   tongue range/checks; eye/head/pupil fits stay intact.
2. Keep your tongue hidden. The **blue outline** should follow the outer lips.
   Open/close your mouth, smile and talk. There should be no accepted green region
   extending beyond the outline. This is the first check in the position guide.
3. Show the tongue beyond a lip. **Green** marks selected exterior color;
   **orange** marks its outer front; **cyan** marks the middle of that front;
   **purple** marks the attachment estimate near the lip. The cyan point is on
   the front boundary, not the region's center of mass.
4. Move slowly to your left, right, up and down. Each visible pose needs some
   tongue color extending outside the outer-lip outline. Movement entirely inside
   the mouth is deliberately unavailable. Keep the head still and the lip outline
   accurate. Try even lighting and a slightly different distance if contrast or
   the outline is poor. Read the rejection reason below the crop.
5. The raw position plots work immediately; normalized joystick values require
   the position guide. Both tabs read the same camera captures. Delayed tongue
   overlays always use their original mouth crop, never a newer camera image.

This is a color-extension proxy, not a trained anatomical tongue recognizer.
Makeup, similar-colored objects touching the lips, shadows and unusual lighting
can fool it. If green appears with tongue hidden, do not train around that false
candidate. Adjust the scene or use the explicit ONNX comparison. There is no
silent backend fallback when detection fails.

## Learn and check the tongue joystick

1. Press **Start tongue position guide**. Hide the tongue for the initial absence
   capture. Follow rest/preparation cues; each pose waits for
   **I'm in position — capture** before collecting samples.
2. Show a comfortable central extension, then your left/right/up/down limits.
   Keep the visible colored front beyond a lip, your head still, and the other
   axis near its center. For the up pose, raise the visible front from its center height while
   keeping a visible extension beyond a lip. Avoid maximum strain.
3. Repeat the five fresh check poses. On failure use **Retry this pose**; read the
   reason instead of restarting unrelated calibrations. **Reset tongue — start
   over** cancels tongue work and clears its range, retaining the current backend.
   No background photo, tissue click or pixel-recall training is used here.
4. After success, check center (.5,.5), left X=0, right X=1, up Y=0, down Y=1.
   Camera view is unmirrored; instructions refer to your own body. Raw X/Y are
   mouth widths with origin between the corners; personal axes are 0–1.
5. Save the active profile. Loading/restarting retains the range but requires
   **Recheck saved tongue range** with new hidden/visible evidence. Loading never
   re-arms the mouse. An old range cannot validate a new backend automatically.
6. Only after the raw detection looks consistent, choose **Tongue tip** under
   **Pointer joystick input**, then test the simulated cursor in **Live lab**.
   Head Y remains vertical scroll. Head X has no new device mapping in this change.
   The real OS mouse driver integration remains separate.

For the optional neural comparison, **Compare: load local ONNX tongue model…**
accepts the existing pinned `tongue_seg.onnx`; see
[model setup/license](../Vision/TONGUE_MODEL_NOTICE.md). It has independent
range calibration because its mask and coordinate measurement differ.

## Engineering details

MediaPipe supplies its ordered outer lip ring and a mouth-aligned 160×160 crop
covering 1.6 mouth widths. Outer-lip orientation permits a closed inner mouth for
absence checks. Every color inference:

- Measures median nearby skin and lip color in LAB chroma. Low contrast or missing
  references marks the observation unavailable, so it cannot pass absence checks.
- Selects tissue-like chroma beyond a small expanded lip margin. Requires a
  sufficiently large connected region that touches the lip rim; rejects detached
  patches, competing extensions, multiple fronts and crop-edge clipping.
- Uses the most exterior contour band, measures its transverse midpoint and picks
  an actual supported boundary point. The region centroid is diagnostic only.
- Applies the existing timestamp-based extreme-jump rejection and supplies a
  heuristic quality score. This score is not a calibrated probability.

Constants in `Vision/lip_boundary.py` are experimental: reference contrast ≥6 LAB
chroma units; color distance >max(8, 2.5×local variation); exterior border ~.02 mouth
widths (minimum 2 px); attachment rim .08; area ≥.004 mouth-width²; extension ≥.055
mouth widths. Ambiguity and temporal jump settings use existing detector config.
Personal normalized positions use the existing piecewise axis fits and fresh
validation; device dead zones, acceleration and smoothing remain downstream.

Measurement identity: `lip_color_extension_mouth_width_v1`; built-in algorithm:
`lip-color-extension-v1`. Preset v9 stores this identity instead of a model hash;
explicit neural v9 profiles retain their pinned model hash. v1–v8 fully validate
before migration. Compatible eye/wink/head fits and direct pupil settings survive.

The bounded tongue process has one in-flight job, one replaceable pending job and
one latest reply. It carries the original session, sequence, timestamp, crop and
calibration generation. The face/camera loop never waits for tongue completion.
Each fast capture still emits its own eye/head/pupil sample; tongue retains its
separate sample origin and stale-result gates. This isolates model stalls, though
shared CPU load can still affect measured FPS. Check actual face sample rate,
tongue completion rate/age and inference time in the lab. No artificial FPS claim
is made. See [independent scheduling](INDEPENDENT_DETECTOR_TESTING.md).

## Developer verification

```sh
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_lip_boundary.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_lip_boundary.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_horizontal_head.py -v
```

Generated fixtures cover directions, outer-boundary placement, bad color/geometry,
ambiguity, clipping, missing evidence, independent scheduling and capture-origin
overlays. Profile migration, calibration retry, endpoint saturation and raw-loss
handling are covered through App. Local-model smoke checks use generated/blank
images; no user camera, recordings or personal profiles are required. Human-camera
accuracy and the usable range still require the live checks above.

Verification completed for this change: 139 Vision cases, 104 integration cases
including native Tk, and 75 Processing cases (318 total). The Vision full run
contained 138 cases; the additional color-guide case passed in its focused module.
The integration full run exposed one test-only Tcl-state comparison; after fixing
that assertion, all five tests in the affected module passed. The 490-frame mouse
demo accepted every frame, observed all four actions, and ended stopped/released.
Ruff F, whitespace and integration scope checks passed.
