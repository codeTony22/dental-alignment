"""Multi-implant geometric consistency — a conservative, explainable cross-implant check.

Feeds the clinical-safety gate's ``multi_implant_consistent`` signal (previously count-match
only). Deliberately catches ONLY impossible or beyond-protocol geometry:

  * platform spacing below the physical minimum — two implants cannot occupy the same bone
    (clinical implant-to-implant minimum is ~3 mm plus fixture radii);
  * pairwise axis divergence beyond any accepted protocol — tilted-implant protocols
    (e.g. All-on-4) run to ~45°, so the threshold sits well above that.

Legitimate clinical variation must never flag here; a missed inconsistency is caught by the
human review that advisory mode already routes real cases to.
"""
from __future__ import annotations

from itertools import combinations
from math import acos, degrees
from typing import List, Sequence, Tuple

import numpy as np

from case_prep.domain.poses import Pose6DoF

MIN_PLATFORM_SPACING_MM = 4.0   # ~3mm bone minimum + fixture radii; below this is impossible
MAX_AXIS_DIVERGENCE_DEG = 60.0  # All-on-4 tilts reach ~45°; beyond 60° no protocol applies


def multi_implant_consistency(
    poses: Sequence[Pose6DoF],
    min_spacing_mm: float = MIN_PLATFORM_SPACING_MM,
    max_axis_divergence_deg: float = MAX_AXIS_DIVERGENCE_DEG,
) -> Tuple[bool, List[str]]:
    """Check every implant pair; returns (consistent, explainable reasons for each violation)."""
    reasons: List[str] = []
    for (i, a), (j, b) in combinations(enumerate(poses), 2):
        spacing = float(np.linalg.norm(np.asarray(a.position) - np.asarray(b.position)))
        if spacing < min_spacing_mm:
            reasons.append(
                f"implants {i} and {j}: platform spacing {spacing:.1f}mm < "
                f"physical minimum {min_spacing_mm:.1f}mm")
            continue  # overlapping fixtures make the axis comparison meaningless
        cos = float(np.clip(np.dot(a.axis.direction, b.axis.direction), -1.0, 1.0))
        divergence = degrees(acos(cos))
        if divergence > max_axis_divergence_deg:
            reasons.append(
                f"implants {i} and {j}: axis divergence {divergence:.0f}° > "
                f"protocol maximum {max_axis_divergence_deg:.0f}°")
    return (not reasons, reasons)
