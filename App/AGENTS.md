# Application integration

This directory belongs to the integration owner. Read the root `AGENTS.md` and
`Contracts/README.md`. Wire public Vision, Processing, and Drivers interfaces;
do not duplicate their logic. Own lifecycle, selected subject/profile, camera
ownership, clock/timebase, configuration assembly, and stop/shutdown behavior.

Begin with fixture → processor → logging driver. Make replay/mock mode explicit
and available without hardware permissions. Ensure only one live input driver is
enabled, and disable/release output before switching subjects or profiles.
Add whole-pipeline checks under `tests/integration/` when implementation begins.

The native MVP is implemented: read `README.md` and `Contracts/MOUSE_MVP.md`.
`MouseSession` owns the single Vision worker and connects dictionaries directly
to `Lab.ingest`. `IntegratedDesktop` extends the existing Tk lab. Keep input,
processing, and drawing clocks independent; no browser/JS/HTTP transport. Stop,
EOF, and errors must call `Lab.disconnect` immediately. Preserve explicit subject
selection and source ownership. The demo tests four mouse outputs; camera mode
exposes raw diagnostics with invalid controls until calibration/detectors exist.
Do not report synthetic success as live detector accuracy or driver completion.
