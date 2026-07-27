"""Messy-mesh generator — injects the defect classes real intraoral scans exhibit
(holes, vertex noise, spurious disconnected fragments) so we can stress the booleans
and ingest the way real files would, without needing patient data."""
import numpy as np
import trimesh

from case_prep.adapters.booleans import screw_channel
from case_prep.adapters.messy import DefectSpec, inject_defects


def _sphere():
    return trimesh.creation.icosphere(subdivisions=4, radius=3.0)


def test_holes_make_the_mesh_non_watertight():
    out = inject_defects(_sphere(), DefectSpec(seed=1, hole_fraction=0.1))
    assert not out.is_watertight


def test_noise_perturbs_vertices():
    base = _sphere()
    out = inject_defects(base, DefectSpec(seed=2, noise_mm=0.1))
    moved = np.linalg.norm(out.vertices[: len(base.vertices)] - base.vertices, axis=1)
    assert moved.mean() > 0.0


def test_spurious_fragment_adds_a_disconnected_body():
    out = inject_defects(_sphere(), DefectSpec(seed=3, spurious_fragments=1))
    assert out.body_count >= 2


def test_clean_spec_is_a_noop_passthrough():
    base = _sphere()
    out = inject_defects(base, DefectSpec(seed=0))
    assert out.is_watertight
    assert len(out.faces) == len(base.faces)


def _fine_cylinder():
    m = trimesh.creation.cylinder(radius=4.0, height=10.0, sections=64)
    for _ in range(2):
        m = m.subdivide()  # small triangles -> small, bridgeable holes (like a real scan)
    return m


def test_booleans_survive_a_fully_degraded_mesh():
    # the point of the generator: every defect at once, SDF-CSG still yields a clean solid
    clean_volume = _fine_cylinder().volume
    messy = inject_defects(_fine_cylinder(),
                           DefectSpec(seed=5, hole_fraction=0.12, noise_mm=0.05, spurious_fragments=1))
    assert not messy.is_watertight
    out = screw_channel(messy, position=[0, 0, 0], axis=[0, 0, 1], radius=1.2, length=14.0, pitch=0.25)
    assert out.is_watertight
    # and it must not COLLAPSE — the solid is recovered, then bored (channel removes a little)
    assert out.volume > 0.7 * clean_volume
