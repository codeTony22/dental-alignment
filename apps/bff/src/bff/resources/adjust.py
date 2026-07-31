"""THE ADJUST TOOLS' RESOURCE (plan §4 Adjust, §5, §7 slice 6) — the flagged-site
rework surface, server-side.

Four tools, all the same shape: a GATED PROPOSAL over one site's shipped pose.

  - ``POST .../sites/{tooth}/rotation``      {step_deg, reset}
  - ``POST .../sites/{tooth}/mark-trench``   {scan_point}
  - ``POST .../sites/{tooth}/fit-by-points`` {pairs}          — incl. the TWO-POINT SPAN
  - ``POST .../sites/{tooth}/best-fit``      {matching_diameter_mm, apply}

plus the reads the panes open on: ``GET .../sites/{tooth}/seated`` — the shipped pose's
own deviation colouring, the same payload shape Declare's preview serves — and
``GET .../sites/{tooth}/landmarks`` — AUTO-MARK's proposal (client 2026-07-29, item 3:
"another tool where we automatically mark the points in the library and the client has
to match the same points on the scan"). The part half of a correspondence pair has
always been the easy half; this route serves it, best clock evidence first
(``case_prep.application.adjust.clock_landmarks``), so ``fit-by-points`` gains a mode
where the operator's whole job is finding the SAME feature in the scan — a pair built
on a served landmark cannot fail the part-side lever rule by construction.

WHAT THIS RESOURCE OWNS, AND WHAT IT REFUSES TO OWN. Every millimetre, gate and
refusal sentence is ``case_prep.application.adjust``'s (plan §1.3: presentation may not
do the physics, and neither may the BFF). This module owns four things and no more:

 1. THE PRECONDITION. A tool needs a VERDICT to rework: a done current run, a summary
    row for this tooth, and a site standing on ready|flagged|adjusted. Adjusting a site
    the run never aligned is meaningless, and the refusal says exactly that.
 2. THE INPUT CORPUS (plan §6/AM-9, ledger row 4): ``extra="forbid"`` on every body,
    length-3 + finiteness on every client coordinate, the ±45° step and the ≤8 pairs
    cap copied VERBATIM from the frozen models so a client hitting the BFF directly
    meets the same wall the UI does. The application re-judges everything anyway — it
    owns the geometry — so these are the cheap door, never the only lock.
 3. THE LANDING. A successful tool moves the site through ``status.adjust`` (its first
    legitimate writer), folds the new instrument reading into the run's summary row,
    joins the newly emitted files to the run's package list, marks the stage visited —
    and RETIRES THE CONFIRMATION (``session.clear_confirmation``): a confirmed case
    whose fits moved is not confirmed any more.
 4. THE REFUSAL SPLIT, matching the demo's own statuses so the client reads one
    taxonomy: ``AdjustInvalid`` → 422 (the ask was malformed), ``AdjustRefused`` → 409
    (a gate said no), and ``AlreadyOptimal`` → 409 carrying the machine-readable fields
    that let the surface render the pass GREEN with a one-click widen. A refusal
    changes NOTHING: no status, no row, no session write at all.

THE ONE HONEST SEAM. The physics runs OUTSIDE the CAS mutation (it takes seconds and a
retry must never re-run it), and it WRITES — the tools re-emit the cap STL, the site
record, the proof and the manifest inside the run directory. So the landing re-judges
the run POINTER on the fresh document and refuses (409) when it moved: the adjustment
then sits in a directory that is history, recorded in that directory's own append-only
``adjustments`` list, and the session says so instead of pretending it landed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from case_prep.application.adjust import (AdjustInvalid, AdjustOutcome, AdjustRefused,
                                          AlreadyOptimal, Correspondence,
                                          align_to_correspondence, align_to_mark,
                                          best_fit_site, clock_landmarks, load_site,
                                          rotate_site, seated_payload)
from case_prep.application.cases import CaseRecord
from case_prep.application.catalog import UnknownSelection
from case_prep.application.detection import ScanUnreadable

from .. import status
from ..config import Settings
from ..session import (CaseSession, RunSession, SessionStore, SiteStatus,
                       clear_confirmation)
from .case_sessions import (CaseSessionDetail, _case_or_404, _context, _detail,
                            _mutate_session, _require_known_tooth)
# ONE home for the run directory's path shape (the disclosure edge's) — two spellings
# of "where this run lives" would be two answers waiting to disagree.
from .deliver import _run_dir

router = APIRouter(prefix="/api/case-sessions", tags=["adjust"])


# --- the request models: the validation corpus, extended (plan §6/AM-9, ledger row 4) ----

# server.py:1268, verbatim — a nudge is a correction, not a re-seat.
_MAX_STEP_DEG = 45.0
# server.py:1768, verbatim.
_MAX_PAIRS = 8
# server.py:2012-2017, verbatim (the ceiling is the winner pass's own cutoff, doubled).
_MIN_DIAMETER_MM = 0.05
_MAX_DIAMETER_MM = 2.0


def _finite_triple(value, field_name: str):
    """Length-3 + finiteness on every client coordinate — the corpus' promised
    EXTENSION (plan §6/AM-9: the demo checked the marks it happened to receive; the
    product checks every coordinate that crosses the wire). ``np.isfinite`` became
    ``math.isfinite``: identical semantics, and the BFF owns no numpy."""
    if value is None:
        return value
    if len(value) != 3:
        raise ValueError(f"{field_name} must be an [x, y, z] triple")
    if not all(math.isfinite(c) for c in value):
        raise ValueError(f"{field_name} coordinates must be finite numbers")
    return [float(c) for c in value]


class RotationIn(BaseModel):
    """One operator rotation step, degrees CCW about the seated part's own axis.
    ``reset`` restores the pipeline's own certified pose (``step_deg`` is ignored).

    The ±45° bound is server.py:1281-1287 verbatim, including its sentence: the client
    renders these words, and a bound that drifted between the two apps would be two
    different tools wearing one name."""

    model_config = ConfigDict(extra="forbid")

    step_deg: float = 0.0
    reset: bool = False

    @field_validator("step_deg")
    @classmethod
    def _bounded_step(cls, v):
        if not math.isfinite(v) or abs(v) > _MAX_STEP_DEG:
            raise ValueError(f"step_deg must be a finite step within "
                             f"±{_MAX_STEP_DEG:.0f}°")
        return float(v)


class MarkTrenchIn(BaseModel):
    """The operator's click on the scanned coded trench, world coordinates on the scan
    mesh. The 15mm mark-distance bound is the application's (it needs the site's seated
    position); this model owns the coordinate's SHAPE."""

    model_config = ConfigDict(extra="forbid")

    scan_point: List[float]

    @field_validator("scan_point")
    @classmethod
    def _finite_xyz(cls, v):
        return _finite_triple(v, "scan_point")


class PairIn(BaseModel):
    """One operator correspondence.

    The PART half is EITHER a feature of the library part (by id) OR ``part_point`` —
    an arbitrary canonical-frame click on the part itself (client ask 2026-07-26:
    catalogs whose detector reads a single rotation-defining feature stranded the
    operator at one pair while the part visibly carried a second cutout). Exactly one.

    The SCAN half is one click — or, with ``scan_point_end``, THE SPAN (client ask
    2026-07-26, plan §5): both ENDS of the feature instead of a guess at its centre.
    The span's own bounds (a minimum length, a maximum, the radiality read that decides
    whether its direction names a clock angle at all) are the application's, because
    they are geometry."""

    model_config = ConfigDict(extra="forbid")

    feature_id: Optional[str] = None
    part_point: Optional[List[float]] = None
    scan_point: List[float]
    scan_point_end: Optional[List[float]] = None

    @field_validator("scan_point", "scan_point_end", "part_point")
    @classmethod
    def _finite_xyz(cls, v, info):
        return _finite_triple(v, info.field_name)

    @model_validator(mode="after")
    def _one_part_half(self):
        if (self.feature_id is None) == (self.part_point is None):
            raise ValueError("each pair needs exactly one of feature_id or part_point")
        return self


class FitByPointsIn(BaseModel):
    """The named correspondences. The ≤8 cap is server.py:1859-1862 verbatim; the
    lever-arm rule (a landmark inside 0.5mm of the part's rim centre names the AXIS,
    not a clock angle) is the application's, because it needs the part."""

    model_config = ConfigDict(extra="forbid")

    pairs: List[PairIn] = Field(default_factory=list)

    @field_validator("pairs")
    @classmethod
    def _bounded_pairs(cls, v):
        if len(v) > _MAX_PAIRS:
            raise ValueError(f"a correspondence is capped at {_MAX_PAIRS} pairs, got "
                             f"{len(v)}")
        return v


class BestFitIn(BaseModel):
    """``matching_diameter_mm`` is the operator's correspondence search DIAMETER — the
    dial the dental-CAD best-fit dialogs expose. ``apply=False`` MEASURES ONLY: the
    refinement runs and the gates still judge it, but nothing is touched — a preview,
    never a weaker gate. Bounds are server.py:2043-2051 verbatim."""

    model_config = ConfigDict(extra="forbid")

    matching_diameter_mm: float = 0.3
    apply: bool = True

    @field_validator("matching_diameter_mm")
    @classmethod
    def _bounded_diameter(cls, v):
        if not math.isfinite(v) or not (_MIN_DIAMETER_MM <= v <= _MAX_DIAMETER_MM):
            raise ValueError(f"matching_diameter_mm must be between "
                             f"{_MIN_DIAMETER_MM} and {_MAX_DIAMETER_MM}mm, got {v!r}")
        return float(v)


# --- the response models ------------------------------------------------------------------

class AdjustOutcomeView(BaseModel):
    """What the tool produced, as the surface reads it — the application's own facts,
    passed through. Tool-specific fields are None where they do not apply (a best-fit
    is not a clock nudge and reports no cumulative rotation; a rotation reports no
    residual RMS)."""

    tooth: int
    operation: str
    detail: str
    applied: bool
    files: List[str] = Field(default_factory=list)
    clocking: Optional[dict] = None
    # what this act re-derived over the new pose, and what it could not — the surface
    # tells the operator both, because the second half is what they carry into Deliver
    deviation: Optional[dict] = None
    stale_metrics: List[str] = Field(default_factory=list)
    nudge: Optional[dict] = None
    applied_delta_deg: Optional[float] = None
    cumulative_deg: Optional[float] = None
    stability_excess_mm: Optional[float] = None
    best_fit: Optional[dict] = None
    # one row per OBSERVATION (a span contributes two), each with its own residual
    pairs: List[dict] = Field(default_factory=list)
    residual_rms_mm: Optional[float] = None
    click_azimuth_deg: Optional[float] = None
    matched_feature_azimuth_deg: Optional[float] = None


class AdjustResultView(BaseModel):
    """One applied (or measured) tool: what it did, the NEW pose as the panes render
    it, and the whole case detail — so the surface replaces its payload verbatim
    rather than patching a status locally (the trust direction, AM-4). ``pane_payload``
    is None exactly when nothing was applied."""

    outcome: AdjustOutcomeView
    pane_payload: Optional[dict] = None
    case: CaseSessionDetail


# --- the precondition and the landing ------------------------------------------------------

_VERDICT_RUNGS = (SiteStatus.READY, SiteStatus.FLAGGED, SiteStatus.ADJUSTED)


def _require_verdict(session: CaseSession, case_id: str, tooth: int) -> RunSession:
    """A tool needs a VERDICT to rework (the prompt's own rule, and the honest one):
    a done current run, a summary row for THIS tooth, and a site standing on a rung
    that carries an outcome. Refuses 422 naming which of the three is missing —
    adjusting a site the run never aligned is meaningless, and a bare "cannot" would
    leave the operator guessing which.

    Judged INSIDE every mutation as well as before the physics (25604e7's rule): a
    rival change mid-flight must be re-judged, never re-applied from a stale verdict."""
    run = session.run
    if run is None or run.state != "done" or run.summary is None:
        raise HTTPException(422, f"there is nothing to adjust on case {case_id!r} — "
                                 f"Adjust reworks the fits a completed run produced, "
                                 f"and this case has no completed current run")
    if _summary_row(run, tooth) is None:
        raise HTTPException(422, f"tooth {tooth} carries no verdict from the current "
                                 f"run — adjusting a site the run never aligned is "
                                 f"meaningless")
    site = session.sites.get(str(tooth))
    if site is None or site.status not in _VERDICT_RUNGS:
        standing = site.status.value if site is not None else "detected"
        raise HTTPException(422, f"tooth {tooth} is {standing!r} — a site still "
                                 f"climbing to a verdict has no fit to rework; the "
                                 f"tools open on ready, flagged or adjusted sites")
    return run


def _summary_row(run: RunSession, tooth: int) -> Optional[dict]:
    for row in (run.summary or {}).get("sites") or []:
        try:
            if int(row.get("tooth", -1)) == tooth:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _fold_outcome(run: RunSession, tooth: int, outcome: AdjustOutcome) -> None:
    """Fold the post-adjustment reading into the run's summary row — the demo's
    ``_update_run_row`` (server.py:1337-1375), re-homed: the demo rewrote its cached
    run.json, the product's summary lives on the session receipt.

    THE ROW MUST DESCRIBE THE POSE THAT SHIPPED (review 2026-07-28, finding E). It is
    not a cache here as it was in the demo — the assurance projection reads it verbatim
    and the CONFIRMATION SEALS it, so a row left describing the pre-rework fit puts
    stale numbers under a freshly derived hash, which is worse than not re-hashing at
    all. Three things keep that honest:

      - the instrument readings the tool re-derived over the new pose land here
        (``clocking``, and ``deviation``, whose scalars come off the very payload the
        operator's panes are rendering);
      - what could NOT be re-derived from the shipped record is NAMED
        (``rework.stale_metrics``) so the sealed document says which of its numbers
        predate the rework, instead of implying all of them are fresh;
      - a RESET clears both markers and the best-fit block: the site is back on the
        pipeline's own certified pose, so nothing predates anything and no block may go
        on describing a fit that has been undone.

    ``nudge`` is written only when the tool ROTATED (the demo's 2026-07-25 rule kept
    verbatim: a manual best-fit is a 6-DoF move, not a clock nudge, and must not
    overwrite the site's cumulative rotation with a number it did not apply);
    ``best_fit`` only when a best-fit landed. The new files JOIN the package list —
    the alignment proof is EVIDENCE the operator should see, and the rewritten cap and
    record must not disappear from what the run claims."""
    row = _summary_row(run, tooth)
    if row is None:
        return
    if outcome.clocking:
        row["clocking"] = {**(row.get("clocking") or {}), **outcome.clocking}
    if outcome.deviation:
        # a re-derivation that came back EMPTY (too sparse a footprint at the new pose)
        # writes None over the old numbers on purpose: "missing" is the honest reading
        # of a pose nobody could measure, and the acceptance catalog already renders it
        # that way. Keeping the pre-rework figures would be the stale-row bug again.
        row.update(outcome.deviation)
    if outcome.stale_metrics:
        row["rework"] = {"stale_metrics": list(outcome.stale_metrics)}
    else:
        row.pop("rework", None)
    if outcome.nudge is not None and outcome.operation != "best-fit":
        row["nudge"] = outcome.nudge
    if outcome.best_fit is not None:
        row["best_fit"] = outcome.best_fit
    elif outcome.operation == "rotation-reset":
        row.pop("best_fit", None)
    for name in outcome.files:
        if name not in run.package_files:
            run.package_files.append(name)


def _land(store: SessionStore, case: CaseRecord, tooth: int, run_id: str,
          outcome: AdjustOutcome) -> CaseSession:
    """Persist what an APPLIED tool did, inside one CAS mutation.

    The run pointer is re-judged on the fresh document: the physics already wrote into
    the run directory, so a pointer that moved means the adjustment landed on a run
    that is now history. It stays recorded THERE (the site record's own append-only
    ``adjustments`` list) and this session refuses rather than claiming it as current."""
    def apply(session: CaseSession) -> None:
        run = _require_verdict(session, case.id, tooth)
        if (run.run_id or run.job_id) != run_id:
            raise HTTPException(409, f"case {case.id!r} changed while the adjustment "
                                     f"was computing — the rework is recorded in its "
                                     f"own run directory as history, but that run is "
                                     f"no longer the case's current one; re-read the "
                                     f"case")
        site = session.sites[str(tooth)]
        # the ladder's own move — never a status assigned by hand (AM-4). READY falls
        # here by construction: the pose the review attested has moved.
        site.status = status.adjust(site.status)
        _fold_outcome(run, tooth, outcome)
        # the stage was worked in — a fact about the session, derived from the act
        session.adjust_visited = True
        # THE EVIDENCE BOUNDARY (session.clear_confirmation): a confirmed case whose
        # fits moved is not confirmed any more, and a release over the old evidence
        # is retired with it.
        clear_confirmation(session)

    try:
        return _mutate_session(store, case.id, apply)
    except status.IllegalTransition as exc:
        raise HTTPException(422, str(exc))


def _result(case: CaseRecord, session: CaseSession, settings: Settings,
            outcome: AdjustOutcome) -> AdjustResultView:
    return AdjustResultView(
        outcome=AdjustOutcomeView(
            tooth=outcome.tooth, operation=outcome.operation, detail=outcome.detail,
            applied=outcome.applied, files=list(outcome.files),
            clocking=outcome.clocking, deviation=outcome.deviation,
            stale_metrics=list(outcome.stale_metrics), nudge=outcome.nudge,
            applied_delta_deg=outcome.applied_delta_deg,
            cumulative_deg=outcome.cumulative_deg,
            stability_excess_mm=outcome.stability_excess_mm,
            best_fit=outcome.best_fit, pairs=list(outcome.pairs),
            residual_rms_mm=outcome.residual_rms_mm,
            click_azimuth_deg=outcome.click_azimuth_deg,
            matched_feature_azimuth_deg=outcome.matched_feature_azimuth_deg),
        pane_payload=outcome.pane_payload,
        case=_detail(case, session, settings))


def _refuse(exc: Exception):
    """THE REFUSAL SPLIT, in the demo's own statuses. ``AlreadyOptimal`` alone carries
    a structured detail — the one refusal that is really a PASS, so the surface can
    render it green with a one-click widen instead of re-shipping the refusal tone the
    demo learned to regret. Every other refusal stays a plain sentence, because every
    other refusal really is one."""
    if isinstance(exc, AlreadyOptimal):
        raise HTTPException(409, {"kind": "already_optimal", "message": str(exc),
                                  "matching_diameter_mm": exc.matching_diameter_mm,
                                  "suggested_diameter_mm": exc.suggested_diameter_mm})
    if isinstance(exc, AdjustRefused):
        raise HTTPException(409, str(exc))
    raise HTTPException(422, str(exc))


def _tool_context(request: Request, case_id: str, tooth: int):
    """The pre-physics judgment every tool shares: the case, the fresh session, the
    site's precondition and the run directory the tools rewrite in place."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    _require_known_tooth(case, session, tooth)
    run = _require_verdict(session, case_id, tooth)
    return settings, store, case, run, _run_dir(settings, case_id, run)


def _apply_tool(request: Request, case_id: str, tooth: int, run_tool) -> AdjustResultView:
    """Judge → run the physics (outside the mutation: it takes seconds and a CAS retry
    must never re-run it) → land. A measure-only outcome lands nothing and says so."""
    settings, store, case, run, run_dir = _tool_context(request, case_id, tooth)
    try:
        outcome = run_tool(case, run_dir)
    except (AdjustInvalid, AdjustRefused, UnknownSelection, ScanUnreadable) as exc:
        _refuse(exc)
    if not outcome.applied:
        # MEASURE ONLY: judged, reported, and NOT written — no rung moves, no
        # confirmation falls, nothing is persisted at all
        return _result(case, store.load(case_id), settings, outcome)
    session = _land(store, case, tooth, run.run_id or run.job_id, outcome)
    return _result(case, session, settings, outcome)


# --- the read the panes open on ------------------------------------------------------------

@router.get("/{case_id}/sites/{tooth}/seated")
def site_seated(case_id: str, tooth: int, request: Request) -> dict:
    """The site's SHIPPED pose as the three panes render it — the same payload shape
    Declare's preview serves, from the same builder, so a pose read before and after a
    rework is the same instrument on the same scale. ``preview: false`` on this one:
    the colouring describes a shipped pose, not a pre-run seat.

    A pure read: it writes nothing (pinned by test)."""
    _settings, _store, case, _run, run_dir = _tool_context(request, case_id, tooth)
    try:
        return seated_payload(case, run_dir, tooth)
    except (AdjustInvalid, AdjustRefused, UnknownSelection, ScanUnreadable) as exc:
        _refuse(exc)


@router.get("/{case_id}/sites/{tooth}/landmarks")
def site_landmarks(case_id: str, tooth: int, request: Request) -> List[dict]:
    """AUTO-MARK'S PROPOSAL (client 2026-07-29, item 3) — the part half of every
    correspondence pair, read off the site's declared template instead of hunted for by
    eye. Best clock evidence FIRST (``clock_landmarks`` sorts by lever arm descending):
    the operator's first click buys the most.

    Every landmark served here has already passed ``PartFeature.defines_rotation``, so
    a pair built on one cannot fail the part-side lever rule — and STRUCTURALLY, not by
    a warning, it also cannot become the diametral span the scan-side lever guard
    (``require_clock_lever``) exists to catch: a landmark drawn from the coded band
    never sits near the axis, so the pair it seeds never can either. The operator's
    whole remaining job is recognising the SAME feature in a noisy scan — the one half
    only a human can do.

    A pure read, GET-only like ``seated`` (no allowlist entry needed: the allowlist
    governs writes). It stands on the same precondition — a done run, a verdict for
    this tooth, a site on ready|flagged|adjusted — and writes nothing at all."""
    _settings, _store, case, _run, run_dir = _tool_context(request, case_id, tooth)
    try:
        return clock_landmarks(load_site(case, run_dir, tooth).template)
    except (AdjustInvalid, AdjustRefused, UnknownSelection, ScanUnreadable) as exc:
        _refuse(exc)


# --- the four tools -------------------------------------------------------------------------

@router.post("/{case_id}/sites/{tooth}/rotation", response_model=AdjustResultView)
def post_rotation(case_id: str, tooth: int, body: RotationIn,
                  request: Request) -> AdjustResultView:
    """THE ROTATION DIAL: gated steps about the seated part's own axis, read against
    the coded-cutout residual. ``reset`` restores the pipeline's certified pose — the
    only move that needs no re-judging, because it IS the pipeline's own output."""
    return _apply_tool(request, case_id, tooth, lambda case, run_dir: rotate_site(
        case, run_dir, tooth, step_deg=body.step_deg, reset=body.reset))


@router.post("/{case_id}/sites/{tooth}/mark-trench", response_model=AdjustResultView)
def post_mark_trench(case_id: str, tooth: int, body: MarkTrenchIn,
                     request: Request) -> AdjustResultView:
    """MARK TRENCH: one click on the scan's coded cutout, and the cap rotates so its
    NEAREST code feature lands there — through the same gates as every other rotation.
    A template carrying no coded relief refuses (409): there is nothing to align to."""
    return _apply_tool(request, case_id, tooth, lambda case, run_dir: align_to_mark(
        case, run_dir, tooth, body.scan_point))


@router.post("/{case_id}/sites/{tooth}/fit-by-points", response_model=AdjustResultView)
def post_fit_by_points(case_id: str, tooth: int, body: FitByPointsIn,
                       request: Request) -> AdjustResultView:
    """FIT BY POINTS: the operator names a feature on the part and where they see it on
    the scan — one click, or BOTH ENDS of it (the two-point span, plan §5). Several
    pairs give a QC number the operator can read: each observation's residual at its
    own lever arm, and their RMS."""
    pairs = [Correspondence(scan_point=p.scan_point, scan_point_end=p.scan_point_end,
                            feature_id=p.feature_id, part_point=p.part_point)
             for p in body.pairs]
    return _apply_tool(request, case_id, tooth,
                       lambda case, run_dir: align_to_correspondence(
                           case, run_dir, tooth, pairs))


@router.post("/{case_id}/sites/{tooth}/best-fit", response_model=AdjustResultView)
def post_best_fit(case_id: str, tooth: int, body: BestFitIn,
                  request: Request) -> AdjustResultView:
    """BEST FIT: the pipeline's OWN bounded refinement at the operator's chosen
    matching diameter, judged by the same certification bounds. The already-optimal
    outcome is a PASS with its widen attached, never a bare refusal (see ``_refuse``)."""
    return _apply_tool(request, case_id, tooth, lambda case, run_dir: best_fit_site(
        case, run_dir, tooth, matching_diameter_mm=body.matching_diameter_mm,
        apply=body.apply))
