"""Minimal capture-debug overlay; the full diagnostic/settings UI is Processing's."""


def display_point(point, width, *, mirrored):
    x, y = point
    return (round(width - 1 - x) if mirrored else round(x), round(y))


def render_overlay(bgr, observations, frame, *, mirrored=True,
                   caption="Uncalibrated diagnostics | q: stop"):
    import cv2
    image = cv2.flip(bgr, 1) if mirrored else bgr.copy()
    height, width = image.shape[:2]
    for observation, face in zip(observations, frame["faces"]):
        for p in observation.points:
            cv2.circle(image, display_point(p, width, mirrored=mirrored), 1, (80, 190, 90), -1)
        ref = observation.head_reference
        if ref is not None:
            origin = display_point(ref.origin, width, mirrored=mirrored)
            for axis, color in ((ref.right, (255, 130, 30)), (ref.down, (30, 130, 255))):
                end = (ref.origin[0] + axis[0] * ref.width / 2,
                       ref.origin[1] + axis[1] * ref.width / 2)
                cv2.arrowedLine(image, origin, display_point(end, width, mirrored=mirrored), color, 2)
        x, y = display_point((observation.box.x * width, observation.box.y * height), width,
                             mirrored=mirrored)
        x = max(0, min(x, max(0, width - 240)))
        y = max(65, min(y, height - 70))
        lines = [face["subject_id"]]
        for name in ("left", "right"):
            ratios = observation.eyes.get(name)
            lines.append(f"{name} eye raw: {ratios.openness:.3f}" if ratios else f"{name} eye: unavailable")
        for i, text in enumerate(lines):
            cv2.putText(image, text, (x, y + i * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 240, 240), 1)
    cv2.putText(image, caption, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
    return image
