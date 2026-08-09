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

from case_prep.adapters.cap_detection import measure_rim_diameter
from case_prep.application.cases import CaseRecord
from case_prep.domain.capture_gate import assess_capture
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


@dataclass(frozen=True)
class SuggestedSiteCapture:
    """A CURATED suggested site's capture assessment (the demo's ``suggested_capture``
    rows) — the chair-side chips need these before any work is invested."""

    tooth: int
    center: Optional[Tuple[float, float, float]]
    capture: dict


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


def detect(case: CaseRecord) -> DetectionResult:
    """Ranked cap-site proposals + per-site capture assessments for one case —
    deterministic given the case (the detector and the gate own no randomness)."""
    scan = _scan_mesh(case.scan)
    pts = np.asarray(scan.vertices, float)
    normals = np.asarray(scan.vertex_normals, float)
    ctx = capture_context(pts, normals)

    proposals = []
    for p in propose_sites(pts, normals=normals):
        seed = ctx.frame.T @ (np.asarray(p.center, float) - ctx.origin)
        dia = measure_rim_diameter(ctx.local_points, ctx.xy_tree, seed)
        hint = dia / 2.0 if dia else FALLBACK_RIM_RADIUS_MM
        proposals.append(DetectedSite(
            center=tuple(float(c) for c in p.center),
            void_ratio=float(p.void_ratio),
            rim_below_cusps_mm=float(p.rim_below_cusps_mm),
            tooth_guess=tooth_guess_for(p.center, case.suggested_sites),
            capture=_capture_at(ctx, seed[:2], hint),
        ))

    suggested = []
    for s in case.suggested_sites:
        centre_xy, hint = site_capture_inputs(
            ctx, s.get("center"), s.get("center_mark"), s.get("rim_mark"))
        center = s.get("center")
        suggested.append(SuggestedSiteCapture(
            tooth=int(s["tooth"]),
            center=(tuple(float(c) for c in center) if center is not None else None),
            capture=_capture_at(ctx, centre_xy, hint),
        ))

    axis = tuple(float(c) for c in ctx.frame[:, 2])  # _crowns_frame's third column -- expose, don't recompute
    return DetectionResult(proposals=tuple(proposals), suggested=tuple(suggested),
                           crown_axis=axis, jaw_reading=jaw_from_crown_axis(axis))
