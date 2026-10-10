"""PROVISIONAL preview format. Change this adapter when the driver team agrees."""


def mouse_message(snapshot):
    return {
        "format": "mouse_preview_v0", "mode": "mouse",
        "sequence": snapshot["sequence"], "timestamp_ms": snapshot["timestamp_ms"],
        "source": {"session_id": snapshot["session_id"], "sequence": snapshot["source_sequence"],
                   "timestamp_ms": snapshot["source_timestamp_ms"], "subject_id": snapshot["subject_id"]},
        "enabled": snapshot["enabled"],
        "buttons": {"left": snapshot["left_click"], "right": snapshot["right_click"]},
        "velocity": {"x": snapshot["pointer_x"], "y": snapshot["pointer_y"], "scroll": snapshot["scroll_y"]},
    }
