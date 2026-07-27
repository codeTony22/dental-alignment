"""Signed-distance-field CSG core (pure numpy + skimage marching cubes).

SDF booleans are the robust technique for the non-watertight, degenerate meshes real
intraoral scans produce, where naive mesh booleans crack (design 6.5). Here we test
the math: grid, analytic primitives, boolean combinators, and surface extraction.
"""
import numpy as np
import pytest

from case_prep.domain.sdf import (
    SdfGrid,
    extract_surface,
    op_difference,
    op_intersection,
    op_union,
    sdf_cylinder,
    sdf_sphere,
)


def test_grid_covers_bounds_with_padding():
    grid = SdfGrid.from_bounds(np.array([[0, 0, 0], [10, 10, 10]]), pitch=1.0, pad=2)
    assert grid.coords.shape[-1] == 3
    # padded below the min corner and above the max corner
    assert grid.coords[..., 0].min() <= -1.0
    assert grid.coords[..., 0].max() >= 11.0


def test_sphere_sdf_is_signed_distance():
    grid = SdfGrid.from_bounds(np.array([[-3, -3, -3], [3, 3, 3]]), pitch=0.5, pad=1)
    vals = sdf_sphere(grid, center=[0, 0, 0], radius=2.0)
    # the deepest interior point is about -radius; the far corner is positive
    assert vals.min() == pytest.approx(-2.0, abs=0.5)
    assert vals.max() > 0


def test_difference_removes_the_second_shape():
    grid = SdfGrid.from_bounds(np.array([[-3, -3, -3], [3, 3, 3]]), pitch=0.4, pad=1)
    a = sdf_sphere(grid, [0, 0, 0], 2.0)
    b = sdf_sphere(grid, [1.5, 0, 0], 1.0)  # a smaller sphere to bite out
    diff = op_difference(a, b)
    # a point clearly inside b is now OUTSIDE the result (positive)
    p = np.array([1.5, 0, 0])
    idx = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - p, axis=-1)), grid.shape)
    assert diff[idx] > 0
    # a point inside a but far from b stays inside
    q = np.array([-1.5, 0, 0])
    idx2 = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - q, axis=-1)), grid.shape)
    assert diff[idx2] < 0


def test_union_and_intersection_combinators():
    grid = SdfGrid.from_bounds(np.array([[-3, -3, -3], [3, 3, 3]]), pitch=0.5, pad=1)
    a = sdf_sphere(grid, [-1, 0, 0], 1.5)
    b = sdf_sphere(grid, [1, 0, 0], 1.5)
    assert np.allclose(op_union(a, b), np.minimum(a, b))
    assert np.allclose(op_intersection(a, b), np.maximum(a, b))


def test_cylinder_sdf_inside_and_outside():
    grid = SdfGrid.from_bounds(np.array([[-4, -4, -4], [4, 4, 4]]), pitch=0.5, pad=1)
    vals = sdf_cylinder(grid, point=[0, 0, 0], axis=[0, 0, 1], radius=1.0, half_length=3.0)
    # on the axis, inside radius and length -> negative
    on_axis = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - [0, 0, 0], axis=-1)), grid.shape)
    assert vals[on_axis] < 0
    # far off-axis -> positive
    off = np.unravel_index(np.argmin(np.linalg.norm(grid.coords - [3.5, 0, 0], axis=-1)), grid.shape)
    assert vals[off] > 0


def test_marching_cubes_recovers_a_sphere():
    grid = SdfGrid.from_bounds(np.array([[-3, -3, -3], [3, 3, 3]]), pitch=0.25, pad=2)
    vals = sdf_sphere(grid, [0, 0, 0], 2.0)
    verts, faces = extract_surface(grid.with_values(vals))
    assert len(verts) > 100 and len(faces) > 100
    radii = np.linalg.norm(verts - verts.mean(axis=0), axis=1)
    assert radii.mean() == pytest.approx(2.0, abs=0.15)  # surface sits at ~r
