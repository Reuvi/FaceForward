"""Continuous SignalFrame fixtures for all four mouse behaviors, never inference."""

import math

from .signals import Envelope, make_face, measurement


SUBJECT = "mouse-demo-person"


def mouse_demo_records(*, count=None, fps=30.0):
    """Repeat a 16-second, explicitly synthetic mouse exercise.

    Interleaved neutral periods allow deliberate arming. Includes a short blink,
    independent long winks, simultaneous independent closures, 2D pupil
    motion, and up/down head demand. No camera/model dependencies.
    """
    if count is not None and (type(count) is not int or count < 1):
        raise ValueError("count must be a positive integer or None")
    if type(fps) not in (int, float) or not math.isfinite(fps) or not 1 <= fps <= 120:
        raise ValueError("fps must be between 1 and 120")
    index = 0
    while count is None or index < count:
        t = (index / fps) % 16
        left = 1.5 <= t < 1.62 or 2 <= t < 2.7 or 4 <= t < 4.7
        right = 1.5 <= t < 1.62 or 3 <= t < 3.7 or 4 <= t < 4.7
        x = y = head = 0.5
        if 5 <= t < 9:
            angle = (t - 5) * math.pi / 2
            x, y = 0.5 + 0.32 * math.cos(angle), 0.5 + 0.32 * math.sin(angle)
        if 10 <= t < 11.5:
            head = 0.2
        elif 11.5 <= t < 13:
            head = 0.8
        values = {"left_eye_open": 0 if left else 1, "right_eye_open": 0 if right else 1,
                  "gaze_x": x, "gaze_y": y,
                  "head_x": 0.5, "head_y": head}
        yield Envelope("synthetic-mouse-recording", index, index * 1000 / fps).frame([
            make_face(SUBJECT, {name: measurement(value, 1) for name, value in values.items()})
        ])
        index += 1
