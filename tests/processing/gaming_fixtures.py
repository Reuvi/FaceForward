"""Synthetic contract samples, with no camera or Vision module dependency."""


def frame(sequence=0, timestamp=1000., *, x=.5, y=.5, head_x=.5, head_y=.5,
          left="open", right="open", mouth=0, session="synthetic", subject="person"):
    def measurement(value):
        return {"value": value, "valid": value is not None, "confidence": 1 if value is not None else 0}
    values = {"gaze_x": x, "gaze_y": y, "head_x": head_x, "head_y": head_y,
              "tongue_x": None, "tongue_y": None, "mouth_open": mouth,
              "left_eye_open": 1 if left == "open" else 0 if left != "unknown" else None,
              "right_eye_open": 1 if right == "open" else 0 if right != "unknown" else None}
    result = {"schema_version": 1, "session_id": session, "sequence": sequence,
              "timestamp_ms": timestamp, "faces": [{"subject_id": subject,
              "signals": {key: measurement(value) for key, value in values.items()}}],
              "gaze_measurement": "head_compensated_iris_direction_v1"}
    result["eye_intent"] = {"format": "eye_intent_v1", "subject_id": subject,
                            **{key: result[key] for key in ("session_id", "sequence", "timestamp_ms")}}
    for side, state in (("left", left), ("right", right)):
        result["eye_intent"][side] = {"value": None if state == "unknown" else int(state == "wink"),
                                      "known": state != "unknown", "state": state}
    return result
