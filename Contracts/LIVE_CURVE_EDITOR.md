# Live signal response editor

The user requested connected curve editing with live sliders, useful defaults,
saved profiles and control over response timing across mapped inputs. This adds
one native editor window from Signals, without another main tab or detector UI.

Expose only controls used by the active mapping: velocity pointer shaping,
head-speed boost/braking, target gain/downward amplification/fixation smoothing,
gaming head-key thresholds/smoothing/confirmation, and legacy scroll response.
Show independent calibrated wink ON/OFF and live validity; binary wink actions have
no amplitude curve or added dwell/release timer. Detector calibration is unchanged.
Show the actual transfer curve, live raw/output markers and a labeled synthetic
movement/settling preview from the same Processing filters. Missing inputs stay
unknown; plotted or simulated values never enter the live pipeline.

Sliders hot-update a validated allowlist under the Processing lock. Keep the
processor, input source, output session, armed/enabled state, captured timestamps
and filter velocity/history. Preserve adaptive state while changing its cutoff.
Do not reprocess cached eye samples or create clicks. Edited head-key gates release
and require fresh neutral input before another key activation. Invalid/stale input
and Stop retain priority; edits never arm or revive stopped control. A queued edit
must match both the selected mapping and its settings generation.

The existing mapping revision remains stable during live response-only edits so
Drivers can keep its current session; track a separate local tuning revision for
UI/diagnostics. Structural mapping changes, regular settings, source changes,
profile/default loads and calibration still disarm. Native driver speed ceilings
and routing cannot be changed through the hot-update path. Applying analog gain
changes output inside the existing finite normalized driver bounds.

Add strict signal_tuning_profile_v1 JSON storing a readable name, the complete
active mapping (or legacy mouse config) and mouse/scroll driver speed settings.
Validate before applying, use bounded reads and atomic local writes. Profiles do
not contain detector data, frames or armed state. Loading/defaults always stops
output; default response comes from the built-in family, preserving the current
mapping identity/bindings where applicable. Keep mapping v6, face v3, detector v13
and the driver ABI unchanged. Expose save/load/default controls in the editor.

Test live edits while output is enabled, stopped, stale and unknown; invalid and
outdated edits must be atomic. Verify hold/click independence, filter continuity,
profile round trips/rejection, UI wiring and compiled-driver movement without a
restart or duplicate clicks. Synthetic checks do not establish human comfort.
