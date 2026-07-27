"""Carrier for one recovered implant — the unit the gate and report consume."""
from __future__ import annotations

from dataclasses import dataclass

from case_prep.domain.confidence import ConfidenceScore
from case_prep.domain.geometry import RigidTransform
from case_prep.domain.poses import Pose6DoF, Retention


@dataclass(frozen=True)
class RegisteredImplant:
    tooth: int
    retention: Retention
    scan_body_type: str
    pose: Pose6DoF
    confidence: ConfidenceScore
    transform: RigidTransform  # recovered library-local -> world transform (for baking pose into geometry)
