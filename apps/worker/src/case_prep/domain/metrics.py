"""Accuracy metrics and the aggregate go/no-go rates.

Per-implant error is measured against held-out ground truth; the aggregate
clear-rate and false-confidence-rate are the numbers the design docs say decide
whether Phase 2 pays back (system-design 6.8).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from case_prep.domain.geometry import Axis


def position_error_mm(recovered, truth) -> float:
    a = np.asarray(recovered, dtype=float).reshape(3)
    b = np.asarray(truth, dtype=float).reshape(3)
    return float(np.linalg.norm(a - b))


def axis_error_deg(recovered: Axis, truth: Axis) -> float:
    return recovered.angle_to(truth)


def clocking_error_deg(recovered: Optional[float], truth: Optional[float]) -> Optional[float]:
    """Circular clocking error in [0, 180]. None when either side has no clocking
    (cement-retained), so it is excluded from tolerance checks."""
    if recovered is None or truth is None:
        return None
    diff = abs(recovered - truth) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


@dataclass(frozen=True)
class ClinicalTolerance:
    """The clinical accuracy target the report measures against (distinct from the
    deterministic CI regression bounds)."""

    position_mm: float
    axis_deg: float
    clocking_deg: float


def within_tolerance(
    pos_mm: float,
    axis_deg: float,
    clocking_deg: Optional[float],
    tol: ClinicalTolerance,
) -> bool:
    if pos_mm > tol.position_mm:
        return False
    if axis_deg > tol.axis_deg:
        return False
    if clocking_deg is not None and clocking_deg > tol.clocking_deg:
        return False
    return True


@dataclass(frozen=True)
class ImplantOutcome:
    """What the gate decided (passed) vs what was actually true (within_tolerance)."""

    passed: bool
    within_tolerance: bool


def clear_rate(outcomes: List[ImplantOutcome]) -> float:
    """Fraction of implants the gate auto-passed."""
    if not outcomes:
        return 0.0
    return sum(o.passed for o in outcomes) / len(outcomes)


def false_confidence_rate(outcomes: List[ImplantOutcome]) -> float:
    """Of the implants that PASSED, the fraction that were actually out of tolerance.
    This is the safety-critical number — it must be near zero."""
    passed = [o for o in outcomes if o.passed]
    if not passed:
        return 0.0
    return sum(not o.within_tolerance for o in passed) / len(passed)
