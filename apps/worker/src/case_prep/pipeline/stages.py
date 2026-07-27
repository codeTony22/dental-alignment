"""The staged worker — the real automation workflow, split at the human boundary
(design 6.1): STAGE 1 (auto) ingests + localizes and parks the case at awaiting_seed;
the operator seeds; STAGE 2 (auto) registers + gates + packages. Each stage reads and
writes file artifacts to a work dir (mirroring the S3 intermediate-artifact handoff in
production), so the input and output of every stage are real, inspectable files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

import numpy as np
import trimesh

from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.ingest import normalize_orientation, scale_ok
from case_prep.adapters.loader import load_case
from case_prep.domain.confidence import GateThresholds, apply_case_mode, evaluate_gate
from case_prep.domain.consistency import multi_implant_consistency
from case_prep.domain.poses import Retention
from case_prep.domain.registration import RegisteredImplant
from case_prep.pipeline.orchestrator import DEFAULT_THRESHOLDS, _COUNT_SLACK, _derive_pose, _order_along_arch


class Status(str, Enum):
    SUBMITTED = "submitted"
    AWAITING_SEED = "awaiting_seed"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


@dataclass
class Stage1Result:
    status: Status
    declared_count: int
    detected_count: int
    count_match: bool
    seeds: List[dict]
    artifacts: dict


@dataclass
class Stage2Result:
    status: Status
    clear_rate: float
    implants: List[dict]
    artifacts: dict


def _write_state(work_dir: Path, **state) -> None:
    """Merge into the case state (accumulate across stages), don't overwrite it."""
    path = Path(work_dir) / "case_state.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    current.update(state)
    path.write_text(json.dumps(current, indent=2))


def _needs_normalization(mesh: trimesh.Trimesh) -> bool:
    """Raw real scans arrive off-origin in an arbitrary frame; synthetic/semi-real cases
    are already occlusal-up. Only normalize when the scan isn't already z-up and centred."""
    # Real scanner frames sit far off-origin (Teeth3DS ~100mm); synthetic/semi-real cases
    # are built centred and occlusal-up. Off-origin distance is the clean discriminator.
    return float(np.linalg.norm(np.asarray(mesh.vertices, float).mean(axis=0))) > 30.0


def run_stage1(case_dir, work_dir, thresholds: GateThresholds = DEFAULT_THRESHOLDS) -> Stage1Result:
    case = load_case(case_dir)
    work = Path(work_dir)
    (work / "stage1").mkdir(parents=True, exist_ok=True)

    # --- ingest: normalize frame (real scans only) + scale gate ---
    scan = case.scan
    if _needs_normalization(scan):
        scan, _ = normalize_orientation(scan)
    if not scale_ok(scan):
        _write_state(work, status=Status.REJECTED.value, reason="implausible arch scale")
        return Stage1Result(Status.REJECTED, case.manifest.declared_count, 0, False, [], {})

    normalized_path = work / "stage1" / "normalized_scan.stl"
    scan.export(normalized_path)

    # --- localize: detect scan bodies, emit seeds (count NOT capped, so mismatch shows) ---
    declared = case.manifest.declared_count
    sites = sorted(case.manifest.implant_sites, key=lambda s: s.tooth)
    scan_pts = np.asarray(scan.vertices, float)
    locs = engine.localize(scan_pts, declared + _COUNT_SLACK)
    if len(locs) != declared:
        # Cheap cluster detection missed the count (typical on dense real arches, where teeth are
        # also protrusions). Fall back to template-matching the library CAD along the ridge —
        # robust auto-detection with NO operator click. (Single library type = the common case.)
        lib_mesh = case.library[sites[0].scan_body_type].mesh
        locs = [d.localization for d in engine.auto_localize(
            scan_pts, lib_mesh, declared + _COUNT_SLACK,
            normals=np.asarray(scan.vertex_normals, float))]
    detected = len(locs)
    count_match = detected == declared

    order = _order_along_arch(locs[:declared])
    seeds = []
    for site, li in zip(sites, order):
        loc = locs[li]
        seeds.append({
            "tooth": site.tooth, "retention": site.retention.value,
            "scan_body_type": site.scan_body_type,
            "seed": [float(x) for x in loc.centroid], "axis": [float(x) for x in loc.axis],
        })

    (work / "stage1" / "localization.json").write_text(json.dumps({
        "declared_count": declared, "detected_count": detected, "count_match": count_match,
        "seeds": seeds,
    }, indent=2))

    status = Status.AWAITING_SEED if count_match else Status.NEEDS_REVIEW
    _write_state(work, status=status.value, declared_count=declared,
                 detected_count=detected, count_match=count_match)
    return Stage1Result(status, declared, detected, count_match, seeds,
                        {"normalized_scan": normalized_path,
                         "localization": work / "stage1" / "localization.json"})


def auto_seed(work_dir) -> Path:
    """Operator stand-in: accept stage-1's automatic localization seeds as the human seed.
    Reliable on clean scans; on dense real arches the automatic seeds are brittle, so use
    operator_seed_from_truth (simulated clicks) instead."""
    work = Path(work_dir)
    loc = json.loads((work / "stage1" / "localization.json").read_text())
    seeds_path = work / "seeds.json"
    seeds_path.write_text(json.dumps({"seeds": loc["seeds"]}, indent=2))
    return seeds_path


def operator_seed_from_truth(case_dir, work_dir) -> Path:
    """Simulate the operator seeding each body by clicking it — using the known body
    locations. This is the reliable real-scan path the design makes the default: stage-1
    automatic detection is brittle on real arches, so a human provides the seed."""
    from case_prep.pipeline.evaluation import load_ground_truth

    case = load_case(case_dir)
    gt = load_ground_truth(case_dir)
    sites = {s.tooth: s for s in case.manifest.implant_sites}
    seeds = []
    for p in gt.poses:
        depth = -float(case.library[p.scan_body_type].scan_body_to_platform.apply([0, 0, 0])[2])
        axis = np.asarray(p.axis, float)
        click = np.asarray(p.position, float) + axis * (depth + 4.0)  # a point on the body
        seeds.append({"tooth": p.tooth, "retention": sites[p.tooth].retention.value,
                      "scan_body_type": p.scan_body_type,
                      "seed": [float(x) for x in click], "axis": [float(x) for x in axis]})
    seeds_path = Path(work_dir) / "seeds.json"
    seeds_path.write_text(json.dumps({"seeds": seeds}, indent=2))
    # the operator confirms the count by seeding, so reconcile it — stage 2 then judges the
    # actual registration quality rather than flagging on stage-1's brittle auto-detection.
    state_path = Path(work_dir) / "case_state.json"
    state = json.loads(state_path.read_text())
    state.update(count_match=True, detected_count=len(seeds))
    state_path.write_text(json.dumps(state, indent=2))
    return seeds_path


def run_stage2(case_dir, work_dir, thresholds: GateThresholds = DEFAULT_THRESHOLDS) -> Stage2Result:
    case = load_case(case_dir)
    work = Path(work_dir)
    (work / "stage2").mkdir(parents=True, exist_ok=True)

    scan = trimesh.load(work / "stage1" / "normalized_scan.stl", force="mesh")
    scan_pts = np.asarray(scan.vertices, float)
    scan_normals = np.asarray(scan.vertex_normals, float)  # real normals -> body-isolating ROI
    seeds = json.loads((work / "seeds.json").read_text())["seeds"]
    consistent = json.loads((work / "case_state.json").read_text()).get("count_match", True)

    registered = []
    for s in seeds:
        retention = Retention(s["retention"])
        loc = engine.localize_from_seed(scan_pts, s["seed"], normals=scan_normals)
        part = case.library[s["scan_body_type"]]
        transform, conf = engine.register(loc, part.mesh, retention)
        registered.append((s, part, retention, transform, conf,
                           _derive_pose(transform, part, retention)))

    # cross-implant signal: count reconciliation AND geometric consistency (physically
    # possible spacing, within-protocol axis divergence) — previously count-only
    geo_ok, _ = multi_implant_consistency([r[5] for r in registered])
    cross_ok = consistent and geo_ok

    implants: List[RegisteredImplant] = []
    gated = []
    rows = []
    for s, part, retention, transform, conf, pose in registered:
        from dataclasses import replace
        conf = replace(conf, multi_implant_consistent=cross_ok)
        reg = RegisteredImplant(s["tooth"], retention, s["scan_body_type"], pose, conf, transform)
        # the gate computes its verdict; the case's MODE decides whether it may auto-approve
        # (advisory = fail-closed shadow mode for unvalidated data classes; the would_pass
        # field is the shadow log that later calibrates the thresholds)
        decision = apply_case_mode(evaluate_gate(conf, retention, thresholds), case.manifest.mode)
        implants.append(reg)
        gated.append((reg, decision))
        rows.append({"tooth": reg.tooth, "retention": retention.value,
                     "position": pose.position, "axis": [float(x) for x in pose.axis.direction],
                     "clocking_degrees": pose.clocking_degrees,
                     # HONESTY: with the identity placeholder transform the derived pose is the
                     # SCAN BODY's, not the implant platform's — consumers must know which
                     "pose_origin": ("implant-platform" if part.platform_transform_known
                                     else "scan-body"),
                     "gate": "PASS" if decision.passed else "FLAG", "reasons": decision.reasons,
                     "advisory": decision.advisory, "would_pass": decision.would_pass})

    # --- package: bake recovered bodies into geometry, write the result + comparison ---
    generated = _place_generated(case, implants)
    gen_path = work / "stage2" / "02_generated.stl"
    scan.export(work / "stage2" / "01_input.stl")
    generated.export(gen_path)
    try:  # comparison artifacts (best-effort); coarser pitch for large real arches
        from case_prep.adapters.booleans import mesh_boolean
        pitch = 0.3 if float(max(scan.extents)) < 40 else 0.5
        mesh_boolean(scan, generated, "intersection", pitch).export(work / "stage2" / "03_intersection_AND.stl")
        mesh_boolean(scan, generated, "difference", pitch).export(work / "stage2" / "04_difference.stl")
    except Exception:
        pass

    clear = sum(d.passed for _, d in gated) / len(gated) if gated else 0.0
    status = Status.READY if (consistent and all(d.passed for _, d in gated)) else Status.NEEDS_REVIEW
    (work / "stage2" / "result.json").write_text(json.dumps({
        "status": status.value, "clear_rate": clear, "implants": rows,
    }, indent=2))
    _write_state(work, status=status.value, clear_rate=clear)
    return Stage2Result(status, clear, rows,
                        {"generated": gen_path, "result": work / "stage2" / "result.json"})


def _place_generated(case, implants) -> trimesh.Trimesh:
    parts = []
    for r in implants:
        m = case.library[r.scan_body_type].mesh.copy()
        m.apply_transform(r.transform.matrix)
        parts.append(m)
    return trimesh.util.concatenate(parts) if parts else trimesh.Trimesh()


def run_workflow(case_dir, work_dir, operator_seeds: bool = False) -> tuple:
    """Run stage 1 -> seed -> stage 2. ``operator_seeds`` uses the known body locations as
    simulated operator clicks (the reliable path for dense real arches); otherwise stage-1's
    automatic seeds are used (fine for clean scans)."""
    s1 = run_stage1(case_dir, work_dir)
    if s1.status is Status.REJECTED:
        return s1, None
    if operator_seeds:
        operator_seed_from_truth(case_dir, work_dir)
    else:
        auto_seed(work_dir)
    s2 = run_stage2(case_dir, work_dir)
    return s1, s2
