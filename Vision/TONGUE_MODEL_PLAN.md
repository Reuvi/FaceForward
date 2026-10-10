# Tongue segmentation research: decision and evaluation plan

The supplied research is useful for the next detector iteration. **The current
App still uses local color segmentation; no pretrained tongue model is installed
or active in this calibration increment.** Head/tongue range calibration and the
shared raw views are implemented independently of a future semantic detector.
Do not describe a successful calibration or a synthetic test as tongue accuracy.

## What the current detector can and cannot measure

`mouth_crop()` in `tongue.py` warps the inner mouth to 128×96 and masks an eroded
inner-lip polygon. `TongueModel.detect()` selects a color component and reports
its centroid. That means:

- Protruding tissue outside the lips is excluded, even if clearly visible on camera.
- Centroid motion is not tongue-tip motion; changing the visible tissue changes it.
- Raw Y is divided by the current mouth opening, so opening the mouth changes Y.
- A matching gum/lip patch can pass color gates. Personal range calibration cannot
  fix an incorrect mask; inspect the candidate before starting the range guide.

The new guide learns comfortable ranges of this specific measurement. Raw candidate
coordinates remain visible before range fitting. Null/invalid stays null/invalid;
darker plot holds are display only. The earlier eye previous-input policy does not
turn missing tongue detections into held control input.

## First learned model to evaluate

The [tongue-trained YOLOv8n-seg release](https://github.com/zzqsld/zzqsld-tongue-analysis-api/releases/tag/v3.0)
supplies a local ONNX segmentation model. Its masks make it a useful candidate for
comparison with the color baseline. The release describes a tongue-photo dataset;
its reported validation result does not establish continuous webcam performance.
The weights carry CC BY-NC 4.0 terms. Record model provenance and license with any
future distribution; this change does not bundle those weights or copy its code.

The provided research worktree benchmark was inspected, not rerun here. On its
Apple M3 Max, ONNX Runtime 1.31.0 CPU, four threads, 10 warmups and 100 synthetic
inferences, the 640×640 model took median 41.273 ms / p95 41.743 ms. This excludes
camera capture, MediaPipe, crop preparation, mask decoding and UI. It already
exceeds a 33.3 ms budget for 30 captured frames per second. A small mouth crop alone
does not reduce inference cost if it is still resized to the fixed 640×640 input.
The tested file was 13,287,587 bytes, SHA256
`885ecd06ec97fee5ed3959c85590c7a3dc3d10f134c7dc821c3b99f45506c35e`.
Treat these as inherited speed measurements, not a current end-to-end benchmark.

The supplied Babble comparison returns expression coefficients rather than a mask.
Those could be future alternate inputs, but must not be presented as measured tongue
X/Y. The [ALS segmentation paper](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2022.838191/full)
is supporting research for segmentation feasibility; recorded clinical tongue
movements are a different evaluation task from continuous pointer control.

## Integration design for the next increment

1. Reuse App's existing camera frame and landmarks. Add a selectable local
   segmentation backend, with the color baseline still available. Load only an
   explicit local model path; no runtime downloads or network inference.
2. Define a padded, rotated mouth crop that includes comfortable protrusion.
   Decode and display the actual mask, model score, area and failure reason.
   Missing/ambiguous/out-of-frame masks remain invalid. Do not fabricate a centered
   point or silently fall back to a color candidate after model failure.
3. Keep the initial learned measurement a centroid. Evaluate mouth-width scaling
   on both axes to reduce mouth-opening dependence; this is a new coordinate space,
   not a silent change to the current mouth-height-normalized raw Y.
4. Version and persist the backend, model hash, coordinate space and fitted range
   together. Changing any of them invalidates tongue calibration only. Old color
   ranges must never be reused for a different mask or coordinate system. Update
   `Contracts/MOVEMENT_CALIBRATION.md` before implementing that change.
5. Keep inference off Tk and use bounded work. Every camera capture still emits
   its complete SignalFrame. If tongue inference cannot run for that capture,
   mark tongue unavailable for that capture, with the reason/timestamp; never
   repeat an older inference as new evidence. Measure the resulting availability
   before choosing a slower tongue cadence. Optimize or re-export a smaller model
   only with accuracy and end-to-end latency comparisons.
6. Feed eligible new measurements into the same position guide, raw graphs,
   profile lifecycle and validity rules. Device-specific mouse transfer functions
   and the driver's format stay downstream.

## Comparison protocol

Keep recordings and profiles local and opt-in. Use the same camera framing,
lighting, masks and frame timestamps for both detector comparisons. Test tongue
hidden, teeth/gums visible, talking, smiling, neutral holds, left/right/up/down,
diagonals, changing mouth opening, partial protrusion, head motion and blur.
Include changed lighting/distance and entirely separate recording sessions.

Measure candidate-on fraction while tongue is absent, valid-frame coverage while
visible, normalized position spread during holds, return-to-neutral error,
repeatability at comfortable endpoints, direction mistakes, and p50/p95 total
capture-to-output latency. Candidate false positives are not measured pointer
activations; measure actual false pointer motion later with a fixed Processing
configuration. Show mask overlays while reviewing mistakes. Choose an acceptable
latency/availability tradeoff from these measurements, not from model name/size.

If neither pretrained nor color segmentation works reliably, train a compact
segmentation model on representative labeled crops including tongue-absent frames.
Hold out complete sessions (not adjacent random frames). A pretrained encoder is
not itself a tongue detector. Compare that trained model using the same protocol
before promotion into the default camera path.
