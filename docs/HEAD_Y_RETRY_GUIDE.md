# Redo one part of Head Y calibration

Restart the app, then open **Detection calibration → 2 Head Y**.

- **Retry current step**: repeat the current capture or check. This works while
  the step is running and after a failure. Other accepted poses stay collected.
- Select **Capture neutral**, **Capture up**, or **Capture down**, then press
  **Redo selected step** to replace that particular reference. This also works
  after finishing calibration or loading a saved profile.
- Select **Check neutral**, **Check up**, or **Check down** to check an existing
  fit without changing its learned references. All three references must exist
  before a check can run.
- **Start head pitch guide** remains available for a completely new set of
  captures. Cancel an active guide first if you want to start the whole guide.

Follow the preparation, rest countdown and capture sound as usual. Head Y always
measures nodding pitch; there is no measurement-mode choice. During up/down poses,
use your comfortable limits rather than straining to reach an extreme.

For example, if **up** was captured incorrectly, choose **Capture up → Redo
selected step**. Neutral and down remain unchanged. Capture up once, then perform
fresh neutral/up/down checks. You do not need to collect those other reference
positions again. With default timings this is roughly 16 seconds instead of a
complete six-step guide. If a later check fails, retry that check alone; checks
that already passed with this fit remain passed.

Changing any reference changes the normalization, so its old checks are cleared.
All three positions must pass fresh checks before the new fit replaces your last
working one. Selecting another check cannot skip a failed required check.
A check-only retry on an already completed/loaded fit needs only that selected
check. If this is your first calibration and some references are still missing,
the guide collects those missing poses after the one you selected.

The **References** line shows **captured**, **saved**, or **needed** for each pose.
Captured means a window was collected; the fit still needs its checks to pass.
Saved references are values from a completed fit, not fabricated camera samples.
Choosing another step discards the current unfinished window.

Your last completed Head Y fit stays intact during retries, failure or Cancel.
Other eye, wink, Head X and pupil calibrations are untouched. App preview stops
when you start/retry calibration and does not auto-arm afterward. Leaving the tab
or losing the face cancels unfinished work but retains the completed fit. You can
then redo one pose from that fit. Before any completed fit exists, cancelled or
lost unfinished captures are not retained.

After success, verify up=0, neutral=.5 and down=1 in the Head Y graph. Use **Save
active profile** to keep the change. Profile version remains detector v12 / combined
v3; existing files work without conversion. Raw pitch, endpoint tolerance, sign
handling and mouse scroll mapping are unchanged.

## Engineering and testing

`Vision/head_guide.py` extends the existing timed movement guide for Head Y only.
It keeps untouched captured groups or saved scalar references, rebuilds a small
step queue after a selection, and tracks required checks separately from passed
checks. New samples still pass the existing count, visibility, stability and
separation gates. A replacement fit becomes active only after its scheduled
required checks pass. Saved references never contribute to a new capture count.

`DetectorWorkbench.redo_head_y_step(role, name)` accepts `train`/`check` and
`neutral`/`up`/`down`. `retry_movement_step()` now supports Head Y's current step
as well as Head X's existing failed-step retry. Every selection increments prompt
generation, requires fresh input, and excludes concurrent calibration. Late UI
acknowledgments and captures from an old window cannot start/train its replacement.
App exposes the command through its normal disarming calibration path. The camera,
per-frame trace, Processing cadence and saved-profile schema are unchanged.

Run from the repository root:

```sh
Vision/.venv/bin/python -m unittest discover -s tests/vision -p test_head_guide.py -v
RUN_TK_TESTS=1 Vision/.venv/bin/python -m unittest discover -s tests/integration -p test_head_y_retry.py -v
Vision/.venv/bin/python -m App --source detector-demo
```

The synthetic detector demo follows the current step automatically. Native tests
cover step controls, active retries, tab cancellation, profile round trips,
independent channel preservation and promotion only after fresh checks. These
checks verify software behavior, not human detector accuracy.
