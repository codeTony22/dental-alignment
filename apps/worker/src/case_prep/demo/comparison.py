"""Comparison artifacts — the five inspectable files a human uses to verify the
automation, baked into the workflow:

  01_input               the doctor's scan (what was uploaded)
  02_generated           what we generate: the library scan bodies placed at the
                         recovered poses ("bake pose into geometry")
  03_intersection_AND    input AND generated — where the scan and our placement agree
                         (the registration-quality overlap)
  04_difference          input MINUS generated — the original with the generated bodies
                         removed back out of it
  05_modifications       generated MINUS ground-truth-generated — the auto-vs-truth delta
                         (the synthetic stand-in for an operator's QC correction)

Every file is a real STL openable in any 3D viewer, so each stage can be compared by eye.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import trimesh

from case_prep.adapters.booleans import mesh_boolean
from case_prep.adapters.loader import LoadedCase, load_case
from case_prep.domain.clocking import clocking_angle_deg
from case_prep.domain.geometry import RigidTransform
from case_prep.pipeline.evaluation import load_ground_truth
from case_prep.pipeline.orchestrator import run_case


def _align_z_to(axis: np.ndarray) -> np.ndarray:
    z = np.array([0.0, 0.0, 1.0])
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    v = np.cross(z, a)
    s = float(np.linalg.norm(v))
    c = float(z @ a)
    if s < 1e-9:
        return np.eye(3) if c > 0 else RigidTransform.from_axis_angle([1, 0, 0], 180.0).rotation
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def _transform_from_pose(position, axis, clocking_deg, platform_depth: float) -> RigidTransform:
    r0 = _align_z_to(np.asarray(axis, float))
    if clocking_deg is not None:
        delta = clocking_deg - clocking_angle_deg(r0)
        r = RigidTransform.from_axis_angle(axis, delta).rotation @ r0
    else:
        r = r0
    t = np.asarray(position, float) - r @ np.array([0.0, 0.0, -platform_depth])
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = t
    return RigidTransform(m)


def _place(case: LoadedCase, items: List[Tuple[str, RigidTransform]]) -> trimesh.Trimesh:
    parts = []
    for sb_type, transform in items:
        m = case.library[sb_type].mesh.copy()
        m.apply_transform(transform.matrix)
        parts.append(m)
    return trimesh.util.concatenate(parts)


def _platform_depth(case: LoadedCase, sb_type: str) -> float:
    return -float(case.library[sb_type].scan_body_to_platform.apply([0.0, 0.0, 0.0])[2])


def emit_comparison_artifacts(case_dir, out_dir, pitch: float = 0.3) -> Dict[str, Path]:
    case = load_case(case_dir)
    result = run_case(case_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    input_mesh = case.scan
    generated = _place(case, [(r.scan_body_type, r.transform) for r in result.implants])

    paths: Dict[str, Path] = {}
    paths["input"] = out / "01_input.stl"
    paths["generated"] = out / "02_generated.stl"
    paths["intersection"] = out / "03_intersection_AND.stl"
    paths["difference"] = out / "04_difference_original_minus_generated.stl"
    input_mesh.export(paths["input"])
    generated.export(paths["generated"])
    mesh_boolean(input_mesh, generated, "intersection", pitch).export(paths["intersection"])
    mesh_boolean(input_mesh, generated, "difference", pitch).export(paths["difference"])

    gt_path = Path(case_dir) / "ground_truth.json"
    if gt_path.exists():
        gt = load_ground_truth(case_dir)
        gt_items = [
            (p.scan_body_type,
             _transform_from_pose(p.position, p.axis, p.clocking_degrees,
                                  _platform_depth(case, p.scan_body_type)))
            for p in gt.poses
        ]
        truth_generated = _place(case, gt_items)
        paths["modifications"] = out / "05_modifications_auto_minus_truth.stl"
        mesh_boolean(generated, truth_generated, "difference", pitch).export(paths["modifications"])

    from case_prep.adapters.render import render_comparison
    render = render_comparison(paths, out / "comparison.png")
    if render:
        paths["render"] = render
    return paths
