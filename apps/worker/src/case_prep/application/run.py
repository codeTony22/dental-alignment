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
from typing import Mapping, Optional

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
        if site is None or site.get("center") is None:
            raise RunRefused(f"tooth {tooth} has no site centre on case {case.id!r} "
                             f"— nothing to align")
        # marks pass through AS GIVEN (the re-click pair-integrity record: a mark is
        # never re-centred), exactly as the preview passes them
        confirmed.append(ConfirmedSite(
            tooth, tuple(float(c) for c in site["center"]),
            selection.variants[tooth], site.get("marked_points"),
            site.get("center_mark"), site.get("rim_mark"),
            rim_points=site.get("rim_points")))

    library = _library_for(case.data_root, selection.model,
                           [v for v in selection.variants.values() if v])
    construction_file = require_construction(case.data_root,
                                             selection.construction_path)
    scan = _scan_mesh(case.scan)
    jaw = selection.jaw or case.jaw
    try:
        return run_auto_case(
            case_id=case.id, scan=scan, library=library,
            construction_mesh=_construction_mesh(str(construction_file)),
            vendor=construction_catalog.vendor_of(selection.construction_path),
            confirmed=confirmed, jaw_label=jaw, out_dir=Path(out_dir),
            proposals=None, gingival_offset_mm=selection.gingival_offset_mm,
            # EVERYTHING ON (plan §1.2): product bored, QC rendered, confidence
            # computed, package emitted — the run IS the emission; disclosure gates
            # later (Deliver), never the physics
            generate_product=True, render_qc=True, compute_confidence=True,
            emit_package=True)
    except ValueError as exc:
        # the pipeline's REFUSALS travel as ValueError with a human message — the
        # export gates ("package NOT emitted", the relief gate) and "no confirmed
        # site could be aligned"; answers to the operator, in the gate's words
        raise RunRefused(str(exc)) from exc
