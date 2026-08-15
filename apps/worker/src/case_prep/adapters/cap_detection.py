"""Clinical healing-cap detection on a doctor's arch scan.

Low-profile healing caps defeat the tall-scan-body detector: template fitness alone ranks
tooth domes above real caps (measured on the client's Neodent healing arch). This module is
the validated discriminator stack instead:

  1. ``crown_up_axis`` — the occlusal axis is the arch's thinnest principal direction; its
     SIGN is disambiguated by bump topology: the crowns side carries MANY separate bumps
     (cusps, cap rings) spread along the arch, the palate side one compact dome. (The naive
     protrusion-tail heuristic flips on full upper-jaw scans.)
  2. Height window — a cap's rim sits >= ~4 mm BELOW the arch cusp line (measured 5.9/6.1 mm
     for the real caps; every tooth site <= 1.9 mm).
  3. The RIM-SLAB test — a cap presents a full-360° ring of surface at ONE height (its rim,
     within ±1 mm) with an empty core above the slab bottom (the screw recess is deep or
     unscannable). Teeth cannot close a ring in a single slab (cusp flanks slope through it),
     a dome's apex fills the core (measured caps 0.50-0.70 core/ring density vs flat gingiva
     1.9), and scan-boundary voids fail ring closure.

Output = candidate cap sites (center, evidence). Type/size identification and 6-DoF alignment
then reuse the template machinery (``register`` + ``resolve_sites``) per candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

from case_prep.domain.circle_fit import fit_circle_xy_or_kasa

# validated on the real Neodent healing arch (see docs/engagement + memory 2026-07-03)
_BAND_MM = 12.0            # candidate band depth below the cusp line (caps sit 4-8mm below)
_MIN_BELOW_CUSPS_MM = 2.75  # recalibrated on 5 labeled arches (2026-07-11): at 4.0 two real caps
#                              were MISSED (rims 3.1/3.8mm below partial-arch cusp lines); 2.75 proposes
#                              6/6 caps at +3 extra candidates total — recall first, confirm rejects. (real caps
#                            6.2-6.6; teeth <= 1.9; a posterior scan-edge artifact sat at 3.6)
_RING_R = (1.4, 2.8)       # mm; the rim annulus
_CORE_R = 0.8              # mm; the recess disc
_RIM_SLAB_MM = 1.0         # the ring must live within +-this of ONE height (the cap rim)
_RATIO_MAX = 0.9           # RECALL-oriented: the generator proposes, template
#                            registration disposes (detect_caps_clinical); caps 0.0-0.66 across
#                            two real arches, worst tissue artifacts 0.79-1.9
_SURROUND_R = (4.5, 7.5)   # mm; a real cap is SURROUNDED by scanned tissue — this outer
_SURROUND_MIN_BINS = 10    # annulus must cover >=10/12 bearings (scan-edge corners don't)
_RING_MIN_DENSITY = 10.0   # pts/mm^2 in the rim slab; the ring must be real surface
_RING_MAX_Z_STD = 0.6      # mm; a cap rim is LEVEL (real bevelled rims measure ~0.5) — a
#                            surface sloping clean through the slab is a flank, not a rim
_MIN_SEPARATION_MM = 8.0   # two implants are never closer (clinical >=3mm + radii)
_ARCH_BAND_MM = 7.0        # a cap site sits within this of the cusp-level arch trace (implants
#                            live in the tooth row; palate rugae rings otherwise false-positive)

# --- P3.1 density prior (healing-cap-curve-alignment-design.md §4.3) -----------------
#
# Triangle density is a real signal on 7/10 fleet sites (cap-local tessellation
# 1.34x–4.62x finer than tissue 6–12 mm away) but INVERTS on neodent-gm t4 (0.76x)
# and is exporter-specific. These constants copy the probe's geometry
# (eval/probe_cap_curves.py::local_density) into production — do not import from eval/.
#
# Informativeness gate: if p90/p10 of density ratios across all FPS candidates is below
# _DENSITY_INFORM_RATIO, the field is flat (uniform remesh / decimated export) and the
# prior is disabled. Measured threshold: 1.5–1.8 from the design spec; 1.5 is used here
# so borderline cases stay disabled rather than silently active.
#
# Per-candidate rule: even when the field is informative, a specific candidate whose own
# density ratio < 1.0 (cap coarser than tissue = inversion) does NOT use the prior.
# Rationale: adding extra seeds at high-density positions would seed AWAY from the cap,
# which is anti-recall. density_prior_used=False is the honest report for that site.
_DENSITY_CAP_MM = 3.0          # ball radius for the local "cap" density region
_DENSITY_TISSUE_LO_MM = 6.0    # inner radius of the tissue reference annulus
_DENSITY_TISSUE_HI_MM = 12.0   # outer radius
_DENSITY_INFORM_RATIO = 1.5    # p90/p10 of density ratios below this → flat, prior off
_DENSITY_FINEST_PCT = 5.0      # top-N% finest (smallest area) face centroids → extra seeds


@dataclass(frozen=True)
class CapSiteCandidate:
    """A healing-cap site found on the arch, with its discriminating evidence."""

    center: Tuple[float, float, float]  # world frame, at rim height over the void
    rim_below_cusps_mm: float
    void_ratio: float
    # P3.1 — additive field; False when faces=None, field is flat, or density inverted
    density_prior_used: bool = False


def _smallest_axis(v: np.ndarray) -> np.ndarray:
    c = v - v.mean(axis=0)
    _, vec = np.linalg.eigh(c.T @ c)
    return vec[:, 0] / np.linalg.norm(vec[:, 0])


def _band_spread(v: np.ndarray, axis: np.ndarray) -> float:
    """RMS in-plane radius of the top band along ``axis``. The crowns side's band is a wide
    U-strip tracing the arch (large spread); the palate side's band is one compact dome apex
    (small spread). NOTE: a bump-COUNT heuristic fails on real anatomy — cusps CONNECT along
    the tooth row into few components while the palate band fragments; spread is the robust
    signal (measured on the client's real upper jaw)."""
    h = v @ axis
    band = v[h > h.max() - 5.0]
    if len(band) < 50:
        return 0.0
    t0 = np.cross(axis, [0, 0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0, 0])
    t0 /= np.linalg.norm(t0)
    t1 = np.cross(axis, t0)
    xy = np.c_[band @ t0, band @ t1]
    return float(np.sqrt(np.mean(np.sum((xy - xy.mean(axis=0)) ** 2, axis=1))))


def crown_up_axis(vertices: np.ndarray, normals: Optional[np.ndarray] = None) -> np.ndarray:
    """The occlusal axis, oriented toward the CROWNS.

    Primary sign signal: the mesh's surface NORMALS — an intraoral scan is captured from the
    occlusal side, so its (outward) normals predominantly face the scanner, i.e. crowns-up.
    Fallback (bare point clouds): band spread — the crowns side's top band traces the whole
    arch (wide) while the palate side's is a compact dome apex. (The spread heuristic alone
    is not universal: a flat sheet has identical spread from both sides.)"""
    v = np.asarray(vertices, float)
    a = _smallest_axis(v)
    if normals is not None:
        mean_n = np.asarray(normals, float).mean(axis=0)
        proj = float(mean_n @ a)
        if abs(proj) > 0.05:
            return a if proj > 0 else -a
    return a if _band_spread(v, a) >= _band_spread(v, -a) else -a


def _density_ratio_at(cxy: np.ndarray, fc_xy: np.ndarray, face_areas: np.ndarray,
                       fc_tree: cKDTree) -> Optional[float]:
    """Local triangle density ratio (cap ball / tissue annulus) at position ``cxy`` (2-D).

    Mirrors the probe's ``local_density`` geometry (eval/probe_cap_curves.py) without
    importing from eval/. Returns None when either region is too sparse for a reading —
    the caller treats None as 'unknown', never as 0 or 1.
    Ratio < 1.0 signals inversion (cap coarser than tissue, e.g. neodent-gm t4)."""
    cap_idx = fc_tree.query_ball_point(cxy, _DENSITY_CAP_MM)
    outer_idx = fc_tree.query_ball_point(cxy, _DENSITY_TISSUE_HI_MM)
    tissue_idx = [i for i in outer_idx
                  if float(np.linalg.norm(fc_xy[i] - cxy)) >= _DENSITY_TISSUE_LO_MM]
    cap_area = float(face_areas[cap_idx].sum()) if cap_idx else 0.0
    tissue_area = float(face_areas[tissue_idx].sum()) if tissue_idx else 0.0
    if cap_area <= 0.0 or tissue_area <= 0.0 or not cap_idx or not tissue_idx:
        return None
    return (len(cap_idx) / cap_area) / (len(tissue_idx) / tissue_area)


def _density_setup(local_verts: np.ndarray, faces: np.ndarray
                   ) -> Optional[Tuple[np.ndarray, np.ndarray, cKDTree]]:
    """Prepare face-centroid 2-D array, face areas, and KD-tree for density queries.

    Returns None when the faces array is too small to be meaningful. Face indices
    are into ``local_verts`` (already in the crowns-up local frame)."""
    fa = np.asarray(faces, int)
    if fa.ndim != 2 or fa.shape[1] != 3 or len(fa) < 20:
        return None
    tris = local_verts[fa]                          # (N, 3, 3) in local frame
    fc_xy = tris.mean(axis=1)[:, :2]               # (N, 2) face centroids
    cross = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)    # (N,) face areas
    return fc_xy, areas, cKDTree(fc_xy)


def _density_field_is_informative(ratios: List[Optional[float]]) -> bool:
    """True when the density-ratio field across the FPS candidates is informative.

    Informativeness gate: p90 / p10 of valid ratios > _DENSITY_INFORM_RATIO. A flat
    field (uniform remesh / decimated export) has ratios clustering near 1.0 and fails
    this gate. Called once per ``find_cap_sites`` invocation — it is a per-file verdict."""
    valid = [r for r in ratios if r is not None and r > 0.0]
    if len(valid) < 3:
        return False
    p10, p90 = float(np.percentile(valid, 10)), float(np.percentile(valid, 90))
    return p10 > 0.0 and (p90 / p10) >= _DENSITY_INFORM_RATIO


def _interior_mask(xy: np.ndarray, cell: float = 2.0, margin_cells: int = 2) -> np.ndarray:
    """True for points away from the scan's in-plane BOUNDARY. Intraoral scans flare at their
    rim (vestibule/lip tissue where the scanner exits the mouth) and that flare can stand
    TALLER than the teeth — polluting any 'highest points = cusps' assumption (measured: it
    inflated the Zimmer cusp line by ~3mm and planted arch-trace points on the border).
    Occupancy-grid morphology: boundary cells touch an empty neighbour; interior points sit
    >= margin_cells (Chebyshev) from every boundary cell."""
    cells = np.floor(xy / cell).astype(int)
    occupied = set(map(tuple, cells))
    boundary = {c for c in occupied
                if any((c[0] + dx, c[1] + dy) not in occupied
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))}
    if not boundary:
        return np.ones(len(xy), dtype=bool)
    from scipy.spatial import cKDTree as _T
    btree = _T(np.array(sorted(boundary), dtype=float))
    d, _ = btree.query(cells.astype(float))
    return d > margin_cells


def find_cap_sites(vertices: np.ndarray, max_sites: int = 8,
                   axis: Optional[np.ndarray] = None,
                   normals: Optional[np.ndarray] = None,
                   faces: Optional[np.ndarray] = None) -> List[CapSiteCandidate]:
    """Find healing-cap sites on an arch scan via the validated stack (see module docstring).

    Pass the mesh's ``vertex_normals`` — they anchor the crowns-up orientation.

    ``faces`` (optional): integer face array (N, 3), indices into ``vertices``. When
    provided, the P3.1 density prior is evaluated:
    - Per-file informativeness gate: if p90/p10 of local density ratios across FPS
      candidates < _DENSITY_INFORM_RATIO (field is flat), the prior is disabled for
      ALL returned candidates (``density_prior_used=False``).
    - Per-site label: a candidate whose own density ratio < 1.0 (inversion — cap
      coarser than tissue, e.g. neodent-gm t4) also gets ``density_prior_used=False``
      even when the field is globally informative. The extra FPS seeds from the finest
      face centroids would seed AWAY from an inverted cap, so they are not added for
      that site.
    - Recall-first: extra seeds are ADDITIVE only. No existing candidate is removed."""
    v = np.asarray(vertices, float)
    a = crown_up_axis(v, normals) if axis is None else np.asarray(axis, float) / np.linalg.norm(axis)
    t0 = np.cross(a, [0, 0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0, 0])
    t0 /= np.linalg.norm(t0)
    frame = np.c_[t0, np.cross(a, t0), a]  # right-handed; local = (v - origin) @ frame
    origin = v.mean(axis=0)
    L = (v - origin) @ frame           # z = occlusal height
    h = L[:, 2]

    # --- density setup (P3.1) — prepare face data once for the full call ----------------
    _density_ctx: Optional[Tuple[np.ndarray, np.ndarray, cKDTree]] = None
    if faces is not None:
        _density_ctx = _density_setup(L, np.asarray(faces, int))

    # cusp line + arch trace come from INTERIOR points only — the scan's border flare
    # (vestibule tissue) can top the teeth and poison both (see _interior_mask)
    interior = _interior_mask(L[:, :2])
    h_int = h[interior]
    if not h_int.size:
        return []
    cusp_line = float(np.median(h_int[h_int > np.percentile(h_int, 90)]))
    band_idx = np.where(interior & (h > cusp_line - _BAND_MM) & (h < cusp_line + 3.0))[0]
    if len(band_idx) == 0:
        return []
    band = L[band_idx]

    # THE ARCH-BAND CONSTRAINT: implants live in the tooth row, not on the palate. The cusp-level
    # points trace the arch; a candidate must lie within _ARCH_BAND_MM (in-plane) of that trace —
    # this rejects palate rugae rings, which otherwise pass every local test.
    cusp_sel = interior & (h > cusp_line - 3.0) & (h < cusp_line + 3.0)
    cusp_xy = L[cusp_sel][:, :2]
    arch_tree = cKDTree(cusp_xy) if len(cusp_xy) else None

    xy_tree = cKDTree(L[:, :2])

    def rim_slab_ratio(center_xy):
        """The rim-slab test at one probe position: find the local rim height from the ring
        annulus, require a CLOSED (12/12 angular bins) ring within +-_RIM_SLAB_MM of it, and
        return core/ring density where the CORE counts everything at-or-above the slab bottom
        — so a dome's apex reads core-FULL (rejected) while a cap's recess (deep or unscanned)
        reads core-empty. Returns None when no closed ring exists here."""
        c = np.asarray(center_xy, float)
        near = L[xy_tree.query_ball_point(c, _RING_R[1])]
        rr = np.linalg.norm(near[:, :2] - c, axis=1)
        ring_all = near[rr >= _RING_R[0]]
        if len(ring_all) < 40:
            return None
        rim = float(np.percentile(ring_all[:, 2], 80))
        ring = ring_all[np.abs(ring_all[:, 2] - rim) < _RIM_SLAB_MM]
        a_ring = np.pi * (_RING_R[1] ** 2 - _RING_R[0] ** 2)
        if len(ring) / a_ring < _RING_MIN_DENSITY:
            return None
        ang = np.degrees(np.arctan2(ring[:, 1] - c[1], ring[:, 0] - c[0]))
        if len(set(((ang + 180) // 30).astype(int))) < 12:
            return None
        if float(np.std(ring[:, 2])) > _RING_MAX_Z_STD:
            return None  # sloping through the slab: a dome flank, not a level cap rim
        # a real cap is embedded in the arch: scanned tissue must surround it on (almost) all
        # bearings — a scan-edge corner can close the small rim ring but not this outer annulus
        surround = L[xy_tree.query_ball_point(c, _SURROUND_R[1])]
        sr = np.linalg.norm(surround[:, :2] - c, axis=1)
        outer = surround[(sr >= _SURROUND_R[0]) & (np.abs(surround[:, 2] - rim) < 6.0)]
        if len(outer):
            oang = np.degrees(np.arctan2(outer[:, 1] - c[1], outer[:, 0] - c[0]))
            if len(set(((oang + 180) // 30).astype(int))) < _SURROUND_MIN_BINS:
                return None
        else:
            return None
        core = near[(rr < _CORE_R) & (near[:, 2] > rim - _RIM_SLAB_MM)]
        return (len(core) / (np.pi * _CORE_R ** 2)) / (len(ring) / a_ring)

    # farthest-point candidates over the deep band
    start = int(np.argmax(band[:, 2]))
    chosen = [start]
    d = np.linalg.norm(band[:, :2] - band[start, :2], axis=1)
    # dense enough that every point of the band is within the ±3mm probe reach of some
    # candidate — a 2.5mm FPS stop with a small budget left a real cap unprobed on the
    # larger Zimmer band (nearest candidate 4.9mm from the ring)
    while len(chosen) < max_sites * 24 and d.max() > 2.5:
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.linalg.norm(band[:, :2] - band[i, :2], axis=1))

    # P3.1 density informativeness gate — computed on FPS candidates BEFORE ring search.
    # Outcome: is_informative (file-level) + density ratio per FPS candidate.
    # Extra seeds from finest face centroids are added when the field is informative.
    _density_ratios_at_fps: List[Optional[float]] = []
    _is_density_informative = False
    if _density_ctx is not None:
        fc_xy, face_areas, fc_tree = _density_ctx
        for i in chosen:
            _density_ratios_at_fps.append(
                _density_ratio_at(band[i, :2], fc_xy, face_areas, fc_tree))
        _is_density_informative = _density_field_is_informative(_density_ratios_at_fps)

        if _is_density_informative:
            # Additive extra FPS seeds: finest (smallest face area = highest density)
            # face centroids in the band, up to _DENSITY_FINEST_PCT percent of all faces.
            # Only face centroids that fall within the band height range qualify.
            band_h_lo = cusp_line - _BAND_MM
            band_h_hi = cusp_line + 3.0
            fc_h = fc_xy  # 2-D; check height via the 3-D face centroid would need L[fa]
            # Use the 2-D cusp-band spatial extent instead: any face centroid within
            # xy-distance of the band (generous — the ring is at most 3mm from centre)
            band_xy_min = band[:, :2].min(axis=0) - 3.0
            band_xy_max = band[:, :2].max(axis=0) + 3.0
            in_band_mask = (
                (fc_xy[:, 0] >= band_xy_min[0]) & (fc_xy[:, 0] <= band_xy_max[0]) &
                (fc_xy[:, 1] >= band_xy_min[1]) & (fc_xy[:, 1] <= band_xy_max[1])
            )
            band_face_idx = np.where(in_band_mask)[0]
            if len(band_face_idx) > 0:
                n_extra = max(1, int(len(band_face_idx) * _DENSITY_FINEST_PCT / 100.0))
                finest = np.argsort(face_areas[band_face_idx])[:n_extra]
                extra_xys = fc_xy[band_face_idx[finest]]
                # Convert extra face centroids to band-like indices via nearest
                # band-vertex lookup (so chosen stays index-based into band)
                if len(extra_xys):
                    band_tree_2d = cKDTree(band[:, :2])
                    for exy in extra_xys:
                        ei = int(band_tree_2d.query(exy)[1])
                        if ei not in chosen:
                            chosen.append(ei)

    found: List[Tuple[float, np.ndarray, float, float]] = []  # (void, xy, rim_z, below)
    for i in chosen:
        c0 = band[i, :2]
        # on the dental arch, not the palate interior
        if arch_tree is not None and arch_tree.query(c0)[0] > _ARCH_BAND_MM:
            continue
        # local rim height: top-75th percentile in the ring — the cap rim / bump top
        idx = xy_tree.query_ball_point(c0, _RING_R[1])
        near = L[idx]
        if len(near) < 30:
            continue
        rim_z = float(np.percentile(near[:, 2], 75))
        below = cusp_line - rim_z
        if below < _MIN_BELOW_CUSPS_MM:
            continue  # tooth-height structure
        # fine search for the cap's rim ring (±3mm at 0.25mm — the recess is ~1.5mm across
        # and FPS candidates land up to ~2.5mm off)
        best = None
        for dx in np.arange(-3.0, 3.01, 0.25):
            for dy in np.arange(-3.0, 3.01, 0.25):
                ratio = rim_slab_ratio(c0 + [dx, dy])
                if ratio is not None and (best is None or ratio < best[0]):
                    best = (ratio, c0 + [dx, dy])
        if best is None or best[0] > _RATIO_MAX:
            continue
        # THE Z BELONGS TO THE REPORTED XY (fleet sweep, 2026-08-01). rim_z above was
        # sampled around the COARSE candidate c0; the fine search just moved the xy up
        # to 3mm away (measured travel c0->cxy 1.46-3.35mm, median 2.12), and pairing
        # the refined xy with the stale z put the fleet's axial error at 0.559mm RMS —
        # on one arch the proposed centre floated +0.758mm ABOVE the surface, the one
        # marker that visibly hung in the air. Re-sample the ring at the point actually
        # being reported. The ADMISSION gate above deliberately keeps judging the c0
        # sample — this change moves no site in or out of the proposal set, it only
        # makes the reported point's two halves come from the same place. The sparse
        # fallback keeps the c0 sample rather than dropping the site, for the same
        # reason.
        # The band subset can be sparse at the refined xy (measured: one real-arch
        # proposal kept its stale z through the fallback and still sat +0.44mm off) —
        # widen the annulus once before giving up. Only if even that is sparse does
        # the c0 sample survive, and then only because a site is never dropped for
        # the crime of being hard to measure (recall-first).
        rim_near = None
        for ring_r in (_RING_R[1], _RING_R[1] * 1.5):
            ring_near = L[xy_tree.query_ball_point(best[1], ring_r)]
            if len(ring_near) >= 30:
                rim_near = ring_near
                break
        if rim_near is not None:
            rim_z = float(np.percentile(rim_near[:, 2], 75))
            below = cusp_line - rim_z
        found.append((best[0], best[1], rim_z, below))

    # dedupe by void quality, then back to world frame
    found.sort(key=lambda f: f[0])
    sites: List[CapSiteCandidate] = []
    kept_xy: List[np.ndarray] = []
    for void_ratio, cxy, rim_z, below in found:
        if any(np.linalg.norm(cxy - k) < _MIN_SEPARATION_MM for k in kept_xy):
            continue
        kept_xy.append(cxy)
        world = origin + frame @ np.array([cxy[0], cxy[1], rim_z])

        # P3.1 — per-site density_prior_used: informative field AND this site's own
        # ratio ≥ 1.0 (density co-varies with caps, not inverted). Computed at the
        # REFINED candidate xy (best[1]), not the coarse FPS seed.
        used = False
        if _is_density_informative and _density_ctx is not None:
            fc_xy_c, face_areas_c, fc_tree_c = _density_ctx
            site_ratio = _density_ratio_at(cxy, fc_xy_c, face_areas_c, fc_tree_c)
            used = site_ratio is not None and site_ratio >= 1.0

        sites.append(CapSiteCandidate(tuple(float(x) for x in world),
                                      float(below), float(void_ratio),
                                      density_prior_used=used))
        if len(sites) >= max_sites:
            break
    return sites


def measure_rim_diameter(local_pts: np.ndarray, xy_tree, center_local: np.ndarray,
                         search_r: float = 5.0, slab_mm: float = 0.8) -> Optional[float]:
    """Fit a circle (Taubin) to the cap's rim ring in the crowns-up LOCAL frame and return its
    diameter (mm) — the size-variant guide (classes sit ~0.8mm apart; scans read within
    ~0.4-0.8mm of a class, so the caller classifies WITH a margin and may refuse). None when
    the ring is too sparse to fit."""
    near = local_pts[xy_tree.query_ball_point(np.asarray(center_local[:2]), search_r)]
    rr = np.linalg.norm(near[:, :2] - center_local[:2], axis=1)
    ring_all = near[rr >= 1.0]
    if len(ring_all) < 60:
        return None
    rim = float(np.percentile(ring_all[:, 2], 80))
    ring = ring_all[np.abs(ring_all[:, 2] - rim) < slab_mm]
    if len(ring) < 40:
        return None
    fit = fit_circle_xy_or_kasa(ring[:, :2])
    if fit is None:
        return None
    return float(2.0 * fit[1])
