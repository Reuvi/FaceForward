# Sampled wink calibration, October 10

## Current calibration workflow

The eye tab has two separately started native guides: **Eye open/closed** (seven
geometry steps) and **Blinks & winks** (fourteen appearance/check steps).
`start_eye_guide` starts geometry only. `start_wink_guide` requires at least one
completed eye geometry fit and never clears or refits it. Failed, cancelled or
restarted blink/wink training retains eye/head/tongue calibration. Starting new
geometry clears dependent wink models; only geometry that passes its reopen check
can become the basis of wink training. Starting wink training clears old wink
models, releases output and resets Processing's eye-input history.

Both guides show a prominent rest countdown and the upcoming instruction together.
Rest/preparation frames stay excluded from training; capture timestamps own phase
timing and UI acknowledgments are tied to the calibration generation. Completion
returns to the lab; geometry never automatically starts blink/wink training.
Completed geometry can be saved/loaded before training winks. Existing profile
formats (combined v3 / detector v5), learned models and frame semantics are unchanged.

The original classifier contract below still applies; references to one integrated
flow describe the earlier UI, superseded by this split workflow.

Reuvi requests removing the separate Detection research interface and integrating
useful blink/wink training into eye calibration. Confirmed output: 1 while an
intentional wink is observed, 0 on reopening; a natural blink is not an action.
No minimum closure time, duration feature, release debounce, cooldown or elapsed
time threshold decides the calibrated camera's eye input.

Vision owns independently trained per-eye, per-frame appearance classification.
Inputs are same-eye eyelid ratio, blink/squint/cheek/brow/wide expression coefficients
and normalized brow/cheek landmark distances. These are visual proxies, not direct
muscle measurements or verified intent. Training and later checking use separate
prompt windows. Rest/preparation frames never train. Indistinguishable appearances,
missing features or failed checks must not enable a wink classifier.

SignalFrame v1 eye fields retain their actual anatomical open/closed meaning. An
additive `eye_intent` object accompanies each calibrated capture:

```text
format: eye_intent_v1
session_id, sequence, timestamp_ms: exact enclosing frame envelope
subject_id: single-user
left/right: {value: 0|1|null, known: bool, state: open|blink|wink|unknown}
```

Unknown intent has null raw value. Processing records one sample per fresh capture,
holding the previous numeric input independently with known=false (startup 0).
It releases output on unknown; the held number never becomes action evidence.
For this input only, the mouse gate follows valid wink state immediately without
dwell/debounce. A fresh anatomical open sample is required after arming or unknown
before that eye can activate. Independent eyes never gate each other. Existing
raw/replay formats retain their legacy timing behavior for compatibility.

Only one preview path is active in App. Detection research UI and per-frame research
processing are removed; retained research modules are developer/legacy-profile
code. The unified App hides legacy eye timing controls and labels their scopes as
wink samples. Native camera, one-user persistence, head/tongue processing and driver
serialization remain unchanged.

New saved profiles use `face_mouse_profile_v3` with detector/processing/preview,
without research. Detector preset v3 adds per-eye `winks` models and their checks.
Old v1/v2 profiles remain readable, restoring geometry/head/tongue/settings. Old
event classifiers are not frame classifiers: old files need new wink calibration
before camera closures can activate mouse buttons. Profile loading remains local,
atomic, disarmed and possible without a current face. No raw training data is saved.

Guide collection/rest durations schedule training only. Capture timestamps still
control freshness/watchdogs and head/tongue motion; those are not wink-duration
thresholds. Save/load and temporary tracking loss retain completed models.
