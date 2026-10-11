# Fixed pupil direction and square matrix

User requests stronger downward detection, no pupil sensitivity controls or
calibration, and a square matrix representation. This supersedes the adjustable
pupil settings in DIRECT_PUPILS.md. Keep the native local runtime, one camera,
original fast capture timestamps and independent tongue scheduling.

## No settings or calibration

Remove pupil sensitivity controls and their runtime command. New detector preset
v10 (`fixed-pupil-matrix-v10`) stores only a fixed pupil measurement identity;
validate v1–v9 fully before discarding their old pupil fits/sensitivity values.
Other compatible fits survive. Preserve explicit v9 tongue backend selection when
loading it; v1–v8 neural-to-lip-boundary migration remains as already specified.
Combined profiles stay v3. No rolling extrema, learned neutral or hidden calibration.

Raw iris X/Y remain eye-width offsets in the existing eye-corner coordinate frame.
Left/right/up mappings remain fixed at existing default scale. Downward behavior
will be checked against the open-eye gate and positive-Y response before changing
it; any fixed changes must be documented and covered by generated-eye checks.
Actual eye closure, unusable geometry, missing input and tracking loss remain
invalid. Do not change wink/click classification to improve pupil direction.

## Square matrix representation

Add `pupil_matrix` on every calibrated workbench SignalFrame (including no face):
`format: pupil_matrix_v1`, `size: 11`, capture `session_id`, `sequence`,
`timestamp_ms`, logical `subject_id`, `valid`, `confidence`, nullable `row`,
`column`, and `values` (11×11 nested integer array, or null when unavailable).
For valid normalized x/y, column= floor(x*10+.5), row=floor(y*10+.5).
Exactly one cell is 1; all others are 0. Row 0 is up, column 0 is the user's left,
row/column 5 is center, and row/column 10 is down/right. Unknown matrices are null,
never a fabricated neutral cell or control hold.

Keep continuous gaze_x/y for existing Processing; the matrix is an additive,
quantized representation for visualization and downstream integration. Existing
raw_mouse_v1 matrix parsing can consume its values explicitly in a future adapter;
there is no implicit change to mouse transfer functions or driver formats here.
CSV records matrix row/column/validity/size beside continuous/raw pupil data, not
121 duplicated cells per trace row. Both tabs use the same capture trace.

The native pupil view draws an actual square 11×11 grid, highlighted active cell,
continuous position and raw data. Unknown intervals can dark-hold the last plotted
cell with an explicit unknown label; displayed holds never become samples. No
sensitivity, setup wizard or pupil calibration controls remain.
