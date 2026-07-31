"""THE DELIVER RESOURCE (plan §4 Deliver, §6; grill AM-1/AM-10/AM-12): the
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
from ..pricing import InvoicePaymentView, InvoiceView, price_invoice
from ..session import (CaseSession, ConfirmationRecord, PaymentRecord,
                       ReleaseRecord, RunSession, SessionConflict, SessionStore,
                       adjustments_of, release_matches_confirmation,
                       released_teeth_of, split_released_files, summary_teeth_of,
                       tooth_of_file)
from .case_sessions import (CaseSessionDetail, _case_or_404, _context, _detail,
                            _effective_choices, _mutate_session)

router = APIRouter(prefix="/api/case-sessions", tags=["deliver"])
# the terms are a CASE-INDEPENDENT document: their own resource, not a
# sub-resource of whichever case happens to be citing them
terms_router = APIRouter(prefix="/api/terms", tags=["terms"])


# --- the terms (plan §10-A) ---------------------------------------------------------------
#
# Client, verbatim: "Delivery should be confirm and accept alginment and term and
# conditions, payment, and released artifacts." The agreement moves OFF Declare's
# per-site ticks and onto this one commercial signature — plan §10-A: "This can be
# at the time of payment … as a Terms and Conditions or more explicit saying someone
# reviewed the alignment changes and they agree to proceed."
#
# THE TEXT BELOW IS A PLACEHOLDER. It is NOT contractual language this codebase is
# entitled to invent — the real terms are the client's to supply, and until they do,
# this string stands in, marked as a placeholder both here and on screen
# (DeliverStage.tsx renders it inside an unmissable "PLACEHOLDER" banner). Swapping
# it for the client's real text is a ONE-STRING change; bump ``TERMS_VERSION``
# alongside it so a confirmation sealed over the old text reads honestly as having
# accepted THAT text, never silently reinterpreted as covering the new one.
TERMS_VERSION = "placeholder-v1"

TERMS_TEXT_PLACEHOLDER = (
    "PLACEHOLDER — pending the client's final Terms and Conditions text. "
    "I have reviewed the alignment for all N sites in this case, including the "
    "assurance report and its QC images. I accept the alignment as shown and "
    "authorize release of the deliverables."
)


# THE TERMS AS A RESOLVABLE DOCUMENT (client 2026-07-30: "shouldn't term and
# condition be a link and if clicked route to the proper pages").
#
# They are right, and the reason is stronger than layout. Every confirmation already
# records WHICH terms it accepted (``terms_version``, sealed into the evidence hash),
# but until now that string pointed at nothing: an auditor reading "placeholder-v1"
# in a sealed bundle had no way to obtain the text it names. Serving each version by
# id makes the recorded version RESOLVABLE — the evidence stops citing a document
# nobody can produce.
#
# Versions are additive, never edited in place: when the client's real text lands it
# becomes a NEW id, and a confirmation sealed over the old one still resolves to the
# text its signer actually saw. That is the whole point of recording a version.
TERMS_DOCUMENTS: Dict[str, Dict[str, str]] = {
    TERMS_VERSION: {
        "version": TERMS_VERSION,
        "title": "Terms and Conditions",
        "status": "placeholder",
        "body": TERMS_TEXT_PLACEHOLDER,
    },
}


class TermsDocumentView(BaseModel):
    """One terms version, verbatim. ``status`` is "placeholder" until the client's
    real text lands — the surface renders that word rather than deciding for itself
    whether the document it received is binding."""

    version: str
    title: str
    status: str
    body: str


@terms_router.get("/{version}", response_model=TermsDocumentView)
def terms_document(version: str) -> TermsDocumentView:
    """One version's text — 404 for an id this build does not carry, which is the
    honest answer: a version served from a different deployment is not something
    this one can vouch for."""
    document = TERMS_DOCUMENTS.get(version)
    if document is None:
        raise HTTPException(
            404, f"no terms document with version {version!r} — this build carries "
                 f"{', '.join(sorted(TERMS_DOCUMENTS))}")
    return TermsDocumentView(**document)


@terms_router.get("", response_model=TermsDocumentView)
def current_terms() -> TermsDocumentView:
    """The CURRENT version — what a confirmation signed right now would record."""
    return TermsDocumentView(**TERMS_DOCUMENTS[TERMS_VERSION])


# --- response models --------------------------------------------------------------------

class AssuranceRotation(BaseModel):
    """The cap's rotation as the run measured it: degrees, the instrument the answer
    came from, and whether the pipeline itself called it unverified.

    TWO ROTATIONS LIVE HERE, AND THEY ARE NOT THE SAME NUMBER (gap
    ``per-site-pairs-rotation-diameter``, 2026-07-31). ``deg`` is the MEASURED notch
    shift — what the instrument reads at the shipped pose, re-derived after every
    rework. ``operator_cumulative_deg`` is how far a HUMAN turned the cap off the
    pipeline's certified pose, folded onto the summary row by the adjust tools
    (``row["nudge"]["cumulative_deg"]``). Until now the second reached the surface
    only as an untyped dict inside ``RunView.sites``, which is why the Deliver row
    could not say it. They answer different questions — "is it clocked right?" and
    "how much of that did we do by hand?" — and an operator confirming a case is
    entitled to both. None on a site nobody rotated."""

    deg: Optional[float] = None
    evidence: Optional[str] = None
    unverified: bool = False
    operator_cumulative_deg: Optional[float] = None


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


class AssuranceCorrespondence(BaseModel):
    """THE PAIRS a fit-by-points stood on (design flow.dc.html's PAIRS metric).

    ``pairs`` is what the operator NAMED; ``observations`` is what those pairs
    produced (a two-point span contributes two), and the two differ exactly when
    spans were used — which is the fact a reader of a sealed row most wants, since a
    span is the stronger observation. ``max_pairs`` is the wire's own cap, carried so
    a surface renders "3/8" from a server fact instead of hard-coding the bound."""

    pairs: Optional[int] = None
    observations: Optional[int] = None
    max_pairs: Optional[int] = None
    residual_rms_mm: Optional[float] = None


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
    # THE DISCLOSURE GAP THIS FIELD CLOSES (finding, 2026-07-28; plan §10-E). One
    # construction part is case-level while the variant is per-site (ARCHITECTURE.md
    # §7's own stated limit); when a case's sites identify DIFFERENT variants, one
    # shared part cannot match all of them, and the worker already says so —
    # auto_flow.py writes ``"single construction part shared across sites
    # identifying N distinct variants — per-variant construction parts needed"``
    # into ``row["production"]["note"]``. Until this field existed, this read
    # picked the clamp fields out of that SAME block and dropped the note: a
    # two-variant case showed per-site GREEN verdicts with nothing said, and the
    # client confirmed and paid against that surface. Verbatim from the worker —
    # no rewriting, no new physics — beside the clamp story it already stands next
    # to in the production block. None on every single-variant case (the worker
    # never writes the key when there is nothing to disclose).
    production_note: Optional[str] = None
    # THE NUMBERS IN THIS ROW THAT PREDATE AN OPERATOR REWORK (review 2026-07-28,
    # finding E). Adjust re-derives what it can over the new pose — the deviation
    # scalars and the clocking — and NAMES what it cannot: the rim agreement was
    # anchored on the scan's own fitted rim circle and the guidance on a dozen
    # run-time inputs, neither of which the shipped record carries. Sealing the row
    # without saying so gave stale numbers a fresh signature; empty on every row the
    # run itself produced, so a clean case reads exactly as it always did.
    stale_metrics: List[str] = Field(default_factory=list)
    # THE OPERATOR'S BEST-FIT DIAL, typed onto the row (gap
    # ``per-site-pairs-rotation-diameter``, 2026-07-31). The matching diameter a
    # best-fit was run at is the single number that explains why a refinement moved
    # what it moved, and it reached the surface only through ``RunView.sites`` as an
    # untyped dict. Read off ``row["best_fit"]``, which the adjust landing folds and
    # a rotation-reset drops — so None means "this site ships the pipeline's own
    # refinement", never "we forgot".
    matching_diameter_mm: Optional[float] = None
    # THE CORRESPONDENCE the shipped pose stands on — the design's PAIRS metric. See
    # ``adjust._fold_outcome`` for why this is the LAST applied set rather than a
    # monotonic per-site tally.
    correspondence: Optional[AssuranceCorrespondence] = None
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
    # THE FORK'S WORD ("skip" | "adjust" | None), on the document the operator reads
    # before confirming. The standing directive evidence.py cites — when Adjust is
    # not surfaced the assurance must still show what was done — is not satisfied by
    # sealing the word: a hash shows nobody anything. It rides here so Deliver's
    # report can state it, and it is dropped from the projection the bundle seals
    # (the bundle states the ACT as its own top-level key, beside the run's FACTS)
    # so the canonical bytes carry one statement, not two.
    adjustments: Optional[str] = None
    sites: List[AssuranceSite]

    def sealed_facts(self) -> dict:
        """The run's facts as the bundle seals them: this document minus the act.
        One method, so the confirm route and the release re-derivation cannot drop
        different fields."""
        return self.model_dump(mode="json", exclude={"adjustments"})


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

# THE RUNGS THAT CARRY A RESOLVED VERDICT. A confirmation is a signature over every
# site's outcome, so every site must HAVE one: ready (the operator attested it) or
# flagged (the run raised it and the operator acknowledges it row by row). ADJUSTED is
# deliberately not here — a reworked site's pose has moved since anything was attested,
# and the ladder already draws its way back (adjusted → review_ready → ready).
_RESOLVED_RUNGS = ("ready", "flagged")


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
    rework = row.get("rework") if isinstance(row.get("rework"), dict) else {}
    # the adjust landing's own blocks (adjust._fold_outcome), read defensively like
    # every other worker-shaped block on this row
    nudge = row.get("nudge") if isinstance(row.get("nudge"), dict) else {}
    best_fit = row.get("best_fit") if isinstance(row.get("best_fit"), dict) else {}
    correspondence = (row.get("correspondence")
                      if isinstance(row.get("correspondence"), dict) else None)
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
            operator_cumulative_deg=nudge.get("cumulative_deg"),
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
        production_note=production.get("note"),
        stale_metrics=[str(m) for m in (rework.get("stale_metrics") or [])],
        matching_diameter_mm=best_fit.get("matching_diameter_mm"),
        correspondence=(AssuranceCorrespondence(**{
            k: correspondence.get(k)
            for k in ("pairs", "observations", "max_pairs", "residual_rms_mm")})
            if correspondence is not None else None),
        qc_images=_site_qc_images(run, case_id, tooth),
        references={key: metrics[key] for key in _REFERENCE_KEYS if key in metrics},
    )


def _needs_acknowledgment(site: AssuranceSite) -> bool:
    """AM-12's acknowledgment gate applies whenever EITHER of two things is true:
    the run's own guidance flagged the site (the session ladder's rung), or the
    PRODUCTION block disclosed a fact the operator must weigh before releasing —
    today, exactly the shared-construction-part conflict ``production_note``
    carries (plan §10-E, finding 2026-07-28).

    THE FLAG-VS-ANNOTATE DECISION, made here: a multi-variant case FLAGS rather
    than merely displaying the note quietly. The note's own words are "cannot
    match", not "differs slightly" — the worker is not hedging, it is naming a
    geometry that will not fit some of what was declared. An operator who can
    confirm and pay without ever having to acknowledge that sentence is exactly
    the disclosure gap this fix closes; annotating it INTO the row without also
    gating on it would have fixed the reading experience and left the trust
    architecture's own doctrine ("screen order is not a control") unmet for the
    one row that most needs it. This predicate is the ONE place that doctrine is
    applied — the sort below and ``confirm_case``'s acknowledgment gate both call
    it, so a row can never look pinned-first without also being blocked, or vice
    versa."""
    return site.status == "flagged" or site.production_note is not None


def _sort_worst_first(sites: List[AssuranceSite]) -> List[AssuranceSite]:
    """AM-12: rows needing acknowledgment pinned first (``_needs_acknowledgment``
    — the session's flagged rung OR a production disclosure), then the worse
    gate, then tooth for a stable order across reloads. An unknown gate word
    sorts as worst — a vocabulary the sorter does not know is a reason to look,
    never to bury.

    A production note escalates the SORT position without rewriting the
    worker's own gate word: ``AssuranceGate`` stays verbatim (the docstring's own
    promise — "the run's guidance verdict verbatim"), so the escalation lives only
    in this local severity used for ordering, never written back onto the site.
    It ranks at least as urgent as "action-needed" even on a row the run itself
    called ready — the shared-part conflict is a fact about what ships, not
    about how well this one site's geometry seated."""
    def key(site: AssuranceSite):
        pinned = 0 if _needs_acknowledgment(site) else 1
        severity = _GATE_SEVERITY.get(site.gate.level, len(_GATE_SEVERITY))
        if site.production_note is not None:
            severity = max(severity, _GATE_SEVERITY["action-needed"])
        return (pinned, -severity, site.tooth)
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
        adjustments=adjustments_of(session),
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


# --- the invoice (design payLines/payTotal 1475-1480) ------------------------------------
#
# EVIDENCE class too, and for the same reason: an operator must be able to read what a
# case costs BEFORE authorizing anything, exactly as they read the assurance before
# confirming. A pure projection — reading it writes nothing.
#
# THE DOCTRINE POINT, stated where the money is: no route anywhere accepts an amount.
# A client that could POST one could pay $0 for a released case, which is a
# status-shaped claim wearing a currency symbol. The amount is derived here from the
# run's own assurance and the case's turnaround, and ``bff.pricing`` owns the card.

def _billing_dispositions(session: CaseSession, run: RunSession) -> Dict[str, str]:
    """The dispositions the invoice prices against: the STANDING confirmation's when
    it names this run, else empty — and empty resolves, site by site, to release.

    That default is confirm's own rule (client 2026-07-27 #4: "omission means
    release"), read here rather than re-invented: a case that reached Deliver is a
    case being delivered, and an invoice that quoted zero until someone clicked every
    site would be describing a different flow than the one the confirm route
    implements."""
    confirmation = session.confirmation
    if (confirmation is None
            or confirmation.run_id != (run.run_id or run.job_id)):
        return {}
    return dict(confirmation.dispositions)


def derive_invoice(case: CaseRecord, session: CaseSession) -> InvoiceView:
    """The one invoice derivation — the GET serves it and the payment route prices
    with it, so what the operator read and what they were charged cannot diverge
    (the ``derive_assurance`` pattern, for the same reason).

    An EXCEPTION is a site ``_needs_acknowledgment`` returns true for — the very
    predicate the confirmation gate stands on. Deliberately one predicate: what the
    invoice discounts and what the operator was made to face row by row must be the
    same set, or the surface would be charging half for something it never asked
    anyone to acknowledge (or worse, the reverse)."""
    run = _require_done_run(session, case.id)
    assurance = derive_assurance(case, session)
    effective = _effective_choices(case, session.choices)
    dispositions = _billing_dispositions(session, run)
    released = exceptions = withheld = 0
    for site in assurance.sites:
        if dispositions.get(str(site.tooth), "release") == "withhold":
            withheld += 1
        elif _needs_acknowledgment(site):
            exceptions += 1
        else:
            released += 1
    payment = session.payment
    return price_invoice(
        case_id=case.id, run_id=run.run_id or run.job_id,
        turnaround=effective.turnaround,
        turnaround_source=effective.turnaround_source,
        released=released, exceptions=exceptions, withheld=withheld,
        paid=(InvoicePaymentView(
            amount_cents=payment.amount_cents, currency=payment.currency,
            rate_card_version=payment.rate_card_version,
            turnaround=payment.turnaround, at=payment.at)
            if payment is not None and payment.payment_authorized else None),
    )


@router.get("/{case_id}/invoice", response_model=InvoiceView)
def case_invoice(case_id: str, request: Request) -> InvoiceView:
    """What this case costs, derived. 404 without a done current run — there is
    nothing to price before the work exists, and quoting a case the pipeline has not
    run would be a promise about physics nobody has done."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    return derive_invoice(case, store.load(case_id))


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
    any disposition set that does not match the evidence it derived itself.

    DISPOSITIONS ARE OPTIONAL, AND OMISSION MEANS RELEASE (client 2026-07-27:
    "What is disposition release vs withhold" — on a single-site case, 7 of the 9
    real cases, the question was friction with one sane answer). A case that reached
    Deliver is a case being delivered; withholding is the exceptional act, and the
    only one that must be SAID. What is NOT relaxed: a flagged site that is released
    still needs its own row acknowledgment (AM-12 — the client's own assurance
    rule), which is exactly what the refusals now name.

    ``terms_accepted`` is the agreement itself, moved here from Declare's per-site
    ticks (plan §10-A). Required, like ``PaymentIn.authorize`` — a default would
    let the act happen by omission, and the whole point of moving the agreement to
    the commercial moment is that it is given, not assumed. There is no
    ``terms_version`` field on the wire: the server names which text was shown
    (``TERMS_VERSION``) — a client cannot accept a version it did not ask to see,
    and inventing one here would be a claim ``dispositions`` never gets to make
    either."""

    model_config = ConfigDict(extra="forbid")

    dispositions: Dict[str, Literal["release", "withhold"]] = Field(
        default_factory=dict)
    acknowledged_flags: List[int] = Field(default_factory=list)
    terms_accepted: bool


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


def _derive_evidence_sha(case: CaseRecord, session: CaseSession,
                         settings: Settings, run: RunSession) -> str:
    """The re-derivation both release and the artifact gate stand on (plan §4:
    validity is re-derivation, never trust in a record): the assurance projection
    as it stands NOW, the QC images' bytes as they are NOW, and the adjust decision
    as it stands NOW — hashed by the same canonical rule the confirmation sealed. A
    missing QC image counts as drift — evidence that cannot be re-covered no longer
    matches anything.

    ``terms_version`` is read off the STANDING CONFIRMATION, not re-derived —
    unlike the fork, there is no separate act that can move it independently of
    confirming itself (the agreement is confirm's own act, plan §10-A), so the
    only "current" answer that means anything is what the confirmation being
    checked actually recorded. A case with no confirmation at all has nothing to
    re-derive against anyway (both callers refuse first on that)."""
    assurance = derive_assurance(case, session)
    try:
        hashes = qc_image_hashes(_run_dir(settings, case_id=case.id, run=run),
                                 _qc_image_names(run))
    except FileNotFoundError:
        return "evidence-incomplete"   # never equals a sha256 hex digest
    terms_version = (session.confirmation.terms_version
                     if session.confirmation is not None else None)
    # ONE read of the fork: the projection served it, and the bundle's own key
    # restates that same value — the two can never describe different decisions
    return canonical_bundle(assurance.sealed_facts(), hashes,
                            assurance.adjustments, terms_version).sha256


# the two file-attribution rules live in bff/session.py now: the Deliver surface
# must say what a release WOULD disclose (before it exists) with the same rule that
# decides what it DOES disclose, and two derivations of "what ships" would be two
# answers waiting to disagree. Re-exported under this module's private names so the
# gate below reads as it always did.
_summary_teeth = summary_teeth_of
_tooth_of_file = tooth_of_file


# --- the confirmation (plan §6, grill AM-10/AM-12) --------------------------------------

def _require_every_site_resolved(assurance: AssuranceView) -> None:
    """EVERY SITE CARRIES A VERDICT BEFORE ANYTHING IS SIGNED (review 2026-07-28,
    finding F). This precondition lived only in ``flow.ts``'s reachability, which is a
    screen order, not a control — and screen order in a presentational app has never
    been one (AM-1's own rule, applied here).

    It was unreachable before slice 6: nothing wrote ``adjusted``, so every post-run
    site already stood on ready or flagged. The Adjust tools are that rung's first
    writer, and they made it reachable — measured, an adjusted site whose acceptance
    row read FAIL confirmed, released and disclosed eleven files straight through the
    API. The refusal names the sites and the rung, so the operator knows the act
    (re-review over the new panes), not just the wall."""
    unresolved = [site for site in assurance.sites
                  if (site.status or "detected") not in _RESOLVED_RUNGS]
    if not unresolved:
        return
    raise HTTPException(
        422, "every site needs a verdict before the case is confirmed — still "
             "unresolved: "
             + ", ".join(f"tooth {s.tooth} is {s.status or 'detected'}"
                         for s in unresolved)
             + ". A reworked site is re-reviewed over its new panes; the "
               "confirmation signs the fits as they stand now")


@router.post("/{case_id}/confirm", response_model=CaseSessionDetail)
def confirm_case(case_id: str, body: ConfirmIn,
                 request: Request) -> CaseSessionDetail:
    """Seal the confirmation over the evidence as it stands NOW — and, since plan
    §10-A, accept the terms in the same act: "confirm and accept terms" is ONE
    signature, not two. ``body.terms_accepted`` must be literally true (the
    ``PaymentIn.authorize`` pattern — a default would let the act happen by
    omission), checked FIRST and outside the CAS mutation: a refusal that stands
    regardless of session state costs no load.

    Refuses unless: terms accepted; a done current run; EVERY SITE STANDS ON A
    VERDICT (``_require_every_site_resolved`` — slice 6's ADJUSTED rung made
    flow.ts's client-side rule reachable, so it lives here now); every site
    ``_needs_acknowledgment`` heading for release appears in
    ``acknowledged_flags`` (AM-12 — row by row, never in bulk; an acknowledgment
    of a site that needs none is refused too, a claim about nothing). A MISSING
    DISPOSITION IS NO LONGER A REFUSAL (client 2026-07-27 #4: "What is
    disposition release vs withhold") — every unnamed site defaults to release,
    resolved once below, so the acknowledgment demand is the only thing this
    route can be short of besides the terms. On success, INSIDE the CAS
    mutation: re-derive the assurance, hash the QC images' bytes, build and
    WRITE the evidence bundle (now carrying ``TERMS_VERSION`` beside the fork's
    word — plan §10-A: "recorded with its timestamp and the evidence hash it was
    given over") — a failed write REFUSES the whole confirmation (AM-10's
    transactional half; the content-addressed write is idempotent, so the
    mutation's one CAS retry re-writes the same bytes harmlessly) — then persist
    the record."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    if not body.terms_accepted:
        raise HTTPException(422, "confirming requires accepting the current "
                                 "terms — the act is {\"terms_accepted\": true} "
                                 "beside the dispositions, or no act at all")

    def apply(session: CaseSession) -> None:
        run = _require_done_run_for_act(session, case_id, "confirm")
        assurance = derive_assurance(case, session)
        _require_every_site_resolved(assurance)
        teeth = [site.tooth for site in assurance.sites]
        known = {str(t) for t in teeth}
        unknown = sorted(k for k in body.dispositions if k not in known)
        if unknown:
            raise HTTPException(422, "dispositions name sites this run does not "
                                     "carry: "
                                     + ", ".join(f"tooth {k}" for k in unknown))
        # EVERY SITE DEFAULTS TO RELEASE (client 2026-07-27): the effective map is
        # what gets recorded, so the record still states an act for every site and
        # every reader downstream (released_teeth_of, the artifact gate, the display
        # half) keeps reading one complete map — the default is resolved HERE, once,
        # never re-guessed by each reader.
        dispositions = {str(t): body.dispositions.get(str(t), "release")
                        for t in teeth}
        # AM-12's acknowledgment gate, extended (plan §10-E, 2026-07-28): a site
        # needs its own row acknowledgment when the session ladder flagged it OR
        # the production block disclosed a shared-construction-part conflict
        # (``_needs_acknowledgment`` — the one predicate the sort above and this
        # gate both read, so a row can never look pinned-first without also
        # being blocked here).
        flagged = {site.tooth for site in assurance.sites
                   if _needs_acknowledgment(site)}
        acknowledged = set(body.acknowledged_flags)
        unacknowledged = [t for t in sorted(flagged)
                          if dispositions.get(str(t)) == "release"
                          and t not in acknowledged]
        if unacknowledged:
            # AM-12: the flag is confirmed ROW BY ROW — each unacknowledged one
            # is named; a bulk "yes to all flags" cannot exist on this wire.
            # Since dispositions became optional this is the ONLY thing a refusal
            # can be short of: it never asks for a disposition the operator was
            # not obliged to give (client 2026-07-27's friction complaint).
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
        bundle = canonical_bundle(assurance.sealed_facts(), hashes,
                                  assurance.adjustments, TERMS_VERSION)
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
            dispositions=dispositions,
            acknowledged_flags=list(body.acknowledged_flags),
            # the sealed word restated in the open, from the SAME read the bundle
            # used — so the display half can notice a fork re-clicked after
            # release without re-hashing the run's QC bytes to find out
            adjustments=assurance.adjustments,
            # the acceptance, recorded WITH its timestamp (``at`` above) and the
            # evidence hash it was given over (``evidence_sha256`` above) — plan
            # §10-A's own words. ``body.terms_accepted`` is guaranteed True here
            # (refused above otherwise), so the record states the act, not the
            # wire value.
            terms_accepted=True,
            terms_version=TERMS_VERSION,
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
    body, and stub-authorized history stays tellable from paid history).

    IT NOW CARRIES AN AMOUNT, AND STILL ACCEPTS NONE (2026-07-31). The body is the
    same single ``authorize`` boolean it always was; the server derives the price
    (``derive_invoice`` — the very document the operator read at
    ``GET /{id}/invoice``) and records what it charged. An amount on the wire would
    be the money-shaped cousin of a claimed verdict: a client that could send one
    could pay $0 for a released case.

    GATED ON THE TERMS (plan §10-A: "Payment (and therefore release) is gated on
    it") — a REAL server-side precondition, not the progression's screen order:
    payment refuses 409 unless a standing confirmation exists AND its own
    ``terms_accepted`` is true. Reading the CONFIRMATION's flag rather than
    re-checking anything here is deliberate: terms acceptance is confirm's own
    act (``ConfirmIn.terms_accepted``, required there), so a standing
    confirmation already proves it — and a confirmation sealed before the
    concept existed reads ``terms_accepted=False`` honestly (the same
    under-claiming precedent ``adjustments``/``payment_authorized`` already
    follow), refusing until it is re-confirmed under the current terms."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    if not body.authorize:
        raise HTTPException(422, "the payment stub authorizes nothing implicitly — "
                                 "the act is {\"authorize\": true}, or no act at "
                                 "all")

    def apply(session: CaseSession) -> None:
        confirmation = session.confirmation
        if confirmation is None or not confirmation.terms_accepted:
            raise HTTPException(409, f"payment requires a confirmation that "
                                     f"accepted the terms — confirm case "
                                     f"{case_id!r} (and accept the terms) before "
                                     f"authorizing payment")
        # A DONE CURRENT RUN, EXPLICITLY (2026-07-31). Pricing needs one, and the
        # act needs one for the same reason every other gate here does: a cleared
        # run pointer means the case changed under the confirmation, which is inert
        # without a current run anyway. Named as an ACT refusal (409, this module's
        # own sentence) rather than letting the read helper's 404 leak out of a POST.
        _require_done_run_for_act(session, case_id, "pay for")
        # THE SERVER PRICES AT AUTHORIZATION TIME (2026-07-31), inside the mutation,
        # off the FRESH document — the same derivation the operator just read. The
        # body carries no amount and never will; what is recorded is what this
        # server charged, with the card version and turnaround it charged under, so
        # a later repricing (a turnaround change fires no boundary) leaves the
        # receipt readable instead of retroactively rewritten.
        invoice = derive_invoice(case, session)
        session.payment = PaymentRecord(payment_authorized=True, provider="stub",
                                        at=_now(),
                                        amount_cents=invoice.total_cents,
                                        currency=invoice.currency,
                                        rate_card_version=invoice.rate_card_version,
                                        turnaround=invoice.turnaround)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- the demo's doors back (client 2026-07-30) ------------------------------------------


@router.post("/{case_id}/reset", response_model=CaseSessionDetail)
def reset_case(case_id: str, request: Request) -> CaseSessionDetail:
    """RESET THE WHOLE CASE to fresh intake (client 2026-07-30: "there is a need for
    resetting the cases persistance").

    The delivery reset below withdraws three signatures; this one returns the case to
    the state it had on ingest — no system, no declarations, no previews, no
    detection, no run, no signatures — so a demo can be walked from the very start
    rather than from the last thing that happened to it.

    WHAT SURVIVES, and it is not an oversight: the immutable RUN DIRECTORIES under
    ``reports/product/<case>/runs/<run_id>/``. AM-1 says a landed run is history and
    history is not erased by someone re-walking a demo — this clears the session's
    POINTER to it, exactly as every other reset boundary already does. The case
    record itself (the scan, the suggestions) is the ingest's, and no route of ours
    writes it.

    A fresh ``CaseSession`` is built rather than fields nulled one by one,
    deliberately: a field added later would otherwise survive this reset silently,
    and "reset" would quietly come to mean "reset the fields someone remembered".
    The CAS version is carried FORWARD (not reset to 0) so a rival writer holding the
    pre-reset document still loses its save — a reset must not become a way to make
    a stale write look current."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        fresh = CaseSession(case_id=session.case_id, tenant_id=session.tenant_id,
                            version=session.version)
        for field in CaseSession.model_fields:   # on the CLASS (pydantic 2.11+)
            setattr(session, field, getattr(fresh, field))

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- the delivery door back --------------------------------------------------------------


@router.post("/{case_id}/delivery/reset", response_model=CaseSessionDetail)
def delivery_reset(case_id: str, request: Request) -> CaseSessionDetail:
    """START OVER — withdraw the confirmation, the payment and the release, so the
    delivery flow can be walked again (client 2026-07-30: "This is a demo … once paid
    i cant go back").

    The client's first framing was "we dont need to persist" — this route is the
    version that keeps the trust architecture honest instead. Payment staying
    server-side truth is the entire reason the forged-checkout-return test means
    anything; making it ephemeral would demo a product whose money state evaporates.
    So the state PERSISTS exactly as before, and the door back is an explicit,
    body-less operator ACT: three signed records withdrawn together, loudly, leaving
    the run and every site rung exactly where they stand. Re-walking the flow then
    re-derives and re-seals evidence through the same gates as the first pass —
    nothing about the second walk is cheaper.

    All three records go TOGETHER, deliberately: a confirmation without its payment
    would let the walk resume mid-flow with the terms acceptance already spent, and a
    release outliving its confirmation is exactly the divergence the artifact gate
    exists to refuse. Refuses 409 when nothing is signed — "start over" from the
    start is a no-op someone mistook for a reset, and pretending it did something
    would teach the demo operator a false model."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        if (session.confirmation is None and session.payment is None
                and session.release is None):
            raise HTTPException(409, f"nothing to start over from on case "
                                     f"{case_id!r} — no confirmation, payment or "
                                     f"release is standing")
        session.confirmation = None
        session.payment = None
        session.release = None

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- the checkout return leg (plan §10-A: "a checkout screen and a return") -------------

class CheckoutReturnIn(BaseModel):
    """THE RETURN LEG'S ONLY FIELD, and it carries no claim. A real payment
    provider's redirect-back always carries an identifier (a checkout/session id)
    so the app can ask "what happened over there?" — ``reference`` stands in for
    that identifier. There is deliberately no ``status``, no ``paid``, no
    ``outcome`` field: ``extra="forbid"`` makes it structurally impossible to
    smuggle one, which is the whole point (see ``checkout_return`` below) — a
    browser round trip is the most forgeable channel there is, so the wire shape
    itself must be unable to say "success"."""

    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)


@router.post("/{case_id}/checkout/return", response_model=CaseSessionDetail)
def checkout_return(case_id: str, body: CheckoutReturnIn,
                    request: Request) -> CaseSessionDetail:
    """THE SECURITY RULE, stated where it is enforced: this route asserts
    NOTHING about payment. ``body.reference`` is accepted and read by nobody —
    it exists on the wire only because a real provider's return always carries
    one, and pretending otherwise would misdescribe the shape a real
    integration will need. The route MUTATES NOTHING: it re-reads the session
    and returns the SAME detail a plain GET would, because "the return from
    checkout" means exactly that — re-read this case — and nothing more.

    Whether payment actually happened is decided ENTIRELY by whether
    ``POST .../payment`` was separately called and landed a ``PaymentRecord``
    (``CaseSession.payment_authorized`` — the one and only source of truth).
    There is no code path from this request to that record: a forged
    ``{"reference": "evt_fake", "status": "success"}`` 422s on the extra field
    before it is even parsed, and a well-formed ``{"reference": "..."}`` changes
    nothing it could not have learned from GET."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
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

class ArtifactFile(BaseModel):
    """One released deliverable as the delivery surface needs it (client 2026-07-27
    #6: "Make sure we have good UI for payment and release of information /
    artifacts") — the name, its SIZE on disk, and the site it belongs to so the
    surface can group by site instead of showing one flat list of near-identical
    filenames. ``size_bytes`` is None when the package claims a file the run
    directory no longer holds: an honest gap the operator can see, never a 0."""

    name: str
    size_bytes: Optional[int] = None
    tooth: Optional[int] = None   # None = case-wide (overlay, manifest, jaw scan)


class ArtifactsView(BaseModel):
    run_id: str
    # the released deliverables, package order preserved; QC images are the
    # EVIDENCE class and never appear here, withheld sites' per-tooth files are
    # excluded (they stay open, not shipped)
    files: List[ArtifactFile]
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


_ARTIFACT_MEDIA = {".stl": "model/stl", ".json": "application/json",
                   ".html": "text/html"}


def _artifact_file(run_dir: Path, name: str, case_id: str,
                   teeth: List[int]) -> ArtifactFile:
    """One listed deliverable with the two facts the delivery surface needs beyond
    its name: how big it is, and which site it belongs to. The size is read from the
    run directory at list time (the run dir is immutable, so this is a stat, not a
    derivation); a file the package claims but disk no longer holds reports None —
    visible as a gap rather than smoothed into a zero."""
    path = run_dir / name
    return ArtifactFile(
        name=name,
        size_bytes=(path.stat().st_size if path.is_file() else None),
        tooth=tooth_of_file(name, case_id, teeth),
    )


@router.get("/{case_id}/runs/current/artifacts", response_model=ArtifactsView)
def list_artifacts(case_id: str, request: Request) -> ArtifactsView:
    """The DELIVERABLE list — even listing is disclosure (names leak what was
    made), so the release gate sits on the list too."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run, release = _require_valid_release(case, session, settings)
    teeth = _summary_teeth(run)
    withheld = sorted(set(teeth) - set(release.released_teeth))
    names, held_case_files = split_released_files(
        run.package_files, teeth, release.released_teeth, case.id)
    run_dir = _run_dir(settings, case.id, run)
    return ArtifactsView(run_id=run.run_id or run.job_id,
                         files=[_artifact_file(run_dir, name, case.id, teeth)
                                for name in names],
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
