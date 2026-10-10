"""Selected-face scalar measurements for local experiments; no action decisions."""

from math import atan2, asin, hypot, log

from .landmarks import EYES
from .geometry import eye_ratios, midpoint, sub

EXPRESSION_NAMES = tuple(
    prefix + side
    for prefix in (
        "eyeBlink",
        "eyeSquint",
        "cheekSquint",
        "browDown",
        "eyeWide",
        "mouthSmile",
        "eyeLookUp",
        "eyeLookDown",
        "eyeLookIn",
        "eyeLookOut",
    )
    for side in ("Left", "Right")
) + ("browInnerUp", "jawOpen")


def feature_frame(core):
    """Match the exact current capture, selected track and calibration generation."""
    if core.frame is None or core.selected not in core.observations:
        return None
    obs = core.observations[core.selected]
    values = {name: None for name in EXPRESSION_NAMES}
    face_ok = (
        core.features.get("face") is not None and core.features["face"].quality > 0
    )
    if face_ok:
        values.update({k: v for k, v in obs.expressions.items() if k in values})
    values.update(
        yaw=None, pitch=None, roll=None, face_x=None, face_y=None, face_scale=None
    )
    if face_ok:
        values.update(
            face_x=obs.box.x + obs.box.width / 2,
            face_y=obs.box.y + obs.box.height / 2,
            face_scale=log(max(1e-6, obs.box.width)),
        )
        if obs.rotation is not None:
            r = obs.rotation
            # R = Rz(roll) Ry(yaw) Rx(pitch); camera axes, unmirrored input.
            values.update(
                yaw=asin(max(-1, min(1, -float(r[2][0])))),
                pitch=atan2(r[2][1], r[2][2]),
                roll=atan2(r[1][0], r[0][0]),
            )
    for side, (corners, pairs, iris) in EYES.items():
        feature = core.features.get(side)
        usable = (
            face_ok
            and feature is not None
            and feature.quality > 0
            and feature.value is not None
        )
        values[side + "_quality"] = feature.quality if feature else 0
        values[side + "_ratio"] = feature.value if usable else None
        values[side + "_closure"] = None
        values[side + "_eye_known"] = 0
        fit = core.eyes.get(side)
        if fit and usable:
            values[side + "_eye_known"] = int(
                fit.classify(feature.value, feature.quality)["valid"]
            )
            opened = fit.open_limit if fit.open_limit is not None else fit.opened
            closed = fit.closed_limit if fit.closed_limit is not None else fit.closed
            values[side + "_closure"] = max(
                0, min(1, (opened - feature.value) / (opened - closed))
            )
        for name in ("iris_x", "iris_y", "brow_gap", "cheek_gap"):
            values[side + "_" + name] = None
        for name in EXPRESSION_NAMES:
            if name.endswith(side.title()) and not usable:
                values[name] = None
        if usable:
            a, b = [obs.points[i] for i in corners]
            center = midpoint(a, b)
            span = hypot(a[0] - b[0], a[1] - b[1])
            brow, cheek = (282, 425) if side == "left" else (52, 205)
            for label, index in (("brow_gap", brow), ("cheek_gap", cheek)):
                p = obs.points[index]
                values[side + "_" + label] = (
                    hypot(p[0] - center[0], p[1] - center[1]) / span
                )
            if (
                fit
                and fit.classify(feature.value, feature.quality)["value"] == 1
                and len(obs.points) >= 478
            ):
                try:
                    down = sub(midpoint(obs.points[61], obs.points[291]), center)
                    iris_center = tuple(
                        sum(obs.points[i][j] for i in iris) / 4 for j in (0, 1)
                    )
                    ratios = eye_ratios(
                        a,
                        b,
                        [(obs.points[i], obs.points[j]) for i, j in pairs],
                        iris_center,
                        down,
                    )
                    values[side + "_iris_x"], values[side + "_iris_y"] = (
                        ratios.horizontal,
                        ratios.vertical,
                    )
                except ValueError:
                    pass
    return dict(
        format="face_features_v1",
        session_id=core.frame["session_id"],
        sequence=core.frame["sequence"],
        timestamp_ms=core.frame["timestamp_ms"],
        subject_id=core.selected,
        generation=core.generation,
        values=values,
    )
