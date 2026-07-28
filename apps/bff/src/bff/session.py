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
from typing import Dict, List, Literal, Optional, Tuple

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


class SeatedSelection(BaseModel):
    """WHAT a site's preview actually seated (plan §4 Declare / AM-8; the 2026-07-28
    effective-default drift finding): the full selection — system, construction,
    variant, jaw, relief — recorded beside the seat facts. The effective fallbacks
    (the case's suggestions, the standing relief default) live OUTSIDE this document
    and can change with no reset boundary firing, so a READY rung alone cannot prove
    the review still describes the case: THIS record is what the proof compares.
    Written only by the preview route from the selection the BFF itself minted (a
    server derivation, never a client claim — AM-4 holds); values only, no
    attribution, so pinning a suggestion as an explicit act flips no equality. The
    run gate refuses any READY site whose record no longer matches the case's
    current selection, and a re-preview whose seat differs drops READY through
    ``bff.status.reseat_preview`` instead of repainting under a standing tick."""

    model: str
    construction_path: str
    variant: str
    jaw: Optional[str] = None
    gingival_offset_mm: float


class SiteSession(BaseModel):
    status: SiteStatus = SiteStatus.DETECTED
    declared_variant: Optional[str] = None
    # THE PREVIEW'S SEAT FACTS (plan §7 slice 5b): the two numbers the operator judges
    # a seat by, persisted by the preview route from what the application derived —
    # worker facts, never a client's. The payload's mesh is response-only and never
    # stored; these clear at every reset boundary (see ``clear_preview_facts``).
    seat_method: Optional[str] = None
    rim_agreement_mm: Optional[float] = None
    # the seat RECORD (2026-07-28): the selection those facts were derived with —
    # None on documents persisted before the record existed, which the run gate
    # treats as unverifiable (fail-closed: re-preview + re-review once)
    seated_selection: Optional[SeatedSelection] = None

    def clear_preview_facts(self) -> None:
        """The reset boundaries' ONE home for forgetting a preview's facts — called
        beside every status event that invalidates a preview (a re-declaration, the
        system switch, a choices change), so a fact and the rung that justified it
        can never drift apart."""
        self.seat_method = None
        self.rim_agreement_mm = None
        self.seated_selection = None


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
        """All three choices EXPLICITLY made — the raw-acts fact. The wire's
        completion (worklist ``choices_complete``, the detail's ``choices.
        complete``) is the EFFECTIVE one since the 2026-07-27 automation ask —
        derived in ``resources.case_sessions._effective_choices``, where the
        case's suggestions and the standing relief default count too."""
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
    # "failed" is in the vocabulary because the PORT can report it (the tie holds both
    # directions); the in-process route never persists it — a crash WITHDRAWS the
    # queued receipt and serves a 500, so nothing wedges — but phase-2's async
    # landing will write it back, and the receipt must already speak the word.
    state: Literal["queued", "running", "done", "refused", "failed"]
    refusal: Optional[str] = None
    # the immutable run directory's name; equals job_id under the in-process adapter,
    # kept separate because phase-2's queue mints job ids the dir name must outlive
    run_id: Optional[str] = None
    summary: Optional[dict] = None
    package_files: List[str] = Field(default_factory=list)


"""THE THREE SIGNED RECORDS CARRY NO ACTOR (client 2026-07-27: "WE dont need
operator name the checkmark is sufficient").

Until this change each record held an ``operator`` string taken verbatim from an
``X-Operator`` header. Behind no authentication that was not identity — it was a
text field anyone could type anything into — and persisting it made the records
LOOK rigorous while proving nothing. What each record now stands on is the ACT
itself (a run authorized only by per-site attestations, a confirmation sealed over
re-derivable evidence) plus ``at``: WHEN is a fact the act genuinely produced.
Real identity arrives with real auth (plan §8 / phase-2), where a name will mean
something. The field is GONE rather than nullable — a column that could only ever
hold None would document an intention nobody has."""


class ConfirmationRecord(BaseModel):
    """Sealed by Deliver (plan §6, grill AM-10/AM-12): WHAT was confirmed, and when.

    ``evidence_sha256`` is the content address of the bundle the confirm route wrote
    under the run directory — release RE-DERIVES the evidence and compares, so this
    record is a claim that gets re-verified, never trusted (a rival change between
    confirm and release 409s by construction). ``dispositions`` are the operator's
    per-site ACTS (release | withhold, keyed by tooth-as-string — JSON object keys);
    ``acknowledged_flags`` are the flagged teeth the operator acknowledged ROW BY ROW
    (AM-12: a flag is never confirmed in bulk)."""

    at: str
    run_id: str
    evidence_sha256: str
    dispositions: Dict[str, str] = Field(default_factory=dict)
    acknowledged_flags: List[int] = Field(default_factory=list)


class PaymentRecord(BaseModel):
    """THE PAYMENT STUB (plan §4 Deliver): fail-closed — this record exists only
    when someone explicitly authorized, and ``provider: "stub"`` keeps
    stub-authorized sessions PERMANENTLY distinguishable from paid ones once a real
    provider lands. Never faked deeper than this: no amounts, no receipts, no
    provider ids — inventing those would be a lie wearing a schema."""

    payment_authorized: bool
    provider: str
    at: str


class AdjustDecisionRecord(BaseModel):
    """THE FORK, RECORDED (client 2026-07-27: "Skipping adjust should be optional we
    should have two options one to skip and another to delivery — Delivery vs Skip
    Adjustments").

    Declare's single Continue hid a decision: with nothing flagged it walked past
    Adjust silently, and the case's own record could never say whether the fits were
    reworked or waved through. This is that decision made EXPLICIT and kept — an ACT
    ("what the operator DID"), never a status claim: it moves no site, opens and
    closes no stage (flow reachability is untouched — skip never blocks navigating
    to Adjust), and a later decision simply REPLACES it (newest act wins).

    Keyed to ``run_id`` because a decision is about THESE verdicts: the run boundary
    clears it with the run pointer (``clear_current_run``), so a decision can never
    outlive the evidence it was made over. The decision WORD rides into the evidence
    bundle, so what a client confirms includes whether adjustments were skipped."""

    decision: Literal["skip", "adjust"]
    at: str
    run_id: str


class ReleaseRecord(BaseModel):
    """The disclosure act (plan §4: release = disclosure; grill AM-1): WHAT was
    released — over which run and which sealed evidence, and which teeth the
    released set actually carries (withheld sites dropped and stayed open). The
    artifact endpoints re-verify this record against the current run and the
    re-derived evidence on every read — screen order is not a control."""

    at: str
    run_id: str
    evidence_sha256: str
    released_teeth: List[int] = Field(default_factory=list)


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
    # the Delivery-vs-Skip fork (client 2026-07-27), keyed to the current run and
    # cleared with it by ``clear_current_run``; None = the fork was never faced
    adjust_decision: Optional[AdjustDecisionRecord] = None
    confirmation: Optional[ConfirmationRecord] = None
    # fail-closed: only the payment stub route (slice 8) ever writes this record;
    # its absence IS "not authorized" (pre-8 documents persisted a bare
    # ``payment_authorized: false`` — always false, ignored on load)
    payment: Optional[PaymentRecord] = None
    # the disclosure act (slice 8); validity against the CURRENT run is judged at
    # read time by the artifact endpoints, never assumed from the record existing
    release: Optional[ReleaseRecord] = None

    @property
    def payment_authorized(self) -> bool:
        """Derived, fail-closed: authorized exactly when the stub record says so."""
        return self.payment is not None and self.payment.payment_authorized


def clear_current_run(session: "CaseSession") -> None:
    """THE RUN BOUNDARY'S ONE HOME (5c's rule, given a name when the adjust decision
    joined it): every reset boundary — a choices change, a system switch, a
    re-declaration — clears the CURRENT-run pointer so stale physics never
    masquerades as current. The FORK falls with it: a decision to skip or rework
    adjustments was made over THOSE verdicts, and verdicts that no longer describe
    the case cannot carry a decision forward. One function, so a later fact keyed to
    the run cannot be forgotten at one boundary and cleared at the other two."""
    session.run = None
    session.adjust_decision = None


_QC_SUFFIX = ".png"


def tooth_of_file(name: str, case_id: str, teeth: List[int]) -> Optional[int]:
    """File→site attribution, ANCHORED to the pipeline's own construction: every
    per-tooth file the worker emits is ``f"{case_id}-{tooth}-…"`` (adapters/
    output_package.py — caps, scan bodies, sidecars, QC renders alike), so a file
    belongs to tooth ``t`` exactly when it starts with ``f"{case_id}-{t}-"``. At most
    one tooth can match (tooth numbers carry no dash), so the answer cannot depend on
    the order ``teeth`` arrives in. The previous anywhere-substring scan attributed by
    ascending-tooth luck: an operator-typed case id ending in ``-4`` claimed every
    other tooth's file for tooth 4 — a disclosure hazard at the artifact gate (AM-1),
    not a cosmetic one. Anything unanchored is case-wide, and case-wide files ship
    only when NO site is withheld (``split_released_files``).

    Lives HERE, not in the deliver resource, since the Deliver surface needed the
    same split BEFORE release (to say what a release would disclose) as after it:
    two derivations of "what ships" would be two answers waiting to disagree."""
    for tooth in teeth:
        if name.startswith(f"{case_id}-{tooth}-"):
            return tooth
    return None


def split_released_files(package_files: List[str], summary_teeth: List[int],
                         released_teeth: List[int],
                         case_id: str) -> Tuple[List[str], List[str]]:
    """The released set and the case-wide files held back, package order kept.

    A file attributed to a tooth ships iff that tooth is released. A file attributed
    to NO tooth is case-wide, and case-wide files ship only when no site is withheld
    — fail-closed by construction: the worker's own notes say the overlay merges ALL
    aligned components and the manifest carries every site's row and file hashes
    (adapters/output_package.py), and any case-wide file this rule has never heard of
    gets the same benefit of NO doubt. A partial release ships exactly the released
    sites' own files (AM-1: release = disclosure, and a withheld site's geometry must
    not ride out inside an aggregate).

    Takes the released TEETH rather than a release record so the same function can
    answer "what would this confirmation disclose?" before any release exists."""
    withheld = set(summary_teeth) - set(released_teeth)
    files: List[str] = []
    held_case_files: List[str] = []
    for name in package_files:
        if name.endswith(_QC_SUFFIX):
            continue   # EVIDENCE class — never an artifact
        tooth = tooth_of_file(name, case_id, summary_teeth)
        if tooth is None and withheld:
            held_case_files.append(name)
        elif tooth not in withheld:
            files.append(name)
    return files, held_case_files


def summary_teeth_of(run: "RunSession") -> List[int]:
    """The teeth the run's summary carries, in its own order."""
    summary = run.summary or {}
    return [int(r.get("tooth")) for r in (summary.get("sites") or [])]


def released_teeth_of(dispositions: Dict[str, str]) -> List[int]:
    """The released set a disposition map implies — sorted ints (the map's keys are
    tooth-as-string JSON keys). ONE derivation, shared by the release route (sealing
    the record), the artifact gate and the display half: the same map must never
    imply two different sets in two places."""
    return sorted(int(t) for t, act in dispositions.items() if act == "release")


def release_matches_confirmation(session: "CaseSession") -> bool:
    """The record-consistency half of release validity (plan §4: validity is
    re-derivation, never trust in a record). Dispositions are deliberately NOT part
    of the evidence bundle — they are the operator's acts, not the run's facts — so
    a re-confirm that changes one moves no evidence hash, and the artifact gate
    must compare the records themselves: the release is valid only while it still
    covers the CURRENT confirmation (same run, same sealed evidence, and a released
    set equal to what the confirmation's dispositions imply NOW). A withhold signed
    after release therefore RETIRES the release — the operator's newest signed act
    wins, and disclosure stops until an explicit re-release."""
    release, confirmation = session.release, session.confirmation
    return (release is not None and confirmation is not None
            and release.run_id == confirmation.run_id
            and release.evidence_sha256 == confirmation.evidence_sha256
            and release.released_teeth
            == released_teeth_of(confirmation.dispositions))


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
