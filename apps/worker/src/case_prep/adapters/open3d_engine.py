"""Open3D registration engine — the only module that imports Open3D (lazily), so the
rest of the package stays testable without it.

Pipeline per implant: localize (cluster protrusions standing proud of the gingiva)
-> seed a transform from the cluster centroid + PCA axis -> trimmed point-to-plane
ICP refine. For screw-retained sites, multi-start ICP about the axis recovers the
clocking and the best-vs-antipodal RMSE gap measures anti-rotation confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

from case_prep.domain.confidence import ConfidenceScore
from case_prep.domain.geometry import RigidTransform
from case_prep.domain.icp import trimmed_icp
from case_prep.domain.poses import Retention
from case_prep.adapters.rng import PipelineRng, sample_surface

_UP = np.array([0.0, 0.0, 1.0])  # synthetic frame is z-up; real scans get normalized upstream
_FEATURE_RESID_FLOOR = 0.05  # mm; clocking-ratio denominator floor (mesh-sampling resolution)
# Body-isolating ROI for operator-seeded localization on a dense arch. The body is a ~vertical
# post; the arch spreads horizontally. A vertical cylinder about the occlusal normal + a surface-
# normal filter (drop horizontal arch, keep the body's lateral wall) isolates the body from the
# surrounding teeth that otherwise dominate a sphere crop (~3/4 tissue) and bias registration.
_ROI_CYL_RADIUS = 3.5  # mm
_ROI_CYL_HALF_HEIGHT = 5.0  # mm
_ROI_CORE_RADIUS = 2.6  # mm; near-axis core kept regardless of normal (the body cap/top, which
#                         constrains AXIAL position — a lateral wall alone slides along its axis)
_ROI_NORMAL_MAX = 0.5  # keep points whose surface normal is >~60deg off the occlusal normal
_ROI_NORMAL_NN = 16  # neighbours used to estimate each point's surface normal
# Auto-localization (no operator seed): template-match the library CAD along the occlusal ridge.
# A real body fills the isolating ROI and the CAD registers well (fitness ~0.65); a tooth gives a
# sparse ROI and a poor fit (~0.2). Both gaps are used — ROI-fill as a cheap pre-filter, fitness
# as the confirming discriminator.
_DETECT_ROI_MIN = 1000  # a body fills the isolating ROI; a tooth crop is far sparser (~700)
_DETECT_QUICK_MIN = 0.35  # cheap coarse-fit screen: shortlist candidates worth a full registration
_DETECT_FITNESS_MIN = 0.40  # a registered CAD fitting this well marks a body (teeth ~0.2)
_DETECT_NMS_RADIUS = 4.0  # mm; suppress duplicate detections of the same body
_CANDIDATE_SPACING = 2.5  # mm; farthest-point spacing of ridge candidate seeds
_CANDIDATE_MAX = 48  # cap on candidate seeds, to bound the multi-start cost
# Axis-cone seeds for the registration multi-start. loc.axis is a noisy PCA of an (often
# occluded) blob, and near-symmetric / chunky bodies (e.g. coded scan abutments) admit a
# competing basin tilted ~45deg off; clocking-only starts can miss the correct basin. Seeding a
# few axis tilts (in addition to clocking) lets ICP reach the true basin, which then wins on
# plain surface RMSE. Kept small (5 seeds) to bound the multi-start cost.
def _axis_cone() -> list:
    R = RigidTransform.from_axis_angle
    deg = 18.0
    return [
        np.eye(3),
        R([1.0, 0.0, 0.0], deg).rotation, R([1.0, 0.0, 0.0], -deg).rotation,
        R([0.0, 1.0, 0.0], deg).rotation, R([0.0, 1.0, 0.0], -deg).rotation,
        # NOTE: a 180° flip seed was tried here (to be canonical-z-sign agnostic) and REVERTED:
        # on a near-flip-symmetric cap under occlusion the upside-down basin sometimes wins on
        # RMSE, degrading real-arch recovery. The canonical frame is instead kept stable by
        # making canonicalize_library idempotent (fixed-point early return) — see ingest.py.
    ]


_AXIS_CONE = _axis_cone()
_MULTISTART_REFINE = 6  # how many best coarse basins get the full fine ICP


def _o3d():
    import open3d as o3d  # lazy: keeps Open3D out of the importable core
    return o3d


@dataclass
class Localization:
    centroid: np.ndarray
    axis: np.ndarray  # unit, points away from gingiva
    base_point: np.ndarray  # near-gingiva end of the scan body
    roi_points: np.ndarray  # Nx3 region of interest for ICP


def _pcd(points: np.ndarray):
    o3d = _o3d()
    p = o3d.geometry.PointCloud()
    p.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    return p


def localize(scan_points: np.ndarray, max_clusters: int) -> List[Localization]:
    """Find scan-body instances as clusters of points standing proud of the gingiva,
    returning up to ``max_clusters`` of them (largest first). The caller compares the
    count returned against the declared count to reconcile — detection is NOT capped to
    the declared count, so an over- or under-count is observable rather than hidden."""
    pts = np.asarray(scan_points, dtype=float)
    height = pts @ _UP
    # Just above the gingiva, so each cluster spans the FULL scan-body shaft (not just
    # the top) — otherwise PCA of a short top-segment yields a wrong (horizontal) axis.
    thr = height.min() + 0.2 * (height.max() - height.min())
    above = pts[height > thr]

    pcd = _pcd(above)
    labels = np.asarray(pcd.cluster_dbscan(eps=2.5, min_points=10))

    sizes = [(lbl, int(np.sum(labels == lbl))) for lbl in set(labels.tolist()) if lbl >= 0]
    sizes.sort(key=lambda x: -x[1])
    chosen = [lbl for lbl, _ in sizes[:max_clusters]]

    centers = [above[labels == lbl][:, :2].mean(axis=0) for lbl in chosen]
    locs = [_build_localization(pts, height, thr, c) for c in centers]
    return [loc for loc in locs if loc is not None]


def _build_localization(pts: np.ndarray, height: np.ndarray, thr: float, xy_center: np.ndarray):
    """Crop the body shaft around an xy seed and derive its axis + on-axis base point.
    Shared by automatic clustering and operator-seeded (stage-2) localization."""
    in_column = np.linalg.norm(pts[:, :2] - xy_center, axis=1) < 4.5
    # Axis + seed come from the clean shaft (above gingiva). The ICP ROI extends ~1mm
    # lower to include the base cap, which constrains axial position.
    core = pts[in_column & (height > thr)]
    roi = pts[in_column & (height > thr - 1.0)]
    if len(core) < 10:
        return None  # degenerate cluster (e.g. a stray clump) — not a usable scan body

    centroid = core.mean(axis=0)
    _, _, vt = np.linalg.svd(core - centroid, full_matrices=False)
    axis = vt[0] / np.linalg.norm(vt[0])  # tallest spread = body axis
    if axis @ _UP < 0:
        axis = -axis
    proj = core @ axis
    base_point = centroid + axis * (proj.min() - float(centroid @ axis))
    return Localization(centroid, axis, base_point, roi)


def _lateral_mask(points: np.ndarray, normals: Optional[np.ndarray] = None) -> np.ndarray:
    """Boolean mask: True for points on a roughly VERTICAL surface (a scan-body wall), False for
    the horizontal arch (occlusal surface, normal ~parallel to the occlusal normal). Uses the
    mesh's real vertex normals when supplied (accurate); otherwise estimates them by PCA of each
    point's neighbourhood (pure numpy/scipy — no Open3D)."""
    if normals is not None and len(normals) == len(points):
        n = np.asarray(normals, float)
    elif len(points) >= _ROI_NORMAL_NN:
        _, idx = cKDTree(points).query(points, k=_ROI_NORMAL_NN)
        nbrs = points[idx]                                  # (n, k, 3)
        centred = nbrs - nbrs.mean(axis=1, keepdims=True)
        cov = np.einsum("nki,nkj->nij", centred, centred)   # (n, 3, 3) neighbourhood covariance
        n = np.linalg.eigh(cov)[1][:, :, 0]                 # smallest-variance eigenvector = normal
    else:
        return np.ones(len(points), dtype=bool)
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, norm, out=np.zeros_like(n), where=norm > 1e-9)
    return np.abs(n @ _UP) < _ROI_NORMAL_MAX


def localize_from_seed(scan_points: np.ndarray, seed_point, radius: float = 5.5,
                       normals: Optional[np.ndarray] = None):
    """Localize a single scan body from an operator's 3-D seed (a click ON the body), the stage-2
    entry and the reliable real-scan path. On a dense arch the body is fused to the surrounding
    teeth, so a plain sphere crop is ~3/4 tissue and biases ICP. Instead we ISOLATE the body:
    (1) a VERTICAL CYLINDER about the occlusal normal through the seed (the body is a vertical
    post; the arch spreads horizontally); (2) a surface-NORMAL filter dropping the horizontal arch
    and keeping the body's lateral wall; (3) the axis seed is the occlusal normal (reliable),
    refined by registration's axis cone -- NOT a PCA of the contaminated crop. Falls back to a
    sphere crop when the isolated set is too small (e.g. clean synthetic bodies)."""
    pts = np.asarray(scan_points, dtype=float)
    seed = np.asarray(seed_point, dtype=float)[:3]
    nrm = np.asarray(normals, dtype=float) if normals is not None else None
    rel = pts - seed
    axial = rel @ _UP
    radial = np.linalg.norm(rel - np.outer(axial, _UP), axis=1)
    sel = (radial < _ROI_CYL_RADIUS) & (np.abs(axial) < _ROI_CYL_HALF_HEIGHT)
    if sel.sum() < 10:
        sel = np.linalg.norm(rel, axis=1) < radius  # sphere fallback (sparse/edge cases)
        if sel.sum() < 10:
            return None
    core = pts[sel]
    core_n = nrm[sel] if nrm is not None else None
    # Keep the body's lateral wall (drops the far horizontal arch) PLUS the near-axis core (the
    # cap/top, which constrains axial position). Together they isolate the body from surrounding
    # teeth while keeping the full body geometry on a clean (synthetic/isolated) case.
    keep = _lateral_mask(core, core_n) | (radial[sel] < _ROI_CORE_RADIUS)
    roi = core[keep] if keep.sum() >= 10 else core
    # Axis = PCA of the ISOLATED body. On a clean/isolated body this is the true body axis (as
    # before); on a real arch the isolation has removed the contaminating teeth, so the PCA is no
    # longer dragged off by tissue. Registration's axis cone refines it.
    centroid = roi.mean(axis=0)
    _, _, vt = np.linalg.svd(roi - centroid, full_matrices=False)
    axis = vt[0] / np.linalg.norm(vt[0])
    if axis @ _UP < 0:
        axis = -axis
    proj = roi @ axis
    base_point = centroid + axis * (proj.min() - float(centroid @ axis))
    return Localization(centroid, axis, base_point, roi)


def _rotation_align(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Rotation mapping unit vector a onto unit vector b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = float(a @ b)
    if s < 1e-8:
        return np.eye(3) if c > 0 else RigidTransform.from_axis_angle([1, 0, 0], 180.0).rotation
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def _sample(mesh, k: int = 2500, rng: "Optional[PipelineRng]" = None) -> np.ndarray:
    """Sample the library mesh for ICP. This is RANDOM: without an injected stream it
    draws from numpy's process-global one, which is why registration used to inherit
    whatever the caller had seeded (see adapters/rng.py)."""
    return sample_surface(rng, mesh, k)


def _icp_coarse(source_pts, target_pts, t_init: np.ndarray, target_tree=None):
    """Cheap wide-radius ICP — enough to rank a seed's basin, not to finish it."""
    return trimmed_icp(source_pts, target_pts, t_init, max_corr_dist=2.0, max_iter=25,
                       target_tree=target_tree)


def _icp_fine(source_pts, target_pts, t_init: np.ndarray, target_tree=None):
    """Tight-radius trimmed ICP — the accurate refinement from a good coarse seed."""
    return trimmed_icp(
        source_pts, target_pts, t_init, max_corr_dist=0.6, trim_fraction=0.85, max_iter=60,
        target_tree=target_tree,
    )


def register(
    loc: Localization, library_mesh, retention: Retention, multistart: int = 12,
    axis_bound_deg: Optional[float] = None,
    rng: "Optional[PipelineRng]" = None,
) -> Tuple[RigidTransform, ConfidenceScore]:
    """``axis_bound_deg`` is an OPT-IN seating constraint: pass it only when ``loc.axis``
    is a genuine clinical prior (the cap flow seeds it crowns-up — a component cannot seat
    sideways/upside-down). Leave None when loc.axis is a rough PCA hint (arbitrary-pose
    part recovery): bounding against a noisy hint forbids correct basins.

    ``rng``: the caller's owned random stream for the library-mesh sampling below. None
    keeps the historical process-global draw (see adapters/rng.py's migration shim)."""
    target_pts = np.asarray(loc.roi_points, dtype=float)
    lib_pts = _sample(library_mesh, rng=rng)

    R0 = _rotation_align(_UP, loc.axis)

    def seed(clock_deg: float, tilt: np.ndarray) -> np.ndarray:
        t = np.eye(4)
        t[:3, :3] = tilt @ R0 @ RigidTransform.from_axis_angle(_UP, clock_deg).rotation
        t[:3, 3] = loc.base_point
        return t

    # Multi-start about the axis ALWAYS (the anti-rotation flat must be geometrically aligned for
    # an accurate position+axis), AND over a small AXIS CONE: loc.axis is a noisy PCA of an
    # occluded blob, and a near-symmetric body admits a competing basin ~45deg off. Clocking-only
    # starts can miss the correct basin entirely; seeding a few axis tilts lets ICP reach it, then
    # plain best-RMSE selects it (no fragile selection prior needed). Matches the validated harness.
    #
    # To keep the thorough search cheap, COARSE-rank every (clock x cone) seed, then run the full
    # FINE ICP only on the best few basins — ~3x less work than fine-refining all ~60 seeds.
    def _axis_plausible(t: np.ndarray) -> bool:
        # DOMAIN CONSTRAINT, not a selection prior: with a clinical axis prior, trimmed
        # ICP wandering into a flipped/sideways basin can WIN on RMSE (a fit that explains
        # less of the part trims away the unexplained points — measured: a squat cap
        # registering 180 deg flipped). Such a basin is geometrically impossible.
        if axis_bound_deg is None:
            return True
        return float((t[:3, :3] @ _UP) @ loc.axis) > np.cos(np.radians(axis_bound_deg))

    def _rank(cr):
        return cr[1].inlier_rmse if cr[1].fitness > 0.1 else 1e9

    def _rank_fine(cr):
        # the axis constraint gates FINAL verdicts only — coarse (unconverged) results
        # wander transiently, and filtering them would drop the path to the true basin
        # (measured: a clean-part recovery losing its correct coarse candidate)
        if cr[1].fitness <= 0.1 or not _axis_plausible(cr[1].transform.matrix):
            return 1e9
        return cr[1].inlier_rmse

    roi_tree = cKDTree(target_pts)  # ONE tree for all ~66 coarse+fine trials
    coarse = [
        (c, _icp_coarse(lib_pts, target_pts, seed(c, tilt), target_tree=roi_tree))
        for c in np.linspace(0, 360, multistart, endpoint=False)
        for tilt in _AXIS_CONE
    ]
    coarse.sort(key=_rank)
    trials = [
        (c, _icp_fine(lib_pts, target_pts, res.transform.matrix, target_tree=roi_tree))
        for c, res in coarse[:_MULTISTART_REFINE]
    ]
    trials.sort(key=_rank_fine)
    best_clock, best = trials[0]
    if not _axis_plausible(best.transform.matrix):
        # every refined basin violates the seating cone — return the best-RMSE fit rather
        # than an arbitrary violator, and make the violation VISIBLE: fitness 0 routes the
        # site to the advisory/review path instead of silently shipping a sideways pose
        trials.sort(key=_rank)
        best_clock, best = trials[0]
        best = replace(best, fitness=0.0)

    if retention is Retention.SCREW:
        # Clocking confidence is measured ON the anti-rotation feature, not over the whole
        # surface (where it is swamped). The feature = library points indented from the
        # cylinder radius (geometry-agnostic: a flat/notch sits inside the round envelope).
        # Compare the feature's fit at the best clock vs a RIGID 180-degree flip about the
        # axis (no ICP — re-running ICP would just re-converge to the correct clock and
        # hide the ambiguity). A captured flat makes the flipped fit far worse (ratio >> 1);
        # a symmetric/uncaptured one leaves them similar (ratio ~ 1) and the gate flags it.
        flip_local = RigidTransform.from_axis_angle(_UP, 180.0).matrix
        t_flip = best.transform.matrix @ flip_local
        radial = np.linalg.norm(lib_pts[:, :2], axis=1)
        feature = lib_pts[radial < radial.max() - 0.2]
        tree = cKDTree(target_pts)

        def feature_residual(t: np.ndarray) -> float:
            world = feature @ t[:3, :3].T + t[:3, 3]
            return float(tree.query(world)[0].mean())

        resid_best = feature_residual(best.transform.matrix)
        # Floor the denominator at the mesh-sampling resolution: a spuriously tiny
        # resid_best (over-fit on a sparse/occluded feature) must not inflate the ratio
        # into false clocking confidence.
        gap = float(feature_residual(t_flip) / max(resid_best, _FEATURE_RESID_FLOOR))
        conf = ConfidenceScore(
            icp_fitness=float(best.fitness),
            inlier_rmse_mm=float(best.inlier_rmse),
            multi_implant_consistent=True,  # set by the orchestrator across implants
            clocking_gap=gap,
            anti_rotation_residual=resid_best,
        )
    else:
        conf = ConfidenceScore(
            icp_fitness=float(best.fitness),
            inlier_rmse_mm=float(best.inlier_rmse),
            multi_implant_consistent=True,
            clocking_gap=None,  # cement: clocking not evaluated
            anti_rotation_residual=None,
        )
    return best.transform, conf


@dataclass
class Detection:
    localization: Localization
    transform: RigidTransform
    fitness: float


def _ridge_candidates(points: np.ndarray, spacing: float, max_n: int) -> np.ndarray:
    """Farthest-point-sampled seeds over the occlusal ridge (the high-z band), so candidate body
    locations are well spread with a bounded count."""
    band = points[points[:, 2] > points[:, 2].max() - 4.0]
    if len(band) == 0:
        return np.empty((0, 3))
    start = int(np.argmax(band[:, 2]))
    chosen = [start]
    d = np.linalg.norm(band - band[start], axis=1)
    while len(chosen) < max_n and d.max() > spacing:
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.linalg.norm(band - band[i], axis=1))
    return band[chosen]


def _quick_fit(loc: Localization, lib_pts: np.ndarray):
    """Cheap coarse-ICP from a few clocking seeds — enough to tell a body-shaped ROI from a tooth
    without paying the full axis-cone multi-start. Returns (fitness, rough_centre) where the centre
    is the coarse fit's recovered library origin (~the body centre), used to re-seed the ROI."""
    R0 = _rotation_align(_UP, loc.axis)
    target = np.asarray(loc.roi_points, dtype=float)
    best_rmse, best_fit, best_centre = 1e9, 0.0, None
    for c in np.linspace(0, 360, 4, endpoint=False):
        t = np.eye(4)
        t[:3, :3] = R0 @ RigidTransform.from_axis_angle(_UP, c).rotation
        t[:3, 3] = loc.base_point
        res = _icp_coarse(lib_pts, target, t)
        if res.fitness > 0.1 and res.inlier_rmse < best_rmse:
            best_rmse, best_fit, best_centre = res.inlier_rmse, res.fitness, res.transform.matrix[:3, 3]
    return best_fit, best_centre


def auto_localize(scan_points: np.ndarray, library_mesh, max_bodies: int,
                  normals: Optional[np.ndarray] = None,
                  retention: Retention = Retention.CEMENT) -> List[Detection]:
    """Detect scan bodies on a dense arch WITHOUT an operator seed, by template-matching the
    library CAD along the occlusal ridge. At each candidate ridge point we isolate a body-shaped
    ROI (see localize_from_seed) and check how well the CAD fits: a real body fills the ROI and
    fits well (fitness ~0.65), a tooth gives a sparse ROI and a poor fit (~0.2). Three-stage to
    stay cheap: ROI-fill pre-filter -> coarse-fit screen -> full registration only on the non-max-
    suppressed survivors (the actual bodies)."""
    pts = np.asarray(scan_points, dtype=float)
    nrm = np.asarray(normals, dtype=float) if normals is not None else None
    lib_pts = _sample(library_mesh)
    candidates = _ridge_candidates(pts, _CANDIDATE_SPACING, _CANDIDATE_MAX)

    # cheap screen: keep candidates whose isolated ROI both fills and coarsely fits the CAD, then
    # RE-CENTRE the ROI on the coarse fit's recovered body centre (the ridge candidate is typically
    # ~2mm off, which otherwise clips the body and depresses the final fit below threshold).
    shortlist = []
    for seed in candidates:
        loc = localize_from_seed(pts, seed, normals=nrm)
        if loc is None or len(loc.roi_points) < _DETECT_ROI_MIN:
            continue
        qf, centre = _quick_fit(loc, lib_pts)
        if qf < _DETECT_QUICK_MIN or centre is None:
            continue
        recentred = localize_from_seed(pts, centre, normals=nrm)
        shortlist.append((qf, recentred if recentred is not None else loc))

    # non-max suppression on the coarse fitness, then take up to max_bodies distinct sites
    shortlist.sort(key=lambda x: -x[0])
    kept_locs: List[Localization] = []
    for _, loc in shortlist:
        if all(np.linalg.norm(loc.centroid - k.centroid) > _DETECT_NMS_RADIUS for k in kept_locs):
            kept_locs.append(loc)
        if len(kept_locs) >= max_bodies:
            break

    # confirm each survivor with the full axis-cone registration, then REFINE: re-localize at the
    # recovered platform centre (now well-centred on the body, unlike the ~2mm-off ridge seed) and
    # re-register. This sharpens the near-symmetric axis the detection seed leaves noisy.
    detections: List[Detection] = []
    for loc in kept_locs:
        transform, conf = register(loc, library_mesh, retention)
        refined = localize_from_seed(pts, transform.apply(np.zeros(3)), normals=nrm)
        if refined is not None:
            t2, c2 = register(refined, library_mesh, retention)
            if c2.icp_fitness >= conf.icp_fitness:  # keep the sharper fit
                loc, transform, conf = refined, t2, c2
        if conf.icp_fitness >= _DETECT_FITNESS_MIN:
            detections.append(Detection(loc, transform, float(conf.icp_fitness)))
    return detections
