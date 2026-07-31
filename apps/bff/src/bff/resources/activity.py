"""THE ACTIVITY RESOURCE (gap ``session-activity-log``, 2026-07-31): what happened to
this case, read back.

``GET /api/case-sessions/{id}/activity`` — one document, two sources, both of them
records somebody already wrote:

  1. THE SESSION'S OWN NARRATIVE (``bff.session.record_activity``): the newest
     ``ACTIVITY_WINDOW`` acts, each appended inside the very CAS mutation that landed
     the act it names. Nothing here was ever POSTed — see the session module for why a
     client-writable log would be a channel for writing claims into the record.
  2. THE PER-SITE REWORK PROVENANCE THE WORKER ALREADY KEEPS. Every adopted adjustment
     appends ``{ts, operation, who, detail, evidence}`` to an append-only
     ``adjustments`` list on the run directory's ``<case>-<tooth>-implant.json``
     (``case_prep.application.adjust._finish_adjustment``). It has been written since
     slice 6 and no endpoint ever read it back, so the geometry's own history was
     invisible to the surface that caused it.

GET-ONLY, and EVIDENCE class in the AM-1 sense: a narrative is not a deliverable, and
an operator must be able to read what happened to a case before deciding anything about
it. Reading writes nothing.

ITS OWN MODULE because it reads across two seams — the session store and the run
directory — and neither existing resource owns both: ``case_sessions`` cannot reach the
run directory's path shape without importing ``deliver`` (which imports it back), and
``deliver`` is the DISCLOSURE edge, which this is not.
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from case_prep.application.adjust import implant_record_path

from ..session import ACTIVITY_WINDOW, CaseSession, RunSession
from .case_sessions import _case_or_404, _context
from .deliver import _run_dir

router = APIRouter(prefix="/api/case-sessions", tags=["activity"])


class ActivityEntryView(BaseModel):
    """One session act, verbatim from the record. No actor: this layer authenticates
    nobody (the three signed records' own posture), and ``at`` is the fact the act
    genuinely produced."""

    at: str
    event: str
    detail: str
    tooth: Optional[int] = None


class SiteAdjustmentView(BaseModel):
    """One entry off a site's shipped record, as the worker wrote it.

    ``who`` is carried VERBATIM — it reads "operator (no identity is captured)",
    which is the worker's own way of recording that a human acted while declining to
    invent a name for them. Rewriting it here would drop the disclaimer and leave the
    word "operator" looking like an identity.

    ``evidence`` (the operator's own points, when the tool had any) is deliberately
    NOT projected: it is a geometry payload, it belongs to the run directory, and a
    narrative that inlined it would grow without bound."""

    tooth: int
    at: str
    operation: str
    who: str
    detail: str


class CaseActivityView(BaseModel):
    """The case's narrative. ``entries`` are NEWEST FIRST — a log is read from the
    thing that just happened backwards, and ordering it server-side means every
    surface reads the same order.

    ``recorded`` is every act ever recorded, ``window`` how many this log keeps: the
    two together are what stop a bounded list from being read as a complete audit
    trail. When ``recorded`` exceeds ``window`` the difference is real history this
    document cannot show, and saying so is the honest half of keeping the session
    document small enough to re-read per request."""

    case_id: str
    entries: List[ActivityEntryView] = Field(default_factory=list)
    recorded: int
    window: int
    # the run these per-site adjustments belong to; None when no current run exists
    run_id: Optional[str] = None
    site_adjustments: List[SiteAdjustmentView] = Field(default_factory=list)


def _site_adjustments(settings, case_id: str,
                      run: Optional[RunSession]) -> List[SiteAdjustmentView]:
    """Every site's shipped-record adjustments for the CURRENT run, oldest first.

    Only the current run's: a landed run directory is immutable history and stays on
    disk, but this document describes the case as it stands, and folding a retired
    run's rework into it would narrate a pose the case no longer ships.

    A record that is missing, unreadable or shaped unexpectedly contributes NOTHING
    rather than raising — the worklist's per-row error contract applied here: one bad
    file must not take down the whole narrative. The file is the worker's, this module
    only reads it, and a read that cannot parse it has no better answer than silence.
    """
    if run is None or run.state != "done":
        return []
    run_dir = _run_dir(settings, case_id, run)
    out: List[SiteAdjustmentView] = []
    for row in (run.summary or {}).get("sites") or []:
        try:
            tooth = int(row.get("tooth"))
        except (TypeError, ValueError):
            continue
        path = implant_record_path(run_dir, case_id, tooth)
        try:
            record = json.loads(path.read_text())
            entries = record.get("adjustments") or []
        except (OSError, ValueError, AttributeError):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            out.append(SiteAdjustmentView(
                tooth=tooth,
                at=str(entry.get("ts") or ""),
                operation=str(entry.get("operation") or ""),
                who=str(entry.get("who") or ""),
                detail=str(entry.get("detail") or ""),
            ))
    # by WHEN across sites — a case's rework reads as one story, not as N per-site
    # ones; the tooth breaks ties so two same-second entries keep a stable order
    return sorted(out, key=lambda a: (a.at, a.tooth))


def _activity_view(session: CaseSession, settings) -> CaseActivityView:
    run = session.run
    return CaseActivityView(
        case_id=session.case_id,
        # newest first — the store keeps them in the order they landed
        entries=[ActivityEntryView(**entry.model_dump())
                 for entry in reversed(session.activity)],
        recorded=session.activity_recorded,
        window=ACTIVITY_WINDOW,
        run_id=(run.run_id or run.job_id) if run is not None else None,
        site_adjustments=_site_adjustments(settings, session.case_id, run),
    )


@router.get("/{case_id}/activity", response_model=CaseActivityView)
def case_activity(case_id: str, request: Request) -> CaseActivityView:
    """The case's narrative. A case nobody has touched answers with an honestly empty
    log rather than a 404: "nothing has happened yet" is an answer, and it is true."""
    settings, store = _context(request)
    _case_or_404(settings, case_id)
    try:
        session = store.load(case_id)
    except ValueError as exc:
        # the store's refusal, verbatim (its one home for those words): a corrupt
        # session is faced here as everywhere else, never papered over
        raise HTTPException(409, str(exc))
    return _activity_view(session, settings)
