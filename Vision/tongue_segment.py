"""Local pinned YOLOv8 tongue masks. No network, color fitting or stale reuse."""
from pathlib import Path
from time import perf_counter
import hashlib

import cv2
import numpy as np

from .tongue import TongueModel, TongueResult
from .tongue_tip import estimate_tip

MEASUREMENT = "onnx_tip_mouth_width_v1"
MODEL_SHA256 = "885ecd06ec97fee5ed3959c85590c7a3dc3d10f134c7dc821c3b99f45506c35e"
DEFAULT_MODEL = Path("Vision/.local/tongue_seg.onnx")


def decode_mask(outputs, size=160, threshold=.55):
    """Decode one-class, 32-prototype, fixed 640px YOLOv8-seg outputs."""
    if len(outputs) != 2:
        raise ValueError("Tongue model must have prediction and prototype outputs")
    predictions, prototypes = (np.asarray(v) for v in outputs)
    if predictions.shape != (1, 37, 8400) or prototypes.shape != (1, 32, 160, 160):
        raise ValueError("Unsupported tongue model output shapes")
    if not all(np.isfinite(v).all() for v in (predictions, prototypes)):
        raise ValueError("Nonfinite tongue model output")
    rows = predictions[0].T
    candidates = rows[rows[:, 4] >= threshold]
    if len(candidates) == 0:
        return None, 0., "No tongue detected"
    candidates = candidates[np.argsort(-candidates[:, 4])[:100]]
    boxes = np.column_stack((candidates[:, 0]-candidates[:, 2]/2,
                             candidates[:, 1]-candidates[:, 3]/2,
                             candidates[:, 2], candidates[:, 3]))
    keep = np.asarray(cv2.dnn.NMSBoxes(boxes.tolist(), candidates[:, 4].tolist(), threshold, .45)).reshape(-1)
    if not len(keep):
        return None, 0., "No supported tongue box"
    if len(keep) > 1:
        return None, float(candidates[keep[0], 4]), "Multiple tongue detections; keep one visible tip"
    row = candidates[keep[0]]
    logits = row[5:] @ prototypes[0].reshape(32, -1)
    mask = (logits.reshape(160, 160) > 0).astype(np.uint8)*255
    x, y, w, h = boxes[keep[0]]/4
    support = np.zeros_like(mask)
    x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
    x1, y1 = min(160, int(np.ceil(x+w))), min(160, int(np.ceil(y+h)))
    if x1 <= x0 or y1 <= y0:
        return None, 0., "Tongue box is outside crop"
    support[y0:y1, x0:x1] = 255
    return cv2.resize(mask & support, (size, size), interpolation=cv2.INTER_NEAREST), float(row[4]), "Tongue mask available"


def mask_result(mask, crop, config, confidence):
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    candidates = sorted(range(1, count), key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)
    if not candidates:
        return TongueResult(reason="Tongue box has no supported mask", mask=mask, candidate_present=True)
    best = candidates[0]
    fraction = float(stats[best, cv2.CC_STAT_AREA]/mask.size)
    if not config.tongue_min_area <= fraction <= config.tongue_max_area:
        return TongueResult(reason="Tongue mask size unsupported; expose the tip clearly", mask=mask,
                            candidate_present=True, area_fraction=fraction)
    if len(candidates) > 1 and stats[candidates[1], cv2.CC_STAT_AREA] > config.tongue_ambiguity*stats[best, cv2.CC_STAT_AREA]:
        return TongueResult(reason="Tongue mask has ambiguous disconnected regions", mask=mask, candidate_present=True)
    selected = (labels == best).astype(np.uint8)*255
    tip = estimate_tip(selected, crop.inner_mask, crop.mouth_pixels, config)
    return TongueResult(xy=crop.raw_point(tip.point) if tip.point else None,
                        quality=min(confidence, tip.quality), reason=tip.reason, mask=selected,
                        area_fraction=fraction, candidate_present=True,
                        centroid=crop.raw_point(centers[best]),
                        attachment=crop.raw_point(tip.attachment) if tip.attachment else None,
                        edge=tip.edge, extension=tip.extension)


class SegmentedTongueModel(TongueModel):
    """Lazy CPU inference on the capture worker, one result per current image."""
    measurement = MEASUREMENT

    def __init__(self, path=None):
        self.path = Path(path or DEFAULT_MODEL).expanduser().resolve()
        self.session = None
        self.load_error = None
        self.report = {"backend": "YOLOv8n-seg · local CPU", "model_sha256": MODEL_SHA256,
                       "inference_ms": None, "confidence": None, "error": None}
        self.reset_tracking()

    def verify_file(self):
        if not self.path.is_file():
            raise ValueError("Local tongue model missing. Run python -m Vision.setup_tongue_model or choose its ONNX file.")
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("Tongue model checksum differs from the supported release")

    def _load(self):
        self.verify_file()
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ValueError("Install Vision/requirements-tongue.txt in the app's Python environment") from exc
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(self.path), sess_options=options, providers=["CPUExecutionProvider"])
        if self.session.get_inputs()[0].shape != [1, 3, 640, 640]:
            self.session = None
            raise ValueError("Unsupported tongue model input shape")

    def _detect(self, crop, config):
        started = perf_counter()
        try:
            if self.load_error is not None:
                raise ValueError(self.load_error)
            if self.session is None:
                try:
                    self._load()
                except Exception as exc:
                    self.load_error = str(exc)
                    raise
            rgb = cv2.cvtColor(cv2.resize(crop.bgr, (640, 640)), cv2.COLOR_BGR2RGB)
            tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)/255.
            outputs = self.session.run(None, {self.session.get_inputs()[0].name: tensor})
            mask, confidence, reason = decode_mask(outputs, crop.bgr.shape[0])
            self.report.update(confidence=confidence, error=None)
            if mask is None:
                return TongueResult(reason=reason, candidate_present=confidence >= .55)
            return mask_result(mask, crop, config, confidence)
        except Exception as exc:
            # Do not kill the camera/other detectors, and never fall back to color.
            self.report.update(confidence=None, error=str(exc))
            return TongueResult(reason="Tongue model unavailable: " + str(exc))
        finally:
            self.report["inference_ms"] = (perf_counter()-started)*1000
