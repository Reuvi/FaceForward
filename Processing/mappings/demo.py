"""Explicit synthetic gaming controls, added only to the App's demo source."""

from copy import deepcopy


def gaming_demo_frame(frame, fps):
    """Decorate a rebased synthetic mouse frame; never apply to camera/replay."""
    frame = deepcopy(frame)
    face = frame["faces"][0]
    values = face["signals"]
    t = frame["sequence"]/fps % 16
    values["head_x"] = {"value": .8 if 10 <= t < 11.5 else .2 if 11.5 <= t < 13 else .5,
                        "valid": True, "confidence": 1}
    values["mouth_open"] = {"value": int(14 <= t < 14.7), "valid": True, "confidence": 1}
    values["mouth_openness"] = {"value": .8 if 14 <= t < 14.7 else 0, "valid": True, "confidence": 1}
    intent = {"format": "eye_intent_v1", "subject_id": face["subject_id"],
              **{key: frame[key] for key in ("session_id", "sequence", "timestamp_ms")}}
    for side in ("left", "right"):
        closed = values[side+"_eye_open"]["value"] == 0
        intent[side] = {"value": int(closed), "known": True, "state": "wink" if closed else "open"}
    if intent["left"]["value"] or intent["right"]["value"]:
        for axis in ("x", "y"):
            values["gaze_"+axis] = {"value": None, "valid": False, "confidence": 0}
    frame.update(eye_intent=intent, simulated=True)
    return frame
