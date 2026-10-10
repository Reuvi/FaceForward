# Application integration

This directory belongs to the integration owner. Read the root `AGENTS.md` and
`Contracts/README.md`. Wire public Vision, Processing, and Drivers interfaces;
do not duplicate their logic. Own lifecycle, selected subject/profile, camera
ownership, clock/timebase, configuration assembly, and stop/shutdown behavior.

Begin with fixture → processor → logging driver. Make replay/mock mode explicit
and available without hardware permissions. Ensure only one live input driver is
enabled, and disable/release output before switching subjects or profiles.
Add whole-pipeline checks under `tests/integration/` when implementation begins.
