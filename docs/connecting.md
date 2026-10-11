# Connecting Vision, Processing, and Drivers

**Implemented App connection:** follow [the live output guide](DRIVER_CONNECTION_GUIDE.md)
and [current contract](../Contracts/DRIVER_CONNECTION.md). The driverTest library is
now integrated with both App mapping modes. This update supersedes the earlier
background-service proposal below: Stop and closing App release/destroy output.
No background service is installed. `Drivers.binding` is the shared public ctypes
binding; `Drivers.output.DriverOutput` validates Processing commands. App calls
`fid_submit_processed` synchronously, with zero additional button dwell/dead zone.
Original ABI v3 structs and `fid_submit` remain available to standalone tools.

```text
Camera → Vision (SignalFrame) → Processing (ControlFrame) → Python adapter → C ABI v3 → OS
```

Vision emits calibrated SignalFrames. Python Processing selects the subject and
maps controls; its adapter validates each ControlFrame, converts it to
`fid_frame`, and calls the C++ library with `ctypes`. See the [contract](../Contracts/README.md)
and [Driver guide](../Drivers/readme.MD).

## Runtime

App owns one camera and one optional driver handle. Preview is the default;
Driver dry run and Live mouse + keyboard are explicit choices. Native output
requires Camera, usable calibration and a new Start. Close always stops output.

## Python → C ABI

Build/load the OS library; match ABI v3 structs and check `abi_version`. Call
`fid_default_config`, set the backend, then `fid_create` → `fid_enable`; submit
neutral to arm, then fresh frames with `fid_submit` at 30–60 Hz. Check status;
pause on Stop/failure and destroy on shutdown. Test dry-run first.

Axes are finite `[0,1]`; `0.5` is neutral, lower/higher means left/up and
right/down. The Driver applies its dead zone and speed curve. Keep invalid
measurements invalid; do not replace them with neutral values.

The adapter validates `device_control_v1` or legacy `mouse_preview_v0` metadata
omitted by `fid_frame`. Native eye commands trigger one complete click per
activation, without driver dwell. Gaming head directions use ABI v3 held keys.
The adapter and independent C worker each enforce the 250 ms freshness limit;
the worker can release if Python stops sending while the process remains alive.
Dictation remains phase two.

## Test order

Test fixtures → dry-run → one camera signal → native Linux/macOS; verify direction,
release, stale/lost-face stop, permissions, and service restart.
