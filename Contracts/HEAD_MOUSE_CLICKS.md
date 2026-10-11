# Precise head movement and independent wink clicks

Follow-up: [EYE_MODE_CONTROL_RECOVERY.md](EYE_MODE_CONTROL_RECOVERY.md) adds the explicit plain-closure option, mapping v7 and fresh head-center startup.

Follow-up: [LIVE_CURVE_EDITOR.md](LIVE_CURVE_EDITOR.md) permits validated live
response-only slider edits without disarming. Regular settings and full profile
loads still stop; all wink validity and independence rules below remain.

The user requested very slow, precise cursor speed for small head movements,
fast travel for larger/quicker turns, and left/right clicks from the matching eye
in wink mode. This supersedes Mouse test's earlier eye/click exclusion. It keeps
the existing name and head X/Y velocity input; pupils, keyboard bindings and scroll
remain ignored. No new detector calibration, camera, model or native driver API.

Built-in Mouse test now uses dead zone .03, activation margin .005, response
exponent 1.8 and pointer gain 1.4. The small neutral zone rejects stationary jitter;
above it the continuous curved response starts very slowly and rises to full speed.
Existing 20 ms smoothing, zero interpolation delay, 3× downward gain, capture-speed
boost and return braking remain. Preserve raw measurements, output bounds and
immediate stops on invalid/stale input. Existing mapping exports retain their
saved response rather than being silently retuned.

Enable calibrated wink clicks by default in Mouse test. Only a valid same-capture
`eye_intent_v1` wink is ON. Left wink maps to left click; right wink maps to right
click. Use the existing independent per-eye gates: no dwell, debounce, opposite-eye
gate or combined-eye suppression. Unknown releases that eye and requires its own
actual reopening before another activation; opening/closed non-actions are OFF.
Anatomical closure without a valid appearance-intent channel cannot cause a click,
including legacy raw_mouse_v1 inputs. Missing wink calibration does not block head
movement. The existing driver emits one complete click per activation, not repeated
clicks or dragging while held. Stop/loss/staleness/settings changes release output.

Startup still needs fresh neutral head input and must not start with a known wink
or button held. After output is enabled, eyes and pointer remain independent: a
missing head axis stops movement, and an unknown eye releases only that click.
Malformed eye-intent envelopes fail closed when clicks are enabled; the explicit
clicks-off mode retains the old ignore-eyes behavior. Pupil gaming is unchanged.

Mapping files become input_mapping_v6, adding `head_wink_clicks` (boolean). It is
true in built-in Mouse test, false elsewhere. Validate v1–v5 completely and migrate
with wink clicks off, preserving their earlier behavior. Expose the checkbox and
independent eye action rows in head mapping settings/Signals; hide eye rows when
off. Copies, export/import and face-profile loading keep the selected click option.
Applying it disarms output. Detector presets v13, face profiles v3, SignalFrame and
driver ABI v3 remain unchanged. Native calibration-classifier accuracy is separate
from synthetic software checks.
