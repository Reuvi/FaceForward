# Measured pointer tuning game

The user requested a native target game to collect head-controlled cursor behavior
and improve personal defaults from repeated performance, rather than arbitrary
slider changes. App adds a Target game window from Signals; keep two main tabs,
one camera, the existing Processing pipeline and explicit native output arming.

Use actual OS cursor coordinates in the game's canvas. A separately labeled
physical-mouse practice mode cannot tune or promote controller defaults. Live
experiments require camera + head mouse mapping + native output. Record actual
monotonic cursor sample times, canvas/screen geometry, capture sequence/time,
normalized head observations/validity, processed pointer demand, driver status and
the complete tuning profile. Never save frames, images or detector models. Local
session JSONL, per-trial CSV and reports live under ignored .local/target-game.
Bound individual rounds/samples, flush progress and report storage failures.

Each round repeats 16 directional/distance/size conditions, including small targets
and diagonals. Start from a home target, then move into the destination and hold
for 600 ms. Clicks are not part of this movement test. Record first arrival,
settling/acquisition time, exits/re-entries, path efficiency, overshoot, transverse
variability and hold accuracy. A timestamp-resampled velocity-variation heuristic
reports roughness separately from data gaps. This is a dwell task inspired by
pointing-device research, not ISO throughput or a clinical skill score.

Source loss, disabled/error output, stale/unknown head input, layout changes,
source/session/settings changes or excessive cursor sampling gaps invalidate the
active attempt and pause. Never count a gap as successful holding. Resume is
explicit; retry that condition from home. Stop/Escape/close stops output and saves
partial work. Practice data and interrupted attempts remain labeled and excluded
from tuning. Unknown values stay null; plotted holds are never input.

Continuation recovery: explicit Start/Resume may adopt a changed resting center
without discarding saved rounds. Recenter & continue requests a fresh center
capture using the existing control action; it never resumes automatically after
loss. Record center/layout changes in additive `setup_changes` report entries and
trace events, keeping original round profiles unchanged. Layout changes between
rounds may continue collecting data; movement during a round still pauses it.
Changed centers/layouts are not matched A/B pairs, and a round recentered during
collection is not eligible for automatic tuning. Other response/calibration/source
changes still require a new session. Persist game UI errors in the session trace.

After a complete, usable baseline, offer at most one bounded response adjustment
supported by observed re-entry/overshoot, direction asymmetry, travel time or
roughness. The rules are experimental hypotheses, not guarantees. Compare in
A-B-B-A rounds with identical target geometry, driver speeds, eye routing and
center. Apply changes only between rounds. Never lower confidence/freshness gates,
change calibration/routing or add a neural model. Repeated A rounds expose practice
or fatigue effects. Require sufficient matched successful conditions and agreement
in both comparisons, with speed/precision/smoothness regression guards, to select B.
Otherwise keep A. Results show component metrics and the decision rationale.
Speed comparisons remove the fixed hold and normalize by each trial's actual
departure-distance/target-width difficulty. Remember rejected candidate settings
for a matching baseline so later sessions can test another supported hypothesis.
If no candidate is supported, allow additional baseline rounds instead of blocking
continuation. Label these A throughout and never claim an untested B won.

A completed comparison saves the selected profile as the local personal default;
an incomplete comparison never promotes a candidate. Restore A on cancel only
while the app still uses this experiment's settings; do not overwrite unrelated
user edits. Applying profiles releases output, and stopping never auto-arms.
Normal app startup can load a valid personal default without arming; explicit
other mappings/config remain authoritative. Factory settings remain unchanged
and `--factory-defaults` bypasses personal loading for reproducible runs. Live curves
offers separate Personal default and Factory defaults actions. No selection occurs
until user data exists. Mapping v7, tuning profile v1, face v3, detector v13 and
driver ABI are unchanged. Keep a machine-readable analysis command so later
iterations can inspect local results without rerunning the game.

An explicit user request may adopt a data-guided provisional trial from existing
baseline observations without completing the automatic comparison. Save its
evidence, unverified status and rollback profile privately; preserve the latest
user-selected resting center. This is distinct from an automatic verified winner
and does not change automatic promotion rules or arm a running controller.

Reference: MacKenzie, Kauppinen & Silfverberg (CHI 2001), target re-entry and path
accuracy measures: https://www.yorku.ca/mack/CHI01.htm . Our resampled velocity roughness
and conservative comparison thresholds are project heuristics, not that paper's
validated measures. Synthetic tests verify software, not human improvement.
