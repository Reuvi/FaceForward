from copy import deepcopy
from math import isfinite

SOURCES = ("left_eye", "right_eye", "both_eyes", "smile", "brow", "dwell", "disabled")
DEFAULTS = dict(
    policy="independent",
    click_mode="release",
    pointer_mode="tongue",
    scroll_enabled=True,
    activation=0.75,
    release=0.35,
    open_ms=80.0,
    cooldown_ms=200.0,
    stale_ms=250.0,
    left_min_ms=320.0,
    right_min_ms=320.0,
    max_ms=1200.0,
    model="rules",
    left_source="left_eye",
    right_source="right_eye",
    dwell_ms=900.0,
    dwell_radius=0.025,
    head_center_x=0.5,
    head_center_y=0.5,
    head_range=0.15,
    head_deadzone=0.12,
    motion_limit=3.0,
    recovery_ms=100.0,
    gaze_radius_px=80.0,
    gaze_smoothing_ms=70.0,
    pose_gate=False,
)
LIMITS = dict(
    activation=(0.1, 0.99),
    release=(0.01, 0.9),
    open_ms=(0, 1000),
    cooldown_ms=(0, 2000),
    stale_ms=(80, 2000),
    left_min_ms=(40, 3000),
    right_min_ms=(40, 3000),
    max_ms=(100, 10000),
    dwell_ms=(200, 5000),
    dwell_radius=(0.005, 0.2),
    head_center_x=(0, 1),
    head_center_y=(0, 1),
    head_range=(0.02, 0.5),
    head_deadzone=(0, 0.5),
    motion_limit=(0.1, 20),
    recovery_ms=(0, 1000),
    gaze_radius_px=(5, 500),
    gaze_smoothing_ms=(0, 500),
)


def settings(data=None):
    data = {} if data is None else data
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError("Unknown research setting")
    result = deepcopy(DEFAULTS)
    result.update(data)
    for key, (low, high) in LIMITS.items():
        value = result[key]
        if (
            type(value) not in (float, int)
            or not isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError(f"{key} must be {low}..{high}")
    for key, choices in dict(
        policy=("independent", "strict"),
        click_mode=("release", "hold"),
        pointer_mode=("tongue", "head", "gaze"),
        model=("rules", "geometry", "blink", "face"),
        left_source=SOURCES,
        right_source=SOURCES,
    ).items():
        if result[key] not in choices:
            raise ValueError(f"Invalid {key}")
    for key in ("scroll_enabled", "pose_gate"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if result["release"] >= result["activation"]:
        raise ValueError("Release must be below activation")
    if max(result["left_min_ms"], result["right_min_ms"]) >= result["max_ms"]:
        raise ValueError("Maximum closure must exceed minimum")
    if (
        result["left_source"] == result["right_source"]
        and result["left_source"] != "disabled"
    ):
        raise ValueError("Assign a gesture to only one action")
    if "both_eyes" in (result["left_source"], result["right_source"]) and any(
        v in ("left_eye", "right_eye")
        for v in (result["left_source"], result["right_source"])
    ):
        raise ValueError("Bilateral mapping conflicts with individual eye mappings")
    if result["pointer_mode"] in ("head", "gaze") and result["scroll_enabled"]:
        raise ValueError(
            "Head pointer and head scrolling need separate modes; disable scrolling"
        )
    if result["click_mode"] == "hold" and result["model"] != "rules":
        raise ValueError("Completed-event models require click on release")
    return result
