# Head mouse, eye buttons and mouth-open Space

Restart App, select **Mouse test**, load your face calibration, and connect
**Live mouse + keyboard**. Open both eyes, close your mouth, hold a comfortable
head pose and choose **Center head & start**. Existing personal response settings
and eye-mode selection remain reusable.

| Input | Default Mouse test action |
| --- | --- |
| Head X + Head Y | Relative mouse movement, with the existing precision curve |
| Left eye action | Hold W until released |
| Right eye action | One left click per activation |
| Mouth open | Hold Space while open; release when closed |

Mouth uses the existing camera's jaw-open coefficient, converted to 0/1 with a
fixed 0.5 threshold. There is no mouth calibration, slider, new model or tongue
detection. **Signals** shows its live bit and Space state; **Live curves → Mouth
open** shows the binary input and output without adjustment controls.

The saved **Require calibrated wink for eye actions** choice remains authoritative.
Checked uses trained wink intent; unchecked uses anatomical eye closure, so an
ordinary blink can activate W/click. Eyes work independently. Missing mouth or eye
evidence releases that input and requires its inactive state before another
activation. Missing head axes stop the pointer while valid buttons remain usable.
Face loss, stale input and Stop release everything and require explicit Start.

**Relative movement** is the driver's existing velocity mode. Processing sends
direction and speed; the driver integrates them into relative X/Y deltas. On
macOS, its mouse events include explicit Quartz delta fields for clients that
lock the pointer. Holding the head off-center continues moving; returning to
rest stops. This does not change the head response into absolute positioning.
The older pupil Screen destination mapping remains separately available.

For Roblox, choose its desired camera/first-person mode and test while live
control is running. Compiled dry-run tests verify deltas and key/click events;
they cannot prove a particular game consumes those events or that motion feels
smoother. The existing [driver pointer-lock probe](../Drivers/testing/README.md)
can help distinguish relative-event delivery from a game's input behavior.

**Mapping settings** allows changing the three button assignments. Applying a
mapping or loading a profile stops output. Save/export to retain the choice.
Mapping v8 stores these bindings; older v1–v7 files load with their original
left/right-click assignments and mouth unassigned. They are not silently remapped.
The user's existing local personal default is explicitly updated for this request,
with a rollback copy, while preserving its measured movement settings.

No native pointer or keyboard events are injected by automated tests. Run the
compiled driver checks with `ctest --test-dir Drivers/build --output-on-failure`
and the integration suite with `FID_LIBRARY` pointing to that build.
