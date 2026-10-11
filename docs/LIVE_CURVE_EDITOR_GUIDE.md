# Live curves and tuning profiles

Restart App and open **Signals → Live curves…** beside the active mapping. The
editor connects to the current Processing response. If output is running, sliders
change it immediately without another Start. If output is stopped, editing leaves
it stopped. **Stop output / Escape** releases output from the editor.

Choose an input from the menu. Only controls used by that mapping appear:

| Input | Adjustable response |
| --- | --- |
| Mouse test Head X/Y | Gain, downward amplification, dead zone, start margin, curve exponent, smoothing, acceleration, braking, delay, fast-turn boost and return braking |
| Gaming pupils, screen destination | Gain, downward amplification, position smoothing, delay and fixation dead band |
| Gaming pupils, velocity | Velocity curve, gain, smoothing, acceleration/braking, delay and quick-move boost/fade |
| Gaming head keys | Each axis's press threshold, release threshold, smoothing and press confirmation time |
| Mouse and scroll: Head Y | Scroll curve, smoothing, ramp/braking, delay and quick-move boost/fade |
| Left/right eye actions (wink or plain closure) | Live independent ON/OFF state; keys hold and mouse buttons click once per activation |
| Mouth open | Live binary input/action; no calibration or response sliders |

**Require calibrated wink for eye actions** selects the eye source for this mapping.
Leave it checked for trained wink actions. Uncheck it for plain **open/closed**:
each eye activates its assigned button immediately. In Mouse test, left eye → W
and right eye → left click. Ordinary blinks also activate those assignments. Only the Eye open/closed geometry guide is needed in this mode;
wink training and wink intent are ignored. Unknown releases that eye, and actual
reopening re-arms it. Holding closed never repeats clicks. Changing the flag stops
output; press Start again. Save as… and mapping export retain the choice.

For Mouse test, **Center head & start** is available on Signals and in the editor.
Hold a comfortable resting pose, open your eyes and close your mouth. The next fresh valid Head X/Y
capture becomes your resting center, then output starts from a neutral command.
This recovers a controller stuck waiting for the old center without weakening the
precision dead zone. It uses the currently connected output mode. If the head is
at a calibrated range limit, move closer to the middle first. Missing/stale input
cancels the request; retry when tracking returns. Save the tuning profile to keep
the new center. Normal Start continues to use the saved center.

Winks are binary: there is no adjustable click strength or additional wink timer.
Use Calibration for wink training. Legacy raw-eye developer inputs expose their
existing closure/reopen confirmation sliders only when those timers actually run.
Head keys are also discrete; their curves show press/release thresholds, not
variable key strength. Editing a head-key gate releases that axis and requires
fresh neutral input before another press. Other mapped inputs continue working.

The upper graph is the response curve, with dots for **actual input and output**.
For X/Y pointer control, each line shows that axis with the other centered; live
diagonal motion uses the coupled radial curve. Pointer/scroll velocity .5 means
stopped; for screen destinations, .5 means the screen center. Unknown input has
no dot and is labeled unknown. Graphs do not fabricate valid values.

The lower graph is a **synthetic timing preview** using the same filters. It turns
outward, holds, and starts returning at .8 seconds. It shows how motion ramps and
settles as you adjust settings. This simulation never enters live control. A wink
or closure preview shows the activation level; the driver still clicks only on its rising edge.

## Measured adjustments

Use **Signals → Target game…** to measure travel speed, small-target precision and
roughness, then test one supported adjustment against your baseline. Repeated
rounds can save an improved personal default. [Game guide](TARGET_GAME_GUIDE.md).
The manual controls below remain available for experiments.

## Manual adjustments

- For finer small movements, raise **Curve exponent** a little. Reduce **Rest dead
  zone** only if intentional small movements are being ignored.
- For faster travel, raise **Signal gain** or **Fast-turn boost**. Driver output
  remains bounded by the existing maximum speed.
- For less lag, reduce **Motion smoothing** or **Input delay**. Delay is shared by
  pointer and scroll in the old Mouse and scroll mapping.
- To stop sooner, increase **Braking** or **Return braking**. To make an ordinary
  quick-move boost last longer, raise **Boost fade time** where available.
- For head keys that trigger too easily, raise their **Press threshold**. Increase
  **Press confirmation** to require a longer deliberate movement. Release stays
  below press; moving one threshold past the other adjusts its partner.

Mouse test starts with the tuned precision defaults: gain 1.4, downward boost 3,
exponent 1.8, dead zone .03, start margin .005, smoothing 20 ms, no input delay,
acceleration 10/s, braking 14/s, fast-turn extra boost .75 and return braking .65.
The existing head calibration is reused. [Head movement and wink setup](HEAD_POINTER_GUIDE.md).

## Save, load and restore

Name the tuning profile and choose **Save as…** to write a local JSON file. It
contains the current mapping response, bindings and driver speed settings; it
contains no detector calibration, captures or armed state. Save the face profile
separately for eye/head calibration. Mapping export also retains live-tuned values.

**Load…** validates the entire file before applying it and selecting its mapping.
It stops output; center/release your inputs and press Start on Signals afterward.
**Personal default** loads the head mouse profile selected in the Target game.
**Factory defaults** restores the built-in family's response and default speed
limits, preserving your mapping name, identity, bindings, pointer mode, eye-click enable and wink/closure
choice. It also stops output. Save custom tuning before resetting if you want it
back. Each mapping can have multiple named local tuning files.

Routing, mapping family, detector configuration and driver connection still live
in their existing controls. Live edits never start a stopped controller, bypass
unknown/stale input, replay eye activations or reset the capture clock. Closing the
editor retains applied settings for this session; saving retains them after restart.
