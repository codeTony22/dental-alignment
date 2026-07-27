"""THE CASE-SESSION RESOURCE (plan §3, §4 Intake, §7 slices 1+4; grill AM-2/AM-4/AM-7).

The read model (slice 1):

  - ``GET /api/case-sessions`` — the worklist: one row per discovered case with its
    site-queue rollup and run/confirmation state. The 20-scan morning's home screen.
  - ``GET /api/case-sessions/{id}`` — flow-shaped: the case, its sites (worker-suggested,
    overlaid with session state and capture verdicts), the catalogs Declare renders from,
    the relief ceiling per declared variant, the detection record, the operator's
    case-level choices, and the session's own state.

The first ACTIONS (slice 4) — writes that carry no claimed outcomes:

  - ``POST /api/case-sessions/{id}/detect`` — runs ``application.detection`` and persists
    the result (worker FACTS). No request body at all; ``?fresh=1`` re-derives.
  - ``PUT /api/case-sessions/{id}/choices`` — the case-level OPERATOR CHOICES only
    (construction part, jaw, relief). The request model is the start of the validation
    corpus (plan §6/AM-9, copy-debt ledger row 4).

Every status is still DERIVED: cases and suggestions from ``case_prep.application``,
statuses from the session store. The doctrine is structural and tested: every non-GET
route sits on an explicit allowlist, and no request model carries a status-shaped field
(see test_case_sessions.TestStatusesAreNeverClientWritable).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import (UnknownSelection, construction_parts,
                                           DEFAULT_GINGIVAL_OFFSET_MM, library_groups,
                                           relief_ceiling, require_construction)
from case_prep.application.detection import DetectionResult, ScanUnreadable, detect

from ..config import Settings
from ..session import (CaseChoices, CaseSession, DetectedProposal, DetectionRecord,
                       SessionStore, SiteStatus)

router = APIRouter(prefix="/api/case-sessions", tags=["case-sessions"])


# --- response models: presentation-shaped, no physics -----------------------------------

class SiteRollup(BaseModel):
    total: int
    declared: int   # sites past "detected" — an operator act has touched them
    ready: int
    flagged: int


class WorklistRow(BaseModel):
    id: str
    doctor: str
    jaw: str
    suggested_model: Optional[str]
    sites: SiteRollup
    run_state: str          # "none" | queued | running | done | refused (AM-3 states)
    confirmed: bool
    # Intake's completion facts (plan §4 / slice 4), derived server-side like the rest:
    detected: bool          # a detection record exists for this session
    choices_complete: bool  # all three case-level choices explicitly made


class SiteView(BaseModel):
    tooth: int
    status: str
    declared_variant: Optional[str]     # the session's (an operator act), never inferred
    suggested_variant: Optional[str]    # the curated suggestion the UI may prefill
    center: Optional[List[float]]       # a coordinate FACT from intake, passed through
    # the worker's capture assessment (CaptureAssessment.to_dict), once detection ran —
    # the chair-side verdict Intake surfaces BEFORE any work is invested (plan §4)
    capture: Optional[dict] = None


class DetectedProposalView(BaseModel):
    """A detector proposal: centre + evidence + the NON-BINDING tooth guess + capture."""

    center: List[float]
    void_ratio: float
    rim_below_cusps_mm: float
    tooth_guess: Optional[int]
    capture: dict


class DetectionView(BaseModel):
    proposals: List[DetectedProposalView]


class ChoicesView(BaseModel):
    """The operator's case-level choices as persisted (None = not yet made), plus the
    facts the UI needs to render them honestly: the worker's default relief ask and the
    server-derived completion verdict (the UI never computes completion itself)."""

    construction_path: Optional[str]
    jaw: Optional[str]
    gingival_offset_mm: Optional[float]
    gingival_offset_default_mm: float
    complete: bool


class CaseView(BaseModel):
    id: str
    doctor: str
    jaw: str
    scan_filename: str
    suggested_model: Optional[str]
    suggested_construction: Optional[str]


class CatalogView(BaseModel):
    groups: List[dict]          # the full flagged library catalog (worker-shaped rows)
    constructions: List[dict]   # vendor construction parts, picked by path_id


class ReliefCeilingView(BaseModel):
    """One (construction x variant) ceiling — the worker's reading verbatim, or the
    refusal as an ``error`` row so one bad variant cannot take the resource down."""

    variant: str
    construction_path: Optional[str] = None
    model: Optional[str] = None
    max_safe_mm: Optional[float] = None
    requested_default_mm: Optional[float] = None
    default_is_safe: Optional[bool] = None
    limited_by: Optional[str] = None
    wall_mm_at_zero: Optional[float] = None
    wall_mm_at_default: Optional[float] = None
    shippable_at_zero: Optional[bool] = None
    min_wall_rule_mm: Optional[float] = None
    searched_to_mm: Optional[float] = None
    note: Optional[str] = None
    error: Optional[str] = None


class SessionView(BaseModel):
    tenant_id: str
    adjust_visited: bool
    run_state: str
    confirmed: bool
    payment_authorized: bool


class CaseSessionDetail(BaseModel):
    case: CaseView
    sites: List[SiteView]
    catalog: CatalogView
    relief_ceilings: List[ReliefCeilingView]
    detection: Optional[DetectionView]
    choices: ChoicesView
    session: SessionView


# --- request models: THE VALIDATION CORPUS BEGINS HERE (plan §6/AM-9, ledger row 4) -----

JAWS = ("upper", "lower")            # server.py:215, verbatim

# A gingival relief is a fraction of a millimetre; anything past this is a typo, not a
# clinical intent (the part would be eaten away). Bound, not a silent clamp.
# server.py:165-167, verbatim.
_MAX_GINGIVAL_OFFSET_MM = 1.0


class ChoicesIn(BaseModel):
    """The case-level operator choices — the ONLY payload the choices route accepts.

    The rules are the frozen demo's, copied VERBATIM from server.py's ``RunIn``
    validators (jaw: 253-258; relief bounds incl. finiteness: 260-266) — the UI is
    untrusted and the BFF re-validates everything (plan §6). Divergences, recorded in
    ledger row 4: fields are Optional (choices arrive one PUT at a time; None is "not
    chosen yet", never a guessed default) and ``np.isfinite`` became ``math.isfinite``
    (identical semantics; the BFF owns no numpy). Construction-part membership is
    checked in the handler — it needs the data tree, and the refusal sentence lives in
    ``application.catalog.require_construction`` (one home).

    NO status-shaped field may ever join this model — the allowlist test introspects it.
    """

    construction_path: Optional[str] = None
    jaw: Optional[str] = None
    gingival_offset_mm: Optional[float] = None

    @field_validator("jaw")
    @classmethod
    def _known_jaw(cls, v):
        if v is not None and v not in JAWS:
            raise ValueError(f"jaw must be one of {', '.join(JAWS)}, got {v!r}")
        return v

    @field_validator("gingival_offset_mm")
    @classmethod
    def _sane_offset(cls, v):
        if v is None:
            return v
        if not math.isfinite(v) or v < 0.0 or v > _MAX_GINGIVAL_OFFSET_MM:
            raise ValueError(f"gingival_offset_mm must be a clearance between 0 and "
                             f"{_MAX_GINGIVAL_OFFSET_MM}mm, got {v!r}")
        return float(v)


# --- derivations ------------------------------------------------------------------------

def _site_views(case: CaseRecord, session: CaseSession) -> List[SiteView]:
    """Worker-suggested sites overlaid with session state; session-only sites (a later
    slice can add one at Declare) still render. Capture verdicts join from the session's
    detection record — worker facts, persisted by the detect route, never a client's."""
    capture: Dict[str, dict] = (
        session.detection.site_capture if session.detection is not None else {})
    views = {}
    for s in case.suggested_sites:
        tooth = int(s["tooth"])
        sess = session.sites.get(str(tooth))
        views[tooth] = SiteView(
            tooth=tooth,
            status=(sess.status.value if sess else SiteStatus.DETECTED.value),
            declared_variant=(sess.declared_variant if sess else None),
            suggested_variant=s.get("declared_variant"),
            center=s.get("center"),
            capture=capture.get(str(tooth)),
        )
    for key, sess in session.sites.items():
        tooth = int(key)
        if tooth not in views:
            views[tooth] = SiteView(tooth=tooth, status=sess.status.value,
                                    declared_variant=sess.declared_variant,
                                    suggested_variant=None, center=None,
                                    capture=capture.get(key))
    return [views[t] for t in sorted(views)]


def _rollup(sites: List[SiteView]) -> SiteRollup:
    return SiteRollup(
        total=len(sites),
        declared=sum(1 for s in sites if s.status != SiteStatus.DETECTED.value),
        ready=sum(1 for s in sites if s.status == SiteStatus.READY.value),
        flagged=sum(1 for s in sites if s.status == SiteStatus.FLAGGED.value),
    )


def _run_state(session: CaseSession) -> str:
    return session.run.state if session.run is not None else "none"


def _ceilings(case: CaseRecord, session: CaseSession, sites: List[SiteView],
              settings: Settings) -> List[ReliefCeilingView]:
    """One ceiling per DECLARED variant (session first, curated suggestion else), read
    against the CHOSEN construction part the moment one is chosen (plan §4: the relief
    input lives beside its ceiling at Intake, so the ceiling must follow the operator's
    pick, not the name-matched suggestion). The SYSTEM stays the case's suggestion until
    Declare's system bar exists (slice 5a). Without a system+construction there is
    nothing meaningful to measure — the list is honestly empty, never guessed."""
    construction = session.choices.construction_path or case.suggested_construction
    if case.suggested_model is None or construction is None:
        return []
    variants = sorted({v for v in
                       (s.declared_variant or s.suggested_variant for s in sites)
                       if v is not None})
    out = []
    for variant in variants:
        try:
            out.append(ReliefCeilingView(**relief_ceiling(
                settings.data_root, construction,
                case.suggested_model, variant)))
        except UnknownSelection as exc:
            out.append(ReliefCeilingView(variant=variant, error=str(exc)))
    return out


def _detection_record(result: DetectionResult) -> DetectionRecord:
    """application.detection's result, shaped for the session store."""
    return DetectionRecord(
        proposals=[DetectedProposal(
            center=list(p.center), void_ratio=p.void_ratio,
            rim_below_cusps_mm=p.rim_below_cusps_mm,
            tooth_guess=p.tooth_guess, capture=p.capture,
        ) for p in result.proposals],
        site_capture={str(s.tooth): s.capture for s in result.suggested},
    )


def _detection_view(session: CaseSession) -> Optional[DetectionView]:
    if session.detection is None:
        return None
    return DetectionView(proposals=[
        DetectedProposalView(**p.model_dump()) for p in session.detection.proposals])


def _choices_view(session: CaseSession) -> ChoicesView:
    return ChoicesView(
        construction_path=session.choices.construction_path,
        jaw=session.choices.jaw,
        gingival_offset_mm=session.choices.gingival_offset_mm,
        gingival_offset_default_mm=DEFAULT_GINGIVAL_OFFSET_MM,
        complete=session.choices.complete,
    )


def _detail(case: CaseRecord, session: CaseSession,
            settings: Settings) -> CaseSessionDetail:
    """The one flow-shaped assembly — GET detail and both actions return it, so the UI
    always renders what the server derived (trust direction, AM-4)."""
    sites = _site_views(case, session)
    return CaseSessionDetail(
        case=CaseView(
            id=case.id, doctor=case.doctor, jaw=case.jaw,
            scan_filename=case.scan.name,
            suggested_model=case.suggested_model,
            suggested_construction=case.suggested_construction,
        ),
        sites=sites,
        catalog=CatalogView(
            groups=library_groups(settings.data_root),
            constructions=construction_parts(settings.data_root),
        ),
        relief_ceilings=_ceilings(case, session, sites, settings),
        detection=_detection_view(session),
        choices=_choices_view(session),
        session=SessionView(
            tenant_id=session.tenant_id,
            adjust_visited=session.adjust_visited,
            run_state=_run_state(session),
            confirmed=session.confirmation is not None,
            payment_authorized=session.payment_authorized,
        ),
    )


# --- resources --------------------------------------------------------------------------

def _context(request: Request):
    settings: Settings = request.app.state.settings
    store: SessionStore = request.app.state.sessions
    return settings, store


def _case_or_404(settings: Settings, case_id: str) -> CaseRecord:
    case = next((c for c in discover_cases(settings.data_root) if c.id == case_id), None)
    if case is None:
        raise HTTPException(404, f"unknown case {case_id!r}")
    return case


@router.get("", response_model=List[WorklistRow])
def worklist(request: Request) -> List[WorklistRow]:
    settings, store = _context(request)
    rows = []
    for case in discover_cases(settings.data_root):
        session = store.load(case.id)
        sites = _site_views(case, session)
        rows.append(WorklistRow(
            id=case.id, doctor=case.doctor, jaw=case.jaw,
            suggested_model=case.suggested_model,
            sites=_rollup(sites),
            run_state=_run_state(session),
            confirmed=session.confirmation is not None,
            detected=session.detection is not None,
            choices_complete=session.choices.complete,
        ))
    return rows


@router.get("/{case_id}/scan")
def case_scan(case_id: str, request: Request) -> FileResponse:
    """The case's scan STL, streamed for the product's main stage (plan §7 slice 3).

    The file path comes from the application layer's CaseRecord — discovery picked it,
    so no client-supplied path ever reaches the filesystem. Read-only like the detail
    resource; the same 404 refusal shape.
    """
    settings, _store = _context(request)
    case = _case_or_404(settings, case_id)
    # "model/stl" is the emerging IANA-style label; FileResponse would otherwise guess
    # application/octet-stream, which tells the viewer nothing.
    return FileResponse(case.scan, media_type="model/stl", filename=case.scan.name)


@router.get("/{case_id}", response_model=CaseSessionDetail)
def case_session(case_id: str, request: Request) -> CaseSessionDetail:
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    return _detail(case, store.load(case_id), settings)


@router.post("/{case_id}/detect", response_model=CaseSessionDetail)
def detect_case(case_id: str, request: Request, fresh: bool = False) -> CaseSessionDetail:
    """Run automatic detection and persist its FACTS into the session (plan §4: detection
    fires on Intake, capture verdicts surface before work is invested).

    A compute TRIGGER, not a state claim: the request carries no body at all — what gets
    persisted is what ``application.detection`` derived, never what a client asserted.
    Idempotent by design: a session already detected returns its current state untouched;
    ``?fresh=1`` is the explicit re-ask (a rescanned case re-derives, the demo's own
    ``fresh`` semantics). The worker's refusal (an unreadable scan) maps to 422 in its
    own sentence.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    if session.detection is None or fresh:
        try:
            result = detect(case)
        except ScanUnreadable as exc:
            raise HTTPException(422, str(exc))
        # detect() runs for many SECONDS on a real scan, and Intake auto-fires it while
        # the choices panel stays live — a choices PUT can land mid-derivation. Saving
        # the session loaded ABOVE would clobber that PUT with its stale document,
        # silently discarding an operator act (the write-write cousin of the client
        # claims AM-4 forbids; found by the slice-4 adversarial review). So: re-load
        # AFTER the derivation and write ONLY the detection facts onto the fresh
        # document. A store compare-and-swap is the durable answer once more writers
        # exist (slice 5).
        session = store.load(case_id)
        session.detection = _detection_record(result)
        store.save(session)
    return _detail(case, session, settings)


@router.put("/{case_id}/choices", response_model=CaseSessionDetail)
def put_choices(case_id: str, body: ChoicesIn, request: Request) -> CaseSessionDetail:
    """Persist the operator's case-level choices — the whole document, replaced (PUT
    semantics: what you send is what is chosen; omitting a field un-chooses it, so the
    UI always submits its full current panel). Construction membership is checked here
    against the catalog (never a path join); jaw and relief were already refused by the
    request model in the demo's own words.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    if body.construction_path is not None:
        try:
            require_construction(settings.data_root, body.construction_path)
        except UnknownSelection as exc:
            raise HTTPException(422, str(exc))
    session = store.load(case_id)
    session.choices = CaseChoices(
        construction_path=body.construction_path,
        jaw=body.jaw,
        gingival_offset_mm=body.gingival_offset_mm,
    )
    store.save(session)
    return _detail(case, session, settings)
