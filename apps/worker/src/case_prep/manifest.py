"""The case manifest (case.json) — the structured intake the portal captures,
serialized into the pipeline. Mirrors schema.sql implant_sites/cases so a real
portal case maps straight in. This is the decisive simplification: because the
declaration says which scan-body library to load and how many to find, detection
collapses from 'identify unknown objects' to 'locate N known objects'.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, field_validator, model_validator

from case_prep.domain.confidence import CaseMode
from case_prep.domain.poses import Retention


class SiteSpec(BaseModel):
    """One declared implant site (mirrors an implant_sites row)."""

    tooth: int
    scan_body_type: str
    retention: Retention


class CaseManifest(BaseModel):
    case_ref: str  # opaque shop label; never PII
    scan_file: str
    implant_sites: List[SiteSpec]
    tooth_notation: str = "universal"
    # FAIL-CLOSED: a case that does not declare its data class runs in advisory mode (the gate
    # never auto-approves; see domain.confidence.CaseMode). Only writers whose data class the
    # thresholds were calibrated on (today: the synthetic generator) set VALIDATED explicitly.
    mode: CaseMode = CaseMode.ADVISORY

    @field_validator("implant_sites")
    @classmethod
    def _non_empty(cls, sites: List[SiteSpec]) -> List[SiteSpec]:
        if not sites:
            raise ValueError("a case must declare at least one implant site")
        return sites

    @model_validator(mode="after")
    def _unique_teeth(self) -> "CaseManifest":
        teeth = [s.tooth for s in self.implant_sites]
        if len(set(teeth)) != len(teeth):
            raise ValueError("duplicate tooth numbers in implant_sites")
        return self

    @property
    def declared_count(self) -> int:
        return len(self.implant_sites)
