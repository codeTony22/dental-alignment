"""Case-prep orchestrator: load -> count -> localize -> register -> derive pose ->
retention-aware gate. Returns a CaseResult the report layer turns into artifacts.

Tooth labels are assigned to localized clusters by arch order (a position prior):
clusters are ordered along the arch's principal direction and zipped to the
ascending declared teeth. Accuracy is independent of this labeling — the report
matches recovered poses to ground truth by geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Tuple

import numpy as np

from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.loader import LibraryPart, load_case
from case_prep.domain.clocking import clocking_angle_deg
from case_prep.domain.confidence import GateDecision, GateThresholds, apply_case_mode, evaluate_gate
from case_prep.domain.consistency import multi_implant_consistency
from case_prep.domain.geometry import Axis, RigidTransform
from case_prep.domain.poses import Pose6DoF, Retention
from case_prep.domain.registration import RegisteredImplant

# Calibrated against synthetic ground truth at the spike's mesh resolution. The clocking
# decision is driven by min_clocking_gap (the scale-invariant best-vs-flipped ratio);
# max_anti_rotation_residual is a loose sanity bound at the target-sampling floor, not the
# primary clocking discriminator. Production tightens these on dense real scans.
DEFAULT_THRESHOLDS = GateThresholds(
    min_fitness=0.30,
    max_rmse_mm=0.30,
    min_clocking_gap=1.5,  # flipped clock must fit >=1.5x worse on the feature to trust it
    max_anti_rotation_residual=0.60,
)

# How many clusters beyond the declared count to look for, so over-detection is visible
# (and bounded — a noisy scan won't spawn unbounded ROIs/registrations).
_COUNT_SLACK = 3


@dataclass
class UnresolvedSite:
    """A declared site with no detected scan body — surfaced, never silently dropped."""
    tooth: int
    retention: Retention
    reason: str


@dataclass
class CaseResult:
    case_ref: str
    declared_count: int
    detected_count: int
    count_match: bool
    implants: List[RegisteredImplant]
    gated: List[Tuple[RegisteredImplant, GateDecision]]
    unresolved_sites: List[UnresolvedSite]


def _derive_pose(t: RigidTransform, part: LibraryPart, retention: Retention) -> Pose6DoF:
    """CONTRACT: the platform transform's TRANSLATION is fully honored; the implant axis is the
    scan body's +z — body and platform are assumed COAXIAL (true for every system in the
    current catalog). An angulated-interface system would need axis = t.rotation @
    (scan_body_to_platform.rotation @ z) instead — extend here when such a part arrives."""
    platform_local = part.scan_body_to_platform.apply([0.0, 0.0, 0.0])
    position = t.apply(platform_local)
    axis = Axis.from_vector(t.rotation @ np.array([0.0, 0.0, 1.0]))
    clocking = clocking_angle_deg(t.rotation) if retention is Retention.SCREW else None
    return Pose6DoF(position=[float(x) for x in position], axis=axis, clocking_degrees=clocking)


def _order_along_arch(locs) -> List[int]:
    """Indices of localizations ordered along the arch's principal spread direction."""
    if len(locs) <= 1:
        return list(range(len(locs)))
    centroids = np.array([l.centroid for l in locs])
    _, _, vt = np.linalg.svd(centroids - centroids.mean(axis=0), full_matrices=False)
    coord = centroids @ vt[0]
    return list(np.argsort(coord))


def run_case(case_dir, thresholds: GateThresholds = DEFAULT_THRESHOLDS) -> CaseResult:
    case = load_case(case_dir)
    declared = case.manifest.declared_count

    # Detect WITHOUT capping to the declared count, so over-/under-count is observable.
    locs = engine.localize(np.asarray(case.scan.vertices, dtype=float), declared + _COUNT_SLACK)
    detected = len(locs)
    consistent = detected == declared

    sites = sorted(case.manifest.implant_sites, key=lambda s: s.tooth)
    # Assign the declared sites to the largest detected clusters, in arch order. Any
    # surplus declared sites (under-detection) are surfaced as unresolved, not dropped.
    usable = locs[:declared]
    order = _order_along_arch(usable)
    resolved_sites = sites[: len(usable)]
    unresolved = [
        UnresolvedSite(tooth=s.tooth, retention=s.retention,
                       reason=f"no scan body detected (declared {declared}, found {detected})")
        for s in sites[len(usable):]
    ]

    registered = []
    for site, li in zip(resolved_sites, order):
        loc = usable[li]
        part = case.library[site.scan_body_type]
        transform, confidence = engine.register(loc, part.mesh, site.retention)
        registered.append((site, transform, confidence, _derive_pose(transform, part, site.retention)))

    # cross-implant signal: the declared/detected COUNT must reconcile AND the recovered
    # geometry must be physically possible (spacing) and within clinical protocol (divergence)
    geo_ok, _geo_reasons = multi_implant_consistency([r[3] for r in registered])
    cross_ok = consistent and geo_ok

    gated: List[Tuple[RegisteredImplant, GateDecision]] = []
    final: List[RegisteredImplant] = []
    for site, transform, confidence, pose in registered:
        conf = replace(confidence, multi_implant_consistent=cross_ok)
        reg = RegisteredImplant(
            tooth=site.tooth, retention=site.retention,
            scan_body_type=site.scan_body_type, pose=pose, confidence=conf,
            transform=transform,
        )
        final.append(reg)
        # the case's mode decides whether the gate may auto-approve (advisory = fail-closed
        # shadow mode for data classes the thresholds were never validated on)
        gated.append((reg, apply_case_mode(
            evaluate_gate(conf, reg.retention, thresholds), case.manifest.mode)))

    return CaseResult(
        case_ref=case.manifest.case_ref,
        declared_count=declared,
        detected_count=detected,
        count_match=consistent,
        implants=final,
        gated=gated,
        unresolved_sites=unresolved,
    )
