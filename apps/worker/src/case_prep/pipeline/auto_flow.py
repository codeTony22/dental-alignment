"""The seamless clinical case flow: PROPOSE -> (human) CONFIRM -> align -> measure -> package.

Detection on real arches runs as auto-propose + human-confirm — the measured decision
(2026-07-03): no fully-automatic arbiter separates low-profile healing caps from tissue
artifacts at the current data volume (2 arches), so the generator's ranked proposals go to an
operator who confirms each site in one click. Everything downstream of confirmation is
automatic: best-template alignment (which also identifies the size variant), interproximal
site measurement, advisory gating (real cases never auto-pass), and the industry-grounded
output package. Full-auto confirmation is a data-gated improvement, not a blocker.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.cap_detection import crown_up_axis, find_cap_sites, measure_rim_diameter
from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.output_package import (MeshFacts, SitePackageSpec,
                                                emit_case_package, facts_of,
                                                register_package_files)
from case_prep.adapters.rng import PipelineRng, sample_surface
from case_prep.adapters.site_analysis import measure_site
from case_prep.domain.cap_catalog import CapSpec, classify_diameter, variant_flags
from case_prep.domain.channel import channel_from_boundary_loops
from case_prep.domain.circle_fit import circle_centre_xy, fit_circle_xy, fit_circle_xy_or_kasa
from case_prep.domain.guidance import advisory_guidance
from case_prep.domain.island import segment_island
from case_prep.domain.pose_confidence import confidence_grade, pose_spread
from case_prep.domain.poses import Retention
from case_prep.pipeline.deliverables import (arch_with_parts_fused,
                                              cap_imprint_holes,
                                              cap_imprint_parts,
                                              open_arch_with_through_holes,
                                              remove_cap_region)
from case_prep.pipeline.isolation import isolate_scanned_cap
from case_prep.pipeline.final_product import (DEFAULT_GINGIVAL_OFFSET_MM,
                                              DEFAULT_SCREW_RADIUS_MM,
                                              ReliefClamp,
                                              build_final_product,
                                              measure_delivered_channel,
                                              resolve_gingival_offset)
from case_prep.pipeline.package_viewer import write_view_html

_COVERAGE_TOL_MM = 0.35  # scan point counts as explained if this close to the fitted template

# SHADOW ISLAND (master plan slice 6, walking skeleton): report the machine-segmented
# island next to every shipped pose. REPORTING ONLY — computed after all winner poses
# are final, consumed by nothing; the shipped pose is byte-identical with this on or
# off (the zero-pose-movement contract, tests/test_island.py). The flag exists so that
# contract stays provable and the shadow is revertible without a code revert.
SHADOW_ISLAND = True


@dataclass(frozen=True)
class ProposedSite:
    """A candidate healing-cap site for the operator to confirm (ranked, with evidence)."""

    center: Tuple[float, float, float]
    # "void" is the SCREW RECESS seen as an absence of scan in the cap's core (see
    # _screw_recess_centre). The instruments were renamed to say recess; this WIRE KEY
    # stays as shipped because the web renders it — rename both sides together.
    void_ratio: float
    rim_below_cusps_mm: float


@dataclass(frozen=True)
class ConfirmedSite:
    """An operator-confirmed site: the tooth number, the (possibly adjusted) location, and —
    when the doctor declared it — the expected size variant (e.g. "6030"). A declaration is
    AUTHORITATIVE for billing; the system still measures and FLAGS any disagreement (a
    smaller part constructed into a bigger space must never pass silently).

    ``marked_points`` is the RealGUIDE-style BRUSH input: the operator paints the cap area on
    the 3D scan and the painted patch becomes the registration ROI directly — the strongest
    human-in-the-loop signal (a region, not a click)."""

    tooth: int
    center: Tuple[float, float, float]
    declared_variant: Optional[str] = None
    marked_points: Optional[List[List[float]]] = None
    # precise marks (RealGUIDE registration-point style): the cap CENTER and a point on
    # the WIDEST rim edge — together they hand the rim seat its center and radius from
    # the human directly, no estimator trusted
    center_mark: Optional[List[float]] = None
    rim_mark: Optional[List[float]] = None
    # MULTI-POINT rim (client spec 2026-07-14): several clicks around the cap's visible
    # border; the rim circle (centre AND radius) is least-squares fit through them, so
    # no single imprecise click can corrupt the measurement. With >=3 points this
    # OVERRIDES centre/rim single marks for the seat's circle — the centre click is
    # then only a locator.
    rim_points: Optional[List[List[float]]] = None


def propose_sites(scan_points: np.ndarray,
                  normals: Optional[np.ndarray] = None,
                  max_sites: int = 8) -> List[ProposedSite]:
    """Ranked healing-cap proposals for operator confirmation (best evidence first)."""
    candidates = find_cap_sites(np.asarray(scan_points, float),
                                max_sites=max_sites, normals=normals)
    ranked = sorted(candidates, key=lambda c: c.void_ratio)
    return [ProposedSite(c.center, c.void_ratio, c.rim_below_cusps_mm) for c in ranked]


def _crowns_frame(pts: np.ndarray, normals: Optional[np.ndarray]):
    a = crown_up_axis(pts, normals)
    t0 = np.cross(a, [0.0, 0.0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0.0, 0.0])
    t0 /= np.linalg.norm(t0)
    # RIGHT-HANDED (det=+1): [t0, a×t0, a] — a left-handed frame makes the composed
    # pose a REFLECTION and mirrors the deliverable's pose_matrix (review M1)
    return np.c_[t0, np.cross(a, t0), a], pts.mean(axis=0), a  # frame(cols), origin, axis


def _template_radius(mesh: trimesh.Trimesh) -> float:
    v = np.asarray(mesh.vertices, float)
    return float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 95))


def _library_is_squat(library: CapLibrary) -> bool:
    """Healing caps seat rim-first; tall scan bodies register by ICP. Delegates to the
    library itself (CapLibrary.rim_seatable): loaded cap CATALOGS are rim-seatable by
    construction, stand-ins decide by the historical wider-than-tall geometry test.
    (An aspect heuristic here mis-fired the moment the canonicalization fix gave the
    narrow-tall neodent caps their true axes — see rim_seatable's doc.)"""
    return library.rim_seatable


def _rim_seat(patch: np.ndarray, seed_xy: np.ndarray, rim_r: float,
              template: trimesh.Trimesh,
              min_arc_bins: int = 9,
              rng: Optional[PipelineRng] = None
              ) -> Optional[Tuple[np.ndarray, float]]:
    """Seat a cap RIM-FIRST, the way a CAD tech does: the visible rim band fit as a 3D
    circle gives the CENTER and (plane normal) the AXIS — the cap's physical tilt; the
    remaining freedom is a 1-D slide along that axis, solved by direct search. No 6-DoF
    ICP is left to wander: trimmed ICP repeatedly chose tilted/slid basins that score
    well by explaining ridge walls (measured on 3 of 6 real sites, fits up to 47 deg off
    a 15-deg rim plane). Clocking is irrelevant for a revolute part.

    Returns (pose_matrix in the crowns frame, trimmed seat residual) or None when the
    visible rim arc is too partial to trust (< 9 of 12 angular bins)."""
    # NOTE (2026-07-14): the seat NEEDS a self-consistent centre+radius pair — five
    # variations of in-seat/post-seat "self-correction" were tried against corrupted
    # pairs (re-clicked centre + stale rim) and every one either broke the calibrated
    # blind-identification contract or degraded curated seats. The pair's integrity
    # is owned at the SOURCE: the UI translates the rim mark with a re-placed centre
    # so the doctor's measured radius survives (see the re-click guard test).
    d = np.linalg.norm(patch[:, :2] - seed_xy, axis=1)
    band = patch[np.abs(d - rim_r) < 0.5]
    if len(band) < 40:
        return None
    # INLIER-REFINED plane fit: at rim radius the band can also catch pocket/tooth wall
    # points (measured: they dragged the zimmer rim plane to 41 deg). Wall points do not
    # lie in the rim's plane — two fit-and-prune rounds drop them; a genuinely tilted
    # rim's own points survive because they define the plane.
    c0 = band.mean(axis=0)
    n = None
    for _ in range(3):
        _, _, vt = np.linalg.svd(band - c0, full_matrices=False)
        n = vt[2] / np.linalg.norm(vt[2])
        keep_band = np.abs((band - c0) @ n) < 0.6
        if keep_band.all() or keep_band.sum() < 40:
            break
        band = band[keep_band]
        c0 = band.mean(axis=0)
    if len(band) < 40:
        return None
    ang = np.arctan2(band[:, 1] - seed_xy[1], band[:, 0] - seed_xy[0])
    # a human-vouched radius relaxes the arc requirement (min_arc_bins=6): the centre
    # and radius are ground truth, the band only has to pin the plane
    arc_bins = len(set(((ang + np.pi) // (np.pi / 6.0)).astype(int)))
    if arc_bins < min_arc_bins:
        return None
    if n[2] < 0:
        n = -n
    # GATE 1: the rim plane's normal is the cap's axis — outside the plausible seating
    # cone it is not a cap rim we should trust (fall through to bounded ICP)
    if n[2] < np.cos(np.radians(45.0)):
        return None
    # rim circle center: Taubin fit in the rim plane
    t0 = np.cross(n, [0.0, 0.0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0.0, 0.0])
    t0 /= np.linalg.norm(t0)
    t1 = np.cross(n, t0)
    uv = (band - c0) @ np.c_[t0, t1]
    fit = fit_circle_xy_or_kasa(uv)
    if fit is None:
        return None
    uc, fitted_rim_r = fit
    center = c0 + uc[0] * t0 + uc[1] * t1

    z = np.array([0.0, 0.0, 1.0])
    pivot = np.cross(z, n)
    if np.linalg.norm(pivot) < 1e-9:
        R = np.eye(3)
    else:
        angle = float(np.arccos(np.clip(z @ n, -1.0, 1.0)))
        R = trimesh.transformations.rotation_matrix(angle, pivot)[:3, :3]
    sampled = sample_surface(rng, template, 1200)
    S = sampled @ R.T
    # the template's OWN widest rim ring, for the SYMMETRIC score term: an OVERSIZED
    # template envelops the patch (tiny patch->template residual) but its rim hangs over
    # gingiva in air — measured on labeled arches: a Ø8 cap outscored the true Ø7 until
    # this term existed (blind identification 1/4)
    tr = np.linalg.norm(np.asarray(sampled, float)[:, :2], axis=1)
    ring_sel = tr > (tr.max() - 0.4)
    ring_S = S[ring_sel]
    # CALIBRATED on the client's labeled arches (2026-07-13): score = untrimmed
    # patch->template + 2 x (template-above-gingiva -> patch). The second term makes any
    # WRONG-SIZE template pay for the surface it claims but the scan does not show
    # (oversize: rim beyond the patch; undersize: the patch's rim unexplained). Radius
    # terms failed: these caps FLARE at the emergence, max radius != rim radius. Result
    # on ground truth: diameter class 4/4; heights tie by physics on submerged caps and
    # route to the doctor via the too-close rule.
    patch_tree = cKDTree(patch)
    # ONE tree, 61 translated queries: ||patch-(S+c+nt)|| == ||(patch-c-nt)-S|| — the
    # depth search was rebuilding a KD-tree per step (per site x spec: ~2200 builds/case)
    # NOTE (2026-07-14): choosing t by the combined score (seat + 2*t2p) was tried for
    # re-click stability and REGRESSED the calibrated blind/all-sites contracts — the
    # depth stays chosen by the pure seat term the calibration was measured with.
    tree = cKDTree(S)
    base = patch - center
    best = None
    for t in np.linspace(-3.0, 3.0, 61):
        dd = tree.query(base - n * t)[0]
        seat_resid = float(dd.mean())
        if best is None or seat_resid < best[1]:
            best = (t, seat_resid)
    above = S + center + n * best[0]
    above = above[((above - center) @ n) > -0.4]  # the part that must be visible
    t2p = (float(patch_tree.query(above)[0].mean()) if len(above) else 9.9)
    best = (best[0], best[1], best[1] + 2.0 * t2p)
    # GATE 2: the depth search railing at its boundary means the true seat is outside
    # the searched range — refuse rather than clamp (a measured 4.2mm slide once shipped)
    if abs(best[0]) >= 2.9:
        return None
    # GATE 3: seat residual beyond calibration (good real seats read 0.3-0.7mm trimmed)
    if best[1] > 1.0:
        return None
    # NOTE (2026-07-14): clocking is NOT applied here — re-scoring clocked candidates
    # let wrong-size templates rotate into flattering poses and flipped the blind
    # diameter class (cap7030 60 vs 70). Ranking stays exactly as calibrated; the
    # WINNER's pose is clocked afterwards in run_auto_case.
    m = np.eye(4)
    m[:3, :3] = R
    m[:3, 3] = center + n * best[0]
    # returned residual = the SYMMETRIC score (seat + rim-on-scan): ranks size variants
    # honestly; the refusal gates above stay on the pure seat component. arc_bins
    # reports how much of the rim ring was actually visible (12 = full circle) — a
    # partial arc under-constrains the seat and the gate says so.
    return m, best[2], arc_bins


def _fit_circle_xy(pts_xy: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Least-squares (Taubin) circle through >=3 xy points — the multi-point rim
    measurement: each click is ±1mm but the FIT averages the error out. Taubin
    replaces algebraic Kasa because Kasa shrinks partial arcs (the fleet's measured
    case). Returns (centre_xy, radius) or None when the points cannot support a
    circle (collinear, all on one side, or a fit outside any cap's physical size)."""
    P = np.asarray(pts_xy, float)
    if len(P) < 3:
        return None
    fit = fit_circle_xy(P)
    if fit is None:
        return None
    centre, r = fit
    if not (1.0 <= r <= 8.0):  # outside any healing cap's physical rim radius
        return None
    # the clicks must actually surround the cap: with everything on one side the fit
    # is a guess, not a measurement (require >= a third of the circle covered)
    ang = np.arctan2(P[:, 1] - centre[1], P[:, 0] - centre[0])
    if len(set(((ang + np.pi) // (np.pi / 6.0)).astype(int))) < 3:
        return None
    return centre, r


def _fit_circle_plane(Q: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    """Ungated plane + in-plane Taubin circle through points — the core _fit_circle_3d
    builds on (also used to score candidate subsets during outlier arbitration)."""
    Q = np.asarray(Q, float)
    if len(Q) < 3:
        return None
    c0 = Q.mean(axis=0)
    _, _, vt = np.linalg.svd(Q - c0, full_matrices=False)
    n = vt[2] / np.linalg.norm(vt[2])
    if n[2] < 0:
        n = -n
    t0 = np.cross(n, [0.0, 0.0, 1.0])
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.array([1.0, 0.0, 0.0])
    t0 /= np.linalg.norm(t0)
    t1 = np.cross(n, t0)
    uv = (Q - c0) @ np.c_[t0, t1]
    fit = fit_circle_xy(uv)
    if fit is None:
        return None
    uc, r = fit
    return c0 + uc[0] * t0 + uc[1] * t1, n, float(r)


def _border_click_disagreement(P: np.ndarray) -> Optional[float]:
    """Max leave-one-out plane distance over the border clicks (n >= 4; three clicks
    always define their plane exactly, so there is nothing to measure below four).
    THE outlier signal for a small click set: an LSQ plane over all n SPLITS a single
    bad click's error across every point (the client's 0.89mm-out redo click read only
    0.21 whole-fit rms and slipped under that gate), while each click's distance from
    the OTHERS' plane reads the disagreement directly (~0.3 on good real gestures).
    Hypothesis-trigger + reporting only — the seat itself still honors the doctor's
    clicks; rigid-transform invariant, so callers may pass world or local coords."""
    P = np.asarray(P, float)
    if len(P) < 4:
        return None
    worst = 0.0
    for i in range(len(P)):
        Q = np.delete(P, i, axis=0)
        cq = Q.mean(axis=0)
        _, _, vt = np.linalg.svd(Q - cq, full_matrices=False)
        worst = max(worst, float(abs((P[i] - cq) @ vt[2])))
    return worst


def _fit_circle_3d(P: np.ndarray,
                   scan_tree=None) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    """3D circle through the doctor's border clicks: best-fit PLANE (its normal is the
    cap's axis and its height the visible depth) + in-plane Kasa circle (centre and
    width). The border points define the visible ring COMPLETELY — this is what lets
    the seat pin the template to it. With >=4 points an OUTLIER click is detected and
    dropped (leave-one-out: a click that landed past the rim edge on the slope tilts
    the whole plane to pass through it — measured on a client run: one point 1.3mm
    low tilted the pinned seat 13 degrees; a genuinely tilted rim's points are
    COPLANAR and survive the check). Returns (centre, normal, radius) or None when
    the points cannot support a circle (too few, one-sided, implausibly tilted, or a
    radius outside any cap's physical size)."""
    P = np.asarray(P, float)
    if len(P) < 3:
        return None
    if len(P) >= 4 and scan_tree is not None:
        c0 = P.mean(axis=0)
        _, _, vt = np.linalg.svd(P - c0, full_matrices=False)
        full_rms = float(np.sqrt(np.mean(((P - c0) @ vt[2]) ** 2)))
        disagreement = _border_click_disagreement(P)
        # Two triggers, one machinery: whole-fit rms catches generally scattered
        # clicks, but at n=4 the LSQ plane SPLITS a single outlier's error across all
        # points — the client's 0.89mm-out redo click read rms 0.206 and shipped a
        # 12-degree tilt with no alternate ever generated. The leave-one-out
        # disagreement reads that click directly, so it must also open the gate; the
        # alternate still has to win the scan-hug ranking here and the pin contract +
        # calibrated seat score downstream, exactly as before.
        if full_rms > 0.25 or (disagreement is not None and disagreement > 0.8):
            # the points do not sit in ONE plane. Geometry alone cannot decide which
            # click is the outlier at n=4 ("one low point" and "three points on a
            # tilted rim" are symmetric hypotheses) — THE SCAN decides: the true rim
            # circle lies ON scan surface all the way around; a wrong circle dives
            # into gum or air. Score each candidate circle by how well it hugs the
            # scan and keep the best subset when it clearly wins.
            def _circle_on_scan(Q):
                fit = _fit_circle_plane(Q)
                if fit is None:
                    return None, 9.9
                c, n_, r_ = fit
                u = np.cross(n_, [0.0, 0.0, 1.0])
                if np.linalg.norm(u) < 1e-6:
                    u = np.array([1.0, 0.0, 0.0])
                u /= np.linalg.norm(u)
                w = np.cross(n_, u)
                th = np.linspace(0, 2 * np.pi, 24, endpoint=False)
                ring = c + r_ * (np.outer(np.cos(th), u) + np.outer(np.sin(th), w))
                return fit, float(scan_tree.query(ring)[0].mean())

            _, full_score = _circle_on_scan(P)
            best_Q, best_score, best_excl = None, full_score, 0.0
            for i in range(len(P)):
                Q = np.delete(P, i, axis=0)
                fit_q, sc = _circle_on_scan(Q)
                if sc < best_score and fit_q is not None:
                    excl_d = float(abs((P[i] - Q.mean(axis=0)) @ fit_q[1]))
                    best_Q, best_score, best_excl = Q, sc, excl_d
            # local geometry CANNOT decide reliably which hypothesis is true ("one
            # click slipped off the edge" vs "the rim is genuinely tilted/uneven" —
            # measured: every local gate combination broke one real case or the
            # other). When a plausible outlier exists, return BOTH circles and let
            # the calibrated PINNED SEAT decide — same variant either way, so the
            # identification ranking is untouched.
            if best_Q is not None and best_excl > 0.8:
                alternate = best_Q
            else:
                alternate = None
        else:
            alternate = None
    else:
        alternate = None
    def _gated(Q):
        fit = _fit_circle_plane(Q)
        if fit is None:
            return None
        centre, n, r = fit
        if n[2] < np.cos(np.radians(45.0)):  # outside the plausible seating cone
            return None
        if not (1.0 <= r <= 8.0):
            return None
        t0 = np.cross(n, [0.0, 0.0, 1.0])
        if np.linalg.norm(t0) < 1e-6:
            t0 = np.array([1.0, 0.0, 0.0])
        t0 /= np.linalg.norm(t0)
        t1 = np.cross(n, t0)
        uv = (Q - centre) @ np.c_[t0, t1]
        ang = np.arctan2(uv[:, 1], uv[:, 0])
        if len(set(((ang + np.pi) // (np.pi / 6.0)).astype(int))) < 3:
            return None  # clicks bunched on one side: a guess, not a measurement
        return centre, n, r

    candidates = []
    primary = _gated(P)
    if primary is not None:
        candidates.append(primary)
    if alternate is not None:
        alt = _gated(alternate)
        if alt is not None:
            candidates.append(alt)
    return candidates or None


def _pinned_rim_seat(patch: np.ndarray, circle: Tuple[np.ndarray, np.ndarray, float],
                     template: trimesh.Trimesh,
                     rng: Optional[PipelineRng] = None
                     ) -> Optional[Tuple[np.ndarray, float]]:
    """Seat PINNED to the doctor's border circle (client spec 2026-07-14: 'width needs
    to match and depth needs to match'): find the axial position where the template's
    own silhouette has the clicked radius, and place that ring exactly ON the clicked
    circle — centre, axis, width and depth all come from the human's points, nothing
    is left for a residual search to drift. Only the VARIANT ranking remains, scored
    with the same calibrated formula as the free rim seat. Returns (pose, score) or
    None when the template never reaches the clicked width."""
    centre, n, r_fit = circle
    v = np.asarray(template.vertices, float)
    rad = np.linalg.norm(v[:, :2], axis=1)
    z = v[:, 2]
    # the template's silhouette r(z) in 0.25mm bins, top-down: the border the doctor
    # sees is the HIGHEST place the part is that wide (caps flare at the emergence)
    order = np.argsort(z)
    zs, rs = z[order], rad[order]
    bins = np.arange(zs[0], zs[-1] + 0.25, 0.25)
    idx = np.digitize(zs, bins)
    z_t = None
    for b in range(idx.max(), 0, -1):
        sel = idx == b
        if sel.any() and float(rs[sel].max()) >= r_fit - 0.15:
            z_t = float(zs[sel].mean())
            break
    if z_t is None:
        return None  # the part never reaches the clicked width — wrong variant
    zaxis = np.array([0.0, 0.0, 1.0])
    pivot = np.cross(zaxis, n)
    if np.linalg.norm(pivot) < 1e-9:
        R = np.eye(3)
    else:
        angle = float(np.arccos(np.clip(zaxis @ n, -1.0, 1.0)))
        R = trimesh.transformations.rotation_matrix(angle, pivot)[:3, :3]
    T = centre - R @ np.array([0.0, 0.0, z_t])
    # coded-face clocking at the pinned pose (same asymmetry search as the free seat)
    R = _best_clocking(cKDTree(patch), template, R, T)
    T = centre - R @ np.array([0.0, 0.0, z_t])
    sampled = sample_surface(rng, template, 1200)
    S_world = sampled @ R.T + T
    tree = cKDTree(S_world)
    seat_resid = float(tree.query(patch)[0].mean())
    above = S_world[((S_world - centre) @ n) > -0.4]
    t2p = (float(cKDTree(patch).query(above)[0].mean()) if len(above) else 9.9)
    if seat_resid > 1.2:  # the pinned pose does not explain the scan — refuse
        return None
    m = np.eye(4)
    m[:3, :3] = R
    m[:3, 3] = T
    return m, seat_resid + 2.0 * t2p


def _rim_agreement_mm(L: np.ndarray, centre_xy: np.ndarray, rim_r: float,
                      template: trimesh.Trimesh,
                      pose_local: np.ndarray) -> Optional[float]:
    """REPORTING ONLY (client feedback 2026-07-14): how far the scan's visible rim ring
    sits from the posed template (p90, mm) — the alignment number a doctor can judge,
    unlike ROI coverage %, which counts surrounding gingiva the cap can never explain
    and structurally cannot reach 100% on a partially visible cap (a perfect seat read
    41% and was mistaken for a bad alignment). Same tilt-fair band construction as the
    all-site seat guard. Never gates or retries anything — that was tried and it
    degraded calibrated behaviour; this is a read-out."""
    d_xy = np.linalg.norm(L[:, :2] - centre_xy, axis=1)
    near = L[d_xy < rim_r + 0.3]
    if len(near) < 40:
        return None
    rim_z = float(np.percentile(near[:, 2], 80))
    band = L[(d_xy > max(0.8, rim_r - 0.8)) & (d_xy < rim_r + 0.4)
             & (np.abs(L[:, 2] - rim_z) < 2.5)]
    if len(band) < 40:
        return None
    c0 = band.mean(axis=0)
    for _ in range(3):
        _, _, vt = np.linalg.svd(band - c0, full_matrices=False)
        keep = np.abs((band - c0) @ vt[2]) < 0.6
        if keep.all() or keep.sum() < 40:
            break
        band = band[keep]
        c0 = band.mean(axis=0)
    m = np.asarray(pose_local, float)
    tmpl_v = np.asarray(template.vertices, float) @ m[:3, :3].T + m[:3, 3]
    return float(np.percentile(cKDTree(tmpl_v).query(band)[0], 90))


def _best_clocking(patch_tree, template: trimesh.Trimesh, R: np.ndarray,
                   center: np.ndarray) -> np.ndarray:
    """CLOCKING for CODED caps (client screenshots 2026-07-14: a well-positioned seat
    LOOKED sideways because the part's coded cutout landed at an arbitrary rotation —
    measured on cap7030: top-face p90 1.39mm at the shipped clocking vs 0.82mm at the
    right one). The old library was revolute so clocking was rightly ignored; the new
    caps carry COD ED FACES, and the top face is where the asymmetry lives — search
    the rotation about the part's own axis that best matches the scan there. Returns
    the 3x3 rotation R @ Rz(phi_best)."""
    v = np.asarray(template.vertices, float)
    top = v[v[:, 2] > v[:, 2].max() - 1.2]
    if len(top) > 400:
        top = top[np.linspace(0, len(top) - 1, 400).astype(int)]
    if len(top) < 30:
        return R  # no coded face to speak of — revolute behaviour stands
    best_phi, best_d = 0.0, None
    for phi in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
        c, s_ = np.cos(phi), np.sin(phi)
        rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
        tw = (top @ rz.T) @ R.T + center
        d = float(patch_tree.query(tw)[0].mean())
        if best_d is None or d < best_d:
            best_phi, best_d = phi, d
    for phi in (best_phi - np.radians(7.5), best_phi + np.radians(7.5)):
        c, s_ = np.cos(phi), np.sin(phi)
        rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
        tw = (top @ rz.T) @ R.T + center
        d = float(patch_tree.query(tw)[0].mean())
        if d < best_d:
            best_phi, best_d = phi, d
    c, s_ = np.cos(best_phi), np.sin(best_phi)
    return R @ np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])


def _template_bore_centre(template: trimesh.Trimesh) -> Optional[np.ndarray]:
    """Screw-channel MOUTH centre (local 3D), read from the template's open boundary
    loops (domain/channel.py) — the CAD's zero-noise record of the channel: the mouth
    and base-opening loops are perfect circles (radial/z std 0.002-0.052mm across all
    12 variants, autopsy 2026-07-23). None when the template shows neither a loop nor
    a top core (no bore to speak of).

    LOOP TRUTH SUPERSEDES THE CENTROID (2026-07-23). This function was a top-core
    surface centroid, and a hole feeds a centroid no vertices: the estimate was
    REPELLED from the bore — measured 0.87-1.06mm from the loop truth at ~174deg the
    WRONG azimuth, on every variant — and that bias flowed into every consumer
    (_recess_clocking's lever and reachability, scoreboard bore_void_off, the QC bore
    star). The old docstring's "no cheap ground truth exists" was false: the outline
    loop IS the cheap ground truth. Re-measured against it, the true bores are nearly
    RING-CONCENTRIC (|bore - ring| 0.02-0.11mm catalog-wide, vs the centroid-era
    0.77-1.12mm) — see _recess_clocking for what that retires. The earlier "0.43-0.76mm
    off the rotational axis" record was the estimator's own artifact; the direct read
    puts the channel 0.20-0.59mm off the CANONICAL axis, on the opposite azimuth,
    concentric with the rim ring. The printed phantom (reports/phantom/) remains the
    physical arbiter, but the CAD-side dispute is settled by the CAD itself.

    FALLBACK: the old top-core centroid survives ONLY for meshes with no qualifying
    boundary loop (watertight or degenerate templates — no catalog part today). It
    keeps its known biases: hole repulsion, and the 4020/4030 cut-fraction
    sensitivity (review 2026-07-20)."""
    ch = channel_from_boundary_loops(template)
    if ch is not None:
        return ch.mouth_centre
    v = np.asarray(template.vertices, float)
    top = v[v[:, 2] > v[:, 2].max() - 1.0]
    if len(top) < 30:
        return None
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    core = top[np.linalg.norm(top[:, :2], axis=1) < 0.45 * rmax]
    if len(core) < 10:
        return None
    return core.mean(axis=0)


def _screw_recess_centre(pts: np.ndarray, centre_xy: np.ndarray, footprint_r: float,
                       expected_radius: Optional[float] = None,
                       radial_tol: float = 0.8) -> Optional[np.ndarray]:
    """Occlusal (xy) centre of the SCANNED screw-recess void near ``centre_xy`` — the dip
    the scanner records where the screw channel opens (it cannot see the bore's interior,
    but the depression is rich signal: measured fleet 547-8356 points, 0.76-3.5mm deep).

    Anchored at DEEP points, tried deepest-first: the recess is a deep compact dip, while
    the coded cutout's D-flat also dips (and on shallow-recess caps can dip COMPARABLY —
    measured on the labeled 7030: the notch out-deepened the recess and hijacked a naive
    single-anchor search) and gum-pocket crevices dip more but only at the periphery. Two
    structural defenses: the anchor search stays within 0.45x the footprint, and — when
    ``expected_radius`` (the template bore's off-axis reach, KNOWN from the CAD) is given —
    a candidate cluster is accepted only if its centre lies within ``radial_tol`` of that
    reachable ring: the screw hole can only be where the screw hole can be. Quality-gated:
    None when nothing acceptable is deep, dense and reachable."""
    d_xy = np.linalg.norm(pts[:, :2] - centre_xy, axis=1)
    near = pts[d_xy < footprint_r * 0.9]
    if len(near) < 100:
        return None
    z_top = float(np.percentile(near[:, 2], 85))
    central = near[np.linalg.norm(near[:, :2] - centre_xy, axis=1) < footprint_r * 0.6]
    below = central[central[:, 2] < z_top - 0.35]
    if len(below) < 40:
        return None
    inner = below[np.linalg.norm(below[:, :2] - centre_xy, axis=1) < footprint_r * 0.45]
    if len(inner) < 20:
        return None
    order = np.argsort(inner[:, 2])
    tried: List[np.ndarray] = []
    for idx in order:
        anchor = inner[int(idx)]
        if any(np.linalg.norm(anchor[:2] - t) < 1.0 for t in tried):
            continue  # same dip as an already-rejected anchor
        if len(tried) >= 4:
            break
        tried.append(anchor[:2].copy())
        cluster = below[np.linalg.norm(below[:, :2] - anchor[:2], axis=1) < 1.3]
        if len(cluster) < 40:
            continue
        if (z_top - float(np.percentile(cluster[:, 2], 10))) < 0.8:
            continue  # dimple, not a recess
        recess_c = cluster[:, :2].mean(axis=0)
        if expected_radius is not None:
            reach_err = abs(float(np.linalg.norm(recess_c - centre_xy)) - expected_radius)
            if reach_err > radial_tol:
                continue  # unreachable by the bore — a notch or crevice, not the recess
        return recess_c
    return None


def _ring_fixed_candidate(template: trimesh.Trimesh, R: np.ndarray,
                          center: np.ndarray,
                          phi_rad: float) -> Optional[Tuple[np.ndarray, float]]:
    """Compensated candidate pose: rotate the pose by ``phi_rad`` about the part's own
    axis while holding the MEASURED rim centre (Kasa of the posed p97-band) exactly
    still — the same ring-fixed kinematics as _recess_clocking, for a single externally
    chosen angle (the coded-cutout clock). Returns (pose4x4, stability_excess_mm) or
    None when the ring is unmeasurable; callers must apply the same stability bound
    (0.35mm) and certification gates as _recess_clocking's adoption."""
    ring3 = _ring_centre_3d(template)
    if ring3 is None:
        return None
    v = np.asarray(template.vertices, float)
    rmax_ring = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
    band = v[np.linalg.norm(v[:, :2], axis=1) > rmax_ring - 0.4]
    if len(band) < 20:
        return None
    if len(band) > 600:
        band = band[np.linspace(0, len(band) - 1, 600).astype(int)]

    center = np.asarray(center, float)
    g0 = circle_centre_xy((band @ R.T + center)[:, :2])
    c, s_ = np.cos(phi_rad), np.sin(phi_rad)
    rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
    Rp = R @ rz
    corr = g0 - circle_centre_xy((band @ Rp.T + center)[:, :2])
    pred = (R @ (rz @ ring3 - ring3))[:2]
    excess = float(np.linalg.norm(corr + pred))
    out = np.eye(4)
    out[:3, :3] = Rp
    out[:3, 3] = center
    out[:2, 3] += corr
    return out, excess


def _recess_clocking(pts: np.ndarray, template: trimesh.Trimesh, R: np.ndarray,
                   center: np.ndarray) -> Optional[np.ndarray]:
    """CLOCKING by the SCREW RECESS (client report 2026-07-18: "screw channels are not
    rotated properly ... the center is never really centered"). The old top-face-distance
    sweep is nearly FLAT on these caps (0.04-0.07mm variation — no discrimination), while
    the bore is OFF-AXIS, so clocking decides where the screw hole lands: measured on the
    shipped fleet, the bore sat 0.3-1.3mm from the scanned recess with the true optimum up
    to ~150 deg away.

    CATALOG RETIREMENT (2026-07-23): the premise numbers above were the POISONED
    estimator's own artifact. Read from the boundary-loop truth (see
    _template_bore_centre), every catalog bore is nearly CONCENTRIC with the rim ring
    — |bore - ring| = 0.02-0.11mm across all 12 variants, below the 0.15mm lever
    floor — so on today's catalog this pass measures no clocking information in the
    recess position and refuses (None) on every variant. That is the physics, not a
    bug: a ring-concentric bore does not move when the part clocks, and the recess
    azimuth was independently convicted as a biased instrument (phantom-clock-truth
    record; codes are the primary clock). The pass and its guards stay for genuinely
    eccentric-channel parts a future catalog may carry.

    RING-FIXED KINEMATICS: the rotation about the part's own axis is composed with the
    exact compensating slide that returns the MEASURED rim centre — the Kasa fit of the
    posed rim band's occlusal projection, the very quantity _center_on_rim just drove
    onto the scanned rim and every rim guard measures — to where it started. Both the
    bore and the rim ring sit off the canonical axis (0.20-0.59mm and 0.18-0.57mm,
    loop-truth/Kasa reads), so an uncompensated axis rotation swings the ring off the
    scanned rim — the measured fleet cost was up to +0.51mm rim off-centre, trading
    away the client's OTHER complaint ("the center is never really centered"). The
    compensation is computed PER CANDIDATE ANGLE from the re-measured Kasa centre, not
    from a fixed 3D ring point: the rim band is a radius-selected STRIP whose
    z-asymmetric cutouts make its projected Kasa centre drift as the part clocks under
    a tilted seat (a fixed-point stand-in leaked 0.20mm, measured 2026-07-19). The
    sweep objective includes the same per-angle compensation, so the chosen angle is
    optimal for the pose actually returned. Ranking is long decided (winner-only) —
    the same structural safety as _best_clocking, which remains the fallback when the
    scan shows no usable recess. Returns the full 4x4 pose (rotation + compensating
    slide) or None (caller falls back)."""
    bore = _template_bore_centre(template)
    if bore is None:
        return None
    ring3 = _ring_centre_3d(template)
    if ring3 is None:
        # no measurable rim ring (degenerate/sparse mesh): the pass's invariant — the
        # measured ring centre — does not exist, so refuse rather than clock about a
        # meaningless Kasa fit (lstsq on <2 points returns silently, review 2026-07-20)
        return None
    arm = bore - ring3
    lever = float(np.linalg.norm(arm[:2]))
    if lever < 0.15:
        return None  # bore concentric with the ring: no clocking information
    center = np.asarray(center, float)
    v = np.asarray(template.vertices, float)
    # the same rim-band definition as _posed_rim_centre / the rim guards
    rmax_ring = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
    band = v[np.linalg.norm(v[:, :2], axis=1) > rmax_ring - 0.4]
    if len(band) < 20:
        return None
    if len(band) > 600:
        band = band[np.linspace(0, len(band) - 1, 600).astype(int)]

    g0 = circle_centre_xy((band @ R.T + center)[:, :2])  # the invariant: the MEASURED rim centre
    top = v[v[:, 2] > v[:, 2].max() - 1.0]
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    recess_c = _screw_recess_centre(pts, g0, rmax, expected_radius=lever)
    if recess_c is None:
        return None

    def _at(phi: float):
        """(bore xy, compensating slide) with the rim centre held at g0 exactly."""
        c, s_ = np.cos(phi), np.sin(phi)
        rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
        Rp = R @ rz
        corr = g0 - circle_centre_xy((band @ Rp.T + center)[:, :2])
        return (Rp @ bore + center)[:2] + corr, corr

    phis = np.linspace(0.0, 2.0 * np.pi, 144, endpoint=False)
    offs = [float(np.linalg.norm(_at(p)[0] - recess_c)) for p in phis]
    best = int(np.argmin(offs))
    phi = phis[best]
    best_off = offs[best]
    for p in (phi - np.radians(1.25), phi + np.radians(1.25)):
        o = float(np.linalg.norm(_at(p)[0] - recess_c))
        if o < best_off:
            phi, best_off = p, o
    # INCUMBENT GATE: this pass exists to REDUCE screw-hole error, never to trade it.
    # When the pose already in hand (the coded-face sweep's rotation) puts the bore
    # closer to the recess than this sweep's own best — the ring circle can sit
    # radially farther from the void than the axis circle the incumbent used
    # (measured: cap7030 0.312 incumbent vs 0.455 sweep best) — keep the incumbent.
    off_now = float(np.linalg.norm((R @ bore + center)[:2] - recess_c))
    if best_off >= off_now - 0.02:
        return None
    c, s_ = np.cos(phi), np.sin(phi)
    rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
    _, corr = _at(phi)
    # STABILITY REFUSAL: the measured compensation must agree with the swing the
    # canonical ring geometry PREDICTS for this angle. The excess is Kasa drift —
    # tolerable at the ~0.2mm strip-projection level the per-angle re-measure exists
    # to absorb, but on a tilted partial-band site the estimate can go unstable and
    # "compensate" the part >1.4mm sideways (t13 re-click, battery 2026-07-19),
    # riding the rim band past its certification bar. An unstable ring measure means
    # this site cannot support ring-fixed clocking: refuse, keep the face-sweep pose.
    pred = (R @ (rz @ ring3 - ring3))[:2]
    if float(np.linalg.norm(corr + pred)) > 0.35:
        return None
    out = np.eye(4)
    out[:3, :3] = R @ rz
    out[:3, 3] = center
    out[:2, 3] += corr  # the measured rim centre stays exactly put
    return out


def _refine_depth(patch: np.ndarray, template: trimesh.Trimesh,
                  m: np.ndarray,
                  rng: Optional[PipelineRng] = None) -> Optional[np.ndarray]:
    """WINNER-ONLY axial-depth polish (client report 2026-07-15: the labeled 6030,
    seeded by the curated centre+rim PAIR, shipped ~2mm HIGH — and with the coded
    cutout hanging in air it read as 'sideways/90 deg rotated'). The 1-D depth search
    inside _rim_seat minimizes the pure patch->template term, and on a TALL straight-
    walled cap that objective is depth-blind-and-biased: the wall explains the patch
    at any height (measured on the real arch: its own minimum IS the 2mm-high pose,
    while the calibrated SYMMETRIC score — seat + 2x(above->patch), the very
    identification formula — bottoms 1.75-2mm lower, 1.71 vs 3.37, with the top face
    ON the scan, 0.35 vs 1.96mm). Ranking is already decided when this runs, so the
    calibrated identification contract is untouched by construction — the same
    structural safety as _best_clocking and _refine_best_fit. The historical
    'combined-score depth choice' regression (see _rim_seat's NOTE) changed depth
    INSIDE the per-variant ranking loop; this stage does not.

    MONOTONIC, multi-gated acceptance — the slide is adopted only when BOTH the
    symmetric score and the TOP-FACE agreement strictly improve. The top face is the
    cap's always-visible surface, so a correct seat at ANY submergence level is
    already at its top-face minimum and refuses the move (this is what makes the
    stage safe on the submerged curated caps that killed the in-ranking variant).
    The pure seat term must also stay inside its own calibration gate (<= 1.0), and
    an argmin railing at the search edge refuses. Returns the slid pose, or None to
    keep the seed."""
    m = np.asarray(m, float)
    R, T = m[:3, :3], m[:3, 3]
    n = R @ np.array([0.0, 0.0, 1.0])
    v = np.asarray(template.vertices, float)
    top = v[v[:, 2] > v[:, 2].max() - 1.2]
    if len(top) > 400:
        top = top[np.linspace(0, len(top) - 1, 400).astype(int)]
    if len(top) < 30:
        return None
    S = sample_surface(rng, template, 1200)
    S_w = S @ R.T + T
    above_w = S[S[:, 2] > -0.4] @ R.T + T  # the part's upper half, its own frame
    top_w = top @ R.T + T
    patch_tree = cKDTree(patch)
    tree = cKDTree(S_w)  # ONE tree: sliding the template == translating the queries

    def seat_at(dz: float) -> float:
        return float(tree.query(patch - n * dz)[0].mean())

    def sym_at(dz: float) -> float:
        t2p = float(patch_tree.query(above_w + n * dz)[0].mean())
        return seat_at(dz) + 2.0 * t2p

    def top_at(dz: float) -> float:
        return float(patch_tree.query(top_w + n * dz)[0].mean())

    base_sym, base_top = sym_at(0.0), top_at(0.0)
    coarse = np.arange(-2.5, 2.5001, 0.25)
    dz = float(coarse[int(np.argmin([sym_at(d) for d in coarse]))])
    fine = np.arange(dz - 0.25, dz + 0.2501, 0.05)
    dz = float(fine[int(np.argmin([sym_at(d) for d in fine]))])
    if abs(dz) >= 2.4:
        return None  # railing — the true seat is outside the trusted slide range
    if sym_at(dz) > base_sym - 0.05 or top_at(dz) > base_top - 0.05:
        return None  # no clear joint improvement — the calibrated seed stands
    # Anti-catastrophe bound on the pure seat term — RELATIVE, not absolute: the
    # correct downward slide legitimately pays some seat cost on a tall wall (the
    # biased objective liked the high pose; measured +0.19 on the labeled 6030,
    # +0.41 on the pocket-polluted zimmer t7 whose gum inflates the term past any
    # absolute bar), but a pathological trade that torches the seat to buy t2p is
    # refused even if the symmetric sum happens to improve.
    if seat_at(dz) > seat_at(0.0) + 0.5:
        return None
    out = m.copy()
    out[:3, 3] = T + n * dz
    return out


def _scan_rim_centre(L: np.ndarray, seed_xy: np.ndarray,
                     rim_r: float) -> Optional[np.ndarray]:
    """Circle centre (occlusal xy) of the SCANNED cap's visible rim band about ``seed_xy`` at
    radius ``rim_r`` — the same band+fit the free rim seat uses internally, exposed so the
    winner-centering pass can target the scan's actual rim. None when the band is too sparse."""
    d = np.linalg.norm(L[:, :2] - seed_xy, axis=1)
    band = L[np.abs(d - rim_r) < 0.6]
    if len(band) < 40:
        return None
    band = band[band[:, 2] > np.percentile(band[:, 2], 50) - 1.0]
    if len(band) < 40:
        return None
    return circle_centre_xy(band[:, :2])


def _ring_centre_3d(template: trimesh.Trimesh) -> Optional[np.ndarray]:
    """The rim ring's 3D circle centre in the CANONICAL frame — fitted xy plus the ring's
    own height. The z matters: under a tilted pose the xy-projection of the posed ring
    (what every rim measure sees) is the projection of THIS point, and holding a z=0
    stand-in fixed instead lets the true ring centre swing by h*sin(tilt) — measured
    0.2mm on a ~4° seat (the 2026-07-19 ring-fixed clocking leak)."""
    v = np.asarray(template.vertices, float)
    rmax = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
    ring = v[np.linalg.norm(v[:, :2], axis=1) > rmax - 0.4]
    if len(ring) < 20:
        return None
    cxy = circle_centre_xy(ring[:, :2])
    return np.array([cxy[0], cxy[1], float(ring[:, 2].mean())])


def _posed_rim_centre(template: trimesh.Trimesh, m: np.ndarray) -> Optional[np.ndarray]:
    """Circle centre (occlusal xy, in ``m``'s frame) of the POSED template's widest rim ring —
    where the cap's rim actually lands on screen. None if the ring is too sparse to fit."""
    v = np.asarray(template.vertices, float)
    rmax = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
    ring = v[np.linalg.norm(v[:, :2], axis=1) > rmax - 0.4]
    if len(ring) < 20:
        return None
    rw = ring @ m[:3, :3].T + m[:3, 3]
    return circle_centre_xy(rw[:, :2])


def _rim_off_centre_anchor_mm(L: np.ndarray, centre_xy: np.ndarray, rim_r: float,
                              template: trimesh.Trimesh,
                              t_local: np.ndarray) -> Optional[float]:
    """The rim-centring instrument parameterized by an EXPLICIT anchor circle — the
    shared band+Kasa construction behind both the marks-anchored panel number
    (_rim_off_centre_mm below) and its machine-anchored twin (_machine_qa_twins):
    the band is the scan annulus at ``rim_r`` about ``centre_xy``, kept above
    median-1.0mm so gingiva under the rim doesn't drag the fit; the read-out is the
    posed rim-circle centre vs that band's Kasa centre (occlusal mm, crowns frame).
    None when the band or the template ring is too sparse — withheld, never guessed."""
    d = np.linalg.norm(L[:, :2] - np.asarray(centre_xy, float), axis=1)
    band = L[np.abs(d - float(rim_r)) < 0.6]
    if len(band) < 20:
        return None
    band = band[band[:, 2] > np.percentile(band[:, 2], 50) - 1.0]
    if len(band) < 20:
        return None
    posed = _posed_rim_centre(template, t_local)
    if posed is None:
        return None
    return float(np.linalg.norm(posed - circle_centre_xy(band[:, :2])))


def _rim_off_centre_mm(L: np.ndarray, center_mark_local: np.ndarray,
                       rim_mark_local: np.ndarray, template: trimesh.Trimesh,
                       t_local: np.ndarray) -> Optional[float]:
    """REPORTING ONLY — the panel's rim-centring number (master plan §8 item 12): the
    posed rim-circle centre vs the SCANNED rim band's Kasa centre, occlusal mm, in the
    crowns frame. Mirrors the fleet scoreboard's marks-anchored construction verbatim
    (tools/fleet_scoreboard.py) so the run row and the scoreboard column read the same
    instrument: the band is the scan annulus at the human-measured rim radius about the
    CENTRE MARK (marks are the anchor — the metric must not be fed by the pose it
    judges), kept above median-1.0mm so gingiva under the rim doesn't drag the fit.
    None when the band or the template ring is too sparse — withheld, never guessed."""
    rim_r = float(np.linalg.norm((rim_mark_local - center_mark_local)[:2]))
    return _rim_off_centre_anchor_mm(L, center_mark_local[:2], rim_r, template, t_local)


def _machine_qa_twins(L: np.ndarray, reading, template: trimesh.Trimesh,
                      t_local: np.ndarray) -> Dict:
    """MACHINE-ANCHORED QA twins (master plan slices 14–15, §8 item 6): the same two
    rim instruments the row already reports — rim agreement (p90) and rim centring —
    anchored to the ISLAND SHADOW'S MACHINE RING instead of the doctor's clicks.

    Invariant Q2 is the reason this exists: *an instrument may never be anchored to an
    input under its own judgment*. The click-anchored numbers are anchored to the very
    gesture that drove the pose, so a pose that follows a corrupted gesture is graded
    by the corruption itself — measured (t13 re-click): a 1.09mm-off pose IMPROVED
    click-anchored rim_agreement while the part sat visibly off the cap. The machine
    ring is segmented from the SCAN, independent of the gesture, so the twin worsens
    exactly where the click-anchored number flatters (the blindness-closure test).

    DUAL-REPORT (transition, slice 29 sunset): the click-anchored fields remain the
    tracked numbers; these twins ride alongside. Consumes the per-site island reading
    ALREADY computed by the shadow block — never re-runs segmentation. Unconverged
    island -> both None plus the honest reason (converged-or-absent, no
    partially-trusted anchors). REPORTING ONLY."""
    if reading is None or not reading.converged:
        reason = "shadow error" if reading is None else reading.reason
        return {"rim_agreement_machine_mm": None,
                "rim_off_centre_machine_mm": None,
                "machine_anchor_reason": f"island unconverged: {reason}"}
    mc = np.asarray(reading.centre_xy, float)
    mr = float(reading.radius)
    agree = _rim_agreement_mm(L, mc, mr, template, t_local)
    off = _rim_off_centre_anchor_mm(L, mc, mr, template, t_local)
    return {
        "rim_agreement_machine_mm": (round(agree, 2) if agree is not None else None),
        "rim_off_centre_machine_mm": (round(off, 3) if off is not None else None),
        # converged anchor: the twins speak for themselves; both unmeasurable on a
        # converged island is named out loud (sparse band), never left ambiguous
        "machine_anchor_reason": ("machine rim band too sparse"
                                  if agree is None and off is None else None),
    }


def delivered_channel_offsets(product: trimesh.Trimesh, pose_w: np.ndarray,
                              frame: np.ndarray, origin: np.ndarray, L: np.ndarray,
                              template: trimesh.Trimesh) -> Dict:
    """G3 measurement (single source of truth, master plan §8 item 12 / slice 12): the
    delivered product's AS-BUILT screw channel vs (a) the RAW scanned recess dip and
    (b) the cap CAD's loop-truth channel, plus the as-built radius. ``product`` is the
    emitted prosthesis in its CANONICAL frame (the scoreboard un-poses the emitted STL
    by inv(pose_matrix) before calling; the pipeline passes the pre-pose mesh — the
    same geometry). Ported verbatim from tools/fleet_scoreboard.py (2026-07-24) so the
    run row and the scoreboard column can never drift; the scoreboard imports it back.
    Judges the DELIVERABLE, never an estimator; every failure withholds (None), never
    guesses. Lives in the pipeline layer because it composes the pipeline's own scan
    instruments (_screw_recess_centre/_ring_centre_3d) — an adapter must not import the
    pipeline layer (qc_render's stated contract). Deterministic: plane sections only."""
    out = {"delivered_channel_vs_recess": None, "delivered_channel_vs_cap_channel": None,
           "delivered_channel_r_mm": None}
    m = measure_delivered_channel(product)
    if m is None:
        return out
    out["delivered_channel_r_mm"] = round(m.radius, 3)

    ch = channel_from_boundary_loops(template)
    # evaluate the as-built channel LINE at the cap mouth plane (the occlusal opening,
    # where the screw enters and where the recess dip lives); mid-stack point otherwise
    p = m.centre
    if ch is not None and abs(float(m.axis[2])) > 1e-9:
        p = m.centre + m.axis * ((float(ch.mouth_centre[2]) - m.centre[2])
                                 / float(m.axis[2]))
    if ch is not None:
        out["delivered_channel_vs_cap_channel"] = round(
            float(np.linalg.norm(p[:2] - ch.mouth_centre[:2])), 3)

    pose_w = np.asarray(pose_w, float)
    Rl = frame.T @ pose_w[:3, :3]
    Tl = frame.T @ (pose_w[:3, 3] - origin)
    ring3 = _ring_centre_3d(template)
    ring3 = ring3 if ring3 is not None else np.zeros(3)
    g0 = (Rl @ ring3 + Tl)[:2]
    tv = np.asarray(template.vertices, float)
    top = tv[tv[:, 2] > tv[:, 2].max() - 1.0]
    if len(top) == 0:
        return out
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    # RAW dip (expected_radius=None): a measurement column must not gate the scan read
    # by a template lever — the G2 five-site contract convention
    recess_c = _screw_recess_centre(L, g0, rmax, expected_radius=None)
    if recess_c is not None:
        out["delivered_channel_vs_recess"] = round(
            float(np.linalg.norm((Rl @ p + Tl)[:2] - recess_c)), 3)
    return out


def _center_on_rim(template: trimesh.Trimesh, m: np.ndarray,
                   target_xy: np.ndarray, max_shift_mm: float = 0.8) -> Optional[np.ndarray]:
    """WINNER-ONLY occlusal re-centering (client report 2026-07-15: seats read 'a bit off
    centre' on every single-pair run). ROOT CAUSE: ``canonicalize_revolute`` centres a cap on
    its mesh CENTROID, but the coded cutouts + emergence flare pull that centroid 0.2-0.58mm
    off the part's true rotational axis (measured across the whole catalog) — so the seat,
    which lands the template ORIGIN on the scanned rim centre, leaves the visible RIM offset by
    that much. Slide the posed template in the occlusal plane so its rim-circle centre lands on
    ``target_xy`` (the scan's Kasa rim centre, or the doctor's clicked circle centre). Bounded
    to ``max_shift_mm`` — a centering nudge, never a basin jump. Ranking is already decided when
    this runs, so the calibrated identification contract is untouched by construction (same
    structural safety as ``_best_clocking``/``_refine_depth``). Returns the slid pose, or None
    (nothing to fit, or the shift exceeds the bound)."""
    posed = _posed_rim_centre(template, m)
    if posed is None:
        return None
    shift = np.asarray(target_xy, float) - posed
    if np.linalg.norm(shift) > max_shift_mm:
        return None
    out = m.copy()
    out[0, 3] += float(shift[0])
    out[1, 3] += float(shift[1])
    return out


_BEST_FIT_CORR_DIST_MM = 1.0  # the winner pass's ICP correspondence cutoff


def _refine_best_fit(patch: np.ndarray, template: trimesh.Trimesh,
                     m_init: np.ndarray,
                     accept=None,
                     max_corr_dist: float = _BEST_FIT_CORR_DIST_MM,
                     rng: Optional[PipelineRng] = None,
                     on_reject: Optional[Callable[[str], None]] = None
                     ) -> Optional[np.ndarray]:
    """BEST-FIT REFINEMENT (client ask 2026-07-14 — the industry pattern: RealGUIDE/
    exocad/3Shape follow coarse human-point alignment with a dense best-fit that
    minimises scan-to-part distance over the selected surface). Kept SAFE against the
    historical trimmed-ICP failure (wandering to ridge-wall basins that score well)
    by construction: a tight TRUST REGION around the seed (≤1.2mm, ≤8°) and
    MONOTONIC ACCEPTANCE — adopted only when it strictly improves the seed's own
    scan-surface agreement and passes the caller's extra check (rim band, tilt cone).
    Returns the refined pose or None (keep the seed).

    ``max_corr_dist`` is the ICP correspondence cutoff (a RADIUS about each source
    point — see ``domain.icp.trimmed_icp``); it defaults to the winner pass's own
    ``_BEST_FIT_CORR_DIST_MM``, so this path is unchanged. It is a parameter only so the
    OPERATOR-triggered pass (``server.best_fit``) can run the identical refinement at the
    matching diameter the lab chose, instead of a second transcription of it.

    ``on_reject`` (review 2026-07-26) is told WHY a None is a None — "trust-region"
    (ICP found only a different basin; NOTHING here proved the seed optimal),
    "no-improvement" (the seed already is the best fit in this band) or
    "accept-rejected" (the caller's extra check said no). The operator endpoint must
    not report the first as the second: only "no-improvement" is a pass. Optional so
    the winner pass, which only cares that the seed stands, is untouched."""
    from case_prep.domain.icp import trimmed_icp

    m0 = np.asarray(m_init, float)
    sampled = sample_surface(rng, template, 2000)
    S0 = sampled @ m0[:3, :3].T + m0[:3, 3]
    before = float(cKDTree(S0).query(patch)[0].mean())
    res = trimmed_icp(S0, patch, np.eye(4), max_corr_dist=float(max_corr_dist),
                      trim_fraction=0.85, max_iter=25)
    r = np.asarray(res.transform.matrix, float)
    dt = float(np.linalg.norm(r[:3, 3]))
    ang = float(np.degrees(np.arccos(np.clip((np.trace(r[:3, :3]) - 1.0) / 2.0,
                                             -1.0, 1.0))))
    if dt > 1.2 or ang > 8.0:
        if on_reject is not None:
            on_reject("trust-region")
        return None  # left the trust region: a different basin, not a refinement
    refined = r @ m0
    S1 = sampled @ refined[:3, :3].T + refined[:3, 3]
    after = float(cKDTree(S1).query(patch)[0].mean())
    if after >= before - 0.01:
        if on_reject is not None:
            on_reject("no-improvement")
        return None  # no strict improvement — the calibrated seed stands
    if accept is not None and not accept(refined):
        if on_reject is not None:
            on_reject("accept-rejected")
        return None
    return refined


def _mean_shift_top(L: np.ndarray, xy: np.ndarray, snap_r: float,
                    max_drift_mm: float = 2.5) -> Tuple[np.ndarray, Optional[float]]:
    """Walk xy to the centroid of the local top surface (the cap crown): any click on
    the cap converges to the same top-centre point. Drift is clamped so the walk can
    never wander off the marked cap onto a taller neighbour. Returns the (possibly
    unchanged) xy and the local top height (None when the area is too sparse)."""
    anchor = np.asarray(xy, float).copy()
    cur = anchor.copy()
    z_top = None
    for _ in range(12):
        near = L[np.linalg.norm(L[:, :2] - cur, axis=1) < snap_r]
        if len(near) < 20:
            break
        zt = float(np.percentile(near[:, 2], 80))
        band = near[near[:, 2] >= zt - 1.2]
        new_xy = band[:, :2].mean(axis=0)
        if np.linalg.norm(new_xy - anchor) > max_drift_mm:
            break
        moved = float(np.linalg.norm(new_xy - cur))
        cur = new_xy
        z_top = zt
        if moved < 1e-9:
            break
    return cur, z_top


def _cap_patch_roi(L: np.ndarray, seed_xy: np.ndarray,
                   rim_radius_mm: Optional[float] = None,
                   lift_mm: float = 0.3) -> Optional[np.ndarray]:
    """AUTO-BRUSH: the cap's exposed surface above the local tissue level around the click —
    the same input a doctor's brush stroke produces. The tall-scan-body cylinder isolator
    (localize_from_seed) keeps ridge WALLS on low-profile caps, and a trimmed fit happily
    explains a wall (measured: template body poking out of the buccal slope while its top
    grazed the dome).

    The crop is a 3D BALL centred at rim height — the shape of an actual brush stroke.
    A z-cut cylinder needs a tissue-level estimate, and every estimator tried lied on some
    geometry (a wide annulus plunges ~3mm on sloped ridges; a tight collar reads tooth
    slopes inside pockets). The ball needs no tissue estimate: centred on the rim, it fades
    out below the cap and above the neighbours by construction (validated: seats the
    tilted-fit lower case and drops the Zimmer pocket cap from 27 to 5 deg)."""
    del lift_mm  # kept for signature stability; the ball crop needs no tissue estimate
    rim_r = float(rim_radius_mm) if rim_radius_mm else 2.6
    d = np.linalg.norm(L[:, :2] - seed_xy, axis=1)
    near = L[d < rim_r]
    if len(near) < 40:
        return None
    rim_z = float(np.percentile(near[:, 2], 80))
    center = np.array([seed_xy[0], seed_xy[1], rim_z])
    # the ball must clear the rim with margin — an undersized crop truncates the rim
    # band and forfeits the closed-form seat (measured: a wide cap sliding 4.2mm)
    patch = L[np.linalg.norm(L - center, axis=1) < min(rim_r + 1.2, 5.4)]
    return patch if len(patch) >= 60 else None


def _pose_stability_bootstrap(L: np.ndarray, site, frame: np.ndarray,
                              origin: np.ndarray, template: trimesh.Trimesh,
                              rng: np.random.Generator,
                              sample_rng: Optional[PipelineRng] = None,
                              k: int = 8, sigma_mm: float = 0.3):
    """CONFIDENCE probe (Spec A, 2026-07-15): re-seat the WINNING variant ``k`` times under
    Gaussian occlusal-plane perturbation of the doctor's marks (``sigma_mm`` = the measured
    good-gesture click noise), reusing the SAME seat callables the main path uses. Returns
    ``(perturbed_poses, reference_pose)`` in the local crowns frame — the reference is the
    UNPERTURBED re-seat, so the spread is measured against this path's own baseline rather
    than the shipped pose (which carries extra winner-only post-passes). READ-ONLY: nothing
    here changes the shipped pose or the identified variant. Returns None when the input is
    not a rim gesture (brush/click) or too few re-seats succeed to trust the spread.

    The bootstrap answers the clinical question a lab actually asks: would a slightly
    different, equally-plausible click have given the same alignment? A tight spread = yes.

    TWO streams, both owned, neither the run's: ``rng`` perturbs the marks, ``sample_rng``
    feeds the k+1 re-seats' surface sampling. The re-seats must draw from their OWN stream
    — this is a REPORTING probe, and a reporting probe that spends the run's randomness
    would make the shipped poses of later sites depend on whether the operator asked for
    a confidence number. Both are seeded per tooth, so the grade is reproducible."""
    border_l = ((np.asarray(site.rim_points, float) - origin) @ frame
                if site.rim_points and len(site.rim_points) >= 3 else None)
    center_l = (frame.T @ (np.asarray(site.center_mark, float) - origin)
                if site.center_mark is not None else None)
    rim_l = (frame.T @ (np.asarray(site.rim_mark, float) - origin)
             if site.rim_mark is not None else None)
    if border_l is None and (center_l is None or rim_l is None):
        return None  # brush/click seeds: no rim gesture to perturb

    scan_tree = cKDTree(L)

    def _seed_z(xy: np.ndarray) -> float:
        d = np.linalg.norm(L[:, :2] - xy, axis=1)
        near = L[d < 2.5] if int((d < 2.5).sum()) >= 20 else L[np.argsort(d)[:12]]
        return float(np.percentile(near[:, 2], 80)) if len(near) else 0.0

    # NOTE: clocking is deliberately NOT applied in the bootstrap. The coded top faces are
    # near-revolute, so their clocking objective is nearly flat — small mark perturbations
    # flip the argmin across shallow minima (measured 40-160deg spread on good gestures,
    # no discrimination). Clocking stability is a separate, weaker concern; the CLINICAL
    # confidence a lab needs is POSITION + AXIS of the implant platform, which the rim seat
    # determines and which the bootstrap measures cleanly.

    def _seat_border(P: np.ndarray):
        circles = _fit_circle_3d(P, scan_tree=scan_tree)
        fit = _fit_circle_xy(P[:, :2])
        if circles is None or fit is None:
            return None
        patch = _cap_patch_roi(L, fit[0], rim_radius_mm=fit[1])
        if patch is None:
            return None
        best = None
        for circle in circles:
            s = _pinned_rim_seat(patch, circle, template, rng=sample_rng)
            if s is not None and (best is None or s[1] < best[1]):
                best = s
        return best[0] if best is not None else None

    def _seat_pair(c_xy: np.ndarray, r_xy: np.ndarray):
        rim_r = float(np.linalg.norm(r_xy - c_xy))
        seed = np.array([c_xy[0], c_xy[1], _seed_z(c_xy)])
        patch = _cap_patch_roi(L, seed[:2], rim_radius_mm=rim_r)
        if patch is None:
            return None
        # min_arc_bins=6: the bootstrap always has a human-vouched radius (the pair), the
        # same relaxation the main path applies when human_rim_r is set
        s = _rim_seat(patch, seed[:2], rim_r, template, min_arc_bins=6, rng=sample_rng)
        return s[0] if s is not None else None

    def _seat(offsets):
        if border_l is not None:
            P = border_l.copy()
            P[:, :2] = P[:, :2] + offsets
            return _seat_border(P)
        return _seat_pair(center_l[:2] + offsets[0], rim_l[:2] + offsets[1])

    n_marks = len(border_l) if border_l is not None else 2
    reference = _seat(np.zeros((n_marks, 2)))
    if reference is None:
        return None
    poses = []
    for _ in range(k):
        m = _seat(rng.normal(0.0, sigma_mm, size=(n_marks, 2)))
        if m is not None:
            poses.append(m)
    if len(poses) < max(3, k // 2):
        return None  # too unstable to even re-seat — the spread would be untrustworthy
    return poses, reference


@dataclass(frozen=True)
class WinnerPose:
    """What the winner pass produces: the pose that actually ships, the coverage measured
    at it, and the clocking instrument's read-out (None on seats the pass does not touch).
    """

    pose: np.ndarray                       # 4x4, template canonical -> crowns-up local
    coverage: float
    clocking: Optional[Dict]


def refine_winner_pose(L: np.ndarray, roi: np.ndarray, template: trimesh.Trimesh,
                       pose: np.ndarray, coverage: float, *,
                       squat_library: bool, seat_method: str, seat_pinned: bool,
                       rim_fit_circle, human_rim_r, seed_xy: np.ndarray,
                       seat_rim_r, rng: Optional[PipelineRng] = None) -> WinnerPose:
    """THE WINNER PASS: the ordered chain of polish stages applied to the ALREADY-CHOSEN
    seat, and to nothing else.

    The separation this function exists to make visible: identification and ranking are
    finished before it is called, on the calibrated (unclocked) scores. Every stage here
    only moves the pose that already won — so no stage can change WHICH part is shipped,
    and the house rule that ranking never sees winner-only work is structural instead of
    a comment. Each stage is individually gated and monotonic: it is adopted only when
    the depth-sensitive read-outs it could fool do not get worse.

    Inputs are the site's evidence, not the site's objects: ``L`` the whole scan in the
    crowns-up local frame, ``roi`` the isolated cap surface, ``template`` the winning
    variant's CAD, ``pose`` the seat to polish. ``rim_fit_circle`` / ``human_rim_r`` /
    ``seed_xy`` / ``seat_rim_r`` are the rim anchors, in the precedence the seat used.

    Order is load-bearing and NOT free to change — see each stage's own note; the
    measured failures that fixed it are recorded there (a clock before a depth pass has
    no signal; a centring pass after a clock drags the bore off the scanned recess).
    """
    t_local = pose
    clocking_info = None  # set by the winner clocking pass on rim seats
    # WINNER-ONLY POST-PASSES — identification/ranking is already decided with the
    # calibrated (unclocked) scores; these stages only polish the shipped pose:
    # (0) DEPTH: the free rim path's 1-D depth search is blind on tall straight
    # walls (client report 2026-07-15: a 6030 rode ~2mm high and read 'sideways');
    # slide the winner along its own axis, multi-gated — see _refine_depth;
    # (1) CLOCKING: rotate the coded face to match the scan (client screenshots:
    # a well-positioned seat LOOKED sideways with the cutout at a random angle) —
    # run AFTER depth: at the wrong height the top face is off the scan everywhere
    # and the clocking sweep has no signal (measured: 1.92-1.96 flat);
    # (2) BEST-FIT refinement (RealGUIDE-style), trust-region + monotonic accept.
    if squat_library and seat_method == "rim" and not seat_pinned:
        deep = _refine_depth(roi,
                             template, t_local, rng=rng)
        if deep is not None:
            # the band-anchored read-out must not get worse — same guard style as
            # the best-fit stage's accept below
            _da = None
            if rim_fit_circle is not None:
                _da = (rim_fit_circle[0], rim_fit_circle[1])
            elif human_rim_r:
                _da = (seed_xy, float(human_rim_r))
            _b0 = _b1 = None
            if _da is not None:
                _b0 = _rim_agreement_mm(L, _da[0], _da[1],
                                        template, t_local)
                _b1 = _rim_agreement_mm(L, _da[0], _da[1],
                                        template, deep)
            if _b0 is None or _b1 is None or _b1 <= _b0 + 0.02:
                t_local = deep
    if squat_library and seat_method == "rim":
        # (1) CLOCKING (coded-face sweep): orients the coded face for the refinement
        # stage's metrics. The authoritative RECESS clocking runs as the FINAL pass
        # below — rotation about the axis must happen after every translation stage,
        # or the centering pass drags the bore back off the scanned recess (measured
        # 0.31 -> 0.46 when clocking preceded centering).
        t_clocked = t_local.copy()
        t_clocked[:3, :3] = _best_clocking(
            cKDTree(roi), template,
            t_local[:3, :3], t_local[:3, 3])
        t_local = t_clocked
    if squat_library and seat_method == "rim":
        _anchor = None
        if rim_fit_circle is not None:
            _anchor = (rim_fit_circle[0], rim_fit_circle[1])
        elif human_rim_r:
            _anchor = (seed_xy, float(human_rim_r))

        # Depth-sensitive readouts guarding _accept: best-fit's own objective
        # (patch->template mean) is depth-blind on straight walls — without these
        # gates it would happily slide a depth-polished part back UP inside its
        # 1.2mm trust region (the wall "improves" at any height; the top face and
        # the symmetric score do not lie about depth).
        _tmpl_w = template
        _roi_pts = roi
        _roi_tree = cKDTree(_roi_pts)
        _tvw = np.asarray(_tmpl_w.vertices, float)
        _topw = _tvw[_tvw[:, 2] > _tvw[:, 2].max() - 1.2]
        if len(_topw) > 400:
            _topw = _topw[np.linspace(0, len(_topw) - 1, 400).astype(int)]
        _sampw = sample_surface(rng, _tmpl_w, 1200)
        _abovew = _sampw[_sampw[:, 2] > -0.4]

        def _depth_metrics(mm):
            seat = float(cKDTree(_sampw @ mm[:3, :3].T + mm[:3, 3]
                                 ).query(_roi_pts)[0].mean())
            t2p = float(_roi_tree.query(_abovew @ mm[:3, :3].T + mm[:3, 3])[0].mean())
            top = (float(_roi_tree.query(_topw @ mm[:3, :3].T + mm[:3, 3])[0].mean())
                   if len(_topw) else 0.0)
            return seat + 2.0 * t2p, top

        _sym0, _top0 = _depth_metrics(t_local)

        def _accept(m_ref):
            axis_ref = m_ref[:3, :3] @ np.array([0.0, 0.0, 1.0])
            if axis_ref[2] < np.cos(np.radians(45.0)):
                return False
            sym1, top1 = _depth_metrics(m_ref)
            if sym1 > _sym0 + 0.05 or top1 > _top0 + 0.05:
                return False  # a depth-blind "improvement" — would ride back up
            if _anchor is None:
                return True
            b0 = _rim_agreement_mm(L, _anchor[0], _anchor[1],
                                   template, t_local)
            b1 = _rim_agreement_mm(L, _anchor[0], _anchor[1],
                                   template, m_ref)
            return b0 is None or b1 is None or b1 <= b0 + 0.02

        refined = _refine_best_fit(roi,
                                   template, t_local,
                                   accept=_accept, rng=rng)
        if refined is not None:
            t_local = refined
            _rs = sample_surface(rng, template, 2500)
            _rw = _rs @ t_local[:3, :3].T + t_local[:3, 3]
            coverage = float((cKDTree(_rw).query(
                roi)[0] < _COVERAGE_TOL_MM).mean())
    if squat_library and seat_method == "rim":
        # (3) CENTERING — land the posed rim on the scan's rim (single-pair path)
        # or the doctor's clicked circle (border path). Corrects the off-centroid
        # canonical origin (see _center_on_rim). Monotonic: adopt only when the
        # band-anchored agreement and top-face BOTH hold — a noisy partial-rim Kasa
        # target can't drag the seat off. The p90 ride-off bound (below) also
        # applies: a rim-perfect slide must not lift the face off the scan
        # (zimmer-t7 2026-07-19: such a slide pushed p90 1.4 -> 1.72).
        _tmpl_cc = template
        _roi_tree_vc = cKDTree(roi)
        _tvv = np.asarray(_tmpl_cc.vertices, float)
        _tpv = _tvv[_tvv[:, 2] > _tvv[:, 2].max() - 1.2]
        if len(_tpv) > 400:
            _tpv = _tpv[np.linspace(0, len(_tpv) - 1, 400).astype(int)]
        _Ltree = cKDTree(L)
        _P90_BOUND = 1.5  # the certification guards' top-face p90 limit

        def _top_p90(m):
            return float(np.percentile(
                _Ltree.query(_tpv @ m[:3, :3].T + m[:3, 3])[0], 90))

        _target = None
        if rim_fit_circle is not None:
            _target = np.asarray(rim_fit_circle[0], float)
        elif human_rim_r:
            _target = _scan_rim_centre(L, seed_xy, float(human_rim_r))
        _ac = _ar = None
        if rim_fit_circle is not None:
            _ac, _ar = _target, float(rim_fit_circle[1])
        elif human_rim_r:
            _ac, _ar = seed_xy, float(human_rim_r)
        elif seat_rim_r:
            # click/brush path: no human rim marks, but the measured rim radius is
            # a valid band anchor — the REPORTING block below already uses exactly
            # this fallback, and without it the void clock's rim-band certification
            # gate was silently skipped on this seed path (review 2026-07-20).
            _ac, _ar = seed_xy, float(seat_rim_r)
        if _target is not None:
            centred = _center_on_rim(_tmpl_cc, t_local, _target)
            if centred is not None:
                b0 = _rim_agreement_mm(L, _ac, _ar, _tmpl_cc, t_local)
                b1 = _rim_agreement_mm(L, _ac, _ar, _tmpl_cc, centred)
                top0 = float(_Ltree.query(
                    _tpv @ t_local[:3, :3].T + t_local[:3, 3])[0].mean())
                top1 = float(_Ltree.query(
                    _tpv @ centred[:3, :3].T + centred[:3, 3])[0].mean())
                p90_0, p90_1 = _top_p90(t_local), _top_p90(centred)
                if ((b0 is None or b1 is None or b1 <= b0 + 0.02)
                        and top1 <= top0 + 0.05
                        and not (p90_1 > _P90_BOUND and p90_1 > p90_0 + 0.02)):
                    t_local = centred
        # (4) CLOCKING — the true FINAL pass (client reports 2026-07-18 + 07-20:
        # "screw channels are not rotated properly ... never really centered",
        # "not properly aligned and rotated to match the healing cap"). The
        # CODED CUTOUTS are primary: a lab tech judges rotation at the coded
        # features, and the two-pose-consistency validation (2026-07-20, design
        # e8 — the only extractor that reproduced known applied rotations, 6/7
        # sites <=10 deg) measured that the recess-void AZIMUTH is systematically
        # unreliable (a partially-visible recess dip biases its centroid sideways;
        # the void clock had rotated AWAY from the coded features on 5 of 7 sites
        # where it fired). Arbitration: coded-feature reading with evidence ->
        # rotate to the codes (ring-fixed kinematics, all certification gates,
        # plus a confirm re-read at the candidate pose); no code evidence -> the
        # recess clock exactly as before (weak-signal sites keep their behavior);
        # neither instrument -> the face-sweep pose ships flagged
        # rotation_unverified. When both instruments read, their disagreement is
        # reported (clock_consistency_deg) — on a rigid part they cannot both be
        # right, and >20 deg routes operator attention. The physical arbiter for
        # the instrument conflict is the printed phantom (designed clock angles).
        from case_prep.domain.clock_signature import (notch_reading,
                                                      scan_rim_centre,
                                                      template_signature)

        def _clock_gates_ok(cand: np.ndarray) -> bool:
            d_now = float(_roi_tree_vc.query(
                _tpv @ t_local[:3, :3].T + t_local[:3, 3])[0].mean())
            d_new = float(_roi_tree_vc.query(
                _tpv @ cand[:3, :3].T + cand[:3, 3])[0].mean())
            p90_0, p90_1 = _top_p90(t_local), _top_p90(cand)
            band_ok = True
            if _ar:
                bv0 = _rim_agreement_mm(L, _ac, _ar, _tmpl_cc, t_local)
                bv1 = _rim_agreement_mm(L, _ac, _ar, _tmpl_cc, cand)
                if bv0 is not None and bv1 is not None:
                    band_ok = not (bv1 >= 1.6 and bv1 > bv0 + 0.02)
            return (d_new <= d_now + 0.4 and band_ok
                    and not (p90_1 > _P90_BOUND and p90_1 > p90_0 + 0.02))

        _sig = template_signature(_tmpl_cc)
        _crop = L[np.linalg.norm(L[:, :2] - t_local[:2, 3], axis=1) < 8.0]
        _canon0 = (_crop - t_local[:3, 3]) @ t_local[:3, :3]
        _c0 = scan_rim_centre(_canon0, _sig.ztop, _sig.rmax)
        _cL = t_local[:3, :3] @ np.array([_c0[0], _c0[1], _sig.ztop]) \
            + t_local[:3, 3]
        _read0 = notch_reading(_canon0, _sig, _c0)
        m_recess = _recess_clocking(L, _tmpl_cc, t_local[:3, :3], t_local[:3, 3])
        _phi_recess = None
        if m_recess is not None:
            _rel = t_local[:3, :3].T @ m_recess[:3, :3]
            _phi_recess = float(np.degrees(np.arctan2(_rel[1, 0], _rel[0, 0])))
        clocking_info = {
            "notch_shift_deg": (round(_read0.shift_deg, 1)
                                if _read0.shift_deg is not None else None),
            "notch_corr": round(_read0.corr, 3),
            "notch_prominence": round(_read0.prominence, 3),
            "evidence": "none",
            "consistency_deg": None,
            "rotation_unverified": False,
        }
        if (_read0.has_evidence and _phi_recess is not None):
            # codes want the pose rotated by -reading (the reading grows WITH an
            # applied rotation — two-pose identity, validated); the recess wants
            # +phi_recess. Their disagreement is the cross-instrument check.
            clocking_info["consistency_deg"] = round(
                abs(float((-_read0.shift_deg - _phi_recess + 180.0)
                          % 360.0 - 180.0)), 1)
        if _read0.has_evidence:
            clocking_info["evidence"] = ("codes+recess" if m_recess is not None
                                         else "codes")
            if abs(_read0.shift_deg) > 6.0:
                # nulling rotation = MINUS the reading (two-pose identity:
                # m_after - m_before = applied rotation, verified 6/7 sites)
                _rf = _ring_fixed_candidate(_tmpl_cc, t_local[:3, :3],
                                            t_local[:3, 3],
                                            np.radians(-_read0.shift_deg))
                if _rf is not None and _rf[1] <= 0.35 and _clock_gates_ok(_rf[0]):
                    _cand = _rf[0]
                    _canon1 = (_crop - _cand[:3, 3]) @ _cand[:3, :3]
                    _c1 = ((_cL - _cand[:3, 3]) @ _cand[:3, :3])[:2]
                    _read1 = notch_reading(_canon1, _sig, _c1)
                    if (_read1.shift_deg is not None
                            and abs(_read1.shift_deg) <= 12.0
                            and _read1.corr >= _read0.corr - 0.05):
                        t_local = _cand
                        clocking_info["notch_shift_deg"] = round(
                            _read1.shift_deg, 1)
                        clocking_info["notch_corr"] = round(_read1.corr, 3)
                    else:
                        clocking_info["rotation_unverified"] = True
                else:
                    clocking_info["rotation_unverified"] = True
        elif m_recess is not None and _clock_gates_ok(m_recess):
            # no coded-feature evidence: the recess clock keeps its shipped
            # behavior verbatim (gates identical to the 2026-07-19 pass)
            t_local = m_recess
            clocking_info["evidence"] = "recess"
        else:
            clocking_info["rotation_unverified"] = True
    return WinnerPose(pose=t_local, coverage=coverage, clocking=clocking_info)



def _relief_summary(requested_mm: float,
                    clamps: Dict[int, ReliefClamp]) -> Dict[str, object]:
    """The case-level gingival-relief verdict: what was asked for, what was cut, and
    whether those differ.

    The run now COMPLETES when the ask exceeds a part's safe ceiling (client escalation
    2026-07-25) — so the one thing this block must never do is let that difference hide.
    ``clamped`` True is the loud fact; ``by_tooth`` carries the per-site numbers, because
    sites identifying different caps have different ceilings and a single case-level
    applied figure would be a fiction. ``gingival_offset_applied_mm`` is therefore a number
    only when every site was cut at the same relief, and None otherwise."""
    rows = [{"tooth": tooth, **clamp.as_json()} for tooth, clamp in sorted(clamps.items())]
    clamped = [r for r in rows if r["clamped"]]
    applied = sorted({r["gingival_offset_applied_mm"] for r in rows})
    if not rows:
        note = "no production set was generated — no gingival relief was cut"
    elif clamped:
        note = (f"the requested {float(requested_mm):.2f}mm relief is NOT safe on "
                f"{len(clamped)} of {len(rows)} site(s): the export gate would refuse the "
                f"part. The package was emitted at the maximum safe relief for each "
                f"construction-part/cap pair — the requested value was REFUSED, not "
                f"applied. See clamp_reason.")
    else:
        note = (f"every site was cut at the requested {float(requested_mm):.2f}mm relief "
                f"— the export gate accepts it on all of them")
    return {
        "gingival_offset_requested_mm": float(requested_mm),
        "gingival_offset_applied_mm": (applied[0] if len(applied) == 1 else None),
        "clamped": bool(clamped),
        "clamp_reason": ("; ".join(dict.fromkeys(r["clamp_reason"] for r in clamped))
                         if clamped else None),
        "by_tooth": rows,
        "note": note,
    }


def run_auto_case(case_id: str, scan: trimesh.Trimesh, library: CapLibrary,
                  construction_mesh: trimesh.Trimesh, vendor: str,
                  confirmed: List[ConfirmedSite], jaw_label: str,
                  out_dir, generate_product: bool = True,
                  emit_package: bool = True,
                  screw_radius_mm: float = DEFAULT_SCREW_RADIUS_MM,
                  proposals: Optional[List[List[float]]] = None,
                  compute_confidence: bool = False,
                  render_qc: bool = True,
                  gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM,
                  site_gingival_offsets: Optional[Dict[int, float]] = None,
                  rng: Optional[PipelineRng] = None) -> Dict:
    """Align, measure, gate and package every confirmed site — see ``_align_and_package``
    for the full contract. This wrapper exists for ONE reason: THE CALLER'S RANDOMNESS IS
    NOT OURS TO SPEND.

    Aligning a case used to overwrite numpy's process-global stream outright
    (``np.random.seed(0)``). It no longer needs to — the run draws from its own injected
    ``rng`` — but the global stream is still touched INSIDE third-party code we call:
    every ``trimesh`` ``apply_transform`` draws from it (``transformations.flips_winding``
    probes the winding with ``np.random.random``), as do the not-yet-migrated seeded shims
    in qc_render / clock_signature / final_product. Measured on a real run: 41 global
    draws, most of them from trimesh internals we do not control.

    So the boundary is enforced here instead of chased: whatever the caller's stream was
    on the way in, it is exactly that on the way out — including when the run raises. Our
    own reproducibility does not depend on this (that comes from ``rng``); this is about
    not corrupting a study harness, a fixture or a benchmark that happens to call us."""
    ambient = np.random.get_state()
    try:
        return _align_and_package(
            case_id=case_id, scan=scan, library=library,
            construction_mesh=construction_mesh, vendor=vendor, confirmed=confirmed,
            jaw_label=jaw_label, out_dir=out_dir, generate_product=generate_product,
            emit_package=emit_package,
            screw_radius_mm=screw_radius_mm, proposals=proposals,
            compute_confidence=compute_confidence, render_qc=render_qc,
            gingival_offset_mm=gingival_offset_mm,
            site_gingival_offsets=site_gingival_offsets, rng=rng)
    finally:
        np.random.set_state(ambient)


def _align_and_package(case_id: str, scan: trimesh.Trimesh, library: CapLibrary,
                       construction_mesh: trimesh.Trimesh, vendor: str,
                       confirmed: List[ConfirmedSite], jaw_label: str,
                       out_dir, generate_product: bool = True,
                       emit_package: bool = True,
                       screw_radius_mm: float = DEFAULT_SCREW_RADIUS_MM,
                       proposals: Optional[List[List[float]]] = None,
                       compute_confidence: bool = False,
                       render_qc: bool = True,
                       gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM,
                       site_gingival_offsets: Optional[Dict[int, float]] = None,
                       rng: Optional[PipelineRng] = None) -> Dict:
    """Align, measure, gate and package every confirmed site. Returns the case summary
    (also written as ``<case_id>-auto-report.json`` beside the package).

    ``gingival_offset_mm`` (default 0.20, the client's value) is the tissue clearance the
    emitted construction part carries — see ``final_product.build_final_product``. The
    value USED lands in each site row's ``production`` block and in the package audit
    (``<case>-<tooth>-implant.json`` -> ``audit.gingival_offset_mm``), so a delivered part
    can always be traced to the relief it was cut with.

    IT IS AN ASK, NOT A GUARANTEE (2026-07-25, client escalation "end-to-end automation must
    complete"). Each (construction part x identified cap) pair is measured for the largest
    relief the export gate will still emit (``final_product.resolve_gingival_offset``) and
    the part is cut at min(requested, ceiling). The run therefore COMPLETES where it used to
    die at emission — but never quietly: ``clamped``/``clamp_reason`` and both numbers ride
    in the site row, the audit, the manifest and the case-level ``gingival_relief`` block.
    The export gate is unchanged and still hard-blocks a part that fails even at 0.0.

    ``compute_confidence`` (opt-in, default off): run the per-site pose-stability bootstrap
    (K re-seats of the winner under click noise) and attach a graded ``confidence`` to each
    row. Off by default because the bootstrap costs several seconds/site — enable it on the
    interactive server, leave it off for the battery.

    ``render_qc`` (default on): emit the two per-site QC acceptance PNGs (clock view +
    signed difference map) into the hashed package manifest. Reporting only — never moves
    a pose; tests that need speed may pass False.

    ``rng`` is the run's OWN random stream (surface sampling is the pipeline's only
    randomness). Default: a fresh ``PipelineRng()`` on the shipped seed, so the same
    inputs always give the same poses regardless of what the process did to numpy's
    global stream beforehand — and the caller's global stream is left untouched."""
    if not confirmed:
        raise ValueError("no confirmed sites — run propose_sites and confirm at least one")

    # Reproducibility (clinical/audit requirement): registration and coverage scoring sample
    # surfaces, and sampling is random. The run OWNS that stream (``rng``) instead of
    # seeding the process-global one, so a run's poses depend on its inputs and nothing
    # else: not on what the caller drew before, not on which other case ran first in this
    # process. It also stops the pipeline trampling the caller's own global stream, which
    # the old ``np.random.seed(0)`` did on every call. Byte-identical to that seeding:
    # same MT19937, same seed, same draw order — see adapters/rng.py.
    # Not-yet-migrated stages (qc_render, final_product, clock_signature) keep their own
    # local seed/restore shims and are unaffected either way.
    rng = rng if rng is not None else PipelineRng()

    pts = np.asarray(scan.vertices, float)
    normals = np.asarray(scan.vertex_normals, float)
    frame, origin, occ_axis = _crowns_frame(pts, normals)
    L = (pts - origin) @ frame
    Ln = normals @ frame

    xy_tree = cKDTree(L[:, :2])
    variant_table = library.variant_dimensions()
    squat_library = _library_is_squat(library)

    package_sites = []
    site_rows = []
    # inputs for the post-loop SHADOW island measurement: (tooth, seed xy, rim-radius
    # hint, final local pose, template). Stashed — never consumed inside the loop.
    shadow_inputs = []
    for site in confirmed:
        # THE SEED only says WHERE the cap is (client spec: brush marks are POINTERS —
        # the first mark can be just the cap's center). Brush or click, the SCAN provides
        # the alignment surface and the seating logic is identical — a few dabs must
        # align exactly as well as a dense patch or a curated click.
        human_rim_r = None
        # per-site brush patch — a site may carry BOTH marks and a brush; a stale patch
        # from a previous site must never leak into this one (review 2026-07-14, HIGH)
        marks = ((np.asarray(site.marked_points, float) - origin) @ frame
                 if site.marked_points else None)
        # MULTI-POINT rim border (client spec 2026-07-14): the doctor clicks several
        # points around the cap's visible border; the circle FIT through them is the
        # measurement — centre AND radius — robust to any one imprecise click. It
        # overrides the single centre/rim marks (which then only locate the cap). The
        # full 3D circle (plane = axis + depth) additionally PINS the seat downstream.
        rim_fit_circle = None
        rim_circle_3d = None
        border_disagreement = None
        if site.rim_points and len(site.rim_points) >= 3:
            P = (np.asarray(site.rim_points, float) - origin) @ frame
            rim_fit_circle = _fit_circle_xy(P[:, :2])
            rim_circle_3d = _fit_circle_3d(P, scan_tree=cKDTree(L))
            border_disagreement = _border_click_disagreement(P)
        if rim_fit_circle is not None:
            centre_fit, human_rim_r = rim_fit_circle
            seed_local = np.array([centre_fit[0], centre_fit[1], 0.0])
            d_xy = np.linalg.norm(L[:, :2] - seed_local[:2], axis=1)
            near = L[d_xy < 2.5] if int((d_xy < 2.5).sum()) >= 20 \
                else L[np.argsort(d_xy)[:12]]
            if len(near):
                seed_local[2] = float(np.percentile(near[:, 2], 80))
            seed_source = "marks"
        elif site.center_mark is not None:
            seed_local = frame.T @ (np.asarray(site.center_mark, float) - origin)
            # SNAP TO THE CAP TOP (client fix 2026-07-14): a centre mark only IDENTIFIES
            # the cap — the raycast's depth depends on viewing angle/scanner position at
            # click time and must not steer the seat (and in a tilted crowns frame a depth
            # error bleeds into local xy too). The depth is ALWAYS re-read from the SCAN
            # (nearest points when the mesh is sparse); a bare centre click additionally
            # mean-shifts xy to the local top-surface centroid, so any click on the cap's
            # crown converges to the same top-centre point.
            d_xy = np.linalg.norm(L[:, :2] - seed_local[:2], axis=1)
            snap_r = next((r for r in (2.5, 5.0)  # widen on sparse meshes
                           if int((d_xy < r).sum()) >= 20), None)
            near = L[d_xy < snap_r] if snap_r is not None else L[np.argsort(d_xy)[:12]]
            if len(near):
                seed_local[2] = float(np.percentile(near[:, 2], 80))
            if snap_r is not None and site.rim_mark is None:
                # bare centre click: the scan supplies the geometry — walk to the cap top.
                # With a centre+rim PAIR the human measured centre AND radius: xy is
                # ground truth and only the depth above is re-read.
                new_xy, z_top = _mean_shift_top(L, seed_local[:2], snap_r)
                seed_local[:2] = new_xy
                if z_top is not None:
                    seed_local[2] = z_top
            seed_source = "marks"
            if site.rim_mark is not None:
                rim_local = frame.T @ (np.asarray(site.rim_mark, float) - origin)
                human_rim_r = float(np.linalg.norm((rim_local - seed_local)[:2]))
            elif site.rim_points:  # 1-2 border points: average radius about the centre
                P = (np.asarray(site.rim_points, float) - origin) @ frame
                human_rim_r = float(np.mean(np.linalg.norm(
                    P[:, :2] - seed_local[:2], axis=1)))
        elif marks is not None:
            seed_local = marks.mean(axis=0)
            seed_source = "brush"
        else:
            seed_local = frame.T @ (np.asarray(site.center, float) - origin)
            seed_source = "click"
        # measured rim: sizes the auto-brush crop AND classifies the variant later; the
        # human's wide-end mark overrides the estimator for the crop/seat radius
        measured_dia = measure_rim_diameter(L, xy_tree, seed_local)
        seat_rim_r = human_rim_r if human_rim_r else (measured_dia / 2.0
                                                      if measured_dia else None)

        # AUTO-BRUSH: crop the cap's exposed surface around the seed from the SCAN —
        # the patch a full brush stroke would have painted
        patch = _cap_patch_roi(L, seed_local[:2], rim_radius_mm=seat_rim_r)
        if patch is None and marks is not None and len(marks) >= 60:
            # no crop-able cap around the seed but the operator painted a DENSE patch —
            # trust their surface directly
            patch = marks
        if patch is None:
            # sparse/edge site — fall back to the scan-body isolator's ROI
            fallback = engine.localize_from_seed(L, seed_local, normals=Ln)
            patch = (np.asarray(fallback.roi_points, float)
                     if fallback is not None else None)
        if patch is not None:
            centroid = patch.mean(axis=0)
            base = centroid.copy()
            base[2] = float(patch[:, 2].min())
            loc = engine.Localization(centroid=centroid,
                                      axis=np.array([0.0, 0.0, 1.0]),
                                      base_point=base, roi_points=patch)
        else:
            loc = None
        if loc is None:
            site_rows.append({"tooth": site.tooth, "error": "no surface at confirmed site"})
            continue

        # VARIANT GUIDE: classify the measured rim against the library's dimension table —
        # a confident class narrows registration to its variants (both collar heights);
        # an ambiguous measurement refuses and all variants stay in play
        dia_class = (classify_diameter(measured_dia, variant_table)
                     if measured_dia is not None and variant_table else None)
        # the DOCTOR'S CHOICE drives alignment (RealGUIDE-parity flow): a declared variant
        # that exists in the library IS the template — the measured rim stays the
        # independent second opinion (variant_flags cross-checks it against the class)
        declared_spec = next((sp for sp in library.specs
                              if sp.variant == site.declared_variant), None)
        if declared_spec is not None:
            candidate_specs = [declared_spec]
        else:
            # AUTO mode: every variant competes on the symmetric seat score. The visible
            # rim UNDERESTIMATES native size on submerged caps (measured: -2.1mm), so a
            # hard class restriction excluded the true variant (blind test: the labeled
            # 7030 never even ranked). dia_class stays as a reported signal only.
            candidate_specs = library.specs

        def _best_fit(fit_loc):
            # best template by scan-coverage (picks the collar height within the class;
            # whole-CAD fitness is structurally low on partially-visible caps). loc.axis
            # is a genuine clinical prior (crowns-up), so the accepted basin is bounded
            # to the plausible seating cone (sideways/flipped is impossible).
            found = None
            for spec_ in candidate_specs:
                transform, conf = engine.register(fit_loc, library.template(spec_),
                                                  Retention.CEMENT, axis_bound_deg=45.0,
                                                  rng=rng)
                sampled = sample_surface(rng, library.template(spec_), 2500)
                world_t = (sampled @ transform.rotation.T
                           + transform.translation)
                cov_ = float((cKDTree(world_t).query(
                    np.asarray(fit_loc.roi_points, float))[0] < _COVERAGE_TOL_MM).mean())
                if found is None or cov_ > found[2]:
                    found = (spec_, transform.matrix, cov_, float(conf.icp_fitness))
            return found

        # RIM-FIRST SEAT for squat cap libraries: axis + center from the visible rim
        # circle (closed form), depth by 1-D search — nothing left for a trimmed metric
        # to tilt. Falls through to ICP when the rim arc is too partial to trust.
        best = None
        seat_method = "icp"
        seat_pinned = False  # True when the doctor's border circle pinned the depth
        rim_arc_bins = None  # how much of the rim ring the winning seat actually saw
        rim_candidates = []  # (variant, seat residual) for EVERY candidate — billing honesty
        if squat_library and rim_circle_3d is not None:
            # PINNED seat: the doctor's border circle fixes centre/axis/width/depth;
            # candidates only compete on the calibrated score AT that pose. When the
            # border clicks admit TWO circle hypotheses (a suspected outlier click vs
            # a genuinely uneven rim), both are tried and the seat score decides —
            # same variant either way, so identification is untouched.
            pin_fit = None
            rim_pts_local = (np.asarray(site.rim_points, float) - origin) @ frame
            for spec_ in candidate_specs:
                spec_best, spec_rank = None, None
                for circle in rim_circle_3d:
                    seat = _pinned_rim_seat(np.asarray(loc.roi_points, float),
                                            circle, library.template(spec_), rng=rng)
                    if seat is None:
                        continue
                    # THE PIN'S CONTRACT arbitrates between circle hypotheses: every
                    # one of the doctor's ORIGINAL clicks must lie on the posed part
                    # (a click on the flank stays on the part either way; a genuine
                    # ring point floats in air if it was wrongly dropped)
                    tv = (np.asarray(library.template(spec_).vertices, float)
                          @ seat[0][:3, :3].T + seat[0][:3, 3])
                    cmax = float(cKDTree(tv).query(rim_pts_local)[0].max())
                    if cmax >= 0.9:
                        continue  # the pin CONTRACT is broken (a click floats off
                        # the posed part) — this circle hypothesis is wrong for this
                        # spec; without a contract-holding pin the site falls through
                        # to the free rim seat below
                    if spec_rank is None or seat[1] < spec_rank:
                        spec_best, spec_rank = seat, seat[1]
                seat = spec_best
                if seat is None:
                    continue
                rim_candidates.append({"variant": spec_.variant,
                                       "seat_residual_mm": round(float(seat[1]), 3)})
                if pin_fit is None or seat[1] < pin_fit[2]:
                    pin_fit = (spec_, seat[0], seat[1])
            if pin_fit is not None:
                seat_method = "rim"
                seat_pinned = True  # centre/axis/width/DEPTH all from the clicked circle
                rim_arc_bins = 12  # the human circle is complete by construction
                spec_, m, _ = pin_fit
                sampled = sample_surface(rng, library.template(spec_), 2500)
                world_t = sampled @ m[:3, :3].T + m[:3, 3]
                cov = float((cKDTree(world_t).query(
                    np.asarray(loc.roi_points, float))[0] < _COVERAGE_TOL_MM).mean())
                best = (spec_, m, cov, 1.0)  # fitness 1.0: pinned by the human circle
        if best is None and squat_library and seat_rim_r is not None:
            rim_fit = None
            for spec_ in candidate_specs:
                seat = _rim_seat(np.asarray(loc.roi_points, float), seed_local[:2],
                                 seat_rim_r, library.template(spec_),
                                 min_arc_bins=(6 if human_rim_r else 9), rng=rng)
                if seat is None:
                    continue
                rim_candidates.append({"variant": spec_.variant,
                                       "seat_residual_mm": round(float(seat[1]), 3)})
                if rim_fit is None or seat[1] < rim_fit[3]:
                    rim_fit = (spec_, seat[0], seat[2], seat[1])
            if rim_fit is not None:
                seat_method = "rim"
                spec_, m, rim_arc_bins, resid = rim_fit
                sampled = sample_surface(rng, library.template(spec_), 2500)
                world_t = sampled @ m[:3, :3].T + m[:3, 3]
                cov = float((cKDTree(world_t).query(
                    np.asarray(loc.roi_points, float))[0] < _COVERAGE_TOL_MM).mean())
                best = (spec_, m, cov, 1.0)  # fitness 1.0: seated by construction

        if best is None:
            best = _best_fit(loc)
            if best[3] == 0.0:
                # no basin inside the cone — the part may be a TALL scan body (a ball
                # around its top under-constrains it). Retry with the body isolator's ROI
                # before flagging.
                fallback = engine.localize_from_seed(L, seed_local, normals=Ln)
                if fallback is not None:
                    roi_fb = np.asarray(fallback.roi_points, float)
                    base_fb = np.asarray(fallback.centroid, float).copy()
                    base_fb[2] = float(roi_fb[:, 2].min())
                    loc_fb = engine.Localization(centroid=fallback.centroid,
                                                 axis=np.array([0.0, 0.0, 1.0]),
                                                 base_point=base_fb, roi_points=roi_fb)
                    retry = _best_fit(loc_fb)
                    if retry[3] > 0.0:
                        best, loc = retry, loc_fb
        spec, t_local, coverage, fitness = best
        # THE WINNER PASS (pipeline/auto_flow.refine_winner_pose): every polish stage
        # applied to the seat that already won, and to nothing else. Ranking is finished
        # above; nothing below can change WHICH part ships.
        _winner = refine_winner_pose(
            L, np.asarray(loc.roi_points, float), library.template(spec),
            t_local, coverage,
            squat_library=squat_library, seat_method=seat_method,
            seat_pinned=seat_pinned, rim_fit_circle=rim_fit_circle,
            human_rim_r=human_rim_r, seed_xy=seed_local[:2], seat_rim_r=seat_rim_r,
            rng=rng)
        t_local, coverage, clocking_info = (_winner.pose, _winner.coverage,
                                            _winner.clocking)
        roi = np.asarray(loc.roi_points, float)
        rim_candidates.sort(key=lambda c: c["seat_residual_mm"])
        # two variants are INSEPARABLE when their seat residuals differ by less than the
        # larger of 0.05mm or 10% — the scan cannot decide; the doctor must
        candidates_too_close = (len(rim_candidates) >= 2 and
                                (rim_candidates[1]["seat_residual_mm"]
                                 - rim_candidates[0]["seat_residual_mm"])
                                < max(0.05, 0.1 * rim_candidates[0]["seat_residual_mm"]))

        # compose the canonical-template -> jaw-world pose
        pose = np.eye(4)
        pose[:3, :3] = frame @ t_local[:3, :3]
        pose[:3, 3] = origin + frame @ t_local[:3, 3]
        # MISNOMER, kept on the wire deliberately (see the row's alignment_error_mm):
        # this is the distance from the operator's CONFIRMED SITE CENTRE to the shipped
        # POSE ORIGIN — two different things measured in different places. The pose origin
        # is the template's canonical origin, a collar height BELOW the rim the operator
        # clicked on, so a perfect seat still reads ~1-2mm here and the number contains a
        # systematic per-variant offset. It is a sanity check that the pose landed at the
        # right TOOTH, nothing more; it is not a seat-quality measure and must never be
        # read as one. The honest seat numbers are fit.avg_mm/max_mm, rim_agreement_mm,
        # top_face_agreement_mm and auto_delta_mm (which is deliberately compared
        # surface-to-surface for exactly this reason — see its own note below).
        site_origin_offset = float(np.linalg.norm(pose[:3, 3]
                                                  - np.asarray(site.center, float)))

        measurement = measure_site(pts, pose[:3, 3],
                                   _template_radius(library.template(spec)), occ_axis)

        # registration-error stats over the alignment surface (RealGUIDE's Registration
        # Error dialog reports the same avg/max; the max includes screw-recess points,
        # where the template's bore has no surface — same as theirs)
        _fs = sample_surface(rng, library.template(spec), 2500)
        _fw = _fs @ t_local[:3, :3].T + t_local[:3, 3]
        _fd = cKDTree(_fw).query(roi)[0]
        fit_stats = {"avg_mm": float(_fd.mean()), "max_mm": float(_fd.max())}
        # coverage refreshed at the FINAL pose (review 2026-07-20: it was computed at
        # the seat/best-fit pose and went stale through the depth/clock/centre/void
        # winner passes, which move the pose by up to ~2mm — every other read-out here
        # already uses the final t_local). Reuses _fd: zero extra RNG draws, so the
        # pinned-seed stream feeding later stages is untouched.
        coverage = float((_fd < _COVERAGE_TOL_MM).mean())

        # how much of the CAP'S OWN surface the seated part explains (client ask
        # 2026-07-14: 'how much of the surface we have aligned and covered'): unlike
        # raw ROI coverage — which counts surrounding gingiva no cap can explain and
        # misled a doctor at '41%' — this is measured only over scan points inside the
        # part's own footprint around its axis
        _ax = t_local[:3, :3] @ np.array([0.0, 0.0, 1.0])
        _rel = roi - t_local[:3, 3]
        _radial = np.linalg.norm(_rel - np.outer(_rel @ _ax, _ax), axis=1)
        _cap_pts = roi[_radial < _template_radius(library.template(spec)) + 0.3]
        cap_explained_pct = (round(float(
            (cKDTree(_fw).query(_cap_pts)[0] < _COVERAGE_TOL_MM).mean()) * 100.0, 1)
            if len(_cap_pts) >= 20 else None)

        # rim agreement (mm): the alignment number the doctor can visually judge —
        # coverage % counts unexplainable gingiva and misreads as "bad" on good seats
        rim_agreement = None
        if squat_library:
            if rim_fit_circle is not None:
                _ac, _ar = rim_fit_circle
            elif human_rim_r:
                _ac, _ar = seed_local[:2], float(human_rim_r)
            elif seat_rim_r:
                _ac, _ar = seed_local[:2], float(seat_rim_r)
            else:
                _ac = None
            if _ac is not None:
                rim_agreement = _rim_agreement_mm(L, _ac, _ar,
                                                  library.template(spec), t_local)
        # TOP-FACE agreement: distance of the posed part's top face to the scan. The band
        # and tilt are blind to a slide along a straight wall — this is the read-out that
        # sees it (healthy fleet mean 0.16-0.59; ride-high failures 1.96/2.45). Reported as
        # the MEAN (the reassuring headline number), but the GATE acts on the P90 — the
        # same measure the physical-bounds guard uses (bar 1.5). A part that RIDES OFF ON
        # ONE SIDE reads a low mean but a high p90 (measured on a t7 gesture: mean 1.45,
        # p90 2.32); gating on the mean let the centering pass drop the mean under 1.5 and
        # present READY while the part still rode off — so the gate must see the p90 too.
        top_face_agreement = None   # mean, reported
        top_face_p90 = None         # ride-off measure, drives the gate (matches the guard)
        if squat_library:
            _tvf = np.asarray(library.template(spec).vertices, float)
            _topf = _tvf[_tvf[:, 2] > _tvf[:, 2].max() - 1.2]
            if len(_topf) > 400:
                _topf = _topf[np.linspace(0, len(_topf) - 1, 400).astype(int)]
            if len(_topf) >= 30:
                _topfw = _topf @ t_local[:3, :3].T + t_local[:3, 3]
                _topfd = cKDTree(L).query(_topfw)[0]
                top_face_agreement = float(_topfd.mean())
                top_face_p90 = float(np.percentile(_topfd, 90))

        # CONFIDENCE (Spec A, opt-in): how stable is this seat under plausible click error?
        # Re-seat the winner K times with the marks jittered by click noise; grade the pose
        # spread together with the fit residuals (rim + top-face — so a STABLE-but-WRONG seat
        # is still caught by the fit signals, not read as confident). READ-ONLY, advisory:
        # the thresholds are preliminary (pending an operator FLE study) and do NOT drive
        # auto-pass. A local per-tooth RNG keeps it deterministic without touching the global
        # seed the pipeline pins. See domain/pose_confidence.py.
        confidence = None
        if compute_confidence and squat_library:
            # per-tooth seeds: the same site always grades the same, and the probe
            # never touches the run's own stream (see _pose_stability_bootstrap)
            _boot_seed = abs(int(site.tooth)) % 100000
            boot = _pose_stability_bootstrap(
                L, site, frame, origin, library.template(spec),
                np.random.default_rng(_boot_seed),
                sample_rng=PipelineRng(seed=_boot_seed))
            if boot is not None:
                spread = pose_spread(boot[0], boot[1])
                confidence = {
                    "grade": confidence_grade(
                        spread, rim_agreement_mm=rim_agreement,
                        top_face_p90_mm=top_face_p90,
                        candidates_too_close=candidates_too_close,
                        border_disagree_mm=border_disagreement, tre_mm=None),
                    "pose_pos_spread_mm": round(spread.pos_p90_mm, 2),
                    "pose_axis_spread_deg": round(spread.axis_p90_deg, 1),
                }

        package_sites.append((
            SitePackageSpec(tooth=site.tooth, implant_model=spec.model,
                            variant_code=spec.variant, vendor=vendor,
                            pose_matrix=pose, scan_coverage=coverage, advisory=True,
                            pose_origin="component"),
            library.template(spec), construction_mesh))
        # the winner pose is final for this site — stash the shadow-island inputs
        # (reuses L and the cached template; the measurement itself runs after the loop)
        shadow_inputs.append((site.tooth, seed_local[:2].copy(), seat_rim_r,
                              t_local.copy(), library.template(spec)))
        # the billing/clinical gate: declared vs identified must agree, and an ambiguous
        # measurement is said out loud rather than silently guessed. A rim-seated part
        # matching the declaration turns the smaller-visible-rim reading into the
        # EXPECTED submergence note instead of a false-alarm dispute.
        seat_confirms = (seat_method == "rim"
                         and site.declared_variant == spec.variant)
        flags = variant_flags(site.declared_variant, spec.variant, measured_dia,
                              dia_class, len(variant_table),
                              seat_confirms_declared=seat_confirms)
        submergence_expected = (
            seat_confirms and site.declared_variant is not None
            and dia_class is not None
            and site.declared_variant not in dia_class.variants
            and all(site.declared_variant > v for v in dia_class.variants))
        if fitness == 0.0:
            # the engine found no basin inside the plausible seating cone (register()
            # zeroes fitness on an axis-constraint violation) — say it out loud
            flags = list(flags) + [
                "registration could not seat the cap within the plausible axis cone "
                "- manual review required"]

        # the COMPARE: how far the HUMAN's site reference (painted-patch centroid, or the
        # confirmed click) sits from the automation's nearest proposal. Like-for-like: both
        # are scan-surface site centers — NOT the component pose origin, which sits a collar
        # height below the rim and would bake a constant bias into the number. A centre
        # mark is reported at its SNAPPED seed (the seat ignores the raycast depth — the
        # delta must not re-import it).
        human_ref = (frame @ seed_local + origin
                     if site.center_mark is not None
                     else np.asarray(site.marked_points, float).mean(axis=0)
                     if site.marked_points else np.asarray(site.center, float))
        auto_delta = (min(float(np.linalg.norm(human_ref - np.asarray(pp, float)))
                          for pp in proposals) if proposals else None)

        # RIM CENTRING at reporting time (panel-completion, master plan §8 item 12):
        # the scoreboard's marks-anchored construction mirrored into the row itself, so
        # the verification panel's rim_off_centre_mm stops reading "missing". None when
        # the centre+rim mark pair is absent — the metric is marks-anchored by design
        # (it must not be fed by the pose it judges). REPORTING ONLY.
        rim_off_centre = None
        if site.center_mark is not None and site.rim_mark is not None:
            rim_off_centre = _rim_off_centre_mm(
                L, frame.T @ (np.asarray(site.center_mark, float) - origin),
                frame.T @ (np.asarray(site.rim_mark, float) - origin),
                library.template(spec), t_local)

        site_rows.append({
            "tooth": site.tooth, "spec": spec.label, "vendor": vendor,
            "seed_source": seed_source,
            "auto_delta_mm": auto_delta,
            "coverage": coverage, "icp_fitness": fitness,
            "fit": fit_stats,
            "seat_method": seat_method,
            "rim_arc_bins": rim_arc_bins,  # 12 = full ring visible; None on icp seats
            "rim_agreement_mm": (round(rim_agreement, 2)
                                 if rim_agreement is not None else None),
            # posed rim-circle centre vs the marks-anchored scanned rim band (occlusal
            # mm) — the scoreboard's construction, now IN the row for the panel; None
            # without a centre+rim mark pair (see _rim_off_centre_mm)
            "rim_off_centre": (round(rim_off_centre, 3)
                               if rim_off_centre is not None else None),
            # max leave-one-out plane distance over the doctor's border clicks (n>=4)
            # — the Copy-run-report loop's answer to "why did this seat tilt": ~0.3 is
            # click noise, ~0.9 is one click past the rim edge (guidance names it too)
            "border_click_disagreement_mm": (round(border_disagreement, 2)
                                             if border_disagreement is not None
                                             else None),
            # mean top-face->scan distance — the depth read-out (see its computation)
            "confidence": confidence,  # {grade, pose spreads} or None (opt-in / non-cap)
            "top_face_agreement_mm": (round(top_face_agreement, 2)
                                      if top_face_agreement is not None else None),
            "cap_surface_explained_pct": cap_explained_pct,
            # coded-cutout clock instrument (None on icp seats): shift/corr/prominence,
            # which instrument anchored the rotation, and the cross-instrument check
            "clocking": clocking_info,
            "guidance": advisory_guidance(
                seat_method=seat_method,
                fit_avg_mm=fit_stats["avg_mm"], fit_max_mm=fit_stats["max_mm"],
                declared=site.declared_variant,
                dia_class_confident=dia_class is not None,
                measurement_disputes_declared=(
                    site.declared_variant is not None and dia_class is not None
                    and site.declared_variant not in dia_class.variants
                    and not submergence_expected),
                variant_ambiguous=(measured_dia is not None and dia_class is None
                                   and len(variant_table) > 1),
                axis_violation=(fitness == 0.0),
                seed_source=seed_source,
                candidates_too_close=candidates_too_close,
                border_points_given=bool(site.rim_points
                                         and len(site.rim_points) >= 3),
                border_clicks_disagree_mm=border_disagreement,
                top_face_off_mm=top_face_p90,
                rotation_unverified=bool(clocking_info
                                         and clocking_info["rotation_unverified"]),
                # METRIC HONESTY (master plan slice, 2026-07-23): when the rotation is
                # CODE-VERIFIED (codes evidence + confirm re-read <=12 deg), the
                # codes-vs-recess disagreement is the recess azimuth's PHANTOM-CONVICTED
                # bias (a partially visible dip skews its centroid), not a pose defect —
                # routing those sites to "attention" over-warned 5 verified seats. The
                # disagreement stays in the row (clocking.consistency_deg) as data; it
                # drives attention only when the rotation is NOT verified.
                clock_consistency_deg=(
                    clocking_info.get("consistency_deg")
                    if clocking_info and not (
                        str(clocking_info.get("evidence", "")).startswith("codes")
                        and not clocking_info.get("rotation_unverified")
                        and clocking_info.get("notch_shift_deg") is not None
                        and abs(clocking_info["notch_shift_deg"]) <= 12.0)
                    else None)),
            # NAME IS A MISNOMER — |confirmed site centre - pose ORIGIN|, which sits a
            # collar height below the clicked rim, so a perfect seat still reads 1-2mm.
            # A tooth-identity sanity check, NOT a seat-quality number (fit.avg_mm,
            # rim_agreement_mm and top_face_agreement_mm are those). The KEY is kept as
            # shipped: the web renders it under this name today, and renaming a live wire
            # field mid-flight would break the panel for a cosmetic gain. Rename it on
            # both sides in one coordinated change — `site_origin_offset_mm`.
            "alignment_error_mm": site_origin_offset,
            "variant": {
                "identified": spec.variant,
                "declared": site.declared_variant,
                "measured_rim_diameter_mm": measured_dia,
                "diameter_class_margin_mm": (dia_class.margin_mm if dia_class else None),
                "flags": flags,
                "candidates": rim_candidates or None,
                # SURFACED (slice 4, master plan §8 item 12): the inseparable-variants
                # verdict was computed here and consumed only by guidance — an invisible
                # high-blocker. Now a row fact: True = the scan cannot separate the top
                # two size candidates; the doctor's declaration decides.
                "candidates_too_close": bool(candidates_too_close),
            },
            "advisory": True,  # real data class: always routed to human review
            "site_measurement": {
                "md_span_mm": measurement.md_span_mm,
                "gap_mesial_mm": measurement.gap_mesial_mm,
                "gap_distal_mm": measurement.gap_distal_mm,
                "classification": measurement.classification,
                "terminal_site": measurement.terminal_site,
            },
        })

    if not package_sites:
        raise ValueError("no confirmed site could be aligned — nothing to package")

    # OUR OWN EXPORT (no external CAD handoff): the final product per site = the vendor
    # construction part with the screw channel bored along the implant axis; the emitter
    # poses it into the jaw frame and writes the production set
    final_products = None
    # the relief actually cut per variant/tooth, next to the one the lab asked for —
    # empty when no production set is generated (nothing was cut, so nothing is claimed)
    _clamp_by_variant: Dict[tuple, "ReliefClamp"] = {}
    _clamp_by_tooth: Dict[int, "ReliefClamp"] = {}
    if generate_product:
        # G1 WIRING (2026-07-23): each site's product is bored at ITS identified cap's
        # LOOP-TRUTH channel (domain.channel), so the delivered screw channel lands in
        # world exactly where the cap CAD says the screw goes — measured miss collapses
        # 0.34-0.38mm -> 0.001-0.018mm. Built per distinct variant (the channel differs
        # per cap); sites sharing a variant share the product.
        # PER-SITE RELIEF (§10-B/C, 2026-08-04): each site's ask is its own
        # override where one stands, else the case-level value — and because two
        # sites can now share a variant while asking different reliefs, the
        # shared-product cache keys on (variant, ask) rather than variant alone.
        _site_offsets = site_gingival_offsets or {}

        def _relief_ask(tooth: int) -> float:
            return float(_site_offsets.get(tooth, gingival_offset_mm))

        _product_by_variant: Dict[tuple, trimesh.Trimesh] = {}
        final_products = {}
        for spec, _, _ in package_sites:
            _key = (spec.variant_code, _relief_ask(spec.tooth))
            if _key not in _product_by_variant:
                _cap_spec = next((s for s in library.specs
                                  if s.variant == spec.variant_code), None)
                _chan = (channel_from_boundary_loops(library.template(_cap_spec))
                         if _cap_spec is not None else None)
                # THE RELIEF CEILING, ASKED BEFORE THE CUT (2026-07-25, client escalation
                # "end-to-end automation must complete"). The requested relief is a
                # PROPOSAL: this pair (construction part x identified cap) is measured for
                # the largest relief the export gate will still emit, and the part is cut
                # at min(requested, ceiling). MEASURED RECEIPTS on the real catalog, all 24
                # (construction x cap) pairs at the client's 0.20mm default: 15 cannot take
                # it. Every atlantis/zimmer-4.5-scanbody pair tops out at 0.06-0.15mm (the
                # client's own tooth-3 refusal, atlantis x neodent-gm 5030, ceilings at
                # 0.06); on dess/neodent-gm-scanbody the CAP SIZE decides — 5020 ceilings at
                # 0.05 and 5030 at 0.09 while 6020/6030 take 0.43/0.47. The driver is cap
                # size, not vendor. The gate itself is untouched and still blocks a part
                # that fails even at 0.0 — this refuses the ASK and completes at the safe
                # value, loudly (see the clamp trio on every row/audit below).
                _clamp_by_variant[_key] = resolve_gingival_offset(
                    construction_mesh, _relief_ask(spec.tooth),
                    library_channel=_chan,
                    screw_radius_mm=screw_radius_mm,
                    part_label=(f"{spec.vendor}/{spec.implant_model} "
                                f"{spec.variant_code}"))
                _product_by_variant[_key] = build_final_product(
                    construction_mesh, screw_radius_mm=screw_radius_mm,
                    library_channel=_chan,
                    gingival_offset_mm=_clamp_by_variant[_key].applied_mm)
            final_products[spec.tooth] = _product_by_variant[_key]
            _clamp_by_tooth[spec.tooth] = _clamp_by_variant[_key]
        # HONESTY (review M1): ONE construction part serves every site — when sites identify
        # DIFFERENT size variants, the shared product geometry cannot match all of them
        distinct = {spec.variant_code for spec, _, _ in package_sites}
        shared_note = (f"single construction part shared across sites identifying "
                       f"{len(distinct)} distinct variants — per-variant construction "
                       f"parts needed" if len(distinct) > 1 else None)
        for row in site_rows:
            if "spec" in row:
                _cl = _clamp_by_tooth.get(row["tooth"])
                row["production"] = {
                    "screw_channel_radius_mm": float(screw_radius_mm),
                    # the tissue clearance this part was actually cut with (client value
                    # 0.20, 2026-07-25) — a row fact, never re-derived downstream. It is
                    # the APPLIED value: when the pair could not take the ask, the trio
                    # below says so rather than this key quietly meaning two things.
                    "gingival_offset_mm": float(_cl.applied_mm if _cl is not None
                                                else _relief_ask(row["tooth"])),
                    **(_cl.as_json() if _cl is not None else {}),
                }
                if shared_note:
                    row["production"]["note"] = shared_note
                # ...and what the relief MEASURES on the delivered part, straight from
                # build_final_product's own read (2026-07-25) — a ROW fact next to
                # clocking/nudge, because the requested figure alone overstates the
                # patient's clearance (0.20 asked, ~0.13-0.15 achieved on the real vendor
                # parts). None when no relief was applied: nothing was measured, and the
                # row says so rather than reporting a 0.0 nobody measured.
                _product = final_products.get(row["tooth"])
                row["gingival_offset"] = (
                    (_product.metadata.get("gingival_offset") or {}).get("achieved")
                    if _product is not None else None)
        # DELIVERED-CHANNEL row fields (panel-completion, master plan §8 item 12): the
        # G3 measurement — previously scoreboard-only, so the panel's
        # delivered_channel_vs_recess_mm read "missing" on every run — now measured on
        # the product each site actually ships, via the SHARED instrument
        # (delivered_channel_offsets; the scoreboard imports it back). The pipeline
        # passes the pre-pose product mesh — the same geometry the scoreboard reads
        # from the emitted STL after un-posing. REPORTING ONLY; None-safe throughout.
        _pkg_by_tooth = {sp.tooth: (sp, tmpl) for sp, tmpl, _ in package_sites}
        for row in site_rows:
            entry = _pkg_by_tooth.get(row.get("tooth"))
            if entry is None or "spec" not in row:
                continue
            _sp, _tmpl = entry
            row.update(delivered_channel_offsets(
                final_products[_sp.tooth], _sp.pose_matrix, frame, origin, L, _tmpl))

    audit_by_tooth = {r["tooth"]: {"fit": r["fit"], "seed_source": r["seed_source"],
                                   "seat_method": r["seat_method"],
                                   "guidance_level": r["guidance"]["level"],
                                   "declared_variant": r["variant"]["declared"],
                                   "identified_variant": r["variant"]["identified"],
                                   "candidates": r["variant"]["candidates"],
                                   # the relief the shipped part was cut with travels WITH
                                   # the paid record (client value 0.20, 2026-07-25) —
                                   # None when no production set was generated. When the
                                   # pair could not take the ask, the requested/applied/
                                   # clamped/clamp_reason quartet rides in the SAME audit
                                   # block: a lab reading the paid record must never have
                                   # to infer that it got a different number than it asked
                                   # for (2026-07-25 clamp).
                                   "gingival_offset_mm": (
                                       float(_clamp_by_tooth[r["tooth"]].applied_mm)
                                       if r["tooth"] in _clamp_by_tooth
                                       else (float((site_gingival_offsets or {})
                                                   .get(r["tooth"],
                                                        gingival_offset_mm))
                                             if generate_product else None)),
                                   **(_clamp_by_tooth[r["tooth"]].as_json()
                                      if r["tooth"] in _clamp_by_tooth else {})}
                      for r in site_rows if "error" not in r}
    # SHADOW ISLAND MEASUREMENT (master plan slice 6) — the machine-segmented island
    # reported NEXT TO the shipped numbers, changing nothing. Runs after every winner
    # pose above is final and is consumed by no downstream stage. Global RNG state is
    # saved/restored around it (the template_signature guard pattern — measured hazard,
    # review 2026-07-20) even though segment_island itself draws nothing, so the pinned
    # stream feeding QC render / emission below is untouched by construction.
    if SHADOW_ISLAND:
        _rows_by_tooth = {r["tooth"]: r for r in site_rows if "error" not in r}
        _rng_state = np.random.get_state()
        try:
            for _tooth, _seed_xy, _rim_hint, _t_loc, _tmpl in shadow_inputs:
                _row = _rows_by_tooth.get(_tooth)
                if _row is None:
                    continue
                try:
                    _reading = segment_island(L, _seed_xy, radius_hint=_rim_hint)
                except Exception as exc:  # a shadow must never take down a case run
                    _row["island"] = {"converged": False,
                                      "reason": f"error: {exc}"}
                    _row.update(_machine_qa_twins(L, None, _tmpl, _t_loc))
                    continue
                # MACHINE-ANCHORED QA twins (slices 14-15): rim agreement + rim
                # centring re-anchored to the machine ring this reading just measured
                # — the dual-report next to the click-anchored numbers above. Rides
                # the shadow (same revertibility flag, same RNG-state guard); the
                # island reading is REUSED, never re-segmented.
                _row.update(_machine_qa_twins(L, _reading, _tmpl, _t_loc))
                if not _reading.converged:
                    _row["island"] = {"converged": False, "reason": _reading.reason}
                    continue
                # machine centre vs the SHIPPED pose's rim-circle centre (occlusal mm)
                _posed_c = _posed_rim_centre(_tmpl, _t_loc)
                _off = (float(np.linalg.norm(
                    np.asarray(_reading.centre_xy) - _posed_c))
                    if _posed_c is not None else None)
                _row["island"] = {
                    "machine_centre_offset_mm": (round(_off, 3)
                                                 if _off is not None else None),
                    "radius": round(float(_reading.radius), 3),
                    "converged": True,
                    "bins_hit": _reading.bins_hit,
                    "contamination_est": (round(_reading.contamination_est, 3)
                                          if _reading.contamination_est is not None
                                          else None),
                    # P2.2 — per-bearing DP confidence (additive; pre-field records omit these)
                    "dp_gap_fraction": (round(float(_reading.dp_gap_fraction), 4)
                                        if _reading.dp_gap_fraction is not None
                                        else None),
                    "bearing_margin": ([round(float(x), 4) for x in _reading.bearing_margin]
                                       if _reading.bearing_margin is not None
                                       else None),
                }
        finally:
            np.random.set_state(_rng_state)

    # QC ACCEPTANCE ARTIFACTS (per site: clock view + signed difference map) — the
    # renders a lab tech accepts by. REPORTING ONLY, computed at the shipped pose;
    # written before emission so the hashed manifest covers them like any deliverable.
    # The deviation SCALARS (RMS/p90 over the cap footprint) land in the row either
    # way (panel-completion, master plan §8 item 12): the render call returns the
    # stats it printed; render_qc=False computes them via the shared stats function
    # WITHOUT rendering (site_deviation_stats — RNG-state-safe, same math).
    qc_paths: List[Path] = []
    _rows_by_tooth_qc = {r["tooth"]: r for r in site_rows if "error" not in r}

    def _stash_deviation(row, stats) -> None:
        if row is None:
            return
        row["deviation_rms_mm"] = (round(float(stats["rms_mm"]), 3)
                                   if stats.get("rms_mm") is not None else None)
        row["deviation_p90_mm"] = (round(float(stats["p90_mm"]), 3)
                                   if stats.get("p90_mm") is not None else None)

    if render_qc:
        from case_prep.adapters.qc_render import render_site_qc
        clocking_by_tooth = {r["tooth"]: r.get("clocking")
                             for r in site_rows if "error" not in r}
        for _sp, _tmpl, _cons in package_sites:
            _paths, _dev_stats = render_site_qc(
                case_id, _sp.tooth, pts, _sp.pose_matrix, _tmpl,
                clocking_by_tooth.get(_sp.tooth), out_dir)
            qc_paths.extend(_paths)
            _stash_deviation(_rows_by_tooth_qc.get(_sp.tooth), _dev_stats)
    else:
        from case_prep.adapters.qc_render import site_deviation_stats
        for _sp, _tmpl, _cons in package_sites:
            _stash_deviation(_rows_by_tooth_qc.get(_sp.tooth),
                             site_deviation_stats(pts, _sp.pose_matrix, _tmpl))
    # The per-site package stays even on a preview: it is small, and the preview
    # endpoint READS the pose back out of its implant.json.
    manifest = emit_case_package(case_id, scan, jaw_label, package_sites, out_dir,
                                 final_product_mesh=final_products,
                                 audit_by_tooth=audit_by_tooth,
                                 extra_files=qc_paths or None,
                                 include_scan_layer=emit_package,
                                 overlay=emit_package)

    # ARCH DELIVERABLES ARE NOT PREVIEW MATERIAL (verification 2026-07-26): the
    # auto-fire preview behind the verify view wrote the whole arch STL trio AND a
    # 45MB base64-inlined view.html on every variant change — MEASURED 124MB per
    # preview into an unpruned directory. A preview needs a pose, not a deliverable.
    if emit_package:
            # ARCH-LEVEL DELIVERABLES (client spec 2026-07-11): (2) the WHOLE arch with the aligned
            # healing caps covering the scanned gaps; (3) the arch with the scanned cap regions
            # REMOVED and the constructions in their place. (Composites; not yet in the hashed
            # manifest — fold into the emitter when the trio is confirmed final.)
            from pathlib import Path as _P
            dims = library.variant_dimensions()
            # ARTIFACT FACTS FOR THE COMPOSITES (boolean-engine plan 4c): every mesh
            # below is already in memory the instant it is written, so its facts are
            # computed HERE, straight off that mesh — never a reload of the STL this
            # same lane just wrote. Keyed by bare name and handed to
            # ``register_package_files`` alongside the paths it re-hashes.
            composite_facts: Dict[str, MeshFacts] = {}

            # THE SEAT IS THE CAP'S OWN IMPRINT (§10-AO, client 2026-08-06): each
            # hole is the healing cap's dilated surface — its exact footprint plus
            # the relief this run applied — floored by the cap's own offset base.
            # The cylinder socket survives only as the per-site fallback, noted on
            # the site's own row. BUILT BEFORE THE FUSED COMPOSITES BELOW (moved
            # here, DEFECT 1 EXCISION slice, client-ruled 2026-08-15): the fused
            # healing-cap composite needs each site's own catalog rim radius to
            # excise the scanned cap's crust, and this loop is the one place that
            # radius is already derived.
            imprint_sites = []
            for sp, tmpl, _c in package_sites:
                dia_h = dims.get(sp.variant_code)
                if dia_h is None:
                    # no catalog dims for this variant — derive the fallback radius from the
                    # template's own canonical geometry (bore on +z) rather than guessing a constant
                    ext = tmpl.bounds[1] - tmpl.bounds[0]
                    dia_h = (float(max(ext[0], ext[1])), float(ext[2]))
                row = _rows_by_tooth_qc.get(sp.tooth) or {}
                applied = row.get("gingival_offset_applied_mm")
                offset = (float(applied) if isinstance(applied, (int, float))
                          else float((site_gingival_offsets or {}).get(
                              sp.tooth, gingival_offset_mm)))
                imprint_sites.append((tmpl, sp.pose_matrix, offset,
                                      float(dia_h[0]) / 2.0))

            caps_posed = [(tmpl, sp.pose_matrix) for sp, tmpl, _ in package_sites]
            # DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15): the
            # SAME templates/poses ``caps_posed`` already carries, plus each
            # site's own catalog rim radius (``imprint_sites``' own 4th element,
            # same order) — "white patches poking through the library cap" was
            # this exact composite's symptom, and the part's own posed surface
            # must replace the scanned cap's crust, never merge with it.
            caps_excise_sites = [(tmpl, sp.pose_matrix, rim_r)
                                 for (sp, tmpl, _c), (_t, _p, _o, rim_r)
                                 in zip(package_sites, imprint_sites)]
            arch_caps, caps_composite_notes = arch_with_parts_fused(
                scan, caps_posed, excise_sites=caps_excise_sites)
            arch_caps_path = _P(out_dir) / f"{case_id}-arch-with-healingcaps.stl"
            arch_caps.export(arch_caps_path)
            composite_facts[arch_caps_path.name] = facts_of(arch_caps)
            for note in caps_composite_notes:
                # "part N …" — N is 1-based caps_posed/package_sites order; land it
                # on that row. A WHOLE-COMPOSITE note (the fail-open fallback,
                # §10-AT 3b — no "part " prefix) lands on every row: the
                # degradation covered all of them.
                if note.startswith("part "):
                    teeth = [package_sites[int(note.split()[1]) - 1][0].tooth]
                else:
                    teeth = [sp.tooth for sp, _t, _c in package_sites]
                for tooth in teeth:
                    target = _rows_by_tooth_qc.get(tooth)
                    if target is not None:
                        target.setdefault("production", {})[
                            "composite_note"] = note

            # SCANNED-CAP ISOLATION (clinical pipeline plan Stage 2 slice 2a, boolean
            # plan 4d): per site, exactly what the scanner saw of the healing cap —
            # cylinder pre-cut at the catalog rim, template-matched band, core-keep
            # for the scanned screw-recess void the template can never cover (§10-AT
            # front 1 corrected). Whole triangles from the scan's own bytes; nothing
            # moved, nothing inferred. A pathological pose that catches nothing skips
            # emission and lands a per-site note instead of an empty file, the same
            # honesty rule the imprint/composite notes below already carry.
            scanned_cap_names: List[str] = []
            for _index, ((_sp, _tmpl, _c), (_t, _pose, _offset, _rim_r)) in enumerate(
                    zip(package_sites, imprint_sites), 1):
                _isolated = isolate_scanned_cap(scan, _tmpl, _pose, _rim_r)
                if _isolated is None:
                    _target = _rows_by_tooth_qc.get(_sp.tooth)
                    if _target is not None:
                        _target.setdefault("production", {})["scanned_cap_note"] = (
                            f"site {_index}: the scanned-cap isolation caught nothing "
                            "at this pose — the artifact was not emitted")
                    continue
                _scanned_cap_path = (_P(out_dir)
                                     / f"{case_id}-{_sp.tooth}-scanned-cap.stl")
                _isolated.export(_scanned_cap_path)
                register_package_files(
                    manifest.path, [_scanned_cap_path],
                    facts_by_name={_scanned_cap_path.name: facts_of(_isolated)})
                scanned_cap_names.append(_scanned_cap_path.name)

            arch_socketless, socket_dish, imprint_notes = cap_imprint_parts(
                scan, imprint_sites)
            arch_removed = (trimesh.util.concatenate(
                [arch_socketless, socket_dish])
                if socket_dish is not None else arch_socketless)
            for note in imprint_notes:
                # "site N: …" lands on that row; a WHOLE-CARVE note (the CSG
                # route's fallback sentence, §10-AS.12 — no site prefix)
                # lands on every row: the degradation covered all of them
                if note.startswith("site "):
                    teeth = [package_sites[
                        int(note.split(":", 1)[0].split()[1]) - 1][0].tooth]
                else:
                    teeth = [sp.tooth for sp, _t, _c in package_sites]
                for tooth in teeth:
                    target = _rows_by_tooth_qc.get(tooth)
                    if target is not None:
                        target.setdefault("production", {})[
                            "imprint_note"] = note
            arch_capless_path = _P(out_dir) / f"{case_id}-arch-capless.stl"
            arch_removed.export(arch_capless_path)
            composite_facts[arch_capless_path.name] = facts_of(arch_removed)
            # THE FIFTH ARTIFACT (client 2026-08-09): the platform socket —
            # and both sockets as their own layer files for the tinted preview
            _, socket_platform, _pn = cap_imprint_parts(scan, imprint_sites,
                                                        top_floor=True)
            arch_platform = (trimesh.util.concatenate(
                [arch_socketless, socket_platform])
                if socket_platform is not None else arch_socketless)
            (_P(out_dir) / f"{case_id}-arch-platform.stl").write_bytes(
                arch_platform.export(file_type="stl"))
            composite_facts[f"{case_id}-arch-platform.stl"] = facts_of(arch_platform)
            (_P(out_dir) / f"{case_id}-arch-socketless.stl").write_bytes(
                arch_socketless.export(file_type="stl"))
            composite_facts[f"{case_id}-arch-socketless.stl"] = facts_of(arch_socketless)
            _layer_names = [f"{case_id}-arch-socketless.stl"]
            if socket_dish is not None:
                (_P(out_dir) / f"{case_id}-socket-dish.stl").write_bytes(
                    socket_dish.export(file_type="stl"))
                composite_facts[f"{case_id}-socket-dish.stl"] = facts_of(socket_dish)
                _layer_names.append(f"{case_id}-socket-dish.stl")
            if socket_platform is not None:
                (_P(out_dir) / f"{case_id}-socket-platform.stl").write_bytes(
                    socket_platform.export(file_type="stl"))
                composite_facts[f"{case_id}-socket-platform.stl"] = facts_of(socket_platform)
                _layer_names.append(f"{case_id}-socket-platform.stl")

            # ARTIFACT 6, THE THIRD RULING (client-ruled, 2026-08-15): the closed
            # model retires AGAIN — "just the open scan, and the hole viewed like
            # it is" — replaced by the open arch wearing each cap's exact
            # THROUGH-hole, no backfilled body.
            _model_closed, _model_notes = open_arch_with_through_holes(
                scan, imprint_sites)
            if _model_closed is not None:
                (_P(out_dir) / f"{case_id}-arch-open-holes.stl").write_bytes(
                    _model_closed.export(file_type="stl"))
                composite_facts[f"{case_id}-arch-open-holes.stl"] = facts_of(_model_closed)
                _layer_names.append(f"{case_id}-arch-open-holes.stl")
            for _note in _model_notes:
                if _note.startswith("site "):
                    _teeth = [package_sites[
                        int(_note.split(":", 1)[0].split()[1]) - 1][0].tooth]
                else:
                    _teeth = [sp.tooth for sp, _t, _c in package_sites]
                for _tooth in _teeth:
                    _target = _rows_by_tooth_qc.get(_tooth)
                    if _target is not None:
                        _target.setdefault("production", {})[
                            "model_note"] = _note
            cons_posed = [(final_products[sp.tooth] if final_products else cons, sp.pose_matrix)
                          for sp, _t, cons in package_sites]
            arch_cons, cons_composite_notes = arch_with_parts_fused(
                arch_removed, cons_posed)
            arch_cons_path = _P(out_dir) / f"{case_id}-arch-with-constructions.stl"
            arch_cons.export(arch_cons_path)
            composite_facts[arch_cons_path.name] = facts_of(arch_cons)
            for note in cons_composite_notes:
                if note.startswith("part "):
                    teeth = [package_sites[int(note.split()[1]) - 1][0].tooth]
                else:
                    teeth = [sp.tooth for sp, _t, _c in package_sites]
                for tooth in teeth:
                    target = _rows_by_tooth_qc.get(tooth)
                    if target is not None:
                        target.setdefault("production", {})[
                            "composite_note"] = note

            # THE MANIFEST SEALS THE COMPOSITES (W4 boolean plan, 2026-08-14). The
            # eight boolean-composite artifacts above are written straight to
            # ``out_dir`` — ``emit_case_package`` had already closed the manifest
            # before any of them existed — so, exactly like the scanned-cap isolation
            # above, each is re-hashed IN by ``register_package_files``. Only names
            # this run actually produced ride the seal: the two tinted-preview socket
            # layers and the closed model are conditional (``_layer_names`` already
            # carries only what was written), so a file the run never made is never
            # hallucinated into the hash list. ``composite_facts`` (boolean-engine
            # plan 4c) rides the SAME call: every one of these meshes was in memory
            # the instant it was written, so its facts are the caller-provides route
            # throughout — never a reload of the file this call is re-hashing.
            composite_paths = [arch_caps_path, arch_capless_path,
                               _P(out_dir) / f"{case_id}-arch-platform.stl",
                               arch_cons_path]
            composite_paths.extend(_P(out_dir) / name for name in _layer_names)
            register_package_files(manifest.path, composite_paths,
                                   facts_by_name=composite_facts)

            # view.html: the offline, no-install 3D viewer for the whole package (skipped with a
            # note when the standalone bundle has not been built on this machine)
            viewer_file = []
            try:
                scan_name = f"{case_id}-{jaw_label}.stl"
                parts = ([{"name": scan_name, "role": "arch", "path": _P(out_dir) / scan_name},
                          {"name": arch_capless_path.name, "role": "arch",
                           "path": arch_capless_path}]
                         + [{"name": f"{case_id}-{sp.tooth}-healingcap-aligned.stl", "role": "cap",
                             "path": _P(out_dir) / f"{case_id}-{sp.tooth}-healingcap-aligned.stl"}
                            for sp, _t, _c in package_sites]
                         + [{"name": f"{case_id}-{sp.tooth}-prosthesis_cad.stl",
                             "role": "construction",
                             "path": _P(out_dir) / f"{case_id}-{sp.tooth}-prosthesis_cad.stl"}
                            for sp, _t, _c in package_sites
                            if (_P(out_dir) / f"{case_id}-{sp.tooth}-prosthesis_cad.stl").exists()])
                write_view_html(case_id, out_dir,
                                parts=[q for q in parts if Path(q["path"]).exists()],
                                meta={"sites": [{k: r.get(k) for k in
                                                 ("tooth", "seat_method", "seed_source")}
                                                | {"variant": r["variant"]["identified"],
                                                   "fit": r["fit"],
                                                   "guidance_level": r["guidance"]["level"]}
                                                for r in site_rows if "error" not in r]})
                viewer_file = ["view.html"]
            except FileNotFoundError:
                pass  # standalone bundle not built — package stays valid without the viewer

    summary = {
        "case_id": case_id,
        "mode": "propose+confirm",
        "jaw": jaw_label,
        "confirmed_sites": [{"tooth": s.tooth, "center": list(s.center)} for s in confirmed],
        "sites": site_rows,
        # CASE-LEVEL RELIEF VERDICT (2026-07-25) — the run COMPLETED, and if it completed
        # at anything other than what was asked for, that is the first thing a reader sees
        # rather than a per-site detail they have to go looking for.
        "gingival_relief": _relief_summary(gingival_offset_mm, _clamp_by_tooth),
        # A preview lists its per-site files but no arch deliverables (none were made).
        "package_files": [f.name for f in manifest.files] + (
            [arch_caps_path.name, arch_capless_path.name,
             f"{case_id}-arch-platform.stl", arch_cons_path.name]
            + _layer_names
            + scanned_cap_names
            + viewer_file if emit_package else []),
    }
    # emit_case_package used to create out_dir as a side effect; a preview skips it,
    # so the report (the one thing a preview DOES write) makes its own directory.
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    report_path = Path(out_dir) / f"{case_id}-auto-report.json"
    report_path.write_text(json.dumps(summary, indent=2))
    return summary
