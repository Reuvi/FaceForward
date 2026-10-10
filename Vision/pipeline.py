"""Vision-local wiring and an explicit, session/subject-bound calibration hook."""

from dataclasses import dataclass

from .calibration import EyeCalibration, calibrated_eye, combine_gaze
from .signals import make_face, unit_number
from .tracking import SubjectTracker


@dataclass(frozen=True)
class EyeBinding:
    """App must deliberately bind calibration and a validated quality assessor.

    quality_assessor(observation) returns left/right measurement quality scores;
    MediaPipe task thresholds are not scores and are never substituted here.
    This Python API is Vision-local, not an agreed shared profile schema.
    """

    session_id: str
    subject_id: str
    left: EyeCalibration | None
    right: EyeCalibration | None
    quality_assessor: object
    disagreement_tolerance: float
    allow_single_eye: bool = False

    def __post_init__(self):
        if not self.session_id or not self.subject_id or not callable(self.quality_assessor):
            raise ValueError("binding requires explicit session, subject, and quality assessor")
        if not unit_number(self.disagreement_tolerance):
            raise ValueError("disagreement_tolerance must be in [0, 1]")
        if type(self.allow_single_eye) is not bool:
            raise ValueError("allow_single_eye must be boolean")


class VisionPipeline:
    def __init__(self, tracker=None):
        self.tracker = SubjectTracker() if tracker is None else tracker
        self.binding = None

    def bind(self, binding):
        if not isinstance(binding, EyeBinding):
            raise TypeError("expected EyeBinding")
        self.binding = binding

    def process(self, captured, observations):
        observations = list(observations)
        try:
            ids = self.tracker.update(captured.envelope, [item.box for item in observations])
        except Exception:
            self.binding = None
            raise
        if self.binding is not None and (
            self.binding.session_id != captured.envelope.session_id
            or self.binding.subject_id not in ids
        ):
            self.binding = None
        faces = []
        for subject, observation in zip(ids, observations):
            values = {}
            if self.binding is not None and subject == self.binding.subject_id:
                binding = self.binding
                try:
                    quality = binding.quality_assessor(observation)
                    left = calibrated_eye(observation.eyes.get("left"), binding.left, quality.get("left"))
                    right = calibrated_eye(observation.eyes.get("right"), binding.right, quality.get("right"))
                    values = {
                        "left_eye_open": left["open"], "right_eye_open": right["open"],
                        **combine_gaze(left, right,
                                       disagreement_tolerance=binding.disagreement_tolerance,
                                       allow_single_eye=binding.allow_single_eye),
                    }
                except Exception:
                    # A failing assessor must not preserve usable calibration.
                    self.binding = None
                    raise
            faces.append(make_face(subject, values))
        return captured.envelope.frame(faces)
