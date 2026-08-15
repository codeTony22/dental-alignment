"""Domain geometry: RigidTransform (SE3), Axis and the AXIS-LOCKED FIT. Pure, no
Open3D."""
import math

import numpy as np
import pytest

from case_prep.domain.geometry import Axis, RigidTransform, fit_axis_locked


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


# --- THE AXIS-LOCKED FIT (client ruling 2026-08-15) ---------------------------------------
#
# "Point pair tools should not only be rotating, also down or up, it needs to match the
# points where the user added them, because the user is pointing to the holes in the
# library and scan and matching it."
#
# The primitive under every rung of the pair ladder: the part may TURN about its own
# axis and SLIDE; it may never TILT. Everything here is hand-computable — one clock
# angle, one 3-vector, and the millimetres each correspondence still misses by.


def _rot_z(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class TestOneCorrespondenceIsPureTranslation:
    """RUNG 1. Three constraints, three degrees of freedom — exactly determined, and
    the only honest answer is the offset itself."""

    def test_the_translation_is_the_offset_and_the_clock_does_not_move(self):
        fit = fit_axis_locked([[2.0, 0.0, 1.0]], [[2.3, -0.1, 1.05]])
        assert fit.rotation_deg == pytest.approx(0.0)
        assert fit.translation == pytest.approx(np.array([0.3, -0.1, 0.05]))
        assert fit.residuals_mm == pytest.approx(np.array([0.0]))

    def test_one_point_carries_no_clock_baseline_at_all(self):
        """The lever a rotation is read over is the spread ABOUT THE CENTROID — with
        one point there is none, so the estimator says so rather than reporting an
        atan2(0, 0) as an answer."""
        fit = fit_axis_locked([[2.0, 0.0, 1.0]], [[2.3, -0.1, 1.05]])
        assert fit.clock_baseline_mm == pytest.approx(0.0)


class TestTwoCorrespondencesRecoverTheClockAndTheSlide:
    """RUNG 2. The chord between the two part points, carried onto the chord between
    the two scan points — and the translation that lands their centroids together."""

    def test_a_known_turn_and_a_known_slide_come_back_exactly(self):
        source = np.array([[2.0, 0.0, 1.0], [-1.0, 1.5, 1.0]])
        offset = np.array([0.4, -0.25, 0.1])
        target = source @ _rot_z(37.0).T + offset
        fit = fit_axis_locked(source, target)
        assert fit.rotation_deg == pytest.approx(37.0)
        assert fit.translation == pytest.approx(offset)
        assert fit.residuals_mm == pytest.approx(np.zeros(2), abs=1e-9)

    def test_the_clock_baseline_of_two_points_is_their_in_plane_separation(self):
        """The same quantity a span's baseline measures, between pairs instead of
        within one: 3-4-5 in plane, and the z difference does not lengthen it."""
        fit = fit_axis_locked([[0.0, 0.0, 0.0], [3.0, 4.0, 9.0]],
                              [[0.0, 0.0, 0.0], [3.0, 4.0, 9.0]])
        assert fit.clock_baseline_mm == pytest.approx(5.0)

    def test_points_stacked_on_one_azimuth_leave_the_clock_unreadable(self):
        """Two clicks at the same xy differ only in height: they name a position and
        no bearing at all, and the baseline is what says so."""
        fit = fit_axis_locked([[2.0, 0.0, 0.0], [2.0, 0.0, 3.0]],
                              [[2.2, 0.1, 0.0], [2.2, 0.1, 3.0]])
        assert fit.clock_baseline_mm == pytest.approx(0.0)
        assert fit.rotation_deg == pytest.approx(0.0)
        assert fit.translation == pytest.approx(np.array([0.2, 0.1, 0.0]))


class TestThePartMayNeverTilt:
    def test_an_out_of_plane_ask_is_answered_in_plane_and_the_miss_is_reported(self):
        """A 6-DoF fit would tilt the part to chase two clicks; this one may not. The
        unreachable part of the ask survives as the residual the operator reads."""
        source = np.array([[2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]])
        target = np.array([[2.0, 0.0, 0.5], [-2.0, 0.0, -0.5]])   # a pure tilt
        fit = fit_axis_locked(source, target)
        assert fit.rotation_deg == pytest.approx(0.0)
        assert fit.translation == pytest.approx(np.zeros(3), abs=1e-9)
        assert fit.residuals_mm == pytest.approx(np.array([0.5, 0.5]))

    def test_the_z_slide_is_the_mean_height_difference(self):
        source = np.array([[2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]])
        target = np.array([[2.0, 0.0, 0.5], [-2.0, 0.0, 0.1]])
        fit = fit_axis_locked(source, target)
        assert fit.translation[2] == pytest.approx(0.3)


class TestTheClockIsPivotIndependent:
    """The rotation is read from the CENTRED points, so it does not matter which
    origin the two clouds are expressed about — the pivot parallax that produced the
    −17.1° ghost (§10-AJ) cannot enter this estimator at all."""

    def test_shifting_the_frame_moves_the_translation_and_never_the_angle(self):
        source = np.array([[2.0, 0.0, 1.0], [-1.0, 1.5, 1.0], [0.5, -2.0, 1.0]])
        target = source @ _rot_z(-24.0).T + np.array([0.2, 0.3, 0.0])
        shift = np.array([13.0, -7.0, 4.0])
        plain = fit_axis_locked(source, target)
        shifted = fit_axis_locked(source + shift, target)
        assert shifted.rotation_deg == pytest.approx(plain.rotation_deg)
        assert shifted.residuals_mm == pytest.approx(plain.residuals_mm, abs=1e-9)


class TestThreeNoisyCorrespondences:
    """RUNG 3+. Constrained least squares: the residual is a MEASUREMENT (four
    parameters against nine constraints), not the tautology one pair produces."""

    def test_the_recovered_turn_survives_click_scatter_and_the_residual_reports_it(
            self):
        rng = np.random.default_rng(23)
        source = np.array([[2.4, 0.0, 1.0], [-1.2, 2.1, 1.0], [-0.9, -2.2, 1.0]])
        truth, offset = -18.0, np.array([0.35, 0.1, -0.05])
        sigma = 0.05
        target = source @ _rot_z(truth).T + offset + rng.normal(0.0, sigma, source.shape)
        fit = fit_axis_locked(source, target)
        # the clock error a 0.05mm scatter buys at these levers, measured over the seed
        assert abs(fit.rotation_deg - truth) < 2.0
        rms = float(np.sqrt(np.mean(fit.residuals_mm ** 2)))
        assert 0.2 * sigma < rms < 3.0 * sigma
        assert fit.residuals_mm.shape == (3,)

    def test_a_correspondence_that_names_a_different_feature_shows_up_as_its_own_miss(
            self):
        """The whole point of the residual: the pair that disagrees is NAMED by its
        own row, in the order it was given."""
        source = np.array([[2.4, 0.0, 1.0], [-1.2, 2.1, 1.0], [-0.9, -2.2, 1.0]])
        target = source.copy()
        target[1] += np.array([0.0, 0.9, 0.0])
        fit = fit_axis_locked(source, target)
        assert fit.residuals_mm[1] == max(fit.residuals_mm)


class TestTranslationOnlyIsAskable:
    def test_locking_the_rotation_fits_the_centroid_and_nothing_else(self):
        source = np.array([[2.0, 0.0, 1.0], [-1.0, 1.5, 1.0]])
        target = source @ _rot_z(37.0).T + np.array([0.4, -0.25, 0.1])
        fit = fit_axis_locked(source, target, allow_rotation=False)
        assert fit.rotation_deg == 0.0
        assert fit.translation == pytest.approx(target.mean(axis=0) - source.mean(axis=0))
        # the turn it was forbidden to make survives as the residual, in full
        assert float(np.sqrt(np.mean(fit.residuals_mm ** 2))) > 1.0


class TestTheAskMustBeWellFormed:
    def test_mismatched_counts_raise_rather_than_fitting_what_they_can(self):
        with pytest.raises(ValueError):
            fit_axis_locked([[1.0, 0.0, 0.0]], [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])

    def test_an_empty_correspondence_set_raises(self):
        with pytest.raises(ValueError):
            fit_axis_locked(np.zeros((0, 3)), np.zeros((0, 3)))

    def test_a_non_finite_point_raises_rather_than_producing_a_nan_pose(self):
        with pytest.raises(ValueError):
            fit_axis_locked([[1.0, 0.0, 0.0]], [[float("nan"), 0.0, 0.0]])
