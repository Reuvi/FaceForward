# Lip-boundary tongue candidate and direct head yaw

Reuvi requests two changes after DIRECT_PUPILS.md: infer tongue direction from
color extending beyond MediaPipe's lip outline, and use raw head X without a guide.
Head Y and eye/wink calibration stay unchanged. Keep native local execution and
independent bounded tongue scheduling from ASYNC_DETECTION.md.

## Direct head X

Reuse yaw degrees from the current face transformation. Emit the existing head_x
slot immediately on every usable capture: clip(.5 + yaw / (2 * half_range), 0, 1).
Default half_range is 30 degrees; allow 5–90 with a direct native scale control.
Raw zero maps to .5, negative yaw toward 0, positive yaw toward 1. No trained
neutral/endpoints, guide, recheck or old fit may gate this channel. Head Y retains
its personal pitch fit. Unavailable pose/image quality remains invalid; graph
holds stay display-only. Scale changes disarm preview and preserve other fits.

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

Detector preset v9 (`lip-boundary-direct-yaw-v9`) replaces head_x fit with direct
settings `{measurement: mediapipe_yaw_v2, half_range_degrees: 30}`; nullable head
still stores vertical pitch. Pupil direct settings remain unchanged. Tongue may
identify built-in `{backend: lip-boundary, algorithm: lip-color-extension-v1}` or
the pinned existing ONNX backend, or legacy developer color prototypes.

Fully validate v1–v8 before state mutation; ignore legacy horizontal fits in favor
of direct yaw. Legacy ONNX profiles migrate to the new built-in tongue backend
and discard incompatible tongue ranges. Preserve compatible other fits/settings.
New v9 files restore their explicit backend; tongue ranges still need fresh checks.
Combined profile v3 and mouse mappings/Drivers remain unchanged.
