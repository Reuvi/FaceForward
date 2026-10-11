"""Calibration-free binary mouth observation from existing face blendshapes."""

from .signals import invalid, measurement, unit_number, finite_number


def mouth_open(observation, width, height):
    score = observation.expressions.get("jawOpen")
    if not unit_number(score):
        return invalid()
    # A blendshape on an off-frame mouth is not usable button evidence.
    for index in (61, 291, 13, 14):
        if index >= len(observation.points):
            return invalid()
        x, y = observation.points[index]
        if not (finite_number(x) and finite_number(y) and 0 <= x < width and 0 <= y < height):
            return invalid()
    # Availability flag, not a probability of correct expression recognition.
    return measurement(int(score >= .5), 1)
