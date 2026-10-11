# Mouth button and relative head control

User-requested integration update: Mouse test keeps the tuned head X/Y response
and relative velocity pointer, and now maps left eye action to held W, right eye
action to one left click, and mouth open to held Space. No right click, pupil
movement, head-direction keys or scroll in this preset. Existing wink/plain-eye
selection remains independent and saved. This supersedes the Mouse test click
assignments in HEAD_MOUSE_CLICKS.md; other imported mappings keep their routing.

Vision adds optional `signals.mouth_open` to SignalFrame v1. It is a discrete
0/1 measurement (1=open), derived from the existing same-capture MediaPipe
`jawOpen` coefficient at a fixed threshold of 0.5. No new inference, calibration,
user setting, tongue detector or worker. Missing/nonfinite/out-of-range coefficient
or unavailable mouth landmarks means null/0/false. Confidence 1 denotes available
evidence, not calibrated accuracy. Preserve capture time and independent channels.
Expose the raw score and bit in local diagnostics. Old frames without it stay valid.

Processing mapping v8 adds `button_bindings` with left_eye, right_eye and mouth
keys, each selecting a supported keyboard key, left_click, right_click or none.
Strictly validate v1–v7 and migrate with their previous left/right mouse bindings
and mouth unassigned. The new built-in Mouse test assigns W/left_click/Space.
Full mapping/tuning copies and profiles persist routing. Response-only defaults
preserve routing. The explicit local personal default is upgraded with the user's
new routing while retaining all measured response values and resting center.

Button input is instantaneous binary state. W and Space hold until their source
releases; mouse activations use the existing one-click-per-activation driver.
Unknown releases only the affected action and requires a fresh inactive sample
before reactivation. Startup cannot enable while a mapped known button is active.
Multiple inputs assigned to one output combine with OR. Stop/loss/staleness,
source/mapping/profile changes release everything and require explicit rearming.

device_control_v1 gains optional `known.keys`, a complete boolean map for the six
supported keys. New routed commands use this per-output validity so keyboard
actions do not depend on head validity. Unknown outputs cannot activate. The
driver still accepts older commands using the existing head validity rule.
Mouse validity follows its assigned input, never an anatomical eye name.
Driver ABI v3 and the native C implementations remain unchanged.

The driver already distinguishes velocity (relative deltas) from absolute target
mode. Head mappings explicitly emit velocity throughout; display this as Relative
movement. No cursor-position feedback or absolute target command enters that path.
Build/test the native driver, verify relative demand and independent button/key
events in dry-run, and retain target support for existing pupil mappings. Synthetic
tests cannot establish Roblox compatibility or improved human smoothness.
