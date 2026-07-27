"""Held-out ground truth. The pipeline NEVER imports or reads this; only the
metrics/report layer compares against it. Keeping it a distinct type enforces
that separation (no answer leakage into registration)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from case_prep.domain.poses import Retention


class ImplantTruth(BaseModel):
    tooth: int
    scan_body_type: str
    retention: Retention
    position: List[float]  # platform point, world frame (mm)
    axis: List[float]  # unit implant axis, world frame
    clocking_degrees: Optional[float] = None  # None for cement-retained


class GroundTruth(BaseModel):
    poses: List[ImplantTruth]

    def by_tooth(self, tooth: int) -> ImplantTruth:
        for p in self.poses:
            if p.tooth == tooth:
                return p
        raise KeyError(f"no ground truth for tooth {tooth}")
