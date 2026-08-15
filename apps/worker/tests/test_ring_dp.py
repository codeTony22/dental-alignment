"""Periodic DP on a (θ, r) cylinder — the P2 replacement for longest-contiguous-run.

The island's `_ring_fit` picked the longest closed radial run, which is
grid-phase-bistable on an inner code-step ring (cap6030: 1.81 ↔ 2.64 mm).
Closure as a *constraint* (`r_0 = r_N`) plus a light outer bias is the
upgrade: a gapped outer rim stays one circle; an inner plateau is not
preferred just because a phase made its run look longer.
"""
from __future__ import annotations

import numpy as np
import pytest

from case_prep.domain.ring_dp import periodic_min_path


def _ridge(t: int, r: int, r_true: int, amp: float = 1.0) -> np.ndarray:
    w = np.zeros((t, r))
    w[:, r_true] = amp
    return w


class TestPeriodicMinPath:
    def test_constant_ridge_is_a_closed_circle(self):
        path = periodic_min_path(_ridge(24, 20, 10), lam=0.35, max_step=2)
        assert path is not None
        assert list(path.r_index) == [10] * 24
        assert path.gap_fraction == pytest.approx(0.0)

    def test_a_gap_is_bridged_not_broken(self):
        w = _ridge(24, 20, 12)
        w[0:5, 12] = 0.0
        path = periodic_min_path(w, lam=0.35, max_step=2)
        assert path is not None
        assert list(path.r_index) == [12] * 24
        assert path.gap_fraction == pytest.approx(5 / 24)

    def test_periodicity_rejects_a_spiral(self):
        # Without r_0 = r_N the cheapest path walks inward one bin per step.
        # Periodicity must close: a constant-radius ridge still wins.
        t, r = 12, 16
        w = np.zeros((t, r))
        for i in range(t):
            w[i, 8] = 1.0
            w[i, max(0, 8 - i)] = 0.4
        path = periodic_min_path(w, lam=0.15, max_step=2)
        assert path is not None
        assert list(path.r_index) == [8] * t

    def test_outer_bias_prefers_the_true_rim_over_a_stronger_inner_ring(self):
        # The cap6030 anatomy in weight space: a denser inner code-step and a
        # slightly weaker but complete outer rim. Longest-run locked inner;
        # outer_bias is the DP analog of "take the OUTER edge of the ring".
        t, r = 24, 20
        w = np.zeros((t, r))
        w[:, 6] = 1.2
        w[:, 14] = 1.0
        inner = periodic_min_path(w, lam=0.35, max_step=2, outer_bias=0.0)
        outer = periodic_min_path(w, lam=0.35, max_step=2, outer_bias=0.04)
        assert inner is not None and outer is not None
        assert list(inner.r_index) == [6] * t
        assert list(outer.r_index) == [14] * t

    def test_all_zero_weight_refuses(self):
        assert periodic_min_path(np.zeros((24, 16))) is None

    def test_bearing_margin_is_one_per_theta(self):
        path = periodic_min_path(_ridge(24, 20, 10), lam=0.35, max_step=2)
        assert path is not None
        assert path.bearing_margin.shape == (24,)
        assert float(path.bearing_margin.min()) > 0.0
