# Lip-boundary tongue candidate and reliable calibrated head yaw

Reuvi requests two changes after DIRECT_PUPILS.md: infer tongue direction from
color extending beyond MediaPipe's lip outline, and improve Head X dropouts while retaining calibration (latest clarification).
Head Y and eye/wink calibration stay unchanged. Keep native local execution and
independent bounded tongue scheduling from ASYNC_DETECTION.md.

## Calibrated head X reliability

Keep independent neutral/left/right calibration, raw degrees and learned 0/.5/1
mapping. Going beyond a learned endpoint is saturation at 0 or 1, not loss of
tracking. Apply saturation only after valid current yaw/image evidence; actual
face loss, missing pose or failed image quality remains invalid. Never fabricate
a current sample from a display hold. Head Y behavior is unchanged.

Keep the last completed horizontal fit while retrying its guide. Only a successful
new guide replaces it; cancelling, failing or losing the face during a retry must
not destroy a working fit. Explicit Reset Head X still clears it. Output is stopped
during calibration. Explain saturation separately from actual tracking failure in
the live readings and trace, so a user can identify which source is dropping.

## Lip-boundary tongue candidate

Use MediaPipe's outer lip contour, mouth-aligned crop and local color contrast.
Estimate nearby skin and lip chroma each capture, mask tissue-like color outside
an expanded lip boundary, and require a coherent region connected to that boundary.
Reject insufficient contrast, tiny/disconnected regions, ambiguous multiple
extensions and clipping. Report the center of the supported outer front boundary,
not the blob centroid. Raw coordinates remain mouth widths; this is an experimental
color-extension proxy, not an anatomical guarantee that the region is tongue.
Teeth, changing illumination, makeup and objects at the mouth require live checks.

No background-photo sequence, tissue clicking, trained neural model or download
is needed for the new default camera backend. Preserve the local ONNX option for
explicit comparison; never silently switch backends on a detection failure.
The color algorithm runs in the existing independent tongue process. Every result
retains its original crop, capture sequence/time and lifecycle epoch; a slow result
cannot block eyes/head/pupils. Overlays show the lip outline and selected exterior
region on that original crop. Head/eye/pupil sampling remains independent.

Use `lip_color_extension_mouth_width_v1` to identify the new measurement. Existing
tongue position/range training and fresh absence/visible checks remain for joystick
normalization; raw candidates are visible immediately. Changing tongue backend
clears only its old range/validation. Other completed fits survive.

## Persistence

Detector preset v9 (`lip-boundary-head-reliability-v9`) retains the existing
independent head_x fit and direct pupil settings. Tongue may identify built-in
`{backend: lip-boundary, algorithm: lip-color-extension-v1}` or the pinned existing
ONNX backend, or legacy developer color prototypes.

Fully validate v1–v8 before state mutation, retaining compatible eye/head/pupil
calibration. Legacy ONNX profiles migrate to the new built-in tongue backend and
discard incompatible tongue ranges. New v9 files restore their explicit backend;
tongue ranges still need fresh checks. Calibrated head_x now saturates past trained
limits when the raw observation remains usable.
Combined profile v3 and mouse mappings/Drivers remain unchanged.

The user clarifies that raw yaw/face tracking also disappears. Use experimental
presence/tracking confidence floors of .35 in the calibrated live Lab (initial
face-detection confidence remains .5); expose these values in diagnostics/docs.
Generic detector defaults remain .5. Never replace genuinely absent landmarks
with a held or invented head observation. Encourage small comfortable Head X
turns (roughly 10–20 degrees), and allow a failed horizontal guide pose to retry
without repeating good captures. Human-camera validation is still required.
