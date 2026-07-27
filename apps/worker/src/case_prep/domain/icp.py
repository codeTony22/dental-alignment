"""Trimmed point-to-point ICP — pure numpy + scipy KDTree.

Used instead of Open3D's registration_icp, which segfaults on the Open3D 0.18
macOS-arm64 wheel (see the feasibility memo). Deterministic and dependency-light,
which is exactly what a clinical-safety registration core wants — and it is the
documented point-to-point fallback (design D33).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from case_prep.domain.geometry import RigidTransform


@dataclass(frozen=True)
class IcpResult:
    transform: RigidTransform  # maps source -> target
    fitness: float  # inlier fraction of the source
    inlier_rmse: float  # RMS correspondence distance over inliers


def _kabsch(p: np.ndarray, q: np.ndarray):
    """Best rigid R, t mapping points p onto q (Umeyama without scale)."""
    cp = p.mean(axis=0)
    cq = q.mean(axis=0)
    h = (p - cp).T @ (q - cq)
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T))
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    t = cq - r @ cp
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = t
    return m


def trimmed_icp(
    source: np.ndarray,
    target: np.ndarray,
    init: np.ndarray,
    max_corr_dist: float,
    trim_fraction: float = 1.0,
    max_iter: int = 60,
    tol: float = 1e-7,
    target_tree=None,
) -> IcpResult:
    # A discarded multi-start trial can transiently overflow; suppress FP-status
    # warnings for the whole numerical routine so the sticky flag never leaks to callers.
    with np.errstate(all="ignore"):
        source = np.asarray(source, dtype=float)
        target = np.asarray(target, dtype=float)
        # callers registering many seeds against ONE ROI pass the tree in (a register()
        # multistart was rebuilding it 66x per part)
        tree = target_tree if target_tree is not None else cKDTree(target)
        transform = np.asarray(init, dtype=float).copy()

        dist = np.array([])
        mask = np.array([], dtype=bool)
        for _ in range(max_iter):
            cur = source @ transform[:3, :3].T + transform[:3, 3]
            if not np.isfinite(cur).all():
                break  # a prior degenerate step diverged this start; abandon it
            dist, idx = tree.query(cur)

            mask = dist <= max_corr_dist
            if trim_fraction < 1.0 and mask.any():
                # additionally keep only the closest trim_fraction of the matched points
                kept = np.where(mask)[0]
                order = kept[np.argsort(dist[kept])]
                keep_n = max(3, int(len(order) * trim_fraction))
                keep = np.zeros_like(mask)
                keep[order[:keep_n]] = True
                mask = keep
            if mask.sum() < 3:
                break

            step = _kabsch(cur[mask], target[idx[mask]])
            # degenerate correspondences (e.g. collinear) can yield a non-finite or
            # absurdly large step; reject it so the trial never diverges/overflows
            if not np.isfinite(step).all() or np.abs(step[:3, 3]).max() > 1e6:
                break
            transform = step @ transform
            if np.linalg.norm(step - np.eye(4)) < tol:
                break

        inliers = int(mask.sum())
        fitness = float(inliers) / len(source) if len(source) else 0.0
        inlier_rmse = float(np.sqrt(np.mean(dist[mask] ** 2))) if inliers else float("inf")
    return IcpResult(RigidTransform(transform), fitness, inlier_rmse)
