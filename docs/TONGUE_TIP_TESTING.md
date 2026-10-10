# Test the visible tongue tip

The current detector uses your calibrated tongue color and a geometric front-edge
estimate. The cyan point is the **middle of the visible front boundary**, where
tongue-colored tissue meets its surroundings. It is not the center of the whole
colored region. No pretrained tongue network is running.

## Open the native lab

From the repository root:

```bash
Vision/.venv/bin/python -m App --source camera \
  --model Vision/.local/face_landmarker.task --camera-id 0 --fps 30
```

For a software-only exercise, replace the camera arguments with
`--source detector-demo`. That synthetic face follows the position guide. It
checks wiring, not real tongue detection. The lab uses one capture worker and
the same samples across tabs. The simulated mouse remains downstream.

## Calibrate and inspect

1. Load your saved profile if you want to retain eye/head calibration. Older
   detector presets (v1–v4) require **new tongue appearance and range calibration**;
   their inner-mouth centroid measurements cannot be reused for the tip.
2. Open **Detection calibration → 3 Tongue**. Frame your face so the whole tongue
   and surrounding lips/chin fit in the camera image. Open your mouth with the
   tongue hidden. Press **Capture EMPTY open mouth** and hold for the capture.
   The larger crop now learns lips, surrounding skin, teeth and mouth interior
   as negative examples.
3. Show the tongue with its front end visible. Press **Freeze visible tongue**,
   then click an interior patch of tongue tissue, away from edges/lips/teeth.
   Press **Fit appearance model**. The preview returns to live video.
4. Inspect the crop before collecting a range. **Green** is the color mask,
   **orange** is the selected front boundary, **cyan** is its middle, and **purple**
   is the central-mouth attachment cue. The cyan point should sit on the front
   outline as you move. It should not slide into the body of the tongue. A mask
   on lips/gums requires resetting and recollecting appearance.
5. Press **Start tongue position guide**. Hide the tongue for the absence check,
   then follow center → your left → your right → up → down. Keep a comfortably
   visible front end throughout. Rest/prepare/capture prompts and tones are
   unchanged. Repeat the five positions for fresh checks.
6. Inspect the raw and personal position planes and time graphs. Return to center
   several times and try halfway positions. Save with **Save active profile**.
   New detector presets are v5 inside the same combined v3 profile. Loading or
   restarting requires **Recheck saved tongue range** before valid output.

If a guide fails, its reason identifies the failed step. Short, partly hidden or
ambiguous front ends are intentionally unavailable. Try a comfortable visible
extension, improve lighting, or recenter the camera. Do not force an uncomfortable
pose to make the calibration pass. **Reset tongue calibration** affects only
tongue appearance/range. Changing the entire Settings JSON resets all fits.

## What to measure

| Display/export | Meaning |
| --- | --- |
| Raw tip X/Y (`tongue_tip_x/y`) | Signed displacement from the mouth-corner midpoint, divided by mouth width on both axes; anatomical right +X, down +Y |
| Raw plot domain | −.8 to +.8 mouth widths on each axis; zero is the mouth midpoint, not necessarily your tongue's comfortable neutral |
| Personal X/Y (`tongue_x/y`) | Your calibrated comfortable endpoints 0/1 and neutral .5; positions, not mouse velocity |
| Region X/Y (`tongue_region_x/y`) | Color-region centroid, debug/export only; never substituted for an unavailable tip |
| `tongue_candidate_present` | A large color candidate exists, including candidates whose tip was rejected |
| `tongue_tip_extension` | Approximate distance through the mask from the central-mouth seed, in mouth widths; not physical tongue length |
| `tongue_quality` / `tongue_tip_reason` | Heuristic quality and geometric failure reason; quality is not a probability of anatomical correctness |
| `tongue_reason` | Final calibration/output availability reason |

The older diagnostic names `tongue_candidate_x/y` remain aliases for the **new raw
tip coordinates**. Check `tongue_measurement=color_tip_mouth_width_v1` when reading
CSV data; do not compare these values directly with old centroid traces.

Use the raw selector in **Vision source & raw signals**, or the raw graphs in
calibration. Both read the same capture rows. Unknown segments hold the previous
height in a darker color; actual tongue measurements remain null/invalid and do
not drive motion. Every capture still emits a sample. **Export trace CSV** includes
these diagnostics, capture timestamps, sequence and calibration generation; it
does not export images. Keep personal files in ignored `local-profiles/` or other
local storage outside Git.

Test steady center and endpoints, diagonals, a curved tongue, hiding/reappearing,
mouth-opening changes, talking, teeth/gums/lips without tongue, head motion,
lighting changes and a partly clipped tip. Record false candidates when absent,
valid-frame fraction when visible, tip jitter, direction errors and return-to-center
spread. Inspect the orange edge when a point looks wrong. A visible color boundary
alone is insufficient: a lip covering the tongue can create a false end.

## How the estimate works

`Vision/tongue.py` constructs a mouth-aligned 160×160 square spanning 1.6 mouth
widths. Both axes use mouth width, so vertical scale does not change solely from
mouth opening. The crop includes protrusion beyond the lips. The existing local
weighted-Lab color prototypes produce the mask; no new dependencies or inference
worker are added.

`Vision/tongue_tip.py` requires a component attached to the central inner-mouth
region, then grows an eight-neighbor distance wave through that component. A
unique distal region identifies the possible free end. The distance search is
capped at 320 steps so excessively winding masks cannot monopolize the worker. A nearby body section
estimates its local direction, including curves. The algorithm selects a short
front contour, fits a quadratic to smooth pixel stair-steps, and evaluates its
transverse middle, then anchors that fit to the nearest observed front-boundary
pixel. That is the orange boundary's cyan midpoint. The attachment
cue is geometric; the camera does not observe the anatomical root.

Clipping, insufficient extension, competing fronts, disconnected tissue, irregular
or concave edges and unsupported fits produce unknown. A sudden displacement
larger than `.12 + tongue_tip_max_speed × dt_seconds` also rejects that capture
and clears temporal history. A subsequent independently supported edge can be
accepted immediately. This continuity check is not a dwell timer or a tracker
that can establish tongue identity. Missing evidence/source loss clears history.

| Advanced setting | Default | Units |
| --- | --- | --- |
| `tongue_tip_min_extension` | .10 | Minimum mask-distance extension, mouth widths |
| `tongue_tip_fit_error` | .025 | Maximum front-boundary RMS fit error, mouth widths |
| `tongue_tip_max_speed` | 6 | Continuity allowance, mouth widths/second, plus .12 fixed allowance |
| `tongue_min_area` | .025 | Minimum candidate fraction of the expanded crop |

The algorithm is experimental. Matching lip/gum colors, occlusion, blur,
perspective and a tongue pointing toward the camera can defeat the shape cues.
Synthetic boundary tests establish software behavior, not human accuracy. Test
the masks and raw tip before tuning mouse transfer functions. See the
[measurement contract](../Contracts/TONGUE_TIP.md) and
[general movement guide](MOVEMENT_CALIBRATION_GUIDE.md).

## Verification recorded for this change

246 automated tests passed, including synthetic front-edge geometry, calibration,
profile migration, shared traces and native Tk checks. The 490-frame headless mouse
exercise observed all four behaviors and released at EOF. On this machine,
`Vision.benchmark_detection --frames 500` measured 6.24 ms mean / 7.09 ms p95 for
selected-face features plus crop/color/tip processing on a repeated synthetic
image. Capture, MediaPipe, tracking, frame construction, UI and OS output are
excluded; measure live end-to-end latency separately.
