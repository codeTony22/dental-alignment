"""The demo scenarios — a curated, self-checking tour of the pipeline's behaviour.

Each scenario states what it is meant to demonstrate AND an expectation the demo
asserts, so the dashboard is a *check* (green/red), not just a picture. Together they
tell the story: the easy wedge clears, full 6-DoF screw clears when captured well,
degraded scans are flagged not passed, and a count mismatch is caught.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from case_prep.adapters.synthetic import SyntheticParams
from case_prep.domain.metrics import ClinicalTolerance
from case_prep.domain.poses import Retention

# Clinical targets the demo measures against (position/axis/clocking).
CLINICAL = ClinicalTolerance(position_mm=0.2, axis_deg=2.0, clocking_deg=5.0)


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    params: SyntheticParams
    tol: ClinicalTolerance = CLINICAL
    extra_declared_teeth: Tuple[int, ...] = ()  # over-declare to force a count mismatch
    expect_min_clear: float = 0.0
    expect_max_clear: float = 1.0
    expect_max_false_confidence: float = 0.0
    expect_count_match: bool = True


SCENARIOS = [
    Scenario(
        name="Cement — clean (the easy wedge)",
        description="Cement-retained crowns need only position + axis (no clocking). The "
                    "most automatable case type and the first auto-target.",
        params=SyntheticParams(seed=4, n_implants=2, retention=Retention.CEMENT),
        expect_min_clear=1.0,
    ),
    Scenario(
        name="Screw — clean (full 6-DoF incl. clocking)",
        description="Screw-retained needs accurate rotational clocking for the screw "
                    "channel. A well-captured scan clears with confident clocking.",
        params=SyntheticParams(seed=7, n_implants=2, retention=Retention.SCREW),
        expect_min_clear=1.0,
    ),
    Scenario(
        name="Screw — degraded (safety gate)",
        description="Heavy vertex noise + 40% occlusion. Poses drift out of tolerance; the "
                    "gate MUST flag them to manual seeding, never pass them blind.",
        params=SyntheticParams(seed=7, n_implants=2, retention=Retention.SCREW,
                               noise_mm=0.4, partial_fraction=0.4),
        expect_max_clear=0.5,
    ),
    Scenario(
        name="Count mismatch (billing / safety check)",
        description="Two scan bodies present but three declared. Detection reconciles "
                    "against the declaration and flags the case rather than dropping a site.",
        params=SyntheticParams(seed=5, n_implants=2, retention=Retention.CEMENT),
        extra_declared_teeth=(31, 2, 14, 18, 30),  # runner adds the first not already present
        expect_max_clear=0.0,
        expect_count_match=False,
    ),
]
