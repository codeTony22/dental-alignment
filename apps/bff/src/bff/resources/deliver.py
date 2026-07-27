"""THE DELIVER RESOURCE (plan §4 Deliver, §6; grill AM-1/AM-10/AM-11/AM-12): the
disclosure edge — the one place the BFF decides what leaves the building.

TWO CLASSES OF DISCLOSURE (AM-1, the plan's corrected FATAL), stated here because this
module enforces the boundary:

  1. EVIDENCE — the assurance summary (per-site numbers, gate and clamp words, QC
     images) — is visible BEFORE any confirmation: signing over visible evidence is
     the whole design (plan §1.4). ``GET .../assurance`` and ``GET .../runs/current/
     qc/{filename}`` are UNGATED (no operator header, no payment).
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

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from case_prep.application.cases import CaseRecord
from case_prep.domain.acceptance import evaluate_acceptance

from ..config import Settings
from ..session import CaseSession, RunSession, SessionStore
from .case_sessions import _case_or_404, _context

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


def _site_qc_images(run: RunSession, tooth: int) -> List[str]:
    """This site's QC images by the pipeline's own naming (``<case>-<tooth>-*.png``,
    qc_render.py) — the ``-<tooth>-`` segment match cannot confuse tooth 4 with 41."""
    marker = f"-{tooth}-"
    return sorted(n for n in _qc_image_names(run) if marker in n)


def _assurance_site(row: dict, session: CaseSession, run: RunSession) -> AssuranceSite:
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
        qc_images=_site_qc_images(run, tooth),
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
    sites = [_assurance_site(row, session, run)
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
