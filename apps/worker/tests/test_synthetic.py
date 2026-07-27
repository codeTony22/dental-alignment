"""Adversarial synthetic generator. Places known scan bodies at known 6-DoF poses
on a gingiva arch, writing a complete case dir + HELD-OUT ground truth. The pipeline
never reads ground_truth.json; only the metrics layer does."""
import json
from pathlib import Path

import numpy as np
import trimesh

from case_prep.adapters.synthetic import (
    SyntheticParams,
    generate_case,
    make_scan_body_mesh,
)
from case_prep.manifest import CaseManifest


def test_scan_body_mesh_has_height_and_breaks_symmetry():
    mesh = make_scan_body_mesh()
    assert isinstance(mesh, trimesh.Trimesh)
    # stands proud: extent along its axis (z) is a few mm
    zext = mesh.bounds[1][2] - mesh.bounds[0][2]
    assert 3.0 < zext < 15.0
    # anti-rotation feature breaks rotational symmetry: the cross-section centroid
    # is offset from the axis on at least one side (a flat removes material)
    mirrored = mesh.copy()
    mirrored.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [0, 0, 1]))
    # not invariant under 180-degree rotation about axis (a pure cylinder would be)
    assert not np.allclose(
        np.sort(mesh.vertices, axis=0), np.sort(mirrored.vertices, axis=0), atol=1e-6
    )


def test_generate_case_writes_full_contract(tmp_path):
    params = SyntheticParams(seed=7, n_implants=3)
    gt = generate_case(tmp_path, params)

    assert (tmp_path / "case.json").exists()
    assert (tmp_path / "scan.stl").exists()
    assert (tmp_path / "ground_truth.json").exists()
    # a library mesh + transform per distinct scan-body type
    assert (tmp_path / "library").is_dir()
    types = {s.scan_body_type for s in CaseManifest.model_validate_json(
        (tmp_path / "case.json").read_text()).implant_sites}
    for t in types:
        assert (tmp_path / "library" / t / "mesh.stl").exists()
        assert (tmp_path / "library" / t / "transform.json").exists()

    # ground truth has one pose per declared site
    assert len(gt.poses) == 3


def test_declared_count_matches_ground_truth(tmp_path):
    gt = generate_case(tmp_path, SyntheticParams(seed=1, n_implants=2))
    manifest = CaseManifest.model_validate_json((tmp_path / "case.json").read_text())
    assert manifest.declared_count == len(gt.poses) == 2


def test_scan_contains_geometry_near_each_truth_position(tmp_path):
    gt = generate_case(tmp_path, SyntheticParams(seed=3, n_implants=2))
    scan = trimesh.load(tmp_path / "scan.stl", force="mesh")
    for pose in gt.poses:
        d = np.linalg.norm(scan.vertices - np.asarray(pose.position), axis=1)
        assert d.min() < 3.0  # some scan-body surface sits near the platform point


def test_generation_is_deterministic_for_a_seed(tmp_path):
    a = generate_case(tmp_path / "a", SyntheticParams(seed=42, n_implants=2))
    b = generate_case(tmp_path / "b", SyntheticParams(seed=42, n_implants=2))
    pa = np.array([p.position for p in a.poses])
    pb = np.array([p.position for p in b.poses])
    assert np.allclose(pa, pb)
