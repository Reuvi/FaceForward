# Presentation: head pointer, mouth brake and dictation

Select **Presentation** on Signals. Existing Mouse test and gaming mappings stay
available with their previous bindings. Presentation defaults to **plain eye
open/closed**; wink training is optional. It still needs your saved/calibrated
Eye open/closed geometry and both head axes. Mouth opening needs no calibration.

| Input | Action |
| --- | --- |
| Head X / Y | Direction and speed of relative mouse movement |
| Open mouth wider | More resistance; wide opening stops the pointer |
| Close/reopen left eye | Left click (default minimum closure 120 ms) |
| Hold left eye | Mouse down after 650 ms; move head to drag; reopen to release |
| Close/reopen right eye | One Enter press (default minimum closure 120 ms) |
| Hold both eyes closed | Toggle dictation after 450 ms; reopen between toggles |

Both-eye gestures suppress click/Enter. Short simultaneous blinks do not toggle
anything. Unknown eye evidence cancels a pending gesture and releases dragging;
reopen both eyes to resume. Stop, tracking loss and stale input release everything
and require Start again. Missing mouth evidence stops pointer movement in this
mapping; it does not invent a closed-mouth value.

With **Require calibrated wink for eye actions** enabled, a recognized wink clicks
on reopening without an extra minimum hold. The first closed frame can precede
wink recognition; it no longer rejects the entire gesture. Hold a recognized
left wink for dragging. Known closed non-wink readings release pending recognition;
unknown readings cancel the gesture until you reopen both eyes. Both-eye dictation
continues to use anatomical closure, independent of wink recognition.

## Build and run

From the repository root:

```bash
cmake -S Drivers -B Drivers/build -DFID_NATIVE_BACKEND=ON
cmake --build Drivers/build -j 4
python3 tools/build_dictation.py
Vision/.venv/bin/python -m App --source camera --mapping presentation
```

Synthetic/replay inputs cannot start the microphone.

The dictation build requires macOS and Xcode command-line Swift tools. The signed
helper lives in a private cache per checkout, outside cloud-synced Desktop folders.
No model is downloaded by the build or App. `--mapping presentation` reuses the
head response and resting center in the local personal default when available.
Use `--factory-defaults` to compare the built-in response. These defaults are a
starting point, not a claim of measured improvement from mouth braking.

1. Load your camera profile. Head X, Head Y and Eye open/closed should have valid
   readings. You can skip Wink action calibration with the default plain-eye mode.
2. Click **Set up dictation** once. Allow Speech Recognition and Microphone for
   Face Controller Dictation/the launching host if macOS requests them. A setup
   error stays visible. The helper requires on-device speech support for your
   system language; if unavailable, enable/download that language under System
   Settings → Keyboard → Dictation, then retry setup. There is no cloud fallback.
3. Select **Live mouse + keyboard**, click **Connect output**, then hold your
   comfortable resting pose with both eyes open and click **Center head & start**.
   Live output requires Camera and Accessibility permission for the Python host.
4. Move to the browser/text field and left-click it. Hold both eyes closed, then
   reopen and speak. The pointer and other actions pause during dictation.
5. Hold both eyes closed again and reopen to finish. The finalized text is sent
   through the driver one printable Unicode character every 35 ms. No Enter is
   appended. Return your head to center before moving again; use the right eye
   to press Enter when ready.

Dictation doesn't open/activate another window. Keep the intended text field
focused while speaking and sending. Native target applications must accept Quartz
Unicode key events. The helper uses macOS Speech with on-device recognition;
actual microphone accuracy and application compatibility require operator testing.
Recognition can finish early or stop recording at 55 seconds; it still waits for
your finish gesture before sending. After two minutes without finishing it cancels.

Stop/Escape cancels speech and discards unsent characters. Already-entered
characters remain in the focused application. Errors never send a partial speech
hypothesis. Audio and transcripts are not saved to disk or diagnostic logs; a
short live transcript is visible in Signals while dictating.

## Connected adjustments

**Live curves → Mouth opening → pointer resistance** exposes onset (0.08), full
brake (0.65) and curve exponent (1.5). Opening increases resistance monotonically,
removes existing momentum and reduces requested velocity. It never reverses the
pointer. Closing releases the brake and restores speed through the existing head
acceleration/filter. Head response settings remain separate.

**Live curves → Eye gesture timing** adjusts the plain-mode solo closure minimum,
both-eye hold and drag hold. The solo minimum is hidden in wink mode because wink
recognition already qualifies the action. **Require calibrated wink for eye actions** selects wink vs
plain anatomical input for solo actions; both-eye dictation always uses anatomical
closure. Save/load a named tuning profile to keep these choices. Loading profiles
or changing eye mode stops output; live response sliders do not arm it.

For scrollbars: position over the scrollbar thumb, hold the left eye until the
Signals row says Dragging, move your head, then reopen. Mouth resistance also
works while dragging.

If a wink does not click, the left-eye Signals row distinguishes **waiting for
calibrated wink**, **wink unknown**, **wink recognized — reopen for click**, and
**Eye open/closed unknown**. Wink mode needs a camera profile with completed Wink
action calibration, not just a saved response/curve profile. Retry only the Wink
action guide if recognition remains unavailable; existing head and eye geometry
are retained. The local diagnostic log includes scalar recognition state and
capture-level action/unknown counts, so brief winks are visible between 5 Hz log
observations. Counts are gesture requests; `driver_events` confirms delivery.

## Software checks

Processing tests cover braking, gestures, missing input, reopening, migration and
saved curves. Integration tests inject synthetic camera-compatible measurements,
a fake speech service and the actual compiled dry-run driver to verify character
ordering, cancellation, click/Enter separation and watchdog drag release. Native
Tk tests cover mapping/curve/setup controls. These checks do not use a real camera,
microphone or live OS input and do not establish human accuracy.

Apple references: [on-device recognition](https://developer.apple.com/documentation/speech/sfspeechrecognizer/supportsondevicerecognition),
[Speech permission](https://developer.apple.com/documentation/speech/sfspeechrecognizer/requestauthorization(_:)),
[Unicode keyboard events](https://developer.apple.com/documentation/coregraphics/cgevent/keyboardsetunicodestring(stringlength:unicodestring:)).
