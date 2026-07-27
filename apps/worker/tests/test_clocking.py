"""Clocking angle derived from a rotation matrix — a single definition used for
BOTH ground truth and recovered poses, so their difference is meaningful regardless
of how the placement was parameterized."""
import numpy as np
import pytest

from case_prep.domain.clocking import clocking_angle_deg
from case_prep.domain.geometry import RigidTransform


def test_rotation_about_axis_changes_clocking_by_that_angle():
    base = RigidTransform.identity().rotation
    rotated = RigidTransform.from_axis_angle([0, 0, 1], 30.0).rotation
    diff = (clocking_angle_deg(rotated) - clocking_angle_deg(base)) % 360.0
    assert diff == pytest.approx(30.0, abs=1e-6)


def test_clocking_is_in_0_360():
    for deg in [0, 45, 170, 350]:
        R = RigidTransform.from_axis_angle([0, 0, 1], deg).rotation
        c = clocking_angle_deg(R)
        assert 0.0 <= c < 360.0


def test_clocking_stable_under_small_tilt():
    # a few degrees of axis tilt should barely move the clocking estimate
    R0 = RigidTransform.from_axis_angle([0, 0, 1], 100.0).rotation
    tilt = RigidTransform.from_axis_angle([1, 0, 0], 3.0)
    R1 = (tilt.compose(RigidTransform.from_rotation(R0))).rotation
    assert abs((clocking_angle_deg(R1) - clocking_angle_deg(R0) + 180) % 360 - 180) < 5.0
