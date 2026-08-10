"""RE-EMIT FROM PROVEN POSES — §10-O.7 built (plan §10-AC, 2026-08-02).

THE MEASURED FACT this module stands on (§10-M): the pose is
construction-independent. ``construction_mesh`` enters ``_align_and_package`` only at
the signatures, the package triple and the product-build block — every alignment,
seat, clock and confidence computation runs on the CAP template. So a
construction-part (or relief) change owes a RE-EMIT, never a re-align: the poses a
run already certified — including any the operator adjusted afterwards, because
``_reemit_site`` keeps ``implant.json``'s pose current — are read back out of the
SOURCE run directory and the emission stages run again with the new part.

INTO A NEW DIRECTORY, always. AM-1 makes landed runs immutable, and that answers two
of §10-M's four hazards by construction: the "wholesale implant.json rewrite" hazard
becomes copy-forward (the operator provenance keys — ``adjustments``, ``nudge``,
``best_fit`` — are read from the source records and merged into the NEW records after
emission, then re-hashed via ``register_package_files``); and the "manifest never
removes" hazard cannot bite, because the new directory gets a fresh manifest and an
old vendor's ``-scanbody-<vendor>.stl`` simply is not emitted into it.

The other two hazards are the caller's, stated here so the seam is honest: the
design-rule/relief gates inside ``emit_case_package`` CAN REFUSE — this raises
``RunRefused`` with the gate's own words, and the BFF's worker-port containment turns
that into a REFUSED run on the surfaces that already render refusals; and the QC
evidence is cap+pose, so the SESSION must clear its confirmation explicitly — a
re-emitted package would verify against a stale signature otherwise.

WHAT THE ROWS CARRY: the source report's site rows travel VERBATIM in their pose,
seat, clock, variant and guidance facts (none of those moved — same poses, same
caps), while every product-derived fact is FRESH: the relief clamp trio, the achieved
relief, the delivered-channel offsets, the shared-construction note, and the design
gate's advisories. The report states its own provenance: ``emitted_from`` names the
source run.

Plain functions over ``case_prep.pipeline``/``adapters`` — no server import, no HTTP
types (test_application_boundaries' AST guard).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from case_prep.adapters import construction_catalog
from case_prep.adapters.output_package import (SitePackageSpec, emit_case_package,
                                               register_package_files)
from case_prep.adapters.qc_render import render_site_qc
from case_prep.domain.channel import channel_from_boundary_loops
# Deliberate private imports from the pipeline (same distribution, application seam):
# the crowns frame and the relief summary are THE run's own derivations — a re-emit
# that re-implemented either would drift from the thing it claims to re-emit.
from case_prep.pipeline.auto_flow import _crowns_frame, _relief_summary
from case_prep.pipeline.auto_flow import delivered_channel_offsets
from case_prep.pipeline.deliverables import arch_with_parts, cap_imprint_holes
from case_prep.pipeline.final_product import (DEFAULT_SCREW_RADIUS_MM,
                                              build_final_product,
                                              resolve_gingival_offset)
from case_prep.pipeline.package_viewer import write_view_html

from .cases import CaseRecord
from .catalog import _construction_mesh, _library_for, require_construction
from .detection import _scan_mesh
from .run import RunRefused, RunSelection, _require_selection

# the operator-provenance keys an implant.json may have gained after its run landed
# (application/adjust.py writes them); a re-emit carries them FORWARD, never invents
# them and never drops them
_PROVENANCE_KEYS = ("adjustments", "nudge", "best_fit")


def _read_json(path: Path, what: str) -> dict:
    if not path.is_file():
        raise RunRefused(f"the source run carries no {what} at {path.name} — "
                         "a re-emit reads poses out of a completed run's package")
    return json.loads(path.read_text())


def emit_from_poses(case: CaseRecord, selection: RunSelection,
                    source_run_dir: Path, out_dir: Path) -> dict:
    """Re-emit ``case``'s package into ``out_dir`` from the poses the source run
    certified, with ``selection``'s construction part and relief. Returns the summary
    dict in ``run_case``'s shape, plus ``emitted_from``. Raises ``RunRefused`` with
    the gate's own words when the new (part × cap) pair cannot be emitted."""
    _require_selection(case, selection)
    source_run_dir = Path(source_run_dir)
    out_dir = Path(out_dir)

    report = _read_json(source_run_dir / f"{case.id}-auto-report.json", "report")
    source_rows = [dict(r) for r in report.get("sites", []) if "error" not in r]
    if not source_rows:
        raise RunRefused(f"the source run for case {case.id!r} carries no aligned "
                         "sites — nothing to re-emit")

    # the poses, read from each site's implant.json — the CURRENT pose, because the
    # adjust tools rewrite it in place when the operator moves a cap
    records: Dict[int, dict] = {}
    for row in source_rows:
        tooth = int(row["tooth"])
        records[tooth] = _read_json(
            source_run_dir / f"{case.id}-{tooth}-implant.json",
            f"implant record for tooth {tooth}")

    library = _library_for(
        case.data_root, selection.model,
        [str(r["variant"]["identified"]) for r in source_rows
         if r.get("variant", {}).get("identified")])
    construction_file = require_construction(case.data_root,
                                             selection.construction_path)
    construction_mesh = _construction_mesh(str(construction_file))
    vendor = construction_catalog.vendor_of(selection.construction_path)
    scan = _scan_mesh(case.scan)
    jaw_label = selection.jaw or case.jaw

    # the crowns frame — deterministic scan derivatives (auto_flow.py:1699-1703),
    # recomputed identically here because emission's row facts are measured in it
    pts = np.asarray(scan.vertices, float)
    normals = np.asarray(scan.vertex_normals, float)
    frame, origin, _occ = _crowns_frame(pts, normals)
    L = (pts - origin) @ frame

    # rebuild the package triple from the records — identity from the record, the
    # PART from the selection (that is the whole point of the re-emit). The cap
    # template is looked up by the record's variant through the library's own specs
    # (``template`` takes a CapSpec, exactly as the product block below does).
    def _template_for(variant_code: str):
        cap_spec = next((s for s in library.specs if s.variant == variant_code),
                        None)
        if cap_spec is None:
            raise RunRefused(f"the library carries no cap variant "
                             f"{variant_code!r} — the source run's identity "
                             "cannot be rebuilt against this library")
        return library.template(cap_spec)

    package_sites = []
    for row in source_rows:
        record = records[int(row["tooth"])]
        spec = SitePackageSpec(
            tooth=int(record["tooth"]),
            implant_model=str(record["implant_model"]),
            variant_code=str(record["variant_code"]),
            vendor=vendor,
            pose_matrix=np.asarray(record["pose_matrix"], float),
            scan_coverage=float(record.get("scan_coverage") or 0.0),
            advisory=bool(record.get("advisory", True)),
            pose_origin=str(record.get("pose_origin") or "component"),
        )
        package_sites.append(
            (spec, _template_for(spec.variant_code), construction_mesh))

    # ---- the product block, mirrored from auto_flow.py:2239-2323 ----
    # PER-SITE RELIEF (§10-B/C): the ask is the site's own override where one
    # stands, else the selection's case-level value; the shared-product cache
    # keys on (variant, ask) — two same-variant sites with different reliefs are
    # two different bored products.
    site_offsets = {int(t): float(v)
                    for t, v in (selection.site_reliefs or {}).items()}

    def _relief_ask(tooth: int) -> float:
        return site_offsets.get(tooth, selection.gingival_offset_mm)

    product_by_variant: Dict[tuple, object] = {}
    clamp_by_variant: Dict[tuple, object] = {}
    clamp_by_tooth: Dict[int, object] = {}
    final_products: Dict[int, object] = {}
    for spec, _tmpl, _cons in package_sites:
        key = (spec.variant_code, _relief_ask(spec.tooth))
        if key not in product_by_variant:
            cap_spec = next((s for s in library.specs
                             if s.variant == spec.variant_code), None)
            channel = (channel_from_boundary_loops(library.template(cap_spec))
                       if cap_spec is not None else None)
            clamp_by_variant[key] = resolve_gingival_offset(
                construction_mesh, _relief_ask(spec.tooth),
                library_channel=channel,
                screw_radius_mm=DEFAULT_SCREW_RADIUS_MM,
                part_label=(f"{spec.vendor}/{spec.implant_model} "
                            f"{spec.variant_code}"))
            product_by_variant[key] = build_final_product(
                construction_mesh, screw_radius_mm=DEFAULT_SCREW_RADIUS_MM,
                library_channel=channel,
                gingival_offset_mm=clamp_by_variant[key].applied_mm)
        final_products[spec.tooth] = product_by_variant[key]
        clamp_by_tooth[spec.tooth] = clamp_by_variant[key]

    distinct = {spec.variant_code for spec, _, _ in package_sites}
    shared_note = (f"single construction part shared across sites identifying "
                   f"{len(distinct)} distinct variants — per-variant construction "
                   f"parts needed" if len(distinct) > 1 else None)

    rows_by_tooth = {int(r["tooth"]): r for r in source_rows}
    for spec, tmpl, _cons in package_sites:
        row = rows_by_tooth[spec.tooth]
        clamp = clamp_by_tooth.get(spec.tooth)
        row["production"] = {
            "screw_channel_radius_mm": float(DEFAULT_SCREW_RADIUS_MM),
            "gingival_offset_mm": float(clamp.applied_mm if clamp is not None
                                        else _relief_ask(spec.tooth)),
            **(clamp.as_json() if clamp is not None else {}),
        }
        if shared_note:
            row["production"]["note"] = shared_note
        product = final_products.get(spec.tooth)
        row["gingival_offset"] = (
            (product.metadata.get("gingival_offset") or {}).get("achieved")
            if product is not None else None)
        row.update(delivered_channel_offsets(
            final_products[spec.tooth], spec.pose_matrix, frame, origin, L, tmpl))

    # ---- the audit block, mirrored from auto_flow.py:2325-2346 ----
    audit_by_tooth = {
        r["tooth"]: {"fit": r["fit"], "seed_source": r["seed_source"],
                     "seat_method": r["seat_method"],
                     "guidance_level": r["guidance"]["level"],
                     "declared_variant": r["variant"]["declared"],
                     "identified_variant": r["variant"]["identified"],
                     "candidates": r["variant"]["candidates"],
                     "gingival_offset_mm": (
                         float(clamp_by_tooth[r["tooth"]].applied_mm)
                         if r["tooth"] in clamp_by_tooth
                         else _relief_ask(int(r["tooth"]))),
                     **(clamp_by_tooth[r["tooth"]].as_json()
                        if r["tooth"] in clamp_by_tooth else {})}
        for r in source_rows}

    # ---- QC (cap+pose — re-rendered against the CURRENT pose) ----
    qc_paths: List[Path] = []
    for spec, tmpl, _cons in package_sites:
        row = rows_by_tooth[spec.tooth]
        paths, dev_stats = render_site_qc(case.id, spec.tooth, pts,
                                          spec.pose_matrix, tmpl,
                                          row.get("clocking"), out_dir)
        qc_paths.extend(paths)
        if dev_stats.get("rms_mm") is not None:
            row["deviation_rms_mm"] = round(float(dev_stats["rms_mm"]), 3)
        if dev_stats.get("p90_mm") is not None:
            row["deviation_p90_mm"] = round(float(dev_stats["p90_mm"]), 3)

    # ---- the package (the design-rule + relief gates live inside and CAN refuse) ----
    try:
        manifest = emit_case_package(case.id, scan, jaw_label, package_sites,
                                     out_dir, final_product_mesh=final_products,
                                     audit_by_tooth=audit_by_tooth,
                                     extra_files=qc_paths or None,
                                     include_scan_layer=True, overlay=True)
    except ValueError as exc:
        raise RunRefused(str(exc)) from exc

    # ---- provenance copy-forward (§10-M hazard 1, answered as copy) ----
    for spec, _tmpl, _cons in package_sites:
        source_record = records[spec.tooth]
        carried = {key: source_record[key] for key in _PROVENANCE_KEYS
                   if key in source_record}
        if not carried:
            continue
        new_path = out_dir / f"{case.id}-{spec.tooth}-implant.json"
        new_record = json.loads(new_path.read_text())
        new_record.update(carried)
        new_path.write_text(json.dumps(new_record, indent=2))
        register_package_files(manifest.path, [new_path])

    # ---- arch deliverables, mirrored from auto_flow.py:2441-2500 ----
    dims = library.variant_dimensions()
    caps_posed = [(tmpl, sp.pose_matrix) for sp, tmpl, _ in package_sites]
    arch_caps_path = out_dir / f"{case.id}-arch-with-healingcaps.stl"
    arch_with_parts(scan, caps_posed).export(arch_caps_path)

    # THE SEAT IS THE CAP'S OWN IMPRINT (§10-AO, client 2026-08-06): each hole is
    # the healing cap's dilated surface — its exact footprint plus the relief the
    # run itself applied — floored by the cap's own offset base. The cylinder
    # socket survives only as the per-site fallback, and a fallen-back site says
    # so on its own row.
    imprint_sites = []
    for sp, tmpl, _c in package_sites:
        dia_h = dims.get(sp.variant_code)
        if dia_h is None:
            ext = tmpl.bounds[1] - tmpl.bounds[0]
            dia_h = (float(max(ext[0], ext[1])), float(ext[2]))
        clamp = clamp_by_tooth.get(sp.tooth)
        offset = float(clamp.applied_mm) if clamp is not None \
            else float(_relief_ask(sp.tooth))
        imprint_sites.append((tmpl, sp.pose_matrix, offset,
                              float(dia_h[0]) / 2.0))
    arch_removed, imprint_notes = cap_imprint_holes(scan, imprint_sites)
    for note in imprint_notes:
        # "site N: …" — N is 1-based package_sites order; land it on that row
        tooth = package_sites[int(note.split(":", 1)[0].split()[1]) - 1][0].tooth
        rows_by_tooth[tooth].setdefault("production", {})["imprint_note"] = note
    arch_capless_path = out_dir / f"{case.id}-arch-capless.stl"
    arch_removed.export(arch_capless_path)
    # THE FIFTH ARTIFACT (client 2026-08-09): the same socket at FULL depth —
    # walls all the way down, floor at the cap's offset base, the implant's top
    # space. The shallow dish above stays the default capless artifact.
    arch_platform, _ = cap_imprint_holes(scan, imprint_sites, top_floor=True)
    arch_platform_path = out_dir / f"{case.id}-arch-platform.stl"
    arch_platform.export(arch_platform_path)

    cons_posed = [(final_products[sp.tooth], sp.pose_matrix)
                  for sp, _t, _cons in package_sites]
    arch_cons_path = out_dir / f"{case.id}-arch-with-constructions.stl"
    arch_with_parts(arch_removed, cons_posed).export(arch_cons_path)

    viewer_file: List[str] = []
    try:
        scan_name = f"{case.id}-{jaw_label}.stl"
        parts = ([{"name": scan_name, "role": "arch", "path": out_dir / scan_name},
                  {"name": arch_capless_path.name, "role": "arch",
                   "path": arch_capless_path}]
                 + [{"name": f"{case.id}-{sp.tooth}-healingcap-aligned.stl",
                     "role": "cap",
                     "path": out_dir / f"{case.id}-{sp.tooth}-healingcap-aligned.stl"}
                    for sp, _t, _c in package_sites]
                 + [{"name": f"{case.id}-{sp.tooth}-prosthesis_cad.stl",
                     "role": "construction",
                     "path": out_dir / f"{case.id}-{sp.tooth}-prosthesis_cad.stl"}
                    for sp, _t, _c in package_sites
                    if (out_dir / f"{case.id}-{sp.tooth}-prosthesis_cad.stl").exists()])
        write_view_html(case.id, out_dir,
                        parts=[q for q in parts if Path(q["path"]).exists()],
                        meta={"sites": [{k: r.get(k) for k in
                                         ("tooth", "seat_method", "seed_source")}
                                        | {"variant": r["variant"]["identified"],
                                           "fit": r["fit"],
                                           "guidance_level": r["guidance"]["level"]}
                                        for r in source_rows]})
        viewer_file = ["view.html"]
    except FileNotFoundError:
        pass  # standalone bundle not built — package stays valid without the viewer

    summary = {
        "case_id": case.id,
        "mode": "reemit-from-poses",
        # the receipt's own provenance: which run's poses this package stands on
        "emitted_from": source_run_dir.name,
        "jaw": jaw_label,
        "confirmed_sites": report.get("confirmed_sites", []),
        "sites": source_rows,
        # §10-AD × §10-AC: the source run's re-apply receipts ride forward — the
        # copied poses still stand on those acts, and a summary that dropped the
        # receipts would deny evidence the package embodies. Same copy-forward
        # doctrine as the per-site provenance keys (``_PROVENANCE_KEYS``,
        # applied per implant record above).
        **({"evidence_reapplied": report["evidence_reapplied"]}
           if report.get("evidence_reapplied") else {}),
        "gingival_relief": _relief_summary(selection.gingival_offset_mm,
                                           clamp_by_tooth),
        "package_files": [f.name for f in manifest.files]
        + [arch_caps_path.name, arch_capless_path.name,
           arch_platform_path.name, arch_cons_path.name]
        + viewer_file,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{case.id}-auto-report.json").write_text(
        json.dumps(summary, indent=2))
    return summary
