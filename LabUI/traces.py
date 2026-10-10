"""Display-only holds. Source values, validity and exported rows are never modified."""

from math import isfinite


def darker(color):
    """Retain a trace's hue at 52% brightness for unknown intervals."""
    return "#" + "".join(f"{round(int(color[i:i+2], 16) * .52):02x}" for i in (1, 3, 5))


def trace_runs(samples, *, step=False, max_gap=None, start=None):
    """Return (unknown, [(time, value), ...]) runs, with holds across missing data.

    Samples are (time, value-or-None, context). A context change or None resets
    the remembered value, as does a non-increasing timestamp. No initial value
    is invented. max_gap marks unsampled time as unknown. Recovery is a jump at
    the new sample, never an interpolated ramp through the unknown interval.
    start clips the view after finding a seed in the supplied bounded history.
    """
    runs = []
    previous = None
    last_value = None
    context = None

    def append(unknown, points):
        if start is not None:
            if points[-1][0] < start:
                return
            while len(points) > 1 and points[1][0] < start:
                points.pop(0)
            if points[0][0] < start:
                (a, av), (b, bv) = points[:2]
                points[0] = (start, av + (bv-av)*(start-a)/(b-a))
        if runs and runs[-1][0] == unknown and runs[-1][1][-1] == points[0]:
            runs[-1][1].extend(points[1:])
        else:
            runs.append((unknown, points))

    for timestamp, value, current_context in samples:
        valid = isinstance(value, (int, float)) and isfinite(value)
        if (current_context is None or current_context != context
                or previous is not None and timestamp <= previous[0]):
            previous, last_value = None, None
        context = current_context
        if context is None:
            continue
        if previous is not None and last_value is not None:
            old_time, old_valid = previous
            unknown = not valid or not old_valid or (max_gap is not None and timestamp-old_time > max_gap)
            if unknown:
                append(True, [(old_time, last_value), (timestamp, last_value)])
                if valid:
                    append(False, [(timestamp, last_value), (timestamp, value)])
            else:
                points = [(old_time, last_value)]
                if step:
                    points.append((timestamp, last_value))
                points.append((timestamp, value))
                append(False, points)
        if valid:
            last_value = value
        previous = (timestamp, valid)
    return runs
