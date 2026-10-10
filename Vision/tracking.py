"""Conservative geometric association, not biometric identity recognition."""

from dataclasses import dataclass
from math import hypot

from .signals import finite_number


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        if not all(finite_number(v) for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("box coordinates must be finite")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("box must have positive area")

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2

    def overlaps(self, other):
        return (min(self.x + self.width, other.x + other.width) > max(self.x, other.x)
                and min(self.y + self.height, other.y + other.height) > max(self.y, other.y))


class SubjectTracker:
    """Retire IDs immediately on absence, ambiguity, restart, or a long gap.

    Retain an ID only for a reciprocal unique candidate. Overlapping observations
    receive fresh IDs on every frame until separate again. These deliberately
    conservative gates need real-camera evaluation before use with live controls.
    """

    def __init__(self, *, max_gap_ms=250.0, motion_ratio=0.6, scale_ratio=1.5):
        if not all(finite_number(x) and x > 0 for x in (max_gap_ms, motion_ratio, scale_ratio)):
            raise ValueError("tracking gates must be finite and positive")
        if scale_ratio < 1:
            raise ValueError("scale_ratio must be at least 1")
        self.max_gap_ms, self.motion_ratio, self.scale_ratio = max_gap_ms, motion_ratio, scale_ratio
        self._session = None
        self._previous = []
        self._next_id = 0
        self._timestamp = self._sequence = None

    def _candidate(self, old, new):
        scale = max(old.width / new.width, new.width / old.width,
                    old.height / new.height, new.height / old.height)
        distance = hypot(old.center[0] - new.center[0], old.center[1] - new.center[1])
        return (scale <= self.scale_ratio
                and distance <= self.motion_ratio * min(hypot(old.width, old.height),
                                                         hypot(new.width, new.height)))

    def update(self, envelope, boxes):
        envelope.frame([])  # Validate the clock/envelope before updating state.
        boxes = list(boxes)
        if len(boxes) > 2 or not all(isinstance(box, Box) for box in boxes):
            raise ValueError("tracker expects at most two Box observations")
        if envelope.session_id != self._session:
            self._session = envelope.session_id
            self._previous = []
            self._timestamp = self._sequence = None
            self._next_id = 0
        if self._timestamp is not None:
            if envelope.timestamp_ms < self._timestamp or envelope.sequence <= self._sequence:
                raise ValueError("tracker cannot consume old or duplicate frames")
            if envelope.timestamp_ms - self._timestamp > self.max_gap_ms:
                self._previous = []
        candidates = [
            [j for j, (_, old) in enumerate(self._previous) if self._candidate(old, box)]
            for box in boxes
        ]
        ambiguous = {
            i for i, box in enumerate(boxes)
            if any(i != j and box.overlaps(other) for j, other in enumerate(boxes))
        }
        result = []
        for i, box in enumerate(boxes):
            choices = candidates[i]
            if (i not in ambiguous and len(choices) == 1
                    and sum(choices[0] in options for options in candidates) == 1):
                subject = self._previous[choices[0]][0]
            else:
                subject = f"subject-{self._next_id}"
                self._next_id += 1
            result.append(subject)
        # Ambiguous boxes must not be eligible for association on the next frame.
        self._previous = [(subject, box) for i, (subject, box) in enumerate(zip(result, boxes))
                          if i not in ambiguous]
        self._timestamp, self._sequence = envelope.timestamp_ms, envelope.sequence
        return result
