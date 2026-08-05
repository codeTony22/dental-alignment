"""Pre-run alignment preview for the product's Declare panes.

NEXT TRANCHE of the server.py lift (plan §4 Declare / §7 slice 5b; copy-debt ledger
row 7). Supersedes, FOR THE PRODUCT: ``_deviation_payload`` (server.py:1068-1156) and
the pre-run preview endpoint ``preview_site_alignment`` + ``_PREVIEW_DIRNAME``
(1176-1257). The demo keeps its own copies behind the freeze.

THE VERIFICATION MUST WORK ON THE FIRST PASS (client, 2026-07-26): the three panes are
read BEFORE any run, so the union pane's colouring must be derivable from nothing but
the operator's declaration. This is deliberately NOT a second alignment: it runs the
SAME ``run_auto_case`` pass the run does, for ONE site, with the product emission, the
QC renders and the pose-stability bootstrap turned off (the demo measured 3.5s vs
~30-60s for a full run). Nothing it produces is shippable and nothing it writes
survives the call.

DIVERGENCES from the lifted region, recorded here and in the ledger row per its rules:

  - NO cache and NO persistent ``preview/`` directory. The demo cached per (case,
    tooth, selection, marks) and worked under ``OUT/<case>/preview``; the product's
    caller (the BFF) persists the seat FACTS into the case session and the payload is
    response-only, so the derivation works in a scratch directory that is deleted
    before returning. The multi-second cost is the caller's to schedule — phase 2
    jobs it (plan §3's job-shaped port); the UI treats it per-site non-blocking.
  - The selection arrives as an explicit ``PreviewSelection`` derived from the case
    session, not the demo's ``RunIn`` request body; the demo's marked-sites 422s
    become the BFF's own refusals about what the SESSION still lacks. The site's
    marks come from the case's curated ``sites.json`` (the product has no marking UI
    yet — marks arrive with a later slice), passed through AS GIVEN (the re-click
    pair-integrity record: a mark is never re-centred).
  - The demo's ``_required_selection`` explicit-selection gate is NOT copied here —
    it remains ledger row 5's, lifted when 5c's run needs its exact sentence.

Plain functions over ``case_prep.pipeline``/``adapters`` — NO server import
(test_application_boundaries' AST guard), no HTTP types. Refusals raise:
``PreviewRefused`` for the pipeline's own refusals (the BFF's 409, exactly as the
demo surfaced them), ``UnknownSelection``/``ScanUnreadable`` propagate from the
catalog and the scan reader (the BFF's 422s).
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import trimesh

from case_prep.adapters import construction_catalog
from case_prep.adapters.qc_render import (DEVIATION_CLAMP_MM, DEVIATION_COLORMAP,
                                          DEVIATION_FOOTPRINT_BAND_MM,
                                          site_deviation_stats, vertex_deviation)
from case_prep.domain.clock_signature import (canon_point_to_world, scan_rim_centre,
                                              template_signature)
from case_prep.domain.part_features import MIN_LEVER_ARM_MM
from case_prep.pipeline.auto_flow import ConfirmedSite, _crowns_frame, run_auto_case
from case_prep.pipeline.final_product import DEFAULT_GINGIVAL_OFFSET_MM

from .cases import CaseRecord
from .catalog import _construction_mesh, _library_for, require_construction
from .detection import _scan_mesh

# mm/coordinate precision on the wire; the read itself is unrounded (server.py:1038)
_DEVIATION_ROUND = 4


class PreviewRefused(RuntimeError):
    """The pipeline could not seat this site from what the case holds. The message is
    the whole payload — the gate's own sentence, servable verbatim (the demo's 409)."""


@dataclass(frozen=True)
class PreviewSelection:
    """What the preview seats WITH — every field an operator act the caller (the BFF)
    read from the case session, never a suggestion this layer promoted."""

    model: str
    construction_path: str
    variant: str
    jaw: Optional[str] = None                # None = the case's own reading
    gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM
    # THE OPERATOR'S RE-MARK (the 12° defect, 2026-08-04): until this field the
    # preview ALWAYS seated from the curated record — a re-marked centre changed
    # the panes' framing and never the previewed pose, so the operator corrected
    # a centre and watched the same tilt come back. Same rule as the run: a
    # re-marked centre seeds ALONE (the record's mark pair belongs to the
    # record's own centre — pair integrity).
    marked_center: Optional[Sequence[float]] = None


def deviation_payload(case_id: str, tooth: int, scan_pts: np.ndarray,
                      pose: np.ndarray, template: trimesh.Trimesh,
                      implant_model, variant, preview: bool = False) -> dict:
    """The union pane's whole wire payload for ONE seated pose — the demo's
    ``_deviation_payload`` (server.py:1068-1156), lifted verbatim so the SHIPPED read
    (5c's run) and the PRE-RUN PREVIEW stay the same instrument on the same scale.
    Two payload builders would be two colourings, and the operator would be verifying
    one thing before Process and reading another after it."""
    posed, signed, vertex_stats = vertex_deviation(scan_pts, pose, template)
    # THE ACCEPTANCE SCALARS ARE THE PNG'S OWN, not a re-derivation over the CAD's
    # vertices. Both aggregates come out of the same kernel, but a CAD mesh is dense at
    # features and sparse on flat walls while the PNG samples the surface by AREA — on a
    # real site the two footprint RMSs differ (measured cap7030 tooth 29: 0.361 vertex-
    # weighted vs 0.427 area-uniform). One site must have ONE published RMS, so the panel
    # is served the number the difference map and the run row already publish; the
    # vertex-set coverage rides alongside under its own name, hidden from nobody.
    png_stats = site_deviation_stats(scan_pts, pose, template)
    finite = np.isfinite(signed)
    payload = {
        "case_id": case_id,
        "tooth": tooth,
        "implant_model": implant_model,
        "variant": variant,
        "frame": "jaw-scan world frame",
        "units": "mm",
        # THE SEATED CAP'S OWN FRAME (2026-07-26 client directive, kept verbatim from
        # the lifted region): pane 1 shows a library part in its canonical frame, so
        # the viewer can aim down its file +z exactly. Panes 2/3 show the SEATED cap,
        # whose axis is wherever the implant went — the jaw's occlusal proxy sat
        # 6.2°-42.0° off the real axis across the fleet (median ~13°), and a
        # client-side axis-of-revolution fit was tried and REFUSED on evidence
        # (26.9°/48.3° on zimmer-4.5 7030/8030). This is the pose the alignment
        # actually produced, so it is exact by construction and cannot fail.
        #
        # x_axis rides along because it is what makes the three panes COMPARABLE: with
        # a shared up-vector the coded cutout appears at the same clock angle in every
        # pane, which is the whole point of putting them side by side.
        "pose": {
            "axis": [round(float(v), 6) for v in pose[:3, 2]],
            "x_axis": [round(float(v), 6) for v in pose[:3, 0]],
            "origin": [round(float(v), 6) for v in pose[:3, 3]],
        },
        "n_points": int(len(posed)),
        "points": np.round(posed, _DEVIATION_ROUND).tolist(),
        "faces": np.asarray(template.faces, int).tolist(),
        "deviation_mm": [None if not ok else round(float(v), _DEVIATION_ROUND)
                         for v, ok in zip(signed, finite)],
        "scale": {
            # the colorbar bounds: clamp/colormap shared with the acceptance PNG, plus
            # what this site's data actually spans (so the UI can say "clamped")
            "clamp_mm": float(DEVIATION_CLAMP_MM),
            "min_mm": -float(DEVIATION_CLAMP_MM),
            "max_mm": float(DEVIATION_CLAMP_MM),
            "colormap": DEVIATION_COLORMAP,
            "sign_convention": "+ = scan outside the cap surface",
            "data_min_mm": (round(float(signed[finite].min()), _DEVIATION_ROUND)
                            if finite.any() else None),
            "data_max_mm": (round(float(signed[finite].max()), _DEVIATION_ROUND)
                            if finite.any() else None),
            "footprint_band_mm": float(DEVIATION_FOOTPRINT_BAND_MM),
        },
        # the site's published acceptance numbers — identical to the deviation PNG's and
        # to the run row's deviation_rms_mm/deviation_p90_mm
        "stats": {
            "rms_mm": (round(float(png_stats["rms_mm"]), 3)
                       if png_stats.get("rms_mm") is not None else None),
            "p90_mm": (round(float(png_stats["p90_mm"]), 3)
                       if png_stats.get("p90_mm") is not None else None),
            "n_footprint": int(png_stats.get("n_footprint") or 0),
            "n_samples": int(png_stats.get("n_samples") or 0),
            "source": "area-uniform surface samples (the acceptance difference map)",
        },
        # how much of the COLOURED mesh falls in the inspection band — a coverage
        # read-out for the panel, never a second acceptance number
        "vertex_footprint_points": int(vertex_stats.get("n_footprint") or 0),
        "reporting_only": True,
        # TRUE when this colouring came from the PRE-RUN preview seat rather than from a
        # shipped package — the UI captions the pane accordingly. Nothing else differs:
        # same alignment pass, same instrument, same scale.
        "preview": bool(preview),
    }
    return payload


def measured_rim_centre_world(scan_pts: np.ndarray, scan_normals: np.ndarray,
                              pose_world: np.ndarray,
                              template: trimesh.Trimesh) -> np.ndarray:
    """THE MEASURED RIM CENTRE ``application.adjust.require_clock_lever`` guards
    against (plan §10-F), in WORLD coordinates — read directly from a scan and a
    world pose, because a PRE-RUN preview has no shipped record to build the cached
    ``SiteContext`` ``adjust.site_clicks`` reads from.

    Rebuilds the SAME crowns-local frame ``adjust.load_site`` builds
    (``_crowns_frame`` is deterministic on the scan alone — no RNG, no iteration
    order to disagree on) and reads the SAME 8mm local-xy crop
    ``adjust.site_clicks`` selects before calling the one ``scan_rim_centre`` fit
    both modules use — so a Declare preview and a shipped Adjust read the identical
    point for the identical scan and pose. Cross-checked against ``adjust``'s own
    cached-frame path on real fleet data — see test_preview.py; a synthetic-only
    check could not have caught a frame mismatch that merely looks plausible."""
    pts = np.asarray(scan_pts, float)
    frame, origin, _axis = _crowns_frame(pts, scan_normals)
    local = (pts - origin) @ frame
    pose = np.asarray(pose_world, float)
    pose_local = np.eye(4)
    pose_local[:3, :3] = frame.T @ pose[:3, :3]
    pose_local[:3, 3] = frame.T @ (pose[:3, 3] - origin)
    sig = template_signature(template)
    crop = local[np.linalg.norm(local[:, :2] - pose_local[:2, 3], axis=1) < 8.0]
    canon = (crop - pose_local[:3, 3]) @ pose_local[:3, :3]
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)
    return canon_point_to_world(c0, sig.ztop, pose)


def preview_site(case: CaseRecord, selection: PreviewSelection, tooth: int) -> dict:
    """Seat ONE site's declared cap and return its deviation colouring, with nothing
    shipped and nothing kept — the union pane's read before any run (the demo's
    ``preview_site_alignment``, lifted; the refusal order runs cheapest-first so an
    impossible ask never costs a mesh parse).

    The site's centre and marks come from the case's curated sites (AS GIVEN); the
    declared variant, construction part, jaw and relief come from ``selection`` — the
    operator's persisted acts, read by the caller from the session. Multi-second on a
    real case (the demo measured ~3.5s): phase 2 jobs this through the worker port;
    the UI treats it per-site non-blocking either way.
    """
    site = next((s for s in case.suggested_sites
                 if int(s.get("tooth", -1)) == tooth), None)
    marked = selection.marked_center
    centre = marked if marked is not None else (
        site.get("center") if site is not None else None)
    if centre is None:
        raise PreviewRefused(
            f"tooth {tooth} has no site centre on case {case.id!r} — nothing to seat "
            f"a preview on")
    site = site or {}

    # the run's own rule (see application/run.py, the 12° defect): a re-marked
    # centre seeds ALONE — the record's pair belongs to the record's own centre.
    # Built BEFORE the library/scan loads, run.py's own order: the seeding
    # decision is cheap and the loads are the expensive part.
    remarked = marked is not None
    confirmed = ConfirmedSite(
        tooth, tuple(float(c) for c in centre), selection.variant,
        None if remarked else site.get("marked_points"),
        None if remarked else site.get("center_mark"),
        None if remarked else site.get("rim_mark"),
        rim_points=None if remarked else site.get("rim_points"))

    library = _library_for(case.data_root, selection.model, [selection.variant])
    construction_file = require_construction(case.data_root,
                                             selection.construction_path)
    scan = _scan_mesh(case.scan)
    jaw = selection.jaw or case.jaw

    # nothing is shipped from a preview: no bored product, no QC renders, no stability
    # bootstrap — this is a POSE, read once; the scratch dir dies with the call
    with tempfile.TemporaryDirectory(prefix="case-prep-preview-") as scratch:
        out_dir = Path(scratch)
        try:
            summary = run_auto_case(
                case_id=case.id, scan=scan, library=library,
                construction_mesh=_construction_mesh(str(construction_file)),
                vendor=construction_catalog.vendor_of(selection.construction_path),
                confirmed=[confirmed], jaw_label=jaw, out_dir=out_dir,
                proposals=None, gingival_offset_mm=selection.gingival_offset_mm,
                generate_product=False, render_qc=False, compute_confidence=False,
                emit_package=False)
        except ValueError as exc:
            # the pipeline's own refusals ("no confirmed site could be aligned") — an
            # answer to the operator, in the words the gate wrote
            raise PreviewRefused(str(exc)) from exc
        implant_path = out_dir / f"{case.id}-{tooth}-implant.json"
        if not implant_path.exists():
            raise PreviewRefused(
                f"tooth {tooth} could not be seated from the site's marks — re-mark "
                f"the cap and try again")
        rec = json.loads(implant_path.read_text())

    variant = rec.get("variant_code")
    spec = next((sp for sp in library.specs if sp.variant == variant), None)
    if spec is None:
        raise PreviewRefused(f"previewed variant {variant!r} is not in the current "
                             f"{selection.model} library")
    row = next((r for r in (summary.get("sites") or [])
                if r.get("tooth") == tooth), None)
    scan_pts = np.asarray(scan.vertices, float)
    pose_world = np.asarray(rec["pose_matrix"], float)
    tmpl = library.template(spec)
    payload = deviation_payload(
        case.id, tooth, scan_pts, pose_world, tmpl,
        implant_model=rec.get("implant_model") or selection.model, variant=variant,
        preview=True)
    # TO MAKE THE SPAN CAUTION A TRUE PRE-REFUSAL (plan §10-F): the same measured rim
    # centre ``require_clock_lever`` guards against, beside its own bound, so a client
    # can refuse locally with the gate's own number instead of the seated pose's
    # ORIGIN — close to this point but not it (see ``measured_rim_centre_world``).
    payload["clock_reference"] = {
        "rim_centre": [round(float(v), 6) for v in measured_rim_centre_world(
            scan_pts, np.asarray(scan.vertex_normals, float), pose_world, tmpl)],
        "min_lever_mm": MIN_LEVER_ARM_MM,
    }
    # The two numbers the operator judges a seat by, from the SAME row the results
    # table prints after Process — so the preview is comparable to what follows it.
    payload["seat"] = {
        "seat_method": (row or {}).get("seat_method"),
        "rim_agreement_mm": (row or {}).get("rim_agreement_mm"),
        "fit": (row or {}).get("fit"),
    }
    return payload
