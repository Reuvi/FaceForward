# Tongue removal — current mouse MVP

> Pupil mapping update: [PUPIL_HEAD_CALIBRATION.md](PUPIL_HEAD_CALIBRATION.md)
> supersedes fixed/no-calibration pupil behavior. Tongue stays retired, matrix
> shape stays 11×11, and detector presets now save v12.

User decision: retire tongue detection. This supersedes tongue runtime, guide,
backend, graph and pointer-selection requirements in earlier contracts.

- App and standalone Vision lab measure independent eyes/winks, head Y pitch,
  head X yaw and fixed MediaPipe pupil direction. No tongue crop, inference,
  worker, setup, calibration, graph or model download is part of either runtime.
- App's mouse pointer uses precise `gaze_x/y`; its 11×11 pupil matrix stays
  available for inspection. No pupil calibration or sensitivity controls.
- SignalFrame v1 keeps its required `tongue_x/y` slots, always null/invalid in
  current producers. No `tongue_sample` or tongue coordinate metadata is emitted.
  The standalone Processing library retains legacy tongue replay support.
- Detector presets v11 (`eyes-head-pupils-v11`) omit tongue model/range/identity
  and settings. Fully validate old v1–v10 profiles before discarding retired
  tongue state. Retain compatible eyes, wink models, head axes and fixed pupils.
  App migrates old pointer settings to `gaze`; loading always disarms output.
  Combined face/mouse profiles remain v3. Legacy detector/model modules may remain
  for old-file validation and isolated developer tests, never active sampling.
- Preserve head calibration/retry, independent wink classification, capture
  timestamps, unknown validity/dark display holds, single-user fits and stop/loss
  behavior. No new Drivers or OS injection changes.

Acceptance: native screens contain no tongue controls/plots; camera and demo do
not create a tongue worker or extract a mouth crop; profile migration retains
eye/head fits; pupil pointer, left/right clicks and vertical scroll still work.
