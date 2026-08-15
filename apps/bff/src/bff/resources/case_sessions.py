"""THE CASE-SESSION RESOURCE (plan §3, §4 Intake, §7 slices 1+4; grill AM-2/AM-4/AM-7).

The read model (slice 1):

  - ``GET /api/case-sessions`` — the worklist: one row per discovered case with its
    site-queue rollup and run/confirmation state. The 20-scan morning's home screen.
  - ``GET /api/case-sessions/{id}`` — flow-shaped: the case, its sites (worker-suggested,
    overlaid with session state and capture verdicts), the catalogs Declare renders from,
    the relief ceiling per declared variant, the detection record, the operator's
    case-level choices, and the session's own state.

The ACTIONS (slices 4-5b) — writes that carry no claimed outcomes:

  - ``POST /api/case-sessions/{id}/detect`` — runs ``application.detection`` and persists
    the result (worker FACTS). No request body at all; ``?fresh=1`` re-derives.
  - ``PUT /api/case-sessions/{id}/choices`` — the case-level OPERATOR CHOICES only
    (construction part, jaw, relief). The request model is the start of the validation
    corpus (plan §6/AM-9, copy-debt ledger row 4).
  - ``PUT .../system`` and ``PUT .../sites/{tooth}/declaration`` (5a) — the case-scoped
    system and the per-site variant, both reset boundaries.
  - ``POST .../sites/{tooth}/preview`` (5b) — a compute trigger like detect (no body);
    persists the seat FACTS, returns the pane payload response-only.
  - ``POST/DELETE .../sites/{tooth}/review`` (5b) — the operator's two-way ATTESTATION
    over the panes; no body either way, the act is the request itself.
  - ``POST .../adjust-decision`` (client 2026-07-27) — the Delivery-vs-Skip fork,
    recorded: an act about the Adjust STAGE, keyed to the run, gating nothing.
  - ``PUT .../sites/{tooth}/withhold`` (2026-07-31) — dropping a cap: the DRAFT of
    the confirmation's own disposition, reachable from Adjust and reversible.
  - ``PUT .../sites/{tooth}/mark`` (2026-08-01) — an EXISTING site's centre
    corrected by hand: ``post_marked_site``'s exact complement, and a reset
    boundary of its own (a preview, a review, the current run and any
    confirmation sealed over it — all named to the operator before the click
    that fires it, not discovered after).

Every status is still DERIVED: cases and suggestions from ``case_prep.application``,
statuses from the session store. The doctrine is structural and tested: every non-GET
route sits on an explicit allowlist, and no request model carries a status-shaped field
(see test_case_sessions.TestStatusesAreNeverClientWritable).
"""
from __future__ import annotations

import dataclasses
import datetime
import math
import uuid
from typing import Callable, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import (UnknownSelection, construction_parts,
                                           DEFAULT_GINGIVAL_OFFSET_MM, library_groups,
                                           relief_ceiling, require_construction,
                                           require_library_model, require_variant)
from case_prep.application.detection import DetectionResult, ScanUnreadable, detect
from case_prep.application.preview import (PreviewRefused, PreviewSelection,
                                           preview_site)

from .. import status
from ..config import Settings
from ..ports.worker import JobState, WorkerPort
from ..pricing import CURRENCY, TURNAROUNDS, unit_amount_cents
from ..session import (ACT_ADJUST_DECISION, ACT_CHOICES_SET, ACT_DETECTED,
                       ACT_RUN_AUTHORIZED, ACT_RUN_LANDED, ACT_RUN_REFUSED,
                       ACT_RUN_WITHDRAWN, ACT_SITE_DECLARED,
                       ACT_SITE_EXCEPTION_ACKNOWLEDGED,
                       ACT_SITE_EXCEPTION_WITHDRAWN, ACT_SITE_MARKED,
                       ACT_SITE_PREVIEWED, ACT_SITE_REMARKED,
                       ACT_SITE_RIM_POINTS_CLEARED, ACT_SITE_RIM_POINTS_SET,
                       ACT_SITE_REVIEW_WITHDRAWN,
                       ACT_SITE_REVIEWED, ACT_SITE_WITHHOLD_INTENT,
                       ACT_SYSTEM_DECLARED,
                       AdjustDecisionRecord, CaseChoices, CaseSession,
                       DetectedProposal, DetectionRecord, RunSession,
                       SeatedSelection, SessionConflict, SessionStore, SiteSession,
                       SiteStatus, clear_confirmation, clear_current_run,
                       clear_exception_intents, confirmation_covers_bundle_shape,
                       confirmation_covers_fork, needs_acknowledgment,
                       record_activity, release_matches_confirmation,
                       released_teeth_of, split_released_files, summary_teeth_of)

router = APIRouter(prefix="/api/case-sessions", tags=["case-sessions"])


# --- response models: presentation-shaped, no physics -----------------------------------

class SiteRollup(BaseModel):
    total: int
    declared: int   # sites past "detected" — an operator act has touched them
    ready: int
    flagged: int


class WorklistRow(BaseModel):
    """One case's row. Identity fields come from case DISCOVERY and are always present;
    everything below them derives from the SESSION and goes None together, exactly when
    ``error`` is set — THE PER-ROW ERROR CONTRACT (slice 5a, carried from the slice-4
    review): one corrupt session file must not 500 the whole worklist (the 20-scan
    morning's home screen), and a row that cannot state its facts states its trouble
    instead of claiming zeros it never read."""

    id: str
    doctor: str
    jaw: str
    suggested_model: Optional[str]
    # THE SCAN CARD'S REMAINING FACTS (design flow.dc.html SCANS 651-676; gap
    # ``practice-and-batch-on-a-case``, 2026-07-31). ``doctor`` was already the
    # design's "practice" under another name, and ``suggested_model`` its "system";
    # these two are the rest of what its card states. Both are DISCOVERY facts —
    # the teeth the curated sites carry and the scan file's size on disk — so they
    # sit above the error line with identity, present even on a row whose session
    # could not be read (a corrupt session says nothing about the data tree).
    teeth: List[int] = Field(default_factory=list)
    scan_bytes: Optional[int] = None
    sites: Optional[SiteRollup]
    run_state: Optional[str]        # "none" | queued | running | done | refused (AM-3)
    confirmed: Optional[bool]
    # released is the worklist's delivery chip (slice 8): a CURRENT-run verdict,
    # same derivation as the detail's (_released), never the record's bare existence
    released: Optional[bool] = None
    # Intake's completion facts (plan §4 / slice 4), derived server-side like the rest:
    detected: Optional[bool]        # a detection record exists for this session
    # EFFECTIVE values all present (client 2026-07-27): an explicit act, the case's
    # suggestion, or the standing relief default each count — the automation's fact
    choices_complete: Optional[bool]
    # the session store's refusal, verbatim (its one home for those words); None = healthy
    error: Optional[str] = None


class SiteView(BaseModel):
    tooth: int
    status: str
    declared_variant: Optional[str]     # the session's (an operator act), never inferred
    # THE SUGGESTION'S PRECEDENCE (client escalation 2026-08-09): the case's own
    # CURATED value (sites.json) when one exists, else the DETECTION-MEASURED
    # proposal (application.detection.SuggestedSiteCapture.proposed_variant) —
    # never a guess dressed as one; None when neither exists. ``source`` says
    # which, so the UI's chip can render "measured" honestly instead of wearing
    # the curated wording for a fact detection derived on its own.
    suggested_variant: Optional[str]
    suggested_variant_source: Optional[Literal["curated", "measured"]] = None
    center: Optional[List[float]]       # a coordinate FACT from intake, passed through
    # THE RIM BORDER-POINTS INTAKE AID (§10-AL), echoed exactly as recorded — the
    # operator's own measurement, not a worker fact, so this is a pass-through like
    # ``center`` rather than a derivation like ``capture``. None on a site nobody
    # has clicked points on yet, or after a re-mark retired them.
    rim_points: Optional[List[List[float]]] = None
    # the worker's capture assessment (CaptureAssessment.to_dict), once detection ran —
    # the chair-side verdict Intake surfaces BEFORE any work is invested (plan §4)
    capture: Optional[dict] = None
    # THE MAX LEAVE-ONE-OUT PLANE DISTANCE over the operator's own border clicks
    # (auto_flow's ``_border_click_disagreement``, n>=4 — rule 8: a fact the
    # pipeline computes and the UI omits is a bug, and this one already told a
    # Copy-run-report reader "why did this seat tilt" without a surface to show
    # it). Read from the CURRENT run's own row for this tooth
    # (``_run_summary_row``) — a RUN fact, never a client's, and never the
    # ``rim_points`` above's own echo: the run measures disagreement over
    # whatever border clicks the SHIPPED package's site record carried, which may
    # predate this route entirely (the demo's own clicks, curated ``sites.json``
    # rim_points). None before any run exists, or when the row itself has fewer
    # than four border clicks to disagree over.
    border_click_disagreement_mm: Optional[float] = None
    # THE PREVIEW'S SEAT FACTS on the wire (client 2026-07-27 #2: the attestation is
    # faced again "at the time to move forward", so Declare's footer must say what
    # each site's tick actually attested). Persisted by the preview route from what
    # the application derived — worker facts, never a client's — and cleared at every
    # reset boundary with the rung that justified them, so a line in that summary can
    # never describe a preview the case has moved past.
    seat_method: Optional[str] = None
    rim_agreement_mm: Optional[float] = None
    # THE DROP, AS A DRAFT (gap ``drop-a-cap-from-adjust``, 2026-07-31): whether the
    # operator has said this site is to be WITHHELD at confirmation time. A standing
    # INTENT, not an outcome — the confirmation is still what signs it, and every
    # surface that renders this must say what the operator DID, never what the site
    # IS (see ``SiteSession.withhold_intent``).
    withhold_intent: bool = False
    # PER-SITE RELIEF OVERRIDE (§10-B/C): this site's own ask, null when the
    # case-level effective value stands. The raw act — the effective composition
    # is the surface's to render from the two served facts.
    gingival_offset_mm: Optional[float] = None
    # THE OPERATOR'S PERSISTED MEASUREMENTS (§10-AD): how many marks/pairs/best-fits
    # will ride the next run's selection and re-apply after automation. A COUNT, not
    # the payloads — the wire carries what a surface renders, and the surface says
    # "N measurements ride the next run", never the coordinates themselves.
    alignment_evidence_count: int = 0
    # THE ACCEPT-AS-FLAGGED-EXCEPTION DRAFT (client ruling 2026-08-02): whether the
    # operator has pre-acknowledged this site's flagged verdict from Adjust — a
    # standing INTENT that PRE-FILLS Deliver's row-by-row checkbox, never a
    # signature (``ConfirmIn.acknowledged_flags`` stays the only thing that seals;
    # see ``SiteSession.exception_intent``). ``bool`` on the wire; the timestamp
    # itself is an internal fact no surface needs to render.
    exception_acknowledged: bool = False


class DetectedProposalView(BaseModel):
    """A detector proposal: centre + evidence + the NON-BINDING tooth guess + capture."""

    center: List[float]
    void_ratio: float
    rim_below_cusps_mm: float
    tooth_guess: Optional[int]
    capture: dict
    density_prior_used: Optional[bool] = None
    dp_gap_fraction: Optional[float] = None
    bearing_margin: Optional[List[float]] = None


class DetectionView(BaseModel):
    proposals: List[DetectedProposalView]
    # §10-AM built: the scan's own jaw reading (application.detection.jaw_from_crown_axis)
    # -- None before detection runs, or when the crown axis makes no claim (a sideways
    # export). ``effective_jaw`` only carries this value while nothing is chosen; once a
    # chosen jaw contradicts it, the raw reading survives only HERE, which is what lets
    # the UI highlight the geometry's own answer on the jaw buttons (the advisory's
    # one-click fix) even while the effective value disagrees with it.
    jaw_reading: Optional[str] = None
    # THE RAW MEASURED FACTS (client escalation 2026-08-09), keyed by tooth like
    # ``site_capture`` — served for the same reason as ``jaw_reading``: a fact the
    # worker computed must not be a fact the UI has no way to show (rule 8).
    # ``SiteView.suggested_variant``/``suggested_variant_source`` are the composed
    # per-site read the surfaces actually render from; this is the record's own
    # verbatim evidence.
    site_measured_height_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    site_proposed_variant: Dict[str, Optional[str]] = Field(default_factory=dict)
    site_measured_diameter_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    # Stage 1 slice 1a (clinical-pipeline-plan.md): the discriminator evidence
    # behind a proposal -- WHY, not just what -- keyed by tooth like the pair
    # above. These are MEASUREMENTS, not a status/verdict, so serving them
    # server-derived breaks no trust rule (rule 8: disclose what the worker knows).
    site_rim_below_cusps_mm: Dict[str, Optional[float]] = Field(default_factory=dict)
    site_void_ratio: Dict[str, Optional[float]] = Field(default_factory=dict)
    # P4.1 — curve honesty (density prior, DP gap, per-bearing margin). Same
    # tooth-keyed maps as rim/void; measurements, not statuses.
    site_density_prior_used: Dict[str, Optional[bool]] = Field(default_factory=dict)
    site_dp_gap_fraction: Dict[str, Optional[float]] = Field(default_factory=dict)
    site_bearing_margin: Dict[str, Optional[List[float]]] = Field(default_factory=dict)


class EffectiveChoiceView(BaseModel):
    """One case-level choice as the AUTOMATION consumes it (client 2026-07-27) — the
    SystemView pattern mirrored per choice: the operator's explicit act when made,
    the case's non-binding suggestion else (construction from the name-matched
    catalog part, jaw read off the scan filename), the standing default else
    (relief) — and ``source`` says which, so the UI renders its "suggested"/
    "default" chip from a server fact instead of comparing fields itself. ``value``
    is None (source "none") only where no fallback exists: a case whose folder
    matched no construction part."""

    value: Optional[Union[str, float]]
    source: str   # "chosen" | "suggested" | "default" | "none"


class TurnaroundOptionView(BaseModel):
    """One turnaround the rate card prices, with its per-site unit in integer cents.
    Served beside the choices (§10-AB.4) so the Intake chooser prints the CARD's
    money — the same ``bff.pricing`` module the invoice charges from — and the pill
    and the bill can never disagree. Read-only like everything else here."""

    value: str
    unit_amount_cents: int
    currency: str


class ChoicesView(BaseModel):
    """The operator's case-level choices as persisted (None = not yet made), plus the
    facts the UI needs to render them honestly: the worker's default relief ask, the
    EFFECTIVE value+attribution per choice (what preview and run actually consume —
    client 2026-07-27), and the server-derived completion verdict over the EFFECTIVE
    values (the UI never computes completion itself)."""

    construction_path: Optional[str]
    jaw: Optional[str]
    gingival_offset_mm: Optional[float]
    # the turnaround ask (design speedChips 1159-1160): raw act, None until made
    turnaround: Optional[str]
    gingival_offset_default_mm: float
    effective_construction: EffectiveChoiceView
    effective_jaw: EffectiveChoiceView
    effective_relief: EffectiveChoiceView
    # "chosen" | "default" — never "suggested": no case fact suggests a turnaround,
    # and the standing default is the only fallback there is
    effective_turnaround: EffectiveChoiceView
    # the rate card's priced turnarounds (§10-AB.4) — the chooser's whole vocabulary
    turnaround_options: List[TurnaroundOptionView] = Field(default_factory=list)
    # DELIBERATELY unaffected by the turnaround (see ``CaseChoices.turnaround``):
    # the standing default answers it, so a case is never incomplete for want of a
    # commercial choice nobody has to make
    complete: bool
    # §10-AM built: composed server-side, non-null EXACTLY when a scan jaw reading
    # exists AND contradicts the EFFECTIVE jaw (never the raw/declared one — a jaw
    # the operator chose to match the scan must not keep warning about itself). The
    # advisory never blocks: jaw stays the operator's choice, one click away from
    # matching what the scan itself says. Rendered verbatim; the UI composes nothing.
    jaw_advisory: Optional[str] = None


class CaseView(BaseModel):
    id: str
    doctor: str
    jaw: str
    scan_filename: str
    suggested_model: Optional[str]
    suggested_construction: Optional[str]
    # the scan card's discovery facts, same as the worklist row's (2026-07-31)
    teeth: List[int] = Field(default_factory=list)
    scan_bytes: Optional[int] = None


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


class SystemView(BaseModel):
    """WHICH implant system the case is working against (plan §4 Declare / AM-8): the
    session's case-scoped declaration when one exists, else the case's non-binding
    suggestion — and ``source`` says which, so the UI can render its "suggested" tag
    from a server fact instead of comparing fields itself."""

    effective_model: Optional[str]
    source: str   # "declared" | "suggested" | "none"


class ConfirmationView(BaseModel):
    """The sealed state Deliver renders (slice 8): WHEN it was confirmed, over which
    evidence hash — plus the dispositions and per-flag acknowledgments the artifact
    surface needs to show withheld sites honestly. The record's facts verbatim, and
    since the identity removal (client 2026-07-27) the record names no actor: the
    attestation act is the record, and the wire says exactly that much.

    ``terms_accepted``/``terms_version`` are the agreement's new home (plan
    §10-A) — the record's own fields, verbatim, so the surface can say WHICH
    terms text was accepted alongside when and over what evidence.
    ``terms_accepted`` reads False on a confirmation sealed before the concept
    existed (the record's own honest default), never implied true."""

    at: str
    run_id: str
    evidence_sha256: str
    dispositions: Dict[str, str]
    acknowledged_flags: List[int]
    terms_accepted: bool
    terms_version: Optional[str] = None


class PaymentView(BaseModel):
    """The stub's honest face: the UI labels the button AS a stub, and the provider
    field is how a reader tells a stub authorization from a real one.

    THE AMOUNT IS A RECEIPT, NOT A PRICE (2026-07-31): what this authorization
    actually charged, under which rate card and turnaround. It can legitimately
    differ from the case's CURRENT invoice — a turnaround change after payment
    reprices going forward and fires no boundary — so the surface shows both and
    calls them what they are. None on records persisted before pricing existed."""

    provider: str
    at: str
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    rate_card_version: Optional[str] = None
    turnaround: Optional[str] = None


class ReleaseView(BaseModel):
    at: str
    run_id: str
    evidence_sha256: str
    released_teeth: List[int]


class ReleasePreviewView(BaseModel):
    """WHAT A RELEASE WOULD DISCLOSE, said BEFORE the act (client 2026-07-27 #6:
    "Make sure we have good UI for payment and release of information / artifacts" —
    an operator should never learn what left the building by reading the list
    afterwards).

    Derived from the CURRENT confirmation's dispositions through the same
    ``split_released_files`` the artifact gate itself uses (session.py's one home),
    so the promise here and the disclosure there cannot disagree. Counts and the
    operator's own teeth only — no file NAMES, because names are the disclosure this
    is describing, and describing is not disclosing."""

    file_count: int
    teeth: List[int]
    withheld_teeth: List[int]
    withheld_case_file_count: int


class AdjustDecisionView(BaseModel):
    """The Delivery-vs-Skip fork as recorded (client 2026-07-27) — the record
    verbatim, so a surface can SAY what was decided and when, over which run."""

    decision: str
    at: str
    run_id: str


class SessionView(BaseModel):
    tenant_id: str
    adjust_visited: bool
    # the fork's record (client 2026-07-27), None until it is faced — and None again
    # the moment the run boundary clears the verdicts it was decided over
    adjust_decision: Optional[AdjustDecisionView] = None
    run_state: str
    # the refused run's words, VERBATIM (5c) — the one fact the Declare footer needs
    # beside the state; None unless run_state is "refused"
    run_refusal: Optional[str] = None
    confirmed: bool
    payment_authorized: bool
    # the disclosure chain's records (slice 8), verbatim where they exist
    confirmation: Optional[ConfirmationView] = None
    payment: Optional[PaymentView] = None
    release: Optional[ReleaseView] = None
    # what a release WOULD disclose (client 2026-07-27 #6) — present exactly while a
    # confirmation covers the current done run, so the release step can name the
    # consequence before the act rather than after it
    release_preview: Optional[ReleasePreviewView] = None
    # ``released`` is a CURRENT-run verdict, not a record's existence: true only
    # while the release record still names the current done run — the rail's
    # deliver tick reads THIS (a stale release is history, not a state)
    released: bool = False


class RunView(BaseModel):
    """GET /{id}/run — the CURRENT run's persisted facts (plan §7 slice 5c): the
    job-shaped receipt plus what the landing kept — per-site verdict rows and the
    package file list, names relative to the immutable run directory. Worker-shaped
    rows stay untyped like the catalog's (the worker's summary is the schema; the
    key-set is pinned worker-side by test_run.py). Adjust's and Deliver's read
    surface."""

    run_id: str
    job_id: str
    state: str
    refusal: Optional[str] = None
    # the worker's summary verbatim (None while queued/running or refused)
    summary: Optional[dict] = None
    # the per-site rows out of that summary — served flat because they are what
    # Adjust's queue and Deliver's assurance table actually iterate
    sites: List[dict] = Field(default_factory=list)
    package_files: List[str] = Field(default_factory=list)


class CaseSessionDetail(BaseModel):
    case: CaseView
    sites: List[SiteView]
    system: SystemView
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

    # extra="forbid" on EVERY request model (slice 5a, carried from the slice-4 review):
    # pydantic's default silently DROPS unknown fields, so a smuggled {"status": ...}
    # would 200 and the client would believe its claim landed. Refuse it loudly.
    model_config = ConfigDict(extra="forbid")

    construction_path: Optional[str] = None
    jaw: Optional[str] = None
    gingival_offset_mm: Optional[float] = None
    # THE TURNAROUND ASK (design speedChips 1159-1160), admissible on this body for
    # the same reason the fork's "skip" is: it says what the lab ASKED FOR, never
    # what any site IS. A Literal rather than a validated str, so an unknown word is
    # a 422 at the wire and ``bff.pricing`` never has to guess a rate for it.
    turnaround: Optional[Literal["standard", "rush"]] = None

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


class SiteReliefIn(BaseModel):
    """ONE site's relief override (§10-B/C, the Adjustment act): the ask in mm, or
    null to clear the override so the case-level value stands again. Same bounds as
    the case-level ask — the ceiling is judged at cut time per (part × variant),
    exactly as it always was."""

    model_config = ConfigDict(extra="forbid")
    gingival_offset_mm: Optional[float] = None

    @field_validator("gingival_offset_mm")
    @classmethod
    def _sane_offset(cls, v):
        if v is None:
            return v
        if not math.isfinite(v) or v < 0.0 or v > _MAX_GINGIVAL_OFFSET_MM:
            raise ValueError(f"gingival_offset_mm must be a clearance between 0 and "
                             f"{_MAX_GINGIVAL_OFFSET_MM}mm, got {v!r}")
        return float(v)


class SystemIn(BaseModel):
    """The case-scoped implant SYSTEM (plan §4 Declare / AM-8) — one required name.
    Membership is judged in the handler through ``application.catalog.
    require_library_model`` (it needs the data tree; the refusal sentence has one
    home there). The reset a switch causes is a handler DERIVATION through
    bff/status.py — deliberately not expressible in this body."""

    model_config = ConfigDict(extra="forbid")

    model: str


class AdjustDecisionIn(BaseModel):
    """THE FORK'S ONE FIELD (client 2026-07-27: "Delivery vs Skip Adjustments") — the
    act the operator took at Declare's footer, and nothing else.

    An ACT, like choices and dispositions: it says what the operator DID with the
    Adjust stage, never what any site IS. There is deliberately no field for a reason,
    a note or a site list — a decision that could carry a claim about the fits would
    be a status field wearing a different name, and the ladder stays server-derived."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["skip", "adjust"]


class MarkedSiteIn(BaseModel):
    """A cap the DETECTOR MISSED, marked by the operator (client 2026-07-28).

    Two fields, both operator acts in the sense this allowlist means: WHICH tooth and
    WHERE its centre is. Nothing here is a status, a verdict or a gate — the site
    starts at DETECTED like any other and climbs the same ladder, so marking a cap
    buys the operator work to do, never a rung.

    The centre is a world-frame point on the scan the operator clicked. It is NOT
    re-centred, snapped or averaged server-side: the re-click pair-integrity record
    (five attempts, all of which broke calibrated contracts) says a human's mark is
    fixed at the UI or refused, never quietly corrected downstream."""

    model_config = ConfigDict(extra="forbid")

    tooth: int
    center: List[float]


class RemarkedSiteIn(BaseModel):
    """RE-MARKING a site the case ALREADY HAS (client 2026-08-01) — ``MarkedSiteIn``
    minus ``tooth``, because the path already names it (the path names an existing
    subresource; the body carries only what changed about it).

    One field, the same operator act in the allowlist's sense: WHERE the better
    centre is. Not a status, a verdict or a gate — the tooth's declared VARIANT
    (which cap) is untouched; only the physics derived from the old centre falls,
    through the reset boundary this route drives.

    The centre is sent exactly as clicked, never re-centred or averaged server-side
    — the re-click pair-integrity record (five attempts, all of which broke
    calibrated contracts) says a human's mark is fixed at the UI or refused, and a
    RE-mark is a NEW mark replacing the old one WHOLE, never a nudge to it."""

    model_config = ConfigDict(extra="forbid")

    center: List[float]


# a fit needs at least three points to be a circle at all, and the demo's own tool
# capped the click count at twelve (server.py's ``_bounded_rim_points``) — kept here
# as the product route's own ceiling rather than imported, because THIS route's floor
# (3) is a decision the demo never made: the demo also accepted 1-2 points for an
# averaged-radius fallback (server.py's ``_site_capture_inputs``), a mode this route
# does not serve at all — the product tool's one job is the circle fit (§10-AL: "fed
# the rim diameter"), so fewer than three points is refused rather than silently
# falling back to a reading nobody asked for.
_MIN_RIM_POINTS = 3
_MAX_RIM_POINTS = 12


class RimPointsIn(BaseModel):
    """THE RIM BORDER-POINTS INTAKE AID (§10-AL, client: "we lost the tool we had in
    the demo where we made points around the border of the healing cap in the
    scan"). ``RemarkedSiteIn``'s conventions, one field wider: several clicks around
    a cap's visible rim, world-frame, sent exactly as clicked — the re-click
    pair-integrity rule applies here exactly as it does to a mark: points are fixed
    at the UI or refused, never averaged, snapped or reordered server-side.

    Bounded at 3..12 points (see ``_MIN_RIM_POINTS``/``_MAX_RIM_POINTS`` just
    above): fewer than three cannot fit a circle, so a refusal here is honest rather
    than a silent 1-2-point degrade the product route does not implement. Each
    point is an [x, y, z] triple like every other mark in this module."""

    model_config = ConfigDict(extra="forbid")

    points: List[List[float]]

    @field_validator("points")
    @classmethod
    def _bounded_and_shaped(cls, v):
        if not _MIN_RIM_POINTS <= len(v) <= _MAX_RIM_POINTS:
            raise ValueError(
                f"rim_points needs between {_MIN_RIM_POINTS} and {_MAX_RIM_POINTS} "
                f"points to fit a rim circle honestly, got {len(v)}")
        for p in v:
            if len(p) != 3 or not all(math.isfinite(c) for c in p):
                raise ValueError("every rim point must be a finite [x, y, z] triple "
                                 "in the scan's own frame")
        return [[float(c) for c in p] for p in v]


class WithholdIntentIn(BaseModel):
    """DROP THIS CAP / BRING IT BACK (design flow.dc.html dropSite 1345-1354) — one
    boolean, both directions, and nothing else.

    An ACT in this allowlist's sense, and the same one ``ConfirmIn.dispositions``
    already carries: it says what the operator DOES with a site (hold it back from
    the release and the bill), never what the site IS. There is deliberately no
    reason field and no note — a drop that could carry a claim about the fit would
    be a status field wearing a different name, and the ladder stays server-derived.

    The design's own label reads "don't align or bill it". Only the second half is
    true here, and the wording downstream says so: the run still aligns the site.
    Skipping the physics would make the decision irreversible without a re-run,
    which is the opposite of what a reversible draft is for."""

    model_config = ConfigDict(extra="forbid")

    withhold: bool


class DeclarationIn(BaseModel):
    """The per-site variant declaration (plan §4 Declare / AM-8) — one required
    catalog entry id. Membership against the EFFECTIVE system's library is judged in
    the handler (``require_variant``); the detected→declared move it causes is the
    status machine's, never a field here."""

    model_config = ConfigDict(extra="forbid")

    variant: str


# --- derivations ------------------------------------------------------------------------

def _suggested_variant(tooth: int, curated: Optional[str],
                       detection: Optional[DetectionRecord]
                       ) -> Tuple[Optional[str], Optional[str]]:
    """(suggested_variant, suggested_variant_source): the CURATED value (sites.json)
    when present, else the DETECTION-MEASURED proposal (client escalation
    2026-08-09) — a suggestion strong enough to prefill a declaration must say
    where it came from, so the chip can render "measured" honestly instead of
    borrowing the curated wording for a fact the scan derived on its own."""
    if curated is not None:
        return curated, "curated"
    measured = (detection.site_proposed_variant.get(str(tooth))
               if detection is not None else None)
    return (measured, "measured") if measured is not None else (None, None)


def _border_click_disagreement_view(run: Optional[RunSession],
                                    tooth: int) -> Optional[float]:
    """One tooth's ``border_click_disagreement_mm`` off the CURRENT run's own row
    (rule 8 — a fact the pipeline computes and the UI omits is a bug, and this one
    already had a home in the summary; only the surface was missing). Shares
    ``_run_summary_row`` with ``post_acknowledge_exception`` rather than a second
    tooth->row scan — one derivation of "this tooth's current-run row", not two
    that could disagree about which row that is. None before any run, or when the
    row itself never computed the number (fewer than four border clicks, or no
    border clicks at all — the row's own honest gap, passed through)."""
    if run is None:
        return None
    row = _run_summary_row(run, tooth)
    return row.get("border_click_disagreement_mm") if row is not None else None


def _site_views(case: CaseRecord, session: CaseSession) -> List[SiteView]:
    """Worker-suggested sites overlaid with session state; session-only sites (a later
    slice can add one at Declare) still render. Capture verdicts join from the session's
    detection record — worker facts, persisted by the detect route, never a client's."""
    capture: Dict[str, dict] = (
        session.detection.site_capture if session.detection is not None else {})
    run = session.run
    views = {}
    for s in case.suggested_sites:
        tooth = int(s["tooth"])
        sess = session.sites.get(str(tooth))
        suggested, suggested_source = _suggested_variant(
            tooth, s.get("declared_variant"), session.detection)
        views[tooth] = SiteView(
            tooth=tooth,
            status=(sess.status.value if sess else SiteStatus.DETECTED.value),
            declared_variant=(sess.declared_variant if sess else None),
            suggested_variant=suggested,
            suggested_variant_source=suggested_source,
            # the operator's mark WINS over the case's suggestion, the same precedence
            # the run itself applies (application.run) — one rule, stated in both
            # places rather than the surface and the run disagreeing about the centre
            center=((sess.marked_center if sess and sess.marked_center is not None
                     else s.get("center"))),
            rim_points=(sess.rim_points if sess else None),
            capture=capture.get(str(tooth)),
            seat_method=(sess.seat_method if sess else None),
            rim_agreement_mm=(sess.rim_agreement_mm if sess else None),
            border_click_disagreement_mm=_border_click_disagreement_view(run, tooth),
            withhold_intent=(sess.withhold_intent if sess else False),
            alignment_evidence_count=(len(sess.alignment_evidence)
                                      if sess else 0),
            gingival_offset_mm=(sess.gingival_offset_mm if sess else None),
            exception_acknowledged=(sess.exception_intent is not None
                                    if sess else False),
        )
    for key, sess in session.sites.items():
        tooth = int(key)
        if tooth not in views:
            views[tooth] = SiteView(tooth=tooth, status=sess.status.value,
                                    declared_variant=sess.declared_variant,
                                    suggested_variant=None,
                                    # a session-only site now HAS a centre when a
                                    # human marked one — that is the whole point of
                                    # marking, and reporting None here would have the
                                    # surface deny what the run is about to use
                                    center=sess.marked_center,
                                    rim_points=sess.rim_points,
                                    capture=capture.get(key),
                                    seat_method=sess.seat_method,
                                    rim_agreement_mm=sess.rim_agreement_mm,
                                    border_click_disagreement_mm=(
                                        _border_click_disagreement_view(run, tooth)),
                                    withhold_intent=sess.withhold_intent,
                                    alignment_evidence_count=len(
                                        sess.alignment_evidence),
                                    gingival_offset_mm=sess.gingival_offset_mm,
                                    exception_acknowledged=(
                                        sess.exception_intent is not None))
    return [views[t] for t in sorted(views)]


def _curated_teeth(case: CaseRecord) -> List[int]:
    """The teeth DISCOVERY knows about, sorted (gap ``practice-and-batch-on-a-case``,
    2026-07-31). The case record's curated sites only — not the session's, because
    this is the worklist's identity half: it must answer even for a row whose session
    could not be read, and an operator-marked cap is a session fact that belongs to
    the rollup beside it, not to the scan's own description."""
    return sorted({int(s["tooth"]) for s in case.suggested_sites})


def _scan_bytes(case: CaseRecord) -> Optional[int]:
    """The scan file's size on disk — the design's "42.1 MB" on its scan card. A
    single ``stat`` per row: discovery already walked these directories, and no mesh
    is parsed (the 20-scan morning's worklist stays instant, cases.py's own rule).
    None when the file has gone since discovery listed it — the row still stands, it
    just does not claim a size it could not read."""
    try:
        return case.scan.stat().st_size
    except OSError:
        return None


def _rollup(sites: List[SiteView]) -> SiteRollup:
    return SiteRollup(
        total=len(sites),
        declared=sum(1 for s in sites if s.status != SiteStatus.DETECTED.value),
        ready=sum(1 for s in sites if s.status == SiteStatus.READY.value),
        flagged=sum(1 for s in sites if s.status == SiteStatus.FLAGGED.value),
    )


def _run_state(session: CaseSession) -> str:
    return session.run.state if session.run is not None else "none"


def _released(session: CaseSession) -> bool:
    """Released is a CURRENT-run, CURRENT-confirmation, CURRENT-fork fact: the
    record must name the run that is still current and done, still cover the
    current confirmation (``release_matches_confirmation`` — a re-confirm that
    changes a disposition retires the release, because dispositions are acts
    outside the evidence hash), and stand on the fork the confirmation sealed
    (``confirmation_covers_fork``).

    THE FORK JOINED THIS TEST because Declare stays reachable after a release and
    its two buttons are one click away: clicking "Adjust the fits" over a shipped
    case changed the evidence, the artifact endpoints refused on the re-derived
    hash — and this display half went on reporting "Released ✓" beside the refusal,
    since the release and confirmation records still agreed with each other. Two
    ways to retire a release, only one of them visible, is the divergence.

    THE BUNDLE'S SHAPE JOINED IT for the same reason and at the same price (audit
    finding 4, 2026-07-31). A shape move restages every bundle on disk, and unlike
    the fork it needs no operator act at all — a deploy is enough. Every clause
    below still held over a store of cases released under the previous shape, so
    the rail's tick stayed lit while every artifact read 409'd: the exact divergence
    this docstring says was already paid for once, arriving a second time through a
    door the fork's clause does not cover.

    The artifact endpoints still re-verify the evidence BYTES; this stays the cheap
    half — every clause here is a session fact, no disk read — and the rail's
    deliver tick reads it."""
    return (session.release is not None
            and session.run is not None
            and session.run.state == "done"
            and session.release.run_id == (session.run.run_id or session.run.job_id)
            and release_matches_confirmation(session)
            and confirmation_covers_fork(session)
            and confirmation_covers_bundle_shape(session))


def _release_preview(session: CaseSession) -> Optional[ReleasePreviewView]:
    """What releasing WOULD disclose, from the confirmation that is standing now
    (client 2026-07-27 #6). Present only while a confirmation covers the current
    DONE run — before that there is no fixed answer, and inventing one would be a
    promise about a case that has not been confirmed. The split is
    ``session.split_released_files``: the artifact gate's own rule, so this
    description and that disclosure are one derivation.

    THE INVOICE COUNTS TOO, under the exact condition ``deliver.list_artifacts``
    appends it (client 2026-08-09: "plus the invoice") — ``session.
    payment_authorized``. Not imported from ``deliver`` (that module imports THIS
    one; a cycle), so the condition is restated rather than shared code — but it
    is the same boolean read off the same session field, never a second guess at
    when the row appears. Skipping it here is exactly the divergence this
    function's own docstring exists to prevent: ``TestTheReleasePreview`` pins
    that the promise and the disclosure never disagree on a count."""
    run, confirmation = session.run, session.confirmation
    if (run is None or run.state != "done" or confirmation is None
            or confirmation.run_id != (run.run_id or run.job_id)):
        return None
    teeth = summary_teeth_of(run)
    released = released_teeth_of(confirmation.dispositions)
    files, held_case_files = split_released_files(
        run.package_files, teeth, released, session.case_id)
    invoice_files = 1 if session.payment_authorized else 0
    return ReleasePreviewView(
        file_count=len(files) + invoice_files,
        teeth=released,
        withheld_teeth=sorted(set(teeth) - set(released)),
        withheld_case_file_count=len(held_case_files),
    )


def _session_view(session: CaseSession) -> SessionView:
    return SessionView(
        tenant_id=session.tenant_id,
        adjust_visited=session.adjust_visited,
        adjust_decision=(AdjustDecisionView(**session.adjust_decision.model_dump())
                         if session.adjust_decision is not None else None),
        run_state=_run_state(session),
        run_refusal=(session.run.refusal if session.run is not None else None),
        confirmed=session.confirmation is not None,
        payment_authorized=session.payment_authorized,
        # the record's sealed ``adjustments`` is dropped DELIBERATELY, not by a
        # model's leniency: the ASSURANCE is where the operator reads the fork, and
        # a second copy on the session would invite comparing a sealed word against
        # a current one and calling the difference a decision
        # ``bundle_version`` is dropped beside ``adjustments`` and for a related
        # reason: it is an INTERNAL encoding fact, not something an operator acts on
        # — its only job is to let ``released`` above retire cheaply. Putting it on
        # the wire would invite a surface to compare shape strings and invent a
        # verdict the server already derived.
        confirmation=(ConfirmationView(**session.confirmation.model_dump(
            exclude={"adjustments", "bundle_version"}))
            if session.confirmation is not None else None),
        payment=(PaymentView(provider=session.payment.provider,
                             at=session.payment.at,
                             amount_cents=session.payment.amount_cents,
                             currency=session.payment.currency,
                             rate_card_version=session.payment.rate_card_version,
                             turnaround=session.payment.turnaround)
                 if session.payment is not None else None),
        release=(ReleaseView(**session.release.model_dump())
                 if session.release is not None else None),
        release_preview=_release_preview(session),
        released=_released(session),
    )


def _effective_model(case: CaseRecord, session: CaseSession) -> Optional[str]:
    """The system the case works against: the operator's case-scoped declaration
    first, the case's non-binding suggestion else (plan §4 Declare / AM-8)."""
    return session.system or case.suggested_model


# THE STANDING RELIEF DEFAULT (client 2026-07-27): the demo ran every case at the
# worker's own 0.20mm ask unless the lab changed it, so the automation treats the
# unmade relief choice as that standing default rather than refusing. One home for
# the number — the worker's DEFAULT_GINGIVAL_OFFSET_MM — re-exported under the name
# the effective-choices derivation reads.
STANDING_RELIEF_DEFAULT_MM = DEFAULT_GINGIVAL_OFFSET_MM

# THE STANDING TURNAROUND (2026-07-31): a case nobody expedited is a standard case.
# The default lives HERE rather than in ``bff.pricing`` because it is a flow fact —
# what the lab is understood to have asked for — while the rate card is what that
# ask costs; two homes for one word would let a repriced card silently redefine the
# unmade choice.
STANDING_TURNAROUND = "standard"


@dataclasses.dataclass(frozen=True)
class EffectiveChoices:
    """The three case-level choices as the automation consumes them, each with its
    attribution — the internal shape behind ``EffectiveChoiceView`` and the ONE
    document preview/run authorization read. The choices route's reset guard
    compares ``values`` (the withModel pattern — attribution flips are not
    changes); ``complete`` is the worklist/flow completion fact."""

    construction_path: Optional[str]
    construction_source: str
    jaw: Optional[str]
    jaw_source: str
    gingival_offset_mm: Optional[float]
    gingival_offset_source: str
    # the commercial ask, carried here so pricing reads ONE effective document —
    # see ``values`` and ``complete`` below for why it joins neither
    turnaround: str
    turnaround_source: str

    @property
    def complete(self) -> bool:
        """Effective values all present — the completion fact worklist/flow serve
        since the 2026-07-27 automation ask (raw acts alone no longer gate).

        TURNAROUND IS NOT HERE, deliberately: the standing default always answers
        it, so it could only ever be "present", and a field that cannot fail a
        completeness test does not belong in one."""
        return (self.construction_path is not None and self.jaw is not None
                and self.gingival_offset_mm is not None)

    @property
    def values(self) -> tuple:
        """The VALUE triple alone, without attribution — what the choices route's
        reset guard compares: pinning a suggestion flips source suggested→chosen
        while describing the SAME shipped part, and a source flip must never cost
        a preview.

        TURNAROUND IS NOT HERE EITHER, and this is the load-bearing half (gap
        ``turnaround-as-a-case-choice``, 2026-07-31). These three "all describe the
        same shipped part" — that sentence is why a change to any of them retires
        every preview and the current run. A turnaround is a promise about WHEN,
        touching no geometry: upgrading a case to rush must not drop the operator's
        reviews or the run they authorized. Adding it to this tuple would fabricate
        an invalidation, which is the same class of untruth as claiming one."""
        return (self.construction_path, self.jaw, self.gingival_offset_mm)


def _effective_choices(case: CaseRecord, choices: CaseChoices,
                       detection: Optional[DetectionRecord] = None) -> EffectiveChoices:
    """The ``_effective_model`` pattern, mirrored onto the case-level choices
    (client 2026-07-27: 'once implant system and variant for tooth are selected
    the union needs to show up' — the case already carries the suggestions):
    chosen ?? suggested (construction, jaw) ?? standing default (relief). A pure
    READ-time derivation: nothing here ever writes the session, so the raw choices
    stay honestly None until the operator acts and the reset boundaries only fire
    on an explicit CHANGE, never off a default.

    JAW precedence (§10-AM built): chosen beats the SCAN's own reading beats the
    filename suggestion. The scan reading outranks the filename because it is
    measured off the geometry the run actually seats against, while the filename
    is a substring guess that silently defaulted on the very case that started
    this (the arch upload, jaw=upper from no "lower" in its name, geometry lower).
    Detection is optional (a case not yet detected has no reading yet) — the
    filename suggestion is always the honest fallback, never upgraded to a claim
    it cannot support."""
    if choices.construction_path is not None:
        construction = (choices.construction_path, "chosen")
    elif case.suggested_construction is not None:
        construction = (case.suggested_construction, "suggested")
    else:
        construction = (None, "none")
    if choices.jaw is not None:
        jaw = (choices.jaw, "chosen")
    elif detection is not None and detection.jaw_reading is not None:
        jaw = (detection.jaw_reading, "scan")   # measured off the crowns' own axis
    elif case.jaw:
        jaw = (case.jaw, "suggested")   # read off the scan filename by discovery
    else:
        jaw = (None, "none")
    if choices.gingival_offset_mm is not None:
        relief = (choices.gingival_offset_mm, "chosen")
    else:
        relief = (STANDING_RELIEF_DEFAULT_MM, "default")
    if choices.turnaround is not None:
        turnaround = (choices.turnaround, "chosen")
    else:
        turnaround = (STANDING_TURNAROUND, "default")
    return EffectiveChoices(
        construction_path=construction[0], construction_source=construction[1],
        jaw=jaw[0], jaw_source=jaw[1],
        gingival_offset_mm=relief[0], gingival_offset_source=relief[1],
        turnaround=turnaround[0], turnaround_source=turnaround[1],
    )


def _system_view(case: CaseRecord, session: CaseSession) -> SystemView:
    if session.system is not None:
        return SystemView(effective_model=session.system, source="declared")
    if case.suggested_model is not None:
        return SystemView(effective_model=case.suggested_model, source="suggested")
    return SystemView(effective_model=None, source="none")


def _ceilings(case: CaseRecord, session: CaseSession, sites: List[SiteView],
              settings: Settings) -> List[ReliefCeilingView]:
    """One ceiling per DECLARED variant (session first, curated suggestion else), read
    against the CHOSEN construction part the moment one is chosen (plan §4: the relief
    input lives beside its ceiling at Intake, so the ceiling must follow the operator's
    pick, not the name-matched suggestion) and the EFFECTIVE system (the case-scoped
    declaration since slice 5a, the suggestion else). Without a system+construction
    there is nothing meaningful to measure — the list is honestly empty, never
    guessed."""
    construction = _effective_choices(case, session.choices, session.detection).construction_path
    model = _effective_model(case, session)
    if model is None or construction is None:
        return []
    variants = sorted({v for v in
                       (s.declared_variant or s.suggested_variant for s in sites)
                       if v is not None})
    out = []
    for variant in variants:
        try:
            out.append(ReliefCeilingView(**relief_ceiling(
                settings.data_root, construction, model, variant)))
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
            density_prior_used=getattr(p, "density_prior_used", None),
            dp_gap_fraction=getattr(p, "dp_gap_fraction", None),
            bearing_margin=([float(x) for x in p.bearing_margin]
                            if getattr(p, "bearing_margin", None) is not None
                            else None),
        ) for p in result.proposals],
        site_capture={str(s.tooth): s.capture for s in result.suggested},
        jaw_reading=result.jaw_reading,
        # the client escalation's raw evidence (2026-08-09): the honest height
        # reading + the variant it independently suggests, keyed like site_capture
        site_measured_height_mm={str(s.tooth): s.measured_cap_height_mm
                                 for s in result.suggested},
        site_proposed_variant={str(s.tooth): s.proposed_variant
                               for s in result.suggested},
        site_measured_diameter_mm={
            str(s.tooth): getattr(s, "measured_rim_diameter_mm", None)
            for s in result.suggested},
        # 1a: WHY a site was proposed -- the density stack's own evidence,
        # borrowed from the matching proposal (application.detection.
        # candidate_evidence_for), honestly None for a site it never proposed
        site_rim_below_cusps_mm={
            str(s.tooth): getattr(s, "rim_below_cusps_mm", None)
            for s in result.suggested},
        site_void_ratio={
            str(s.tooth): getattr(s, "void_ratio", None)
            for s in result.suggested},
        site_density_prior_used={
            str(s.tooth): getattr(s, "density_prior_used", None)
            for s in result.suggested},
        site_dp_gap_fraction={
            str(s.tooth): getattr(s, "dp_gap_fraction", None)
            for s in result.suggested},
        site_bearing_margin={
            str(s.tooth): ([float(x) for x in s.bearing_margin]
                           if getattr(s, "bearing_margin", None) is not None
                           else None)
            for s in result.suggested},
    )


def _detection_view(session: CaseSession) -> Optional[DetectionView]:
    if session.detection is None:
        return None
    return DetectionView(
        proposals=[DetectedProposalView(**p.model_dump())
                  for p in session.detection.proposals],
        jaw_reading=session.detection.jaw_reading,
        site_measured_height_mm=session.detection.site_measured_height_mm,
        site_proposed_variant=session.detection.site_proposed_variant,
        site_measured_diameter_mm=session.detection.site_measured_diameter_mm,
        site_rim_below_cusps_mm=session.detection.site_rim_below_cusps_mm,
        site_void_ratio=session.detection.site_void_ratio,
        site_density_prior_used=session.detection.site_density_prior_used,
        site_dp_gap_fraction=session.detection.site_dp_gap_fraction,
        site_bearing_margin=session.detection.site_bearing_margin,
    )


def _jaw_advisory(detection: Optional[DetectionRecord],
                  effective_jaw: Optional[str]) -> Optional[str]:
    """The composed advisory sentence (§10-AM built), non-null EXACTLY when a scan
    reading exists and disagrees with the EFFECTIVE jaw. Composed here, not the UI:
    every fact in the sentence (the reading, the crown direction it stands on, the
    case's own jaw) is a server derivation, and a client composing it from parts
    could drift from what was actually measured. Checked against the effective jaw,
    not the raw declared one, so an operator who already fixed the choice — chosen
    now matching the scan — stops seeing a warning about a disagreement that no
    longer exists."""
    reading = detection.jaw_reading if detection is not None else None
    if reading is None or effective_jaw is None or reading == effective_jaw:
        return None
    direction = "up" if reading == "lower" else "down"
    return (f"This scan reads as a {reading} jaw — the crowns point {direction} "
            f"along the scan's own axis — but the case says {effective_jaw}. Check "
            f"the jaw choice; the package and its labels are named by it.")


def _choices_view(case: CaseRecord, session: CaseSession) -> ChoicesView:
    effective = _effective_choices(case, session.choices, session.detection)
    return ChoicesView(
        construction_path=session.choices.construction_path,
        jaw=session.choices.jaw,
        gingival_offset_mm=session.choices.gingival_offset_mm,
        turnaround=session.choices.turnaround,
        gingival_offset_default_mm=DEFAULT_GINGIVAL_OFFSET_MM,
        effective_construction=EffectiveChoiceView(
            value=effective.construction_path, source=effective.construction_source),
        effective_jaw=EffectiveChoiceView(
            value=effective.jaw, source=effective.jaw_source),
        effective_relief=EffectiveChoiceView(
            value=effective.gingival_offset_mm,
            source=effective.gingival_offset_source),
        effective_turnaround=EffectiveChoiceView(
            value=effective.turnaround, source=effective.turnaround_source),
        turnaround_options=[
            TurnaroundOptionView(value=word,
                                 unit_amount_cents=unit_amount_cents(word),
                                 currency=CURRENCY)
            for word in TURNAROUNDS
        ],
        complete=effective.complete,
        jaw_advisory=_jaw_advisory(session.detection, effective.jaw),
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
            teeth=_curated_teeth(case), scan_bytes=_scan_bytes(case),
        ),
        sites=sites,
        system=_system_view(case, session),
        catalog=CatalogView(
            groups=library_groups(settings.data_root),
            constructions=construction_parts(settings.data_root),
        ),
        relief_ceilings=_ceilings(case, session, sites, settings),
        detection=_detection_view(session),
        choices=_choices_view(case, session),
        session=_session_view(session),
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


def _require_known_tooth(case: CaseRecord, session: CaseSession, tooth: int) -> None:
    """The path names a per-site subresource: the tooth must be a site the case
    actually has (a curated suggestion or a session site) — 404 otherwise, the same
    sentence for every per-site action. Judged against the SESSION given, so a caller
    judging inside a mutation judges the fresh document."""
    known = ({int(s["tooth"]) for s in case.suggested_sites}
             | {int(k) for k in session.sites})
    if tooth not in known:
        raise HTTPException(404, f"tooth {tooth} is not a site on case {case.id!r}")


def _mutate_session(store: SessionStore, case_id: str,
                    mutate: Callable[[CaseSession], None]) -> CaseSession:
    """Every mutating route's one write path: fresh-load → mutate → CAS save, retrying
    ONCE on a fresh document before refusing 409 (slice 5a). One retry, deliberately:
    a single interleaved writer is the expected case (a slow detect finishing while a
    quick declaration lands) and re-applying the mutation to the fresh document loses
    neither act; losing TWICE means the case is genuinely contended, and the honest
    move is to tell the operator what happened rather than keep fighting a race on
    their behalf. The 409 carries the store's own words — what changed underneath.

    ``mutate`` may refuse (raise): a refusal on ANY attempt propagates before the
    save, so validation whose verdict depends on session state belongs INSIDE it —
    the retry then re-judges against the fresh document instead of re-applying a
    stale verdict (the declaration route's rule; the 5a dangling-variant race)."""
    last: Optional[SessionConflict] = None
    for _ in range(2):
        session = store.load(case_id)
        mutate(session)
        try:
            store.save(session)
            return session
        except SessionConflict as exc:
            last = exc
    assert last is not None  # the loop only exits here after two conflicts
    raise HTTPException(409, f"{last} — twice in a row; re-read the case and repeat "
                             f"the action on what is actually there now")


@router.get("", response_model=List[WorklistRow])
def worklist(request: Request) -> List[WorklistRow]:
    settings, store = _context(request)
    rows = []
    for case in discover_cases(settings.data_root):
        try:
            session = store.load(case.id)
        except ValueError as exc:
            # THE PER-ROW ERROR CONTRACT (slice 5a): the store's refusal becomes THIS
            # row's fact; the list stays up for every other case. Only the LIST absorbs
            # it — the case detail still refuses loudly, because opening the corrupt
            # case is where the trouble must be faced, not papered over.
            rows.append(WorklistRow(
                id=case.id, doctor=case.doctor, jaw=case.jaw,
                suggested_model=case.suggested_model,
                teeth=_curated_teeth(case), scan_bytes=_scan_bytes(case),
                sites=None, run_state=None, confirmed=None,
                detected=None, choices_complete=None, error=str(exc),
            ))
            continue
        sites = _site_views(case, session)
        rows.append(WorklistRow(
            id=case.id, doctor=case.doctor, jaw=case.jaw,
            suggested_model=case.suggested_model,
            teeth=_curated_teeth(case), scan_bytes=_scan_bytes(case),
            sites=_rollup(sites),
            run_state=_run_state(session),
            confirmed=session.confirmation is not None,
            released=_released(session),
            detected=session.detection is not None,
            choices_complete=_effective_choices(case, session.choices, session.detection).complete,
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
        # the choices panel stays live — a choices PUT can land mid-derivation (the
        # slice-4 lost update). The derivation runs ONCE, above; only the WRITE goes
        # through the CAS path, re-applying the same facts to a fresh document on a
        # conflict. Retry-or-409 posture: a retry never re-runs detect(), and a 409
        # here means two rivals landed during the seconds-long derivation — rare
        # enough that telling the operator beats a third blind write.
        record = _detection_record(result)

        def apply(fresh_session: CaseSession) -> None:
            fresh_session.detection = record
            record_activity(fresh_session, ACT_DETECTED,
                            f"detection found {len(record.proposals)} cap proposal"
                            f"{'' if len(record.proposals) == 1 else 's'}")

        session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


def _site_reliefs_of(session: CaseSession) -> Dict[str, float]:
    """The standing per-site overrides, wire-shaped (§10-B/C)."""
    return {t: float(site.gingival_offset_mm)
            for t, site in session.sites.items()
            if site.gingival_offset_mm is not None}


def _drive_reemit_job(worker: WorkerPort, store: SessionStore, settings: Settings,
                      case: CaseRecord, case_id: str, reemit_run_id: str,
                      reemit_request: dict) -> CaseSession:
    """Submit and land a §10-AC re-emit whose queued receipt is already on disk —
    run_case_action's containment, shared by every boundary that re-emits (the
    choices PUT and the per-site relief PUT). Every exit that lands no verdict
    withdraws the receipt."""
    try:
        job_id = worker.submit(case_id, reemit_request)
        outcome = worker.status(job_id)
        if outcome.state is JobState.FAILED:
            raise HTTPException(
                500, f"the re-emit crashed before reaching a verdict — "
                     f"{outcome.error}; the queued receipt was withdrawn, and "
                     f"the choices stand — re-firing is a fresh part change "
                     f"or a run authorization")

        def land(inner: CaseSession) -> None:
            if inner.run is None or inner.run.job_id != job_id:
                raise HTTPException(
                    409, f"case {case_id!r} changed while the re-emit was "
                         f"computing — its artifacts remain under its run "
                         f"directory as history; re-read the case")
            if outcome.state is JobState.REFUSED:
                # the §10-M flow point that never had a refusal surface: the
                # design/relief gate's words land as a REFUSED run, first-class
                inner.run = RunSession(job_id=job_id, run_id=reemit_run_id,
                                       state="refused",
                                       refusal=outcome.refusal)
                record_activity(inner, ACT_RUN_REFUSED,
                                f"re-emit {reemit_run_id} refused — "
                                f"{outcome.refusal}")
                return
            summary = worker.result(job_id)
            inner.run = RunSession(
                job_id=job_id, run_id=reemit_run_id, state="done",
                summary=summary,
                package_files=[str(n)
                               for n in (summary.get("package_files") or [])])
            # guidance rides the rows VERBATIM from the source run, so the
            # flags land where they already stood — the mapping only moves a
            # site that is not already flagged (rungs survived the boundary)
            for row in summary.get("sites") or []:
                site = inner.sites.get(str(row.get("tooth")))
                if site is None:
                    continue
                level = (row.get("guidance") or {}).get("level")
                if level != "ready" and site.status is not SiteStatus.FLAGGED:
                    site.status = status.flag(site.status)
            record_activity(inner, ACT_RUN_LANDED,
                            f"re-emit {reemit_run_id} completed — the package "
                            f"stands on run "
                            f"{reemit_request['source_run_id']}'s poses")

        try:
            return _mutate_session(store, case_id, land)
        except status.IllegalTransition as exc:
            raise HTTPException(422, str(exc))
    except Exception:
        _withdraw_queued_receipt(store, case_id, reemit_run_id)
        raise


@router.put("/{case_id}/choices", response_model=CaseSessionDetail)
def put_choices(case_id: str, body: ChoicesIn, request: Request) -> CaseSessionDetail:
    """Persist the operator's case-level choices — the whole document, replaced (PUT
    semantics: what you send is what is chosen; omitting a field un-chooses it, so the
    UI always submits its full current panel). Construction membership is checked here
    against the catalog (never a path join); jaw and relief were already refused by the
    request model in the demo's own words.

    THE REVIEW-RESET RULE, LANDED (5b; the demo's rule #1, librarySelection.ts:10-16):
    a review is about a SPECIFIC part, and construction, jaw and relief "all describe
    the same shipped part" — so a CHANGE to any of them clears every site's
    later-ladder facts (the preview's seat facts, the review's READY) through the
    machine's ``invalidate_preview`` — the third reset trigger, beside the declaration
    (per-site) and the system switch (case-wide). Declared VARIANTS survive a choices
    change, exactly as in the demo (its transitions touch ``reviewed`` only), and an
    IDENTICAL re-PUT resets nothing (the demo's own equality guards,
    ``withConstruction``/``withJaw``/``withOffsetInput``) — both pinned by test.

    Since the effective choices landed (client 2026-07-27), "change" is judged over
    the EFFECTIVE document — the system route's ``withModel`` guard, mirrored: a PUT
    that pins exactly the values already in effect (the suggestion, the standing
    default) describes the SAME shipped part, so the previews the automation already
    computed with those values survive the pinning act.

    THE TURNAROUND RIDES ALONG AND RESETS NOTHING (2026-07-31). It is persisted by
    the same PUT because it is a case-level operator choice like the others, but the
    reset guard compares ``EffectiveChoices.values``, which excludes it: the reset
    rule's own justification is that construction, jaw and relief "all describe the
    same shipped part", and a promise about WHEN touches no geometry. Upgrading a
    case to rush therefore costs no review, no preview and no run — pinned by test.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    worker: WorkerPort = request.app.state.worker
    reemit_run_id = _mint_run_id()
    reemit: Dict[str, dict] = {}
    if body.construction_path is not None:
        try:
            require_construction(settings.data_root, body.construction_path)
        except UnknownSelection as exc:
            raise HTTPException(422, str(exc))

    # Retry-or-409 posture: replacing the choices document is idempotent over a fresh
    # load (the operator's whole panel is the payload), and the reset re-derives from
    # each fresh document, so one retry is safe and loses no rival's fact; a second
    # conflict surfaces as the 409.
    def apply(session: CaseSession) -> None:
        replacement = CaseChoices(
            construction_path=body.construction_path,
            jaw=body.jaw,
            gingival_offset_mm=body.gingival_offset_mm,
            turnaround=body.turnaround,
        )
        eff_new = _effective_choices(case, replacement, session.detection)
        eff_old = _effective_choices(case, session.choices, session.detection)
        effective_changed = eff_new.values != eff_old.values
        # THE RE-EMIT BOUNDARY (§10-AC, retiring §10-M's deadlock): a change that
        # touches ONLY the construction part and/or the relief, over a DONE run,
        # owes a RE-EMIT — the pose is construction-independent (measured), so the
        # fits the operator reviewed stand, and the package re-emits from the
        # run's own poses into a NEW run directory in seconds. Rungs survive: the
        # pose the review attested is untouched. A jaw change (or a system switch,
        # which has its own route) keeps the full retirement below.
        part_or_relief_only = (
            effective_changed and eff_new.jaw == eff_old.jaw)
        run_done = (session.run is not None and session.run.state == "done"
                    and (session.run.run_id or session.run.job_id) is not None)
        if effective_changed and part_or_relief_only and run_done:
            source_run_id = session.run.run_id or session.run.job_id
            session.run = RunSession(job_id=reemit_run_id, run_id=reemit_run_id,
                                     state="queued")
            # a NEW run's fork has not been faced, and every drafted
            # acknowledgment was given over the OLD run's rows (the claim path's
            # own rules, §10-AC) — and the confirmation falls EXPLICITLY: the QC
            # evidence is cap+pose and would verify unchanged while
            # prosthesis_cad.stl changed underneath (hazard 4)
            session.adjust_decision = None
            clear_exception_intents(session)
            clear_confirmation(session)
            reemit["request"] = {
                "run_id": reemit_run_id,
                "mode": "reemit",
                "source_run_id": source_run_id,
                "selection": {
                    "model": _effective_model(case, session),
                    "construction_path": eff_new.construction_path,
                    "jaw": eff_new.jaw,
                    "gingival_offset_mm": eff_new.gingival_offset_mm,
                    # identity rides the source records; the variants map is the
                    # gate's shape, from the declarations that produced the run
                    "variants": {t: site.declared_variant
                                 for t, site in session.sites.items()
                                 if site.declared_variant is not None},
                    "site_reliefs": _site_reliefs_of(session),
                    "marked_centers": {},
                    "alignment_evidence": {},
                },
            }
            record_activity(session, ACT_RUN_AUTHORIZED,
                            f"construction/relief changed — re-emitting run "
                            f"{source_run_id}'s poses as run {reemit_run_id}")
        elif effective_changed:
            for site in session.sites.values():
                site.status = status.invalidate_preview(site.status)
                site.clear_preview_facts()
            # the run boundary (5c): changed choices describe a different shipped
            # part, so the current-run pointer clears — the run directory survives
            # as immutable history, but a stale run never masquerades as current.
            # ``clear_current_run`` is that boundary's one home: the adjust decision
            # was made over these verdicts and falls with them
            clear_current_run(session)
        # THE LOG RECORDS A CHANGE, NOT A SUBMIT. This is a PUT of the whole panel and
        # the UI re-submits it whenever anything in it moves, so a byte-identical
        # re-PUT is not an act — recording it would spend the log's bounded window on
        # entries that describe nothing, pushing real acts out. The reset boundary's
        # own guard (``effective_changed``) is not the right test here: pinning a
        # suggestion changes the raw document without moving the effective one, and
        # "the lab chose this explicitly" is worth a line even though it retires
        # nothing. What the entry then states is the CONSEQUENCE — whether previews
        # fell — because that is the thing an operator later asks about.
        if replacement != session.choices:
            record_activity(
                session, ACT_CHOICES_SET,
                ("case choices set — the fits stand; the package re-emits from "
                 "the run's own poses")
                if "request" in reemit else
                "case choices set — the previews and the current run were "
                "retired (they described a different shipped part)"
                if effective_changed else
                "case choices set — the effective selection did not move, "
                "so nothing was retired")
        session.choices = replacement

    session = _mutate_session(store, case_id, apply)
    if "request" in reemit:
        session = _drive_reemit_job(worker, store, settings, case, case_id,
                                    reemit_run_id, reemit["request"])
    return _detail(case, session, settings)


@router.put("/{case_id}/sites/{tooth}/relief", response_model=CaseSessionDetail)
def put_site_relief(case_id: str, tooth: int, body: SiteReliefIn,
                    request: Request) -> CaseSessionDetail:
    """SET (or clear) one site's relief override — §10-B/C landed on the §10-AC lane.

    Relief shapes the EMITTED part and nothing else (§10-C's measured fact), so this
    act moves no rung and retires no review; over a DONE run it RE-EMITS the package
    from the run's own poses with the new per-site ask — the confirmation and every
    draft fall explicitly, exactly as on the choices boundary. Without a done run
    the override simply persists and rides the next run's selection. The ceiling is
    judged at cut time per (part × variant) and lands on the row's clamp trio, as
    it always has."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    worker: WorkerPort = request.app.state.worker
    reemit_run_id = _mint_run_id()
    reemit: Dict[str, dict] = {}

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.setdefault(str(tooth), SiteSession())
        before = site.gingival_offset_mm
        after = body.gingival_offset_mm
        if before == after:
            return   # an identical re-assertion states nothing new
        site.gingival_offset_mm = after
        effective = _effective_choices(case, session.choices, session.detection)
        run_done = (session.run is not None and session.run.state == "done"
                    and (session.run.run_id or session.run.job_id) is not None)
        if run_done:
            source_run_id = session.run.run_id or session.run.job_id
            session.run = RunSession(job_id=reemit_run_id, run_id=reemit_run_id,
                                     state="queued")
            session.adjust_decision = None
            clear_exception_intents(session)
            clear_confirmation(session)
            reemit["request"] = {
                "run_id": reemit_run_id,
                "mode": "reemit",
                "source_run_id": source_run_id,
                "selection": {
                    "model": _effective_model(case, session),
                    "construction_path": effective.construction_path,
                    "jaw": effective.jaw,
                    "gingival_offset_mm": effective.gingival_offset_mm,
                    "variants": {t: st.declared_variant
                                 for t, st in session.sites.items()
                                 if st.declared_variant is not None},
                    "site_reliefs": _site_reliefs_of(session),
                    "marked_centers": {},
                    "alignment_evidence": {},
                },
            }
        ask = ("cleared — the case-level relief stands"
               if after is None else f"set to {after:.2f}mm")
        record_activity(session, ACT_CHOICES_SET,
                        f"tooth {tooth}'s relief override {ask}"
                        + (f" — re-emitting run {reemit['request']['source_run_id']}'s "
                           f"poses as run {reemit_run_id}" if "request" in reemit
                           else " — it rides the next run"),
                        tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    if "request" in reemit:
        session = _drive_reemit_job(worker, store, settings, case, case_id,
                                    reemit_run_id, reemit["request"])
    return _detail(case, session, settings)


@router.put("/{case_id}/system", response_model=CaseSessionDetail)
def put_system(case_id: str, body: SystemIn, request: Request) -> CaseSessionDetail:
    """Declare the case-scoped implant SYSTEM (plan §4 Declare / AM-8).

    Switching the model is the explicit case-level act that resets every site: a
    variant id belongs to ONE system's catalog, so every declared variant drops and
    every site regresses to detected — the demo's ``librarySelection.withModel``
    semantics (librarySelection.ts:96-103) REIMPLEMENTED server-side, because the
    state lives in the session now and the client only displays what came back
    (ledger NOTE row: a semantic port, not a code copy). Same-model PUTs — including
    pinning the suggestion as an explicit act — reset nothing, which is withModel's
    own equality guard. Retry-or-409 posture: the mutation re-derives the reset from
    each fresh load, so a retry is exact; a second conflict is the 409.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    try:
        require_library_model(settings.data_root, body.model)
    except UnknownSelection as exc:
        raise HTTPException(422, str(exc))

    def apply(session: CaseSession) -> None:
        if body.model != _effective_model(case, session):
            for site in session.sites.values():
                site.status = status.regress_to_detected(site.status)
                site.declared_variant = None
                site.clear_preview_facts()   # a preview of a dropped variant (5b)
                # AUDIT 2026-08-04: a "pairs" entry's PART half (feature_id /
                # part_point) was measured against the old system's cap —
                # re-applying it against the new one would land an 'applied'
                # receipt over physics nobody measured on this part. The
                # scan-frame kinds (mark; best_fit's diameter ask) survive:
                # the scan did not change.
                site.alignment_evidence = [
                    e for e in site.alignment_evidence if e.kind != "pairs"]
            # the run boundary (5c): a run of the old system — and the fork
            # decided over its verdicts (see ``clear_current_run``)
            clear_current_run(session)
            record_activity(session, ACT_SYSTEM_DECLARED,
                            f"implant system switched to {body.model!r} — every site "
                            f"dropped its variant and returned to detected")
        else:
            record_activity(session, ACT_SYSTEM_DECLARED,
                            f"implant system declared {body.model!r}")
        session.system = body.model

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.put("/{case_id}/sites/{tooth}/declaration", response_model=CaseSessionDetail)
def put_declaration(case_id: str, tooth: int, body: DeclarationIn,
                    request: Request) -> CaseSessionDetail:
    """Declare a site's cap variant (plan §4 Declare / AM-8) — the act that moves the
    site detected→declared, THROUGH the status machine (bff/status.py).

    Validation corpus (plan §6/AM-9): the tooth must be a site the case actually has
    (404 — the path names a missing subresource); the variant must be an entry of the
    EFFECTIVE system's catalog, by the catalog's own id (422 in the catalog's words —
    archived parts enter one explicit name at a time, the demo's ``_library_for``
    rule, reached through ``application.catalog.require_variant``).

    A re-declaration of a different variant KEEPS declared and clears every
    later-ladder fact about the old part — trivially true today (no such facts exist
    until 5b's previews and review ticks), but the rule lives here NOW so later
    slices clear their facts at this stated boundary instead of rediscovering it.
    A re-declaration of the SAME variant changes nothing at all. Retry-or-409: the
    validation AND the transition re-derive from each fresh load; a second conflict
    is the 409.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        # The validation lives INSIDE the mutation — deliberately, because this is
        # the one route whose validity depends on SESSION state (the effective
        # system). Judged against a separate pre-load, a rival system switch landing
        # between that load and the CAS save let a foreign variant onto the switched
        # document with a 200 (the 5a adversarial review's dangling-variant race):
        # the retry must re-JUDGE against what is actually there, not re-apply a
        # verdict reached against what used to be. A refusal raised here propagates
        # before any save — asking still creates nothing.
        _require_known_tooth(case, session, tooth)
        model = _effective_model(case, session)
        if model is None:
            raise HTTPException(422, f"case {case_id!r} has no implant system yet — "
                                     f"declare the implant system before declaring "
                                     f"variants")
        try:
            require_variant(settings.data_root, model, body.variant)
        except UnknownSelection as exc:
            raise HTTPException(422, str(exc))
        site = session.sites.get(str(tooth), SiteSession())
        if site.declared_variant != body.variant:
            site.status = status.declare(site.status)
            site.declared_variant = body.variant
            # the declaration is the reset boundary (5a's stated rule, real since
            # 5b): the old part's preview facts fall with its rung
            site.clear_preview_facts()
            # AUDIT 2026-08-04: pairs evidence carries a PART half measured
            # against the variant this site no longer declares — it retires with
            # the rung. Marks and best-fit asks are scan-frame and survive.
            site.alignment_evidence = [
                e for e in site.alignment_evidence if e.kind != "pairs"]
            # the run boundary (5c): the current run aligned a part this site no
            # longer declares — the pointer clears (the run dir stays, as history),
            # and the fork decided over its verdicts goes with it
            clear_current_run(session)
            # only a REAL declaration is recorded: a re-declaration of the same
            # variant changes nothing, and a log entry for it would be noise the
            # window then charges a real act for
            record_activity(session, ACT_SITE_DECLARED,
                            f"variant {body.variant!r} declared", tooth=tooth)
        session.sites[str(tooth)] = site

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.post("/{case_id}/sites/{tooth}/preview")
def preview_site_action(case_id: str, tooth: int, request: Request) -> dict:
    """Seat the site's DECLARED cap and return its deviation colouring — the three
    panes' union read, before any run (plan §4 Declare / §7 slice 5b).

    A compute TRIGGER like detect: NO body at all — the declaration and the case-level
    choices it seats with come from the session, so there is nothing a client could
    claim with. The response is ``application.preview``'s payload VERBATIM (the demo's
    wire shape — the copied deviationColormap/pane code renders it); the mesh is
    response-only. What persists are the seat FACTS — the previewed rung through the
    status machine, ``seat_method``, ``rim_agreement_mm`` — and they persist INSIDE
    the mutation, re-judged against the fresh document (commit 25604e7's rule): a
    rival re-declaration landing during the multi-second derivation makes the derived
    facts describe a part no longer declared, and they must refuse (409), never land.

    MULTI-SECOND (the demo measured ~3.5s per site): phase 2 moves this behind the
    job-shaped worker port (plan §3/AM-3) exactly like the full run; until then the
    handler computes in-process and the UI treats it per-site non-blocking — stepping
    sites while one previews is legal, and the busy pane names the work.
    """
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def judge(session: CaseSession) -> PreviewSelection:
        """What the preview seats WITH, read off one session document — refusing
        (404/422, naming exactly what is missing) when the session cannot answer.
        Called on the pre-derivation load (an impossible ask must not cost seconds of
        physics) and AGAIN on the fresh document inside the mutation.

        The choices consumed are the EFFECTIVE ones (client 2026-07-27: a fresh
        session + a declaration previews on the suggestions and the standing
        relief default); a case whose suggestion is absent still refuses, naming
        the piece no fallback covers."""
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth))
        effective = _effective_choices(case, session.choices, session.detection)
        model = _effective_model(case, session)
        missing = []
        if site is None or site.declared_variant is None:
            missing.append("a declared cap variant for this site")
        if model is None:
            missing.append("the implant system")
        if effective.construction_path is None:
            missing.append("the construction part")
        if effective.jaw is None:
            missing.append("the jaw")
        if effective.gingival_offset_mm is None:
            missing.append("the gingival relief")
        if missing:
            raise HTTPException(422, f"nothing to preview yet — tooth {tooth} on "
                                     f"case {case_id!r} still needs: "
                                     + ", ".join(missing))
        return PreviewSelection(
            model=model, construction_path=effective.construction_path,
            variant=site.declared_variant, jaw=effective.jaw,
            gingival_offset_mm=effective.gingival_offset_mm,
            # the operator's re-mark reaches the PREVIEWED pose too (the 12°
            # defect, 2026-08-04) — the worker seeds it alone, pair-integrity
            marked_center=site.marked_center)

    selection = judge(store.load(case_id))
    try:
        payload = preview_site(case, selection, tooth)
    except PreviewRefused as exc:
        # the pipeline's own refusal, in the words the gate wrote (the demo's 409)
        raise HTTPException(409, str(exc))
    except (ScanUnreadable, UnknownSelection) as exc:
        raise HTTPException(422, str(exc))
    seat = payload.get("seat") or {}

    def apply(session: CaseSession) -> None:
        if judge(session) != selection:
            raise HTTPException(409, f"case {case_id!r} changed while the preview "
                                     f"was computing — re-read the case; the panes "
                                     f"re-ask against what is actually there now")
        site = session.sites[str(tooth)]
        # THE SEAT RECORD (AM-8; the 2026-07-28 effective-default drift finding):
        # what this preview actually seated, kept beside the facts. Equality with
        # the site's previous record picks the landing — unchanged seat goes
        # through the machine's ``preview`` (READY holds: a reload never unticks),
        # a changed or unrecorded seat through ``reseat_preview`` (READY falls:
        # these panes now show physics the review never attested, and the drift
        # must cost the tick visibly, never repaint under it).
        seated = SeatedSelection(
            model=selection.model, construction_path=selection.construction_path,
            variant=selection.variant, jaw=selection.jaw,
            gingival_offset_mm=selection.gingival_offset_mm)
        site.status = (status.preview(site.status)
                       if site.seated_selection == seated
                       else status.reseat_preview(site.status))
        site.seat_method = seat.get("seat_method")
        site.rim_agreement_mm = seat.get("rim_agreement_mm")
        site.seated_selection = seated
        record_activity(session, ACT_SITE_PREVIEWED,
                        f"previewed on {selection.variant!r} — "
                        f"{site.seat_method or 'no seat method reported'}",
                        tooth=tooth)

    try:
        _mutate_session(store, case_id, apply)
    except status.IllegalTransition as exc:
        raise HTTPException(422, str(exc))
    return payload


@router.post("/{case_id}/sites", response_model=CaseSessionDetail)
def post_marked_site(case_id: str, body: MarkedSiteIn,
                     request: Request) -> CaseSessionDetail:
    """Add a site the DETECTOR MISSED (client 2026-07-28).

    Detection finds 8 of the 10 sites on this fleet. Before this route the other two
    were unworkable: a centre lived only in the case record, which the ingest writes
    and an operator cannot. The mark rides in the SESSION with every other operator
    act, and the run prefers it over the case's own suggestion (application.run) —
    a human who marked a centre has looked at this scan more recently than the ingest.

    Judged INSIDE the mutation against the fresh document (commit 25604e7's rule):
    a rival mark landing on the same tooth between load and save must lose loudly,
    not overwrite. Refuses a tooth that is already a site — re-marking an existing
    cap is a DIFFERENT act with different consequences (it invalidates a preview
    and a review, and the run cropped around the old centre), and conflating the
    two here would let a mis-typed tooth number silently retire an attestation.
    That different act now exists (2026-08-01) — ``put_remarked_site``, below —
    and this refusal names it: the two routes point at each other, so a tooth
    number has exactly one legal door and a refusal always says which."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    if len(body.center) != 3 or not all(math.isfinite(c) for c in body.center):
        raise HTTPException(422, "the mark's centre must be a finite [x, y, z] point "
                                 "in the scan's own frame")
    if not 1 <= body.tooth <= 32:
        raise HTTPException(422, f"tooth {body.tooth} is not a tooth number "
                                 f"(1-32, FDI/universal as the case uses)")

    def apply(session: CaseSession) -> None:
        known = ({int(s["tooth"]) for s in case.suggested_sites}
                 | {int(k) for k in session.sites})
        if body.tooth in known:
            raise HTTPException(
                409, f"tooth {body.tooth} is already a site on case {case.id!r} — "
                     f"marking is for caps detection MISSED; to correct this "
                     f"site's centre, use PUT .../sites/{body.tooth}/mark instead")
        session.sites[str(body.tooth)] = SiteSession(
            marked_center=[float(c) for c in body.center])
        record_activity(session, ACT_SITE_MARKED,
                        "healing cap centre marked by hand — detection missed this "
                        "site", tooth=body.tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.put("/{case_id}/sites/{tooth}/mark", response_model=CaseSessionDetail)
def put_remarked_site(case_id: str, tooth: int, body: RemarkedSiteIn,
                      request: Request) -> CaseSessionDetail:
    """Re-mark an EXISTING site's centre (client 2026-08-01, the tooth-29 gap on
    case cap6020-neodent-gm: the detector's proposed centre sat visibly off the
    cap, and the operator had no way to correct it).

    ``post_marked_site``'s EXACT COMPLEMENT — a tooth must already BE a site here,
    404 otherwise (naming that route back), where that one refuses a tooth that
    already is one (409, naming this one). Between the two, every tooth number has
    exactly one legal door.

    THE CONSEQUENCES ``post_marked_site``'S OLD DOCSTRING NAMED NOW ACTUALLY FIRE,
    on the ONE site whose centre moved, and ONLY when the centre actually changes
    (judged over the EFFECTIVE value — the site's own mark if it has one, else the
    case's suggestion — the same ``withModel`` equality guard the system and
    choices routes use, so an identical re-PUT costs nothing):

      * the rung drops through ``status.invalidate_preview`` — the SAME per-site
        reset ``put_choices`` uses for a changed construction/jaw/relief, because a
        moved centre is the same CLASS of fact: the declared VARIANT survives (the
        cap did not change, only where it sits), only the physics derived from the
        OLD centre falls;
      * ``SiteSession.clear_preview_facts`` forgets the seat facts that physics
        produced, so they can never drift out of step with the rung that
        justified them (the reset boundaries' one home for that pairing);
      * ``clear_current_run`` drops the case's current-run pointer — the run was
        CROPPED around the old centre, so it is stale physics the instant the
        centre moves, the same boundary ``put_choices``/``put_system``/
        ``put_declaration`` already fire for their own triggers (the run
        directory survives on disk as immutable history; only the pointer falls).

    A STANDING CONFIRMATION IS ALSO RETIRED HERE, and that is this boundary's ONE
    deliberate divergence from those three siblings. ``clear_current_run``'s own
    docstring documents that choices/system/declaration changes leave a
    confirmation standing on purpose — it goes inert the moment its run_id no
    longer names the current run, and every act that could disclose or charge
    against it (``deliver._require_done_run_for_act``) already refuses on that
    mismatch, so under-claiming there costs nothing. That argument does not
    survive a re-mark: what stood confirmed was sealed over evidence measured
    from the exact centre the operator has just said is WRONG, and the words this
    surface must show BEFORE arming the pick name the run "and anything signed
    over it" as retired — a promise made out loud before the act, which must come
    true here rather than merely become unreachable three requests later behind a
    gate nobody was shown. ``clear_confirmation`` is the one-home helper for
    exactly this (session.py) — called here, never hand-rolled.

    Validation is ``MarkedSiteIn``'s minus the tooth (the path already names it):
    finite [x, y, z], sent exactly as clicked and never re-centred here — the
    re-click pair-integrity record says a human's mark is fixed at the UI or
    refused, and a re-mark REPLACES the old mark whole rather than nudging it.
    Judged and applied INSIDE the mutation (25604e7's rule): a rival re-mark, a
    declaration or a run landing between the load and the save must be judged
    against the fresh document, never a stale one."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    if len(body.center) != 3 or not all(math.isfinite(c) for c in body.center):
        raise HTTPException(422, "the mark's centre must be a finite [x, y, z] point "
                                 "in the scan's own frame")

    suggested_center = next(
        (s.get("center") for s in case.suggested_sites if int(s["tooth"]) == tooth),
        None)

    def apply(session: CaseSession) -> None:
        known = ({int(s["tooth"]) for s in case.suggested_sites}
                 | {int(k) for k in session.sites})
        if tooth not in known:
            raise HTTPException(
                404, f"tooth {tooth} is not a site on case {case.id!r} yet — "
                     f"re-marking is for a site the case already has; a cap "
                     f"detection MISSED is marked through POST .../sites instead")
        site = session.sites.get(str(tooth), SiteSession())
        effective_before = (site.marked_center if site.marked_center is not None
                            else suggested_center)
        new_center = [float(c) for c in body.center]
        if effective_before == new_center:
            return   # an identical re-assertion states nothing new (no act, no reset)
        site.marked_center = new_center
        site.status = status.invalidate_preview(site.status)
        site.clear_preview_facts()
        # THE PAIR-INTEGRITY RULE reaches the evidence too (§10-AD): marks and
        # pairs were measured against the OLD centre's crop — a moved centre
        # retires them rather than letting a future run re-apply stale geometry
        site.alignment_evidence = []
        # THE RIM BORDER-POINTS AID RETIRES HERE TOO (§10-AL): the points were
        # clicked around THIS centre's rim, and a centre the operator has just
        # said is wrong cannot go on anchoring a rim reading nobody re-clicked —
        # the exact same pair-integrity reasoning as the line above, one field
        # over (session.py's ``SiteSession.rim_points`` docstring is this
        # invariant's other pin).
        site.rim_points = None
        # the run boundary (5c, mirrored for a fourth trigger): the current run
        # was cropped around the OLD centre, so stale physics can never
        # masquerade as current the instant the centre moves
        clear_current_run(session)
        # THE ONE DIVERGENCE FROM CHOICES/SYSTEM/DECLARATION (see the docstring
        # above): what was confirmed here was sealed over evidence measured from
        # the centre this act has just said is wrong, and the words shown before
        # this pick was armed promised it retires
        clear_confirmation(session)
        session.sites[str(tooth)] = site
        record_activity(session, ACT_SITE_REMARKED,
                        "healing cap centre re-marked by hand — the previous "
                        "mark's preview, review, the run cropped around it and "
                        "any confirmation over it were retired", tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.put("/{case_id}/sites/{tooth}/rim-points", response_model=CaseSessionDetail)
def put_rim_points(case_id: str, tooth: int, body: RimPointsIn,
                   request: Request) -> CaseSessionDetail:
    """Record the operator's rim border-points for one site (§10-AL, "we lost the
    tool we had in the demo where we made points around the border of the healing
    cap in the scan"). Scoped to INTAKE by the plan's own measurement (§10-AH: a
    pair-shaped centre+rim seed LOST to the bare click on the DEV metric) — this
    body feeds the capture assessment's rim-diameter read, never a seat.

    NOT a reset boundary: unlike ``put_remarked_site``, setting rim points changes
    no centre and derives no new physics for a preview or a run to disagree with,
    so no rung falls and no confirmation retires. Idempotent under the
    ``SeatedSelection`` precedent this module already uses everywhere else — an
    identical re-PUT records no second act.

    Requires the tooth already be a site (``_require_known_tooth``): a border
    reading is measured relative to a centre, so there must be one to measure
    against, exactly the ordering ``put_remarked_site`` requires for the same
    reason."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        if site.rim_points == body.points:
            return   # an identical re-assertion states nothing new (no act)
        site.rim_points = body.points
        session.sites[str(tooth)] = site
        record_activity(session, ACT_SITE_RIM_POINTS_SET,
                        f"{len(body.points)} rim border points recorded — feeds "
                        f"this site's capture read, never its seat", tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.delete("/{case_id}/sites/{tooth}/rim-points", response_model=CaseSessionDetail)
def delete_rim_points(case_id: str, tooth: int, request: Request) -> CaseSessionDetail:
    """Clear a standing rim border-points reading — ``put_rim_points``'s reverse,
    reachable the same way back (``put_withhold_intent``'s "bring it back" rule,
    applied here). Refuses 422 for a tooth carrying no standing points: clearing
    nothing is not an act either (``delete_acknowledge_exception``'s own posture)."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        if site.rim_points is None:
            raise HTTPException(
                422, f"tooth {tooth} carries no standing rim border points to clear")
        site.rim_points = None
        session.sites[str(tooth)] = site
        record_activity(session, ACT_SITE_RIM_POINTS_CLEARED,
                        "rim border points cleared", tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.post("/{case_id}/sites/{tooth}/review", response_model=CaseSessionDetail)
def post_review(case_id: str, tooth: int, request: Request) -> CaseSessionDetail:
    """The operator's review tick over the live panes (plan §4 Declare / AM-8): the
    ATTESTATION that this site's panes were read — an ACT, like choices (AM-4 allows
    acts, forbids claimed verdicts). No body at all, deliberately: the act's whole
    content is the request itself, so no field exists for a claimed outcome to ride
    in on. The previewed→ready move is the machine's ``review_ready``, which refuses
    (422, in the ladder's words) any site not standing on a preview — a tick over
    nothing stays impossible server-side, not merely unrendered. Judged INSIDE the
    mutation: the rung is session state (25604e7's rule)."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        site.status = status.review_ready(site.status)
        session.sites[str(tooth)] = site
        record_activity(session, ACT_SITE_REVIEWED,
                        "reviewed over the live panes", tooth=tooth)

    try:
        session = _mutate_session(store, case_id, apply)
    except status.IllegalTransition as exc:
        raise HTTPException(422, str(exc))
    return _detail(case, session, settings)


@router.delete("/{case_id}/sites/{tooth}/review", response_model=CaseSessionDetail)
def delete_review(case_id: str, tooth: int, request: Request) -> CaseSessionDetail:
    """The tick un-ticked — the demo's review checkbox was two-way, and an attestation
    the operator can withdraw is more honest than one that only latches. ready→
    previewed through the machine's ``withdraw_review`` (the panes are still rendered;
    only the attestation is gone — the preview facts deliberately survive), refusing
    (422) a withdrawal of a review that was never given."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        site.status = status.withdraw_review(site.status)
        session.sites[str(tooth)] = site
        record_activity(session, ACT_SITE_REVIEW_WITHDRAWN,
                        "review withdrawn — the panes stand, the attestation does "
                        "not", tooth=tooth)

    try:
        session = _mutate_session(store, case_id, apply)
    except status.IllegalTransition as exc:
        raise HTTPException(422, str(exc))
    return _detail(case, session, settings)


# --- dropping a cap (gap ``drop-a-cap-from-adjust``, 2026-07-31) ------------------------

@router.put("/{case_id}/sites/{tooth}/withhold", response_model=CaseSessionDetail)
def put_withhold_intent(case_id: str, tooth: int, body: WithholdIntentIn,
                        request: Request) -> CaseSessionDetail:
    """Record — or take back — the operator's intent to WITHHOLD this site.

    THE ACT ALREADY EXISTED; ITS REACH DID NOT. ``ConfirmIn.dispositions`` has
    carried release|withhold per site since slice 8, but only from Deliver, at
    signing time. An operator who gives up on a stubborn cap at Adjust had nowhere
    to put that decision until they reached the signing screen — and before any
    confirmation exists there is no record of the intent at all. This route is that
    missing reach, NOT a second exclusion concept: what it writes is a DRAFT that
    ``confirm_case`` folds under the body's own entries.

    THE INTENT IS A DRAFT; THE CONFIRMATION IS THE ACT. Nothing here signs
    anything — the confirmation's body still carries the disposition map, still
    seals it over re-derivable evidence, and an explicit entry there still wins over
    this. That separation is the whole reason this is admissible under AM-4's
    doctrine: a draft that could seal itself would be a client writing a disclosure
    outcome.

    IT IS ALWAYS REACHABLE, both ways. No run, no preview and no declaration is
    required: the decision is recordable at the moment it is actually taken, and the
    reversal is the same route with ``false`` — "bring this cap back into the case"
    must never be harder to find than the drop was.

    A CONTRADICTED CONFIRMATION IS RETIRED (``clear_confirmation``), and the reason
    is worth stating because a draft retiring a signature looks backwards. A
    standing confirmation that signed this site as RELEASED no longer describes what
    the operator wants; dispositions live outside the evidence hash, so the sha does
    not move and the artifact gate's re-derivation would not catch it — the surface
    would go on reading "Released ✓" over a cap the operator has just dropped. This
    module's own rule for the reverse case is already "the operator's newest signed
    act wins, and disclosure stops until an explicit re-release"; under-claiming a
    release is the safe direction everywhere here, and the honest path out is the
    one every other drift takes — re-confirm over what is there now. An intent the
    confirmation ALREADY agrees with retires nothing (an identical re-act flips no
    equality — the ``SeatedSelection`` precedent). The PAYMENT record survives:
    money is not evidence.

    Judged INSIDE the mutation, like every other per-site act, so a rival write
    mid-flight is re-judged rather than re-applied from a stale read."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        # THE CONTRADICTION IS A PROPERTY OF THE STATE, NOT OF THE TRANSITION (audit
        # 2026-07-31). This was judged AFTER an equality early-return, so the state
        # "intent = withhold, standing confirmation = release" — reachable by
        # confirming with an explicit ``{"13": "release"}`` over a dropped cap, the
        # exact path the UI takes when the operator presses `release` on the flagged
        # row — could never be escaped: pressing DROP again matched the intent
        # already on the site and returned 200 having retired nothing, so the cap
        # shipped and was billed while Adjust rendered it dropped. ``confirm_case``
        # now writes the resolved disposition back onto the site, which makes that
        # state unreachable; this ordering is the belt to that fix's braces, and the
        # cheaper half to keep right.
        confirmation = session.confirmation
        signed = (confirmation.dispositions.get(str(tooth))
                  if confirmation is not None else None)
        contradicted = signed is not None and (
            signed == "withhold") != body.withhold
        if site.withhold_intent == body.withhold and not contradicted:
            return   # not an act: an identical re-assertion states nothing new
        site.withhold_intent = body.withhold
        session.sites[str(tooth)] = site
        if contradicted:
            clear_confirmation(session)
        # THE WORDS ARE NOT THE DESIGN'S. Its log line reads "dropped — not aligned,
        # not billed" (flow.dc.html 1352); post-run the first half is a lie — the
        # alignment already ran, and this route deliberately leaves the pipeline
        # alone. What is true either side of a run is that nothing is released for
        # the site and it is not billed.
        detail = ("held back — no construction is released for it and it is not "
                  "billed; the confirmation still signs the dispositions"
                  if body.withhold else
                  "brought back into the case — it releases and bills with the rest")
        if contradicted:
            detail += "; the standing confirmation no longer described this and " \
                      "was retired with any release over it"
        record_activity(session, ACT_SITE_WITHHOLD_INTENT, detail, tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- accepting a flagged exception in advance (client ruling 2026-08-02) ----------------
#
# The comp's amber "accept as flagged exception" button moves onto the Adjustment page.
# THE DESIGN DECISION, already taken: this is a persisted DRAFT — ``withhold_intent``'s
# sibling, not a second acknowledgment concept — that PRE-FILLS Deliver's row-by-row
# checkboxes. It is NOT a signature: ``ConfirmIn.acknowledged_flags`` (AM-12) stays
# required and stays the only thing that seals a released flagged row; this route buys
# the operator a pre-ticked box, never a shortcut past ticking it.

def _run_summary_row(run: RunSession, tooth: int) -> Optional[dict]:
    """The CURRENT run's own row for one tooth. Mirrors ``adjust._summary_row`` exactly
    — re-homed rather than imported, because case_sessions.py sits BELOW adjust.py in
    this package's layering (adjust.py imports from here AND from deliver.py, which
    also imports from here); importing adjust.py from here would cycle. Five lines is
    cheaper than a fourth module knowing about a third."""
    for row in (run.summary or {}).get("sites") or []:
        try:
            if int(row.get("tooth", -1)) == tooth:
                return row
        except (TypeError, ValueError):
            continue
    return None


@router.post("/{case_id}/sites/{tooth}/acknowledge", response_model=CaseSessionDetail)
def post_acknowledge_exception(case_id: str, tooth: int,
                               request: Request) -> CaseSessionDetail:
    """ACCEPT AS FLAGGED EXCEPTION — IN ADVANCE (client ruling 2026-08-02). Modeled
    letter for letter on the review pair above: body-less both ways — the act's whole
    content is the request itself — validity judged INSIDE the mutation (25604e7's
    rule: a rival run landing between the load and the save must be judged against
    what is actually there, never a stale read), ``record_activity`` beside the write.

    THE ELIGIBILITY CHECK IS ``session.needs_acknowledgment`` — the SAME predicate
    ``deliver.confirm_case``'s row-by-row gate stands on (lifted there to session/run
    facts precisely so this route and that gate cannot drift apart): a site the
    confirm gate would never demand an acknowledgment for cannot be pre-acknowledged
    either, or the draft would be a claim about nothing. Refuses 422, in the rule's
    own words, unless there is a completed CURRENT run and this tooth's row on it
    needs acknowledgment — a flagged verdict, or a production block naming a
    shared-construction-part conflict.

    IDEMPOTENT, the same reading ``put_withhold_intent`` gives the SeatedSelection
    precedent: a second POST over a standing draft states nothing new and records no
    second act."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        run = session.run
        if run is None or run.state != "done" or run.summary is None:
            raise HTTPException(
                422, f"there is nothing to acknowledge yet — case {case_id!r} has "
                     f"no completed current run, and the exception is a draft "
                     f"about ITS verdict")
        row = _run_summary_row(run, tooth)
        if row is None:
            raise HTTPException(
                422, f"tooth {tooth} carries no verdict on the current run — the "
                     f"exception is a draft about a row that does not exist yet")
        site = session.sites.get(str(tooth), SiteSession())
        production_note = (row.get("production") or {}).get("note")
        if not needs_acknowledgment(site.status.value, production_note):
            raise HTTPException(
                422, f"tooth {tooth} needs no acknowledgment — the run's guidance "
                     f"did not flag it, and its production block names no "
                     f"shared-construction-part conflict; there is nothing for "
                     f"this draft to accept in advance")
        if site.exception_intent is not None:
            return   # not an act: an identical re-assertion states nothing new
        site.exception_intent = _now_iso()
        session.sites[str(tooth)] = site
        record_activity(
            session, ACT_SITE_EXCEPTION_ACKNOWLEDGED,
            "acknowledged in advance as a flagged exception — Deliver's "
            "confirmation is what signs it", tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.delete("/{case_id}/sites/{tooth}/acknowledge",
               response_model=CaseSessionDetail)
def delete_acknowledge_exception(case_id: str, tooth: int,
                                 request: Request) -> CaseSessionDetail:
    """Withdraw the draft — ``post_acknowledge_exception``'s exact reversal, reachable
    the same way back: an operator who pre-accepted a row and changed their mind must
    find taking it back no harder than giving it (``put_withhold_intent``'s own
    "bring it back" rule, applied here). Refuses 422 for a tooth carrying no standing
    draft — withdrawing nothing is not an act either."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        _require_known_tooth(case, session, tooth)
        site = session.sites.get(str(tooth), SiteSession())
        if site.exception_intent is None:
            raise HTTPException(
                422, f"tooth {tooth} carries no standing exception acknowledgment "
                     f"to withdraw")
        site.exception_intent = None
        session.sites[str(tooth)] = site
        record_activity(
            session, ACT_SITE_EXCEPTION_WITHDRAWN,
            "the advance acknowledgment was withdrawn — Deliver's checkbox for "
            "this row goes back to unticked", tooth=tooth)

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


# --- the run (plan §7 slice 5c; §1.2/AM-1, §3/AM-3, §4 Declare/AM-8) --------------------

def _now_iso() -> str:
    """The one wall-clock stamp this module records (the fork's ``at``); deliver.py
    keeps its own for the signing records — same UTC-ISO shape, different module."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _mint_run_id() -> str:
    """The immutable run directory's name (AM-1): sortable wall-clock prefix + a
    random suffix so two same-second runs (two uvicorn threads, two operators) can
    never collide onto one directory."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def _rescan_recapture_sentence(capture: dict) -> str:
    """The capture gate's own recapture copy — the worst rescan check's message,
    the same sentence Intake's banner already quotes. Never a second vocabulary
    invented at the authorized-run gate (P4.2)."""
    for check in capture.get("checks") or []:
        if isinstance(check, dict) and check.get("verdict") == "rescan":
            msg = check.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    return "Capture quality is below the rescan threshold."


def _authorized_selection(case: CaseRecord, case_id: str,
                          session: CaseSession) -> dict:
    """THE AUTHORIZED GATE, server-minted (AM-8): the full run fires only when the
    EFFECTIVE case-level choices are complete AND every site is READY — the
    operator's review tick over the live panes, not a checkbox. Refuses 422 naming
    EACH missing piece (the operator fixes what is named, never guesses); pieces a
    suggestion or the standing default covers are not missing (client 2026-07-27 —
    the same effective document the previews seated with). READY alone does not
    authorize (the 2026-07-28 effective-default drift finding): each reviewed
    site's RECORDED seat must still equal the selection the run would seat, else
    the fallbacks drifted since the review — no boundary fires for those, so the
    gate is where the drift must refuse, never a run over unattested physics.
    Returns the job-shaped selection, judged INSIDE the mutation that persists the
    receipt (25604e7's rule: a rival change mid-anything is a 409, not a stale
    verdict)."""
    sites = _site_views(case, session)
    missing: List[str] = []
    model = _effective_model(case, session)
    effective = _effective_choices(case, session.choices, session.detection)
    if model is None:
        missing.append("the implant system")
    if effective.construction_path is None:
        missing.append("the construction part")
    if effective.jaw is None:
        missing.append("the jaw")
    if effective.gingival_offset_mm is None:
        missing.append("the gingival relief")
    # with any case-level piece missing there is no selection to compare seats
    # against — the refusal already names the piece, so the per-site judgment
    # below only runs over a complete document
    case_level_complete = not missing
    if not sites:
        missing.append("at least one site")
    for view in sites:
        if view.status != SiteStatus.READY.value:
            missing.append(f"tooth {view.tooth} reviewed over the panes "
                           f"(now {view.status!r})")
        elif case_level_complete:
            # READY implies a declaration (the ladder's construction), so the
            # variant lookup cannot miss; the record is absent only on documents
            # persisted before it existed — unverifiable, so it fails closed too
            site = session.sites[str(view.tooth)]
            seat = site.seated_selection
            # SHARPENED (§10-AC/C, 2026-08-04): the equality covers the POSE
            # INPUTS — model, variant, jaw — because those are what the seat the
            # review attested depends on. Relief and the construction part are
            # provably pose-independent (§10-M/C, measured), so their drift no
            # longer refuses: the attested seat is bit-identical under them, and
            # their changes ride the re-emit lane instead. An absent record still
            # fails closed — READY without proof stays unverifiable.
            if (seat is None or seat.model != model
                    or seat.variant != site.declared_variant
                    or seat.jaw != effective.jaw):
                missing.append(f"tooth {view.tooth} re-previewed and re-reviewed "
                               f"— its review attested a seat the case's current "
                               f"selection no longer describes")
    if session.detection is not None:
        # P4.2 — a capture-gate rescan is a hard run refusal. The instruments
        # already exist on site_capture; this names the gate's own recapture
        # sentence so the operator rescans while the patient is still seated.
        # Missing detection is not a refusal (honest absence — the gate has not
        # spoken). pass/marginal do not block.
        for view in sites:
            cap = session.detection.site_capture.get(str(view.tooth))
            if isinstance(cap, dict) and cap.get("verdict") == "rescan":
                missing.append(
                    f"tooth {view.tooth} recaptured while the patient is in the "
                    f"chair — {_rescan_recapture_sentence(cap)}")
    if missing:
        raise HTTPException(422, f"the run is not authorized yet — case {case_id!r} "
                                 f"still needs: " + "; ".join(missing))
    return {
        "model": model,
        "construction_path": effective.construction_path,
        "jaw": effective.jaw,
        "gingival_offset_mm": effective.gingival_offset_mm,
        # READY implies a declaration (the ladder's construction), so this lookup
        # cannot miss; keyed by tooth-as-string — the wire is JSON either way
        "variants": {str(view.tooth): session.sites[str(view.tooth)].declared_variant
                     for view in sites},
        # Sites that exist because a HUMAN marked them (2026-07-28). Only the marked
        # ones appear: a detected site's centre still comes from the case, and sending
        # a redundant copy would invite the two drifting apart.
        "marked_centers": {
            str(view.tooth): session.sites[str(view.tooth)].marked_center
            for view in sites
            if session.sites[str(view.tooth)].marked_center is not None
        },
        # THE RIM BORDER-POINTS INTAKE AID (§10-AL), threaded beside the centres
        # for the same reason and the same shape — only sites holding any appear.
        # NOT YET CONSUMED past the wire: ``bff.ports.worker.InProcessWorker.
        # _selection`` reads named keys off this dict into ``RunSelection``, which
        # carries no ``rim_points`` field today (nor does ``application.run.
        # ConfirmedSite``'s own rim_points, fed elsewhere from the CASE's curated
        # ``sites.json`` — see that module's docstring). Consuming this key is a
        # worker-source change (out of this slice's scope, which is BFF-only) —
        # the plan's own §10-AL scoping is intake-capture-only regardless, so this
        # key exists to be forward-compatible with a future worker slice, never a
        # promise that it seats anything today.
        "rim_points": {
            str(view.tooth): session.sites[str(view.tooth)].rim_points
            for view in sites
            if session.sites[str(view.tooth)].rim_points is not None
        },
        # PER-SITE RELIEF OVERRIDES (§10-B/C): each site's own ask rides beside
        # the case-level value it overrides
        "site_reliefs": _site_reliefs_of(session),
        # THE OPERATOR'S ALIGNMENT EVIDENCE (§10-AD): every persisted mark/pairs/
        # best-fit rides into the run so the automation's pass is followed by the
        # same re-apply the tools performed — an adjustment must survive the re-run
        # that used to discard it. Only sites holding any appear, like the centres.
        "alignment_evidence": {
            str(view.tooth): [e.model_dump()
                              for e in session.sites[
                                  str(view.tooth)].alignment_evidence]
            for view in sites
            if session.sites[str(view.tooth)].alignment_evidence
        },
    }


def _withdraw_queued_receipt(store: SessionStore, case_id: str, run_id: str) -> None:
    """COMPENSATION (the 5c crash-path fix — the verification refuted claim 2 here):
    the claim persisted a ``queued`` receipt, and no verdict can land — ``submit``
    raised (the run-dir collision), the adapter reported FAILED (a crash inside the
    physics), or the landing itself refused. Left in place, that receipt wedges the
    case FOREVER: every later POST sees "a run is already in flight", and no reset
    boundary is obliged to fire (the equality guards make identical re-writes inert,
    so the only escape regressed the operator's real reviews). So the receipt is
    WITHDRAWN — guarded: only if it is still OURS and still ``queued``, because a
    rival's newer receipt or a landed verdict must never be clobbered by cleanup.
    Best-effort by design: if even this tiny mutation loses the CAS race twice, the
    ORIGINAL failure still propagates — masking it with a cleanup error would hide
    the actual cause — and the next POST's claim re-judges whatever is really there."""
    def clear(session: CaseSession) -> None:
        run = session.run
        if run is not None and run.job_id == run_id and run.state == "queued":
            clear_current_run(session)
            # a run that vanishes with no verdict is exactly the thing an operator
            # later cannot explain — the narrative says the receipt was withdrawn
            record_activity(session, ACT_RUN_WITHDRAWN,
                            f"run {run_id} reached no verdict — its queued receipt "
                            f"was withdrawn so the case stays runnable")

    try:
        _mutate_session(store, case_id, clear)
    except Exception:
        pass


@router.post("/{case_id}/run", response_model=CaseSessionDetail)
def run_case_action(case_id: str, request: Request) -> CaseSessionDetail:
    """Fire the full authorized run (plan §7 slice 5c) — body-less, like detect and
    preview: the selection it runs is the SESSION's own acts, so there is nothing a
    client could claim with. Everything is on worker-side (product, QC, confidence,
    package — plan §1.2: the worker emits at run time; what gates later is
    DISCLOSURE), landing in the immutable ``runs/<run_id>/`` directory.

    Three mutations' worth of honesty in two: the receipt (state ``queued``)
    persists INSIDE a CAS mutation that re-judges the gate on every attempt; the
    port then runs the physics (the in-process adapter is synchronous — phase 2
    swaps the adapter, not this route); the LANDING persists inside a second CAS
    mutation that refuses (409) when the current-run pointer moved underneath the
    multi-second run — the reset boundaries clear that pointer on any rival
    system/declaration/choices change, so stale physics can never land. Verdicts
    map onto the ladder here: guidance ``ready`` holds the rung; anything else is
    the flag event — its first legitimate writer. A pipeline refusal lands as
    state ``refused`` with the words verbatim (a first-class outcome, not an
    error): the response is still the whole detail, and the words ride on
    ``session.run_refusal``."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)
    worker: WorkerPort = request.app.state.worker
    run_id = _mint_run_id()
    submitted: Dict[str, dict] = {}

    def claim(session: CaseSession) -> None:
        if session.run is not None and session.run.state in ("queued", "running"):
            raise HTTPException(409, f"a run is already in flight for case "
                                     f"{case_id!r} — wait for it to finish; its "
                                     f"receipt is on the session")
        submitted["selection"] = _authorized_selection(case, case_id, session)
        session.run = RunSession(job_id=run_id, run_id=run_id, state="queued")
        # a NEW run's fork has not been faced: the previous decision was made over
        # verdicts this run is about to replace (client 2026-07-27's fork, keyed to
        # the run — see session.AdjustDecisionRecord)
        session.adjust_decision = None
        # NOR HAS ITS VERDICT BEEN RE-ACKNOWLEDGED (client ruling 2026-08-02): a
        # done run may be re-authorized directly, with no reset boundary in
        # between, so ``clear_current_run`` never fires on this path — this is the
        # one other call site ``clear_exception_intents`` names in its own
        # docstring. Every drafted acknowledgment was given over the OLD run's
        # rows; the new one may flag the same tooth for a different reason, and the
        # stale draft must not silently pre-fill against a verdict nobody has seen.
        clear_exception_intents(session)
        record_activity(session, ACT_RUN_AUTHORIZED,
                        f"run {run_id} authorized over "
                        f"{len(submitted['selection']['variants'])} reviewed site"
                        f"{'' if len(submitted['selection']['variants']) == 1 else 's'}")

    _mutate_session(store, case_id, claim)
    # From here on a ``queued`` receipt is on disk, and EVERY exit that cannot land
    # a verdict must withdraw it (the except below) — an abandoned queued receipt
    # is a wedged case: 409 forever, no reset boundary obliged to fire (the 5c
    # crash-path fix; the verification refuted exactly this hole).
    try:
        job_id = worker.submit(case_id,
                               {"run_id": run_id, "selection": submitted["selection"]})
        outcome = worker.status(job_id)
        if outcome.state is JobState.FAILED:
            # A crash is an ERROR, not a verdict: REFUSED lands as a first-class
            # outcome in the pipeline's own words, but FAILED means the physics
            # never reached an answer — served as a 500 carrying the crash's words,
            # while the except withdraws the receipt so the case stays runnable.
            raise HTTPException(500, f"the run crashed before reaching a verdict — "
                                     f"{outcome.error}; the queued receipt was "
                                     f"withdrawn, so re-firing mints a fresh run")

        def land(session: CaseSession) -> None:
            # the pointer guards the OPERATOR acts: every reset boundary clears it,
            # so an intact pointer means no system/declaration/choices change landed
            # mid-run. The effective FALLBACKS (suggestions, the standing default)
            # have no boundary — their drift is refused at the authorized gate by
            # the seated-selection check (the 2026-07-28 finding), and mid-run they
            # cannot move under this route because the case record is read once per
            # request (one snapshot end to end). Phase-2's async landing re-opens
            # that window and must re-judge the seats at landing time (plan §3).
            if session.run is None or session.run.job_id != job_id:
                raise HTTPException(409, f"case {case_id!r} changed while the run was "
                                         f"computing — the run's artifacts remain under "
                                         f"its run directory as history, but they no "
                                         f"longer describe the current declarations; "
                                         f"re-read the case")
            if outcome.state is JobState.REFUSED:
                session.run = RunSession(job_id=job_id, run_id=run_id, state="refused",
                                         refusal=outcome.refusal)
                record_activity(session, ACT_RUN_REFUSED,
                                f"run {run_id} refused — {outcome.refusal}")
                return
            summary = worker.result(job_id)
            session.run = RunSession(
                job_id=job_id, run_id=run_id, state="done", summary=summary,
                package_files=[str(n) for n in (summary.get("package_files") or [])])
            for row in summary.get("sites") or []:
                site = session.sites.get(str(row.get("tooth")))
                if site is None:
                    continue   # a row for a site the session no longer tracks
                level = (row.get("guidance") or {}).get("level")
                if level != "ready":
                    # "attention"/"action-needed": the run's evidence flags the site —
                    # the ladder's fork (plan §2), through the machine like every move
                    site.status = status.flag(site.status)
            rows = summary.get("sites") or []
            flagged = [r for r in rows
                       if (r.get("guidance") or {}).get("level") != "ready"]
            record_activity(
                session, ACT_RUN_LANDED,
                f"run {run_id} completed — verdicts written for {len(rows)} site"
                f"{'' if len(rows) == 1 else 's'}"
                + (f", {len(flagged)} flagged" if flagged else ", none flagged"))

        try:
            session = _mutate_session(store, case_id, land)
        except status.IllegalTransition as exc:
            raise HTTPException(422, str(exc))
    except Exception:
        # No verdict landed: submit raised (collision/adapter bug), the worker
        # crashed (the FAILED→500 above), or the landing refused — including the
        # mid-run-rival 409, where the withdrawal's own guard (ours AND still
        # "queued") makes it a no-op because the rival already moved the pointer.
        _withdraw_queued_receipt(store, case_id, run_id)
        raise
    return _detail(case, session, settings)


# --- the Delivery-vs-Skip fork (client 2026-07-27) --------------------------------------

@router.post("/{case_id}/adjust-decision", response_model=CaseSessionDetail)
def post_adjust_decision(case_id: str, body: AdjustDecisionIn,
                         request: Request) -> CaseSessionDetail:
    """Record which way the operator took Declare's fork — "Skip adjustments" or
    "Adjust the fits" (client: "Skipping adjust should be optional we should have
    two options one to skip and another to delivery — Delivery vs Skip
    Adjustments").

    AN ACT, NOT A GATE, and the distinction is the whole design:

      - it moves no site and touches no run; ``domain/flow.ts`` reachability never
        reads it, so recording "skip" does NOT close Adjust — the operator may walk
        straight back into it, and a later decision REPLACES this one (newest act
        wins, the slice-8 rule).
      - it is EVIDENCE, and it is SHOWN: the decision word rides into the
        confirmation's bundle (bff/evidence.py) AND onto the assurance projection
        the operator reads before signing (``AssuranceView.adjustments``). Sealing
        it satisfies only half the standing directive — that when Adjust is not
        surfaced the assurance must still show what was done — because a hash shows
        nobody anything.

    Refuses 422 unless there is something to decide ABOUT: a done current run, and
    every site carrying a verdict (ready or flagged) — a site still climbing has no
    fit to skip or rework. Judged INSIDE the mutation (25604e7's rule: a rival
    change mid-flight must be re-judged, never re-applied from a stale verdict);
    keyed to the run, which the reset boundaries clear beneath it."""
    settings, store = _context(request)
    case = _case_or_404(settings, case_id)

    def apply(session: CaseSession) -> None:
        run = session.run
        if run is None or run.state != "done" or run.summary is None:
            raise HTTPException(422, f"there is nothing to decide about yet — case "
                                     f"{case_id!r} has no completed current run, and "
                                     f"the fork is a choice about ITS verdicts")
        unresolved = [v for v in _site_views(case, session)
                      if v.status not in (SiteStatus.READY.value,
                                          SiteStatus.FLAGGED.value)]
        if unresolved:
            raise HTTPException(422, "every site needs its verdict before the fork — "
                                     "still climbing: "
                                     + ", ".join(f"tooth {v.tooth} ({v.status})"
                                                 for v in unresolved))
        session.adjust_decision = AdjustDecisionRecord(
            decision=body.decision, at=_now_iso(),
            run_id=run.run_id or run.job_id)
        record_activity(session, ACT_ADJUST_DECISION,
                        f"the fork was taken: {body.decision!r} — recorded over run "
                        f"{run.run_id or run.job_id}")

    session = _mutate_session(store, case_id, apply)
    return _detail(case, session, settings)


@router.get("/{case_id}/run", response_model=RunView)
def case_run(case_id: str, request: Request) -> RunView:
    """The CURRENT run's persisted facts (Adjust's and Deliver's read surface). 404
    while no current run exists — including after a reset boundary cleared the
    pointer: the old run's directory is history on disk, not a servable present."""
    settings, store = _context(request)
    _case_or_404(settings, case_id)
    session = store.load(case_id)
    run = session.run
    if run is None:
        raise HTTPException(404, f"case {case_id!r} has no current run — Declare "
                                 f"authorizes one when every site is reviewed")
    summary = run.summary or {}
    return RunView(
        run_id=run.run_id or run.job_id, job_id=run.job_id, state=run.state,
        refusal=run.refusal, summary=run.summary,
        sites=list(summary.get("sites") or []),
        package_files=list(run.package_files),
    )
