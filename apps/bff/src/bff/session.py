"""THE SESSION STORE (plan §3, grill AM-4): per-case flow state, persisted and derived.

One JSON document per case under ``<product_root>/<case>/session.json`` — site-queue
statuses, adjust-visited, the run receipt, the confirmation record, ``payment_authorized``.
Rehydrated on BFF start and re-read per request: a restart mid-morning loses nothing,
least of all at the money-adjacent step.

STATUSES ARE NEVER ACCEPTED FROM CLIENTS — structurally. No endpoint takes a session
field from a request body (the case-session resources are GET-only, and their test
asserts that on the route table); every mutation enters through THIS module, called by
server-side flow logic in later slices. A presentational app PATCHing a flagged site to
``ready`` is impossible, not merely unstyled.

Failure posture: a corrupt session file REFUSES loudly (naming the file) instead of
silently starting fresh — a quiet reset would forget a confirmation or a payment
authorization, which is exactly the state this store exists to protect. Writes are
atomic (tmp file + ``os.replace``) so a crash mid-save leaves the previous session, not
half a document.
"""
from __future__ import annotations

import enum
import os
from pathlib import Path
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


class SiteStatus(str, enum.Enum):
    """The site queue's states (plan §2) — DERIVED by the BFF from worker facts and
    operator acts: detected → declared → previewed → ready | flagged → adjusted."""

    DETECTED = "detected"
    DECLARED = "declared"
    PREVIEWED = "previewed"
    READY = "ready"
    FLAGGED = "flagged"
    ADJUSTED = "adjusted"


class SiteSession(BaseModel):
    status: SiteStatus = SiteStatus.DETECTED
    declared_variant: Optional[str] = None


class RunSession(BaseModel):
    """The job-shaped run receipt (grill AM-3) — mirrors ``bff.ports.worker.JobState``
    so the SQS adapter later changes an adapter, not this record."""

    job_id: str
    state: Literal["queued", "running", "done", "refused"]
    refusal: Optional[str] = None


class ConfirmationRecord(BaseModel):
    """Sealed by Deliver (plan §6): who confirmed WHAT, verifiable at release time.
    Defined now so the read model's shape is stable; slice 8 writes it."""

    confirmed_at: str
    actor: str
    evidence_hash: str


class CaseSession(BaseModel):
    case_id: str
    # phase-2 carries a tenant on every case from day one (grill AM-3)
    tenant_id: str = "local"
    # keyed by tooth number as a string (JSON object keys are strings; kept honest here)
    sites: Dict[str, SiteSession] = Field(default_factory=dict)
    adjust_visited: bool = False
    run: Optional[RunSession] = None
    confirmation: Optional[ConfirmationRecord] = None
    # fail-closed: only the payment hook (slice 8) ever sets this
    payment_authorized: bool = False


class SessionStore:
    """File-backed, deliberately boring: no in-memory authority that a restart could
    lose. ``load`` is a pure read (asking creates nothing); ``save`` creates the case
    directory on first write."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, case_id: str) -> Path:
        # the id becomes a path segment — refuse anything that could leave the root
        if (not case_id or case_id.startswith(".")
                or "/" in case_id or "\\" in case_id):
            raise ValueError(f"invalid case id {case_id!r}")
        return self.root / case_id / "session.json"

    def load(self, case_id: str) -> CaseSession:
        path = self._path(case_id)
        if not path.is_file():
            return CaseSession(case_id=case_id)
        try:
            return CaseSession.model_validate_json(path.read_text())
        except Exception as exc:
            raise ValueError(
                f"corrupt session file {path} — refusing to silently reset flow state "
                f"(it may hold a confirmation or payment record): {exc}") from exc

    def save(self, session: CaseSession) -> None:
        path = self._path(session.case_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(session.model_dump_json(indent=2))
        os.replace(tmp, path)

    def rehydrate(self) -> Dict[str, CaseSession]:
        """Every persisted session, parsed — called at startup so a corrupt file fails
        the boot loudly instead of a random later request."""
        if not self.root.is_dir():
            return {}
        return {p.parent.name: self.load(p.parent.name)
                for p in sorted(self.root.glob("*/session.json"))}
