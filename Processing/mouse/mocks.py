"""Deterministic synthetic sampled signals; no detector needed."""

import math


SCENARIOS = ("manual", "blink_wink", "pointer_circle", "scroll_flick", "jitter", "dropout")


def clamp(value):
    return min(1.0, max(0.0, value))


def vector(position, size=11):
    values = [0] * size
    values[round(clamp(position) * (size - 1))] = 1
    return values


def matrix(x, y, rows=9, columns=9):
    values = [[0] * columns for _ in range(rows)]
    values[round(clamp(y) * (rows - 1))][round(clamp(x) * (columns - 1))] = 1
    return values


def scenario(name, seconds, manual):
    state = dict(manual)
    t = seconds % 8.0
    if name != "manual":
        state.update(x=0.5, y=0.5, scroll=0.5, left=False, right=False)
    if name == "blink_wink":
        state["left"] = 1 <= t < 1.12 or 2 <= t < 2.85 or 5 <= t < 5.85
        state["right"] = 1 <= t < 1.12 or 3.5 <= t < 4.35 or 5 <= t < 5.85
    elif name == "pointer_circle" and t >= 0.7:
        state.update(x=0.5 + 0.34 * math.cos((t - 0.7) * 1.5),
                     y=0.5 + 0.34 * math.sin((t - 0.7) * 1.5))
    elif name in ("scroll_flick", "dropout"):
        state["scroll"] = 0.9 if 1 <= t < 1.4 else 0.7 if 1.4 <= t < 3 else 0.25 if 5 <= t < 6.5 else 0.5
    elif name == "jitter" and t >= 0.7:
        state.update(x=0.5 + 0.065 * math.sin(t * 13), y=0.5 + 0.065 * math.sin(t * 19),
                     scroll=0.5 + 0.065 * math.sin(t * 17))
    # Dropout stops delivery entirely, testing the independent output watchdog.
    state["deliver"] = not (name == "dropout" and 2 <= t < 3.2)
    return state


def raw_frame(sequence, timestamp_ms, state=None, *, session_id="mock-session", subject_id="mock-person",
              closed_value=1, rows=9, columns=9, vector_size=11):
    state = state or {"x": 0.5, "y": 0.5, "scroll": 0.5, "left": False, "right": False}
    return {
        "format": "raw_mouse_v1", "session_id": session_id, "subject_id": subject_id,
        "sequence": sequence, "timestamp_ms": timestamp_ms,
        "left_eye": closed_value if state["left"] else 1 - closed_value,
        "right_eye": closed_value if state["right"] else 1 - closed_value,
        "tongue": matrix(state["x"], state["y"], rows, columns),
        "gaze": matrix(state["x"], state["y"], rows, columns),
        "head_vertical": vector(state["scroll"], vector_size),
    }
