# Head movement speed response

The user prefers calibrated head X/Y pointer control and requested acceleration
and deceleration based on head movement speed, while retaining the existing smooth
Mouse test behavior. This change applies only to the head-mouse mapping family.
Raw head detection/calibration, downward gain, base velocity curve, neutral zone,
pupil mappings and independent gaming key/eye actions remain unchanged.

Mouse test enables a bounded movement-speed response. Estimate motion from
original capture timestamps and centered calibrated head coordinates, before
pointer gain/downward amplification/inversion. Moving away from neutral adds a
modest speed multiplier and raises the acceleration limit; moving toward neutral
removes that boost, reduces the requested speed and raises the deceleration limit.
The existing position-driven pointer speed remains the steady-state response when
the head holds still. Never integrate head velocity as a new cursor position.
Keep the existing adaptive smoothing and normalized driver limits.

Use a short capture window to suppress derivative noise, ignore very small motion,
and suppress outward boost immediately on return, reversal or stationary evidence.
No boost inside the neutral zone. Repeated output ticks cannot create motion
samples; transient response must expire without fresh captures. Equal capture
timestamps replace samples without division by zero. Clear movement history on
missing input, reset/rearm and source changes. Invalid/stale input and Stop release
immediately; returning to neutral brakes smoothly to a complete stop.

Mapping files become input_mapping_v5, adding head_motion with enabled (boolean),
speed_gain (0–2, default .75) and return_brake (0–1, default .65). Built-in Mouse test
enables it; other mappings disable it. Fully validate v1–v4 and migrate with this
feature disabled to preserve saved behavior. Copies, export/import and face-profile
loading retain these mapping settings. A settings change stops output. Turning the
feature off restores the previous Mouse test filter exactly.

Expose the toggle and two strengths in Mapping settings for head mouse only, with
readable movement phase and bounded scalar diagnostics. The motion estimator uses
normalized personal half-range per second, not physical degrees/second. No Vision,
SignalFrame, driver ABI, detector-preset or face-profile version change is needed.
Test slow/fast outward movement, holding, return/reversal, both axes and diagonals,
noise, variable capture/output rates, duplicate timestamps, loss, restart and
compiled driver deltas. Synthetic tests do not establish the user's comfort.
