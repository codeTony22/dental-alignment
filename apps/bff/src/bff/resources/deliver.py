"""THE DELIVER RESOURCE (plan §4 Deliver, §6; grill AM-1/AM-10/AM-11/AM-12): the
disclosure edge — the one place the BFF decides what leaves the building.

TWO CLASSES OF DISCLOSURE (AM-1, the plan's corrected FATAL), stated here because this
module enforces the boundary:

  1. EVIDENCE — the assurance summary (per-site numbers, gate and clamp words, QC
     images) — is visible BEFORE any confirmation: signing over visible evidence is
     the whole design (plan §1.4). ``GET .../assurance`` and ``GET .../runs/current/
     qc/{filename}`` are UNGATED (no confirmation, no payment).
  2. DELIVERABLE ARTIFACTS — the STLs and package files a mill consumes — disclose
     ONLY behind a still-valid confirmation AND payment (slice 8-ii's release-gated
     artifact endpoints). Anything that is not a QC image refuses on the evidence
     endpoints and points at the artifact class.

The assurance projection is EXACTLY that — a projection: every number, word and
verdict comes from the persisted run summary (the worker's, verbatim) and the
acceptance catalog (``case_prep.domain.acceptance`` — the backend's own pairing of
each measured number with the industry reference the doctor already knows). No new
physics; sorted worst-first SERVER-side (AM-12: exception-first — flagged rows are
pinned above the fold, then the worse gate leads).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from case_prep.application.cases import CaseRecord
from case_prep.domain.acceptance import evaluate_acceptance

from ..config import Settings
from ..evidence import canonical_bundle, qc_image_hashes, write_bundle
from ..session import (CaseSession, ConfirmationRecord, PaymentRecord,
                       ReleaseRecord, RunSession, SessionConflict, SessionStore,
                       release_matches_confirmation, released_teeth_of)
from .case_sessions import (CaseSessionDetail, _case_or_404, _context, _detail,
                            _mutate_session)

router = APIRouter(prefix="/api/case-sessions", tags=["deliver"])


# --- response models --------------------------------------------------------------------

class AssuranceRotation(BaseModel):
    """The cap's rotation as the run measured it: degrees, the instrument the answer
    came from, and whether the pipeline itself called it unverified."""

    deg: Optional[float] = None
    evidence: Optional[str] = None
    unverified: bool = False


class AssuranceClamp(BaseModel):
    """The relief clamp story per site (the production block's own fields): what the
    lab asked, what was applied, and the pipeline's reason when they differ."""

    requested_mm: Optional[float] = None
    applied_mm: Optional[float] = None
    clamped: bool = False
    reason: Optional[str] = None


class AssuranceGate(BaseModel):
    """The run's guidance verdict verbatim — the level and the exact action words
    the operator confirms over."""

    level: str
    actions: List[str] = Field(default_factory=list)


class AssuranceSite(BaseModel):
    """One verdict-table row. Facts only: the summary row's numbers, the session's
    ladder rung, and the acceptance catalog's reference pairings — nothing derived
    that the worker or the domain has not already said."""

    tooth: int
    status: Optional[str]              # the session ladder's rung (flagged | ready)
    declared_variant: Optional[str]
    identified_variant: Optional[str]
    # the backend's own word for the identity check: match | mismatch | undeclared
    variant_agreement: Optional[str]
    seat_method: Optional[str]
    rim_agreement_mm: Optional[float]
    rotation: AssuranceRotation
    deviation_rms_mm: Optional[float]
    deviation_p90_mm: Optional[float]
    gate: AssuranceGate
    clamp: AssuranceClamp
    # this site's QC images, by run-relative name (the qc endpoint serves them)
    qc_images: List[str] = Field(default_factory=list)
    # the acceptance catalog's rows for the numerics this table serves, VERBATIM
    # (label, unit, value, display, band, industry_ref, note) keyed by metric key —
    # worker/domain-shaped like the catalog views: the domain payload is the schema
    references: Dict[str, dict] = Field(default_factory=dict)


class AssuranceView(BaseModel):
    case_id: str
    run_id: str
    # the case-level relief outcome verbatim (requested/applied/clamped) — part of
    # what the evidence bundle must cover, so it is part of what the operator sees
    relief: Optional[dict] = None
    sites: List[AssuranceSite]


# --- the projection ---------------------------------------------------------------------

# the numerics the table serves, paired with their acceptance-catalog metric keys
# (the catalog pairs each with its industry reference — plan §2 "numbers vs industry
# refs" comes from the domain, never from presentation editorial)
_REFERENCE_KEYS = ("rim_agreement_mm", "deviation_rms_mm", "rotation_deg",
                   "cap_identity")

# worst-first within a status rung (AM-12): the worker's guidance vocabulary is
# ready < attention < action-needed (domain/guidance.py)
_GATE_SEVERITY = {"ready": 0, "attention": 1, "action-needed": 2}

_QC_SUFFIX = ".png"


def _require_done_run(session: CaseSession, case_id: str) -> RunSession:
    """Both evidence endpoints and every 8-ii gate stand on the same fact: a DONE
    current run. Refused/queued/crashed runs have no evidence to show or sign, and a
    cleared pointer means the case changed — 404 in one sentence for all of them."""
    run = session.run
    if run is None or run.state != "done" or run.summary is None:
        raise HTTPException(404, f"case {case_id!r} has no completed current run — "
                                 f"the assurance summary is the run's evidence, and "
                                 f"there is none to show yet")
    return run


def _qc_image_names(run: RunSession) -> List[str]:
    """The run's QC images = its package's PNGs. The package file list is the run's
    own claim (persisted at landing); the PNG suffix is the class boundary — QC
    renders are the only images the pipeline emits."""
    return [name for name in run.package_files if name.endswith(_QC_SUFFIX)]


def _site_qc_images(run: RunSession, case_id: str, tooth: int) -> List[str]:
    """This site's QC images by the pipeline's own naming (``<case>-<tooth>-*.png``,
    qc_render.py) — attributed by the same ANCHORED rule as the artifact gate
    (``_tooth_of_file``): a bare ``-<tooth>-`` substring scan mis-filed another
    site's evidence whenever the case id itself ends in a tooth number."""
    return sorted(n for n in _qc_image_names(run)
                  if _tooth_of_file(n, case_id, [tooth]) == tooth)


def _assurance_site(row: dict, session: CaseSession, run: RunSession,
                    case_id: str) -> AssuranceSite:
    tooth = int(row.get("tooth", -1))
    site = session.sites.get(str(tooth))
    clocking = row.get("clocking") if isinstance(row.get("clocking"), dict) else {}
    guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else {}
    production = (row.get("production")
                  if isinstance(row.get("production"), dict) else {})
    variant = row.get("variant") if isinstance(row.get("variant"), dict) else {}
    # the domain's evaluation — each numeric beside its industry reference, in the
    # backend's own words; a pure function of the row (no new physics)
    metrics = {m["key"]: m for m in evaluate_acceptance(row)["metrics"]}
    return AssuranceSite(
        tooth=tooth,
        status=(site.status.value if site is not None else None),
        declared_variant=variant.get("declared"),
        identified_variant=variant.get("identified"),
        variant_agreement=metrics["cap_identity"].get("value"),
        seat_method=row.get("seat_method"),
        rim_agreement_mm=row.get("rim_agreement_mm"),
        rotation=AssuranceRotation(
            deg=clocking.get("notch_shift_deg"),
            evidence=clocking.get("evidence"),
            unverified=bool(clocking.get("rotation_unverified")),
        ),
        deviation_rms_mm=row.get("deviation_rms_mm"),
        deviation_p90_mm=row.get("deviation_p90_mm"),
        gate=AssuranceGate(
            level=str(guidance.get("level") or "attention"),
            actions=[str(a) for a in (guidance.get("actions") or [])],
        ),
        clamp=AssuranceClamp(
            requested_mm=production.get("gingival_offset_requested_mm"),
            applied_mm=production.get("gingival_offset_applied_mm"),
            clamped=bool(production.get("clamped")),
            reason=production.get("clamp_reason"),
        ),
        qc_images=_site_qc_images(run, case_id, tooth),
        references={key: metrics[key] for key in _REFERENCE_KEYS if key in metrics},
    )


def _sort_worst_first(sites: List[AssuranceSite]) -> List[AssuranceSite]:
    """AM-12: flagged rows pinned first, then the worse gate, then tooth for a
    stable order across reloads. An unknown gate word sorts as worst — a vocabulary
    the sorter does not know is a reason to look, never to bury."""
    def key(site: AssuranceSite):
        flagged = 0 if site.status == "flagged" else 1
        severity = _GATE_SEVERITY.get(site.gate.level, len(_GATE_SEVERITY))
        return (flagged, -severity, site.tooth)
    return sorted(sites, key=key)


def derive_assurance(case: CaseRecord, session: CaseSession) -> AssuranceView:
    """The one assurance derivation — the GET serves it and 8-ii's confirmation
    seals it (the same document both times, so what the operator saw and what the
    seal covers can never diverge). Pure over the session given."""
    run = _require_done_run(session, case.id)
    summary = run.summary or {}
    sites = [_assurance_site(row, session, run, case.id)
             for row in (summary.get("sites") or [])]
    return AssuranceView(
        case_id=case.id,
        run_id=run.run_id or run.job_id,
        relief=summary.get("gingival_relief"),
        sites=_sort_worst_first(sites),
    )


# --- the evidence endpoints (class 1: ungated) ------------------------------------------

@router.get("/{case_id}/assurance", response_model=AssuranceView)
def case_assurance(case_id: str, request: Request) -> AssuranceView:
    """The per-site verdict table's data (AM-12) — EVIDENCE class, ungated: the
    operator must see this before any confirmation exists to give. 404 without a
    done current run. A pure projection: reading it writes nothing."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    return derive_assurance(case, store.load(case_id))


@router.get("/{case_id}/runs/current/qc/{filename}")
def case_qc_image(case_id: str, filename: str, request: Request) -> FileResponse:
    """One QC image's bytes — EVIDENCE class, ungated (AM-1: the images are part of
    what the operator confirms over, so they must be visible first).

    The filename validates against the RUN'S OWN package file list (no path ever
    comes from the client to the filesystem — the same posture as the scan route),
    and only QC images serve here: anything else in the package is a DELIVERABLE,
    refused with directions to the release-gated artifact endpoint (8-ii)."""
    settings, store = _context(request)
    _case_or_404(settings, case_id)
    session = store.load(case_id)
    run = _require_done_run(session, case_id)
    # defense in depth: an encoded slash survives the route match into the param,
    # so shape-refuse before the membership check ever touches a path
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(404, f"{filename!r} is not among the run's package "
                                 f"files")
    if filename not in run.package_files:
        raise HTTPException(404, f"{filename!r} is not among the run's package "
                                 f"files")
    if not filename.endswith(_QC_SUFFIX):
        raise HTTPException(403, f"{filename!r} is not a QC image — it is a "
                                 f"deliverable, and deliverable artifacts disclose "
                                 f"only through the release-gated artifact endpoint "
                                 f"(confirmation and payment first)")
    path = (settings.product_root / case_id / "runs"
            / (run.run_id or run.job_id) / filename)
    if not path.is_file():
        raise HTTPException(404, f"QC image {filename!r} is missing from the run "
                                 f"directory — the run's package claims it, but "
                                 f"the file is not there to serve")
    return FileResponse(path, media_type="image/png", filename=filename)


# --- no operator header, deliberately (client 2026-07-27) -------------------------------
#
# "WE dont need operator name the checkmark is sufficient."
#
# AM-11's named-session minimum lived here: an ``X-Operator`` header, required by a
# 422 on confirm/payment/release/artifacts and recorded verbatim on every record.
# It is GONE. A self-typed name behind no authentication was never identity — it was
# a text field — and recording it made the records LOOK rigorous while proving
# nothing. The ACT is the record now: a run authorized only by per-site attestations,
# a confirmation sealed over evidence that re-derives, a release that re-verifies
# both. Real identity arrives with real auth (plan §8 / phase-2), where it will mean
# something; until then these endpoints ask nobody's name and keep none.

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --- request models (operator ACTS — legitimate inputs, plan §6/AM-4) -------------------

class ConfirmIn(BaseModel):
    """The confirmation's body: per-site DISPOSITIONS (release | withhold, keyed by
    tooth-as-string) and the flagged teeth acknowledged ROW BY ROW (AM-12).

    These are operator ACTS, not claimed verdicts — the deliberate extension of the
    no-status-fields doctrine (test_case_sessions' allowlist carries the comment): a
    disposition says what the operator DOES with a site, never what the site IS; the
    site's status, gate and evidence all stay server-derived, and the server refuses
    any disposition set that does not match the evidence it derived itself."""

    model_config = ConfigDict(extra="forbid")

    dispositions: Dict[str, Literal["release", "withhold"]]
    acknowledged_flags: List[int] = Field(default_factory=list)


class PaymentIn(BaseModel):
    """The stub's body: the explicit act, nothing else. ``authorize`` must be
    literally true — the stub authorizes nothing implicitly, and there is no other
    field because inventing amounts or references would fake deeper than AM-11
    allows."""

    model_config = ConfigDict(extra="forbid")

    authorize: bool


# --- the gates' shared derivations ------------------------------------------------------

def _require_done_run_for_act(session: CaseSession, case_id: str,
                              act: str) -> RunSession:
    """The act-flavoured twin of ``_require_done_run``: acting (confirm/release/
    disclose) on a case without a completed current run is a CONFLICT with the
    case's state (409), where merely reading was a missing resource (404)."""
    run = session.run
    if run is None or run.state != "done" or run.summary is None:
        raise HTTPException(409, f"nothing to {act} — case {case_id!r} has no "
                                 f"completed current run; the assurance evidence "
                                 f"is the run's, and there is none")
    return run


def _run_dir(settings: Settings, case_id: str, run: RunSession) -> Path:
    return settings.product_root / case_id / "runs" / (run.run_id or run.job_id)


def _mutate_signing(store: SessionStore, case_id: str, mutate, act: str,
                    record_of):
    """The SIGNING acts' write path — confirm and release — deliberately NOT
    ``_mutate_session``: that helper retries a CAS loss on a fresh document, which
    is right for commutative acts (a choices write beside a slow detect loses
    neither) and WRONG for a signature — re-applying it over a rival's write
    erases the rival's record while both operators hold a 200: two winners with
    contradictory receipts. Here a CAS loss refuses outright (one winner), and
    when the rival write WAS the same kind of signing record, the 409 names whose
    act landed first so the loser re-reads deliberately instead of guessing.
    ``record_of`` picks the record this act signs (session→record), compared
    before/after the loss to tell a rival signature from an unrelated write.

    The 409 names WHEN the rival landed, not who: since the identity removal
    (client 2026-07-27) the record carries no name to print, and its timestamp is
    the fact the loser can actually check against what they re-read."""
    session = store.load(case_id)
    before = record_of(session)
    mutate(session)
    try:
        store.save(session)
        return session
    except SessionConflict as exc:
        rival = record_of(store.load(case_id))
        landed = (f" — another {act} landed first, at {rival.at}"
                  if rival is not None and rival != before else "")
        raise HTTPException(409, f"{exc}{landed}; nothing was recorded for this "
                                 f"{act} — re-read the case and repeat the act "
                                 f"over what is actually there now")


def _adjustments_of(session: CaseSession) -> Optional[str]:
    """The fork's decision WORD for the bundle (client 2026-07-27), or None where the
    fork was never faced. The value alone — the record's ``at``/``run_id`` are
    attribution, and re-deciding the same way describes the same case (the
    SeatedSelection precedent: values only, so an identical re-act flips no
    equality and costs nobody a re-confirmation)."""
    return (session.adjust_decision.decision
            if session.adjust_decision is not None else None)


def _derive_evidence_sha(case: CaseRecord, session: CaseSession,
                         settings: Settings, run: RunSession) -> str:
    """The re-derivation both release and the artifact gate stand on (plan §4:
    validity is re-derivation, never trust in a record): the assurance projection
    as it stands NOW, the QC images' bytes as they are NOW, and the adjust decision
    as it stands NOW — hashed by the same canonical rule the confirmation sealed. A
    missing QC image counts as drift — evidence that cannot be re-covered no longer
    matches anything."""
    assurance = derive_assurance(case, session)
    try:
        hashes = qc_image_hashes(_run_dir(settings, case_id=case.id, run=run),
                                 _qc_image_names(run))
    except FileNotFoundError:
        return "evidence-incomplete"   # never equals a sha256 hex digest
    return canonical_bundle(assurance.model_dump(mode="json"), hashes,
                            _adjustments_of(session)).sha256


def _summary_teeth(run: RunSession) -> List[int]:
    summary = run.summary or {}
    return [int(r.get("tooth")) for r in (summary.get("sites") or [])]


def _tooth_of_file(name: str, case_id: str, teeth: List[int]) -> Optional[int]:
    """File→site attribution, ANCHORED to the pipeline's own construction: every
    per-tooth file the worker emits is ``f"{case_id}-{tooth}-…"`` (adapters/
    output_package.py — caps, scan bodies, sidecars, QC renders alike), so a file
    belongs to tooth ``t`` exactly when it starts with ``f"{case_id}-{t}-"``. At
    most one tooth can match (tooth numbers carry no dash), so the answer cannot
    depend on the order ``teeth`` arrives in. The previous anywhere-substring scan
    attributed by ascending-tooth luck: an operator-typed case id ending in
    ``-4`` claimed every other tooth's file for tooth 4 — a disclosure hazard at
    the artifact gate (AM-1), not a cosmetic one. Anything unanchored is
    case-wide, and case-wide files ship only when NO site is withheld
    (``_split_released_files``)."""
    for tooth in teeth:
        if name.startswith(f"{case_id}-{tooth}-"):
            return tooth
    return None


# --- the confirmation (plan §6, grill AM-10/AM-12) --------------------------------------

@router.post("/{case_id}/confirm", response_model=CaseSessionDetail)
def confirm_case(case_id: str, body: ConfirmIn,
                 request: Request) -> CaseSessionDetail:
    """Seal the confirmation over the evidence as it stands NOW.

    Refuses unless: a done current run; EVERY site carries a disposition (each
    missing one named); every FLAGGED site dispositioned ``release`` appears in
    ``acknowledged_flags`` (AM-12 — row by row, never in bulk; an acknowledgment of
    an unflagged site is refused too, a claim about nothing). On success, INSIDE
    the CAS mutation: re-derive the assurance, hash the QC images' bytes, build and
    WRITE the evidence bundle — a failed write REFUSES the whole confirmation
    (AM-10's transactional half; the content-addressed write is idempotent, so the
    mutation's one CAS retry re-writes the same bytes harmlessly) — then persist
    the record."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        run = _require_done_run_for_act(session, case_id, "confirm")
        assurance = derive_assurance(case, session)
        teeth = [site.tooth for site in assurance.sites]
        known = {str(t) for t in teeth}
        missing = [t for t in teeth if str(t) not in body.dispositions]
        if missing:
            raise HTTPException(422, "every site needs a disposition — release or "
                                     "withhold, per row; still missing: "
                                     + ", ".join(f"tooth {t}" for t in missing))
        unknown = sorted(k for k in body.dispositions if k not in known)
        if unknown:
            raise HTTPException(422, "dispositions name sites this run does not "
                                     "carry: "
                                     + ", ".join(f"tooth {k}" for k in unknown))
        flagged = {site.tooth for site in assurance.sites
                   if site.status == "flagged"}
        acknowledged = set(body.acknowledged_flags)
        unacknowledged = [t for t in sorted(flagged)
                          if body.dispositions.get(str(t)) == "release"
                          and t not in acknowledged]
        if unacknowledged:
            # AM-12: the flag is confirmed ROW BY ROW — each unacknowledged one
            # is named; a bulk "yes to all flags" cannot exist on this wire
            raise HTTPException(422, "releasing a flagged site requires its own "
                                     "acknowledgment — still unacknowledged: "
                                     + ", ".join(f"tooth {t}"
                                                 for t in unacknowledged))
        over = sorted(acknowledged - flagged)
        if over:
            raise HTTPException(422, "acknowledged_flags names sites that are not "
                                     "flagged: "
                                     + ", ".join(f"tooth {t}" for t in over)
                                     + " — an acknowledgment must point at a real "
                                       "flag")
        run_dir = _run_dir(settings, case_id, run)
        try:
            hashes = qc_image_hashes(run_dir, _qc_image_names(run))
        except FileNotFoundError as exc:
            raise HTTPException(409, f"the confirmation is refused — the run's "
                                     f"package claims a QC image that is not on "
                                     f"disk to seal: {exc}")
        bundle = canonical_bundle(assurance.model_dump(mode="json"), hashes,
                                  _adjustments_of(session))
        try:
            write_bundle(run_dir, bundle)
        except OSError as exc:
            # AM-10: a confirmation whose bundle failed to persist never seals —
            # a hash with nothing on disk behind it could not be re-verified
            raise HTTPException(500, f"the evidence bundle could not be written — "
                                     f"the confirmation is refused, nothing was "
                                     f"sealed: {exc}")
        session.confirmation = ConfirmationRecord(
            at=_now(),
            run_id=run.run_id or run.job_id,
            evidence_sha256=bundle.sha256,
            dispositions=dict(body.dispositions),
            acknowledged_flags=list(body.acknowledged_flags),
        )

    session = _mutate_signing(store, case_id, apply, "confirmation",
                              lambda s: s.confirmation)
    return _detail(case, session, settings)


# --- the payment stub (grill AM-11) -----------------------------------------------------

@router.post("/{case_id}/payment", response_model=CaseSessionDetail)
def authorize_payment(case_id: str, body: PaymentIn,
                      request: Request) -> CaseSessionDetail:
    """Record the stubbed payment authorization — fail-closed (absence of this
    record IS "not authorized") and honest (``provider: "stub"`` marks the session
    permanently; when a real provider lands, its adapter replaces this route's
    body, and stub-authorized history stays tellable from paid history)."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    if not body.authorize:
        raise HTTPException(422, "the payment stub authorizes nothing implicitly — "
                                 "the act is {\"authorize\": true}, or no act at "
                                 "all")

    def apply(session: CaseSession) -> None:
        session.payment = PaymentRecord(payment_authorized=True, provider="stub",
                                        at=_now())

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- release = disclosure (plan §4/§6, grill AM-1) --------------------------------------

@router.post("/{case_id}/release", response_model=CaseSessionDetail)
def release_case(case_id: str, request: Request) -> CaseSessionDetail:
    """The disclosure act. Body-less: everything the release consumes — the
    confirmation, its dispositions, the payment state — is already the session's,
    so there is nothing a client could claim with.

    Refuses (409) unless: a done current run; a confirmation record; the
    RE-DERIVED evidence hashes to the confirmed sha256 (confirm → change → release
    is structurally a 409: validity is re-derivation, never trust in the record);
    and the stubbed payment is authorized. Persists WHAT was released, over which
    evidence, with the withheld sites already dropped from the released set."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        run = _require_done_run_for_act(session, case_id, "release")
        confirmation = session.confirmation
        if confirmation is None:
            raise HTTPException(409, f"case {case_id!r} is not confirmed — confirm "
                                     f"over the assurance evidence before release")
        current_sha = _derive_evidence_sha(case, session, settings, run)
        if current_sha != confirmation.evidence_sha256:
            raise HTTPException(409, "the case changed since it was confirmed — "
                                     "re-confirm over the current evidence")
        if not session.payment_authorized:
            raise HTTPException(409, f"payment is not authorized for case "
                                     f"{case_id!r} — the (stub) payment gate "
                                     f"precedes disclosure")
        session.release = ReleaseRecord(
            at=_now(),
            run_id=run.run_id or run.job_id,
            evidence_sha256=confirmation.evidence_sha256,
            # the ONE shared derivation (session.released_teeth_of): the gate and
            # the display half must read the identical set off the same map
            released_teeth=released_teeth_of(confirmation.dispositions),
        )

    session = _mutate_signing(store, case_id, apply, "release",
                              lambda s: s.release)
    return _detail(case, session, settings)


# --- the artifact endpoints (class 2: DELIVERABLES, gated) ------------------------------

class ArtifactsView(BaseModel):
    run_id: str
    # the released deliverables, package order preserved; QC images are the
    # EVIDENCE class and never appear here, withheld sites' per-tooth files are
    # excluded (they stay open, not shipped)
    files: List[str]
    withheld_teeth: List[int]
    # the case-wide files held back BECAUSE sites are withheld (empty on a full
    # release) — the list tells the whole truth about what did not ship and why
    withheld_case_files: List[str] = Field(default_factory=list)


def _require_valid_release(case: CaseRecord, session: CaseSession,
                           settings: Settings) -> Tuple[RunSession, ReleaseRecord]:
    """The artifact gate (AM-1's second class), enforced AT THE ENDPOINT — screen
    order in a presentational app is not a control. Refuses 409 stating exactly
    what is missing; validity means: done current run, a release record naming
    THAT run, a release that still covers the CURRENT confirmation
    (``release_matches_confirmation`` — dispositions live outside the evidence
    hash, so a re-confirmed withhold moves no sha and must be caught on the
    records themselves), and evidence that still re-derives to the sha the
    release sealed (post-release drift closes the door again until re-confirm +
    re-release)."""
    run = _require_done_run_for_act(session, case.id, "disclose artifacts for")
    release = session.release
    if release is None or release.run_id != (run.run_id or run.job_id):
        raise HTTPException(409, f"artifacts are not disclosed for case "
                                 f"{case.id!r} — no release record covers the "
                                 f"current run: confirm over the assurance "
                                 f"evidence, authorize payment (stub), then "
                                 f"release")
    if not release_matches_confirmation(session):
        # the operator's newest signed act wins: a withhold confirmed AFTER the
        # release retires it, and disclosure waits for an explicit re-release
        raise HTTPException(409, "the confirmation changed after release — the "
                                 "release no longer covers the operator's "
                                 "current dispositions; disclosure is closed "
                                 "until an explicit re-release over the current "
                                 "confirmation")
    current_sha = _derive_evidence_sha(case, session, settings, run)
    if current_sha != release.evidence_sha256:
        raise HTTPException(409, "the evidence changed after release — disclosure "
                                 "is closed until the case is re-confirmed and "
                                 "re-released over what is actually there now")
    return run, release


def _split_released_files(run: RunSession, release: ReleaseRecord,
                          case_id: str) -> Tuple[List[str], List[str]]:
    """The released set and the case-wide files held back, package order kept.

    A file attributed to a tooth ships iff that tooth is released. A file
    attributed to NO tooth is case-wide, and case-wide files ship only when no
    site is withheld — fail-closed by construction: the worker's own notes say
    the overlay merges ALL aligned components and the manifest carries every
    site's row and file hashes (adapters/output_package.py), and any case-wide
    file this gate has never heard of gets the same benefit of NO doubt. A
    partial release ships exactly the released sites' own files (AM-1: release
    = disclosure, and a withheld site's geometry must not ride out inside an
    aggregate)."""
    teeth = _summary_teeth(run)
    withheld = set(teeth) - set(release.released_teeth)
    files: List[str] = []
    held_case_files: List[str] = []
    for name in run.package_files:
        if name.endswith(_QC_SUFFIX):
            continue   # EVIDENCE class — never an artifact
        tooth = _tooth_of_file(name, case_id, teeth)
        if tooth is None and withheld:
            held_case_files.append(name)
        elif tooth not in withheld:
            files.append(name)
    return files, held_case_files


_ARTIFACT_MEDIA = {".stl": "model/stl", ".json": "application/json",
                   ".html": "text/html"}


@router.get("/{case_id}/runs/current/artifacts", response_model=ArtifactsView)
def list_artifacts(case_id: str, request: Request) -> ArtifactsView:
    """The DELIVERABLE list — even listing is disclosure (names leak what was
    made), so the release gate sits on the list too."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run, release = _require_valid_release(case, session, settings)
    withheld = sorted(set(_summary_teeth(run)) - set(release.released_teeth))
    files, held_case_files = _split_released_files(run, release, case.id)
    return ArtifactsView(run_id=run.run_id or run.job_id,
                         files=files,
                         withheld_teeth=withheld,
                         withheld_case_files=held_case_files)


@router.get("/{case_id}/runs/current/artifacts/{filename}")
def fetch_artifact(case_id: str, filename: str,
                   request: Request) -> FileResponse:
    """One deliverable's bytes — the disclosure edge itself. Filename validates
    against the run's own package list (no client path reaches the filesystem);
    QC images refuse toward the evidence endpoint; a withheld site's files refuse
    with the site's open status."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run, release = _require_valid_release(case, session, settings)
    if ("/" in filename or "\\" in filename or filename.startswith(".")
            or filename not in run.package_files):
        raise HTTPException(404, f"{filename!r} is not among the run's package "
                                 f"files")
    if filename.endswith(_QC_SUFFIX):
        raise HTTPException(403, f"{filename!r} is a QC image — evidence, not a "
                                 f"deliverable; it serves ungated from the qc "
                                 f"endpoint")
    teeth = _summary_teeth(run)
    withheld = sorted(set(teeth) - set(release.released_teeth))
    tooth = _tooth_of_file(filename, case_id, teeth)
    if tooth is not None and tooth in withheld:
        raise HTTPException(403, f"tooth {tooth} is withheld — its site stays "
                                 f"open and its files are not part of the "
                                 f"released set")
    if tooth is None and withheld:
        # fail-closed (AM-1): a case-wide file may aggregate every site — the
        # overlay merges all aligned components, the manifest carries every
        # site's row (the worker's own notes) — so none ships while any site is
        # withheld; the refusal names the open sites keeping it back
        raise HTTPException(403, f"{filename!r} is a case-wide file and sites "
                                 f"are withheld ("
                                 + ", ".join(f"tooth {t}" for t in withheld)
                                 + ") — case-wide files aggregate every site, "
                                   "so they release only when every site does")
    path = _run_dir(settings, case_id, run) / filename
    if not path.is_file():
        raise HTTPException(404, f"artifact {filename!r} is missing from the run "
                                 f"directory — the run's package claims it, but "
                                 f"the file is not there to serve")
    media = _ARTIFACT_MEDIA.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=filename)
