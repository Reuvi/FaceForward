# Screen destination pointer

Gaming now sends a destination to the existing driver. If pupil readings settle
at X=.65, Y=.375, the default mapping travels toward 80% across and 25% down the primary
display, then stops. It does not keep moving right/up. Small changes around the
last accepted destination are ignored; the rest of the screen has no central
dead zone. A missing pupil stops travel immediately without returning to center.

This is **approximate positioning from raw pupils**, not calibrated screen gaze.
The user's no-pupil-calibration choice is retained. The app does not learn where
a particular person is looking on their display, and head movement or a different
resting gaze can shift the correspondence. Existing pupil fits stay inactive.

## Run

Rebuild Drivers once after pulling, then restart App:

```sh
cmake -S Drivers -B Drivers/build
cmake --build Drivers/build -j 4
Vision/.venv/bin/python -m App --source camera --output native
```

1. Select **gaming keyboard mouse mapping 1** on Signals.
2. Open **Mapping settings…**. **Pointer behavior → Screen destination** is the
   new default. Apply stops output. Older imported mapping files retain Velocity;
   select Screen destination and export again to save the change.
3. A saved face profile is optional for pupils, and still supplies independent
   eye-click and head-key calibration. Loading it keeps the selected pointer mode.
4. Keep your head neutral and release eye actions, then press **Start live control**.
   Pupils can start anywhere; there is no pupil-center startup gate in this mode.
5. Look at a fixed location, then another. The cursor should settle at each
   estimated destination. Signals reports the destination and driver arrival.
   Stop/Escape, tracking loss or staleness releases output; restart explicitly.

The new pupil defaults are **Pointer gain 2**, **Downward boost 4**, **Position
smoothing 20 ms**, **Position delay 0 ms**, and **Fixation dead band .002** (0.2%
of screen dimensions). Downward boost multiplies overall gain: positive pupil Y
movement below its center gets 8× total response. X and upward motion get 2×.
For example, raw Y=.53 requests screen Y=.74; Y=.5625 reaches the bottom. X=.25
or .75 reaches the left or right edge. Each axis clips independently, so all four
corners are reachable. Filtering settles exactly at a saturated edge.

Adjust these in **Mapping settings…**. Raising smoothing or fixation dead band
reduces jitter; lowering them responds to smaller changes. Gain also amplifies
noise. Downward boost applies before inversion, preserving the chosen direction.
The driver's pointer speed controls travel speed without overshooting. Loading a
face profile keeps these target settings; export the mapping to save custom tuning
across app restarts. Older imported mapping files preserve their saved response;
set the values above to opt into the new tuning.

**Velocity** remains available for joystick-style movement. It uses the original
center dead zone, response curve and acceleration settings. **Mouse test** remains
head X/Y velocity only, ignoring every eye/pupil/click/key/scroll input. Its separate
defaults are downward boost 3, gain 1, smoothing 20 ms, zero interpolation delay,
dead zone .10 plus .02 activation margin, curve 1.2, acceleration 10/s and
deceleration 14/s. Tiny head jitter still has a neutral zone. Loading a face
profile keeps the chosen Mouse test pointer tuning.

Targets refer to the primary display. Native target support uses macOS or Linux
X11 with the driver's display dependencies; pure Wayland target support is not
implemented. The simulated developer playground follows the same destination
semantics, and dry-run driver checks require no OS input permissions.

## Accuracy and evidence

[Google's MediaPipe Iris description](https://research.google/blog/mediapipe-iris-real-time-iris-tracking-depth-estimation/)
distinguishes iris localization from determining a person's gaze location.
[EyeTrax's documented workflow](https://github.com/ck-zhang/eyetrax)
trains from screen calibration before predicting screen coordinates. For this
app, that supports keeping raw positioning labeled approximate: a screen-dot fit
would be a separate step toward matching the actual location being viewed.

Synthetic checks cover destination arrival, repeated-target stability, jitter,
unknown/stale input, profile/mapping compatibility and key/button release. They
do not measure a person's gaze accuracy. The C ABI stays v3; mapping files are
v4 (v1/v2 import as velocity; v3 preserves its response), detector presets v13 and face profiles v3 stay intact.
See [the adopted interface](../Contracts/SCREEN_POINTER.md).
