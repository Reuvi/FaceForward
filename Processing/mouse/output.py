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


def control_message(snapshot):
    """Serialize the adopted gaming command; legacy mouse preview stays intact."""
    if "mapping_id" not in snapshot:
        return mouse_message(snapshot)
    return {
        "format": "device_control_v1", "output_session_id": snapshot["output_session_id"],
        "sequence": snapshot["sequence"], "timestamp_ms": snapshot["timestamp_ms"],
        "source": {"session_id": snapshot["session_id"], "sequence": snapshot["source_sequence"],
                   "timestamp_ms": snapshot["source_timestamp_ms"], "subject_id": snapshot["subject_id"]},
        "mapping_id": snapshot["mapping_id"], "mapping_revision": snapshot["mapping_revision"],
        "enabled": snapshot["enabled"],
        "buttons": {"left_click": snapshot["left_click"], "right_click": snapshot["right_click"]},
        "keys": dict(snapshot["keys"]),
        "pointer": {"mode": "velocity", "x": snapshot["pointer_x"], "y": snapshot["pointer_y"]},
        "scroll_y": snapshot["scroll_y"], "known": dict(snapshot["known"]),
    }
