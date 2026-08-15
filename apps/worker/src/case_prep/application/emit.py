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
import trimesh

from case_prep.adapters import construction_catalog
from case_prep.adapters.output_package import (MeshFacts, SitePackageSpec,
                                               emit_case_package, facts_of,
                                               register_package_files)
from case_prep.adapters.qc_render import render_site_qc
from case_prep.domain.channel import channel_from_boundary_loops
# Deliberate private imports from the pipeline (same distribution, application seam):
# the crowns frame and the relief summary are THE run's own derivations — a re-emit
# that re-implemented either would drift from the thing it claims to re-emit.
from case_prep.pipeline.auto_flow import _crowns_frame, _relief_summary
from case_prep.pipeline.auto_flow import delivered_channel_offsets
from case_prep.pipeline.deliverables import (arch_with_parts_fused,
                                             cap_imprint_holes,
                                             cap_imprint_parts,
                                             open_arch_with_floored_holes)
from case_prep.pipeline.isolation import isolate_scanned_cap
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
    # ARTIFACT FACTS FOR THE COMPOSITES (boolean-engine plan 4c), mirrored from the
    # run lane: every mesh below is already in memory the instant it is written, so
    # its facts are computed HERE, off that mesh — never a reload of the STL this
    # same lane just wrote.
    composite_facts: Dict[str, MeshFacts] = {}

    # THE SEAT IS THE CAP'S OWN IMPRINT (§10-AO, client 2026-08-06): each hole is
    # the healing cap's dilated surface — its exact footprint plus the relief the
    # run itself applied — floored by the cap's own offset base. The cylinder
    # socket survives only as the per-site fallback, and a fallen-back site says
    # so on its own row. BUILT BEFORE THE FUSED COMPOSITES BELOW (moved here,
    # DEFECT 1 EXCISION slice, client-ruled 2026-08-15): the fused healing-cap
    # composite needs each site's own catalog rim radius to excise the scanned
    # cap's crust, and this loop is the one place that radius is already derived.
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

    caps_posed = [(tmpl, sp.pose_matrix) for sp, tmpl, _ in package_sites]
    # DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15): the SAME
    # templates/poses ``caps_posed`` already carries, plus each site's own
    # catalog rim radius (``imprint_sites``' own 4th element, same order) —
    # "white patches poking through the library cap" was this exact composite's
    # symptom, and the part's own posed surface must replace the scanned cap's
    # crust, never merge with it.
    caps_excise_sites = [(tmpl, sp.pose_matrix, rim_r)
                         for (sp, tmpl, _c), (_t, _p, _o, rim_r)
                         in zip(package_sites, imprint_sites)]
    arch_caps_path = out_dir / f"{case.id}-arch-with-healingcaps.stl"
    arch_caps, caps_notes = arch_with_parts_fused(
        scan, caps_posed, excise_sites=caps_excise_sites)
    arch_caps.export(arch_caps_path)
    composite_facts[arch_caps_path.name] = facts_of(arch_caps)
    for note in caps_notes:
        # "part N …" — N is 1-based package_sites order (caps_posed's own order);
        # land it on that row. A WHOLE-COMPOSITE note (the fail-open fallback,
        # §10-AT 3b — no "part " prefix) lands on every row: the degradation
        # covered all of them.
        if note.startswith("part "):
            teeth = [package_sites[int(note.split()[1]) - 1][0].tooth]
        else:
            teeth = [sp.tooth for sp, _t, _cons in package_sites]
        for tooth in teeth:
            rows_by_tooth[tooth].setdefault("production", {})[
                "composite_note"] = note

    # SCANNED-CAP ISOLATION (clinical pipeline plan Stage 2 slice 2a, boolean plan
    # 4d): per site, exactly what the scanner saw of the healing cap — cylinder
    # pre-cut at the catalog rim, template-matched band, core-keep for the scanned
    # screw-recess void the template can never cover (§10-AT front 1 corrected).
    # Whole triangles from the scan's own bytes; nothing moved, nothing inferred.
    # A pathological pose that catches nothing skips emission and lands a per-site
    # note instead of an empty file — the same honesty rule the imprint/composite
    # notes below already carry.
    scanned_cap_names: List[str] = []
    for index, ((sp, tmpl, _c), (_t, pose, _offset, rim_r)) in enumerate(
            zip(package_sites, imprint_sites), 1):
        isolated = isolate_scanned_cap(scan, tmpl, pose, rim_r)
        if isolated is None:
            rows_by_tooth[sp.tooth].setdefault("production", {})["scanned_cap_note"] = (
                f"site {index}: the scanned-cap isolation caught nothing at this "
                "pose — the artifact was not emitted")
            continue
        scanned_cap_path = out_dir / f"{case.id}-{sp.tooth}-scanned-cap.stl"
        isolated.export(scanned_cap_path)
        register_package_files(
            manifest.path, [scanned_cap_path],
            facts_by_name={scanned_cap_path.name: facts_of(isolated)})
        scanned_cap_names.append(scanned_cap_path.name)

    arch_socketless, socket_dish, imprint_notes = cap_imprint_parts(
        scan, imprint_sites)
    arch_removed = (trimesh.util.concatenate([arch_socketless, socket_dish])
                    if socket_dish is not None else arch_socketless)
    for note in imprint_notes:
        # "site N: …" — N is 1-based package_sites order; land it on that row.
        # A WHOLE-CARVE note (the CSG route's fallback sentence, §10-AS.12 —
        # no site prefix) lands on every row: the degradation covered all.
        if note.startswith("site "):
            teeth = [package_sites[
                int(note.split(":", 1)[0].split()[1]) - 1][0].tooth]
        else:
            teeth = [sp.tooth for sp, _t, _cons in package_sites]
        for tooth in teeth:
            rows_by_tooth[tooth].setdefault("production", {})[
                "imprint_note"] = note
    arch_capless_path = out_dir / f"{case.id}-arch-capless.stl"
    arch_removed.export(arch_capless_path)
    composite_facts[arch_capless_path.name] = facts_of(arch_removed)
    # THE FIFTH ARTIFACT (client 2026-08-09): the platform socket. Both
    # sockets also land as their OWN layer files beside the socketless arch,
    # so the preview can tint the cut surface (the downloads keep the merged
    # solids the lab expects).
    _, socket_platform, _pnotes = cap_imprint_parts(scan, imprint_sites,
                                                    top_floor=True)
    arch_platform = (trimesh.util.concatenate([arch_socketless,
                                               socket_platform])
                     if socket_platform is not None else arch_socketless)
    arch_platform_path = out_dir / f"{case.id}-arch-platform.stl"
    arch_platform.export(arch_platform_path)
    composite_facts[arch_platform_path.name] = facts_of(arch_platform)
    arch_socketless_path = out_dir / f"{case.id}-arch-socketless.stl"
    arch_socketless.export(arch_socketless_path)
    composite_facts[arch_socketless_path.name] = facts_of(arch_socketless)
    layer_names = [arch_socketless_path.name]
    if socket_dish is not None:
        pth = out_dir / f"{case.id}-socket-dish.stl"
        socket_dish.export(pth)
        composite_facts[pth.name] = facts_of(socket_dish)
        layer_names.append(pth.name)
    if socket_platform is not None:
        pth = out_dir / f"{case.id}-socket-platform.stl"
        socket_platform.export(pth)
        composite_facts[pth.name] = facts_of(socket_platform)
        layer_names.append(pth.name)
    # ARTIFACT 6, THE FOURTH RULING (client-ruled, live call over a reference
    # image, 2026-08-15 night): the through-hole shape retires in turn —
    # "why is that cylinder so big" — replaced by the open arch wearing each
    # cap's exact recess cut to the GINGIVAL FLOOR, no shaft descending into
    # the solidified interior.
    model_closed, model_notes = open_arch_with_floored_holes(scan, imprint_sites)
    if model_closed is not None:
        pth = out_dir / f"{case.id}-arch-open-holes.stl"
        model_closed.export(pth)
        composite_facts[pth.name] = facts_of(model_closed)
        layer_names.append(pth.name)
    for note in model_notes:
        if note.startswith("site "):
            teeth = [package_sites[
                int(note.split(":", 1)[0].split()[1]) - 1][0].tooth]
        else:
            teeth = [sp.tooth for sp, _t, _cons in package_sites]
        for tooth in teeth:
            rows_by_tooth[tooth].setdefault("production", {})[
                "model_note"] = note

    cons_posed = [(final_products[sp.tooth], sp.pose_matrix)
                  for sp, _t, _cons in package_sites]
    arch_cons_path = out_dir / f"{case.id}-arch-with-constructions.stl"
    arch_cons, cons_notes = arch_with_parts_fused(arch_removed, cons_posed)
    arch_cons.export(arch_cons_path)
    composite_facts[arch_cons_path.name] = facts_of(arch_cons)
    for note in cons_notes:
        if note.startswith("part "):
            teeth = [package_sites[int(note.split()[1]) - 1][0].tooth]
        else:
            teeth = [sp.tooth for sp, _t, _cons in package_sites]
        for tooth in teeth:
            rows_by_tooth[tooth].setdefault("production", {})[
                "composite_note"] = note

    # THE MANIFEST SEALS THE COMPOSITES (W4 boolean plan, 2026-08-14) — mirrored
    # from auto_flow.py's run lane, so the two lanes produce the SAME manifest
    # shape. The eight boolean-composite artifacts above are written straight to
    # ``out_dir`` after ``emit_case_package`` already closed the manifest, so each
    # is re-hashed IN by ``register_package_files`` exactly like the scanned-cap
    # isolation above. Only names this re-emit actually produced ride the seal
    # (``layer_names`` already carries only what was written): an absent socket
    # layer or closed model is never hallucinated into the hash list.
    # ``composite_facts`` (boolean-engine plan 4c) rides the SAME call, mirroring
    # the run lane: every one of these meshes was in memory the instant it was
    # written, so its facts are the caller-provides route throughout.
    composite_paths = [arch_caps_path, arch_capless_path, arch_platform_path,
                       arch_cons_path]
    composite_paths.extend(out_dir / name for name in layer_names)
    register_package_files(manifest.path, composite_paths,
                           facts_by_name=composite_facts)

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
        + layer_names
        + scanned_cap_names
        + viewer_file,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{case.id}-auto-report.json").write_text(
        json.dumps(summary, indent=2))
    return summary
