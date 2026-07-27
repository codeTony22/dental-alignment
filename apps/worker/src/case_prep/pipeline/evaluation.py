"""Evaluate a CaseResult against held-out ground truth.

This is the only module that reads ground_truth.json — keeping the comparison out of
the pipeline guarantees no answer leakage into registration. Recovered implants are
matched to truth by nearest platform position, so accuracy is independent of the
tooth-labeling heuristic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from case_prep.domain.geometry import Axis
from case_prep.domain.ground_truth import GroundTruth
from case_prep.domain.metrics import (
    ClinicalTolerance,
    ImplantOutcome,
    axis_error_deg,
    clear_rate,
    clocking_error_deg,
    false_confidence_rate,
    position_error_mm,
    within_tolerance,
)
from case_prep.pipeline.orchestrator import CaseResult


def load_ground_truth(case_dir) -> GroundTruth:
    return GroundTruth.model_validate_json((Path(case_dir) / "ground_truth.json").read_text())


@dataclass(frozen=True)
class ImplantEvaluation:
    tooth: int
    retention: str
    position_error_mm: float
    axis_error_deg: float
    clocking_error_deg: Optional[float]
    within_tolerance: bool
    gate_passed: bool
    gate_reasons: List[str]
    gate_would_pass: Optional[bool] = None  # advisory shadow verdict (None when validated)


@dataclass(frozen=True)
class CaseEvaluation:
    case_ref: str
    count_match: bool
    clear_rate: float
    false_confidence_rate: float
    implants: List[ImplantEvaluation]
    # ADVISORY cases: nothing auto-passes, so false_confidence_rate structurally reads 0% while
    # measuring nothing. This SHADOW rate is the same metric computed over what the gate WOULD
    # have passed — the number the advisory audit loop exists to collect. None when the case
    # ran validated (not applicable).
    shadow_false_confidence_rate: Optional[float] = None


def evaluate_case(
    result: CaseResult, ground_truth: GroundTruth, tol: ClinicalTolerance
) -> CaseEvaluation:
    evaluations: List[ImplantEvaluation] = []
    outcomes: List[ImplantOutcome] = []
    shadow_outcomes: List[ImplantOutcome] = []  # advisory: the gate's would-have verdicts

    # 1:1 greedy nearest assignment: each ground-truth implant is consumed at most once,
    # so two recovered poses cannot both match one truth (which would hide a wrong pose
    # and deflate the false-confidence rate — the metric this whole spike defends).
    remaining = list(ground_truth.poses)
    for reg, decision in result.gated:
        if not remaining:
            break  # more recovered poses than truths (over-detection) — nothing left to match
        pos = np.asarray(reg.pose.position)
        j = int(np.argmin([np.linalg.norm(np.asarray(t.position) - pos) for t in remaining]))
        truth = remaining.pop(j)

        pos_err = position_error_mm(reg.pose.position, truth.position)
        axis_err = axis_error_deg(reg.pose.axis, Axis.from_vector(truth.axis))
        clock_err = clocking_error_deg(reg.pose.clocking_degrees, truth.clocking_degrees)
        ok = within_tolerance(pos_err, axis_err, clock_err, tol)

        evaluations.append(
            ImplantEvaluation(
                tooth=reg.tooth,
                retention=reg.retention.value,
                position_error_mm=pos_err,
                axis_error_deg=axis_err,
                clocking_error_deg=clock_err,
                within_tolerance=ok,
                gate_passed=decision.passed,
                gate_reasons=list(decision.reasons),
                gate_would_pass=decision.would_pass,
            )
        )
        outcomes.append(ImplantOutcome(passed=decision.passed, within_tolerance=ok))
        if decision.advisory:
            shadow_outcomes.append(ImplantOutcome(passed=bool(decision.would_pass),
                                                  within_tolerance=ok))

    return CaseEvaluation(
        case_ref=result.case_ref,
        count_match=result.count_match,
        clear_rate=clear_rate(outcomes),
        false_confidence_rate=false_confidence_rate(outcomes),
        implants=evaluations,
        shadow_false_confidence_rate=(
            false_confidence_rate(shadow_outcomes) if shadow_outcomes else None),
    )
