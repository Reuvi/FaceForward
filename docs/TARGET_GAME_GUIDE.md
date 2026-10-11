# Measure and improve head mouse control

Open **Signals → Target game…**. The game measures your actual cursor while the
existing camera → Processing → driver connection moves it. It records a baseline,
tests one suggested setting change, and keeps the adjustment only if it wins two
comparisons. No neural model or additional camera is involved.

## First run

Restart the updated App from the repository root:

```sh
Vision/.venv/bin/python -m App --source camera --output native --mapping mouse-test
```

1. Load your usual face profile or calibrate **Head X** and **Head Y**. Choose
   **Mouse test** and connect **Live mouse + keyboard** on Signals.
2. Hold your comfortable resting pose. Press **Center head & start** if needed,
   otherwise **Start live control**. Confirm that moving your head moves the cursor.
3. Open **Target game…**. Choose **Fullscreen** before starting if desired; keep
   the window size, position, display and calibration unchanged during a comparison.
4. Press **Start baseline** or Enter. Use your head only; leave the physical mouse
   alone during measured trials. Return to the blue home ring, then move to the
   gold target and remain inside for **0.6 seconds**. No clicking is needed.
5. Complete 16 targets. The report shows your results and, when supported by the
   data, one proposed adjustment. Rest between rounds, then press Enter to continue.
   Output stops between rounds; return to the same resting pose for each Start.

If Start waits for a resting position you cannot comfortably reproduce, hold a
comfortable pose and press **Recenter & continue** in the game. You can also use
**Center head & start** on Signals, then return and start the next round. Completed
rounds remain saved. A changed center or window layout means those rounds cannot
be treated as an unchanged A/B comparison; they still provide useful movement data.
Other response edits or changed camera/calibration require a new session.

The four rounds are **A baseline → B adjustment → B repeat → A repeat**. Each
repeats the same targets: left/right/up/down at three sizes, plus four diagonals.
Small targets require precise short movements; other targets test longer travel.
The current radii are 14, 27 and 44 canvas pixels. Targets time out after 20 seconds.
There is no penalty score or guessed global skill rating: each result is a separate
measurement of this task and controller configuration.

**Practice with mouse** lets you learn the game using the physical mouse. It stops
controller output, is clearly labeled, and cannot produce tuning suggestions or
change defaults. The app cannot reliably distinguish physical-mouse assistance
while live head control is active; do not mix the two during measured trials.

## What is measured

| Measurement | Meaning |
| --- | --- |
| First arrival | Time until the cursor first enters the target |
| Arrival + stable hold | Total acquisition time, including the required 600 ms hold |
| Extra settling time | Time after first arrival, excluding the final required hold |
| Exits and re-entries | Leaving the target and coming back before completing it; reported separately for small targets |
| Path efficiency | Shortest required distance divided by traveled distance; closer to 100% is more direct |
| Overshoot | Distance past the far edge along the travel direction, in target radii |
| Small-target hold error | RMS distance from target center during the final hold, in target radii |
| Motion roughness | Extra velocity variation from stops, speed changes and reversals; lower is smoother |

The saved reports also include transverse path variability and success/timeouts.
Roughness is a project heuristic using actual timestamps resampled every 50 ms,
with the final mandatory hold excluded. Sampling gaps over 120 ms invalidate an
attempt rather than counting as a successful hold or as poor movement.

Target re-entry and path accuracy follow established pointing-device evaluation
ideas described by [MacKenzie, Kauppinen and Silfverberg (CHI 2001)](https://www.yorku.ca/mack/CHI01.htm).
This game uses dwell selection; it does **not** report ISO throughput. Its roughness
formula and decision thresholds are experimental, not validated clinical measures.

## How settings improve

A usable live round needs all 16 conditions attempted, at least 12 successful
targets and at least 3 successful small targets, with sufficient cursor samples.
Practice and interrupted attempts never tune. The first round can suggest one
bounded adjustment:

- Repeated small-target re-entry: a gentler curve, or slightly less gain.
- Overshoot: stronger braking when returning toward the resting head pose.
- Slower downward movement without extra re-entry: slightly more downward gain.
- Repeated speed/direction changes: slightly more smoothing.
- Slow, direct, precise movement: slightly more gain.

These are hypotheses to test, not assumed improvements. B must beat A in **both**
paired comparisons while preserving completion, precision and smoothness. Speed
comparison removes the fixed hold and accounts for each trial's actual departure
distance relative to target width. Better precision may justify a small speed
cost. If results are mixed, A wins. The repeated baseline exposes changes from
practice or fatigue. Failed suggestions are remembered for matching baseline
settings so a later session can try a different supported adjustment.

The winning profile is saved locally as **Personal measured head control**. Normal
App startup, or startup with `--mapping mouse-test`, loads it without starting
output. Explicit other mappings still win. **Live curves → Personal default**
reloads it; **Factory defaults** restores the built-in response for the current
mapping. Both stop output. For a reproducible factory run:

```sh
Vision/.venv/bin/python -m App --source demo --mapping mouse-test --factory-defaults
```

If no clear adjustment is supported, keep the settings and review the paths.
Start remains available to collect additional baseline rounds with the same
response; these are labeled A, and no untested adjustment is promoted.
**Keep baseline as default** can save a completed usable first round without
claiming improvement. Ordinary **Save as… / Load…** tuning profiles remain
available. Face calibration is saved separately.

## Pauses and results

Missing/stale head input, camera/driver failures, disabled output, focus loss or
recording gaps pause the attempt and stop output. **Resume target** explicitly
starts again from home after fresh input. It never resumes automatically.
Changing calibration, source or response settings requires a new session. Moving
the game during a target pauses it; restore its position before resuming. Between
rounds, a changed layout can continue collecting data but is not a matched comparison.
Recentering during a paused round keeps the completed trials and retries the current
target, while excluding that mixed-center round from automatic tuning.
**Stop / Escape / closing the game**
saves partial results and restores A while the game still owns the current settings.
An unfinished B is never promoted; unrelated edits are preserved.

Sessions are private local files under `.local/target-game/<session-id>/`:

- `cursor.jsonl`: actual cursor coordinates/times, head observations, capture
  sequence/timestamps, processed pointer requests, validity, output status and events.
- `round-1.json` … `round-4.json`: complete settings and per-target results.
- `round-1.csv` …: convenient per-target tables.
- `decision.json` and `selected-profile.json`: final comparison and chosen settings.
- `partial-round.json`: interrupted work, when present.

Traces also record blocked UI actions and setup changes, so continuation failures
can be diagnosed later. Original round profiles are never rewritten after recentering.

`personal-default.json` and bounded `history.json` live in `.local/target-game/`.
No images or face calibration models are recorded, and this directory is ignored
by Git. Rounds are bounded to 12 minutes, 64 attempts and 180,000 cursor samples
per session. Storage failures stop the test and show an error.

For later analysis without camera access or changing settings:

```sh
python3 -m Processing.target_game .local/target-game/<session-id>
```

After your first live comparison, share the session ID or say the rounds are
finished in the integration task. The saved paths and synchronized head signals
can guide the next iteration. Software tests use synthetic trajectories; your
real trials are needed to establish whether any setting actually helps you.
You can explicitly request a provisional trial profile from existing baseline
data; its saved review identifies it as unverified and includes the prior profile
for rollback. That choice does not count as a successful A/B comparison.
