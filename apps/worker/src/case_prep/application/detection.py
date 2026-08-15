"""Automatic cap-site detection + capture assessment for the product's Intake.

THIRD TRANCHE of the server.py lift (plan §4 Intake, §7 slice 4; copy-debt ledger row 6).
Supersedes, FOR THE PRODUCT, the demo's capture assembly and propose orchestration
(server.py:733-857): ``_capture_context``, ``_capture_block``, ``_site_capture_inputs``,
``_with_capture``, ``_run_sites_capture`` and ``POST /api/cases/{id}/propose``. The demo
keeps its own copies behind the freeze.

Plain deterministic functions over ``case_prep.pipeline``/``domain`` — NO server import
(test_application_boundaries' AST guard enforces it), no HTTP types. Refusals raise
(``ScanUnreadable``); the caller (the BFF) owns mapping them to its transport.

DIVERGENCES from the lifted region, recorded here and in the ledger row per its rules:

  - NO caches. The demo layered a per-process cfg cache plus ``proposals.json``/
    ``capture.json`` on disk because its propose endpoint re-fires per click; the
    product's caller persists the RESULT into the case session, so detection runs once
    per case unless explicitly re-asked. ``detect(case)`` is a pure derivation.
  - ``duration_s``/``cached`` dropped — serve-time telemetry, not detection facts.
  - ``tooth_guess`` is NEW product logic, not a copy: the demo's proposals carry no
    tooth (its operator assigns one at confirmation). Intake's site list is keyed by
    tooth, so a proposal within ``TOOTH_GUESS_RADIUS_MM`` of a CURATED suggested site
    inherits that tooth as a NON-BINDING guess — labelled a guess, never silently
    promoted (client directive 2026-07-25: the lab chooses, the software never guesses).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from case_prep.adapters import library_catalog
from case_prep.adapters.cap_detection import measure_rim_diameter
from case_prep.application.cases import CaseRecord
from case_prep.domain.cap_catalog import propose_variant
from case_prep.domain.capture_gate import assess_capture
from case_prep.domain.island import segment_island
from case_prep.pipeline.auto_flow import _crowns_frame, _fit_circle_xy, propose_sites

# The demo's crop fallback: when no rim is measurable at a site, capture is assessed at
# the 2.6mm radius the pipeline's own crop uses (server.py's _site_capture_inputs).
FALLBACK_RIM_RADIUS_MM = 2.6

# A healing cap is ~5mm across; a proposal within one cap-width of a curated site's
# centre is that site seen by the detector, anything farther is its own finding.
TOOTH_GUESS_RADIUS_MM = 5.0

# cos(60 deg) -- the fleet-measured jaw cone (§10-AM: crown-up sat within 1-16 deg of
# world z on every one of 10 scans). 60 deg is generous headroom over that spread, not
# a fitted boundary -- a scan that lands outside it is genuinely ambiguous, not unlucky.
JAW_AXIS_COS_THRESHOLD = 0.5


class ScanUnreadable(RuntimeError):
    """The case's scan could not be parsed into a usable mesh. The message is the whole
    payload — one human sentence the caller can serve verbatim as its refusal detail."""


@dataclass(frozen=True)
class CaptureContext:
    """Per-case crowns-up local frame + xy tree for capture assessment — the same
    ``_crowns_frame`` the pipeline itself seats in (lift of server.py's
    ``_capture_context``, minus its cfg-dict cache)."""

    frame: np.ndarray          # 3x3, columns = local axes in world space, det = +1
    origin: np.ndarray         # world point the local frame is centred on
    local_points: np.ndarray   # the scan in the local frame (crowns up +z)
    xy_tree: cKDTree           # over local_points[:, :2]


@dataclass(frozen=True)
class DetectedSite:
    """One detector proposal with its capture verdict — the demo's proposal row plus
    the product's non-binding tooth guess."""

    center: Tuple[float, float, float]   # world coords, as proposed
    void_ratio: float
    rim_below_cusps_mm: float
    tooth_guess: Optional[int]
    capture: dict                        # CaptureAssessment.to_dict()
    # P4.1 — curve-honesty fields. density_prior_used is always a bool on a
    # proposal (False when the informativeness gate was off). DP fields are
    # None at detect: island has not run; absence is None, never 0.0.
    density_prior_used: bool = False
    dp_gap_fraction: Optional[float] = None
    bearing_margin: Optional[Tuple[float, ...]] = None


@dataclass(frozen=True)
class SuggestedSiteCapture:
    """A CURATED suggested site's capture assessment (the demo's ``suggested_capture``
    rows) — the chair-side chips need these before any work is invested.

    ``measured_cap_height_mm``/``proposed_variant`` (client escalation 2026-08-09):
    the site's own honest height reading and the variant it independently suggests
    — see ``measured_cap_height_mm`` and ``domain.cap_catalog.propose_variant`` for
    what "honest" means here. Both None whenever the geometry cannot support the
    read (a starved site, no system to propose against, an ambiguous class) —
    never a guess wearing a suggestion's clothes."""

    tooth: int
    center: Optional[Tuple[float, float, float]]
    capture: dict
    measured_cap_height_mm: Optional[float] = None
    proposed_variant: Optional[str] = None
    # the VISIBLE cap's own rim, read fresh off the scan (§10-AS.18, client
    # 2026-08-10: "remove the soft tissue... just the healing cap") — on a
    # submerged cap tissue heals OVER the flanks, and the catalog rim would
    # honestly include that overgrowth; this is the separator the panes crop by
    measured_rim_diameter_mm: Optional[float] = None
    # THE DISCRIMINATOR EVIDENCE (clinical-pipeline-plan.md Stage 1, slice 1a):
    # ``cap_detection.CapSiteCandidate``'s own core/ring density read and its
    # rim-below-cusps depth, borrowed from the nearest matching PROPOSAL (see
    # ``candidate_evidence_for``) so Intake can say WHY a site was proposed —
    # not recomputed independently, so a curated site can never disagree with
    # the proposal that found it about its own numbers. None when the
    # automatic pass never proposed this site at all (a human mark, or a
    # recall miss): there is no ring density to show, and it is never
    # invented from a nearby but distinct candidate.
    rim_below_cusps_mm: Optional[float] = None
    void_ratio: Optional[float] = None
    # P4.1 — borrowed from the matching proposal (``candidate_evidence_for``).
    # None when the automatic pass never proposed this site: never False/0.0
    # standing in for an untaken measurement. False is a real report ("prior off").
    density_prior_used: Optional[bool] = None
    dp_gap_fraction: Optional[float] = None
    bearing_margin: Optional[Tuple[float, ...]] = None


@dataclass(frozen=True)
class DetectionResult:
    proposals: Tuple[DetectedSite, ...]
    suggested: Tuple[SuggestedSiteCapture, ...]
    crown_axis: Tuple[float, float, float]  # world-space crown-up axis, from _crowns_frame
    jaw_reading: Optional[str]              # jaw_from_crown_axis(crown_axis) -- §10-AM


def capture_context(points: np.ndarray, normals: Optional[np.ndarray]) -> CaptureContext:
    """The crowns-up local frame + xy tree, computed once per detection pass."""
    pts = np.asarray(points, float)
    frame, origin, _ = _crowns_frame(pts, normals)
    local = (pts - origin) @ frame
    return CaptureContext(frame=frame, origin=origin, local_points=local,
                          xy_tree=cKDTree(local[:, :2]))


def site_capture_inputs(ctx: CaptureContext, center,
                        center_mark=None, rim_mark=None, rim_points=None
                        ) -> Tuple[np.ndarray, float]:
    """(centre_xy_local, rim_r_hint) for a site — the same centre+radius precedence
    ``run_auto_case`` applies (border-circle fit > centre+rim marks > measured rim >
    the 2.6mm crop fallback), lifted verbatim from server.py's ``_site_capture_inputs``.
    The pair is passed to the gate AS GIVEN — capture assessment never re-centres a
    human mark (the re-click pair-integrity record)."""
    if rim_points and len(rim_points) >= 3:
        P = (np.asarray(rim_points, float) - ctx.origin) @ ctx.frame
        fit = _fit_circle_xy(P[:, :2])
        if fit is not None:
            centre_xy, rim_r = fit
            return np.asarray(centre_xy, float), float(rim_r)
    world = np.asarray(center_mark if center_mark is not None else center, float)
    seed = ctx.frame.T @ (world - ctx.origin)
    if rim_mark is not None:
        rim_local = ctx.frame.T @ (np.asarray(rim_mark, float) - ctx.origin)
        return seed[:2], float(np.linalg.norm((rim_local - seed)[:2]))
    if rim_points:  # 1-2 border points: average radius about the centre
        P = (np.asarray(rim_points, float) - ctx.origin) @ ctx.frame
        return seed[:2], float(np.mean(np.linalg.norm(P[:, :2] - seed[:2], axis=1)))
    dia = measure_rim_diameter(ctx.local_points, ctx.xy_tree, seed)
    return seed[:2], (dia / 2.0 if dia else FALLBACK_RIM_RADIUS_MM)


def tooth_guess_for(center, suggested_sites: Sequence[Dict],
                    max_mm: float = TOOTH_GUESS_RADIUS_MM) -> Optional[int]:
    """The nearest CURATED site's tooth, when the proposal lands within ``max_mm`` of
    its centre (world distance); None otherwise — a guess is labelled a guess."""
    c = np.asarray(center, float)
    best: Tuple[float, Optional[int]] = (float("inf"), None)
    for s in suggested_sites:
        site_center = s.get("center")
        if site_center is None or "tooth" not in s:
            continue
        d = float(np.linalg.norm(np.asarray(site_center, float) - c))
        if d <= max_mm and d < best[0]:
            best = (d, int(s["tooth"]))
    return best[1]


@dataclass(frozen=True)
class CandidateEvidence:
    """The nearest matching proposal's discriminator + curve-honesty numbers
    (P4.1). Every field defaults to None — honest absence, never False or 0.0
    standing in for a measurement the detector never took."""

    rim_below_cusps_mm: Optional[float] = None
    void_ratio: Optional[float] = None
    density_prior_used: Optional[bool] = None
    dp_gap_fraction: Optional[float] = None
    bearing_margin: Optional[Tuple[float, ...]] = None


def candidate_evidence_for(center, proposals: Sequence[DetectedSite],
                           max_mm: float = TOOTH_GUESS_RADIUS_MM
                           ) -> CandidateEvidence:
    """The nearest detector PROPOSAL's own discriminator + curve-honesty fields
    for a CURATED site, when the density stack actually found something within
    one cap-width of it — the reverse of ``tooth_guess_for`` (there a proposal
    inherits a site's tooth; here a site borrows a proposal's WHY). Empty
    ``CandidateEvidence`` when no proposal lands this close: a human-marked or
    manually confirmed site the automatic pass never proposed has no ring
    density to show, and a nearby but DISTINCT candidate's numbers are never
    borrowed in its place — the same 'a guess is labelled a guess' discipline
    ``tooth_guess_for`` already keeps."""
    if center is None:
        return CandidateEvidence()
    c = np.asarray(center, float)
    best_d = float("inf")
    best: Optional[DetectedSite] = None
    for p in proposals:
        d = float(np.linalg.norm(np.asarray(p.center, float) - c))
        if d <= max_mm and d < best_d:
            best_d = d
            best = p
    if best is None:
        return CandidateEvidence()
    return CandidateEvidence(
        rim_below_cusps_mm=best.rim_below_cusps_mm,
        void_ratio=best.void_ratio,
        density_prior_used=best.density_prior_used,
        dp_gap_fraction=best.dp_gap_fraction,
        bearing_margin=best.bearing_margin,
    )


def jaw_from_crown_axis(axis) -> Optional[str]:
    """The measured convention (§10-AM): scanners export arches jaw-signed -- crown-up
    points toward +z for a lower arch, -z for an upper one, confirmed across the whole
    fleet. Outside a 60-degree cone of either pole the scan makes no claim: a sideways
    export is honestly ``None``, never a coin-flip guess -- the same discipline
    ``tooth_guess_for`` applies to an unmatched proposal. A SUGGESTION only: the caller
    never rewrites the declared jaw or the scan bytes from this (§10-AM: cross-check,
    never a transform)."""
    z = float(np.asarray(axis, float)[2])
    if z >= JAW_AXIS_COS_THRESHOLD:
        return "lower"
    if z <= -JAW_AXIS_COS_THRESHOLD:
        return "upper"
    return None


# A footprint sample needs enough points to trust a "top" reading — the same
# >=20-point bar the seat's own centre-snap already trusts before it reads a local
# patch of the scan (auto_flow's ``_mean_shift_top``/``snap_r`` convention).
_HEIGHT_FOOTPRINT_MIN_PTS = 20


def measured_cap_height_mm(ctx: CaptureContext, centre_xy, footprint_r: float,
                           collar_z: Optional[float]) -> Optional[float]:
    """The cap's own measured height at one site: its highest scanned point within
    its own footprint, above the LOCAL collar ``assess_capture`` already read there
    (``CaptureAssessment.rim_z`` — passed in, never resampled here, so a site's
    capture verdict and its height can never disagree about where the collar
    sits). The footprint is the same disc the capture checks sample around, radius
    = the site's own measured rim — reusing the gate's own vocabulary rather than
    inventing a new sampler.

    None — never a guess — when the collar itself is unmeasurable (mirrors
    ``assess_capture``'s own starved-site refusal), the footprint holds too few
    points to trust a top reading, or the reading is non-positive (a cap's dome
    sits ABOVE its own rim by definition; anything else says the footprint was
    not really the cap — noise, not a measurement)."""
    if collar_z is None:
        return None
    xy = ctx.local_points[:, :2] - np.asarray(centre_xy, float)
    footprint = ctx.local_points[np.linalg.norm(xy, axis=1) < footprint_r]
    if len(footprint) < _HEIGHT_FOOTPRINT_MIN_PTS:
        return None
    height = float(footprint[:, 2].max()) - float(collar_z)
    return height if height > 0.0 else None


def _variant_table_for(case: CaseRecord) -> Dict[str, Tuple[float, float]]:
    """variant -> (rim_diameter_mm, height_mm), CURRENT shelf only, for the case's
    own suggested system — the exact table run-time identification measures a cap
    against (``CapLibrary.variant_dimensions``), read here from the cached
    full-catalog scan (``library_catalog.catalog_groups`` hashes every mesh once
    per process per data root) instead of loading a second ``CapLibrary``:
    ``detect()`` already parses the whole doctor's scan, and it must not ALSO
    re-canonicalize a shelf of cap CADs on every Intake click.

    Empty — never raised — when the case names no system, or its folder-matched
    name is not an actual catalog model: an honest 'nothing to propose against',
    and ``propose_variant`` already answers None over an empty table. Superseded/
    legacy/unloadable entries are excluded by construction, so nothing built from
    this table can ever propose an archived id (curation may still declare one)."""
    if case.suggested_model is None:
        return {}
    group = next((g for g in library_catalog.catalog_groups(case.data_root)
                 if g["model"] == case.suggested_model), None)
    if group is None:
        return {}
    return {v["variant"]: (v["rim_diameter_mm"], v["height_mm"])
           for v in group["variants"]
           if not (set(v["flags"]) & {"superseded", "legacy", "unloadable"})
           and v["rim_diameter_mm"] is not None and v["height_mm"] is not None}


def _scan_mesh(scan: Path) -> trimesh.Trimesh:
    try:
        mesh = trimesh.load(scan, force="mesh")
    except Exception as exc:  # trimesh raises a zoo; the caller needs one sentence
        raise ScanUnreadable(f"the scan {scan.name} could not be read as a mesh: "
                             f"{exc}") from exc
    vertices = getattr(mesh, "vertices", None)
    if vertices is None or len(vertices) == 0:
        raise ScanUnreadable(f"the scan {scan.name} holds no surface to detect on — "
                             f"is the file complete?")
    return mesh


def _capture_at(ctx: CaptureContext, centre_xy, rim_r_hint: float) -> dict:
    return assess_capture(ctx.local_points, centre_xy, rim_r_hint).to_dict()


def island_curve_honesty(local_points, centre_xy, radius_hint: float
                         ) -> Tuple[Optional[float], Optional[Tuple[float, ...]]]:
    """Shadow-island DP honesty for Intake (P4.1 leftover). Reports
    ``(dp_gap_fraction, bearing_margin)`` when the island converges; otherwise
    ``(None, None)``. An exception is swallowed — the same posture
    ``auto_flow``'s SHADOW_ISLAND row already keeps: a shadow must never take
    down detect, and absence is None, never 0.0. Does not move a pose."""
    try:
        reading = segment_island(np.asarray(local_points, float),
                                 np.asarray(centre_xy, float),
                                 radius_hint=float(radius_hint))
    except Exception:
        return None, None
    if not reading.converged:
        return None, None
    gap = reading.dp_gap_fraction
    margin = reading.bearing_margin
    return (
        (float(gap) if gap is not None else None),
        (tuple(float(x) for x in margin) if margin is not None else None),
    )


def detect(case: CaseRecord) -> DetectionResult:
    """Ranked cap-site proposals + per-site capture assessments for one case —
    deterministic given the case (the detector and the gate own no randomness)."""
    scan = _scan_mesh(case.scan)
    pts = np.asarray(scan.vertices, float)
    normals = np.asarray(scan.vertex_normals, float)
    ctx = capture_context(pts, normals)

    scan_faces = getattr(scan, "faces", None)
    proposals = []
    for p in propose_sites(pts, normals=normals,
                           faces=(np.asarray(scan_faces, int)
                                  if scan_faces is not None else None)):
        seed = ctx.frame.T @ (np.asarray(p.center, float) - ctx.origin)
        dia = measure_rim_diameter(ctx.local_points, ctx.xy_tree, seed)
        hint = dia / 2.0 if dia else FALLBACK_RIM_RADIUS_MM
        gap, margin = island_curve_honesty(ctx.local_points, seed[:2], hint)
        proposals.append(DetectedSite(
            center=tuple(float(c) for c in p.center),
            void_ratio=float(p.void_ratio),
            rim_below_cusps_mm=float(p.rim_below_cusps_mm),
            tooth_guess=tooth_guess_for(p.center, case.suggested_sites),
            capture=_capture_at(ctx, seed[:2], hint),
            density_prior_used=bool(p.density_prior_used),
            dp_gap_fraction=gap,
            bearing_margin=margin,
        ))

    variant_table = _variant_table_for(case)
    suggested = []
    for s in case.suggested_sites:
        centre_xy, hint = site_capture_inputs(
            ctx, s.get("center"), s.get("center_mark"), s.get("rim_mark"))
        center = s.get("center")
        cap = _capture_at(ctx, centre_xy, hint)
        # THE INDEPENDENT SCAN READ (client escalation 2026-08-09): a human mark's
        # own RADIUS is exactly what this measurement is asked to CROSS-CHECK, so
        # the diameter feeding the variant proposal is read fresh off the scan at
        # the site's centre — never substituted by a human's rim click. Same
        # posture auto_flow's own dia_class cross-check already takes
        # (``measured_dia`` there is computed unconditionally, marks or not).
        measured_dia = measure_rim_diameter(ctx.local_points, ctx.xy_tree, centre_xy)
        height = (measured_cap_height_mm(ctx, centre_xy, measured_dia / 2.0,
                                         cap.get("rim_z_mm"))
                 if measured_dia is not None else None)
        evidence = candidate_evidence_for(center, proposals)
        suggested.append(SuggestedSiteCapture(
            tooth=int(s["tooth"]),
            center=(tuple(float(c) for c in center) if center is not None else None),
            capture=cap,
            measured_cap_height_mm=height,
            proposed_variant=propose_variant(measured_dia, height, variant_table),
            measured_rim_diameter_mm=measured_dia,
            rim_below_cusps_mm=evidence.rim_below_cusps_mm,
            void_ratio=evidence.void_ratio,
            density_prior_used=evidence.density_prior_used,
            dp_gap_fraction=evidence.dp_gap_fraction,
            bearing_margin=evidence.bearing_margin,
        ))

    axis = tuple(float(c) for c in ctx.frame[:, 2])  # _crowns_frame's third column -- expose, don't recompute
    return DetectionResult(proposals=tuple(proposals), suggested=tuple(suggested),
                           crown_axis=axis, jaw_reading=jaw_from_crown_axis(axis))
