"""THE SESSION STORE (plan §3, grill AM-4): per-case flow state, persisted and derived.

One JSON document per case under ``<product_root>/<case>/session.json`` — site-queue
statuses, adjust-visited, the run receipt, the confirmation record, ``payment_authorized``.
Rehydrated on BFF start and re-read per request: a restart mid-morning loses nothing,
least of all at the money-adjacent step.

STATUSES ARE NEVER ACCEPTED FROM CLIENTS — structurally. Since slice 4 the resource is
no longer GET-only (choices and compute triggers are legitimate writes), but no request
body may carry a status/verdict/gate-shaped field — asserted on the route table AND the
request models by test_case_sessions' allowlist test; every status mutation still enters
through THIS module, called by server-side flow logic. A presentational app PATCHing a
flagged site to ``ready`` is impossible, not merely unstyled.

Failure posture: a corrupt session file REFUSES loudly (naming the file) instead of
silently starting fresh — a quiet reset would forget a confirmation or a payment
authorization, which is exactly the state this store exists to protect. Writes are
atomic (tmp file + ``os.replace``) so a crash mid-save leaves the previous session, not
half a document.

Writes are also COMPARE-AND-SWAP (slice 5a): every document carries ``version``, and
``save`` refuses (``SessionConflict``) when the disk has moved past the version the
caller loaded — the durable answer to the lost-update race slice 4's detect route
dodged by hand (commit 1c4af60 named this store change as slice 5's obligation). With
choices, system and per-site declarations all writing the same document, "last save
wins" would silently discard operator acts — the write-write cousin of the client
claims AM-4 forbids. Handlers retry once on a fresh load, then surface a 409. The
check-then-write pair holds under an in-process lock (5a fix): FastAPI runs sync
handlers on a threadpool, so rival saves genuinely overlap even with one uvicorn
worker — cross-PROCESS CAS remains the SQLite/phase-2 story (plan §3).
"""
from __future__ import annotations

import enum
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SessionConflict(RuntimeError):
    """A CAS save lost: the disk's version is no longer the one the caller loaded.
    Carries both versions so a handler's 409 can say what happened instead of a bare
    "conflict" — the caller re-loads and re-applies, or the operator re-reads."""

    def __init__(self, case_id: str, expected: int, found: int):
        super().__init__(
            f"session {case_id!r} changed underneath this write: loaded version "
            f"{expected}, but the disk holds version {found}")
        self.case_id = case_id
        self.expected = expected
        self.found = found


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
    # THE PREVIEW'S SEAT FACTS (plan §7 slice 5b): the two numbers the operator judges
    # a seat by, persisted by the preview route from what the application derived —
    # worker facts, never a client's. The payload's mesh is response-only and never
    # stored; these clear at every reset boundary (see ``clear_preview_facts``).
    seat_method: Optional[str] = None
    rim_agreement_mm: Optional[float] = None

    def clear_preview_facts(self) -> None:
        """The reset boundaries' ONE home for forgetting a preview's facts — called
        beside every status event that invalidates a preview (a re-declaration, the
        system switch, a choices change), so a fact and the rung that justified it
        can never drift apart."""
        self.seat_method = None
        self.rim_agreement_mm = None


class CaseChoices(BaseModel):
    """The CASE-LEVEL operator choices (plan §4 Intake): the construction part, the jaw,
    the gingival relief ask. OPERATOR ACTS, never derived — the one kind of write the
    doctrine allows in (see test_case_sessions' allowlist test) — and each is honestly
    None until the operator has actually made it: no field here is ever pre-filled
    server-side from a suggestion (the lab chooses, the software never guesses)."""

    construction_path: Optional[str] = None
    jaw: Optional[str] = None
    gingival_offset_mm: Optional[float] = None

    @property
    def complete(self) -> bool:
        """All three choices explicitly made — the fact Intake's completion tick reads."""
        return (self.construction_path is not None and self.jaw is not None
                and self.gingival_offset_mm is not None)


class DetectedProposal(BaseModel):
    """One persisted detector proposal (application.detection.DetectedSite, serialized):
    a world-space centre, the detector's evidence numbers, the NON-BINDING tooth guess,
    and the site's capture assessment — worker facts, written only by the detect route."""

    center: List[float]
    void_ratio: float
    rim_below_cusps_mm: float
    tooth_guess: Optional[int] = None
    capture: dict


class DetectionRecord(BaseModel):
    """The persisted product of automatic detection (plan §4: detection fires on Intake,
    verdicts surface BEFORE work is invested). ``site_capture`` keys the CURATED sites'
    capture verdicts by tooth (string keys — JSON objects; same honesty as ``sites``)."""

    proposals: List[DetectedProposal] = Field(default_factory=list)
    site_capture: Dict[str, dict] = Field(default_factory=dict)


class RunSession(BaseModel):
    """The job-shaped run receipt (grill AM-3) — mirrors ``bff.ports.worker.JobState``
    (tied by test_worker_port.TestStateTie) so the SQS adapter later changes an
    adapter, not this record.

    Since 5c it also carries THE RUN FACTS the landing persisted: the worker's
    summary VERBATIM (per-site verdict rows, the relief outcome — scalars, no
    meshes) and the package file list as names RELATIVE to the immutable run
    directory ``runs/<run_id>/`` (AM-1). The mesh-heavy payloads stay on disk in
    that directory; session.json stays small (pinned by test_run_resource's size
    test) because the store re-reads it per request. This receipt is the CURRENT-run
    pointer only: the reset boundaries clear it (a stale run never masquerades as
    current) while the run directory survives as immutable history."""

    job_id: str
    state: Literal["queued", "running", "done", "refused"]
    refusal: Optional[str] = None
    # the immutable run directory's name; equals job_id under the in-process adapter,
    # kept separate because phase-2's queue mints job ids the dir name must outlive
    run_id: Optional[str] = None
    summary: Optional[dict] = None
    package_files: List[str] = Field(default_factory=list)


class ConfirmationRecord(BaseModel):
    """Sealed by Deliver (plan §6): who confirmed WHAT, verifiable at release time.
    Defined now so the read model's shape is stable; slice 8 writes it."""

    confirmed_at: str
    actor: str
    evidence_hash: str


class CaseSession(BaseModel):
    case_id: str
    # the CAS version (slice 5a): bumped by every save; a save whose loaded version
    # is stale refuses. Pre-5a documents carry none and default to 0 honestly.
    version: int = 0
    # phase-2 carries a tenant on every case from day one (grill AM-3)
    tenant_id: str = "local"
    # the case-scoped implant SYSTEM (plan §4 Declare / AM-8): the operator's explicit
    # case-level act, None until declared (the detail falls back to the case's
    # suggestion and SAYS which one it served). Switching it resets every site —
    # enforced by the system route through bff/status.py, never assumed here.
    system: Optional[str] = None
    # keyed by tooth number as a string (JSON object keys are strings; kept honest here)
    sites: Dict[str, SiteSession] = Field(default_factory=dict)
    # worker facts, persisted by the detect route; None = detection has not run yet
    detection: Optional[DetectionRecord] = None
    # operator acts, persisted by the choices route
    choices: CaseChoices = Field(default_factory=CaseChoices)
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
        # save()'s check-then-write must be atomic across THREADS: sync handlers run
        # on FastAPI's threadpool, so two same-case writes overlap even in the
        # one-uvicorn-worker deployment (the 5a verification watched both rivals pass
        # the version check unlocked — a silent lost update, every pair). One lock per
        # store: saves are millisecond file writes, per-case locks are not worth it.
        self._lock = threading.Lock()

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
        """Compare-and-swap: refuse when the disk's version is not the one this
        object was loaded at (``SessionConflict`` carries both), else bump and write.
        The bump lands on the caller's object too, so a handler may keep mutating and
        save again without a wasted re-load.

        The pair runs under the store's lock because it must be atomic across
        THREADS, not just uninterrupted by luck: one uvicorn worker still runs sync
        handlers on a threadpool, and unlocked, two rivals both passed the version
        check at the same loaded version (a silent lost update) while racing onto one
        shared tmp filename (``FileNotFoundError`` → 500) — the 5a verification's
        finding. The tmp name is unique per save as well, so even a SECOND process —
        outside this lock's reach — can at worst lose the CAS race, never crash a
        rival's replace mid-flight; true cross-process CAS is the SQLite/phase-2
        story (plan §3)."""
        path = self._path(session.case_id)
        with self._lock:
            current = self.load(session.case_id)   # version 0 when nothing exists yet
            if current.version != session.version:
                raise SessionConflict(session.case_id, session.version, current.version)
            session.version += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                tmp.write_text(session.model_dump_json(indent=2))
                os.replace(tmp, path)
            finally:
                # a failed write may leave its uniquely-named tmp behind — remove it
                # so the "nothing beside session.json" promise survives the failure
                tmp.unlink(missing_ok=True)

    def rehydrate(self) -> Dict[str, CaseSession]:
        """Every persisted session, parsed — called at startup so a corrupt file fails
        the boot loudly instead of a random later request."""
        if not self.root.is_dir():
            return {}
        return {p.parent.name: self.load(p.parent.name)
                for p in sorted(self.root.glob("*/session.json"))}
