"""Independent frame appearance models. No duration, speed or opposite-eye input."""

from copy import deepcopy
from math import dist, exp

from .landmarks import EYES
from .signals import finite_number

NAMES = (
    "lid_ratio",
    "blink",
    "squint",
    "cheek",
    "brow",
    "wide",
    "brow_gap",
    "cheek_gap",
)
FLOORS = (0.015, 0.03, 0.03, 0.03, 0.03, 0.03, 0.025, 0.025)


def measure(observation, features):
    """Coefficients describe visible facial shape, not measured muscle force."""
    result = {}
    for side, (corners, _, _) in EYES.items():
        feature = features.get(side)
        if feature is None or feature.quality <= 0 or feature.value is None:
            result[side] = None
            continue
        points = observation.points
        a, b = [points[i] for i in corners]
        width = dist(a, b)
        center = tuple((x + y) / 2 for x, y in zip(a, b))
        brow, cheek = (282, 425) if side == "left" else (52, 205)
        coefficients = [
            observation.expressions.get(name + side.title())
            for name in ("eyeBlink", "eyeSquint", "cheekSquint", "browDown", "eyeWide")
        ]
        if (
            width <= 0
            or len(points) <= max(brow, cheek)
            or not all(finite_number(v) and 0 <= v <= 1 for v in coefficients)
        ):
            result[side] = None
            continue
        vector = [
            feature.value,
            *coefficients,
            dist(points[brow], center) / width,
            dist(points[cheek], center) / width,
        ]
        result[side] = vector if all(finite_number(v) for v in vector) else None
    return result


def score(model, vector):
    if (
        vector is None
        or len(vector) != len(NAMES)
        or not all(finite_number(v) for v in vector)
    ):
        return None
    # Unsupported appearance is unknown, even if the linear extrapolation is large.
    if any(v < lo or v > hi for v, lo, hi in zip(vector, model["low"], model["high"])):
        return None
    z = model["weights"][0] + sum(
        w * (v - m) / s
        for w, v, m, s in zip(
            model["weights"][1:], vector, model["mean"], model["scale"]
        )
    )
    return 1 / (1 + exp(-max(-40, min(40, z))))


def classify(model, vector):
    value = score(model, vector)
    if value is None:
        return None
    return 1 if value >= model["on"] else 0 if value <= model["off"] else None


def fit(negative_groups, positive_groups):
    """Learn open versus closed-action appearance with equal group/class weight."""
    import numpy as np

    groups = [(0, g) for g in negative_groups] + [(1, g) for g in positive_groups]
    if (
        len(positive_groups) < 1
        or len(negative_groups) < 1
        or any(len(g) < 3 for _, g in groups)
    ):
        raise ValueError(
            "Need clear open and closed-action samples"
        )
    x = np.asarray([v for _, g in groups for v in g], float)
    y = np.asarray([label for label, g in groups for _ in g], float)
    if x.shape[1:] != (len(NAMES),) or not np.isfinite(x).all():
        raise ValueError("Incomplete facial measurements")
    weight = np.asarray(
        [
            0.5 / (len(positive_groups) if label else len(negative_groups)) / len(g)
            for label, g in groups
            for _ in g
        ]
    )
    mean = (x * weight[:, None]).sum(0)
    scale = np.maximum(np.sqrt(((x - mean) ** 2 * weight[:, None]).sum(0)), FLOORS)
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    w = np.zeros(design.shape[1])
    for _ in range(300):
        probability = 1 / (1 + np.exp(-np.clip(design @ w, -40, 40)))
        w -= 0.2 * (design.T @ ((probability - y) * weight) + 0.02 * np.r_[0, w[1:]])
    model = dict(
        names=list(NAMES),
        mean=mean.tolist(),
        scale=scale.tolist(),
        weights=w.tolist(),
        low=(x.min(0) - 3 * scale).tolist(),
        high=(x.max(0) + 3 * scale).tolist(),
        off=0.35,
        on=0.65,
        report={},
    )
    negative = [score(model, v) for label, g in groups if not label for v in g]
    positive = [score(model, v) for label, g in groups if label for v in g]
    low, high = max(negative), float(np.quantile(positive, 0.05))
    if high - low < 0.15:
        raise ValueError(
            "Open and closed-action appearances overlap; retry this eye"
        )
    model.update(off=low + (high - low) * 0.3, on=low + (high - low) * 0.7)
    return model


def check(model, negative_groups, positive_groups):
    """Fresh prompt windows only. Unknown counts against successful recognition."""
    if (
        len(positive_groups) < 1
        or len(negative_groups) < 1
        or any(len(g) < 3 for g in positive_groups + negative_groups)
    ):
        raise ValueError("Need fresh open and closed-action checks")
    positive = [classify(model, v) for g in positive_groups for v in g]
    negative = [classify(model, v) for g in negative_groups for v in g]
    report = dict(
        wink_frames=len(positive),
        nonwink_frames=len(negative),
        wink_recognized=sum(v == 1 for v in positive),
        false_wink_frames=sum(v == 1 for v in negative),
        nonwink_recognized=sum(v == 0 for v in negative),
        wink_attempts=len(positive_groups),
        negative_windows=len(negative_groups),
    )
    passed = (
        report["false_wink_frames"] == 0
        and all(
            sum(classify(model, v) == 1 for v in g) / len(g) >= 0.9
            for g in positive_groups
        )
        and all(
            sum(classify(model, v) == 0 for v in g) / len(g) >= 0.8
            for g in negative_groups
        )
    )
    if not passed:
        raise ValueError(
            f"Check failed: {report['false_wink_frames']} false wink frames; "
            f"{report['wink_recognized']}/{len(positive)} wink frames recognized"
        )
    model["report"] = report
    return model


def validate_models(models):
    if not isinstance(models, dict) or set(models) - {"left", "right"}:
        raise ValueError("Invalid wink model sides")
    fields = {"names", "mean", "scale", "weights", "low", "high", "off", "on", "report"}
    report_fields = {
        "wink_frames",
        "nonwink_frames",
        "wink_recognized",
        "false_wink_frames",
        "nonwink_recognized",
        "wink_attempts",
        "negative_windows",
    }
    for model in models.values():
        if (
            not isinstance(model, dict)
            or set(model) != fields
            or model["names"] != list(NAMES)
        ):
            raise ValueError("Unsupported wink appearance model")
        for key in ("mean", "scale", "weights", "low", "high"):
            vector = model[key]
            if (
                not isinstance(vector, list)
                or len(vector) != len(NAMES) + (key == "weights")
                or not all(finite_number(v) and abs(v) < 1e6 for v in vector)
            ):
                raise ValueError("Invalid wink model dimensions/values")
        if (
            min(model["scale"]) < 0.001
            or any(a >= b for a, b in zip(model["low"], model["high"]))
            or not all(finite_number(model[k]) for k in ("off", "on"))
            or not 0 <= model["off"] < model["on"] <= 1
        ):
            raise ValueError("Invalid wink model decision bounds")
        report = model["report"]
        if (
            not isinstance(report, dict)
            or set(report) != report_fields
            or any(type(v) is not int or not 0 <= v <= 100000 for v in report.values())
        ):
            raise ValueError("Invalid wink validation report")
        if (
            report["wink_attempts"] < 1
            or report["negative_windows"] < 1
            or report["wink_frames"] < 3
            or report["nonwink_frames"] < 3
            or report["false_wink_frames"] != 0
            or not 0.9 * report["wink_frames"]
            <= report["wink_recognized"]
            <= report["wink_frames"]
            or not 0.8 * report["nonwink_frames"]
            <= report["nonwink_recognized"]
            <= report["nonwink_frames"]
        ):
            raise ValueError("Wink model has not passed its calibration check")
    return deepcopy(models)
