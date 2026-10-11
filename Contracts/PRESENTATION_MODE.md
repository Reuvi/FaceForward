# Presentation mode

Current user decision: a separate Presentation mapping uses calibrated head X/Y
for relative pointer velocity, anatomical left-eye closure for click/drag,
right-eye closure for Enter, and both eyes for speech-to-text dictation. Existing
mappings retain their assignments. The saved `require_wink` option remains; this
preset defaults to plain open/closed eyes. Eye geometry still needs calibration.

Vision adds optional continuous `mouth_openness` in [0,1] from the same validated
MediaPipe jawOpen sample as binary `mouth_open`. It needs no additional model or
calibration. Missing evidence stays invalid. The bit remains unchanged for old
maps. Processing applies a monotone mouth brake after head response: increasing
opening reduces current and requested speed, reaching zero at full brake, never
reversing motion. Unknown mouth stops this mapping's pointer only. Mouth braking
is suspended during dictation because speaking changes mouth shape.

Mapping v9 adds a presentation settings group. Older files migrate with this mode
disabled. Mouth start/full opening and response exponent are connected live
controls; profile loads, mapping changes and eye-mode changes disarm as before.

Only in this explicit combined-gesture mapping, solo eye actions wait for release.
Plain closure requires 120 ms; a calibrated wink already supplies action evidence
and has no additional solo duration threshold. Known closed non-wink frames wait
for recognition instead of rejecting the whole closure. Unknown anatomical or
active-eye wink evidence cancels the pending action and requires reopening;
unknown is never interpreted as a release-click. A later known non-wink frame
clears pending recognition; a subsequent valid wink may qualify again. Left closure
(or recognized wink) held 650 ms presses the mouse button
for dragging; reopening releases. Both closed 450 ms toggles dictation once,
suppresses click/Enter, and requires both to reopen before another gesture. Any
unknown eye cancels pending gestures and releases dragging; both known-open eyes
are needed to resume. Short ordinary blinks do not toggle dictation. This gesture
arbitration supersedes independent instantaneous eye actions only for this mode.
Signals exposes the current gesture blocker and capture-level eye/action counts.
The bounded scalar diagnostic log retains these counts so a brief wink is visible
even between UI observations. No face features, calibration or transcripts are logged.

`device_control_v1` gains optional `presentation` with boolean `enter`, `drag_left`
and `eyes_known`. Enter is one press/release per activation; dragging is a held
state. ABI v3 struct layouts stay unchanged. Additive driver APIs set those states
and type one Unicode scalar at a time. Native macOS supports Unicode text; other
backends explicitly report unsupported text instead of pretending to type. Driver
freshness, neutral startup, pause, errors, shutdown and its independent watchdog
release dragging as well as keys. Auxiliary calls never refresh the watchdog.

App injects a bounded asynchronous dictation service. macOS Speech/AVAudioEngine
run only from explicit Camera control, never synthetic/replay input, in a local
helper with explicit microphone and Speech permissions and required
on-device recognition. No network fallback, runtime model download, clipboard,
stored audio or transcript log. Starting/recording/finalizing/sending freezes the
pointer and other actions. A second deliberate both-eye gesture ends recording;
the completed text is sent through Drivers one scalar per step. No automatic
Enter is appended. The right eye can submit afterward. Stop, face loss, stale
capture, profile/source/output changes or speech error discard unsent text and
cancel recording. A failed provider never silently sends partial text. Synthetic
tests use an injected provider and dry-run output, never camera, mic or live keys.

The native helper does not activate a window, preserving the focused text field.
Permission/setup failures are visible with actionable instructions. Live human
speech, gesture reliability and foreground application acceptance require a trial;
unit tests do not establish those properties.
