# Independently scheduled detector models

Reuvi integration, base 0d1db08. This supersedes earlier "same worker" language:
one camera and one shared capture history remain, but expensive independent
models must not block each other, Tk, or Processing.

MediaPipe owns eye, pupil and head measurements on the fast capture path. Those
features share one model; they emit a SignalFrame for every processed capture.
Neural tongue inference owns a separate spawned process with a limited CPU thread
budget. Submit without waiting, keep one running crop and one replaceable pending
crop, and consume only the latest completed result. No growing frame queue.
Runtime stays local/offline. Slow, missing, failed or hung tongue inference must
not stop eye/head/pupil samples. Shared hardware can still cause CPU contention;
independent scheduling is not a guarantee of identical FPS under overload.

Neural frames add `tongue_sample` with `format: tongue_sample_v1`, `session_id`,
`subject_id`, `sequence`, and `timestamp_ms`. The last two identify the original
crop capture, never its completion/delivery time; both are null before any result.
The enclosing frame continues to describe the current fast capture. Repeated
tongue values carry the same original identity, not new measurements. Invalid,
stale, future, cross-session or out-of-order tongue samples release only that
pointer input. Processing inserts each distinct tongue sample once into its
interpolation history and expires it on its output clock using the original
timestamp and existing stale_ms. Legacy frames and gaze remain capture-timed.
An invalid signal must clear pointer motion even if its tongue identity repeats.

Reset/load/source loss/restart invalidate outstanding jobs; late results cannot
restore a previous calibration or subject. Saved profile schemas do not change.
Tongue calibration counts each completed inference once, gates evidence by its
original capture window, and permits at most stale_ms of delivery grace before
finishing a pose. Rest/preparation/previous-pose results never train the next pose.
A hung backend cannot leave calibration waiting forever.

The camera preview remains current; delayed tongue overlays are shown only on
their own captured mouth crop. The shared trace records capture identity, result
age, new-result status and timings. Unchanged/missing tongue intervals are dark
display holds, never fake fresh points. Show actual fast capture Hz and completed
tongue Hz separately. Stop drops pending work; close cleans up the child process
without waiting indefinitely for inference.
