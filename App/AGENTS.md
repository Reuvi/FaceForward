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
EOF, and errors must call `Lab.disconnect` immediately. Preserve source ownership
and the single-user lifecycle in Contracts/MOUSE_MVP.md.
The camera/detector demo automatically attaches one logical subject; geometric
tracking changes and brief loss must not erase calibration. Keep explicit subject
selection only for legacy replay. Camera and detector-demo use Vision's externally
driven `LabRuntime.ingest`; never start its worker inside App. Embed the same
calibration view and preserve source/subject when changing tabs. Versioned profiles
combine separately validated detector and Processing settings; loading works while
stopped/without a face, disarms preview and clears tongue
validation. Same-source restart preserves learned detector/research fits; switching
source kind or explicit Reset all calibration clears them. Never auto-arm on return.
Collection also disarms preview. Preserve invalid controls until each detector is calibrated.
Do not report synthetic success as live detector accuracy or driver completion.
