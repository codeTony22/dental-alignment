"""Unit pins for ``case_prep.pipeline.kernel`` (boolean-engine plan, Stage 0,
2026-08-13): the narrow ``BooleanKernel`` port that becomes the ONLY surface
``case_prep.pipeline.csg`` calls for a boolean operation. ``ManifoldKernel``
wraps the exact ``trimesh.boolean`` calls the codebase already made — these
pins hold that wrapping honest with axis-aligned cubes, where the
inclusion-exclusion volumes are exact and there is nothing to approximate:
two 2x2x2 cubes shifted by 1mm along x share a 1x2x2=4 slab, so union=12,
difference=4, intersection=4 by construction, not by measurement."""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from case_prep.pipeline.kernel import BooleanKernel, ManifoldKernel, default_kernel


def _cube(shift=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
    box.apply_translation(shift)
    return box


def _open_box() -> trimesh.Trimesh:
    """A box with one triangle dropped — a genuine boundary hole, not a
    passthrough mesh that merely LOOKS open. ``is_watertight`` must read
    False on this fixture or the pin below proves nothing about the kernel."""
    box = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
    faces = np.asarray(box.faces)
    keep = np.ones(len(faces), bool)
    keep[0] = False
    return trimesh.Trimesh(np.asarray(box.vertices, float).copy(),
                           faces[keep].copy(), process=False)


class TestManifoldKernelUnion:
    def test_two_overlapping_cubes_union_to_the_inclusion_exclusion_volume(self):
        kernel = ManifoldKernel()
        out = kernel.union([_cube(), _cube((1.0, 0.0, 0.0))])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(12.0, abs=1e-6)

    def test_a_single_mesh_unions_to_itself(self):
        kernel = ManifoldKernel()
        cube = _cube()
        out = kernel.union([cube])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(float(cube.volume), abs=1e-6)


class TestManifoldKernelDifference:
    def test_cube_minus_the_overlap_leaves_the_inclusion_exclusion_remainder(self):
        kernel = ManifoldKernel()
        out = kernel.difference(_cube(), [_cube((1.0, 0.0, 0.0))])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(4.0, abs=1e-6)

    def test_difference_against_a_non_overlapping_tool_leaves_the_base_unchanged(self):
        kernel = ManifoldKernel()
        cube = _cube()
        out = kernel.difference(cube, [_cube((10.0, 0.0, 0.0))])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(float(cube.volume), abs=1e-6)


class TestManifoldKernelIntersection:
    def test_two_overlapping_cubes_intersect_to_the_shared_slab(self):
        kernel = ManifoldKernel()
        out = kernel.intersection(_cube(), _cube((1.0, 0.0, 0.0)))
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(4.0, abs=1e-6)


class TestIsValidSolid:
    def test_a_closed_cube_is_a_valid_solid(self):
        kernel = ManifoldKernel()
        assert kernel.is_valid_solid(_cube()) is True

    def test_an_open_mesh_is_not_a_valid_solid(self):
        kernel = ManifoldKernel()
        open_mesh = _open_box()
        assert not open_mesh.is_watertight, \
            "the fixture must genuinely be open, or this pin proves nothing"
        assert kernel.is_valid_solid(open_mesh) is False


class TestDefaultKernel:
    def test_default_kernel_satisfies_the_protocol(self):
        assert isinstance(default_kernel(), BooleanKernel)

    def test_default_kernel_is_a_stable_singleton_for_the_process(self):
        assert default_kernel() is default_kernel()
