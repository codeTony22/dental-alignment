"""Trimmed point-to-point ICP (numpy/scipy). Replaces Open3D's registration_icp,
which segfaults on this arm64 build — a portability finding documented in the
feasibility memo. Pure and deterministic, so it is unit-tested directly."""
import numpy as np
import pytest

from case_prep.domain.geometry import RigidTransform
from case_prep.domain.icp import trimmed_icp


def test_recovers_known_rigid_transform_from_identity_seed():
    rng = np.random.default_rng(0)
    src = rng.normal(0, 1.0, (300, 3))
    true = RigidTransform.from_translation([0.5, -0.3, 0.2]).compose(
        RigidTransform.from_axis_angle([0, 0, 1], 15.0)
    )
    tgt = true.apply(src) + rng.normal(0, 0.004, src.shape)

    result = trimmed_icp(src, tgt, np.eye(4), max_corr_dist=1.5, max_iter=60)

    assert result.fitness > 0.9
    err = np.linalg.norm(result.transform.apply(src) - true.apply(src), axis=1).mean()
    assert err < 0.02


def test_trimming_ignores_outlier_target_points():
    # target = transformed source PLUS a blob of unrelated points; ICP should still lock
    rng = np.random.default_rng(1)
    src = rng.normal(0, 1.0, (300, 3))
    true = RigidTransform.from_translation([0.2, 0.1, -0.1])
    clean = true.apply(src)
    noise_blob = rng.normal([8, 8, 8], 0.5, (300, 3))
    tgt = np.vstack([clean, noise_blob])

    result = trimmed_icp(src, tgt, np.eye(4), max_corr_dist=1.0, trim_fraction=0.9, max_iter=60)

    err = np.linalg.norm(result.transform.apply(src) - clean, axis=1).mean()
    assert err < 0.05


def test_degenerate_correspondences_do_not_diverge_to_nonfinite():
    # a seed that puts source far from target with collinear matches must not blow up;
    # the result is reported as a failed fit (inf rmse), not NaN/inf transform values
    rng = np.random.default_rng(9)
    src = rng.normal(0, 1.0, (50, 3))
    tgt = rng.normal([100, 0, 0], 0.1, (50, 3))  # disjoint, no real overlap
    result = trimmed_icp(src, tgt, np.eye(4), max_corr_dist=0.5, max_iter=40)
    assert np.isfinite(result.transform.matrix).all()
    assert result.fitness == 0.0


def test_reports_inlier_rmse():
    rng = np.random.default_rng(2)
    src = rng.normal(0, 1.0, (200, 3))
    tgt = src + rng.normal(0, 0.01, src.shape)
    result = trimmed_icp(src, tgt, np.eye(4), max_corr_dist=0.5, max_iter=40)
    assert 0.0 <= result.inlier_rmse < 0.05
