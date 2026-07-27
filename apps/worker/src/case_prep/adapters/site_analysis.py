"""Healing-cap site analysis on a doctor's arch scan (upper or lower):

  * find the CENTER of a healing cap / scan body (deliverable A);
  * measure the INTERPROXIMAL GAP — the mesio-distal space to the adjacent teeth (deliverable B).

Type-agnostic: works from the scan surface + a rough cap location, no library template required.
The gap is the CORONAL (contact-point / restorative) mesio-distal space recoverable from a surface
scan; bone-level inter-radicular space needs CBCT (see ``caveats``). Clinical thresholds and the
measurement approach follow the design in docs/engagement (Rules-of-Six / ADI spacing guidance).

Pure numpy/scipy + trimesh; no Open3D (its ICP segfaults on this host — clustering here is scipy).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy.spatial import cKDTree

# clinical mesio-distal thresholds (mm) for a single conventional implant restoration
_MD_AMPLE = 7.0        # >= this: room for a standard ~4mm implant (>=1.5mm clearance each side)
_MD_NARROW = 6.0       # [_MD_NARROW, _MD_AMPLE): narrow (3.5mm) implant territory
_MD_TWO_IMPLANT = 12.0  # >= this: room for two implants posteriorly
_TOOTH_MIN_PTS = 800   # a real neighbour crown is a large cluster; smaller = stray fragment/noise
_CLUSTER_LINK_MM = 1.3  # connected-component link distance for crown clustering (occlusal plane)


@dataclass
class InterproximalSite:
    cap_center: List[float]                 # world-frame cap centre (occlusal-plane centroid)
    cap_radius_mm: float
    occlusal_axis: List[float]              # unit; occlusal normal used for the analysis
    mesio_distal_direction: Optional[List[float]] = None  # unit arch tangent (None if undetermined)
    md_span_mm: Optional[float] = None      # tooth-to-tooth mesio-distal space (the clinical number)
    gap_mesial_mm: Optional[float] = None   # cap -> one neighbour clearance
    gap_distal_mm: Optional[float] = None   # cap -> other neighbour clearance
    adjacent_teeth: List[List[float]] = field(default_factory=list)  # neighbour crown centroids (world)
    terminal_site: bool = False             # only one neighbour found (free-end site)
    classification: str = "unknown"
    caveats: List[str] = field(default_factory=list)
    md_span_points: Optional[List[List[float]]] = None  # the two world points defining the span


def occlusal_axis(vertices: np.ndarray) -> np.ndarray:
    """Robust occlusal normal = the arch's SMALLEST-spread principal axis (an arch is a thin curved
    shell; its thinnest direction is occlusal-apical). More reliable than a chunky cap's own PCA or
    normalize_orientation, which can flip on a sparse edentulous arch."""
    v = np.asarray(vertices, float)
    c = v - v.mean(axis=0)
    w, vec = np.linalg.eigh(c.T @ c)
    axis = vec[:, 0]  # smallest eigenvalue
    # orient toward the crowns (the protruding, high-density-at-extreme side)
    h = c @ axis
    if np.mean(h > np.percentile(h, 90)) < np.mean(h < np.percentile(h, 10)):
        axis = -axis
    return axis / np.linalg.norm(axis)


def _plane_basis(axis: np.ndarray):
    a = axis / np.linalg.norm(axis)
    t0 = np.cross(a, [0, 0, 1.0])
    t0 = t0 / np.linalg.norm(t0) if np.linalg.norm(t0) > 1e-6 else np.array([1.0, 0, 0])
    return t0, np.cross(a, t0)


def _cluster(xy: np.ndarray, link: float) -> np.ndarray:
    """Connected-component clustering in the occlusal plane (scipy KDTree; DBSCAN-equivalent)."""
    tree = cKDTree(xy)
    nbrs = tree.query_ball_tree(tree, r=link)
    lab = -np.ones(len(xy), dtype=int)
    cid = 0
    for i in range(len(xy)):
        if lab[i] >= 0:
            continue
        stack = [i]
        lab[i] = cid
        while stack:
            j = stack.pop()
            for k in nbrs[j]:
                if lab[k] < 0:
                    lab[k] = cid
                    stack.append(k)
        cid += 1
    return lab


def cap_center(vertices: np.ndarray, seed, occ_axis: np.ndarray,
               radius: float = 6.0, axial_band: float = 3.5):
    """Deliverable A: the healing-cap centre = the occlusal-plane centroid of the cap points near a
    rough seed (an operator click, an auto-detection, or the segmented scan body). Type-agnostic.
    Bounds BOTH the radial and axial extent so it isolates the compact cap, not the whole vertical
    column through the tooth/gingiva below it."""
    V = np.asarray(vertices, float)
    seed = np.asarray(seed, float)
    a = occ_axis / np.linalg.norm(occ_axis)
    rel = V - seed
    axial = rel @ a
    radial = np.linalg.norm(rel - np.outer(axial, a), axis=1)
    cap = V[(radial < radius) & (np.abs(axial) < axial_band)]
    if len(cap) < 20:
        return seed, radius
    center = cap.mean(axis=0)
    cap_r = float(np.percentile(np.linalg.norm((cap - center) - np.outer((cap - center) @ a, a), axis=1), 95))
    return center, cap_r


def measure_site(vertices: np.ndarray, cap_center_mm, cap_radius: float,
                 occ_axis: Optional[np.ndarray] = None) -> InterproximalSite:
    """Deliverable B (+ echoes A): the interproximal gap to the adjacent teeth for one healing-cap
    site. ``cap_center_mm`` + ``cap_radius`` come from detection/segmentation (deliverable A); this
    decouples the gap measurement from how the cap was found."""
    V = np.asarray(vertices, float)
    a = occlusal_axis(V) if occ_axis is None else occ_axis / np.linalg.norm(occ_axis)
    t0, t1 = _plane_basis(a)
    center = np.asarray(cap_center_mm, float)
    cap_r = float(cap_radius)
    caveats = [
        "md_span is the CORONAL contact-point (restorative) mesio-distal space; bone-level "
        "inter-radicular spacing at the crest requires CBCT and is not derivable from a surface scan.",
        "mesial/distal labels are geometric (the two arch directions); true anatomical mesial/distal "
        "needs the arch's anterior direction (tooth numbering).",
    ]

    def occ_xy(P):
        d = P - center
        return np.c_[d @ t0, d @ t1]

    h = V @ a
    xy = occ_xy(V)
    r = np.linalg.norm(xy, axis=1)
    site = r < 20.0
    Vs, hs, xys, rs = V[site], h[site], xy[site], r[site]

    # crowns = the high occlusal band, with the cap footprint removed
    crown = (hs > np.percentile(hs, 60)) & (rs > cap_r + 0.5)
    Cxy, Ch, Cw = xys[crown], hs[crown], Vs[crown]
    base = dict(cap_center=[float(x) for x in center], cap_radius_mm=cap_r,
                occlusal_axis=[float(x) for x in a], caveats=caveats)
    if len(Cxy) < _TOOTH_MIN_PTS:
        return InterproximalSite(**base, classification="no adjacent teeth found")

    lab = _cluster(Cxy, _CLUSTER_LINK_MM)
    import collections
    sizes = collections.Counter(lab)
    teeth = [c for c, n in sizes.items() if n >= _TOOTH_MIN_PTS]
    # the two neighbour crowns nearest the cap (by occlusal-plane centroid distance)
    teeth.sort(key=lambda c: np.linalg.norm(Cxy[lab == c].mean(0)))
    neighbours = teeth[:2]
    if not neighbours:
        return InterproximalSite(**base, classification="no adjacent teeth found")

    def side_points(c):
        m = lab == c
        return Cw[m], Cxy[m], Ch[m]

    P_a, xy_a, h_a = side_points(neighbours[0])
    cent_a = xy_a.mean(0)
    if len(neighbours) == 1:  # terminal / free-end site: one neighbour, no mesio-distal span
        g = _cap_to_tooth(V, center, a, cap_r, xy_a, occ_xy)
        return InterproximalSite(**base, gap_mesial_mm=float(g), terminal_site=True,
                                 adjacent_teeth=[[float(x) for x in P_a.mean(0)]],
                                 classification="terminal site (one neighbour) — mesio-distal span undefined")

    P_b, xy_b, h_b = side_points(neighbours[1])
    cent_b = xy_b.mean(0)
    tang = cent_a - cent_b
    tang = tang / np.linalg.norm(tang)

    # md_span = nearest tooth-to-tooth distance at the contact band (upper-middle of the crowns);
    # capture the two world endpoints so the measurement can be drawn truthfully.
    band_a = h_a > np.percentile(np.r_[h_a, h_b], 40)
    band_b = h_b > np.percentile(np.r_[h_a, h_b], 40)
    Paw, Pbw, xa, xb = P_a[band_a], P_b[band_b], xy_a[band_a], xy_b[band_b]
    md_span, md_points = None, None
    if len(xa) and len(xb):
        dists, idx = cKDTree(xb).query(xa)
        k = int(dists.argmin())
        md_span = float(dists[k])
        md_points = [[float(x) for x in Paw[k]], [float(x) for x in Pbw[idx[k]]]]

    # cap -> each neighbour clearance, from the cap footprint points
    g_a = _cap_to_tooth(V, center, a, cap_r, xy_a, occ_xy)
    g_b = _cap_to_tooth(V, center, a, cap_r, xy_b, occ_xy)
    mesial, distal = (g_a, g_b) if (cent_a @ tang) >= 0 else (g_b, g_a)  # geometric mesial/distal

    # a FAILED measurement must say so — "insufficient" is a clinical verdict, not a
    # fallback for "could not measure" (sweep finding 2026-07-12)
    cls = ("span unmeasurable — check manually" if md_span is None else
           "two-implant-capable (>=12mm)" if md_span >= _MD_TWO_IMPLANT else
           "ample (>=7mm)" if md_span >= _MD_AMPLE else
           "narrow-implant (~6-7mm)" if md_span >= _MD_NARROW else
           "insufficient (<6mm)")

    return InterproximalSite(
        **base, mesio_distal_direction=[float(x) for x in tang], md_span_mm=md_span,
        gap_mesial_mm=(float(mesial) if mesial == mesial else None),   # NaN -> None:
        gap_distal_mm=(float(distal) if distal == distal else None),   # JSON-safe report
        adjacent_teeth=[[float(x) for x in P_a.mean(0)], [float(x) for x in P_b.mean(0)]],
        classification=cls, md_span_points=md_points)


def cap_seed_mask(V, center, a, cap_r):
    rel = V - center
    axial = rel @ a
    return np.linalg.norm(rel - np.outer(axial, a), axis=1) < cap_r


def _cap_to_tooth(V, center, a, cap_r, tooth_xy, occ_xy) -> float:
    cap_pts = occ_xy(V[cap_seed_mask(V, center, a, cap_r)])
    if len(cap_pts) == 0 or len(tooth_xy) == 0:
        return float("nan")
    return float(cKDTree(tooth_xy).query(cap_pts)[0].min())
