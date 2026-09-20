"""Deterministic vs Intelligence alignment techniques.

Both strategies share one physics path — ``case_prep.application.adjust`` — and
the same ``assemble_site_signals`` envelope. They differ only in HOW they walk
that seam:

* **deterministic** — the pipeline's own one-shot refinement (``best_fit_site``)
  with no agent loop. The full signal set is read out around that single act.
* **intelligence** — drive the MCP tool surface (READ every signal tool, DRY_RUN
  best-fit, then COMMIT best-fit or any operator-supplied act). It never invents
  scan points, pairs, or metrics; landmarks are proposals, not correspondences.

``apply=False`` is the DRY_RUN of either strategy: signals + (for Intelligence)
a measured best-fit, nothing written.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .adjust import (AdjustInvalid, AdjustOutcome, AdjustRefused, AlreadyOptimal,
                     Correspondence, align_to_correspondence, align_to_mark,
                     best_fit_site, clock_landmarks, load_site, rotate_site,
                     seated_payload)
from .cases import CaseRecord
from .signals import SIGNAL_GROUPS, assemble_site_signals, outcome_to_dict

MODE_DETERMINISTIC = "deterministic"
MODE_INTELLIGENCE = "intelligence"
TECHNIQUE_MODES = (MODE_DETERMINISTIC, MODE_INTELLIGENCE)

TOOL_READ = "READ"
TOOL_DRY_RUN = "DRY_RUN"
TOOL_COMMIT = "COMMIT"


@dataclass
class ToolTrace:
    """One MCP-shaped tool call the technique actually made."""

    name: str
    classification: str
    ok: bool
    detail: str
    result: Optional[Dict[str, Any]] = None
    refusal: Optional[Dict[str, Any]] = None


@dataclass
class TechniqueAsk:
    """What the operator asked the technique to do.

    Extra acts (rotation / mark / pairs) are OPERATOR FACTS. Intelligence will
    walk them through the matching COMMIT tools. Deterministic ignores them —
    its one act is the pipeline refinement — so a pair the human did not mean
    to feed the agent loop cannot silently become a deterministic fit.
    """

    mode: str
    apply: bool = True
    matching_diameter_mm: float = 0.3
    step_deg: Optional[float] = None
    reset: bool = False
    scan_point: Optional[Sequence[float]] = None
    pairs: Optional[List[Correspondence]] = None


@dataclass
class TechniqueResult:
    mode: str
    status: str
    detail: str
    signals_before: Dict[str, Any]
    signals_after: Dict[str, Any]
    outcome: Optional[AdjustOutcome] = None
    refusals: List[Dict[str, Any]] = field(default_factory=list)
    trace: List[ToolTrace] = field(default_factory=list)
    proposals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "detail": self.detail,
            "signals_before": self.signals_before,
            "signals_after": self.signals_after,
            "outcome": outcome_to_dict(self.outcome),
            "refusals": list(self.refusals),
            "trace": [
                {
                    "name": step.name,
                    "classification": step.classification,
                    "ok": step.ok,
                    "detail": step.detail,
                    "result": step.result,
                    "refusal": step.refusal,
                }
                for step in self.trace
            ],
            "proposals": dict(self.proposals),
            "signal_groups": list(SIGNAL_GROUPS),
        }


def _refusal_payload(exc: Exception) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "kind": type(exc).__name__,
        "message": str(exc),
    }
    if isinstance(exc, AlreadyOptimal):
        payload["kind"] = "already_optimal"
        payload["matching_diameter_mm"] = exc.matching_diameter_mm
        payload["suggested_diameter_mm"] = exc.suggested_diameter_mm
    elif isinstance(exc, AdjustRefused):
        payload["kind"] = "refused"
    elif isinstance(exc, AdjustInvalid):
        payload["kind"] = "invalid"
    return payload


def _read_landmarks(case: CaseRecord, run_dir: Path, tooth: int,
                    trace: List[ToolTrace]) -> tuple[Optional[List[dict]], Optional[str]]:
    try:
        items = clock_landmarks(load_site(case, run_dir, tooth).template)
    except (AdjustInvalid, AdjustRefused, OSError, ValueError, RuntimeError) as exc:
        trace.append(ToolTrace(
            name="get_landmarks", classification=TOOL_READ, ok=False,
            detail=str(exc), refusal=_refusal_payload(exc)))
        return None, str(exc)
    trace.append(ToolTrace(
        name="get_landmarks", classification=TOOL_READ, ok=True,
        detail=f"{len(items)} landmarks", result={"count": len(items)}))
    return items, None


def _read_seated(case: CaseRecord, run_dir: Path, tooth: int,
                 trace: List[ToolTrace]) -> tuple[Optional[dict], Optional[str]]:
    try:
        payload = seated_payload(case, run_dir, tooth)
    except (AdjustInvalid, AdjustRefused, OSError, ValueError, RuntimeError) as exc:
        trace.append(ToolTrace(
            name="get_seated", classification=TOOL_READ, ok=False,
            detail=str(exc), refusal=_refusal_payload(exc)))
        return None, str(exc)
    stats = (payload or {}).get("stats") if isinstance(payload, dict) else None
    trace.append(ToolTrace(
        name="get_seated", classification=TOOL_READ, ok=True,
        detail="seated pose", result={"stats": stats}))
    return payload, None


def _signals(
    case: CaseRecord,
    run_dir: Path,
    tooth: int,
    row: Dict[str, Any],
    trace: List[ToolTrace],
    *,
    walk_reads: bool,
    outcome: Optional[AdjustOutcome] = None,
) -> Dict[str, Any]:
    landmarks: Optional[List[dict]] = None
    seated: Optional[dict] = None
    landmarks_error = None
    seated_error = None
    if walk_reads:
        landmarks, landmarks_error = _read_landmarks(case, run_dir, tooth, trace)
        seated, seated_error = _read_seated(case, run_dir, tooth, trace)
        envelope = assemble_site_signals(
            row, landmarks=landmarks, seated=seated, outcome=outcome,
            landmarks_error=landmarks_error, seated_error=seated_error)
        trace.append(ToolTrace(
            name="get_site_signals", classification=TOOL_READ, ok=True,
            detail="full taxonomy",
            result={"group_names": list(envelope["group_names"])}))
        trace.append(ToolTrace(
            name="get_acceptance", classification=TOOL_READ, ok=True,
            detail=str((envelope["groups"]["acceptance"] or {}).get("overall_band")),
            result={"overall_band": envelope["groups"]["acceptance"]["overall_band"]}))
        return envelope
    return assemble_site_signals(row, outcome=outcome)


def _call_best_fit(
    case: CaseRecord,
    run_dir: Path,
    tooth: int,
    diameter: float,
    apply: bool,
    trace: List[ToolTrace],
) -> tuple[Optional[AdjustOutcome], Optional[Dict[str, Any]]]:
    name = "commit_best_fit" if apply else "dry_run_best_fit"
    klass = TOOL_COMMIT if apply else TOOL_DRY_RUN
    try:
        outcome = best_fit_site(
            case, run_dir, tooth,
            matching_diameter_mm=diameter, apply=apply)
    except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
        payload = _refusal_payload(exc)
        trace.append(ToolTrace(
            name=name, classification=klass, ok=isinstance(exc, AlreadyOptimal),
            detail=str(exc), refusal=payload))
        return None, payload
    trace.append(ToolTrace(
        name=name, classification=klass, ok=True,
        detail=outcome.detail, result=outcome_to_dict(outcome)))
    return outcome, None


def _commit_operator_acts(
    case: CaseRecord,
    run_dir: Path,
    tooth: int,
    ask: TechniqueAsk,
    trace: List[ToolTrace],
) -> tuple[Optional[AdjustOutcome], List[Dict[str, Any]]]:
    """Intelligence-only: COMMIT tools for facts the operator actually supplied."""
    last: Optional[AdjustOutcome] = None
    refusals: List[Dict[str, Any]] = []

    if ask.reset or ask.step_deg is not None:
        try:
            last = rotate_site(
                case, run_dir, tooth,
                step_deg=float(ask.step_deg or 0.0), reset=ask.reset)
            trace.append(ToolTrace(
                name="commit_rotation", classification=TOOL_COMMIT, ok=True,
                detail=last.detail, result=outcome_to_dict(last)))
        except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
            payload = _refusal_payload(exc)
            refusals.append(payload)
            trace.append(ToolTrace(
                name="commit_rotation", classification=TOOL_COMMIT, ok=False,
                detail=str(exc), refusal=payload))

    if ask.scan_point is not None:
        try:
            last = align_to_mark(case, run_dir, tooth, ask.scan_point)
            trace.append(ToolTrace(
                name="commit_mark_trench", classification=TOOL_COMMIT, ok=True,
                detail=last.detail, result=outcome_to_dict(last)))
        except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
            payload = _refusal_payload(exc)
            refusals.append(payload)
            trace.append(ToolTrace(
                name="commit_mark_trench", classification=TOOL_COMMIT, ok=False,
                detail=str(exc), refusal=payload))

    if ask.pairs:
        try:
            last = align_to_correspondence(case, run_dir, tooth, ask.pairs)
            trace.append(ToolTrace(
                name="commit_fit_by_points", classification=TOOL_COMMIT, ok=True,
                detail=last.detail, result=outcome_to_dict(last)))
        except (AdjustInvalid, AdjustRefused, AlreadyOptimal) as exc:
            payload = _refusal_payload(exc)
            refusals.append(payload)
            trace.append(ToolTrace(
                name="commit_fit_by_points", classification=TOOL_COMMIT, ok=False,
                detail=str(exc), refusal=payload))
    return last, refusals


def run_technique(
    case: CaseRecord,
    run_dir: Path,
    tooth: int,
    row: Dict[str, Any],
    ask: TechniqueAsk,
) -> TechniqueResult:
    if ask.mode not in TECHNIQUE_MODES:
        raise AdjustInvalid(
            f"mode must be one of {list(TECHNIQUE_MODES)}, got {ask.mode!r}")

    walk_reads = ask.mode == MODE_INTELLIGENCE
    trace: List[ToolTrace] = []
    refusals: List[Dict[str, Any]] = []
    before = _signals(case, run_dir, tooth, row, trace, walk_reads=walk_reads)
    proposals = {
        "landmarks": before["groups"]["landmarks"].get("items") or [],
        "note": (
            "landmarks are the part-half AUTO-MARK proposal; Intelligence will "
            "not invent the scan-half of a pair"
        ),
    }

    outcome: Optional[AdjustOutcome] = None
    if ask.mode == MODE_DETERMINISTIC:
        outcome, refusal = _call_best_fit(
            case, run_dir, tooth, ask.matching_diameter_mm, ask.apply, trace)
        if refusal is not None:
            refusals.append(refusal)
            status = (
                "already_optimal" if refusal.get("kind") == "already_optimal"
                else "refused"
            )
            after = _signals(
                case, run_dir, tooth, row, trace, walk_reads=False, outcome=None)
            return TechniqueResult(
                mode=ask.mode, status=status,
                detail=refusal.get("message") or status,
                signals_before=before, signals_after=after,
                outcome=None, refusals=refusals, trace=trace,
                proposals=proposals)
        status = "applied" if (outcome is not None and outcome.applied) else "measured"
        detail = outcome.detail if outcome is not None else status
    else:
        measured, refusal = _call_best_fit(
            case, run_dir, tooth, ask.matching_diameter_mm, apply=False, trace=trace)
        if refusal is not None:
            refusals.append(refusal)
            if refusal.get("kind") == "already_optimal":
                after = _signals(
                    case, run_dir, tooth, row, trace, walk_reads=True)
                return TechniqueResult(
                    mode=ask.mode, status="already_optimal",
                    detail=refusal.get("message") or "already optimal",
                    signals_before=before, signals_after=after,
                    outcome=None, refusals=refusals, trace=trace,
                    proposals=proposals)
            # a dry-run refusal still lets operator-supplied acts through
            outcome = None
        else:
            outcome = measured
            if ask.apply and measured is not None:
                committed, commit_refusal = _call_best_fit(
                    case, run_dir, tooth, ask.matching_diameter_mm,
                    apply=True, trace=trace)
                if commit_refusal is not None:
                    refusals.append(commit_refusal)
                elif committed is not None:
                    outcome = committed

        if ask.apply:
            extra, extra_refusals = _commit_operator_acts(
                case, run_dir, tooth, ask, trace)
            refusals.extend(extra_refusals)
            if extra is not None:
                outcome = extra

        if outcome is not None and outcome.applied:
            status = "applied"
            detail = outcome.detail
        elif refusals and all(r.get("kind") != "already_optimal" for r in refusals) and outcome is None:
            status = "refused"
            detail = refusals[0].get("message") or "refused"
        else:
            status = "measured"
            detail = (
                outcome.detail if outcome is not None
                else "Intelligence read the full tool surface; nothing committed"
            )

    after = _signals(
        case, run_dir, tooth, row, trace,
        walk_reads=walk_reads, outcome=outcome)
    return TechniqueResult(
        mode=ask.mode, status=status, detail=detail,
        signals_before=before, signals_after=after,
        outcome=outcome, refusals=refusals, trace=trace,
        proposals=proposals)
