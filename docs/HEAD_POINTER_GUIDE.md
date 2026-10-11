# Head pointer movement and wink clicks

**Current recovery and eye option:** use **Signals → Center head & start** if Start
waits for the old head center. Hold a comfortable pose with eyes open; the next
valid capture establishes the center and starts output. Save a tuning profile to
keep it. **Live curves → Require calibrated wink for clicks** can be unchecked for
plain open/closed clicks without wink training. Ordinary blinks also click.
The Eye clicks switch in Mapping settings enables/disables both click channels.


Mouse test uses calibrated Head X/Y as smooth velocity control. Small movements
request very slow, precise cursor motion; larger turns travel faster. Holding a
position keeps moving, and returning to neutral stops. Left/right calibrated Wink
actions click the matching mouse button. Pupils, keyboard actions and scroll are
ignored. Your head calibration and 3× downward boost are unchanged.

**Speed-aware acceleration and return braking** adds a bounded boost for quick
outward turns and stronger braking when returning to center. Slow adjustments and
steady holds use the position-based curve. Adaptive smoothing remains in place;
a small dead zone rejects neutral jitter. Missing head input stops the pointer
immediately. Face loss, staleness or Stop requires another explicit Start.

## Try and tune it

Restart App to load the new Mouse test defaults, or launch from the repository:

```sh
Vision/.venv/bin/python -m App --source camera --mapping mouse-test --output native
```

Load your face profile, select **Mouse test**, center your head, release eye
actions and click **Start live control**. Existing head calibration still works.
For clicks, load a profile with completed wink training or finish **Eye open/closed**
and **Wink action** calibration. Without wink calibration, head movement still works.

In **Mapping settings… → Head movement response**:

| Setting | Default | Effect |
| --- | --- | --- |
| Speed-aware acceleration and return braking | On | Adds transient speed response to the precision curve |
| Movement boost | .75 | Up to 75% extra speed during fast outward turns, capped at the existing maximum |
| Return braking | .65 | Up to 65% reduction in requested speed during fast returns, with stronger deceleration |
| Eye clicks | On | Each eye activates its matching mouse button; choose wink or plain closure in Live curves |

Holding a wink produces one click. Reopen before the next wink; each eye works
independently. Unknown eye input releases that button and requires its actual
reopening before another activation. Anatomical closure alone clicks only when
Require calibrated wink is unchecked in Live curves.
Unchecking **Eye clicks** restores pointer-only control. Clicks do not drag.

The built-in pointer curve uses a dead zone of **.03**, activation margin **.005**,
response exponent **1.8**, gain **1.4**, smoothing **20 ms** and no interpolation
delay. These are in personal calibrated coordinates. For an illustrative steady
horizontal turn at the default 900 px/s driver maximum:

| Fraction of calibrated range from neutral | Approximate cursor speed |
| --- | --- |
| 5% | 1 px/s |
| 10% | 11 px/s |
| 20% | 55 px/s |
| 60% | 484 px/s |

Faster outward movement adds the temporary boost. Downward motion retains its
separate 3× amplification. Values describe software requests, not a measured
camera accuracy or timing guarantee.

Try a slow turn, a quick turn to the same position, then return to center. Lower
Movement boost if fast turns overshoot. Raise Return braking if centering carries
the cursor too far; reduce it if returning feels abrupt. Increase the dead zone
slightly if your resting head drifts. Apply stops output; center and Start again.
Signals/logs show movement phase plus independent left/right eye action rows.

Export the mapping to keep custom settings across restarts. Face-profile loading
keeps the response and wink checkbox. Older mapping exports retain their previous
curve and import with wink clicks off; enable clicks and export again to opt in.
Mappings before v5 also import with speed-aware boost/braking off.

## Implementation and checks

Motion uses centered calibrated head positions and original capture times, before
downward amplification or inversion. An 80 ms window plus the latest capture reject
small oscillations and prevent outward boost during a return. The speed floor is
.35 personal half-ranges/s, with full response at 2 half-ranges/s. Without another
capture, the response fades after 80 ms and expires at 150 ms; freshness checks
remain independent.

Synthetic tests cover the precision curve, slow/fast turns, return/reversal,
X/Y/diagonals, rates, noise, missing inputs, independent winks and saved mappings.
Compiled-driver tests verify fractional speed accumulating into single-pixel moves,
one click per wink activation, unknown/reopen behavior and complete stop. The user's
camera test determines comfort and preferred tuning.
