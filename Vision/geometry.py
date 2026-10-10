"""Face-relative pixel geometry. These raw ratios are not control values."""

from dataclasses import dataclass
from math import hypot
from statistics import median

from .signals import finite_number


def point(value):
    if len(value) != 2 or not all(finite_number(v) for v in value):
        raise ValueError("expected a finite 2D pixel point")
    return tuple(value)


def sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def midpoint(a, b):
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


@dataclass(frozen=True)
class Reference:
    origin: tuple
    right: tuple
    down: tuple
    width: float


def reference(left, right, down_hint, *, origin=None):
    left, right, down_hint = point(left), point(right), point(down_hint)
    delta = sub(right, left)
    width = hypot(*delta)
    if width < 1e-6:
        raise ValueError("reference width is degenerate")
    axis = delta[0] / width, delta[1] / width
    down = -axis[1], axis[0]
    if abs(dot(down, down_hint)) < 1e-6:
        raise ValueError("downward direction is ambiguous")
    if dot(down, down_hint) < 0:
        down = -down[0], -down[1]
    return Reference(midpoint(left, right) if origin is None else point(origin), axis, down, width)


@dataclass(frozen=True)
class EyeRatios:
    horizontal: float
    vertical: float
    openness: float


def eye_ratios(left_corner, right_corner, lid_pairs, iris, down_hint):
    frame = reference(left_corner, right_corner, down_hint)
    if not lid_pairs:
        raise ValueError("eyelid observations are missing")
    gaps = [hypot(*sub(point(upper), point(lower))) for upper, lower in lid_pairs]
    offset = sub(point(iris), frame.origin)
    return EyeRatios(
        0.5 + dot(offset, frame.right) / frame.width,
        dot(offset, frame.down) / frame.width,
        median(gaps) / frame.width,
    )


def tongue_ratios(left_corner, right_corner, upper_lip, lower_lip, centroid, down_hint):
    """Requires a real detector's centroid; never substitutes a mouth landmark."""
    frame = reference(left_corner, right_corner, down_hint)
    upper_lip, lower_lip, centroid = point(upper_lip), point(lower_lip), point(centroid)
    height = dot(sub(lower_lip, upper_lip), frame.down)
    if height < 1e-6:
        raise ValueError("mouth opening is degenerate")
    x = 0.5 + dot(sub(centroid, frame.origin), frame.right) / frame.width
    y = dot(sub(centroid, upper_lip), frame.down) / height
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise ValueError("tongue centroid is outside the v1 mouth domain")
    return x, y
