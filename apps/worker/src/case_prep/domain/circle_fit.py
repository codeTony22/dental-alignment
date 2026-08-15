"""Circle fits for rim geometry.

Algebraic Kasa is unbiased on a full circle and biased small on a partial arc
(Chernov). The shipped fit is Taubin's SVD circle (CircleFitByTaubin): same O(n)
cost, no new dependency, less bias when support is a fraction of 2π — which is
the measured fleet case (Appendix A: median rim closure 18/24 at 20°).

Kasa remains available as ``fit_circle_xy_kasa`` for shadow comparison and for
the one-line fall-back when Taubin degenerates (collinear / zero-radius).
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

_MIN_POINTS = 3
# A line-fit wearing a circle's clothes: Taubin's `a` coefficient vanishes.
_MIN_A = 1e-12
# Healing-cap rims are millimetres; a kilometre circle is a line.
_MAX_RADIUS_MM = 1.0e4


def fit_circle_xy_kasa(xy: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Algebraic least-squares (Kasa). Returns (centre_xy, radius) or None."""
    P = np.asarray(xy, dtype=float)
    if len(P) < _MIN_POINTS:
        return None
    centered = P - P.mean(axis=0)
    try:
        _, s, _ = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if len(s) < 2 or float(s[1]) <= 1e-9 * max(float(s[0]), 1e-12):
        return None
    x = P[:, 0] - P[:, 0].mean()
    y = P[:, 1] - P[:, 1].mean()
    A = np.c_[2.0 * x, 2.0 * y, np.ones(len(P))]
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    r2 = float(sol[2] + sol[0] ** 2 + sol[1] ** 2)
    if not np.isfinite(r2) or r2 <= 0.0:
        return None
    centre = np.array([P[:, 0].mean() + sol[0], P[:, 1].mean() + sol[1]], dtype=float)
    r = float(np.sqrt(r2))
    if not np.isfinite(r) or r > _MAX_RADIUS_MM:
        return None
    return centre, r


def fit_circle_xy(xy: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Taubin SVD circle fit (Chernov CircleFitByTaubin). (centre_xy, radius) or None."""
    P = np.asarray(xy, dtype=float)
    if len(P) < _MIN_POINTS:
        return None
    centroid = P.mean(axis=0)
    X = P[:, 0] - centroid[0]
    Y = P[:, 1] - centroid[1]
    Z = X * X + Y * Y
    zmean = float(Z.mean())
    if zmean < _MIN_A:
        return None
    z0 = (Z - zmean) / (2.0 * np.sqrt(zmean))
    try:
        _, _, vt = np.linalg.svd(np.column_stack([z0, X, Y]), full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    a = vt[-1]
    a0 = float(a[0] / (2.0 * np.sqrt(zmean)))
    a1, a2 = float(a[1]), float(a[2])
    a3 = -zmean * a0
    if abs(a0) < _MIN_A:
        return None
    cx = -a1 / (2.0 * a0) + float(centroid[0])
    cy = -a2 / (2.0 * a0) + float(centroid[1])
    disc = a1 * a1 + a2 * a2 - 4.0 * a0 * a3
    if disc <= 0.0 or not np.isfinite(disc):
        return None
    r = float(np.sqrt(disc) / (2.0 * abs(a0)))
    if not np.isfinite(r) or r > _MAX_RADIUS_MM:
        return None
    return np.array([cx, cy], dtype=float), r


def fit_circle_xy_or_kasa(xy: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Taubin, then algebraic Kasa. None only when both refuse."""
    fit = fit_circle_xy(xy)
    if fit is not None:
        return fit
    return fit_circle_xy_kasa(xy)


def circle_centre_xy(xy: np.ndarray) -> np.ndarray:
    """Circle centre in xy. Taubin, then Kasa, then the point-mean.

    Callers that previously ran unguarded lstsq always got a 2-vector back;
    this keeps that contract while swapping the estimator.
    """
    P = np.asarray(xy, dtype=float)
    if len(P) == 0:
        return np.zeros(2, dtype=float)
    fit = fit_circle_xy_or_kasa(P)
    if fit is not None:
        return fit[0]
    return P.mean(axis=0)
