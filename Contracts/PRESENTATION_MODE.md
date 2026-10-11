# Presentation mode

Current user decision: a separate Presentation mapping uses calibrated head X/Y
for relative pointer velocity, anatomical left-eye closure for click/drag,
right-eye closure for right-click, and both eyes for speech-to-text dictation. Existing
mappings retain their assignments. The saved `require_wink` option remains; this
preset defaults to plain open/closed eyes. Eye geometry still needs calibration.

Head startup does not require usable eye measurements: after an explicit Start
or Center head & start, fresh neutral head input can enable the pointer while
unknown eyes remain released. Known closed eyes still block startup. Unknown is
never an open baseline; eye actions and dictation require actual reopening before
their first activation. Missing head input, face loss and stale samples retain
their existing stop/disarm behavior. Mouth validity/braking is unchanged.

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

Current user correction: left eye uses a held mouse button, not a complete click
pulse on recognition or reopening. After a known-open baseline, a valid selected
left action presses immediately: recognized wink in wink mode, anatomical closure
in plain mode. Reopening releases; moving while held drags with no extra timer.
Unknown/unsupported left evidence releases immediately and cannot press. Right-eye
uncertainty does not veto a valid left action. An unknown transition before the
first press does not erase the last known-open baseline; it produces no output.
After a press, invalid/nonmatching left evidence releases and consumes that cycle;
only an actual left reopen permits another press. Stop/loss/staleness clear all
baselines and never auto-arm. No held numeric/display value is action evidence.

Right-eye right-click retains release timing (120 ms in plain mode; no extra minimum
for a recognized wink). Both known closed 450 ms toggles dictation once, releases
the mouse and suppresses solo actions until both reopen. Short simultaneous blinks
do not toggle dictation. An immediate left press can already have occurred if the
second eye closes later; subsequent chord detection releases it but cannot undo
events already sent. This is the requested immediate press/release behavior.
The old saved drag timing field remains readable but is not applied or shown;
plain-mode solo timing now describes right-eye right-click only.
Signals exposes the current gesture blocker and capture-level eye/action counts.
The bounded scalar diagnostic log retains these counts so a brief wink is visible
even between UI observations. No face features, calibration or transcripts are logged.

`device_control_v1` has optional `presentation` with boolean `enter`, `drag_left`
and `eyes_known`. Additive paired `left_known`/`right_known` flags let the adapter
validate each held-left/Enter action independently; legacy messages without them
retain the both-eyes validity gate. `eyes_known` still reports both eyes known.
Presentation left input uses `drag_left` for mouse down/up, never a separate click
pulse; Enter is one press/release per activation. ABI v3 layouts stay unchanged.
Additive driver APIs set those states
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
the completed nonempty text is sent through Drivers one scalar per step, followed
by exactly one main Return press/release. The explicit finish gesture authorizes
that submission; it occurs only after the last character and another fresh enabled
output tick. Empty/whitespace-only recognition, errors, cancellation, face loss,
stale input, or switching profiles/source/output must never submit. A stop between
the last character and Return cancels the pending Return as well. Stop, face loss, stale
capture, profile/source/output changes or speech error discard unsent text and
cancel recording. A failed provider never silently sends partial text. Synthetic
tests use an injected provider and dry-run output, never camera, mic or live keys.

The native helper does not activate a window, preserving the focused text field.
Permission/setup failures are visible with actionable instructions. Live human
speech, gesture reliability and foreground application acceptance require a trial;
unit tests do not establish those properties.

## Return and audible dictation update

User-facing Return is the main Return key on macOS (`kVK_Return`, 0x24),
not keypad Enter. Existing `enter` payload/event/API names remain compatible.
It creates a newline in multiline fields or activates the focused field's Return
handling. Unicode text and Return are separate driver operations.

Launch the signed speech **app bundle** through LaunchServices, without activation,
so microphone/Speech permission belongs to Face Controller Dictation rather than
the Python/terminal/IDE host. Communicate through a private ephemeral local socket;
no transcript/audio files. Disconnect cancels recognition. Setup reports permissions
and local-language availability; failures expose a stable diagnostic code without
logging dictated text. A rising cue marks actual microphone listening, a falling
cue marks recording stopped (finish, captured, cancellation or failure). Repeated
partial results never replay the cues. No sound on a failed start before listening.

Preserve the observed both-open baseline across uncertain closing frames so a
subsequent fully known both-closed hold can start. Unknown input cancels any pending
solo right-click and resets the chord duration; it never counts toward the 450 ms hold
or rearms a consumed chord. Both eyes must reopen after a successful toggle.

## Right-click and dictation submission update

The right-eye gesture now emits the existing `buttons.right_click` pulse with
matching `known.right_click` validity, using the same closure/wink qualification
and release timing as before. It no longer requests `presentation.enter`.
The driver API/ABI, mapping/profile formats and other mappings are unchanged.
The existing Return auxiliary API is called by App only after successful finalized
text delivery. Pointer and solo gestures remain frozen through the submission tick;
unknown eyes do not veto explicit finalized dictation while the session itself is
fresh and enabled. Listening/stopped sounds retain their meaning: stopped means
recording ended, while typing/submission may still be in progress.

Completing dictation releases its temporary pause in the existing enabled session.
Head movement resumes from zero velocity through the normal response curve; it
does not require hitting the precise center dead zone again. Mouth braking and
invalid-input gates still apply. Stop, loss and staleness remain disarming events
and completion must never auto-arm them.
