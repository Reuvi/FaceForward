# Head-compensated pupil calibration (detector preset v12)

The user's latest decision supersedes fixed/no-calibration pupil requirements in
DIRECT_PUPILS, PUPIL_MATRIX and TONGUE_RETIREMENT. Tongue remains retired. The
11×11 matrix and continuous gaze_x/gaze_y share the calibrated pupil output.

Collect center gaze with head neutral, yaw left/right and pitch up/down. Learn a
small affine correction from same-frame raw yaw/pitch degrees to iris displacement
in eye-width units. Then collect comfortable eye left/right/up/down limits with
head near neutral. Subtract predicted head drift and map each side separately:
left/up=0, center=.5, right/down=1; valid endpoint overshoot saturates. This is a
personal directional joystick, not an absolute screen-gaze tracker.

Require fresh center and endpoint checks, including a held-out diagonal head pose.
Reject weak ranges, unstable samples, poor pose coverage and poor checks. Missing
iris/pose or head angles outside tested support produce null/invalid, never a
fabricated center or extrapolated control. Raw measurements remain available before
calibration. No user sensitivity sliders, other-eye action gate or new model.

Use native full-screen targets, clear head-versus-eye instructions, preparation,
rest countdowns and sounds. Prompt acknowledgments start capture windows; only
fresh ordered frames inside those windows train. Retry only the failed pose, or
restart/reset pupils independently. Keep a working fit until a replacement passes.
Completed fits survive tracking loss/restart. Device output stays disarmed during
calibration and profile loading. Do not alter eye or head fits.

Save versioned measurement identity, pose regression, reference/validity bounds,
personal endpoints and validation summary in detector v12 (combined profile v3).
Fully validate v1–v11 before migrating: retain compatible eyes/winks/head, discard
old pupil settings and request this guide. No tongue restoration. Validate all
new pupil parameters before replacing any live profile state.

Record raw iris, head pose, compensated iris, calibrated direction and validity
from the same captured frame in the shared trace/CSV. Dark held plot values remain
presentation only; emit one current valid/invalid matrix and signal sample per
capture. No second camera, network, inference model or runtime training loop.
