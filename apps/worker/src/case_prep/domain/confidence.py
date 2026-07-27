"""Deterministic, retention-aware confidence gate.

The automate-or-flag decision is threshold-based (system-design 6.7): explainable
and auditable for a clinical-safety call, calibrated against ground truth in the
spike. It never silently passes a screw-retained site that lacks clocking evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from case_prep.domain.poses import Retention


class CaseMode(str, Enum):
    """Whether the gate's thresholds are validated for a case's data class.

    VALIDATED — thresholds were calibrated against ground truth for this class (today: the
    synthetic class); a gate PASS may auto-approve.
    ADVISORY — not (yet) validated for this class (real / semi-real / embedded scans, where a
    1.75 mm-wrong pose was measured passing the synthetic thresholds); the gate still runs,
    but auto-approval is disabled: every implant routes to a human and the decision the gate
    WOULD have made is logged, building the audit sample that later calibrates the gate.
    """

    VALIDATED = "validated"
    ADVISORY = "advisory"


ADVISORY_REASON = (
    "advisory mode: gate thresholds are not validated for this data class; "
    "auto-approval disabled — routed to human review"
)


@dataclass(frozen=True)
class ConfidenceScore:
    """Per-implant registration confidence signals."""

    icp_fitness: float  # inlier ratio in [0, 1]; higher is better
    inlier_rmse_mm: float  # surface residual; lower is better
    multi_implant_consistent: bool  # inter-implant geometry agrees with the declaration
    clocking_gap: Optional[float] = None  # best-vs-antipodal RMSE ratio (>=1); higher is better
    anti_rotation_residual: Optional[float] = None  # feature-alignment residual; lower is better


@dataclass(frozen=True)
class GateThresholds:
    min_fitness: float
    max_rmse_mm: float
    min_clocking_gap: float
    max_anti_rotation_residual: float


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    retention: Retention
    reasons: List[str] = field(default_factory=list)
    advisory: bool = False  # True when apply_case_mode disabled auto-approval
    would_pass: Optional[bool] = None  # shadow log: the gate's own verdict (advisory only)


def evaluate_gate(
    score: ConfidenceScore, retention: Retention, thresholds: GateThresholds
) -> GateDecision:
    """Decide PASS (auto-seed) vs FLAG (route to manual). Reasons explain every flag."""
    reasons: List[str] = []

    # Fail closed on non-finite signals: a NaN compares False against every threshold,
    # so it would otherwise slip through as a PASS. Never trust a non-finite metric.
    finite_signals = [score.icp_fitness, score.inlier_rmse_mm]
    if retention is Retention.SCREW:
        finite_signals += [score.clocking_gap, score.anti_rotation_residual]
    if any(s is not None and not math.isfinite(s) for s in finite_signals):
        reasons.append("non-finite confidence signal")

    # Position + axis gates apply to every site.
    if score.icp_fitness < thresholds.min_fitness:
        reasons.append(
            f"icp fitness {score.icp_fitness:.3f} < min {thresholds.min_fitness:.3f}"
        )
    if score.inlier_rmse_mm > thresholds.max_rmse_mm:
        reasons.append(
            f"inlier rmse {score.inlier_rmse_mm:.3f}mm > max {thresholds.max_rmse_mm:.3f}mm"
        )
    if not score.multi_implant_consistent:
        reasons.append("multi-implant consistency check failed")

    # Clocking gates apply to screw-retained sites only.
    if retention is Retention.SCREW:
        if score.clocking_gap is None or score.anti_rotation_residual is None:
            reasons.append("clocking evidence absent for screw-retained site")
        else:
            if score.clocking_gap < thresholds.min_clocking_gap:
                reasons.append(
                    f"clocking gap {score.clocking_gap:.3f} < min "
                    f"{thresholds.min_clocking_gap:.3f} (symmetry ambiguity)"
                )
            if score.anti_rotation_residual > thresholds.max_anti_rotation_residual:
                reasons.append(
                    f"anti-rotation residual {score.anti_rotation_residual:.3f} > max "
                    f"{thresholds.max_anti_rotation_residual:.3f}"
                )

    return GateDecision(passed=not reasons, retention=retention, reasons=reasons)


def apply_case_mode(decision: GateDecision, mode: CaseMode) -> GateDecision:
    """Route a gate decision through the case's safety mode.

    VALIDATED returns the decision unchanged. ADVISORY disables auto-approval — the routed
    decision never passes — while preserving the gate's own verdict in ``would_pass`` (the
    shadow measurement) and the original reasons (a real flag stays explained)."""
    if mode is CaseMode.VALIDATED:
        return decision
    return GateDecision(
        passed=False,
        retention=decision.retention,
        reasons=[*decision.reasons, ADVISORY_REASON],
        advisory=True,
        would_pass=decision.passed,
    )
