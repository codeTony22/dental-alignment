"""Domain geometry: RigidTransform (SE3) and Axis. Pure, no Open3D."""
import numpy as np
import pytest

from case_prep.domain.geometry import Axis, RigidTransform


def test_axis_normalizes_to_unit_length():
    axis = Axis.from_vector([0.0, 0.0, 5.0])
    assert np.allclose(axis.direction, [0.0, 0.0, 1.0])
    assert axis.is_unit()


def test_axis_rejects_zero_vector():
    with pytest.raises(ValueError):
        Axis.from_vector([0.0, 0.0, 0.0])


def test_axis_angle_between_is_symmetric_and_in_degrees():
    a = Axis.from_vector([1.0, 0.0, 0.0])
    b = Axis.from_vector([0.0, 1.0, 0.0])
    assert a.angle_to(b) == pytest.approx(90.0)
    assert b.angle_to(a) == pytest.approx(90.0)


def test_identity_transform_leaves_points_unchanged():
    t = RigidTransform.identity()
    pts = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    assert np.allclose(t.apply(pts), pts)


def test_translation_then_inverse_round_trips():
    t = RigidTransform.from_translation([10.0, 0.0, -2.0])
    pts = np.array([[1.0, 1.0, 1.0]])
    moved = t.apply(pts)
    assert np.allclose(moved, [[11.0, 1.0, -1.0]])
    assert np.allclose(t.inverse().apply(moved), pts)


def test_compose_applies_right_then_left():
    rot_z_90 = RigidTransform.from_axis_angle([0, 0, 1], 90.0)
    trans = RigidTransform.from_translation([1.0, 0.0, 0.0])
    composed = trans.compose(rot_z_90)  # rotate first, then translate
    p = np.array([[1.0, 0.0, 0.0]])
    # rotate (1,0,0) about z by 90deg -> (0,1,0); translate +x -> (1,1,0)
    assert np.allclose(composed.apply(p), [[1.0, 1.0, 0.0]], atol=1e-9)


def test_matrix_is_4x4_and_bottom_row_canonical():
    t = RigidTransform.from_translation([1.0, 2.0, 3.0])
    m = t.matrix
    assert m.shape == (4, 4)
    assert np.allclose(m[3], [0.0, 0.0, 0.0, 1.0])
