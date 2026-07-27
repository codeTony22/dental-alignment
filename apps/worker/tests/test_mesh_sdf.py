"""Mesh <-> SDF bridge. The robustness claim: SDF-CSG yields a clean WATERTIGHT result
even when the input mesh is non-watertight (holes) — exactly the real-scan failure mode
that cracks naive mesh booleans."""
import numpy as np
import trimesh

from case_prep.adapters.mesh_sdf import mesh_to_sdf, sdf_to_mesh


def _holey_sphere(radius=2.0, drop=0.12, seed=0):
    m = trimesh.creation.icosphere(subdivisions=4, radius=radius)
    rng = np.random.default_rng(seed)
    keep = rng.random(len(m.faces)) > drop
    m.update_faces(keep)
    m.remove_unreferenced_vertices()
    return m


def test_sdf_of_sphere_matches_analytic_distance():
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=2.0)
    grid = mesh_to_sdf(mesh, pitch=0.2)
    # sample the signed distance near a known point: surface at radius 2 along +x
    p = np.array([2.0, 0.0, 0.0])
    idx = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - p, axis=-1)), grid.shape)
    assert abs(grid.values[idx]) < 0.4  # ~0 on the surface, within a couple voxels
    # centre is interior (negative), far outside is positive
    c = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - [0, 0, 0], axis=-1)), grid.shape)
    assert grid.values[c] < 0


def test_roundtrip_is_watertight_and_preserves_volume():
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=2.0)
    out = sdf_to_mesh(mesh_to_sdf(mesh, pitch=0.15))
    assert out.is_watertight
    assert out.volume == np_approx(mesh.volume, rel=0.15)


def test_nonwatertight_input_yields_watertight_output():
    holey = _holey_sphere(drop=0.12)
    assert not holey.is_watertight  # the input genuinely has holes
    out = sdf_to_mesh(mesh_to_sdf(holey, pitch=0.15))
    # the SDF route closes the holes — the output is a clean solid
    assert out.is_watertight
    assert out.volume == np_approx((4 / 3) * np.pi * 2.0 ** 3, rel=0.2)


def np_approx(value, rel):
    import pytest
    return pytest.approx(value, rel=rel)
