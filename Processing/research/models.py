"""Small local event classifiers with explicit train/validation trial separation."""

from math import exp, isfinite

GROUPS = dict(
    geometry=("duration_ms", "peak", "area", "close_speed", "open_speed"),
    blink=(
        "duration_ms",
        "peak",
        "area",
        "close_speed",
        "open_speed",
        "blink",
        "squint",
    ),
    face=(
        "duration_ms",
        "peak",
        "area",
        "close_speed",
        "open_speed",
        "blink",
        "squint",
        "cheek",
        "brow",
        "brow_gap",
        "cheek_gap",
        "pose_speed",
    ),
)


def predict(model, event):
    if any(event.get(k) is None for k in model["names"]):
        return None
    z = model["weights"][0] + sum(
        w * (event[k] - m) / s
        for k, m, s, w in zip(
            model["names"], model["mean"], model["scale"], model["weights"][1:]
        )
    )
    return 1 / (1 + exp(-max(-40, min(40, z))))


def validate_models(models):
    if not isinstance(models, dict) or set(models) - {"left", "right"}:
        raise ValueError("Invalid event models")
    for variants in models.values():
        if not isinstance(variants, dict) or set(variants) - set(GROUPS):
            raise ValueError("Invalid event model variant")
        for name, model in variants.items():
            if (
                not isinstance(model, dict)
                or set(model)
                != {"names", "mean", "scale", "weights", "validated", "report"}
                or not isinstance(model["names"], list)
                or tuple(model["names"]) != GROUPS[name]
            ):
                raise ValueError("Invalid model fields")
            if any(
                not isinstance(model[k], list)
                for k in ("names", "mean", "scale", "weights")
            ):
                raise ValueError("Model vectors must be lists")
            n = len(model["names"])
            if (
                len(model["mean"]) != n
                or len(model["scale"]) != n
                or len(model["weights"]) != n + 1
            ):
                raise ValueError("Invalid model dimensions")
            if not all(
                type(v) in (int, float) and isfinite(v)
                for k in ("mean", "scale", "weights")
                for v in model[k]
            ):
                raise ValueError("Nonfinite model")
            if (
                min(model["scale"]) <= 0
                or type(model["validated"]) is not bool
                or not isinstance(model["report"], dict)
            ):
                raise ValueError("Invalid model normalization")
    return models


def fit_models(events):
    import numpy as np

    result = {}
    reports = []
    events = [
        e
        for e in events
        if e.get("label") not in (None, "unlabeled")
        and e.get("role") in ("train", "validation")
    ]

    train_ids = {e.get("trial_id") for e in events if e.get("role") == "train"}
    validation_ids = {
        e.get("trial_id") for e in events if e.get("role") == "validation"
    }
    if None in train_ids | validation_ids or train_ids & validation_ids:
        raise ValueError(
            "Training and validation must use separate complete labeled trials"
        )
    for side in ("left", "right"):
        rows = [
            e
            for e in events
            if e.get("channel") == side and e.get("label") not in (None, "unlabeled")
        ]
        # Use the exact same complete events across all three comparisons.
        rows = [
            e
            for e in rows
            if all(
                type(e.get(k)) in (int, float) and isfinite(e[k])
                for k in GROUPS["face"]
            )
        ]
        train = [e for e in rows if e["role"] == "train"]
        test = [e for e in rows if e["role"] == "validation"]

        def positive(e):
            return e["label"] in (side + "_wink", "both_intentional")

        if (
            min(sum(positive(e) for e in train), sum(not positive(e) for e in train))
            < 6
            or min(sum(positive(e) for e in test), sum(not positive(e) for e in test))
            < 2
        ):
            reports.append(
                f"{side}: need ≥6 positive/negative training events and ≥2 each in separately recorded validation trials with all facial features"
            )
            continue
        result[side] = {}
        for name, names in GROUPS.items():
            x = np.asarray([[e[k] for k in names] for e in train])
            y = np.asarray([positive(e) for e in train], float)
            mean = x.mean(axis=0)
            scale = np.maximum(x.std(axis=0), 1e-6)
            x = np.column_stack((np.ones(len(x)), (x - mean) / scale))
            w = np.zeros(x.shape[1])
            weights = np.where(
                y == 1, 0.5 / max(y.mean(), 1e-6), 0.5 / max(1 - y.mean(), 1e-6)
            )
            for _ in range(400):
                prob = 1 / (1 + np.exp(-np.clip(x @ w, -40, 40)))
                grad = x.T @ ((prob - y) * weights) / len(y) + 0.03 * np.r_[0, w[1:]]
                w -= 0.08 * grad
            model = dict(
                names=list(names),
                mean=mean.tolist(),
                scale=scale.tolist(),
                weights=w.tolist(),
                validated=False,
                report={},
            )
            predictions = [predict(model, e) >= 0.5 for e in test]
            tp = sum(p and positive(e) for p, e in zip(predictions, test))
            fp = sum(p and not positive(e) for p, e in zip(predictions, test))
            fn = sum(not p and positive(e) for p, e in zip(predictions, test))
            tn = len(test) - tp - fp - fn
            model["report"] = dict(
                train_events=len(train),
                validation_events=len(test),
                tp=tp,
                fp=fp,
                fn=fn,
                tn=tn,
                train_trials=len({e["trial_id"] for e in train}),
                validation_trials=len({e["trial_id"] for e in test}),
            )
            model["validated"] = (
                min(tp + fn, tn + fp) >= 10 and fp == 0 and tp / max(1, tp + fn) >= 0.95
            )
            result[side][name] = model
            reports.append(
                f"{side} / {name}: TP {tp}, FP {fp}, FN {fn}, TN {tn}; "
                + (
                    "preview eligible"
                    if model["validated"]
                    else "more/better validation required"
                )
            )
    if not result:
        raise ValueError("\n".join(reports))
    return result, "\n".join(reports)
