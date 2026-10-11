# Head pointer movement response

Mouse test still uses calibrated Head X/Y as a smooth velocity control. Moving
farther from neutral requests more cursor speed; holding at that position keeps
moving, and returning to neutral stops. It continues to ignore pupils, eye actions,
keys and scroll. Your head calibration and downward boost are unchanged.

The new **Speed-aware acceleration and return braking** option adds:

- Faster turns away from neutral: a modest extra speed boost and quicker ramp-up.
- Slow adjustments: the existing response for precision.
- Moving back toward neutral: reduced cursor speed and stronger braking.
- Holding still: the usual position-driven speed, with no persistent speed boost.

The existing adaptive smoothing remains in place. Tiny neutral movements stay
inside the dead zone. Missing head input stops immediately, and tracking loss,
staleness or Stop requires another explicit Start.

## Try and tune it

Restart App to load the new Mouse test default, or launch from the repository:

```sh
Vision/.venv/bin/python -m App --source camera --mapping mouse-test --output native
```

Load your face profile, select **Mouse test**, center your head and click
**Start live control**. No new calibration is required.

Open **Mapping settings… → Head movement response**:

| Setting | Default | Effect |
| --- | --- | --- |
| Speed-aware acceleration and return braking | On | Uncheck to restore the previous response for comparison |
| Movement boost | .75 | Up to 75% extra requested speed during fast outward turns, capped at the existing maximum |
| Return braking | .65 | Up to 65% reduction in requested speed during fast returns, with stronger deceleration |

Try a slow turn, a quick turn to the same position, then return to center. Lower
Movement boost if fast turns overshoot your intended destination. Raise Return
braking if centering still carries the cursor too far; reduce it if returning feels
abrupt. Apply stops output; center and Start again. Signals/logs identify
`accelerating`, `return braking`, `steady` or `resting`.

Export the mapping to keep custom settings across restarts. Loading a face profile
keeps these settings. Older mapping exports retain their earlier response with
this feature off; enable it and export again to opt in.

## Implementation and checks

Motion is measured from centered calibrated head positions and original capture
times, before downward amplification or inversion. An 80 ms window plus the latest
capture reject small oscillations and prevent outward boost during a return. The
speed floor is .35 personal half-ranges/s, with full response at 2 half-ranges/s.
This is not degrees/s. Without another capture, the response fades after 80 ms
and expires at 150 ms; the normal stale-input stop remains independent.

Synthetic tests compare slow/fast motion, rest, return, reversal, X/Y/diagonal
movement, capture/output rates, tiny jitter, missing input and mapping migration.
Compiled-driver checks inspect movement deltas and a complete stop. These verify
the software path; the user's camera test determines comfort and preferred tuning.
