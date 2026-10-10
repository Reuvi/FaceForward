"""Calibrated binocular viewport regression; no absolute OS pointer injection."""

from math import isfinite

BASE = (
    "left_iris_x",
    "left_iris_y",
    "right_iris_x",
    "right_iris_y",
    "yaw",
    "pitch",
    "roll",
    "face_x",
    "face_y",
    "face_scale",
)


def vector(values, variant="interaction"):
    keys = BASE[:4] if variant == "eyes" else BASE
    x = [values.get(k) for k in keys]
    if not all(type(v) in (float, int) and isfinite(v) for v in x):
        return None
    if variant == "interaction":
        x += [(x[0] + x[2]) / 2 * x[4], (x[1] + x[3]) / 2 * x[5]]
    return x


def predict(model, values, *, check_domain=True):
    import numpy as np

    x = vector(values, model["variant"])
    if x is None:
        return None
    if check_domain and any(
        v < a - 0.1 * max(b - a, 0.02) or v > b + 0.1 * max(b - a, 0.02)
        for v, a, b in zip(x, model["low"], model["high"])
    ):
        return None
    row = np.r_[1, (np.asarray(x) - model["mean"]) / model["scale"]]
    return (row @ np.asarray(model["weights"])).tolist()


def validate_model(model):
    if model is None:
        return None
    fields = {
        "variant",
        "mean",
        "scale",
        "weights",
        "low",
        "high",
        "viewport",
        "report",
    }
    if (
        not isinstance(model, dict)
        or set(model) != fields
        or model["variant"] not in ("eyes", "pose", "interaction")
    ):
        raise ValueError("Invalid gaze model")
    if any(
        not isinstance(model[k], list)
        for k in ("mean", "scale", "weights", "low", "high", "viewport")
    ) or any(not isinstance(w, list) for w in model["weights"]):
        raise ValueError("Invalid gaze arrays")
    n = {"eyes": 4, "pose": 10, "interaction": 12}[model["variant"]]
    if (
        any(len(model[k]) != n for k in ("mean", "scale", "low", "high"))
        or len(model["weights"]) != n + 1
        or any(len(w) != 2 for w in model["weights"])
    ):
        raise ValueError("Invalid gaze model dimensions")
    numbers = sum((model[k] for k in ("mean", "scale", "low", "high")), []) + sum(
        model["weights"], []
    )
    if (
        not all(type(v) in (int, float) and isfinite(v) for v in numbers)
        or min(model["scale"]) <= 0
        or any(a > b for a, b in zip(model["low"], model["high"]))
    ):
        raise ValueError("Invalid gaze normalization")
    if len(model["viewport"]) != 2 or any(
        type(v) is not int or not 100 <= v <= 20000 for v in model["viewport"]
    ):
        raise ValueError("Invalid viewport")
    if not isinstance(model["report"], dict):
        raise ValueError("Invalid gaze report")
    return model


def evaluate(model, episodes):
    import numpy as np

    errors = []
    outside = 0
    for episode in episodes:
        prediction = predict(model, episode["values"], check_domain=False)
        if prediction is None:
            continue
        if predict(model, episode["values"]) is None:
            outside += 1
        error = np.linalg.norm(
            (np.asarray(prediction) - episode["target"]) * model["viewport"]
        )
        errors.append(float(error))  # Deliberately before clipping to [0,1].
    return dict(
        episodes=len(episodes),
        usable=len(errors),
        outside=outside,
        targets=len({tuple(e["target"]) for e in episodes}),
        poses=len({e["pose"] for e in episodes}),
        median_px=float(np.median(errors)) if errors else None,
        p95_px=float(np.percentile(errors, 95)) if errors else None,
    )


def fit_gaze(episodes, viewport):
    import numpy as np

    train = [e for e in episodes if e["role"] == "train"]
    test = [e for e in episodes if e["role"] == "validation"]
    if (
        len(train) < 18
        or len(test) < 9
        or min(len({tuple(e["target"]) for e in group}) for group in (train, test)) < 9
    ):
        raise ValueError(
            "Need all nine targets in training and validation; at least 18 training and 9 validation fixation episodes"
        )
    # Every episode is one average, so longer/higher-rate fixations cannot dominate.
    results = {}
    report = []
    for variant in ("eyes", "pose", "interaction"):
        x = np.asarray([vector(e["values"], variant) for e in train], float)
        y = np.asarray([e["target"] for e in train])
        if x.ndim != 2 or not np.isfinite(x).all():
            raise ValueError("Gaze training needs complete binocular/pose samples")
        mean = x.mean(axis=0)
        scale = np.maximum(x.std(axis=0), 1e-6)
        z = np.column_stack((np.ones(len(x)), (x - mean) / scale))
        # Tune using complete training episodes; the declared validation set stays held out.
        fold = np.arange(len(x)) % 3
        best = None
        for alpha in (0.1, 1.0, 10.0):
            loss = []
            for f in range(3):
                mask = fold != f
                penalty = np.diag([0] + [alpha] * (z.shape[1] - 1))
                w = np.linalg.lstsq(
                    np.vstack((z[mask], np.sqrt(penalty))),
                    np.vstack((y[mask], np.zeros((z.shape[1], 2)))),
                    rcond=None,
                )[0]
                loss.extend(np.sum((z[~mask] @ w - y[~mask]) ** 2, axis=1))
            score = float(np.mean(loss))
            if best is None or score < best[0]:
                best = (score, alpha)
        penalty = np.diag([0] + [best[1]] * (z.shape[1] - 1))
        w = np.linalg.lstsq(
            np.vstack((z, np.sqrt(penalty))),
            np.vstack((y, np.zeros((z.shape[1], 2)))),
            rcond=None,
        )[0]
        model = dict(
            variant=variant,
            mean=mean.tolist(),
            scale=scale.tolist(),
            weights=w.tolist(),
            low=x.min(axis=0).tolist(),
            high=x.max(axis=0).tolist(),
            viewport=list(viewport),
            report={},
        )
        model["report"] = evaluate(model, test)
        model["report"]["ridge"] = best[1]
        results[variant] = model
        report.append(
            f"{variant}: median {model['report']['median_px']:.1f}px / p95 {model['report']['p95_px']:.1f}px; outside domain {model['report']['outside']}/{len(test)}"
        )
    # Prefer the simpler pose model unless interactions improve held-out error.
    selected = min(
        ("pose", "interaction"), key=lambda k: results[k]["report"]["p95_px"]
    )
    result = results[selected]
    result["report"]["eyes_p95_px"] = results["eyes"]["report"]["p95_px"]
    result["report"]["beats_eyes"] = (
        result["report"]["p95_px"] < results["eyes"]["report"]["p95_px"]
    )
    return result, "\n".join(report)
