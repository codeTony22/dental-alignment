"""Taubin/Pratt circle fit — the P1 replacement for algebraic Kasa.

Kasa (the project's standing fit) is unbiased on a full circle and biased small
on a partial arc — Chernov's measured defect, and the reason the curve design
replaces it. These tests pin that replacement: a full circle still reads the
true radius, a 90° arc is closer to truth than Kasa, collinear points refuse.
"""
from __future__ import annotations

import numpy as np
import pytest

from case_prep.domain.circle_fit import (
    circle_centre_xy, fit_circle_xy, fit_circle_xy_kasa, fit_circle_xy_or_kasa,
)


def _arc(radius: float, span_rad: float, n: int = 40, centre=(0.0, 0.0),
         start: float = 0.0) -> np.ndarray:
    th = np.linspace(start, start + span_rad, n)
    c = np.asarray(centre, float)
    return np.column_stack([c[0] + radius * np.cos(th),
                            c[1] + radius * np.sin(th)])


class TestFitCircleXy:
    def test_full_circle_recovers_radius_and_centre(self):
        pts = _arc(2.5, 2 * np.pi, n=80, centre=(1.2, -0.4))
        fit = fit_circle_xy(pts)
        assert fit is not None
        c, r = fit
        assert r == pytest.approx(2.5, abs=0.02)
        assert c[0] == pytest.approx(1.2, abs=0.02)
        assert c[1] == pytest.approx(-0.4, abs=0.02)

    def test_quarter_arc_is_closer_to_truth_than_kasa(self):
        # The load-bearing claim: Kasa shrinks a partial arc; Taubin/Pratt do not
        # (or shrink less). True rim 2.5 mm, 90° of support — Appendix A closure
        # runs as low as 9/24, so this is the fleet's actual exposure.
        pts = _arc(2.5, np.pi / 2, n=40, centre=(0.0, 0.0))
        taubin = fit_circle_xy(pts)
        kasa = fit_circle_xy_kasa(pts)
        assert taubin is not None and kasa is not None
        _, r_t = taubin
        _, r_k = kasa
        assert abs(r_t - 2.5) < abs(r_k - 2.5)
        assert abs(r_t - 2.5) < 0.15

    def test_collinear_points_refuse(self):
        pts = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])
        assert fit_circle_xy(pts) is None
        assert fit_circle_xy_kasa(pts) is None
        assert fit_circle_xy_or_kasa(pts) is None
        c = circle_centre_xy(pts)
        assert c.shape == (2,)
        assert c[0] == pytest.approx(1.5)
        assert c[1] == pytest.approx(0.0)

    def test_fewer_than_three_points_refuse(self):
        assert fit_circle_xy(np.array([[0.0, 0.0], [1.0, 0.0]])) is None
        assert fit_circle_xy_kasa(np.array([[0.0, 0.0], [1.0, 0.0]])) is None

    def test_centre_helper_matches_taubin_on_a_full_circle(self):
        pts = _arc(2.5, 2 * np.pi, n=80, centre=(1.2, -0.4))
        fit = fit_circle_xy(pts)
        assert fit is not None
        np.testing.assert_allclose(circle_centre_xy(pts), fit[0], atol=1e-9)
