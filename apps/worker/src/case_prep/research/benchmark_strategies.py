"""Offline alternative cap-seating strategies, benchmarked against the shipped
S0 baseline (``case_prep.pipeline.auto_flow``). Grounded in
``docs/research/alignment-algorithm-survey.md`` sections 5-6.

Ubiquitous language
--------------------
* **local frame** — the crowns-up frame built by ``auto_flow._crowns_frame``:
  ``L = (pts - origin) @ frame``. All strategies operate in this frame (a pose
  returned by a strategy is a 4x4 matrix that maps the TEMPLATE's own canonical
  frame into this local frame, exactly like ``auto_flow``'s ``t_local``).
* **patch** — the ball-cropped candidate surface around a site (mirrors
  ``auto_flow._cap_patch_roi``): local scan points within
  ``min(rim_r + 1.2, 5.4)`` mm of the all-clicks circle centre, subsampled to
  <= 8000 points for determinism and runtime.
* **strategy** — a pure function ``(patch, clicks_local, template) -> (pose,
  seat_residual, diagnostics)``. Every strategy is deterministic given
  ``np.random.seed(0)`` at the call site (the benchmark CLI seeds once per
  entry point; nothing here reseeds mid-run so repeated calls in one process
  stay reproducible in aggregate, matching the production seeding contract).

No strategy here is a production candidate by fiat — this module only measures.
The CALIBRATED production functions (imported, never reimplemented insecurely)
remain the source of truth for S0; S1-S3 are literature-grounded alternatives
mirrored fresh per the task brief so this module has no hidden coupling to
production internals beyond the four explicitly-allowed imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from case_prep.pipeline.auto_flow import (_fit_circle_3d, _fit_circle_plane,
                                          _pinned_rim_seat, _rim_agreement_mm)

__all__ = [
    "StrategyResult",
    "build_patch",
    "gnc_circle_fit",
    "s0_production_pinned",
    "s1_gnc_circle",
    "s2_joint_click_surface",
    "s3_dense_constrained_search",
    "pose_to_delta",
    "delta_to_pose",
    "STRATEGIES",
]


@dataclass(frozen=True)
class StrategyResult:
    """One strategy's answer at one site: pose (4x4, local frame, template-space
    -> local-space), the strategy's OWN seat residual (never comparable ACROSS
    strategies — each is its own objective, per the survey's mode-independent
    warning in section 6), and free-form diagnostics for the report."""

    pose: Optional[np.ndarray]
    seat_residual: Optional[float]
    diagnostics: Dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Shared geometry helpers
# --------------------------------------------------------------------------

def build_patch(L: np.ndarray, clicks_local: np.ndarray,
                max_points: int = 8000) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    """The shared candidate-surface crop: ball radius ``min(rim_r + 1.2, 5.4)`` mm
    around the ALL-CLICKS circle centre, subsampled evenly to <= ``max_points``.
    Returns (patch, centre, rim_r) or None when the clicks cannot support a
    circle or too little surface falls inside the ball."""
    fit = _fit_circle_plane(clicks_local)
    if fit is None:
        return None
    centre, _n, rim_r = fit
    ball_r = min(rim_r + 1.2, 5.4)
    d = np.linalg.norm(L - centre, axis=1)
    patch = L[d < ball_r]
    if len(patch) < 60:
        return None
    if len(patch) > max_points:
        idx = np.linspace(0, len(patch) - 1, max_points).astype(int)
        patch = patch[idx]
    return patch, centre, rim_r


# --------------------------------------------------------------------------
# S0 — production-pinned baseline (calls the production functions directly)
# --------------------------------------------------------------------------

def s0_production_pinned(patch: np.ndarray, clicks_local: np.ndarray,
                         template: trimesh.Trimesh) -> StrategyResult:
    """Mirrors the production pinned-rim flow: ``_fit_circle_3d`` proposes 1-2
    circle hypotheses (outlier-click arbitration built in); each is seated with
    ``_pinned_rim_seat``; the PIN CONTRACT (every original click within 0.9mm of
    the posed template) selects the winner among contract holders by minimum
    seat residual. If no hypothesis holds the contract, fall back to the
    all-clicks circle's pin without the contract (never silently return
    nothing when a pose exists)."""
    scan_tree = cKDTree(patch)
    circles = _fit_circle_3d(clicks_local, scan_tree=scan_tree)
    if not circles:
        return StrategyResult(None, None, {"reason": "no circle hypothesis"})

    holders: List[Tuple[np.ndarray, float, float]] = []  # (pose, seat_resid, contract_max)
    all_seats: List[Tuple[np.ndarray, float, float]] = []
    for circle in circles:
        seat = _pinned_rim_seat(patch, circle, template)
        if seat is None:
            continue
        pose, resid = seat
        tv = np.asarray(template.vertices, float) @ pose[:3, :3].T + pose[:3, 3]
        contract_max = float(cKDTree(tv).query(clicks_local)[0].max())
        all_seats.append((pose, resid, contract_max))
        if contract_max < 0.9:
            holders.append((pose, resid, contract_max))

    if holders:
        pose, resid, contract_max = min(holders, key=lambda h: h[1])
        return StrategyResult(pose, resid, {
            "n_hypotheses": len(circles), "n_holders": len(holders),
            "contract_max_mm": contract_max, "contract_held": True,
        })
    if all_seats:
        # no contract holder: fall back to the all-clicks circle's own pin (mirrors
        # the "without the contract" instruction) rather than refuse outright
        all_fit = _fit_circle_plane(clicks_local)
        if all_fit is not None:
            seat = _pinned_rim_seat(patch, all_fit, template)
            if seat is not None:
                pose, resid = seat
                tv = np.asarray(template.vertices, float) @ pose[:3, :3].T + pose[:3, 3]
                contract_max = float(cKDTree(tv).query(clicks_local)[0].max())
                return StrategyResult(pose, resid, {
                    "n_hypotheses": len(circles), "n_holders": 0,
                    "contract_max_mm": contract_max, "contract_held": False,
                })
        pose, resid, contract_max = min(all_seats, key=lambda h: h[1])
        return StrategyResult(pose, resid, {
            "n_hypotheses": len(circles), "n_holders": 0,
            "contract_max_mm": contract_max, "contract_held": False,
        })
    return StrategyResult(None, None, {"reason": "no seat within any circle hypothesis"})


# --------------------------------------------------------------------------
# S1 — GNC-weighted robust circle fit
# --------------------------------------------------------------------------

def _weighted_plane_fit(Q: np.ndarray, w: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Weighted centroid + weighted SVD (sqrt(w)-scaled residuals) plane fit.
    Returns (centre, unit normal)."""
    wsum = float(w.sum())
    centre = (w[:, None] * Q).sum(axis=0) / wsum
    scaled = np.sqrt(w)[:, None] * (Q - centre)
    _, _, vt = np.linalg.svd(scaled, full_matrices=False)
    n = vt[2] / np.linalg.norm(vt[2])
    if n[2] < 0:
        n = -n
    return centre, n


def _weighted_kasa_circle(Q: np.ndarray, centre: np.ndarray, n: np.ndarray,
                          w: np.ndarray) -> Tuple[np.ndarray, float]:
    """Weighted in-plane Kasa circle fit. Returns (centre_3d, radius)."""
    t0 = np.cross(n, [0.0, 0.0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0.0, 0.0])
    t0 /= np.linalg.norm(t0)
    t1 = np.cross(n, t0)
    uv = (Q - centre) @ np.c_[t0, t1]
    sw = np.sqrt(w)
    A = sw[:, None] * np.c_[2.0 * uv, np.ones(len(uv))]
    b = sw * (uv ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    centre3 = centre + sol[0] * t0 + sol[1] * t1
    r2 = sol[2] + sol[0] ** 2 + sol[1] ** 2
    return centre3, float(np.sqrt(max(r2, 1e-9)))


def gnc_circle_fit(P: np.ndarray, max_iter: int = 30
                   ) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Graduated non-convexity (Geman-McClure) robust circle fit over clicks
    (survey section 3(a), candidate 1). Iterates: weighted plane fit (weighted
    centroid + weighted SVD of sqrt(w)-scaled residuals) + weighted in-plane
    Kasa circle; per-click residual r_i = 3D distance to the current circle;
    weight w_i = (mu / (mu + r_i^2))^2; mu anneals from ``(10*max_r)^2``
    downward by /1.4 per iteration until ``mu < 0.3^2`` (~15 iterations on a
    typical spread; ``max_iter`` is a hard cap so a pathological input can
    never loop unbounded).

    Returns (centre, normal, radius, final_weights). One outlier click is
    annealed toward zero weight instead of tilting the plane; clicks are never
    mutated, only weighted (re-click pair-integrity safe)."""
    P = np.asarray(P, float)
    n_pts = len(P)
    w = np.ones(n_pts)
    centre, n = _weighted_plane_fit(P, w)
    centre, r = _weighted_kasa_circle(P, centre, n, w)

    def _residuals(centre_: np.ndarray, n_: np.ndarray, r_: np.ndarray) -> np.ndarray:
        d_plane = (P - centre_) @ n_
        proj = P - np.outer(d_plane, n_)
        d_radial = np.linalg.norm(proj - centre_, axis=1) - r_
        return np.sqrt(d_plane ** 2 + d_radial ** 2)

    resid = _residuals(centre, n, r)
    max_r = max(float(resid.max()), 1e-6)
    mu = (10.0 * max_r) ** 2
    mu_floor = 0.3 ** 2
    it = 0
    while mu >= mu_floor and it < max_iter:
        w = (mu / (mu + resid ** 2)) ** 2
        centre, n = _weighted_plane_fit(P, w)
        centre, r = _weighted_kasa_circle(P, centre, n, w)
        resid = _residuals(centre, n, r)
        mu /= 1.4
        it += 1
    return centre, n, r, w


def s1_gnc_circle(patch: np.ndarray, clicks_local: np.ndarray,
                  template: trimesh.Trimesh) -> StrategyResult:
    """GNC-robust circle -> ``_pinned_rim_seat`` on the single robust circle."""
    if len(clicks_local) < 3:
        return StrategyResult(None, None, {"reason": "fewer than 3 clicks"})
    centre, n, r, w = gnc_circle_fit(clicks_local)
    if not (1.0 <= r <= 8.0):
        return StrategyResult(None, None, {"reason": "gnc circle radius out of range",
                                           "radius_mm": r})
    seat = _pinned_rim_seat(patch, (centre, n, r), template)
    if seat is None:
        return StrategyResult(None, None, {"reason": "pinned seat refused gnc circle",
                                           "radius_mm": r,
                                           "min_weight": float(w.min())})
    pose, resid = seat
    return StrategyResult(pose, resid, {
        "radius_mm": r, "min_weight": float(w.min()), "max_weight": float(w.max()),
        "weights": [float(x) for x in w],
    })


# --------------------------------------------------------------------------
# Pose-delta parameterization (rotvec axis-angle + translation), shared by S2
# --------------------------------------------------------------------------

def delta_to_pose(delta: np.ndarray, base_pose: np.ndarray) -> np.ndarray:
    """Apply a 6-vector delta [rotvec(3), t(3)] as ``dR @ base_R``, ``base_t + dt``
    around ``base_pose`` — a small perturbation about a trusted seed, never an
    absolute re-parameterization (bounds are meaningful only relative to a seed)."""
    delta = np.asarray(delta, float)
    dR = Rotation.from_rotvec(delta[:3]).as_matrix()
    pose = np.eye(4)
    pose[:3, :3] = dR @ base_pose[:3, :3]
    pose[:3, 3] = base_pose[:3, 3] + delta[3:]
    return pose


def pose_to_delta(pose: np.ndarray, base_pose: np.ndarray) -> np.ndarray:
    """Inverse of ``delta_to_pose``: recovers the 6-vector delta that maps
    ``base_pose`` to ``pose`` (round-trip helper, used by the unit test and to
    report S2's final delta in mm/deg)."""
    dR = pose[:3, :3] @ base_pose[:3, :3].T
    rotvec = Rotation.from_matrix(dR).as_rotvec()
    dt = pose[:3, 3] - base_pose[:3, 3]
    return np.concatenate([rotvec, dt])


# --------------------------------------------------------------------------
# S2 — joint click+surface trust-region objective
# --------------------------------------------------------------------------

def s2_joint_click_surface(patch: np.ndarray, clicks_local: np.ndarray,
                           template: trimesh.Trimesh,
                           seed_pose: Optional[np.ndarray] = None,
                           max_patch_points: int = 1500,
                           max_nfev: int = 200) -> StrategyResult:
    """``scipy.optimize.least_squares`` over a 6-parameter delta (rotvec + t)
    around a seed pose (S0's winning pose by default — pass ``seed_pose``
    explicitly to warm-start from a different strategy's pose, e.g. for
    Protocol B's outlier-gesture runs). Residuals = concat[point-to-nearest-
    template-vertex distances for <= ``max_patch_points`` subsampled patch
    points (huber loss, f_scale=0.3), 3.0 * distance of each click to the
    posed template]. Bounds: |rotvec| <= 12 deg per component, |t| <= 1.5mm
    per component — a trust region BY CONSTRUCTION (the historical failure is
    ICP wandering; never allow unbounded search).

    ``max_patch_points``/``max_nfev`` are runtime knobs for the benchmark CLI
    (subsampling and iteration budget respectively); non-default values are
    recorded in the returned diagnostics."""
    if seed_pose is None:
        seed = s0_production_pinned(patch, clicks_local, template)
        if seed.pose is None:
            return StrategyResult(None, None, {"reason": "no S0 seed available"})
        seed_pose = seed.pose

    template_v = np.asarray(template.vertices, float)
    tree = cKDTree(template_v)

    sub_patch = patch
    if len(sub_patch) > max_patch_points:
        idx = np.linspace(0, len(sub_patch) - 1, max_patch_points).astype(int)
        sub_patch = sub_patch[idx]

    def _resid(delta: np.ndarray) -> np.ndarray:
        pose = delta_to_pose(delta, seed_pose)
        Rt, tt = pose[:3, :3], pose[:3, 3]
        # template-space points corresponding to local-space query points:
        # p_local = R @ p_template + t  =>  p_template = R^T @ (p_local - t)
        patch_in_template = (sub_patch - tt) @ Rt
        d_patch = tree.query(patch_in_template)[0]
        clicks_in_template = (clicks_local - tt) @ Rt
        d_clicks = tree.query(clicks_in_template)[0]
        return np.concatenate([d_patch, 3.0 * d_clicks])

    deg12 = np.radians(12.0)
    lb = np.array([-deg12, -deg12, -deg12, -1.5, -1.5, -1.5])
    ub = np.array([deg12, deg12, deg12, 1.5, 1.5, 1.5])
    x0 = np.zeros(6)
    result = least_squares(_resid, x0, loss="huber", f_scale=0.3,
                           bounds=(lb, ub), max_nfev=max_nfev)
    pose = delta_to_pose(result.x, seed_pose)
    d_patch = tree.query((sub_patch - pose[:3, 3]) @ pose[:3, :3])[0]
    seat_resid = float(d_patch.mean())
    return StrategyResult(pose, seat_resid, {
        "delta_rotvec_deg": [float(np.degrees(x)) for x in result.x[:3]],
        "delta_t_mm": [float(x) for x in result.x[3:]],
        "at_bound": bool(np.any(np.isclose(result.x, lb)) or np.any(np.isclose(result.x, ub))),
        "n_patch_points": len(sub_patch), "converged": bool(result.success),
        "max_nfev": max_nfev, "patch_subsampled": len(sub_patch) < len(patch),
    })


# --------------------------------------------------------------------------
# S3 — dense constrained grid search
# --------------------------------------------------------------------------

def _trimmed_mean(d: np.ndarray, drop_frac: float = 0.15) -> float:
    d = np.sort(d)
    keep = max(1, int(round(len(d) * (1.0 - drop_frac))))
    return float(d[:keep].mean())


def s3_dense_constrained_search(patch: np.ndarray, clicks_local: np.ndarray,
                                template: trimesh.Trimesh,
                                seed_pose: Optional[np.ndarray] = None,
                                tilt_deg: float = 9.0, tilt_step_deg: float = 3.0,
                                height_mm: float = 1.5, height_step_mm: float = 0.25,
                                max_score_points: int = 1500,
                                max_scored_patch_points: int = 1200) -> StrategyResult:
    """Grid over tilt cone +-``tilt_deg`` in ``tilt_step_deg`` steps (2 tilt axes
    about the seed circle's in-plane axes) x axial height +-``height_mm`` in
    ``height_step_mm`` steps along the circle normal. Score = trimmed mean
    (drop worst 15%) of patch->posed-template distances. Refine the coarse
    winner +-1 coarse step at half resolution. Clocking is skipped: distance
    metrics are clocking-blind on these revolute parts.

    RUNTIME NOTE: the coarse+fine grid is ~700-1000 candidate poses; scoring
    builds ONE KD-tree over the (fixed) template sample and, per candidate
    pose, transforms the (subsampled, <= ``max_scored_patch_points``) patch
    into template space and queries that one tree — never rebuilds a tree per
    pose (an earlier version did, at ~10ms/pose vs ~1ms/pose here). Both patch
    and template sample sizes are subsampling knobs surfaced for the benchmark
    CLI to tune the total-runtime budget; any non-default values are recorded
    in the returned diagnostics, never silently applied."""
    if seed_pose is None:
        seed = s0_production_pinned(patch, clicks_local, template)
        if seed.pose is None:
            circle_fit = _fit_circle_plane(clicks_local)
            if circle_fit is None:
                return StrategyResult(None, None, {"reason": "no seed pose and no circle"})
            centre, n, _r = circle_fit
            seat = _pinned_rim_seat(patch, (centre, n, _r), template)
            if seat is None:
                return StrategyResult(None, None, {"reason": "no seed pose available"})
            seed_pose = seat[0]
        else:
            seed_pose = seed.pose

    R0 = seed_pose[:3, :3]
    t0 = seed_pose[:3, 3]
    n_axis = R0 @ np.array([0.0, 0.0, 1.0])  # the seed circle's normal, in local space
    u = np.cross(n_axis, [0.0, 0.0, 1.0])
    if np.linalg.norm(u) < 1e-6:
        u = np.array([1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(n_axis, u)

    # DENSE, uniform surface sample (not the raw vertex set — a low-poly template's
    # vertices are too sparse/non-uniform to score sub-degree tilt differences
    # reliably; every other scoring path in production resamples the surface too,
    # e.g. auto_flow._rim_seat, _best_fit, _refine_best_fit)
    sampled, _ = trimesh.sample.sample_surface(template, max_score_points)
    sub_template = np.asarray(sampled, float)
    # ONE tree over the FIXED template sample (in the template's own local frame);
    # score a candidate pose by transforming the (small) patch into template space
    # and querying this one tree, instead of rebuilding a tree per candidate pose
    template_tree = cKDTree(sub_template)

    sub_patch = patch
    if len(sub_patch) > max_scored_patch_points:
        idx = np.linspace(0, len(sub_patch) - 1, max_scored_patch_points).astype(int)
        sub_patch = sub_patch[idx]

    def _pose_for(tilt_u_deg: float, tilt_v_deg: float, h: float) -> np.ndarray:
        Ru = Rotation.from_rotvec(np.radians(tilt_u_deg) * u).as_matrix()
        Rv = Rotation.from_rotvec(np.radians(tilt_v_deg) * v).as_matrix()
        R = Rv @ Ru @ R0
        pose = np.eye(4)
        pose[:3, :3] = R
        pose[:3, 3] = t0 + h * n_axis
        return pose

    def _score(pose: np.ndarray) -> float:
        # p_local = R @ p_template + t  =>  p_template = R^T @ (p_local - t)
        patch_in_template = (sub_patch - pose[:3, 3]) @ pose[:3, :3]
        d = template_tree.query(patch_in_template)[0]
        return _trimmed_mean(d)

    def _grid_search(tilt_range, tilt_step, h_range, h_step, center_tu, center_tv, center_h):
        tus = np.arange(center_tu - tilt_range, center_tu + tilt_range + 1e-9, tilt_step)
        tvs = np.arange(center_tv - tilt_range, center_tv + tilt_range + 1e-9, tilt_step)
        hs = np.arange(center_h - h_range, center_h + h_range + 1e-9, h_step)
        best = None
        for tu in tus:
            for tv in tvs:
                for h in hs:
                    pose = _pose_for(tu, tv, h)
                    sc = _score(pose)
                    if best is None or sc < best[0]:
                        best = (sc, tu, tv, h, pose)
        return best

    coarse = _grid_search(tilt_deg, tilt_step_deg, height_mm, height_step_mm, 0.0, 0.0, 0.0)
    if coarse is None:
        return StrategyResult(None, None, {"reason": "empty coarse grid"})
    _sc, tu, tv, h, _pose = coarse
    fine = _grid_search(tilt_step_deg, tilt_step_deg / 2.0,
                        height_step_mm, height_step_mm / 2.0, tu, tv, h)
    best = fine if (fine is not None and fine[0] <= coarse[0]) else coarse
    score, tu, tv, h, pose = best
    return StrategyResult(pose, score, {
        "tilt_u_deg": float(tu), "tilt_v_deg": float(tv), "height_mm": float(h),
        "coarse_grid_points": int(((2 * tilt_deg / tilt_step_deg) + 1) ** 2
                                  * ((2 * height_mm / height_step_mm) + 1)),
        "template_score_points": len(sub_template), "patch_score_points": len(sub_patch),
        "patch_subsampled": len(sub_patch) < len(patch),
    })


STRATEGIES = {
    "S0-production-pinned": s0_production_pinned,
    "S1-gnc-circle": s1_gnc_circle,
    "S2-joint-click-surface": s2_joint_click_surface,
    "S3-dense-constrained-search": s3_dense_constrained_search,
}
