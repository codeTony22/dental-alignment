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

import datetime
import enum
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from .evidence import BUNDLE_VERSION


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


class AlignmentEvidence(BaseModel):
    """ONE operator alignment measurement, persisted so it survives the run that
    received it (§10-AD, client 2026-08-02: "when adjustment and rerunning the
    alignment it does not take effect"). The payload is exactly what the adjust
    route received — world/canonical-frame points, replayable against any future
    run of the SAME scan — plus the act's own identity. The bare rotation NUDGE is
    deliberately never recorded here: its provenance is eyeball with no marks, and
    auto-re-applying it would silently promote the weakest evidence class.

    What clears it, exhaustively — NOT run boundaries, which is the whole point:
    a re-mark of this site's centre clears everything (the pair-integrity rule: a
    moved centre retires measurements made against the old one), and a variant
    re-declaration or system switch retires the "pairs" kind alone (audit
    2026-08-04: a pair's PART half was measured against the part the site no
    longer declares; the scan-frame kinds survive because the scan did not
    change). A JAW change retires nothing — it moves the alignment's own input,
    not the scan or the part, and the re-apply's own gates judge the result."""

    # "mark" (align-to-mark: one scan point) | "pairs" (fit-by-points: the
    # correspondence list, wire-shaped) | "best_fit" (the refinement act + its
    # search diameter — a correspondence-cutoff ASK, not a part coordinate,
    # which is why it survives the part boundaries that retire "pairs")
    kind: str
    applied_at: str
    # kind="mark": the [x, y, z] scan point
    point: Optional[List[float]] = None
    # kind="pairs": the PairIn dicts exactly as received (part half + scan half)
    pairs: Optional[List[dict]] = None
    # kind="best_fit": the search diameter the operator ran with
    matching_diameter_mm: Optional[float] = None


class SiteSession(BaseModel):
    status: SiteStatus = SiteStatus.DETECTED
    declared_variant: Optional[str] = None
    # THE OPERATOR'S ALIGNMENT EVIDENCE (§10-AD): every applied mark/pairs/best-fit,
    # in apply order — re-applied by every future run AFTER automation, through the
    # same application.adjust functions, with provenance. Survives run boundaries.
    alignment_evidence: List[AlignmentEvidence] = Field(default_factory=list)
    # PER-SITE RELIEF OVERRIDE (§10-B/C, set on Adjustment): this site's own ask,
    # None = the case-level effective value stands. Relief shapes the EMITTED part
    # only (§10-C's measured fact), so setting it moves no rung and retires no
    # review — over a done run it re-emits (§10-AC). Survives run boundaries like
    # the other operator acts.
    gingival_offset_mm: Optional[float] = None
    # THE OPERATOR'S OWN CENTRE (client 2026-07-28): where this site exists because a
    # HUMAN marked it, not because detection found it. Detection misses 2 of the 10
    # sites on this fleet, and a missed cap was previously unworkable — the case
    # record is the only other place a centre lives, and an operator cannot write to
    # the case record. Present ONLY on sites someone marked; a detected site leaves
    # it None and reads its centre from the case as it always did.
    marked_center: Optional[List[float]] = None
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
    # THE DROP, AS A DRAFT (design flow.dc.html dropSite 1345-1354; gap
    # ``drop-a-cap-from-adjust``, 2026-07-31): the operator's standing intent to
    # WITHHOLD this site at confirmation time.
    #
    # It is deliberately NOT a second way to exclude a site. The product already had
    # the act — ``ConfirmationRecord.dispositions`` (release | withhold) — and it was
    # reachable only from Deliver, so an operator abandoning a stubborn cap at Adjust
    # had to carry the decision to the signing screen to record it at all. Two
    # overlapping exclusion concepts would be two gates to keep in step, which is
    # exactly the class of defect audit finding 1 (2026-07-31) found in this module.
    # So this is the SAME concept with a draft stage: it PRE-FILLS the confirmation's
    # dispositions (``confirm_case``), and the confirmation still signs them.
    #
    # An ACT in the allowlist's sense: it says what the operator DOES with a site,
    # never what the site IS. It moves no rung, and the run still aligns the site —
    # skipping the physics would make the decision irreversible without a re-run,
    # and the whole point of a draft is that it can be taken back.
    withhold_intent: bool = False
    # THE ACCEPT-AS-FLAGGED-EXCEPTION DRAFT (client ruling 2026-08-02): withhold_
    # intent's SIBLING — the operator's standing intent to ACKNOWLEDGE this site's
    # flagged (or shared-part-conflicted) verdict in advance, from Adjust, so
    # Deliver's row-by-row checkbox opens PRE-TICKED instead of asking the operator
    # to re-find every row it already discussed with them. ISO timestamp when the
    # draft was given, None otherwise — the same shape as an act's ``at``, not a
    # bare bool, so a reader can say WHEN the exception was accepted.
    #
    # IT IS NOT A SIGNATURE, and never becomes one — the design decision that makes
    # it admissible under AM-4's doctrine, the same reason ``withhold_intent`` is
    # admissible: ``ConfirmIn.acknowledged_flags`` is the row-by-row ACT
    # (deliver.confirm_case), required and unwaived by anything recorded here, and
    # this field never rides into the sealed evidence bundle (``AssuranceView.
    # sealed_facts`` excludes it, exactly as it excludes ``withhold_intent`` — a
    # draft is not evidence the run produced).
    #
    # RESET SEMANTICS DELIBERATELY DIFFER FROM ``withhold_intent``'s (2026-08-02).
    # A withhold is a standing operator PREFERENCE independent of any run's verdict
    # — "don't ship this cap, whatever the physics says" — so it survives every
    # boundary below on purpose (``TestTheIntentSurvivesTheGeometryBoundaries``).
    # An exception-acknowledgment is instead an attestation ABOUT one specific run's
    # specific verdict — "I have looked at THIS flagged row and accept it" — so it
    # cannot honestly survive the run it was given over ceasing to be current: a
    # rework that changes the verdict must not have the OLD acknowledgment silently
    # pre-fill the checkbox for a verdict the operator never actually saw. See
    # ``clear_exception_intents`` for where that boundary is drawn and why it needs
    # a second call site ``clear_current_run``'s own callers do not.
    exception_intent: Optional[str] = None

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
    # THE TURNAROUND ASK (design flow.dc.html speedChips 1159-1160; gap
    # ``turnaround-as-a-case-choice``, 2026-07-31). An ACT in exactly the sense
    # AM-4's allowlist means: it says what the lab ASKED FOR, never what any site
    # IS — no physics reads it, no verdict derives from it.
    #
    # It is deliberately OUTSIDE ``complete`` and outside ``EffectiveChoices.values``:
    # changing it must fire NO reset boundary. The other three describe the shipped
    # PART (the review-reset rule's own words), so a change to any of them retires
    # previews and the current run; a turnaround is a commercial promise about WHEN,
    # touching no geometry, and dropping a case's reviews because the lab upgraded it
    # to rush would be a fabricated invalidation. It is likewise not in ``complete``
    # because the standing default already answers it, so a case is never blocked on
    # a choice nobody has to make.
    turnaround: Optional[Literal["standard", "rush"]] = None

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
    # §10-AM built: the jaw read off the scan's own crown-up axis (application.detection.
    # jaw_from_crown_axis) — "lower"/"upper"/None (a sideways export makes no claim).
    # ADDITIVE Optional, default None: an old session document predating this field loads
    # cleanly with no reading, exactly the store's schema-additivity discipline.
    jaw_reading: Optional[str] = None
    # THE MEASURED HEIGHT + PROPOSAL (client escalation 2026-08-09), keyed by tooth
    # like ``site_capture`` — ``application.detection.SuggestedSiteCapture.
    # measured_cap_height_mm``/``proposed_variant`` verbatim, worker facts written
    # only by the detect route. ADDITIVE, same discipline as ``jaw_reading``: a
    # document written before this pair existed loads with both honestly empty
    # rather than refusing.
    site_measured_height_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    site_proposed_variant: Dict[str, Optional[str]] = Field(default_factory=dict)
    # the VISIBLE cap's own rim (§10-AS.18): the panes' soft-tissue separator
    site_measured_diameter_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    # THE DISCRIMINATOR EVIDENCE (clinical-pipeline-plan.md Stage 1, slice 1a):
    # ``application.detection.SuggestedSiteCapture.rim_below_cusps_mm``/
    # ``void_ratio`` verbatim, keyed by tooth like the pair above -- WHY a site
    # was proposed, not just that it was. ADDITIVE, same discipline as
    # ``site_measured_diameter_mm``: a document written before this pair
    # existed loads with both honestly empty.
    site_rim_below_cusps_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    site_void_ratio: Dict[str, Optional[float]] = Field(default_factory=dict)


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
    (AM-12: a flag is never confirmed in bulk).

    ``adjustments`` is the fork's word AS SEALED — restated in the open beside the
    hash it is folded into. The hash alone cannot be compared against anything
    without re-reading the run's QC bytes off disk, and the display half deliberately
    does not: it kept saying "Released ✓" while the artifact gate 409'd a case whose
    fork had been re-clicked after release. This field is that comparison made cheap
    (``confirmation_covers_fork``), never a second source of truth — the confirm
    route writes it from the same read that builds the bundle. ``None`` is an
    unfaced fork.

    A CONFIRMATION SEALED BEFORE THIS FIELD EXISTED therefore reads as "the fork was
    never faced", and a case that HAD faced it shows as not-released until it is
    re-confirmed. Deliberate, and the same answer bff/evidence.py gives about its
    own shape change: under-claiming a release is the safe direction, the artifact
    gate is unaffected (the bundle's bytes did not move), and a re-confirm over what
    is there now is the honest path every other drift already takes.

    ``terms_accepted``/``terms_version`` are the agreement's new home (plan
    §10-A: "This can be at the time of payment … as a Terms and Conditions or
    more explicit saying someone reviewed the alignment changes and they agree
    to proceed") — moved off Declare's per-site ticks onto this one commercial
    signature. ``terms_accepted`` defaults ``False`` for the same reason
    ``payment_authorized`` used to: a record sealed before this field existed
    never claimed the act, and under-claiming is the safe direction (the same
    honest gap ``adjustments`` reads as for pre-field records). ``terms_version``
    names WHICH text was accepted (``bff.resources.deliver.TERMS_VERSION``) so a
    later swap of the client's real legal text is visible on old records rather
    than silently reinterpreted.

    ``bundle_version`` is the SHAPE the bundle above was built under
    (``bff.evidence.BUNDLE_VERSION`` — audit finding 4, 2026-07-31). The sha alone
    cannot say whether a mismatch means "a number moved" or "this build encodes a
    different document"; the display half needs the second answer without a disk
    read (see ``confirmation_covers_bundle_shape``). ``None`` reads as "sealed
    before the shape was named", which for every such record is true and is drift.

    It rides on the CONFIRMATION only, not on ``ReleaseRecord``: a release is valid
    only while it still covers the current confirmation
    (``release_matches_confirmation``), so the release's own copy could never
    disagree with this one without the record comparison already having failed — and
    a second copy of a fact is a second thing to keep in step."""

    at: str
    run_id: str
    evidence_sha256: str
    dispositions: Dict[str, str] = Field(default_factory=dict)
    acknowledged_flags: List[int] = Field(default_factory=list)
    adjustments: Optional[str] = None
    terms_accepted: bool = False
    terms_version: Optional[str] = None
    bundle_version: Optional[str] = None


class PaymentRecord(BaseModel):
    """THE PAYMENT STUB (plan §4 Deliver): fail-closed — this record exists only
    when someone explicitly authorized, and ``provider: "stub"`` keeps
    stub-authorized sessions PERMANENTLY distinguishable from paid ones once a real
    provider lands. Still never faked deeper than the stub: no receipts, no provider
    ids — inventing those would be a lie wearing a schema.

    THE AMOUNT ARRIVED (gap ``per-site-pricing-model``, 2026-07-31) and it is the one
    fact that had to. The record's original note said "no amounts"; that was right
    while there was no derivation behind an amount, and wrong the moment there was
    one, because a case can be repriced after it is paid (a turnaround change touches
    no physics and fires no boundary — see ``CaseChoices.turnaround``). Without the
    charged figure on the record, "what did this case cost?" could only ever be
    answered by re-deriving TODAY's price and calling it history.

    So: the SERVER prices at authorization time (``bff.pricing``) and writes what it
    charged here, with the rate card version and the turnaround it charged under, so
    an amount is re-readable in its own terms rather than reinterpreted under a later
    card. ``PaymentIn`` still carries nothing but ``authorize`` — an amount a client
    could send would be a status-shaped claim wearing a currency symbol.

    All four are Optional: a record persisted before the invoice existed carries
    none of them, and under-claiming is the safe direction (the ``adjustments``
    precedent). None here means "this authorization predates pricing", never zero."""

    payment_authorized: bool
    provider: str
    at: str
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    rate_card_version: Optional[str] = None
    turnaround: Optional[str] = None


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


# --- THE ACTIVITY LOG (design flow.dc.html pushLog 736-1489 / logRows 1373-1374; gap
# ``session-activity-log``, 2026-07-31) ---------------------------------------------------
#
# The product had no readable narrative of what happened to a case. Every terminal
# record above carries an ``at``, but they are the ENDS of the flow: "when was the run
# authorized?", "when was tooth 13 re-reviewed?", "why is this site adjusted?" were
# unanswerable from the session at all. The per-site rework provenance the worker keeps
# on disk (the run directory's ``<case>-<tooth>-implant.json`` ``adjustments`` list) was
# never read back either.
#
# THE HONESTY QUESTION, DECIDED FIRST, because the design answers it wrongly: its
# ``pushLog`` is a BROWSER array. A list a client maintains — or worse, one a client
# could POST — is a channel for writing claims into the record, and it would read as an
# audit trail while proving nothing. So no route accepts an entry: ``record_activity``
# is called INSIDE the same CAS mutation that lands each act, so an entry exists exactly
# when the act it names actually landed, and a lost CAS race discards the entry with the
# act it belonged to.
#
# AND IT IS A WINDOW, NOT AN AUDIT TRAIL, stated in the shape rather than the prose:
# the store re-reads this document on every request and a size test pins it
# (test_run_resource), so the list is capped at ``ACTIVITY_WINDOW`` and
# ``activity_recorded`` counts every act ever recorded. A surface can then say "the last
# 40 of 137" instead of implying the window is everything. A real audit trail is an
# append-only store of its own, and that is phase-2's story beside real identity —
# claiming one here with a bounded list would be the same fabrication the design's
# browser array is.

ACTIVITY_WINDOW = 40

# The event vocabulary, in ONE place: the wire's words are these, so a surface groups
# and filters on a server fact rather than parsing a sentence. Each act names itself in
# the past tense — a log says what HAPPENED, never what is true now.
ACT_DETECTED = "detected"
ACT_CHOICES_SET = "choices-set"
ACT_SYSTEM_DECLARED = "system-declared"
ACT_SITE_MARKED = "site-marked"
# a DIFFERENT act from the one above, deliberately its own word (2026-08-01): a
# fresh mark buys the operator work to do (post_marked_site's own doctrine), while
# a re-mark is a reset boundary — it retires a preview, a review, the current run
# and any confirmation sealed over it. Conflating the two under one event would
# have a reader of the case's narrative unable to tell "detection missed this
# site" from "the operator corrected a bad centre" apart without opening the diff.
ACT_SITE_REMARKED = "site-remarked"
ACT_SITE_DECLARED = "site-declared"
ACT_SITE_WITHHOLD_INTENT = "site-withhold-intent"
# the accept-as-flagged-exception draft (client ruling 2026-08-02) — the sibling
# events to ACT_SITE_WITHHOLD_INTENT's own pair, one word each direction so a
# reader of the narrative can tell "drafted an acknowledgment" from "withdrew one"
# without opening the detail sentence
ACT_SITE_EXCEPTION_ACKNOWLEDGED = "site-exception-acknowledged"
ACT_SITE_EXCEPTION_WITHDRAWN = "site-exception-withdrawn"
ACT_SITE_PREVIEWED = "site-previewed"
ACT_SITE_REVIEWED = "site-reviewed"
ACT_SITE_REVIEW_WITHDRAWN = "site-review-withdrawn"
ACT_RUN_AUTHORIZED = "run-authorized"
ACT_RUN_LANDED = "run-landed"
ACT_RUN_REFUSED = "run-refused"
ACT_RUN_WITHDRAWN = "run-withdrawn"
ACT_SITE_ADJUSTED = "site-adjusted"
ACT_SITE_RE_READ = "site-re-read"
ACT_ADJUST_DECISION = "adjust-decision"
ACT_CONFIRMED = "confirmed"
ACT_PAYMENT_AUTHORIZED = "payment-authorized"
ACT_RELEASED = "released"
ACT_DELIVERY_RESET = "delivery-reset"
ACT_CASE_RESET = "case-reset"


class ActivityEntry(BaseModel):
    """One act, as it landed. ``at`` is UTC-ISO like every other record here.

    NO ACTOR, for the reason stated above the three signed records: this layer
    authenticates nobody, and a name would be invented. ``tooth`` is present on
    per-site acts and None on case-level ones — never a placeholder, so a reader
    can group by site without guessing which entries belong to no site at all."""

    at: str
    event: str
    detail: str
    tooth: Optional[int] = None


def record_activity(session: "CaseSession", event: str, detail: str,
                    tooth: Optional[int] = None) -> None:
    """Append one act to the case's narrative, inside the caller's mutation.

    Called at the point an act LANDS — after its gates have passed, beside the state
    change it describes — so the log and the state it narrates are written by one CAS
    save or by neither. The stamp is minted here rather than by each caller: one clock
    reading per act, and no route can record a time it chose.

    Oldest entries fall out of the window; ``activity_recorded`` keeps counting, so the
    dropped ones are visible as a number even when their words are gone."""
    session.activity.append(ActivityEntry(
        at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        event=event, detail=detail, tooth=tooth))
    session.activity_recorded += 1
    if len(session.activity) > ACTIVITY_WINDOW:
        del session.activity[:len(session.activity) - ACTIVITY_WINDOW]


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
    # THE CASE'S NARRATIVE (2026-07-31) — the newest ``ACTIVITY_WINDOW`` acts, oldest
    # first, appended only by ``record_activity`` from inside a landing mutation
    activity: List[ActivityEntry] = Field(default_factory=list)
    # every act ever recorded, including the ones the window has dropped: the log is
    # a window, and this number is what stops it being read as the whole history
    activity_recorded: int = 0

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
    the run cannot be forgotten at one boundary and cleared at the other two.

    THE EXCEPTION-ACKNOWLEDGMENT DRAFTS JOIN HERE TOO (2026-08-02,
    ``clear_exception_intents``): every one of them was given over THIS run's
    verdicts, and a run that just stopped being current cannot go on being what an
    acknowledgment describes.

    AND SO DO EVERY SITE'S RUN-DERIVED RUNGS (client 2026-08-06, the stale-flagged
    wedge): FLAGGED and ADJUSTED are rungs only a run's verdict or a tool applied
    over a run can write. When ONE site's boundary retires the CASE's run, an
    untouched neighbour must not keep a verdict whose run no longer exists — the
    queue read "Flagged by the run — no run has measured this fit yet" while
    Adjustment, which needs a run, refused to open. They fall to READY: the
    confirmation that admitted the site to the run still stands (only the CHANGED
    site's own boundary retires that), and READY's pre-run sentence is true. A
    site's alignment evidence is untouched — it re-applies on the next run
    (§10-AD), and the evidence badge carries that story."""
    session.run = None
    session.adjust_decision = None
    clear_exception_intents(session)
    for site in session.sites.values():
        if site.status in (SiteStatus.FLAGGED, SiteStatus.ADJUSTED):
            site.status = SiteStatus.READY


def clear_exception_intents(session: "CaseSession") -> None:
    """Every site's drafted flagged-exception acknowledgment, retired together
    (client ruling 2026-08-02).

    UNLIKE ``withhold_intent``, this draft is tied to a SPECIFIC run's verdict — "I
    acknowledge THIS flagged row" — never a standing operator preference
    independent of the physics (a withhold survives every boundary here on purpose:
    dropping a cap says nothing about what any run finds, so nothing retires it).
    An acknowledgment given over a verdict that is about to stop being current must
    not silently pre-fill Deliver's checkbox against whatever a REWORKED site's row
    says next — that is exactly "a draft acknowledgment of an old run's verdict
    surviving a rework that changed the verdict", the trust failure this function
    exists to close.

    TWO CALL SITES, DELIBERATELY, where ``withhold_intent`` needed none:
    ``clear_current_run`` (the choices/system/declaration/mark reset boundaries,
    where the run pointer is ABOUT to read None) and ``post_run``'s ``claim``
    (case_sessions.py) — a FRESH run may be authorized directly over a still-
    ``done`` one with no reset boundary in between, so a single call site here
    would leave that path re-flagging a site under an acknowledgment nobody gave
    against the NEW verdict."""
    for site in session.sites.values():
        site.exception_intent = None


def clear_confirmation(session: "CaseSession") -> None:
    """THE EVIDENCE BOUNDARY (slice 6): the run's CURRENT deliverables for a site
    changed under the operator's own hand, so nothing signed over the old ones stands.

    Distinct from ``clear_current_run`` on purpose. That boundary fires when the run
    POINTER stops describing the case, and a confirmation is inert without a current
    run anyway (every gate stands on ``_require_done_run``). An ADJUSTMENT is the other
    shape: the run stays current — the tools rewrite the site record, the cap STL and
    the manifest INSIDE that run directory — so the confirmation would keep looking
    valid while the re-derived evidence had already moved. The artifact gate would
    catch it on the next disclosure; the display half would go on reading
    "Released ✓" until then. That divergence was already paid for once (the fork's
    2026-07-28 fix), so an adjustment retires both records HERE rather than leaving
    the cheap half to lie.

    The PAYMENT record deliberately survives: money is not evidence, and the honest
    path after a rework is re-confirm + re-release, not re-charge."""
    session.confirmation = None
    session.release = None


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


def withhold_intents_of(session: "CaseSession") -> Dict[str, str]:
    """The DRAFT disposition map the operator's drops imply — tooth-as-string →
    ``"withhold"``, and nothing for a site nobody dropped (gap
    ``drop-a-cap-from-adjust``, 2026-07-31).

    Shaped as a disposition map on purpose: confirm folds it under the body's own
    entries, and the invoice prices against it while no confirmation exists. Both
    readers then resolve an unnamed site the one way confirm has always resolved one
    (client 2026-07-27 #4: "omission means release"), so the draft and the signature
    are read by identical code and cannot come to mean two different things.

    Lives HERE beside ``released_teeth_of`` for the reason that one does: a second
    reading of "which sites is the operator holding back?" would be a second answer
    waiting to disagree with the first."""
    return {tooth: "withhold" for tooth, site in session.sites.items()
            if site.withhold_intent}


def needs_acknowledgment(site_status: Optional[str],
                         production_note: Optional[str]) -> bool:
    """AM-12's acknowledgment gate — the ONE predicate a row must satisfy before it
    may release without its own row-by-row acknowledgment. LIFTED (2026-08-02) out
    of ``deliver._needs_acknowledgment`` — which read an ``AssuranceSite`` — down to
    the two raw facts it actually tested, so a second, session/run-shaped caller
    (the Adjust-page accept-as-flagged-exception draft, ``post_acknowledge_exception``)
    can share the SAME definition instead of re-deriving a lookalike that could
    drift from it. ``deliver._needs_acknowledgment`` is now a one-line adapter onto
    this.

    TRUE whenever EITHER: the session ladder flagged the site (``SiteStatus.
    FLAGGED``'s own value — a run's verdict), OR the run's production block
    disclosed a fact the operator must weigh before releasing — today, exactly the
    shared-construction-part conflict ``production_note`` carries (plan §10-E,
    finding 2026-07-28). ``site_status`` is a plain string (or None) rather than
    ``SiteStatus`` so a caller holding only ``AssuranceSite.status`` (already a
    string on the wire) need not round-trip it through the enum."""
    return site_status == SiteStatus.FLAGGED.value or production_note is not None


def adjustments_of(session: "CaseSession") -> Optional[str]:
    """The fork's decision WORD as it stands now — "skip", "adjust", or None when
    the fork was never faced. The VALUE alone, never the record: the ``at``/``run_id``
    are attribution, and re-deciding the same way describes the same case (the
    SeatedSelection precedent — an identical re-act must flip no equality and cost
    nobody a re-confirmation).

    Lives HERE beside the file-split rules for the same reason they moved: the
    assurance projection, the evidence bundle and the display half all need this one
    answer, and three readings of "what did the operator decide?" would be three
    answers waiting to disagree."""
    return (session.adjust_decision.decision
            if session.adjust_decision is not None else None)


def confirmation_covers_fork(session: "CaseSession") -> bool:
    """Whether the standing confirmation still covers the fork as it stands NOW.

    The CHEAP half of "the evidence has not moved". The decision word rides inside
    the evidence hash, so a fork clicked after a release retires that release — the
    artifact endpoints have always caught it by re-deriving the whole bundle, QC
    bytes and all. But re-deriving costs a disk read per request, so the display
    half never did it, and the surface kept reading "Released ✓" beside the gate's
    own refusal. The decision is a pure SESSION fact, so this much of the
    re-derivation is free, and the two halves now agree about the fork.

    Everything else in the bundle — the projection's numbers, the QC bytes — stays
    where it was: judged at the gate, on the read that actually discloses."""
    confirmation = session.confirmation
    return (confirmation is not None
            and confirmation.adjustments == adjustments_of(session))


def confirmation_covers_bundle_shape(session: "CaseSession") -> bool:
    """Whether the standing confirmation was sealed under the bundle shape THIS
    build encodes (audit finding 4, 2026-07-31).

    The second cheap half of "the evidence has not moved", and the twin of
    ``confirmation_covers_fork``. The bundle's SHAPE has moved three times already —
    ``adjustments``, ``terms_version``, and every ``AssuranceSite`` field, because
    ``sealed_facts()`` is a ``model_dump`` that emits None-valued keys. Each move
    restages every bundle on disk, the artifact gate catches it by re-deriving, and
    the display half — session-only by design, no disk read per request — kept
    saying "Released ✓" over a case whose every artifact read 409'd. The fork got a
    clause for its own drift; a shape change had none.

    ``None`` is drift, not an exemption: a record sealed before the shape was named
    was sealed under a shape this build no longer writes. Under-claiming a release
    is the safe direction (the ``adjustments`` precedent) and the honest path out is
    the one every other drift takes — re-confirm over what is there now."""
    confirmation = session.confirmation
    return (confirmation is not None
            and confirmation.bundle_version == BUNDLE_VERSION)


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
            session = CaseSession.model_validate_json(path.read_text())
        except Exception as exc:
            raise ValueError(
                f"corrupt session file {path} — refusing to silently reset flow state "
                f"(it may hold a confirmation or payment record): {exc}") from exc
        # RUN-DERIVED RUNGS CANNOT OUTLIVE THE RUN, even on documents persisted
        # before clear_current_run learned to demote them (client 2026-08-06, the
        # stale-flagged wedge): a loaded FLAGGED/ADJUSTED beside run=None is a
        # verdict whose run does not exist — re-derive it as READY here so a
        # standing document heals on its next read. This is a consistency
        # derivation of a status this store itself defines as derived, not a data
        # repair: nothing an operator recorded is touched, and the next CAS save
        # persists it.
        if session.run is None:
            for site in session.sites.values():
                if site.status in (SiteStatus.FLAGGED, SiteStatus.ADJUSTED):
                    site.status = SiteStatus.READY
        return session

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
