"""The ISLAND — the machine-segmented cap-only region (master plan §2.2, slice 6).

Pure domain geometry — no IO, no mesh types, no RNG draws. Given the scan's points in
the local crowns frame and an approximate seed (the doctor's mark: a LOCATOR, never a
measurement), segment the healing cap's own region: centre by recess evidence, rim
circle by closed-ring edge scan, extent by a 48-bin radial boundary march. The result
is an ``IslandReading`` that is CONVERGED-or-refused — a reading that fails any gate
reports ``converged=False`` with the gate's name, and carries no trusted centre.

Ported from the measured island probe (2026-07-22, 10 real sites): converged sites read
0.03–0.67 mm from the shipped rim centre; the two failure modes the gates capture are
cited at each constant below. SHADOW-ONLY today: the pipeline reports this next to the
shipped numbers and consumes it nowhere (auto_flow.SHADOW_ISLAND).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree

# A scan point counts as explained by the posed template within this distance (the same
# tolerance production coverage uses — auto_flow._COVERAGE_TOL_MM).
EXPLAINED_TOL_MM = 0.35

# --- CONVERGENCE GATES — every constant cites the measured failure it refuses -------
#
# The seed is the doctor's locator: fleet clicks measure <=0.6mm from the shipped rim
# centre, and the design margin for degraded seeds is 0.8mm. A machine centre further
# than this from its seed contradicts the locator — it found SOME ring-like structure,
# not the marked cap. Measured: cap7020's rim-slab evidence landscape has its minimum
# 1.3-1.5mm off the true centre (ratio 0.169 at the false lock vs 0.325 at truth; the
# machine centre landed 1.35-1.57mm from the seed and 1.54mm from the shipped centre).
# The strict/plane chooser was investigated and is NOT the defect: BOTH fits sat >1.2mm
# off (strict 1.54 / plane 1.24) because the centre evidence itself was displaced — no
# chooser recovers that; only this locator-consistency gate refuses it. Converged fleet
# max: 0.49mm from true clicks, 0.82mm from 0.8mm-degraded seeds.
MAX_CENTRE_FROM_SEED_MM = 1.2

# The human's rim radius (or the detector's measured rim) is an independent hint. The
# gate reads the SHORTFALL of the larger of the two extent instruments (Kasa rim radius,
# boundary-march island_r) below the hint: a genuine wrong-structure lock under-reads on
# BOTH (t7: 1.51/2.40mm against a 3.62mm hint, shortfall 1.22, alongside a 2.04mm centre
# error), while a true cap can under-read on ONE — the ring scan stops at an inner code
# step (cap6030 measured: Kasa 1.81 on a true 2.68 rim at grid phase zero, centre still
# 0.03mm true, island_r stable at 2.70 across all seed phases) and the march under-reads
# submerged caps (cap6020: island_r 1.65, Kasa 2.38 vs hint 2.78). Converged fleet max
# shortfall: 0.40 (cap6020).
MAX_RADIUS_VS_HINT_MM = 0.8

# Recess evidence quality: core/ring density ratio at the found centre (small = a real
# empty screw recess inside a closed ring). Measured: t7's best evidence anywhere in
# the search read 0.573 — a starved, badly-scanned cap; converged fleet max 0.472.
# The margin on the fail side is thin (0.02) — t7 is independently refused by the
# radius gate above; this gate is the honest name for weak evidence.
MAX_VOID_RATIO = 0.55

# The boundary march must close most of the compass: converged fleet reads 42-48 of 48
# bins; a starved cloud cannot populate the bins at all. This gate also arbitrates the
# march's runaway rule below: a submerged cap whose march loses the trail in most bins
# (cap6020: 28/48 after the start fix) is refused as open_boundary, never given a
# fabricated extent.
MIN_BINS_HIT = 32

# --- RADIUS INSTRUMENT (iteration 1 of the DR1 timebox, 2026-07-24) -----------------
#
# The single-phase Kasa was grid-phase-UNSTABLE: on cap6030 it read 1.81 from the
# curated seed but 2.64 from a 0.8mm-degraded seed (true rim 2.68, centre stable to
# 0.002mm) — the closed-run selection flips between an inner code-step ring and the
# true rim depending on how the 0.15mm r-grid lands. The shipped 1.81 destroyed the
# fleet's best site (seat rim->icp, codes lost). Measured on all 10 fleet sites
# (instrument probe, this iteration): the MEDIAN over these r-grid phases x small
# centre jitters reads cap6030 at -0.03 vs the shipped rim (was -0.87) and keeps every
# healthy site within 0.11; the max-min spread across the pool is itself the honest
# instability diagnostic (t7: 1.39 — wild; healthy sites: 0.03-0.35).
RADIUS_GRID_PHASES = (0.0, 0.03, 0.06, 0.09, 0.12)
RADIUS_CENTRE_JITTERS = ((0.0, 0.0), (0.04, 0.0), (-0.04, 0.0),
                         (0.0, 0.04), (0.0, -0.04))

# --- BOUNDARY-MARCH CONSTRUCTION (same iteration) ------------------------------------
#
# The march used to start at a fixed 1.2mm and accepted sulcus-dip lookalikes INSIDE
# the cap top (cap6020: an engraving/recess transition at 1.8mm on a 2.5mm rim —
# island_r 1.8, 75% of the cap's own points cropped). The island cannot end inside the
# rim circle, so the march now starts just inside the measured rim radius (0.45mm = 3
# grid cells of left context for the dip test at the rim edge). And a bin whose march
# then runs far PAST the rim lost the trail (cap6020 submerged: tissue laps flush with
# the rim, no crevice signature — 28/48 bins ran to 4.05 on a 2.49 rim): such bins
# report no boundary rather than a fabricated one, and the bins gate arbitrates.
MARCH_START_INSIDE_RIM_MM = 0.45
MARCH_RUNAWAY_BEYOND_RIM_MM = 1.2

# --- COVERAGE BAND (same iteration) ---------------------------------------------------
#
# The island's cap-coverage instrument (fraction of band points the posed template
# explains) used the full membership depth (2.0mm below the rim plane) and counted
# sulcus wall against the cap: healthy fleet sites read 0.62-0.72 — barely above the
# 0.60 convergence gate. Clipped at the march's own below-the-island threshold
# (-0.8mm, the sustained-drop definition), healthy sites read 0.77-0.84 while the
# refusals the gate exists for keep failing: t7 0.23, t20 0.54 (the oracle-measured
# codes-loss site stays refused). The gate value itself is unchanged.
COVERAGE_BAND_FLOOR_MM = -0.8


@dataclass(frozen=True)
class IslandReading:
    """One machine measurement of a cap's island. ``converged`` governs ALL trust:
    an unconverged reading's fields are evidence for debugging, never for use
    (master plan invariant: CONVERGED-or-absent, no partially-trusted islands)."""

    converged: bool
    reason: str                       # "ok", or the name of the gate that refused
    centre_xy: Optional[Tuple[float, float]] = None   # machine rim-circle centre (local)
    radius: Optional[float] = None                    # machine rim-circle radius, mm
    island_r: Optional[float] = None                  # island extent (median boundary), mm
    rim_z: Optional[float] = None                     # rim slab height (local z), mm
    plane: Optional[Tuple[float, float, float]] = None  # rim plane: z = ax + by + c
    n_boundary: int = 0               # bins whose march found a boundary
    bins_hit: int = 0                 # distinct angular bins with a boundary (of n_bins)
    boundary_spread_mm: Optional[float] = None  # median |boundary radius - median|
    void_ratio: Optional[float] = None          # recess evidence (core/ring density)
    centre_from_seed_mm: Optional[float] = None
    contamination_est: Optional[float] = None   # see segment_island docstring
    radius_spread_mm: Optional[float] = None    # max-min of the multi-phase radius pool


def _kasa(xy: np.ndarray) -> Tuple[np.ndarray, float]:
    A = np.c_[2.0 * xy, np.ones(len(xy))]
    sol, *_ = np.linalg.lstsq(A, (xy ** 2).sum(axis=1), rcond=None)
    c = sol[:2]
    return c, float(np.sqrt(max(sol[2] + c @ c, 1e-12)))


def _rim_slab_ratio(L: np.ndarray, xy_tree: cKDTree, c: np.ndarray) -> Optional[float]:
    """The cap evidence at ``c``: a CLOSED level ring within +-1mm of one height with an
    empty core (screw recess) above the slab bottom. Returns core/ring density ratio
    (small = cap) or None (no closed ring — tooth flanks and gingiva cannot close one)."""
    near = L[xy_tree.query_ball_point(np.asarray(c, float), 2.8)]
    if len(near) < 40:
        return None
    rr = np.linalg.norm(near[:, :2] - c, axis=1)
    ring_all = near[rr >= 1.4]
    if len(ring_all) < 40:
        return None
    rim = float(np.percentile(ring_all[:, 2], 80))
    ring = ring_all[np.abs(ring_all[:, 2] - rim) < 1.0]
    a_ring = np.pi * (2.8 ** 2 - 1.4 ** 2)
    if len(ring) / a_ring < 10.0:
        return None
    ang = np.degrees(np.arctan2(ring[:, 1] - c[1], ring[:, 0] - c[0]))
    if len(set(((ang + 180) // 30).astype(int))) < 12:
        return None
    if float(np.std(ring[:, 2])) > 0.6:
        return None
    core = near[(rr < 0.8) & (near[:, 2] > rim - 1.0)]
    return (len(core) / (np.pi * 0.8 ** 2)) / (len(ring) / a_ring)


def _ring_fit(L: np.ndarray, xy_tree: cKDTree, c0: np.ndarray, use_plane: bool,
              phase: float = 0.0):
    """Closed-ring EDGE scan about ``c0``: the cap's ring is CLOSED (>=10/12 bearings
    within +-0.4 of one height/plane) from the recess outward TO ITS RIM EDGE; closure
    breaks at the crevice / sulcus gap / tissue step. Kasa on the OUTER ring band only
    (a full-slab Kasa drags toward gingiva plateaus at rim height — measured 1.5mm
    jumps). ``phase`` offsets the r-grid start (the multi-phase radius instrument
    resamples the same anatomy at shifted grid alignments — see RADIUS_GRID_PHASES).
    Returns (centre, ring_r, r_edge, plane, rim_z) or None."""
    cur = np.asarray(c0, float).copy()
    out = None
    for _ in range(3):
        near = L[xy_tree.query_ball_point(cur, 5.2)]
        rr = np.linalg.norm(near[:, :2] - cur, axis=1)
        mid = near[(rr >= 0.9) & (rr <= 2.8)]
        if len(mid) < 60:
            break
        rz = float(np.percentile(mid[:, 2], 80))
        if use_plane:
            sl = near[(rr >= 0.9) & (rr <= 4.4) & (np.abs(near[:, 2] - rz) < 0.9)]
            if len(sl) < 40:
                break
            pl = None
            for _t in range(3):
                A = np.c_[sl[:, :2], np.ones(len(sl))]
                pl, *_ = np.linalg.lstsq(A, sl[:, 2], rcond=None)
                res = np.abs(sl[:, 2] - A @ pl)
                keep = res < max(0.4, 2.5 * float(np.median(res)))
                if keep.sum() < 30 or keep.all():
                    break
                sl = sl[keep]
        else:
            pl = np.array([0.0, 0.0, rz])
        h = near[:, 2] - (near[:, :2] @ pl[:2] + pl[2])
        ang = np.arctan2(near[:, 1] - cur[1], near[:, 0] - cur[0])
        r_grid = np.arange(1.1 + phase, 4.6, 0.15)
        closed = np.zeros(len(r_grid), bool)
        for i, r0 in enumerate(r_grid):
            m = (rr >= r0) & (rr < r0 + 0.3) & (np.abs(h) < 0.4)
            if m.sum() >= 8:
                closed[i] = len(set(((np.degrees(ang[m]) + 180) // 30
                                     ).astype(int))) >= 10
        if not closed.any():
            break
        # LONGEST contiguous closed run (gaps <=1 cell) — the dominant ring band
        runs = []
        i = 0
        while i < len(r_grid):
            if not closed[i]:
                i += 1
                continue
            j, gap, last = i, 0, i
            while j + 1 < len(r_grid) and gap <= 1:
                j += 1
                if closed[j]:
                    last, gap = j, 0
                else:
                    gap += 1
            runs.append((int(closed[i:last + 1].sum()), i, last))
            i = last + 1
        _, _i0, i1 = max(runs)
        r_edge = float(r_grid[i1] + 0.15)
        band = near[(rr >= r_edge - 0.55) & (rr <= r_edge + 0.15) & (np.abs(h) < 0.45)]
        if len(band) < 30:
            break
        c2, r2 = _kasa(band[:, :2])
        if np.linalg.norm(c2 - cur) > 1.2:
            break  # contamination jump — keep the previous result
        moved = float(np.linalg.norm(c2 - cur))
        cur = c2
        out = (c2, float(r2), r_edge, pl, rz)
        if moved < 0.05:
            break
    return out


def _multi_phase_radius(L: np.ndarray, xy_tree: cKDTree, c_void: np.ndarray,
                        use_plane: bool) -> Tuple[Optional[float], Optional[float]]:
    """The radius INSTRUMENT: median rim radius over RADIUS_GRID_PHASES x
    RADIUS_CENTRE_JITTERS re-fits from the recess-evidence centre. The single-phase
    Kasa is grid-phase-bistable on caps with an inner code-step ring (cap6030:
    1.81 vs 2.64 on a 0.002mm-stable centre — the shipped 1.81 lost the codes);
    the pooled median reads through the bistability (measured -0.03 vs the shipped
    rim on cap6030, <=0.11 on every healthy fleet site). Returns (median, spread)."""
    vals = []
    for ph in RADIUS_GRID_PHASES:
        for jx, jy in RADIUS_CENTRE_JITTERS:
            f = _ring_fit(L, xy_tree, c_void + [jx, jy], use_plane=use_plane,
                          phase=ph)
            if f is not None:
                vals.append(float(f[1]))
    if not vals:
        return None, None
    return float(np.median(vals)), float(np.max(vals) - np.min(vals))


def coverage_band(points: np.ndarray, reading: IslandReading) -> np.ndarray:
    """The cap-coverage GATE's band: points inside the island extent and no deeper
    than COVERAGE_BAND_FLOOR_MM below the rim plane — the region the machine asserts
    is cap top + rim edge. The old full-depth band counted sulcus wall against the
    cap (healthy fleet sites read 0.62-0.72, barely over the 0.60 gate); this band
    reads them 0.77-0.84 while t7 (0.23) and t20 (0.54, the measured codes-loss
    hazard) stay refused. Requires a CONVERGED reading — the gate instrument has no
    meaning on a reading whose extent was refused."""
    if not reading.converged:
        raise ValueError("coverage_band requires a converged IslandReading")
    pts = np.asarray(points, float)
    centre = np.asarray(reading.centre_xy, float)
    plane = np.asarray(reading.plane, float)
    inr = np.linalg.norm(pts[:, :2] - centre, axis=1) < float(reading.island_r) + 0.2
    h = pts[:, 2] - (pts[:, :2] @ plane[:2] + plane[2])
    return inr & (h > COVERAGE_BAND_FLOOR_MM)


def _geometric_member(points: np.ndarray, centre_xy: np.ndarray, island_r: float,
                      plane: np.ndarray) -> np.ndarray:
    """Geometric island membership: inside the boundary radius (small margin) and not
    deep below the rim plane. PRIVATE by design — geometry alone over-crops submerged
    caps (measured: 53-83% of template-explained cap points lost on cap6020/7020/7030),
    so the only mask this module exports is the union-safe one below."""
    inr = np.linalg.norm(points[:, :2] - centre_xy, axis=1) < island_r + 0.2
    h = points[:, 2] - (points[:, :2] @ plane[:2] + plane[2])
    return inr & (h > -2.0)


def union_safe_mask(points: np.ndarray, reading: IslandReading,
                    explained: np.ndarray) -> np.ndarray:
    """The island mask production may act on: geometric membership UNION every point the
    posed template explains (``explained``: boolean, caller-computed at EXPLAINED_TOL_MM).

    UNION-SAFE invariant: a template-explained point is NEVER classified non-island.
    The geometric boundary alone lost 53-83% of the cap's own points on the submerged
    caps (cap6020 0.83, cap7020 0.54, cap7030 0.53 measured on the probe fleet) — a
    mask that discards surface the template explains would starve the seat of exactly
    the evidence it needs. Requires a CONVERGED reading — no partially-trusted islands."""
    if not reading.converged:
        raise ValueError("union_safe_mask requires a converged IslandReading")
    explained = np.asarray(explained, bool)
    if explained.shape != (len(points),):
        raise ValueError("explained mask must be one bool per point")
    geo = _geometric_member(np.asarray(points, float),
                            np.asarray(reading.centre_xy, float),
                            float(reading.island_r), np.asarray(reading.plane, float))
    return geo | explained


def segment_island(points_local: np.ndarray, seed_xy: np.ndarray,
                   radius_hint: Optional[float] = None,
                   n_bins: int = 48) -> IslandReading:
    """Machine rim circle + island extent from an APPROXIMATE seed. Deterministic —
    no RNG draws (grid searches and least squares only).

    1. CENTRE by recess evidence: fine-search (+-2mm, 0.25mm grid, then 0.1mm local)
       for the min core/ring rim-slab ratio — the closed level ring + empty screw
       recess locks the centre. No mean-shift: the top-surface centroid drifts up
       neighbouring tooth flanks (measured on t4/t13).
    2. RIM CIRCLE: closed-ring edge scan, run BOTH strict (crowns-z level) and in a
       fitted rim plane — complementary failure modes (strict refuses on tilted seats,
       the plane can chase tissue trends; measured t4 vs t13). Centre is strict-first
       (its failure mode is refusing, not wandering); extent/plane prefer the plane fit.
       The rim RADIUS is the multi-phase median (RADIUS_GRID_PHASES) — the
       single-phase fit is grid-phase-bistable on inner-ring caps (cap6030).
    3. ISLAND EXTENT: per angular bin, march outward from just inside the measured
       rim (MARCH_START_INSIDE_RIM_MM — a fixed interior start accepted engraving-dip
       lookalikes on the cap top, the cap6020 over-crop); the island ends at the
       first sustained drop (cap proud), sulcus dip (scanned crevice), rise above the
       rim slab (flank on submerged caps), or data gap (unscannable sulcus). A bin
       whose boundary lands far past the rim (MARCH_RUNAWAY_BEYOND_RIM_MM) lost the
       trail and reports nothing. Median-filtered boundary radii.
    4. GATES (constants above): a reading that fails any is returned unconverged with
       the gate's name — never a silently-wrong centre.

    ``radius_hint`` (mm): the human's rim radius or the detector's measured rim —
    used ONLY to gate (radius consistency) and to size the contamination estimate's
    reference ROI; it never shapes the segmentation itself.

    ``contamination_est``: the fraction of the production click-anchored ball ROI
    (rebuilt here with the same geometry the pipeline crops) that this island
    classifies as NOT cap — the measured share of today's registration input that is
    tooth/gum by the machine's lights (converged fleet: 0.29-0.72). GEOMETRIC estimate:
    on submerged caps it overcounts (some of what it calls contamination is cap the
    template would explain) — the union-safe mask above, not this number, is what any
    future seat consumes."""
    L = np.asarray(points_local, float)
    seed = np.asarray(seed_xy, float)
    xy_tree = cKDTree(L[:, :2])

    best = None
    for dx in np.arange(-2.0, 2.01, 0.25):
        for dy in np.arange(-2.0, 2.01, 0.25):
            c = seed + [dx, dy]
            ratio = _rim_slab_ratio(L, xy_tree, c)
            if ratio is not None and (best is None or ratio < best[0]):
                best = (ratio, c)
    if best is None:
        return IslandReading(converged=False, reason="no_recess_evidence")
    # local refinement (0.1mm) — decouples the found centre from the seed's grid phase
    b0 = best[1].copy()
    for dx in np.arange(-0.3, 0.31, 0.1):
        for dy in np.arange(-0.3, 0.31, 0.1):
            c = b0 + [dx, dy]
            ratio = _rim_slab_ratio(L, xy_tree, c)
            if ratio is not None and ratio < best[0]:
                best = (ratio, c)
    ratio0, c_void = float(best[0]), best[1].copy()

    fit_strict = _ring_fit(L, xy_tree, c_void, use_plane=False)
    fit_plane = _ring_fit(L, xy_tree, c_void, use_plane=True)
    if fit_strict is None and fit_plane is None:
        return IslandReading(converged=False, reason="no_closed_ring",
                             void_ratio=ratio0)
    # STRICT-FIRST centre (see docstring); extent/plane prefer the plane fit
    chosen = fit_strict if fit_strict is not None else fit_plane
    cur, _ring_r, _r_edge, _pl, rim_z = chosen
    ext = fit_plane if fit_plane is not None else chosen
    plane = ext[3]
    # the rim radius is the multi-phase MEDIAN (see _multi_phase_radius) — the
    # single-phase fit is grid-phase-bistable on inner-ring caps (the cap6030 defect)
    rim_r, rim_r_spread = _multi_phase_radius(L, xy_tree, c_void,
                                              use_plane=fit_plane is not None)
    if rim_r is None:  # the phase-0 fit above succeeded, so the pool cannot be empty
        rim_r, rim_r_spread = float(ext[1]), 0.0

    # island extent: radial march per bin outward from JUST INSIDE THE MEASURED RIM
    # (the island cannot end inside the rim circle — the fixed 1.2mm start accepted
    # engraving-dip lookalikes on the cap top, the cap6020 over-crop), in plane height
    near = L[xy_tree.query_ball_point(cur, 6.5)]
    hn = near[:, 2] - (near[:, :2] @ plane[:2] + plane[2])
    rel = near[:, :2] - cur
    rr = np.linalg.norm(rel, axis=1)
    th = np.arctan2(rel[:, 1], rel[:, 0])
    dr = 0.15
    r_grid = np.arange(0.3, 6.5, dr)
    start_r = max(1.2, rim_r - MARCH_START_INSIDE_RIM_MM)
    start_i = max(6, int(np.ceil((start_r - 0.3) / dr)))
    runaway_r = rim_r + MARCH_RUNAWAY_BEYOND_RIM_MM
    b_radii = []
    for b in range(n_bins):
        t0 = -np.pi + b * 2 * np.pi / n_bins
        dth = np.abs((th - (t0 + np.pi / n_bins) + np.pi) % (2 * np.pi) - np.pi)
        sel = dth < 2 * np.pi / n_bins
        if sel.sum() < 12:
            continue
        wr = rr[sel]
        wh = hn[sel]
        prof = np.full(len(r_grid), np.nan)
        for i, r0 in enumerate(r_grid):
            m = (wr >= r0) & (wr < r0 + dr)
            if m.any():
                prof[i] = float(wh[m].max())
        boundary_i = None
        for i in range(start_i, len(r_grid)):
            if np.isnan(prof[i]):
                j = i
                while j < len(r_grid) and np.isnan(prof[j]):
                    j += 1
                if (j - i) * dr >= 0.5:  # DATA GAP (unscannable sulcus)
                    boundary_i = i - 1
                    break
                continue
            if prof[i] < -0.8:  # SUSTAINED DROP below the rim plane (cap proud)
                nxt = prof[i:i + 4]
                nxt = nxt[~np.isnan(nxt)]
                if len(nxt) == 0 or (nxt < -0.65).all():
                    boundary_i = i - 1
                    break
            if prof[i] > 0.8:  # RISE above the rim plane: tooth/gingiva flank
                nxt = prof[i:i + 3]
                nxt = nxt[~np.isnan(nxt)]
                if (nxt > 0.65).all():
                    boundary_i = i - 1
                    break
            # SULCUS DIP: local min vs the cap side, with a rise after
            lo = max(start_i, i - 7)
            wl = prof[lo:i]
            wl = wl[~np.isnan(wl)]
            wr_ = prof[i + 1:i + 8]
            wr_ = wr_[~np.isnan(wr_)]
            if (len(wl) >= 2 and len(wr_) >= 1 and prof[i] < wl.max() - 0.18
                    and (wr_.max() if len(wr_) else -1e9) > prof[i] + 0.15
                    and r_grid[i] > 1.2):
                boundary_i = i
                break
        if (boundary_i is not None and boundary_i >= start_i
                and r_grid[boundary_i] <= runaway_r):
            # a boundary far past the measured rim is a lost trail (submerged caps:
            # tissue laps flush with the rim), not a reading — the bin reports nothing
            b_radii.append((b, r_grid[boundary_i]))
    if len(b_radii) < 8:
        island_r = rim_r + 0.5
        boundary_spread = None
    else:
        radii = np.array([r for _, r in b_radii])
        med = float(np.median(radii))
        keep = np.abs(radii - med) < max(0.9, 0.3 * med)
        island_r = float(np.median(radii[keep])) if keep.any() else med
        boundary_spread = float(np.median(np.abs(radii - med)))
    bins_hit = len(set(b for b, _ in b_radii))
    d_seed = float(np.linalg.norm(cur - seed))

    # contamination estimate over the production-style ball ROI (same geometry as the
    # pipeline's auto-brush crop: ball at rim height, radius min(hint+1.2, 5.4))
    contamination = None
    roi_r = float(radius_hint) if radius_hint else 2.6
    d = np.linalg.norm(L[:, :2] - seed, axis=1)
    near_seed = L[d < roi_r]
    if len(near_seed) >= 40:
        ball_c = np.array([seed[0], seed[1],
                           float(np.percentile(near_seed[:, 2], 80))])
        roi = L[np.linalg.norm(L - ball_c, axis=1) < min(roi_r + 1.2, 5.4)]
        if len(roi) >= 60:
            member = _geometric_member(roi, cur, island_r, plane)
            contamination = float(1.0 - member.mean())

    def refuse(reason: str) -> IslandReading:
        return IslandReading(
            converged=False, reason=reason,
            centre_xy=(float(cur[0]), float(cur[1])), radius=rim_r,
            island_r=island_r, rim_z=float(rim_z),
            plane=tuple(float(x) for x in plane),
            n_boundary=len(b_radii), bins_hit=bins_hit,
            boundary_spread_mm=boundary_spread, void_ratio=ratio0,
            centre_from_seed_mm=d_seed, contamination_est=contamination,
            radius_spread_mm=rim_r_spread)

    # evidence QUALITY first (the most honest diagnosis on starved/flat geometry —
    # a featureless plane reads ratio ~1 and should say so, not blame the seed),
    # then locator/hint CONSISTENCY, then boundary closure
    if ratio0 > MAX_VOID_RATIO:
        return refuse("weak_recess_evidence")
    if d_seed > MAX_CENTRE_FROM_SEED_MM:
        return refuse("centre_seed_disagreement")
    if (radius_hint is not None
            and float(radius_hint) - max(rim_r, island_r) > MAX_RADIUS_VS_HINT_MM):
        return refuse("radius_hint_disagreement")
    if bins_hit < MIN_BINS_HIT:
        return refuse("open_boundary")
    return IslandReading(
        converged=True, reason="ok",
        centre_xy=(float(cur[0]), float(cur[1])), radius=rim_r,
        island_r=island_r, rim_z=float(rim_z),
        plane=tuple(float(x) for x in plane),
        n_boundary=len(b_radii), bins_hit=bins_hit,
        boundary_spread_mm=boundary_spread, void_ratio=ratio0,
        centre_from_seed_mm=d_seed, contamination_est=contamination,
        radius_spread_mm=rim_r_spread)
