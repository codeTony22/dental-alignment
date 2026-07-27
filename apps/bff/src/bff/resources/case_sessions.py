"""THE CASE-SESSION READ MODEL (plan §3, §7 slice 1; grill AM-2/AM-4/AM-7).

Two GET resources and nothing else:

  - ``GET /api/case-sessions`` — the worklist: one row per discovered case with its
    site-queue rollup and run/confirmation state. The 20-scan morning's home screen.
  - ``GET /api/case-sessions/{id}`` — flow-shaped: the case, its sites (worker-suggested,
    overlaid with session state), the catalogs Declare renders from, the relief ceiling
    per declared variant, and the session's own state.

Every fact is DERIVED: cases and suggestions from ``case_prep.application.cases``,
catalogs and ceilings from ``case_prep.application.catalog`` (the physics stays in the
worker), statuses from the session store. GET-only is a tested structural property — the
store is the single mutation door, and it is server-side (see bff.session).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import (UnknownSelection, construction_parts,
                                           library_groups, relief_ceiling)

from ..config import Settings
from ..session import CaseSession, SessionStore, SiteStatus

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


class SiteView(BaseModel):
    tooth: int
    status: str
    declared_variant: Optional[str]     # the session's (an operator act), never inferred
    suggested_variant: Optional[str]    # the curated suggestion the UI may prefill
    center: Optional[List[float]]       # a coordinate FACT from intake, passed through


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
    session: SessionView


# --- derivations ------------------------------------------------------------------------

def _site_views(case: CaseRecord, session: CaseSession) -> List[SiteView]:
    """Worker-suggested sites overlaid with session state; session-only sites (a later
    slice can add one at Declare) still render."""
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
        )
    for key, sess in session.sites.items():
        tooth = int(key)
        if tooth not in views:
            views[tooth] = SiteView(tooth=tooth, status=sess.status.value,
                                    declared_variant=sess.declared_variant,
                                    suggested_variant=None, center=None)
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


def _ceilings(case: CaseRecord, sites: List[SiteView],
              settings: Settings) -> List[ReliefCeilingView]:
    """One ceiling per DECLARED variant (session first, curated suggestion else), read
    against the case's suggested system+construction. Without both selections there is
    nothing meaningful to measure — the list is honestly empty, never guessed (client
    directive 2026-07-25)."""
    if case.suggested_model is None or case.suggested_construction is None:
        return []
    variants = sorted({v for v in
                       (s.declared_variant or s.suggested_variant for s in sites)
                       if v is not None})
    out = []
    for variant in variants:
        try:
            out.append(ReliefCeilingView(**relief_ceiling(
                settings.data_root, case.suggested_construction,
                case.suggested_model, variant)))
        except UnknownSelection as exc:
            out.append(ReliefCeilingView(variant=variant, error=str(exc)))
    return out


# --- resources --------------------------------------------------------------------------

def _context(request: Request):
    settings: Settings = request.app.state.settings
    store: SessionStore = request.app.state.sessions
    return settings, store


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
        ))
    return rows


@router.get("/{case_id}", response_model=CaseSessionDetail)
def case_session(case_id: str, request: Request) -> CaseSessionDetail:
    settings, store = _context(request)
    case = next((c for c in discover_cases(settings.data_root) if c.id == case_id), None)
    if case is None:
        raise HTTPException(404, f"unknown case {case_id!r}")
    session = store.load(case_id)
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
        relief_ceilings=_ceilings(case, sites, settings),
        session=SessionView(
            tenant_id=session.tenant_id,
            adjust_visited=session.adjust_visited,
            run_state=_run_state(session),
            confirmed=session.confirmation is not None,
            payment_authorized=session.payment_authorized,
        ),
    )
