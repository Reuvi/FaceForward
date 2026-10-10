# Local detection research interface v1

This coordinated integration increment adds experiments alongside the existing mouse
MVP. SignalFrame v1, raw eye polarity and mouse_preview_v0 are unchanged.

Vision emits a separate `face_features_v1` observation with the exact session_id,
sequence, timestamp_ms and selected subject_id of its SignalFrame. `values` contains
finite named scalars or null: per-eye normalized geometry closure, raw blink/squint/
cheek/brow coefficients, eye-relative iris coordinates, head Euler angles (radians),
face center/image dimensions and log face width/image width. These are measurements,
not probabilities. App rejects mismatched joins. Missing features stay null.

Processing owns causal gesture candidates, duration/speed measurements, optional
trained event acceptance, mappings, dwell, relative head pointer and ordered click
events. Independent mode never uses the other eye as a hidden veto; strict mode
requires a reliable open opposite eye throughout. One click event is emitted after
stable reopening; hold mode is explicit. Tracking loss/stop/gaps cancel candidates,
release holds and disable preview. No interpolated/graph-held observation advances
an input timer. Histories and queues are bounded.

Research preview uses the separately named `research_preview_v1`: enabled, pointer
mode, normalized relative velocity or explicit normalized viewport position, held
buttons, and click events with unique monotonically increasing IDs. Absolute gaze
coordinates are never sent through the old relative-velocity path. The adapter is
preview-only; physical monitor mapping and real Drivers delivery remain a separate
hardware agreement. Gaze/head pointer modes disable head scrolling by default.

Profiles v2 contain the existing detector/processing/preview sections plus research
settings, scalar feature fits, event model coefficients and gaze coefficients.
Profiles v1 remain readable. No recordings, trial histories, event IDs, selected
identities or armed states are persisted. Loading binds only to a fresh explicitly
selected face, disarms both previews, and requires fresh gaze validation before
absolute preview. All training/evaluation/export stays local and scalar-only.

Native lab trials have user-supplied labels and session/trial IDs. Split whole trials
and fixation episodes for evaluation, never neighboring frames. Report exact counts,
false actions per observation time, missed/wrong/repeated actions, durations, speed,
latency and invalid time. Compare geometry, added blink coefficients, then facial
features on identical held-out events. Models are experimental and need user data;
synthetic tests cannot establish live accuracy.

## Eye-only neutral samples (user-requested update)

Every fresh captured frame now has an explicit Processing `eye_sample_v1` record,
including frames with uncalibrated/unknown eyes or no selected face. This additive
local sample contains capture `session_id`, `sequence`, `timestamp_ms`, the requested
`subject_id` (nullable when unselected), and independent `left`/`right` entries:
`{"value": 0.0, "known": false}` for unknown. The value convention is normalized
closure: **0 = open/no action, 1 = closed**, with continuous calibrated scores in the
research recognizer and binary values in the original mouse adapter.

Unknown eye input defaults numerically to open. Its `known=false` flag cancels a
pending gesture and releases a hold immediately; fallback open must never qualify
as intentional reopening/click-on-release or as a measured open calibration sample.
Rearming still requires observed open samples. A valid opposite eye remains independent.
Missing selected face records neutral samples and stops output; it never selects a
bystander. Invalid/duplicate/out-of-order/stale captures do not refresh the stream.

Raw SignalFrame/feature observations, graph data and calibration/training data retain
null/invalid values. Unknown graph intervals remain darker holds of the previous known
height. Per-frame exports also include explicit `left_input`/`right_input` numeric
values and `*_input_known` flags. The ordinary 100 Hz output clock remains independent
of camera rate. No samples are invented when capture stops. This fallback applies to
eyes only; head, tongue and other facial channels keep their existing invalid-data
behavior pending their own calibration decisions.

Vision's feature values now include numeric `left_eye_known`/`right_eye_known`
(0/1) from the calibrated eye classifier. The raw geometry closure score may remain
finite while this flag is 0; Processing must then supply the numeric open fallback.
Legacy feature fixtures without these optional flags retain finite-or-null behavior.
The research trace preserves `*_measured_closure` separately from masked graph values.
