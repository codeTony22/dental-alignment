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
import html
import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from case_prep.application.adjust import cross_checked
from case_prep.application.cases import CaseRecord
from case_prep.domain.acceptance import evaluate_acceptance

from ..config import Settings
from ..evidence import (BUNDLE_VERSION, canonical_bundle, qc_image_hashes,
                        write_bundle)
from ..pricing import InvoicePaymentView, InvoiceView, price_invoice
from ..session import (ACT_CASE_RESET, ACT_CONFIRMED, ACT_DELIVERY_RESET,
                       ACT_PAYMENT_AUTHORIZED, ACT_RELEASED, CaseSession,
                       ConfirmationRecord, PaymentRecord, ReleaseRecord, RunSession,
                       SessionConflict, SessionStore, adjustments_of,
                       needs_acknowledgment, record_activity,
                       release_matches_confirmation, released_teeth_of,
                       split_released_files, summary_teeth_of, tooth_of_file,
                       withhold_intents_of)
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
TERMS_VERSION = "placeholder-v2"

# THE RETIRED TEXT, kept verbatim (see TERMS_DOCUMENTS below): a confirmation sealed
# over v1 must still resolve to the words its signer actually saw.
_TERMS_TEXT_V1 = (
    "PLACEHOLDER — pending the client's final Terms and Conditions text. "
    "I have reviewed the alignment for all N sites in this case, including the "
    "assurance report and its QC images. I accept the alignment as shown and "
    "authorize release of the deliverables."
)

# THE SECOND DOCUMENT (gap ``clinical-responsibility-attestation``, 2026-07-31).
#
# The v1 sentence named a SITE COUNT and nothing else. An operator signed "all N
# sites" without the text ever saying that some of those sites release only as
# ACKNOWLEDGED EXCEPTIONS (``_needs_acknowledgment`` — the very rows the confirm gate
# makes them tick one by one), or that a WITHHELD site ships nothing and stays open.
# The signature covered a state of affairs the sentence declined to describe.
#
# This is that missing text. It is a DOCUMENT rather than a sentence composed in the
# browser: the classes it names are the same three the invoice prices against, and a
# clinical attestation whose wording is assembled client-side is a signature nobody
# can reproduce afterwards. The CASE-SPECIFIC COUNTS are deliberately NOT in here — a
# document is case-independent, and its per-case enumeration is derived from the
# invoice's own server-derived line quantities (bff/pricing.py) and rendered beside
# the checkbox.
CLINICAL_VERSION = "clinical-responsibility-placeholder-v1"

CLINICAL_TEXT_PLACEHOLDER = (
    "PLACEHOLDER — pending the client's final clinical-responsibility wording. "
    "I confirm that the alignment metrics shown for this case are the ones I "
    "reviewed, and I accept clinical responsibility for releasing the "
    "constructions named in this confirmation. This includes every site released "
    "as an acknowledged exception — a site the run itself raised, or one whose "
    "construction part is shared with a differently-declared variant — which I "
    "have acknowledged row by row. It excludes every withheld site: a withheld "
    "site discloses nothing, stays open, and remains my responsibility to resolve."
)

# THE CURRENT AGREEMENT (v2). It INCORPORATES the clinical statement by version
# rather than asking for a second signature: ``ConfirmationRecord`` carries one
# ``terms_version``, and a second boolean on the wire would be an act the evidence
# hash does not cover. Citing the id in the text is what makes the incorporation
# legible to an auditor holding only the sealed version string.
TERMS_TEXT_PLACEHOLDER = (
    "PLACEHOLDER — pending the client's final Terms and Conditions text. "
    "I have reviewed the alignment for every site in this case, including the "
    "assurance report and its QC images. I accept the alignment as shown and "
    "authorize release of the deliverables for the sites released under this "
    "confirmation — including those released as acknowledged exceptions, and "
    "excluding any site I have withheld. The Clinical Responsibility Statement "
    f"({CLINICAL_VERSION}) forms part of this agreement and is accepted with it."
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
    CLINICAL_VERSION: {
        "version": CLINICAL_VERSION,
        "title": "Clinical Responsibility Statement",
        "status": "placeholder",
        "body": CLINICAL_TEXT_PLACEHOLDER,
    },
    # ADDITIVE, never edited in place — the rule stated above, applied the first
    # time it actually cost something: v1 is superseded, and a confirmation sealed
    # over it still resolves to the words that signer saw.
    "placeholder-v1": {
        "version": "placeholder-v1",
        "title": "Terms and Conditions",
        "status": "placeholder",
        "body": _TERMS_TEXT_V1,
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
    the operator confirms over.

    ``stale`` IS THE ONE THING THIS MODEL ADDS TO THE WORKER'S WORDS (gap
    ``re-preview-a-site-without-applying-a-tool``, 2026-07-31), and it adds it
    BESIDE them rather than to them. ``_fold_outcome`` re-derives every
    pose-dependent number after a rework and cannot re-derive this one — guidance
    is a function of a dozen run-time inputs the shipped record does not carry, so
    the application NAMES it stale instead (``STALE_AFTER_REWORK``). The naming
    reached the wire on ``AssuranceSite.stale_metrics`` and nowhere near the gate
    itself, and Deliver's assurance table renders ``actions`` for every row: after
    a successful rework the rung moved (flagged → adjusted → ready) while the
    words beside it still described the pre-rework fit, with nothing on the gate
    saying so.

    DERIVED SERVER-SIDE, deliberately, though the client could compute it from a
    list it already receives: "are these words still true?" is a judgment about
    evidence, and this codebase does not make those in a browser. The LEVEL and the
    ACTIONS stay untouched — the projection annotates, it never rewrites."""

    level: str
    actions: List[str] = Field(default_factory=list)
    stale: bool = False


class AssuranceCorrespondence(BaseModel):
    """THE PAIRS a fit-by-points stood on (design flow.dc.html's PAIRS metric).

    ``pairs`` is what the operator NAMED; ``observations`` is what those pairs
    produced. THE TWO DIFFER WHEN A SPAN'S DIRECTION COUNTED — not merely when spans
    were used, which is what this docstring claimed until the 2026-07-31 audit
    (finding 6) checked it against the physics. ``observations_for``
    (case_prep/application/adjust.py) emits a span's direction observation only when
    the span reads as RADIAL (within ``SPAN_RADIAL_TOLERANCE_DEG`` of its own
    radius); a chord ACROSS the feature contributes its midpoint alone, and the
    worker writes it an explicit ``direction_note`` saying so. Three chord spans
    therefore produced 3 pairs and 3 observations — byte-identical, in the sealed
    document, to three plain clicks.

    So the accounting the physics actually produces is carried: ``spans`` is how many
    of the named pairs were two-point spans, ``directions_used`` how many of those
    spans' directions the fit could use. A reader of a confirmed row can tell a fit
    built from clean radial spans from one built from discarded chords — the exact
    fact the 2026-07-28 dropped-direction fix exists to state.

    ``max_pairs`` is the wire's own cap, carried so a surface renders "3/8" from a
    server fact instead of hard-coding the bound. All fields are Optional: a row
    folded before this shape existed simply carries fewer of them.

    ``cross_checked`` IS WHETHER ``residual_rms_mm`` IS A MEASUREMENT (the vacuous-RMS
    defect, cap6020-neodent-gm 2026-08-01). A fit built from ONE observation is exactly
    determined for rotation: that single delta IS the answer, its residual is zero by
    construction, and the RMS over it is arithmetic. The activity log of a real case
    reads "run completed — verdicts written for 1 site, none flagged" at 14:32:30 and
    "fit by 1 point pair(s) → 1 observation(s): rotated -50.9° … marks agree to 0.000mm
    RMS" at 14:32:52; the site left at 0.451mm RMS / 0.745mm p90. Nothing on this row
    could have told the operator that the 0.000mm was not evidence of anything.

    So the fact rides on the row the confirmation is signed over, and — because
    ``sealed_facts()`` is a ``model_dump`` — into the canonical bytes with it. False
    means the fit stands on a single observation; None means the row cannot say (see
    ``_correspondence_view``), and inventing True there would be this defect again."""

    pairs: Optional[int] = None
    observations: Optional[int] = None
    spans: Optional[int] = None
    directions_used: Optional[int] = None
    max_pairs: Optional[int] = None
    residual_rms_mm: Optional[float] = None
    cross_checked: Optional[bool] = None


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
    # THE DISPOSITION THIS ROW IS STANDING ON (audit 2026-07-31, the coherence
    # finding). A cap dropped at Adjust wrote ``SiteSession.withhold_intent``, the
    # invoice priced against it, the attestation sentence counted it withheld and
    # ``confirm_case`` sealed it withheld — but the ASSURANCE ROW, the one thing on
    # screen at the moment of signing, carried no withhold field at all. Deliver's
    # table therefore rendered the literal word "released" over a clean dropped site,
    # with no control on the row to change it back, and confirming from that screen
    # withheld the site plus every case-wide file. One surface, two answers.
    #
    # So the draft rides on the row it is signed over, DERIVED like every other field
    # here (``withhold_intents_of`` — the same read confirm folds and the invoice
    # prices against), never accepted from a client. ``confirm_case`` writes the
    # resolved disposition back onto the same field, so after a confirmation this is
    # not merely a draft: it is THE disposition, and Adjust, the invoice, the
    # attestation and this row cannot disagree about it.
    withhold_intent: bool = False
    # THE ACCEPT-AS-FLAGGED-EXCEPTION DRAFT, ON THE ROW IT PRE-FILLS (client ruling
    # 2026-08-02): ``SiteSession.exception_intent``'s presence, so Deliver's
    # row-by-row checkbox can open pre-ticked for a site the operator already
    # discussed at Adjust. THE SAME COHERENCE ARGUMENT ``withhold_intent`` WAS ADDED
    # FOR (audit 2026-07-31, the finding two paragraphs up) — a draft that reached
    # the invoice and the confirmation but not the one screen actually rendering the
    # checkbox would be exactly that defect again. Never a signature: ``ConfirmIn.
    # acknowledged_flags`` is unaffected by this field's value, in either direction.
    exception_acknowledged: bool = False
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
        """The run's facts as the bundle seals them: this document minus the ACTS.
        One method, so the confirm route and the release re-derivation cannot drop
        different fields.

        TWO EXCLUSIONS, BOTH OPERATOR ACTS AND NEITHER AN OVERSIGHT. ``adjustments``
        is the fork's word — the bundle states it as its own top-level key, beside
        the run's facts, so the canonical bytes carry one statement and not two.
        ``sites[*].withhold_intent`` is the per-site disposition draft, and it is
        excluded for the reason the whole disposition map already is (bff/evidence.py):
        a disposition says what the OPERATOR does with a site, never what the run
        found. Folding it in would make dropping a cap look like evidence drift —
        release's own 409 would fire on the operator's own decision and tell them the
        case "changed since it was confirmed", which it did not.

        ``sites[*].exception_acknowledged`` joins the same exclusion for the same
        reason (client ruling 2026-08-02): it is a draft an operator may withdraw
        AFTER confirming — the row-by-row signature already sealed is
        ``acknowledged_flags``, not this field — and folding it in would have that
        withdrawal read as evidence drift at release time, over a fact the run
        never produced."""
        return self.model_dump(
            mode="json",
            exclude={"adjustments": True,
                     "sites": {"__all__": {"withhold_intent",
                                          "exception_acknowledged"}}})


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


def _correspondence_view(block: dict) -> AssuranceCorrespondence:
    """The row's correspondence block, projected — with ONE derivation.

    ``cross_checked`` is written by ``adjust._fold_outcome`` on every fit landed since
    the vacuous-RMS defect was closed. A block folded BEFORE that still has to answer
    the question, and it already carries the number the answer is a pure function of,
    so it is re-derived from ``observations`` by the worker's own predicate — the same
    definition, in one place, never a second threshold living here. A block that never
    carried the count says None rather than guessing: a fit nobody can size is exactly
    where an invented "cross-checked" would repeat the defect.

    Server-side by the rule this codebase applies to every judgment about evidence —
    "is this number a measurement?" is not a question a browser gets to answer."""
    fields = {k: block.get(k)
              for k in ("pairs", "observations", "spans", "directions_used",
                        "max_pairs", "residual_rms_mm")}
    checked = block.get("cross_checked")
    if checked is None and isinstance(block.get("observations"), int):
        checked = cross_checked(int(block["observations"]))
    return AssuranceCorrespondence(
        **fields, cross_checked=(None if checked is None else bool(checked)))


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
    # the fold's own blocks (application.adjust.fold_outcome_into_row — one fold
    # since 2026-08-04, reached via the adjust landing AND the run's evidence
    # re-apply), read defensively like every other worker-shaped block on this row
    nudge = row.get("nudge") if isinstance(row.get("nudge"), dict) else {}
    best_fit = row.get("best_fit") if isinstance(row.get("best_fit"), dict) else {}
    correspondence = (row.get("correspondence")
                      if isinstance(row.get("correspondence"), dict) else None)
    # the domain's evaluation — each numeric beside its industry reference, in the
    # backend's own words; a pure function of the row (no new physics)
    metrics = {m["key"]: m for m in evaluate_acceptance(row)["metrics"]}
    stale_metrics = [str(m) for m in (rework.get("stale_metrics") or [])]
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
            # ONE reading of the row's own staleness naming — the same list the
            # field below carries, so the gate's flag and the site's list can
            # never describe different rows
            stale="guidance" in stale_metrics,
        ),
        clamp=AssuranceClamp(
            requested_mm=production.get("gingival_offset_requested_mm"),
            applied_mm=production.get("gingival_offset_applied_mm"),
            clamped=bool(production.get("clamped")),
            reason=production.get("clamp_reason"),
        ),
        production_note=production.get("note"),
        withhold_intent=(site.withhold_intent if site is not None else False),
        exception_acknowledged=(site.exception_intent is not None
                                if site is not None else False),
        stale_metrics=stale_metrics,
        matching_diameter_mm=best_fit.get("matching_diameter_mm"),
        correspondence=(_correspondence_view(correspondence)
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
    versa.

    LIFTED (client ruling 2026-08-02) onto ``session.needs_acknowledgment``: the
    Adjust-page accept-as-flagged-exception draft (``case_sessions.
    post_acknowledge_exception``) needs this SAME predicate over session/run facts
    it holds directly (an ``AssuranceSite`` is a projection this route has no
    reason to build), and a second definition would be exactly the drift this
    doctrine exists to close. This is now a one-line adapter onto it."""
    return needs_acknowledgment(site.status, site.production_note)


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


# --- one site's acceptance numbers, for the WORKSPACE ------------------------------------
#
# (gap ``deviation-budget-in-workspace``, 2026-07-31.)
#
# Declare and Adjust could not answer the operator's actual question — how much room is
# left, and on which metric — because nothing measurement-against-threshold reached
# them: the acceptance evaluation existed one stage away, folded into the assurance
# table Deliver renders. This serves the same evaluation for ONE site.
#
# WHAT IS DELIBERATELY NOT PORTED: the design's three-lever budget (flow.dc.html
# 1363-1372) divides a rotation error, a diameter error and a residual scatter each by a
# tolerance the BROWSER holds, and draws three bars. None of those three quantities
# exists here — they are a synthetic sum over the prototype's own state — and the
# product's deviation is MEASURED over real mesh, against bands the domain cites to
# published sources. Porting the formula would have invented physics AND computed a
# tolerance comparison client-side, which is two doctrines broken for one widget.
#
# It lives beside the assurance rather than in the Adjust resource because it is the
# SAME projection over the same row, and two homes for "what does the catalog say about
# this site?" would be two answers waiting to disagree. EVIDENCE class like the
# assurance and for the same reason: an operator must be able to read the numbers
# before, not after, the work they inform. Reading it writes nothing.

class SiteAcceptanceView(BaseModel):
    """One site's acceptance evaluation (``case_prep.domain.acceptance``), verbatim.

    ``metrics`` are the catalog's own rows — worker/domain-shaped like the catalog
    views elsewhere on this wire (the domain payload IS the schema): key, label,
    unit, audience, ``industry_ref``, ``bands`` (the band's own ``pass``/``review``
    thresholds — what "how much room is left" is measured against), ``note``, plus
    the measured ``value``, its preformatted ``display`` and the ``band`` it falls
    in. A metric this row could not measure reads band ``missing`` and is listed in
    ``missing`` — never silently counted as a pass.

    ``stale_metrics`` is the row's own naming of what predates a rework, carried
    here for the same reason it rides on the assurance row: a workspace reading
    these numbers must know which of them describe the pose that is actually
    seated."""

    tooth: int
    run_id: str
    # the catalog's worst evaluated band over this row ("pass"|"review"|"fail", or
    # "missing" when nothing could be measured) — the domain's own rollup, never a
    # count this module invents
    overall_band: str
    missing: List[str] = Field(default_factory=list)
    metrics: List[dict] = Field(default_factory=list)
    stale_metrics: List[str] = Field(default_factory=list)
    # the catalog's standing caveat about click precision, verbatim
    context: dict = Field(default_factory=dict)


def _summary_row_for(run: RunSession, tooth: int) -> Optional[dict]:
    """One site's row out of the run's summary, read defensively.

    A near-twin of ``adjust._summary_row`` and deliberately not shared: the adjust
    resource imports THIS module (``_run_dir``), so the dependency can only point one
    way, and a five-line row lookup is not worth a third module to hold it. If a
    third caller ever appears, ``bff/session.py`` is where it goes — that is already
    the home for derivations two resources must agree on."""
    for row in (run.summary or {}).get("sites") or []:
        try:
            if int(row.get("tooth", -1)) == tooth:
                return row
        except (TypeError, ValueError):
            continue
    return None


@router.get("/{case_id}/sites/{tooth}/acceptance", response_model=SiteAcceptanceView)
def site_acceptance(case_id: str, tooth: int, request: Request) -> SiteAcceptanceView:
    """The acceptance catalog's reading of THIS site. 404 without a done current run
    — pre-run Declare genuinely has nothing to measure, and a zero-filled table would
    claim otherwise; 404 for a tooth this run never aligned, in the same words the
    Adjust precondition uses."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run = _require_done_run(session, case_id)
    row = _summary_row_for(run, tooth)
    if row is None:
        raise HTTPException(404, f"tooth {tooth} carries no verdict from case "
                                 f"{case.id!r}'s current run — there is nothing "
                                 f"measured to hold against the acceptance bands")
    evaluation = evaluate_acceptance(row)
    rework = row.get("rework") if isinstance(row.get("rework"), dict) else {}
    return SiteAcceptanceView(
        tooth=tooth,
        run_id=run.run_id or run.job_id,
        overall_band=str(evaluation["overall"]["band"]),
        missing=[str(k) for k in evaluation["overall"]["missing"]],
        metrics=list(evaluation["metrics"]),
        stale_metrics=[str(m) for m in (rework.get("stale_metrics") or [])],
        context=dict(evaluation.get("context") or {}),
    )


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

def _confirmation_run_id(session: CaseSession) -> Optional[str]:
    return (session.confirmation.run_id
            if session.confirmation is not None else None)


def _billing_dispositions(session: CaseSession, run: RunSession) -> Dict[str, str]:
    """The dispositions the invoice prices against: the STANDING confirmation's when
    it names this run; the operator's WITHHOLD DRAFT when there is no confirmation at
    all, which resolves every un-dropped site to release.

    That default is confirm's own rule (client 2026-07-27 #4: "omission means
    release"), read here rather than re-invented: a case that reached Deliver is a
    case being delivered, and an invoice that quoted zero until someone clicked every
    site would be describing a different flow than the one the confirm route
    implements.

    THE DRAFT IS PRICED (gap ``drop-a-cap-from-adjust``, 2026-07-31), because this
    module's own rule demands it: what the operator READ and what they were CHARGED
    cannot diverge (``derive_invoice``'s one-derivation note). ``confirm_case``
    pre-fills its dispositions from exactly this map, so quoting a dropped cap at the
    full release rate right up until the confirmation lands would be an invoice
    describing a different act than the one the next click performs. Reading the
    draft here also keeps the price honest ACROSS a retirement: dropping a cap the
    standing confirmation released retires that confirmation, and without this the
    invoice would spring back to full price at the exact moment the operator said
    "don't ship it".

    A CONFIRMATION NAMING ANOTHER RUN IS NOT THAT STATE, and conflating the two was
    a money hole (audit finding 1, 2026-07-31). It happens with no race at all:
    ``clear_current_run`` fires at three boundaries and deliberately leaves the
    confirmation standing (pinned by test_pricing), so one re-run later a
    confirmation sealed over run A sits beside a done run B. Returning ``{}`` there
    silently dropped every withhold the operator had signed and priced every site as
    released — a bill FOR evidence nobody confirmed, on a case whose release could
    then never succeed (the sha re-derives over run B and can never equal run A's).
    Fail-open on money is the over-claiming direction, so it refuses instead. The
    honest act is named in the refusal."""
    confirmation = session.confirmation
    if confirmation is None:
        return withhold_intents_of(session)
    current = run.run_id or run.job_id
    if confirmation.run_id != current:
        raise HTTPException(
            409, f"the standing confirmation covers run {confirmation.run_id!r}, "
                 f"but the case's current run is {current!r} — the case changed "
                 f"under its own signature, and neither its price nor its "
                 f"dispositions can be read off a confirmation that does not "
                 f"describe it; re-confirm over the current evidence")
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


_PREVIEW_MESH_MEDIA_STL = "model/stl"
_PREVIEW_MESH_MEDIA_DEFAULT = "application/octet-stream"


@router.get("/{case_id}/runs/current/preview-mesh/{filename}")
def case_preview_mesh(case_id: str, filename: str, request: Request) -> FileResponse:
    """One PACKAGE MESH's bytes, for IN-APP RENDERING (client 2026-08-01: "the
    previews of the artifacts") — EVIDENCE class, ungated like the QC images.

    The disclosure decision, stated once so it never has to be re-litigated: a
    RENDERED view of what the run produced is evidence in exactly the sense the QC
    images are — the operator must see what they are signing and paying for before
    they sign and pay for it. The artifact DOWNLOAD list stays release-gated exactly
    as it is ("even listing is disclosure" holds for a mill-ready download); this
    endpoint serves geometry for RENDERING, named by the server, and is not a
    download route in disguise — it refuses any filename the run's own package does
    not name, the same as the QC endpoint refuses one that is not a QC image.

    ACT-flavored preconditions (409, not 404), unlike the QC endpoint: this feeds a
    live in-app render the operator is mid-decision over, the same conflict class as
    confirm/release rather than a plain missing resource."""
    settings, store = _context(request)
    _case_or_404(settings, case_id)
    session = store.load(case_id)
    run = _require_done_run_for_act(session, case_id, "preview")
    # defense in depth: an encoded slash survives the route match into the param,
    # so shape-refuse before the membership check ever touches a path (the QC
    # endpoint's own guard, mirrored)
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(404, f"{filename!r} is not among the run's package "
                                 f"files")
    if filename not in run.package_files:
        raise HTTPException(404, f"{filename!r} is not among the run's package "
                                 f"files")
    path = _run_dir(settings, case_id, run) / filename
    if not path.is_file():
        raise HTTPException(404, f"{filename!r} is missing from the run directory "
                                 f"— the run's package claims it, but the file is "
                                 f"not there to serve")
    media_type = (_PREVIEW_MESH_MEDIA_STL if filename.endswith(".stl")
                  else _PREVIEW_MESH_MEDIA_DEFAULT)
    return FileResponse(path, media_type=media_type, filename=filename)


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

    AN OMISSION IS RESOLVED AGAINST THE OPERATOR'S DRAFT FIRST (2026-07-31): a cap
    dropped at Adjust (``SiteSession.withhold_intent``) pre-fills its own withhold
    here. That draft is NOT a signature and never becomes one — naming the site in
    this body overrides it, and what is sealed is the map this route resolved.

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
    """The stub's body: the explicit act, and the PRECONDITION naming the document
    the operator read. ``authorize`` must be literally true — the stub authorizes
    nothing implicitly.

    ``invoice_fingerprint`` IS NOT AN AMOUNT AND MUST NEVER BECOME ONE (audit
    2026-07-31). Nothing bound the price the operator READ to the price they were
    CHARGED: the checkout renders an invoice fetched once, and ``authorize_payment``
    re-derives at mutation time. ``turnaround`` is client-settable and fires no reset
    boundary, so a ``PUT {"turnaround": "rush"}`` from a second tab after the dialog
    rendered moved the server price from $32.00 to $48.00 while the sticky bar still
    read "Pay $32.00 (demo)" — and the click charged $48.00 and returned 200.
    ``_mutate_signing`` does not close this: it refuses a CAS loss DURING the
    mutation, and that write landed before the POST.

    So the precondition is a VERSION, not a figure — the opaque digest the invoice
    served (``bff.pricing.invoice_fingerprint``), echoed back. It carries no claim: a
    client cannot express "charge me $0" with it, only "this is the document I was
    shown", which the server re-derives and compares for itself. The same shape as
    the evidence-drift 409 the Deliver surface already handles.

    OPTIONAL ON THE WIRE, and the reason is worth stating rather than discovering.
    Every refusal this route already owns — no confirmation, a confirmation naming
    another run, already paid — must keep its own 409 and its own words; a required
    field would turn all three into a pydantic 422 before the route ever ran, and a
    refusal that stops naming the real problem is a worse trade than the residual.
    The product's own checkout always sends it (it cannot even offer to pay without a
    fetched invoice — CheckoutPage disables the button on a loading or errored one),
    so the walked failure is closed. What stays open is a hand-rolled client that
    omits it, which is exactly the class of caller HTTP's own If-Match leaves open."""

    model_config = ConfigDict(extra="forbid")

    authorize: bool
    invoice_fingerprint: Optional[str] = None


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
        #
        # THE DRAFT SITS BETWEEN THEM (gap ``drop-a-cap-from-adjust``, 2026-07-31).
        # A cap dropped at Adjust pre-fills its own withhold, so a decision taken
        # hours before the signing screen is not silently released by omission. The
        # PRECEDENCE is the point: body → draft → release. THE INTENT IS A DRAFT AND
        # THIS IS THE ACT — an intent is not a signature, so a body that names the
        # site explicitly overrides it, and what gets SEALED is still the map this
        # route resolved and the operator signed, never the session field. The
        # confirmation remains the only place a disposition is sealed.
        drafted = withhold_intents_of(session)
        dispositions = {
            str(t): body.dispositions.get(str(t), drafted.get(str(t), "release"))
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
            # the SHAPE those bytes were encoded under (audit finding 4,
            # 2026-07-31), from the same build that just wrote them — so the
            # display half can retire the moment the shape moves, without
            # re-hashing the run's QC bytes to find out
            bundle_version=BUNDLE_VERSION,
        )
        # THE RESOLVED DISPOSITION GOES BACK ONTO THE SITE (audit 2026-07-31). The
        # draft fed this map; nothing fed the draft back, so "intent = withhold,
        # signed = release" was a reachable and then PERMANENT state: Adjust went on
        # rendering "1 dropped" and offering "bring this cap back" over a cap the
        # confirmation had released, the invoice billed it at full rate, and a second
        # DROP was a silent 200 no-op (``put_withhold_intent``'s equality early
        # return fired before the contradiction was judged). Writing the signature
        # back makes that state unreachable rather than merely detectable — the
        # signature is the stronger act, so it is the one that settles the field.
        # Every tooth here already has a SiteSession (``_require_every_site_resolved``
        # refuses a site with no rung), so this creates nothing.
        for tooth_key, act in dispositions.items():
            site_session = session.sites.get(tooth_key)
            if site_session is not None:
                site_session.withhold_intent = (act == "withhold")
        withheld = sorted(int(t) for t, act in dispositions.items()
                          if act == "withhold")
        record_activity(
            session, ACT_CONFIRMED,
            f"confirmation sealed over run {run.run_id or run.job_id} — "
            f"{len(teeth) - len(withheld)} site"
            f"{'' if len(teeth) - len(withheld) == 1 else 's'} to release"
            + (f", {len(withheld)} withheld" if withheld else "")
            + f"; terms {TERMS_VERSION} accepted")

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
    follow), refusing until it is re-confirmed under the current terms.

    TWO MORE GATES ARRIVED WITH THE AMOUNT (audit 2026-07-31), each closing a walked
    failure rather than a hypothetical one — see the refusals in ``apply``.

    AND IT RIDES THE SIGNING WRITE PATH (``_mutate_signing``), not the retrying one.
    The moment this record carried money it became signature-shaped: ``_mutate_
    session`` re-loads and re-applies after a lost CAS, so a rival ``turnaround`` PUT
    landing in that window re-derived the charge UPWARD and still returned 200 — the
    operator authorized one number and was charged another, with no re-read and no
    consent. Deriving fresh is correct doctrine; charging a number the authorizing
    act never saw is not, and under-claiming here means refusing."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    if not body.authorize:
        raise HTTPException(422, "the payment stub authorizes nothing implicitly — "
                                 "the act is {\"authorize\": true}, or no act at "
                                 "all")

    def apply(session: CaseSession) -> None:
        # ONCE (audit finding 3). Nothing checked this record for existence, so a
        # second POST re-priced off the CURRENT document and OVERWROTE the receipt —
        # and ``turnaround`` is client-settable and fires no reset boundary, so the
        # recorded charge could be LOWERED after the work was billed at the higher
        # rate, leaving the rush charge recorded nowhere. When a real provider
        # replaces this route's body the same second POST becomes a second CHARGE,
        # and this refusal is the idempotency key an amount-carrying stub owes.
        if session.payment is not None and session.payment.payment_authorized:
            raise HTTPException(
                409, f"case {case_id!r} is already paid — authorized at "
                     f"{session.payment.at}, and that record is what was charged; a "
                     f"second authorization would re-price off the case as it "
                     f"stands now and overwrite it. The door back is POST "
                     f"/api/case-sessions/{case_id}/delivery/reset, which withdraws "
                     f"the confirmation, the payment and the release together")
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
        run = _require_done_run_for_act(session, case_id, "pay for")
        # AND THE CONFIRMATION MUST NAME *THAT* RUN (audit finding 1, 2026-07-31).
        # The gate above asks only that SOME run be done. A reset boundary clears
        # the run pointer and deliberately leaves the confirmation standing, so one
        # re-run later a confirmation sealed over run A sits beside a done run B —
        # and paying then charged for evidence nobody signed, at the full released
        # rate, on a case whose release could never succeed afterwards (the sha
        # re-derives over run B and can never equal run A's). RELEASE has always
        # stood on the confirmation of the run it discloses; payment must stand on
        # the confirmation of the run it PRICES, or the two acts describe different
        # cases. Stated here as well as in ``_billing_dispositions`` so the refusal
        # names the ACT rather than the derivation that noticed.
        current = run.run_id or run.job_id
        if confirmation.run_id != current:
            raise HTTPException(
                409, f"the standing confirmation covers run "
                     f"{confirmation.run_id!r}, but case {case_id!r} is now on run "
                     f"{current!r} — paying would charge for evidence nobody "
                     f"confirmed, and release would refuse afterwards anyway; "
                     f"re-confirm over the current evidence, then authorize")
        # THE SERVER PRICES AT AUTHORIZATION TIME (2026-07-31), inside the mutation,
        # off the FRESH document — the same derivation the operator just read. The
        # body carries no amount and never will; what is recorded is what this
        # server charged, with the card version and turnaround it charged under, so
        # a later repricing (a turnaround change fires no boundary) leaves the
        # receipt readable instead of retroactively rewritten.
        invoice = derive_invoice(case, session)
        # AND IT MUST BE THE DOCUMENT THE OPERATOR READ (audit 2026-07-31). Deriving
        # fresh is correct doctrine; charging a figure no surface ever displayed is
        # not. Compared LAST, after every gate above, so a case that is unpayable for
        # a better reason still refuses in that reason's own words.
        if (body.invoice_fingerprint is not None
                and body.invoice_fingerprint != invoice.fingerprint):
            raise HTTPException(
                409, f"the price moved since you read it — case {case_id!r} now "
                     f"prices as invoice {invoice.fingerprint!r} and the "
                     f"authorization names {body.invoice_fingerprint!r}. Turnaround "
                     f"and dispositions both reprice a case without moving its "
                     f"evidence, so nothing here failed; re-read GET "
                     f"/api/case-sessions/{case_id}/invoice and authorize again over "
                     f"the figure it shows")
        session.payment = PaymentRecord(payment_authorized=True, provider="stub",
                                        at=_now(),
                                        amount_cents=invoice.total_cents,
                                        currency=invoice.currency,
                                        rate_card_version=invoice.rate_card_version,
                                        turnaround=invoice.turnaround)
        # the AMOUNT is in the narrative because it can legitimately differ from
        # today's invoice (a turnaround change reprices going forward and fires no
        # boundary) — "what was charged, and when" must be readable in its own terms
        record_activity(session, ACT_PAYMENT_AUTHORIZED,
                        f"payment authorized (stub) — {invoice.total_cents} "
                        f"{invoice.currency} cents at rate card "
                        f"{invoice.rate_card_version}, {invoice.turnaround} "
                        f"turnaround")

    session = _mutate_signing(store, case_id, apply, "payment",
                              lambda s: s.payment)
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
    a stale write look current.

    THE ACTIVITY LOG IS CARRIED FORWARD TOO (2026-07-31), and it is the one exception
    to the paragraph above, so it is named here rather than discovered later. A log
    whose erasure erased the record of the erasure would hide the single act nobody
    could otherwise see — "why is this case back at intake?" is exactly the question a
    narrative exists to answer. The reset is appended to the log it survives. Nothing
    else survives: the log holds words about acts, never the acts' own records, so
    carrying it forward returns no state to the case."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        fresh = CaseSession(case_id=session.case_id, tenant_id=session.tenant_id,
                            version=session.version,
                            activity=list(session.activity),
                            activity_recorded=session.activity_recorded)
        for field in CaseSession.model_fields:   # on the CLASS (pydantic 2.11+)
            setattr(session, field, getattr(fresh, field))
        record_activity(session, ACT_CASE_RESET,
                        "the case was reset to fresh intake — no system, no "
                        "declarations, no previews, no run, no signatures; the "
                        "landed run directories survive as history")

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
        record_activity(session, ACT_DELIVERY_RESET,
                        "the confirmation, the payment and the release were "
                        "withdrawn together so the delivery flow can be walked "
                        "again — the run and every site rung stand where they were")

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
    the stubbed payment is authorized; AND WHAT WAS PAID COVERS WHAT IS ABOUT TO BE
    DISCLOSED. Persists WHAT was released, over which evidence, with the withheld
    sites already dropped from the released set.

    THE AMOUNT IS RE-DERIVED AT THE DISCLOSURE EDGE (audit finding 2, 2026-07-31).
    Gating on the ``payment_authorized`` BOOLEAN alone was a hole with two doors,
    and neither needed a race:

      - DISPOSITIONS sit outside the evidence hash by design (they are the
        operator's acts, not the run's facts — bff/evidence.py), so re-confirming
        four withholds into releases moves no sha at all. Pay a
        withhold-discounted invoice, re-confirm wide, release: every site
        disclosed against a receipt for one.
      - TURNAROUND is client-settable and deliberately fires no boundary. Pay
        standard, upgrade to rush, release: rush work at the standard rate.

    Both are the SAME defect — the price is a function of the case, the case can
    legitimately move after payment, and only the disclosure edge is in a position
    to compare. So it compares, here, at the last moment before anything leaves the
    building."""
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
        # WHAT WAS PAID MUST COVER WHAT SHIPS (audit finding 2). ``derive_invoice``
        # is the same derivation the operator read and the payment route charged
        # under, run once more over the case AS IT STANDS NOW.
        priced = derive_invoice(case, session)
        paid = session.payment.amount_cents
        if paid is None:
            # a record persisted before this module existed carries no amount. It
            # is refused rather than waved through: "we cannot tell what was paid"
            # is not a reason to disclose, and the door back re-walks the flow at
            # today's price. Under-claiming, the ``adjustments`` precedent.
            raise HTTPException(
                409, f"case {case_id!r} carries a payment record from before this "
                     f"server priced anything, so what was charged cannot be read "
                     f"— re-authorize through POST /api/case-sessions/{case_id}/"
                     f"delivery/reset and the payment route before releasing")
        if paid < priced.total_cents:
            raise HTTPException(
                409, f"the authorized payment does not cover this case as it now "
                     f"stands: {paid} {priced.currency} cents were authorized and "
                     f"the case prices at {priced.total_cents} — a shortfall of "
                     f"{priced.total_cents - paid}. Dispositions and turnaround "
                     f"both move the price without moving the evidence hash, so "
                     f"the sha check above cannot see this; re-authorize over the "
                     f"current invoice (POST /api/case-sessions/{case_id}/delivery/"
                     f"reset withdraws the three records so the flow can be walked "
                     f"again) before releasing")
        session.release = ReleaseRecord(
            at=_now(),
            run_id=run.run_id or run.job_id,
            evidence_sha256=confirmation.evidence_sha256,
            # the ONE shared derivation (session.released_teeth_of): the gate and
            # the display half must read the identical set off the same map
            released_teeth=released_teeth_of(confirmation.dispositions),
        )
        released = session.release.released_teeth
        record_activity(session, ACT_RELEASED,
                        f"artifacts released for run {run.run_id or run.job_id} — "
                        + (", ".join(f"tooth {t}" for t in released)
                           if released else "no site released"))

    session = _mutate_signing(store, case_id, apply, "release",
                              lambda s: s.release)
    return _detail(case, session, settings)


# --- the artifact endpoints (class 2: DELIVERABLES, gated) ------------------------------

class ArtifactFacts(BaseModel):
    """ARTIFACT FACTS (boolean-engine plan 4c / clinical-pipeline-plan Stage 5): what
    the worker's manifest measured about this ONE mesh at emit time — the geometry a
    lab or a reviewer would otherwise have to open the file to learn. ``watertight``
    is the open/closed fact verbatim: an open-arch artifact reads False, a closed
    model reads True — no verdict of ours, the worker's own reading, served through."""

    triangle_count: int
    watertight: bool


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
    # THE ARTIFACT CATALOGUE (§10-AT 4b, the client's repeated "what is this
    # file"): one served sentence per known artifact shape, composed HERE so the
    # download list and the analysis digest speak identically. None for a name
    # this catalogue does not know — the surface renders nothing, never a guess.
    description: Optional[str] = None
    # SCHEMA ADDITIVITY (boolean-engine plan 4c): None for a non-mesh file, for a
    # name the manifest never measured, or for a run whose manifest predates this
    # field entirely — the manifest is read defensively (``_manifest_facts``), so an
    # old-shaped record on disk still serves a full listing, just without this.
    facts: Optional[ArtifactFacts] = None


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




# name-shape → the sentence (ordered; first match wins). Names are the emit
# lanes' own stable contracts — a new artifact earns a row here in the same
# change that starts emitting it.
_ARTIFACT_SENTENCES: "list[tuple[str, str]]" = [
    ("-scanned-cap.stl",
     "the scan's own surface at the healing cap, isolated — what the scanner saw of "
     "the cap, nothing else"),
    ("-arch-with-healingcaps.stl",
     "the open arch fused with the aligned library caps — the alignment made solid"),
    ("-arch-with-constructions.stl",
     "the open arch fused with the chosen construction parts at their certified poses"),
    ("-arch-capless.stl",
     "the open arch with each cap replaced by its exact recess (the 1.8mm inspection dish)"),
    ("-arch-platform.stl",
     "the open arch with the shallow platform countersink — the floor showing the gingival offset"),
    ("-arch-open-holes.stl",
     "the open scan with each cap's seat cut clean to the gingival floor — the hole "
     "as the lab expects it"),
    ("-arch-socketless.stl",
     "preview layer: the arch without its recess faces (the tinted view's base)"),
    ("-socket-dish.stl",
     "preview layer: the dish recess surfaces alone, tinted in the preview"),
    ("-socket-platform.stl",
     "preview layer: the platform recess surfaces alone, tinted in the preview"),
    ("-implant.json",
     "the site's pose record — the certified matrix, identity and provenance"),
    ("view.html",
     "a standalone browser view of this package"),
    ("manifest.json",
     "the package manifest — files, hashes, the relief record and production notes"),
    ("-upper.stl", "the doctor's scan, exactly as uploaded"),
    ("-lower.stl", "the doctor's scan, exactly as uploaded"),
]


def artifact_description(name: str) -> Optional[str]:
    """The catalogue sentence for a known artifact name-shape, else None. The
    per-site construction/cap meshes match by their vendor/part infixes below
    the suffix table; anything unrecognized is honestly undescribed."""
    for suffix, sentence in _ARTIFACT_SENTENCES:
        if name.endswith(suffix):
            return sentence
    if "-scanbody-" in name and name.endswith(".stl"):
        return "the construction part at its certified pose, alone"
    if name.endswith(".png"):
        return "QC render — the run's own evidence image"
    return None


def _manifest_facts(run_dir: Path, case_id: str) -> Dict[str, ArtifactFacts]:
    """The worker's manifest, reduced to its per-file ``facts`` blocks, by name —
    read ONCE per listing (a single stat+parse, not a per-artifact cost) rather than
    threaded as a parameter through every ``_artifact_file`` call.

    DEFENSIVE THROUGHOUT (schema additivity, boolean-engine plan 4c): a run whose
    manifest predates this feature, a manifest that fails to parse, or one simply
    absent from the run directory all resolve to ``{}`` — every artifact's facts
    then reads None, never a 500 over a file this endpoint does not itself own the
    shape of. The manifest is the WORKER's own record; a malformed one is the
    worker's problem to fix, not a reason to break the listing."""
    path = run_dir / f"{case_id}-manifest.json"
    if not path.is_file():
        return {}
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    facts: Dict[str, ArtifactFacts] = {}
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        name, raw = entry.get("name"), entry.get("facts")
        if isinstance(name, str) and isinstance(raw, dict):
            try:
                facts[name] = ArtifactFacts(**raw)
            except Exception:
                continue  # a facts block this schema cannot read is absence, not a crash
    return facts


def _artifact_file(run_dir: Path, name: str, case_id: str,
                   teeth: List[int],
                   facts_by_name: Optional[Dict[str, ArtifactFacts]] = None
                   ) -> ArtifactFile:
    """One listed deliverable with the facts the delivery surface needs beyond its
    name: how big it is, which site it belongs to, and (boolean-engine plan 4c) what
    the worker's own manifest measured about its geometry. The size is read from the
    run directory at list time (the run dir is immutable, so this is a stat, not a
    derivation); a file the package claims but disk no longer holds reports None —
    visible as a gap rather than smoothed into a zero."""
    path = run_dir / name
    return ArtifactFile(
        name=name,
        size_bytes=(path.stat().st_size if path.is_file() else None),
        tooth=tooth_of_file(name, case_id, teeth),
        description=artifact_description(name),
        facts=(facts_by_name or {}).get(name),
    )


# --- the paid invoice, riding the download bundle (client 2026-08-09: "when
# downloading the mesh you get the 4 requirements that I asked for plus the invoice
# that they paid for") ---------------------------------------------------------------
#
# TWO THINGS THIS SECTION IS DELIBERATELY NOT: it is not a fifth run-package file —
# ``run.package_files`` is the WORKER's own claim about what it wrote, and this
# document did not come from the worker, so it never enters that list or touches
# ``fetch_artifact``'s ``filename not in run.package_files`` check. And it is not
# priced here a second time — every figure below is ``derive_invoice``'s own line,
# read back rather than recomputed, so a withheld site's $0 and an exception's half
# rate are exactly the fold the checkout already rendered (the one pricing rule,
# now with a second reader instead of a second definition).
#
# GATED ON PAYMENT, DELIBERATELY NARROWER than ``_require_valid_release``: the run's
# own STL files describe EVIDENCE, which can drift (a re-confirm moves the sha), so
# they need the full release chain re-verified on every read. The invoice describes
# what was CHARGED, which ``authorize_payment`` fixes the instant it lands and does
# not move again on this run — so it may serve before a release exists at all, which
# is also the honest answer to "can the lab see its own receipt before disclosing
# anything": yes, it already paid for it.

INVOICE_ARTIFACT_NAME = "invoice"


def _require_paid(session: CaseSession, case_id: str) -> PaymentRecord:
    """The invoice document's own gate. Named in the refusal, the same voice every
    other Deliver refusal uses: what stands in the way, and the door through it."""
    payment = session.payment
    if payment is None or not payment.payment_authorized:
        raise HTTPException(
            409, f"the invoice document is not available for case {case_id!r} — "
                 f"payment has not been authorized yet; confirm over the assurance "
                 f"evidence, then authorize payment (stub) before requesting the "
                 f"invoice")
    return payment


def _money(cents: int, currency: str) -> str:
    """Integer-cents formatting, mirroring the product's own ``formatMoney`` —
    never a float, so this document and the checkout can never round differently."""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}${whole}.{part:02d}" if currency == "USD" \
        else f"{sign}{whole}.{part:02d} {currency}"


def _invoice_document(case: CaseRecord, run: RunSession, invoice: InvoiceView,
                      assurance: AssuranceView, payment: PaymentRecord,
                      dispositions: Dict[str, str]) -> str:
    """The document itself — composed HERE, server-side, from facts every one of
    which already exists elsewhere on the case: ``invoice``'s own priced lines
    (``derive_invoice``, never re-priced), the payment record's own receipt facts
    (what was actually charged, which can differ from ``invoice.total_cents`` if the
    case repriced after payment — both are shown, neither invented), and the
    released/withheld split off the SAME disposition map ``derive_invoice`` folded
    (``_billing_dispositions``, read again rather than re-derived — the standing
    withhold fold, mirrored, per the invoice view's own ``derive_invoice`` note)."""
    released = sorted(site.tooth for site in assurance.sites
                      if dispositions.get(str(site.tooth), "release") != "withhold")
    withheld = sorted(site.tooth for site in assurance.sites
                      if dispositions.get(str(site.tooth), "release") == "withhold")
    rows = "".join(
        f"<tr><td>{html.escape(line.label)}</td><td>{line.quantity}</td>"
        f"<td>{_money(line.amount_cents, invoice.currency) if line.billed else 'not billed'}</td></tr>"
        for line in invoice.lines)
    withheld_row = (
        f"<p data-role=\"invoice-withheld\">Withheld — not released, not billed: "
        + ", ".join(f"tooth {t}" for t in withheld) + ".</p>"
        if withheld else "")
    receipt = (
        f"<p data-role=\"invoice-receipt\">Charged "
        f"{_money(payment.amount_cents, payment.currency or invoice.currency)} at "
        f"{html.escape(payment.at)}"
        + (f" under rate card {html.escape(payment.rate_card_version)}"
           if payment.rate_card_version else "")
        + (f", {html.escape(payment.turnaround)} turnaround"
           if payment.turnaround else "")
        + ".</p>"
        if payment.amount_cents is not None else
        f"<p data-role=\"invoice-receipt\">Authorized at {html.escape(payment.at)} — "
        f"no amount was recorded with this payment.</p>")
    case_id = html.escape(case.id)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>Invoice — case {case_id}</title></head><body>"
        f"<h1>Invoice — case {case_id}</h1>"
        f"<p data-role=\"invoice-run\">Run {html.escape(invoice.run_id)}.</p>"
        f"<p data-role=\"invoice-released\">Released sites: "
        + (", ".join(f"tooth {t}" for t in released) if released else "no site")
        + ".</p>"
        + withheld_row
        + "<table data-role=\"invoice-lines\"><thead><tr><th>Line</th><th>Qty</th>"
          f"<th>Amount</th></tr></thead><tbody>{rows}</tbody>"
          "<tfoot><tr><th colspan=\"2\">Total</th>"
          f"<th data-role=\"invoice-total\">"
          f"{_money(invoice.total_cents, invoice.currency)}</th></tr></tfoot></table>"
        + receipt
        + "</body></html>"
    )


def _invoice_document_for(case: CaseRecord, session: CaseSession,
                          run: RunSession) -> Tuple[str, PaymentRecord]:
    """One call, both readers (the listing's size stat and the document route) —
    so the bytes ``list_artifacts`` reports as this file's size are exactly the
    bytes the fetch route serves, never two derivations that could drift apart."""
    payment = _require_paid(session, case.id)
    assurance = derive_assurance(case, session)
    invoice = derive_invoice(case, session)
    dispositions = _billing_dispositions(session, run)
    body = _invoice_document(case, run, invoice, assurance, payment, dispositions)
    return body, payment


@router.get("/{case_id}/runs/current/artifacts", response_model=ArtifactsView)
def list_artifacts(case_id: str, request: Request) -> ArtifactsView:
    """The DELIVERABLE list — even listing is disclosure (names leak what was
    made), so the release gate sits on the list too.

    THE INVOICE RIDES HERE TOO (client 2026-08-09), appended after the worker's own
    package files and BEFORE nothing new is checked: a valid release already implies
    ``session.payment_authorized`` (``release_case`` refuses without it), so the
    ``if`` below is documentation of the real precondition rather than a second gate
    — it stays explicit so a future loosening of the release chain cannot silently
    ship this row unpaid."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run, release = _require_valid_release(case, session, settings)
    teeth = _summary_teeth(run)
    withheld = sorted(set(teeth) - set(release.released_teeth))
    names, held_case_files = split_released_files(
        run.package_files, teeth, release.released_teeth, case.id)
    run_dir = _run_dir(settings, case.id, run)
    facts_by_name = _manifest_facts(run_dir, case.id)
    files = [_artifact_file(run_dir, name, case.id, teeth, facts_by_name)
            for name in names]
    if session.payment_authorized:
        body, _payment = _invoice_document_for(case, session, run)
        files.append(ArtifactFile(name=INVOICE_ARTIFACT_NAME,
                                  size_bytes=len(body.encode("utf-8")), tooth=None,
                                  description="the service invoice for this release"))
    return ArtifactsView(run_id=run.run_id or run.job_id,
                         files=files,
                         withheld_teeth=withheld,
                         withheld_case_files=held_case_files)


@router.get("/{case_id}/runs/current/artifacts/" + INVOICE_ARTIFACT_NAME)
def fetch_artifact_invoice(case_id: str, request: Request) -> HTMLResponse:
    """The invoice document's own bytes. Registered here, BEFORE ``fetch_artifact``'s
    ``{filename}`` route below — route order is match order (Starlette tries routes
    in registration order), so this literal path wins before the generic one ever
    sees ``"invoice"`` and refuses it for not being in ``run.package_files`` (it
    never is; it is composed here, not written by the worker)."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    session = store.load(case_id)
    run = _require_done_run_for_act(session, case_id,
                                    "produce an invoice document for")
    body, _payment = _invoice_document_for(case, session, run)
    return HTMLResponse(
        content=body,
        headers={"Content-Disposition": "attachment; filename=\"invoice.html\""})


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
