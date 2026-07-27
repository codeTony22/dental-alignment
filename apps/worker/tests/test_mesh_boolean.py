"""Two-mesh SDF boolean — puts BOTH meshes on a common grid so we can intersect (AND)
and subtract the doctor's scan against what we generate. The basis of the comparison
artifacts (input, generated, intersection, difference)."""
import numpy as np
import trimesh

from case_prep.adapters.booleans import mesh_boolean


def _two_spheres():
    a = trimesh.creation.icosphere(subdivisions=3, radius=2.0)
    b = trimesh.creation.icosphere(subdivisions=3, radius=2.0)
    b.apply_translation([2.0, 0, 0])  # overlap region in the middle
    return a, b


def test_intersection_is_smaller_than_either_and_watertight():
    a, b = _two_spheres()
    out = mesh_boolean(a, b, "intersection", pitch=0.15)
    assert out.is_watertight
    assert 0 < out.volume < min(a.volume, b.volume)


def test_union_is_larger_than_either():
    a, b = _two_spheres()
    out = mesh_boolean(a, b, "union", pitch=0.15)
    assert out.is_watertight
    assert out.volume > max(a.volume, b.volume)


def test_difference_removes_the_overlap_from_a():
    a, b = _two_spheres()
    out = mesh_boolean(a, b, "difference", pitch=0.15)
    assert out.is_watertight
    # a minus b: smaller than a, and a point deep inside b is now outside the result
    assert out.volume < a.volume
    assert not out.contains([[2.0, 0.0, 0.0]])[0]
    assert out.contains([[-1.5, 0.0, 0.0]])[0]
