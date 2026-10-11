"""Explicit synthetic completed pupil fit for unrelated integration regressions.

No human calibration data. The real fitting path is exercised by pupil tests.
"""
from Vision.pupil import MEASUREMENT
from Vision.pupil_calibration import SPACE, CHECK_NAMES, validate_model


def pupil_fixture():
    return validate_model(dict(space=SPACE, measurement=MEASUREMENT,
        reference_pose=[0.,0.,0.], pose_bounds=[[-25.,25.],[-25.,25.]],
        slopes=[[0.,0.],[0.,0.]], center=[0.,0.], low=[-.2,-.1], high=[.2,.065],
        checks={name:dict(samples=12,matched_fraction=1.) for name in CHECK_NAMES}))
