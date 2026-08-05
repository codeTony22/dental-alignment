"""THE FULL RUN for the product — the demo's run endpoint, lifted (plan §7 slice 5c).

NEXT TRANCHE of the server.py lift (plan §1.2/AM-1, §3/AM-3; copy-debt ledger row 8).
Supersedes, FOR THE PRODUCT: the explicit-selection gate ``_required_selection``
(server.py:893-916 — ledger row 5 narrows to the adjust-tool judging with this commit)
and the run endpoint's orchestration (server.py:933-1011). The demo keeps its own copies
behind the freeze.

One call: validated selection → ``run_auto_case`` with EVERYTHING ON — the product is
generated, the QC renders written, the pose-stability confidence computed, the package
emitted — because the worker emits at run time (plan §1.2: that is how the pipeline
works and how the adjust tools find their site records; what moves to the END of the
flow is DISCLOSURE, never emission). Multi-second to a minute on a real case: the
caller schedules it behind the job-shaped worker port (plan §3/AM-3).

``out_dir`` is THE CALLER'S RUN DIRECTORY — a parameter, deliberately: application code
names no reports path (AM-1's immutable run dirs are the caller's contract; this layer
only fills whatever directory it was handed).

DIVERGENCES from the lifted region, recorded here and in the ledger row per its rules:

  - NO serve-time cache and NO ``run.json`` reuse (the demo's ``_run_cache_key`` +
    ``_cache`` + disk round-trip): a product run lands in an immutable run directory
    and a re-run mints a NEW directory — caching a run is the caller's decision about
    run IDENTITY, not this layer's about payload hashes.
  - NO run-history append and no ``duration_s``/``files_base``/``selection`` echo —
    serve-time telemetry and transport shaping; the BFF owns its own response.
  - Capture blocks are not re-derived here: the product surfaces capture at Intake
    (application.detection); the demo recomputed them per run response.
  - ``proposals=None``: the demo rode its cached automation proposals along for the
    human-vs-machine ``auto_delta_mm`` compare; the product's detection lives in the
    session and the compare returns with a later slice. The row KEY stays (the
    pipeline always writes it; it reads None).
  - Refusals RAISE — ``RunRefused`` with the pipeline's own words (the demo's 409) —
    and the explicit-selection gate's sentence is kept verbatim, suggestion hint
    included; ``UnknownSelection``/``ScanUnreadable`` propagate from the catalog and
    the scan reader exactly as on the preview path.

Plain functions over ``case_prep.pipeline``/``adapters`` — NO server import
(test_application_boundaries' AST guard), no HTTP types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from case_prep.adapters import construction_catalog
from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case
from case_prep.pipeline.final_product import DEFAULT_GINGIVAL_OFFSET_MM

from .cases import CaseRecord
from .catalog import _construction_mesh, _library_for, require_construction
from .detection import _scan_mesh


class RunRefused(RuntimeError):
    """The pipeline (or the selection gate) said no. The message is the whole payload —
    the gate's own sentence, servable verbatim (the demo surfaced these words as 409)."""


@dataclass(frozen=True)
class RunSelection:
    """What the run acts ON — every field an operator act the caller (the BFF) read
    from the case session, never a suggestion this layer promoted. ``variants`` maps
    tooth → declared variant; a None variant is legal here exactly as in the demo's
    ``RunIn`` (the pipeline identifies), though the product's authorization gate
    always sends declared ones."""

    model: Optional[str]
    construction_path: Optional[str]
    variants: Mapping[int, Optional[str]] = field(default_factory=dict)
    jaw: Optional[str] = None                # None = the case's own reading
    gingival_offset_mm: float = DEFAULT_GINGIVAL_OFFSET_MM
    # THE OPERATOR'S OWN CENTRES (client 2026-07-28: sites the detector missed).
    # tooth → world-frame centre, for sites that exist because a HUMAN marked them.
    # Detection misses 2 of the 10 sites on this fleet, and until now a missed cap
    # could not be worked at all: the case record is the only place a centre lived,
    # and the case record is not something an operator can write to. These ride in
    # the selection with every other operator act rather than being merged into the
    # case, so the case record stays exactly what the ingest produced.
    marked_centers: Mapping[int, Sequence[float]] = field(default_factory=dict)
    # PER-SITE RELIEF OVERRIDES (§10-B/C, 2026-08-04): tooth → the operator's own
    # ask for that site, set on Adjustment; a site absent here takes the case-level
    # value. Overrides ride every future run and re-emit like the other acts.
    site_reliefs: Mapping[int, float] = field(default_factory=dict)
    # THE OPERATOR'S ALIGNMENT EVIDENCE (§10-AD, client 2026-08-02: adjustments must
    # survive a re-run). tooth → the session's AlignmentEvidence dicts in apply
    # order (kind mark|pairs|best_fit + payload). Re-applied AFTER automation via
    # the same application.adjust functions the tools use — the marks are
    # world-frame measurements on a scan that has not changed, so they stay valid
    # across runs exactly like marked_centers. The bare rotation nudge is never in
    # here, by design (its provenance is eyeball with no marks).
    alignment_evidence: Mapping[int, Sequence[dict]] = field(default_factory=dict)


def _require_selection(case: CaseRecord, selection: RunSelection) -> None:
    """The explicit-selection gate — server.py:893-916 VERBATIM (sentence, field
    naming, suggestion hint): the run refuses rather than fall back to the case's
    name-matched suggestion (client directive 2026-07-25 — the silent guess the
    directive removed survives only on propose/preview paths)."""
    missing = []
    if not selection.model:
        missing.append("the implant system (\"model\", e.g. from GET /api/library)")
    if not selection.construction_path:
        missing.append("the construction part (\"construction_path\", a path_id from "
                       "GET /api/constructions)")
    if missing:
        hint = ""
        if case.suggested_model or case.suggested_construction:
            hint = (f" (this case suggests model="
                    f"{case.suggested_model!r}, construction_path="
                    f"{case.suggested_construction!r} — a suggestion only; send it "
                    f"back explicitly to use it)")
        raise RunRefused("the library selection is incomplete: choose "
                         + " and ".join(missing)
                         + ". The software will not pick one for you." + hint)


def _reapply_evidence(case: CaseRecord, run_dir: Path,
                      evidence_by_tooth: Mapping[int, Sequence[dict]],
                      summary: dict) -> None:
    """Re-apply the operator's persisted alignment evidence to a FRESH run, through
    the same ``application.adjust`` functions the tools use — same physics, same
    gates, same in-run provenance (§10-AD). Mutates ``summary`` in place: each act's
    outcome lands in ``summary["evidence_reapplied"]`` (applied / already-optimal /
    refused, with the gate's own words — a refusal here is an ANSWER about the new
    geometry, never a failed run), the re-derived row numbers fold into the site's
    row through the SAME fold the interactive landing uses
    (``adjust.fold_outcome_into_row`` — one fold since the 2026-08-04 audit caught
    the two hand-written copies drifting), and rewritten file names join
    ``package_files``. A re-applied pairs fit rebuilds the correspondence QC block
    from the entry's own pair count — the canonical fold retired this function's
    earlier documented under-claim."""
    from . import adjust  # heavy import, deferred like the pipeline's own

    outcomes: list = []
    rows_by_tooth = {r.get("tooth"): r for r in summary.get("sites", [])
                     if "error" not in r}
    for tooth in sorted(int(t) for t in evidence_by_tooth):
        for entry in evidence_by_tooth[tooth]:
            kind = entry.get("kind")
            receipt = {"tooth": tooth, "kind": kind,
                       "applied_at": entry.get("applied_at")}
            try:
                if kind == "mark":
                    outcome = adjust.align_to_mark(case, run_dir, tooth,
                                                   entry["point"])
                elif kind == "pairs":
                    pairs = [adjust.Correspondence(
                        scan_point=p["scan_point"],
                        scan_point_end=p.get("scan_point_end"),
                        feature_id=p.get("feature_id"),
                        part_point=p.get("part_point"),
                        part_point_end=p.get("part_point_end"))
                        for p in (entry.get("pairs") or [])]
                    outcome = adjust.align_to_correspondence(case, run_dir,
                                                             tooth, pairs)
                elif kind == "best_fit":
                    outcome = adjust.best_fit_site(
                        case, run_dir, tooth,
                        matching_diameter_mm=float(
                            entry.get("matching_diameter_mm") or
                            adjust._BEST_FIT_DEFAULT_DIAMETER_MM),
                        apply=True)
                else:
                    receipt.update(outcome="refused",
                                   detail=f"unknown evidence kind {kind!r} — "
                                          "nothing was re-applied")
                    outcomes.append(receipt)
                    continue
            except adjust.AlreadyOptimal as exc:
                # the one refusal that is a PASS: the fresh automation already
                # stands where the evidence would put it
                receipt.update(outcome="already-optimal", detail=str(exc))
                outcomes.append(receipt)
                continue
            except (adjust.AdjustInvalid, adjust.AdjustRefused) as exc:
                receipt.update(outcome="refused", detail=str(exc))
                outcomes.append(receipt)
                continue
            receipt.update(outcome="applied", operation=outcome.operation,
                           detail=outcome.detail)
            outcomes.append(receipt)
            row = rows_by_tooth.get(tooth)
            if row is not None:
                adjust.fold_outcome_into_row(
                    row, outcome,
                    correspondence_pairs=(len(entry.get("pairs") or [])
                                          if kind == "pairs" else None))
            for name in outcome.files:
                if name not in summary.get("package_files", []):
                    summary.setdefault("package_files", []).append(name)
    if outcomes:
        summary["evidence_reapplied"] = outcomes


def run_case(case: CaseRecord, selection: RunSelection, out_dir: Path) -> dict:
    """Align, measure, gate and PACKAGE every selected site into ``out_dir`` — the
    demo run's semantics as one refusal-raising call. Returns the pipeline's summary
    dict: the per-site rows (guidance/clocking/variant/production/fit — the demo's
    results-table shape) plus ``package_files``, the emitted file list (names relative
    to ``out_dir``). The refusal order runs cheapest-first, like the preview: an
    impossible ask never costs a mesh parse."""
    _require_selection(case, selection)
    teeth = sorted(int(t) for t in selection.variants)
    if not teeth:
        raise RunRefused(f"no sites selected on case {case.id!r} — nothing to run")
    confirmed = []
    for tooth in teeth:
        site = next((s for s in case.suggested_sites
                     if int(s.get("tooth", -1)) == tooth), None)
        # THE OPERATOR'S MARK WINS over the case's own suggestion, and stands alone
        # where there is no suggestion at all. A human who marked a centre has looked
        # at this scan more recently than the ingest did; silently preferring the
        # ingest would make the mark decorative. A site with NEITHER is still refused,
        # in the same words — the refusal was never about where the centre came from.
        marked = selection.marked_centers.get(tooth)
        centre = marked if marked is not None else (
            site.get("center") if site is not None else None)
        if centre is None:
            raise RunRefused(f"tooth {tooth} has no site centre on case {case.id!r} "
                             f"— nothing to align")
        site = site or {}
        # marks pass through AS GIVEN (the re-click pair-integrity record: a mark is
        # never re-centred) — and they pass WITH THE CENTRE THEY MEASURED. When the
        # operator RE-MARKED, the record's center_mark/rim_mark belong to the
        # record's own centre, and shipping them beside a different centre splices
        # two measurements (measured 2026-08-04 on cap6020: the splice held DEV RMS
        # at 0.4157 with the axis 12.2° off the seat the operator's bare centre
        # produces at 0.3053 — the re-mark was decorative for the physics because
        # auto_flow prefers center_mark). A re-marked site therefore seeds ALONE;
        # an unmarked site keeps the record's pair, which BEATS a bare click when
        # the centre is its own (0.4157 vs 0.4894, same case).
        remarked = marked is not None
        confirmed.append(ConfirmedSite(
            tooth, tuple(float(c) for c in centre),
            selection.variants[tooth],
            None if remarked else site.get("marked_points"),
            None if remarked else site.get("center_mark"),
            None if remarked else site.get("rim_mark"),
            rim_points=None if remarked else site.get("rim_points")))

    library = _library_for(case.data_root, selection.model,
                           [v for v in selection.variants.values() if v])
    construction_file = require_construction(case.data_root,
                                             selection.construction_path)
    scan = _scan_mesh(case.scan)
    jaw = selection.jaw or case.jaw
    try:
        summary = run_auto_case(
            case_id=case.id, scan=scan, library=library,
            construction_mesh=_construction_mesh(str(construction_file)),
            vendor=construction_catalog.vendor_of(selection.construction_path),
            confirmed=confirmed, jaw_label=jaw, out_dir=Path(out_dir),
            proposals=None, gingival_offset_mm=selection.gingival_offset_mm,
            # EVERYTHING ON (plan §1.2): product bored, QC rendered, confidence
            # computed, package emitted — the run IS the emission; disclosure gates
            # later (Deliver), never the physics
            generate_product=True, render_qc=True, compute_confidence=True,
            emit_package=True,
            site_gingival_offsets={int(t): float(v)
                                   for t, v in selection.site_reliefs.items()})
    except ValueError as exc:
        # the pipeline's REFUSALS travel as ValueError with a human message — the
        # export gates ("package NOT emitted", the relief gate) and "no confirmed
        # site could be aligned"; answers to the operator, in the gate's words
        raise RunRefused(str(exc)) from exc
    # THE OPERATOR'S EVIDENCE OUTLIVES THE RUN THAT RECEIVED IT (§10-AD): re-apply
    # it now, after automation, into the run's own directory — the same functions,
    # gates and provenance as the live tools. Refusals land as receipts on the
    # summary, never as a failed run: a mark the new geometry cannot take is an
    # answer the operator reads, not a crash.
    if selection.alignment_evidence:
        _reapply_evidence(case, Path(out_dir), selection.alignment_evidence,
                          summary)
        # the report on disk carries the receipts too — the run dir must never
        # say less than the summary the BFF landed (AM-1's honesty half)
        report_path = Path(out_dir) / f"{case.id}-auto-report.json"
        if report_path.is_file():
            import json as _json
            report_path.write_text(_json.dumps(summary, indent=2))
    return summary
