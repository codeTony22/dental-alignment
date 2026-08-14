"""Adapter: the industry-grounded case OUTPUT PACKAGE emitter.

Consumes plain post-alignment inputs (a jaw scan, per-site poses + CAD meshes) and
writes the deliverable a dental lab / doctor actually opens. Grounded in three
industry norms cited in the design brief:

1. The source scan is a legal/clinical record — it is exported UNMODIFIED, never
   re-meshed, re-centered, or otherwise touched. Every other geometry is placed
   relative to it by writing the recovered pose directly into the mesh (the
   in-mesh pose is the PRIMARY carrier — that is what dental CAD packages such as
   exocad/3Shape read); a JSON sidecar duplicates the same pose for traceability
   and for any downstream code that would rather parse numbers than a mesh.
2. Per site, a construction (\"scan-body\") record and a healing-cap record are
   kept separate — they serve different steps of the lab workflow (construction
   scan-bodies drive design; healing caps are what the doctor placed intra-op).
3. A production set (finished prosthesis geometry + an insertion-axis sidecar)
   is emitted only when a final design actually exists. We are explicitly NOT
   claiming exocad ``.constructionInfo`` schema/format compatibility here — the
   sidecar is named ``construction.json`` and only carries the fields this
   pipeline actually knows (``margin``/``material`` are honest ``null``s, not
   invented values).

Everything else (QC overlay, manifest hashing) is bookkeeping to make the
package auditable, not a claim about any vendor's file format.

Pre-export design-rule gate (G5, master plan §7.4): every production part is
measured against the four export rules (``domain/design_rules``) BEFORE anything
is written. Catastrophic violations (an unmanufacturable part) fail closed with
no files emitted; everything else lands as an ADVISORY ``design_rules`` block in
the manifest — flags for a human, never a silent fix.

RELIEF-DESTROYED-THE-CHANNEL BLOCK (2026-07-25): one further condition fails the
export closed — see ``_relief_block_reason``. It is deliberately narrow, and it is
the ONLY gingival-offset condition that blocks.

RELIEF CLAMP (2026-07-25, later the same day). The block above is unchanged and still
fires, but the pipeline no longer WALKS INTO it: ``pipeline.final_product`` measures each
(construction part x cap) pair's safe ceiling before cutting and the run completes at
min(requested, ceiling). What reaches this emitter is therefore already safe in the
ordinary case, and the block is now the backstop for the genuinely unshippable part (one
that fails even at zero relief) rather than the fleet's routine outcome. When a clamp did
happen, the pipeline stamps it into each site's audit and this emitter lifts it to a
manifest-level ``gingival_relief_clamped`` block — see ``_clamp_rows``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh

from case_prep.adapters.ingest import canonicalize_library
from case_prep.domain import design_rules

_LOCAL_Z = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class SitePackageSpec:
    """Everything the emitter needs about one implant site, in plain types —
    no dependency on the engine/pipeline's internal result objects."""

    tooth: int  # Universal 1-32
    implant_model: str  # e.g. "neodent-gm"
    variant_code: str  # e.g. "5020"
    vendor: str  # e.g. "dess" | "atlantis"
    pose_matrix: np.ndarray  # 4x4, component local frame -> jaw-scan world frame
    # DELIBERATE RENAME (2026-07-24, master plan §1 DELIVER row + §8 item 12/slice 11):
    # was ``fitness``. Old: the field/key claimed an ICP-style fitness; new:
    # ``scan_coverage`` — the fraction of ROI scan points the seated part explains
    # (what auto_flow actually passes). Reason: a package key must say what it
    # carries — "never called fitness" is the plan's own ubiquitous-language rule,
    # and the mislabeled key already misled once ("41%" read as a failure). No
    # dual-write: consumers were swept in the same change.
    scan_coverage: float
    advisory: bool
    # what the pose's ORIGIN represents: "component" (the cap/scan-body canonical origin) or
    # "implant-platform" (a validated scan-body->platform transform was applied). Honesty
    # field: a consumer must never mistake a component pose for the implant platform.
    pose_origin: str = "component"

    def __post_init__(self) -> None:
        m = np.asarray(self.pose_matrix, dtype=float)
        if m.shape != (4, 4):
            raise ValueError(f"pose_matrix must be 4x4, got {m.shape}")
        object.__setattr__(self, "pose_matrix", m)

    @property
    def position(self) -> np.ndarray:
        return self.pose_matrix[:3, 3]

    @property
    def axis(self) -> np.ndarray:
        return self.pose_matrix[:3, :3] @ _LOCAL_Z


@dataclass(frozen=True)
class MeshFacts:
    """ARTIFACT FACTS (boolean-engine plan 4c / clinical-pipeline-plan Stage 5): what
    a single emitted STL's own bytes answer — so "what happened to this file" stops
    being a mystery to a lab or a reviewer reading the manifest cold.

    ``triangle_count`` is the mesh's own face count; ``watertight`` is trimesh's
    ``is_watertight`` AT WRITE TIME — this IS the open/closed fact the client asked
    for (an open-arch artifact reads False, the closed model reads True; no separate
    verdict is computed, this is the direct reading).

    DELIBERATELY NO THIRD ``notes`` FIELD. The fallback/degradation notes this
    codebase already tracks (``production.composite_note`` / ``imprint_note`` /
    ``model_note`` / ``scanned_cap_note``) are keyed by TOOTH on the report's row,
    not by artifact filename, and a single note can cover several files (a
    whole-composite fallback) or none of a given one — threading it onto one file's
    facts here would either duplicate that row channel or silently drop the
    many-to-many cases it already handles correctly. Facts stay to what one
    artifact's own geometry can answer by itself."""

    triangle_count: int
    watertight: bool

    def as_json(self) -> Dict[str, object]:
        return {"triangle_count": self.triangle_count, "watertight": self.watertight}


def facts_of(mesh: trimesh.Trimesh) -> MeshFacts:
    """The facts an IN-MEMORY mesh already answers — no disk round-trip. Both emit
    lanes hold every mesh they write (the aligned per-site copies, the boolean
    composites) at the moment they write it; this is the seam they call instead of
    letting the manifest reload the file it just exported."""
    return MeshFacts(triangle_count=int(len(mesh.faces)), watertight=bool(mesh.is_watertight))


def _facts_from_disk(path: Path) -> MeshFacts:
    """THE LOAD FALLBACK — only for an STL no caller already measured in memory.
    ``force="mesh"`` matches every other STL load in this codebase (adapters/
    ingest.py, application/catalog.py, …) and is REQUIRED here, not merely
    conventional: an STL is an unwelded triangle soup on disk, and without the
    default vertex-merge step ``is_watertight`` reads False on every closed mesh
    alike (no two triangles share a vertex to begin with, so no edge is ever seen
    as shared)."""
    mesh = trimesh.load(path, force="mesh")
    return facts_of(mesh)


def _facts_for(path: Path, facts: Optional[MeshFacts]) -> Optional[MeshFacts]:
    """THE ONE FACTS RULE, shared by ``emit_case_package`` and
    ``register_package_files``: use what the caller already measured (no reload —
    the caller-provides route the design brief asks for); for an ``.stl`` no caller
    measured, fall back to loading the file just written/hashed; anything else
    (json/png/html) carries no facts at all — absence, never an invented reading."""
    if facts is not None:
        return facts
    if path.suffix.lower() != ".stl":
        return None
    return _facts_from_disk(path)


@dataclass(frozen=True)
class ManifestFile:
    name: str
    sha256: str
    bytes: int
    # None for a non-mesh file (absence, not an empty object) and for an entry
    # ``register_package_files`` read back off an OLD manifest without touching —
    # that path never re-derives facts for a file nobody asked it to re-hash
    facts: Optional[MeshFacts] = None

    def as_json(self) -> Dict[str, object]:
        row: Dict[str, object] = {"name": self.name, "sha256": self.sha256,
                                  "bytes": self.bytes}
        if self.facts is not None:
            row["facts"] = self.facts.as_json()
        return row


@dataclass(frozen=True)
class PackageManifest:
    """The written record of one emitted package. ``files``/``sites`` mirror the
    JSON manifest 1:1 so callers can act on it without re-reading the file."""

    case_id: str
    jaw: str
    files: Tuple[ManifestFile, ...]
    sites: Tuple[Dict[str, object], ...]
    path: Path
    # pre-export design-rule gate outcomes (G5), one row per production-set tooth;
    # mirrors the manifest JSON's ``design_rules`` block. Empty when no production
    # set was emitted.
    design_rules: Tuple[Dict[str, object], ...] = ()


Site = Tuple[SitePackageSpec, trimesh.Trimesh, trimesh.Trimesh]


def _export_stl(mesh: trimesh.Trimesh, path: Path) -> None:
    path.write_bytes(mesh.export(file_type="stl"))


def _posed_copy(mesh: trimesh.Trimesh, pose_matrix: np.ndarray) -> trimesh.Trimesh:
    """A copy of ``mesh`` transformed into the jaw frame — never mutates the input."""
    posed = mesh.copy()
    posed.apply_transform(pose_matrix)
    return posed


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_file(path: Path, facts: Optional[MeshFacts] = None) -> ManifestFile:
    return ManifestFile(name=path.name, sha256=_sha256_of(path),
                        bytes=path.stat().st_size, facts=facts)


def _relief_record(product: trimesh.Trimesh) -> Dict[str, object]:
    """The gingival-relief receipts ``pipeline.final_product`` stamped on a product
    (``{}`` for a product built by anything else — an emitter must never invent them)."""
    record = (product.metadata or {}).get("gingival_offset")
    return record if isinstance(record, dict) else {}


def _relief_block_reason(spec: SitePackageSpec,
                         product: trimesh.Trimesh) -> Optional[str]:
    """The one gingival-offset condition that FAILS THE EXPORT CLOSED, or None.

    DELIBERATE PROMOTION, advisory -> fail-closed (2026-07-25). MEASURED RECEIPTS on the
    real vendor parts, product built at the cap's library-truth channel:

      atlantis/zimmer-4.5-scanbody (cap zimmer-4.5/7030, bore r=1.102)
        offset 0.00 -> channel measurable r=1.097, min wall 0.224mm  (FLAG: under the
                       0.5mm rule — the vendor part's own thin wall, advisory as before)
        offset 0.20 -> channel UNMEASURABLE; min_wall/angulation read "unknown", and the
                       G5 worst verdict is still only "flag" — the package SHIPS
        (the whole zimmer fleet is the same story: 6020 0.294 -> 0.030mm wall,
         8030 0.287 -> 0.021mm)
      dess/neodent-gm-scanbody (cap neodent-gm/6030, bore r=1.099)
        offset 0.00 -> channel r=1.099, min wall 0.568mm (pass)
        offset 0.20 -> channel r=1.099, min wall 0.330mm (FLAG, advisory — unchanged)
      dess/neodent-gm-scanbody (cap neodent-gm/5020 — the same part, another cap)
        offset 0.00 -> min wall 0.389mm ; offset 0.20 -> 0.105mm  (BLOCKED, rule (b))

    A part whose as-built screw channel cannot be measured at all is a part no
    instrument can accept, and a lab must not ship it unnoticed. So:

      (a) the relief ERASED the channel evidence — measurable before, gone after; or
      (b) the relief thinned a wall that was ALREADY under the ``MIN_WALL_MM`` rule
          before the relief (no margin left to give) and made it thinner still.

    NOT blocked, deliberately: a wall that crosses the rule only BECAUSE of the relief
    (the 6030 row above, 0.568 -> 0.330). That is the existing G5 ``min_wall_thickness``
    flag's job — advisory, human-arbitrated — and blocking it would refuse a
    configuration whose wall still had margin to give before the relief. The narrowing is
    why the block needs the PRE-offset read, which ``build_final_product`` measures on the
    un-relieved reference product with the gate's own instrument; a product carrying no
    receipts is never blocked here.

    The rows above are also the finding this gate exists to surface: the client's 0.20mm
    default is NOT safe on every catalog part — it is safe on none of the zimmer-4.5
    fleet and on some neodent caps only. That is a product decision for the lab, which is
    exactly why the refusal names the part and the number to lower."""
    relief = _relief_record(product)
    if not relief.get("applied"):
        return None
    pre, post = relief.get("pre_offset"), relief.get("post_offset")
    if not isinstance(pre, dict) or not isinstance(post, dict) or not pre.get("measurable"):
        return None
    part = (f"tooth {spec.tooth} ({spec.vendor}/{spec.implant_model} "
            f"{spec.variant_code})")
    asked = float(relief.get("offset_mm") or 0.0)
    smaller = f"re-run with a smaller gingival offset (asked {asked:.2f}mm)"
    if not post.get("measurable"):
        return (f"the {asked:.2f}mm gingival relief ate the screw channel of {part}: the "
                f"as-built channel measured r={pre['radius_mm']:.3f}mm before the relief "
                f"and is UNMEASURABLE after it, so no instrument can accept the delivered "
                f"part — {smaller} or use a construction part with more wall")
    pre_wall, post_wall = pre.get("min_wall_mm"), post.get("min_wall_mm")
    if (pre_wall is not None and post_wall is not None
            and pre_wall < design_rules.MIN_WALL_MM
            and post_wall < design_rules.MIN_WALL_MM and post_wall < pre_wall):
        return (f"the {asked:.2f}mm gingival relief thinned an already-undersized channel "
                f"wall on {part}: {pre_wall:.3f}mm -> {post_wall:.3f}mm, both under the "
                f"{design_rules.MIN_WALL_MM:.2f}mm minimum — {smaller} or use a "
                f"construction part with more wall")
    return None


_CLAMP_KEYS = ("gingival_offset_requested_mm", "gingival_offset_applied_mm",
               "clamped", "clamp_reason")


def _clamp_rows(audit_by_tooth: Optional[Dict[int, dict]]) -> List[Dict[str, object]]:
    """The relief-clamp receipts the pipeline stamped into each site's audit, lifted to a
    manifest-level block — but ONLY for the sites that were actually clamped.

    The emitter stays dumb about the clamp semantics on purpose: it carries what
    ``pipeline.auto_flow`` measured, it does not re-derive or re-judge it. The block exists
    because the manifest is the file a lab opens FIRST — a package cut at a smaller relief
    than the one requested must announce that at the top, not only inside each
    ``implant.json``."""
    rows: List[Dict[str, object]] = []
    for tooth, audit in sorted((audit_by_tooth or {}).items()):
        if not isinstance(audit, dict) or not audit.get("clamped"):
            continue
        rows.append({"tooth": tooth,
                     **{k: audit.get(k) for k in _CLAMP_KEYS},
                     "limited_by": audit.get("limited_by"),
                     "max_safe_mm": audit.get("max_safe_mm")})
    return rows


def emit_case_package(
    case_id: str,
    jaw_scan: trimesh.Trimesh,
    jaw_label: str,
    sites: List[Site],
    out_dir: "Path | str",
    final_product_mesh: Optional[Dict[int, trimesh.Trimesh]] = None,
    overlay: bool = True,
    audit_by_tooth: Optional[Dict[int, dict]] = None,
    include_scan_layer: bool = True,
    extra_files: Optional[List[Path]] = None,
) -> PackageManifest:
    """Write the full case output package to ``out_dir`` and return its manifest.

    ``sites`` is a list of ``(SitePackageSpec, healing_cap_mesh, construction_mesh)``
    triples, one per implant site, each mesh in the component's own canonical local
    frame (the pose in the spec carries it into the jaw frame). ``final_product_mesh``
    maps tooth number -> finished prosthesis mesh (already in the jaw frame, or in the
    same local frame as the other component meshes — see module docstring); teeth
    absent from the map simply get no production set. ``extra_files`` are deliverables
    the caller already wrote into ``out_dir`` (e.g. the per-site QC acceptance renders)
    — they ride in the hashed manifest exactly like the emitted files.
    """
    if len({site[0].tooth for site in sites}) != len(sites):
        raise ValueError("duplicate tooth numbers in sites — filenames would silently collide")
    final_product_mesh = final_product_mesh or {}

    # 0. PRE-EXPORT DESIGN-RULE GATE (G5) — run over every production part BEFORE a
    # single file touches disk, so a catastrophic violation fails CLOSED (nothing is
    # emitted). Everything short of catastrophic rides along as an ADVISORY block in
    # the manifest — 3Shape-style red flags, human-arbitrated, never silently fixed.
    design_rule_rows: List[Dict[str, object]] = []
    clearance_rows: List[Dict[str, object]] = []
    for spec, _cap, construction_mesh in sites:
        product_mesh = final_product_mesh.get(spec.tooth)
        if product_mesh is None:
            continue
        # defensive re-canonicalization is a no-op on the already-canonical meshes the
        # docstring contracts for (idempotence guard in canonicalize_library), and the
        # lumen read is radius-only, so frame sign/xy cannot skew the reference
        canonical_body, _ = canonicalize_library(construction_mesh)
        checks = design_rules.evaluate_site_rules(product_mesh, canonical_body)
        verdict = design_rules.worst_verdict(checks)
        if design_rules.has_catastrophic(checks):
            worst = next(c for c in checks if c.verdict == design_rules.VERDICT_FAIL)
            raise ValueError(
                f"design-rule gate: catastrophic violation on tooth {spec.tooth} "
                f"({worst.rule}): {worst.message} — package NOT emitted")
        blocked = _relief_block_reason(spec, product_mesh)
        if blocked is not None:
            raise ValueError(f"gingival-relief gate: {blocked} — package NOT emitted")
        design_rule_rows.append({
            "tooth": spec.tooth,
            "verdict": verdict,
            "checks": design_rules.checks_as_json(checks),
        })
        # ACHIEVED CLEARANCE (2026-07-25): what the relief actually removed, measured on
        # the delivered part by ``final_product.measure_achieved_clearance`` and carried
        # here verbatim — the record must never echo the REQUEST back as if it were the
        # result (measured: 0.20 asked, ~0.13-0.15 achieved on the real parts).
        achieved = _relief_record(product_mesh).get("achieved")
        if isinstance(achieved, dict):
            clearance_rows.append({"tooth": spec.tooth, **achieved})

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    # caller-provides route (design brief): every mesh written below is already in
    # memory at the moment it is exported, so its facts are computed HERE — never a
    # second load of the file this function just wrote. Non-mesh writes (the JSON
    # sidecars) simply never gain an entry, which ``_facts_for`` reads as "no facts".
    facts_by_path: Dict[Path, MeshFacts] = {}

    # 1. SCAN LAYER — the raw jaw scan, exported unmodified. A PREVIEW skips it
    # (include_scan_layer=False, 2026-07-26): the doctor's scan is 15-25MB and the
    # caller already has it on screen; re-copying it per preview was most of the
    # scratch a preview left behind.
    if include_scan_layer:
        scan_path = out / f"{case_id}-{jaw_label}.stl"
        _export_stl(jaw_scan, scan_path)
        written.append(scan_path)
        facts_by_path[scan_path] = facts_of(jaw_scan)

    overlay_parts: List[trimesh.Trimesh] = [jaw_scan]
    site_rows: List[Dict[str, object]] = []

    for spec, healing_cap_mesh, construction_mesh in sites:
        aligned_cap = _posed_copy(healing_cap_mesh, spec.pose_matrix)
        cap_path = out / f"{case_id}-{spec.tooth}-healingcap-aligned.stl"
        _export_stl(aligned_cap, cap_path)
        written.append(cap_path)
        facts_by_path[cap_path] = facts_of(aligned_cap)
        overlay_parts.append(aligned_cap)

        # 2. IMPLANT RECORD — scan-body CAD carrying the pose in-mesh (primary
        # carrier), plus the JSON sidecar (traceability / non-mesh consumers).
        aligned_body = _posed_copy(construction_mesh, spec.pose_matrix)
        body_path = out / f"{case_id}-{spec.tooth}-scanbody-{spec.vendor}.stl"
        _export_stl(aligned_body, body_path)
        written.append(body_path)
        facts_by_path[body_path] = facts_of(aligned_body)
        overlay_parts.append(aligned_body)

        implant_json = {
            "case_id": case_id,
            "tooth": spec.tooth,
            "implant_model": spec.implant_model,
            "variant_code": spec.variant_code,
            "vendor": spec.vendor,
            "pose_matrix": spec.pose_matrix.tolist(),
            "position": spec.position.tolist(),
            "axis": spec.axis.tolist(),
            # honesty keys (master plan §8 item 12/slice 11, 2026-07-24): the coverage
            # figure under its true name (was "fitness" — no dual-write), and what the
            # pose's ORIGIN represents — the field existed on SitePackageSpec since the
            # loader honesty pass but never reached this sidecar; a consumer must never
            # mistake a component pose for the implant platform.
            "scan_coverage": spec.scan_coverage,
            "pose_origin": spec.pose_origin,
            "advisory": spec.advisory,
            "units": "mm",
            "frame": "jaw-scan world frame",
        }
        audit = dict(audit_by_tooth[spec.tooth]) if (audit_by_tooth
                                                     and spec.tooth in audit_by_tooth) else {}
        clearance = next((r for r in clearance_rows if r["tooth"] == spec.tooth), None)
        if clearance is not None:
            # the MEASURED relief rides in the paid record next to the requested one —
            # a lab reading only ``gingival_offset_mm`` was reading the ASK (2026-07-25)
            audit["gingival_clearance"] = {k: v for k, v in clearance.items()
                                           if k != "tooth"}
        if audit:
            # the run's own quality numbers travel WITH the paid record (registration
            # error, seed provenance, seat method, gate outcome) — audit trail, not
            # just a pose (ROI loop item, 2026-07-12)
            implant_json["audit"] = audit
        implant_json_path = out / f"{case_id}-{spec.tooth}-implant.json"
        implant_json_path.write_text(json.dumps(implant_json, indent=2))
        written.append(implant_json_path)

        # 3. PRODUCTION SET — only when a final design exists for this tooth.
        product_mesh = final_product_mesh.get(spec.tooth)
        if product_mesh is not None:
            aligned_product = _posed_copy(product_mesh, spec.pose_matrix)
            cad_path = out / f"{case_id}-{spec.tooth}-prosthesis_cad.stl"
            _export_stl(aligned_product, cad_path)
            written.append(cad_path)
            facts_by_path[cad_path] = facts_of(aligned_product)
            overlay_parts.append(aligned_product)

            construction_json = {
                "insertion_axis": spec.axis.tolist(),
                "implant_direction": spec.axis.tolist(),
                "implant_model": spec.implant_model,
                "variant_code": spec.variant_code,
                "vendor": spec.vendor,
                "library_ref": f"{spec.vendor}/{spec.implant_model}/{spec.variant_code}",
                "margin": None,  # not yet computed — explicit null, not an invented value
                "material": None,  # not yet selected — explicit null, not an invented value
            }
            construction_json_path = out / f"{case_id}-{spec.tooth}-construction.json"
            construction_json_path.write_text(json.dumps(construction_json, indent=2))
            written.append(construction_json_path)

        site_rows.append({
            "tooth": spec.tooth,
            "implant_model": spec.implant_model,
            "variant_code": spec.variant_code,
            "vendor": spec.vendor,
            # same deliberate rename as the implant.json sidecar (was "fitness")
            "scan_coverage": spec.scan_coverage,
            "advisory": spec.advisory,
        })

    # 5. QC OVERLAY — merged jaw + all aligned components. QC-ONLY, not for
    # manufacturing (see module docstring / manifest note below).
    if overlay:
        overlay_mesh = trimesh.util.concatenate(overlay_parts)
        overlay_path = out / f"{case_id}-{jaw_label}-overlay.stl"
        _export_stl(overlay_mesh, overlay_path)
        written.append(overlay_path)
        facts_by_path[overlay_path] = facts_of(overlay_mesh)

    # 5b. CALLER-WRITTEN DELIVERABLES (e.g. QC acceptance renders) — the manifest's
    # contract is that every listed NAME exists in the package dir and its hash
    # verifies, so each extra must already sit inside ``out_dir`` and must not
    # shadow an emitted file (the manifest is keyed by bare name).
    names = {w.name for w in written}
    for extra in (extra_files or []):
        p = Path(extra)
        if not p.is_file():
            raise ValueError(f"extra deliverable missing on disk: {p}")
        if p.resolve().parent != out.resolve():
            raise ValueError(f"extra deliverable outside the package dir: {p}")
        if p.name in names:
            raise ValueError(f"extra deliverable duplicates a package file name: {p.name}")
        names.add(p.name)
        written.append(p)

    # 4. MANIFEST — SHA-256 over every file emitted above (the manifest is
    # written last, after everything else exists on disk, and does not hash
    # itself).
    file_records = [_record_file(p, _facts_for(p, facts_by_path.get(p))) for p in written]
    manifest_json: Dict[str, object] = {
        "case_id": case_id,
        "jaw": jaw_label,
        "units": "mm",
        "tooth_numbering": "universal",
        "coordinate_frame": "all poses and aligned meshes are expressed in the jaw scan's "
                             "world frame; the jaw scan itself is exported unmodified",
        "files": [f.as_json() for f in file_records],
        "sites": site_rows,
    }
    if overlay:
        manifest_json["overlay_note"] = (
            f"{case_id}-{jaw_label}-overlay.stl is QC-ONLY (merged jaw + aligned components); "
            "not for manufacturing"
        )
    if any(row["advisory"] for row in site_rows):
        manifest_json["advisory_note"] = "advisory mode: all sites routed to human review"
    clamp_rows = _clamp_rows(audit_by_tooth)
    if clamp_rows:
        manifest_json["gingival_relief_clamped"] = clamp_rows
        manifest_json["gingival_relief_clamped_note"] = (
            "the gingival relief REQUESTED for the tooth/teeth listed here was refused: "
            "it would have left a part this package's own export gate blocks. Each part "
            "was cut at gingival_offset_applied_mm — the maximum safe relief for that "
            "construction-part/cap pair — NOT at gingival_offset_requested_mm")
    if clearance_rows:
        manifest_json["gingival_clearance"] = clearance_rows
        manifest_json["gingival_clearance_note"] = (
            "requested_mm is the relief the part was CUT with (= what the lab asked for "
            "unless gingival_relief_clamped lists this tooth, in which case the ask is "
            "gingival_offset_requested_mm there); achieved_* is what the delivered "
            "surface MEASURES against the un-relieved reference part (median/p10/p90 of "
            "the surface-to-surface distance) — the SDF relief lands short of the ask"
        )
    if design_rule_rows:
        manifest_json["design_rules"] = design_rule_rows
        flagged = [r for r in design_rule_rows if r["verdict"] != design_rules.VERDICT_PASS]
        if flagged:
            manifest_json["design_rule_note"] = (
                "pre-export design-rule gate: advisory findings on tooth "
                + ", ".join(str(r["tooth"]) for r in flagged)
                + " — see design_rules"
            )

    # The manifest lists every OTHER emitted file — it cannot hash its own bytes
    # before they are written (hashing after would make the on-disk hash stale).
    # ``PackageManifest.files`` mirrors the JSON's ``files`` array exactly, so
    # "verify every hash in files against what's on disk" holds for both; the
    # manifest.json file itself is a documented, deliberate exception.
    manifest_path = out / f"{case_id}-manifest.json"
    manifest_path.write_text(json.dumps(manifest_json, indent=2))

    return PackageManifest(
        case_id=case_id,
        jaw=jaw_label,
        files=tuple(file_records),
        sites=tuple(site_rows),
        path=manifest_path,
        design_rules=tuple(design_rule_rows),
    )


def register_package_files(manifest_path: "Path | str",
                           paths: List[Path],
                           facts_by_name: Optional[Dict[str, MeshFacts]] = None
                           ) -> Tuple[ManifestFile, ...]:
    """Re-hash ``paths`` into an already-written manifest, inserting or REPLACING each
    record by bare file name; returns the updated records.

    The manifest is written once, at emission. An operator adjustment at the review gate
    (nudge / align-to-mark / correspondence / best-fit) rewrites the site's aligned-cap
    STL and implant.json IN PLACE and adds the alignment-proof PNG — so without this the
    manifest's contract ("every listed name exists and its hash verifies") quietly stops
    holding for the two rewritten files, and the proof is not listed at all. Files must
    already sit in the manifest's own directory (the manifest is keyed by bare name);
    a missing manifest raises rather than silently doing nothing.

    ``facts_by_name`` is the SAME caller-provides seam ``emit_case_package`` uses
    internally: the boolean composites (arch/socket/model layers) and the scanned-cap
    isolation are built by their callers with the mesh already in hand, so their facts
    ride straight in here — no reload of the file this call just re-hashed. A ``.stl``
    absent from the mapping falls back to loading the file (``_facts_for``); a non-STL
    name (an alignment-proof PNG) carries no facts, matching ``emit_case_package``'s
    own rule. An entry this call is not asked to touch is left byte-for-byte as it
    was — an OLD manifest predating facts stays parseable and its untouched rows stay
    bare, never gaining an invented block for a file nobody re-measured."""
    path = Path(manifest_path)
    manifest_json = json.loads(path.read_text())
    records = list(manifest_json.get("files") or [])
    updated: List[ManifestFile] = []
    facts_by_name = facts_by_name or {}
    for p in paths:
        p = Path(p)
        if not p.is_file():
            raise ValueError(f"cannot register a file that is not on disk: {p}")
        if p.resolve().parent != path.resolve().parent:
            raise ValueError(f"cannot register a file outside the package dir: {p}")
        record = _record_file(p, _facts_for(p, facts_by_name.get(p.name)))
        updated.append(record)
        row = record.as_json()
        at = next((i for i, r in enumerate(records) if r.get("name") == record.name), None)
        if at is None:
            records.append(row)
        else:
            records[at] = row
    manifest_json["files"] = records
    path.write_text(json.dumps(manifest_json, indent=2))
    return tuple(updated)
