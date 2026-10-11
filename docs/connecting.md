# Connecting Vision, Processing, and Drivers

```text
Camera → Vision (SignalFrame) → Processing (ControlFrame) → Python adapter → C ABI v3 → OS
```

Vision emits calibrated SignalFrames. Python Processing selects the subject and
maps controls; its adapter validates each ControlFrame, converts it to
`fid_frame`, and calls the C++ library with `ctypes`. See the [contract](../Contracts/README.md)
and [Driver guide](../Drivers/readme.MD).

## Runtime

Use one opt-in per-user background runtime (`systemd --user` on Linux; a
permission-authorized app/background item on macOS). Start camera and input only
when assistance is enabled. Closing the UI leaves an active session running.

## Python → C ABI

Build/load the OS library; match ABI v3 structs and check `abi_version`. Call
`fid_default_config`, set the backend, then `fid_create` → `fid_enable`; submit
neutral to arm, then fresh frames with `fid_submit` at 30–60 Hz. Check status;
pause on Stop/failure and destroy on shutdown. Test dry-run first.

Axes are finite `[0,1]`; `0.5` is neutral, lower/higher means left/up and
right/down. The Driver applies its dead zone and speed curve. Keep invalid
measurements invalid; do not replace them with neutral values.

Python must validate ControlFrame metadata omitted by `fid_frame`. Mouse fields
trigger one dwell-qualified click per activation. ABI v3 key holds need a
ControlFrame contract change. Dictation is phase two. The 250 ms watchdog works
only while the process is alive.

## Test order

Test fixtures → dry-run → one camera signal → native Linux/macOS; verify direction,
release, stale/lost-face stop, permissions, and service restart.
