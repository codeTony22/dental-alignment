"""Per-site alignment confidence metric (Spec A, 2026-07-15): pure math — pose-spread
statistics, the Fitzpatrick TRE closed form, and the grade thresholds. The bootstrap
re-seat and the ground-truth correlation live in test_auto_flow.py; this file guards the
leaf functions in isolation."""
from __future__ import annotations

import numpy as np
import trimesh

from case_prep.domain.pose_confidence import (
    PoseSpread,
    confidence_grade,
    fitzpatrick_tre,
    pose_spread,
)


def _pose(t=(0.0, 0.0, 0.0), axis_deg=0.0, axis=(1.0, 0.0, 0.0), clock_deg=0.0):
    m = np.eye(4)
    R = np.eye(3)
    if axis_deg:
        R = trimesh.transformations.rotation_matrix(np.radians(axis_deg), axis)[:3, :3] @ R
    if clock_deg:
        R = R @ trimesh.transformations.rotation_matrix(np.radians(clock_deg), [0, 0, 1])[:3, :3]
    m[:3, :3] = R
    m[:3, 3] = t
    return m


class TestPoseSpread:
    def test_identical_poses_have_zero_spread(self):
        ref = _pose(t=(1.0, 2.0, 3.0))
        s = pose_spread([ref.copy() for _ in range(5)], ref)
        assert s.pos_p90_mm == 0.0
        assert s.axis_p90_deg == 0.0
        assert s.clock_p90_deg == 0.0

    def test_position_spread_is_p90_of_deviation(self):
        ref = _pose()
        # deviations 0.1..1.0 mm along x; p90 ~= 0.91
        poses = [_pose(t=(d, 0.0, 0.0)) for d in np.linspace(0.1, 1.0, 10)]
        s = pose_spread(poses, ref)
        assert 0.85 < s.pos_p90_mm < 0.95
        assert s.axis_p90_deg == 0.0

    def test_axis_spread_measures_tilt_not_clocking(self):
        ref = _pose()
        # pure clocking about the axis must NOT show up as axis spread
        poses = [_pose(clock_deg=c) for c in (5.0, 10.0, 15.0)]
        s = pose_spread(poses, ref)
        assert s.axis_p90_deg < 0.5, "clocking leaked into the axis-tilt measure"
        assert s.clock_p90_deg > 8.0, "clocking spread not detected"

    def test_axis_tilt_is_reported_in_degrees(self):
        ref = _pose()
        poses = [_pose(axis_deg=a, axis=(0, 1, 0)) for a in (2.0, 4.0, 6.0)]
        s = pose_spread(poses, ref)
        assert 5.0 < s.axis_p90_deg < 7.0


class TestFitzpatrickTre:
    def test_more_marks_lower_tre(self):
        target = np.array([0.0, 0.0])
        few = np.array([[3.0, 0.0], [-3.0, 0.0], [0.0, 3.0]])
        many = np.array([[3.0, 0.0], [-3.0, 0.0], [0.0, 3.0], [0.0, -3.0],
                         [2.0, 2.0], [-2.0, -2.0]])
        assert fitzpatrick_tre(many, target, 0.3) < fitzpatrick_tre(few, target, 0.3)

    def test_wider_spread_lowers_tre_off_centre(self):
        # Fitzpatrick TRE is spread-INDEPENDENT exactly at the fiducial centroid (d_k=0),
        # which is correct physics; spread matters for an OFF-centroid target. A wider
        # fiducial spread stiffens the pose against rotation, lowering TRE off-centre.
        target = np.array([2.0, 0.0])
        tight = np.array([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]])
        wide = np.array([[4.0, 0.0], [-4.0, 0.0], [0.0, 4.0], [0.0, -4.0]])
        assert fitzpatrick_tre(wide, target, 0.3) < fitzpatrick_tre(tight, target, 0.3)

    def test_tre_scales_with_fle(self):
        target = np.array([0.0, 0.0])
        marks = np.array([[3.0, 0.0], [-3.0, 0.0], [0.0, 3.0], [0.0, -3.0]])
        assert fitzpatrick_tre(marks, target, 0.6) == \
            2.0 * fitzpatrick_tre(marks, target, 0.3)

    def test_degenerate_configs_return_none(self):
        target = np.array([0.0, 0.0])
        assert fitzpatrick_tre(np.array([[1.0, 0.0], [-1.0, 0.0]]), target, 0.3) is None
        collinear = np.array([[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        assert fitzpatrick_tre(collinear, target, 0.3) is None


class TestConfidenceGrade:
    def _clean(self, **over):
        base = dict(spread=PoseSpread(0.10, 2.0, 5.0), rim_agreement_mm=0.4,
                    top_face_p90_mm=0.3, candidates_too_close=False,
                    border_disagree_mm=None, tre_mm=0.2)
        base.update(over)
        return base

    def test_all_tight_is_high(self):
        assert confidence_grade(**self._clean()) == "high"

    def test_unstable_pose_is_low(self):
        assert confidence_grade(**self._clean(spread=PoseSpread(1.7, 2.0, 5.0))) == "low"
        assert confidence_grade(**self._clean(spread=PoseSpread(0.1, 25.0, 5.0))) == "low"

    def test_ambiguous_variant_is_not_high(self):
        assert confidence_grade(**self._clean(candidates_too_close=True)) != "high"

    def test_high_seat_residual_is_not_high(self):
        assert confidence_grade(**self._clean(rim_agreement_mm=1.4)) == "low"

    def test_riding_top_face_is_not_high(self):
        assert confidence_grade(**self._clean(top_face_p90_mm=1.8)) == "low"

    def test_disagreeing_clicks_downgrade(self):
        assert confidence_grade(**self._clean(border_disagree_mm=0.9)) != "high"

    def test_borderline_is_medium(self):
        # a good single-pair gesture (moderate spread ~1mm/12deg) -> medium, not high, not low
        assert confidence_grade(**self._clean(spread=PoseSpread(1.0, 12.0, 5.0))) == "medium"
