"""Blind healing-cap candidate proposal — the client's RANSAC idea, made honest.

THE LANE THIS EXISTS FOR (client direction relayed 2026-08-16, over their
partner's RANSAC/Open3D script thread): a scan with NO declared sites and no
template in hand — first-visit intake, or the missed-cap search. Everywhere a
variant IS known, template-matched measurement outranks any blind primitive
fit and this module is the wrong tool; see the §10-AT front-1 rejection of
curvature segmentation for the standing argument.

WHAT IT IS: a patch-seeded cylinder RANSAC over the scan's own normals.
A machined cap wall is a band of surface whose normals point radially off a
near-occlusal axis — so a local patch's normal covariance names the axis
(its smallest eigenvector), and the centre is fit at DISCRETE CATALOG RADII
only (``radii``): a partial visible arc lets a free circle fit balloon
(measured on cap6020: the r~2.6 ring fit free at r=3.33 with the centre
4.3mm off — the draped-tissue partial-arc bias), while a centre-only fit at
a known radius cannot. Two cap-vs-tooth discriminators, both measured on
this fleet: the RECESS-VOID rule (a cap's core dips at/below its own wall
top; a tooth's cusp rises above its wall) with a DOME allowance (a cap's
dome is revolute about the fitted axis — azimuth sectors agree; a cusp
field is lopsided), and the wall-span band (a cap wall is 1-6mm; round 1's
25mm "cylinders" were the arch's own buccal sweep).

FLEET SCOREBOARD AT LANDING (2026-08-16, 9 scans, 10 landed-truth sites,
docs/engagement/blind-detection-scoreboard.md): single-configuration
4/10 within the ±3mm seed basin, 6/10 across configurations, ~7 spurious
per case, ~10s per scan. NOT a detector — a SEED PROPOSER. The queued
wiring (same doc) feeds these seeds through the production rim-slab
refinement as the judge; nothing here writes a proposal to any session.

Deterministic by construction (fixed ``seed``): the detect() determinism
pin must hold for any future consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree

R_MIN_MM = 1.5
R_MAX_MM = 5.0
#: coarse catalog-band coverage; a wired consumer passes the library's own
#: rim radii instead
DEFAULT_RADII_MM: Tuple[float, ...] = (2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2,
                                       3.6, 4.0)
RING_RESID_MAX_MM = 0.6       # centre-only fit acceptance on the seed patch
RADIAL_TOL_MM = 0.15          # machined wall: tight; teeth cannot hold this
NORMAL_RADIAL_MIN = 0.85
CORE_RISE_MAX_MM = 0.5
DOME_SECTOR_SPREAD_MM = 0.9   # revolute-dome allowance on a risen core
AXIS_OCC_MIN = 0.60
WALL_NORMAL_OCC_MAX = 0.60
SPAN_MIN_MM = 1.0
SPAN_MAX_MM = 6.0
MIN_INLIERS = 90
SUPPRESS_FACTOR = 1.4
PATCH_RADIUS_MM = 3.0
PATCH_MIN_PTS = 60
SEEDS = 700
REFIT_ROUNDS = 2


@dataclass(frozen=True)
class BlindCandidate:
    """One blind cylinder hypothesis — a SEED, never a verdict."""

    centre: Tuple[float, float, float]   # a point on the axis at the wall top
    axis: Tuple[float, float, float]     # unit, oriented occlusally
    radius_mm: float
    inliers: int
    wall_span_mm: float
    score: float


def _occlusal_direction(N: np.ndarray) -> np.ndarray:
    m = N.mean(axis=0)
    n = float(np.linalg.norm(m))
    return m / n if n else np.array([0.0, 0.0, 1.0])


def _basis(axis: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    h = (np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9
         else np.array([0.0, 1.0, 0.0]))
    u = np.cross(axis, h)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def _fit_centre_at_radii(Q: np.ndarray, M: np.ndarray,
                         radii: Sequence[float]
                         ) -> Optional[Tuple[np.ndarray, float]]:
    best: Optional[Tuple[float, np.ndarray, float]] = None
    for rk in radii:
        c = (Q - rk * M).mean(axis=0)
        resid = float(np.median(np.abs(np.linalg.norm(Q - c, axis=1) - rk)))
        if best is None or resid < best[0]:
            best = (resid, c, float(rk))
    if best is None or best[0] > RING_RESID_MAX_MM:
        return None
    return best[1], best[2]


def _score(av: np.ndarray, an: np.ndarray, axis: np.ndarray,
           c2: np.ndarray, r: float) -> np.ndarray:
    u, v = _basis(axis)
    Q = np.column_stack([av @ u, av @ v])
    d = np.linalg.norm(Q - c2, axis=1)
    radial_ok = np.abs(d - r) < RADIAL_TOL_MM
    rad_dir = (Q - c2) / np.maximum(d[:, None], 1e-9)
    n2d = np.column_stack([an @ u, an @ v])
    n2d_len = np.linalg.norm(n2d, axis=1)
    align = np.einsum("ij,ij->i", n2d, rad_dir) / np.maximum(n2d_len, 1e-9)
    return radial_ok & (align > NORMAL_RADIAL_MIN) & (n2d_len > 0.3)


def propose_blind_candidates(mesh: trimesh.Trimesh,
                             radii: Sequence[float] = DEFAULT_RADII_MM,
                             max_candidates: int = 8,
                             subsample: int = 60000,
                             seed: int = 0) -> List[BlindCandidate]:
    """Rank blind cylinder seeds on ``mesh`` — deterministic for a fixed
    ``seed``. Returns [] rather than guessing when the scan carries no
    usable wall signal."""
    rng = np.random.default_rng(seed)
    V = np.asarray(mesh.vertices, float)
    N = np.asarray(mesh.vertex_normals, float)
    if len(V) == 0:
        return []
    occ = _occlusal_direction(N)
    if len(V) > subsample:
        idx = rng.choice(len(V), subsample, replace=False)
        V, N = V[idx], N[idx]

    wall = np.abs(N @ occ) < WALL_NORMAL_OCC_MAX
    WV, WN = V[wall], N[wall]
    if len(WV) < 500:
        return []
    tree = cKDTree(WV)

    def hypothesis(patch_idx: np.ndarray
                   ) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
        pn = WN[patch_idx]
        cov = pn.T @ pn / len(pn)
        _w, vecs = np.linalg.eigh(cov)
        axis = vecs[:, 0]
        if axis @ occ < 0:
            axis = -axis
        if axis @ occ < AXIS_OCC_MIN:
            return None
        u, v = _basis(axis)
        pv = WV[patch_idx]
        Q = np.column_stack([pv @ u, pv @ v])
        M = np.column_stack([pn @ u, pn @ v])
        ml = np.linalg.norm(M, axis=1)
        good = ml > 0.3
        if int(good.sum()) < PATCH_MIN_PTS // 2:
            return None
        fit = _fit_centre_at_radii(Q[good], M[good] / ml[good, None], radii)
        if fit is None:
            return None
        c2, r = fit
        if not (R_MIN_MM <= r <= R_MAX_MM):
            return None
        return axis, c2, r

    active = np.ones(len(WV), bool)
    out: List[BlindCandidate] = []
    seeds = rng.choice(len(WV), min(SEEDS, len(WV)), replace=False)

    for _round in range(max_candidates):
        best = None
        for s in seeds:
            if not active[s]:
                continue
            patch = [i for i in tree.query_ball_point(WV[s], PATCH_RADIUS_MM)
                     if active[i]]
            if len(patch) < PATCH_MIN_PTS:
                continue
            hyp = hypothesis(np.asarray(patch))
            if hyp is None:
                continue
            axis, c2, r = hyp
            av, an = WV[active], WN[active]
            inl = _score(av, an, axis, c2, r)
            if int(inl.sum()) < MIN_INLIERS:
                continue

            for _ in range(REFIT_ROUNDS):
                pn = an[inl]
                cov = pn.T @ pn / len(pn)
                _w, vecs = np.linalg.eigh(cov)
                axis2 = vecs[:, 0]
                if axis2 @ occ < 0:
                    axis2 = -axis2
                if axis2 @ occ < AXIS_OCC_MIN:
                    break
                axis = axis2
                u, v = _basis(axis)
                Q = np.column_stack([av[inl] @ u, av[inl] @ v])
                M = np.column_stack([pn @ u, pn @ v])
                ml = np.linalg.norm(M, axis=1)
                ok = ml > 0.3
                fit = _fit_centre_at_radii(Q[ok], M[ok] / ml[ok, None], radii)
                if fit is None:
                    break
                c2, r = fit
                inl = _score(av, an, axis, c2, r)
                if int(inl.sum()) < MIN_INLIERS:
                    break
            if int(inl.sum()) < MIN_INLIERS:
                continue
            h = av[inl] @ axis
            span = float(np.percentile(h, 95) - np.percentile(h, 5))
            if not (SPAN_MIN_MM <= span <= SPAN_MAX_MM):
                continue

            # the core discriminator, dome-aware — see the module docstring
            u, v = _basis(axis)
            top = float(np.percentile(h, 95))
            Qf = np.column_stack([V @ u, V @ v])
            df = np.linalg.norm(Qf - c2, axis=1)
            hf = V @ axis
            core = (df < 0.55 * r) & (hf > top - 6.0) & (hf < top + 4.0)
            if int(core.sum()) >= 25:
                rise = float(np.median(hf[core])) - top
                if rise > CORE_RISE_MAX_MM:
                    ring = core & (df > 0.2 * r)
                    if int(ring.sum()) < 24:
                        continue
                    az = np.arctan2(Qf[ring, 1] - c2[1],
                                    Qf[ring, 0] - c2[0])
                    sector = ((az + np.pi) / (2 * np.pi) * 8).astype(int) % 8
                    heights = [float(np.median(hf[ring][sector == s]))
                               for s in range(8) if (sector == s).sum() >= 3]
                    if len(heights) < 6:
                        continue
                    if max(heights) - min(heights) > DOME_SECTOR_SPREAD_MM:
                        continue

            score = float(inl.sum()) * min(span, 4.0)
            if best is None or score > best[0]:
                best = (score, axis, c2, r, inl, span)

        if best is None:
            break
        score, axis, c2, r, inl, span = best
        av = WV[active]
        u, v = _basis(axis)
        h = av[inl] @ axis
        top = float(np.percentile(h, 95))
        centre3 = c2[0] * u + c2[1] * v + top * axis
        out.append(BlindCandidate(
            centre=tuple(float(x) for x in centre3),
            axis=tuple(float(x) for x in axis),
            radius_mm=float(r), inliers=int(inl.sum()),
            wall_span_mm=span, score=score))
        Qa = np.column_stack([WV @ u, WV @ v])
        near = np.linalg.norm(Qa - c2, axis=1) < SUPPRESS_FACTOR * r
        active &= ~near

    return out
