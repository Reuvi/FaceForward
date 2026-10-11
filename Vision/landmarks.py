"""MediaPipe adapter and pixel diagnostics. No inferred per-signal confidence."""

from dataclasses import dataclass, field
from pathlib import Path

from .geometry import eye_ratios, midpoint, reference, sub
from .signals import finite_number
from .tracking import Box


# Anatomical sides for unmirrored input, checked against MediaPipe's official
# face_mesh_connections.py. Each corner pair points toward the user's right.
EYES = {
    "left": ((263, 362), ((386, 374), (385, 380), (387, 373)), (474, 475, 476, 477)),
    "right": ((133, 33), ((159, 145), (160, 144), (158, 153)), (469, 470, 471, 472)),
}


INNER_LIP = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324,
             308, 415, 310, 311, 312, 13, 82, 81, 80, 191)
# Ordered outer ring from MediaPipe FaceLandmarksConnections.FACE_LANDMARKS_LIPS.
OUTER_LIP = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375,
             291, 409, 270, 269, 267, 0, 37, 39, 40, 185)


@dataclass
class Observation:
    box: Box
    points: tuple
    head_reference: object = None
    eyes: dict = field(default_factory=dict)
    # Optional detector-only diagnostics. Legacy camera users do not request pose.
    rotation: object = None
    expressions: dict = field(default_factory=dict)


def observation_from_landmarks(landmarks, width, height):
    if width <= 0 or height <= 0 or len(landmarks) < 468:
        raise ValueError("incomplete face landmarks or invalid image dimensions")
    pixels = tuple((float(item.x) * width, float(item.y) * height) for item in landmarks)
    if not all(finite_number(v) for p in pixels for v in p):
        raise ValueError("nonfinite face landmark")
    # Normalize only the tracker box, not the geometry calculations.
    xs, ys = [p[0] / width for p in pixels[:468]], [p[1] / height for p in pixels[:468]]
    box = Box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    result = Observation(box, pixels)

    def visible(index):
        x, y = pixels[index]
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError("reference landmark is outside image")
        return x, y

    try:
        left = midpoint(visible(263), visible(362))
        right = midpoint(visible(33), visible(133))
        nose = visible(168)
        down = sub(midpoint(visible(61), visible(291)), midpoint(left, right))
        result.head_reference = reference(left, right, down, origin=nose)
    except ValueError:
        return result
    if len(pixels) < 478:
        return result
    for name, (corners, pairs, iris_indices) in EYES.items():
        try:
            iris_points = [visible(i) for i in iris_indices]
            iris = tuple(sum(p[axis] for p in iris_points) / len(iris_points) for axis in (0, 1))
            eye_frame = reference(visible(corners[0]), visible(corners[1]), down)
            if eye_frame.width < 4:
                continue  # Insufficient pixel geometry, not a confidence estimate.
            result.eyes[name] = eye_ratios(
                visible(corners[0]), visible(corners[1]),
                [(visible(a), visible(b)) for a, b in pairs], iris, down,
            )
        except ValueError:
            continue
    return result


LAB_TRACKING_CONFIDENCE = .35


class MediaPipeDetector:
    """Synchronous VIDEO mode: one inference in flight, one person's face."""

    def __init__(self, model_path, *, include_pose=False, include_expressions=False,
                 min_face_presence_confidence=.5, min_tracking_confidence=.5):
        self.model_path = Path(model_path).expanduser()
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Face Landmarker model not found: {self.model_path}")
        self.landmarker = None
        self.include_pose = include_pose
        self.include_expressions = include_expressions
        self.confidence_options = dict(
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        if any(not finite_number(v) or not 0 <= v <= 1 for v in self.confidence_options.values()):
            raise ValueError("Face confidence floors must be finite values in [0, 1]")
        self._session = self._sequence = self._capture_time = self._inference_time = None

    def __enter__(self):
        import cv2
        import mediapipe as mp
        self.cv2, self.mp = cv2, mp
        self.options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(self.model_path),
                delegate=mp.tasks.BaseOptions.Delegate.CPU,
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=self.include_pose,
            output_face_blendshapes=self.include_expressions,
            **self.confidence_options,
        )
        self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(self.options)
        return self

    def detect(self, captured):
        if self.landmarker is None:
            raise RuntimeError("detector is not open")
        envelope = captured.envelope
        envelope.frame([])
        if self._session is not None and envelope.session_id != self._session:
            self.close()
            self.landmarker = self.mp.tasks.vision.FaceLandmarker.create_from_options(self.options)
            self._sequence = self._capture_time = self._inference_time = None
        if self._sequence is not None and (
            envelope.sequence <= self._sequence or envelope.timestamp_ms < self._capture_time
        ):
            raise ValueError("detector cannot consume old or duplicate frames")
        # VIDEO requires strictly increasing integer ms. Quantization changes only
        # the private inference timestamp, never the original capture envelope.
        timestamp = int(envelope.timestamp_ms)
        if self._inference_time is not None:
            timestamp = max(timestamp, self._inference_time + 1)
        rgb = self.cv2.cvtColor(captured.bgr, self.cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(image, timestamp)
        self._session, self._sequence = envelope.session_id, envelope.sequence
        self._capture_time, self._inference_time = envelope.timestamp_ms, timestamp
        height, width = captured.bgr.shape[:2]
        if len(result.face_landmarks) > 1:
            raise ValueError("detector exceeded the single-face limit")
        observations = [observation_from_landmarks(face, width, height) for face in result.face_landmarks]
        if self.include_pose:
            from .features import rotation_from_matrix
            matrices = getattr(result, "facial_transformation_matrixes", ())
            if len(matrices) == len(observations):
                for observation, matrix in zip(observations, matrices):
                    observation.rotation = rotation_from_matrix(matrix)
        if getattr(self,"include_expressions",False):
            groups = getattr(result, "face_blendshapes", ())
            if len(groups) == len(observations):
                for observation, categories in zip(observations, groups):
                    observation.expressions = {c.category_name: float(c.score) for c in categories
                                              if finite_number(c.score) and 0 <= c.score <= 1}
        return observations

    def close(self):
        if self.landmarker is not None:
            self.landmarker.close()
            self.landmarker = None

    def __exit__(self, *exc):
        self.close()
