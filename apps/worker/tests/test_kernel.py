"""Unit pins for ``case_prep.pipeline.kernel`` (boolean-engine plan, Stage 0,
2026-08-13): the narrow ``BooleanKernel`` port that becomes the ONLY surface
``case_prep.pipeline.csg`` calls for a boolean operation. ``ManifoldKernel``
wraps the exact ``trimesh.boolean`` calls the codebase already made — these
pins hold that wrapping honest with axis-aligned cubes, where the
inclusion-exclusion volumes are exact and there is nothing to approximate:
two 2x2x2 cubes shifted by 1mm along x share a 1x2x2=4 slab, so union=12,
difference=4, intersection=4 by construction, not by measurement.

W2 (boolean-engine plan, "Minkowski-sphere offset replaces vertex-normal
dilation", 2026-08-14) adds ``minkowski_sphere`` pins at the bottom of this
file, against a UNIT cube (not the 2x2x2 fixture above) — its Steiner
volume formula is simplest at unit scale.

THE ENGINE SWITCH (this slice, 2026-08-15) adds ``TestEngineSwitch`` at the
bottom: ``default_kernel()``'s own half of the ``CASE_PREP_BOOLEAN_KERNEL``
contract — the manifold path is BYTE-IDENTICAL whether the variable is
unset or explicitly ``"manifold"``, an unknown value is refused by name,
and the env var is read ONCE per process (a later mutation never changes
what an already-resolved process hands back). The adapter's own half — a
missing meshlib package refusing cleanly, the guard, the cube-algebra
conformance pins — lives beside the adapter in ``test_meshlib_kernel.py``,
per this file's own scope boundary for the slice."""
from __future__ import annotations

import importlib.util
import math

import numpy as np
import pytest
import trimesh

import case_prep.pipeline.kernel as kernel_module
from case_prep.pipeline.kernel import (BooleanKernel, ManifoldKernel,
                                       TrackedResult, default_kernel)


def _cube(shift=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
    box.apply_translation(shift)
    return box


def _unit_cube() -> trimesh.Trimesh:
    return trimesh.creation.box(extents=[1.0, 1.0, 1.0])


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


def _cylinder(radius, height, shift=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    cyl = trimesh.creation.cylinder(radius=radius, height=height)
    cyl.apply_translation(shift)
    return cyl


class TestDifferenceTrackedProvenance:
    """W1 (boolean-engine plan, 2026-08-13): ``difference_tracked`` must
    label every OUTPUT face by which operand's material it carries — read
    off manifold3d's own originalID runs, never measured by distance. A box
    with two separate cylindrical tunnels bored through it has three
    geometrically disjoint face groups (the box's own outer skin, tunnel
    1's wall, tunnel 2's wall) that a plain radial test can verify
    independently of the kernel's own labelling — the ground truth this
    pin checks ``source`` against."""

    def _bored_box(self):
        shell = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
        t1 = _cylinder(1.5, 12.0, (-2.5, 0.0, 0.0))
        t2 = _cylinder(1.5, 12.0, (2.5, 0.0, 0.0))
        return shell, t1, t2

    def test_every_output_face_is_labelled_by_its_own_true_geometric_source(self):
        kernel = ManifoldKernel()
        shell, t1, t2 = self._bored_box()
        result = kernel.difference_tracked(shell, [t1, t2])
        assert isinstance(result, TrackedResult)
        assert result.mesh.is_watertight
        assert result.base_groups == 1

        C = np.asarray(result.mesh.triangles_center, float)
        r1 = np.hypot(C[:, 0] + 2.5, C[:, 1])
        r2 = np.hypot(C[:, 0] - 2.5, C[:, 1])
        on_tool1 = np.abs(r1 - 1.5) < 0.1
        on_tool2 = np.abs(r2 - 1.5) < 0.1
        on_shell_skin = ~on_tool1 & ~on_tool2

        # the three regions must be non-trivial, or this pin proves nothing
        assert on_tool1.sum() > 0 and on_tool2.sum() > 0 and on_shell_skin.sum() > 0

        assert set(result.source[on_tool1].tolist()) == {1}
        assert set(result.source[on_tool2].tolist()) == {2}
        assert set(result.source[on_shell_skin].tolist()) == {0}

    def test_a_tool_entirely_outside_the_base_leaves_every_face_source_zero(self):
        kernel = ManifoldKernel()
        shell = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
        far_tool = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
        far_tool.apply_translation([10.0, 0.0, 0.0])
        result = kernel.difference_tracked(shell, [far_tool])
        assert float(result.mesh.volume) == pytest.approx(8.0, abs=1e-6)
        assert set(result.source.tolist()) == {0}

    def test_needs_at_least_one_tool(self):
        kernel = ManifoldKernel()
        with pytest.raises(ValueError):
            kernel.difference_tracked(trimesh.creation.box(), [])

    def test_a_groups_splits_the_base_into_distinguishable_sub_sources(self):
        """The mechanism ``csg.py``'s scan/fabricated split rides on: a
        per-face group array over ``a`` gives that operand MULTIPLE
        sources, still distinguished from every tool's own — the box's
        own first 6 faces (group 0) and last 6 (group 1) resolve to
        DIFFERENT sources even though they are the very same physical
        solid, and the tool that removes a corner keeps its own source
        distinct from both."""
        kernel = ManifoldKernel()
        box = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
        n = len(box.faces)
        groups = np.zeros(n, dtype=int)
        groups[6:] = 1
        tool = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
        tool.apply_translation([4.0, 4.0, 4.0])  # bites one corner off

        result = kernel.difference_tracked(box, [tool], a_groups=groups)
        assert result.base_groups == 2
        assert set(result.source.tolist()) == {0, 1, 2}


class TestUnionTrackedProvenance:
    def test_every_output_face_traces_to_the_mesh_it_actually_came_from(self):
        kernel = ManifoldKernel()
        a = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
        b = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
        b.apply_translation([1.0, 0.0, 0.0])  # overlaps a by a 1x2x2 slab
        c = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
        c.apply_translation([6.0, 0.0, 0.0])  # entirely disjoint

        result = kernel.union_tracked([a, b, c])
        assert result.mesh.is_watertight
        assert result.base_groups == 1
        assert float(result.mesh.volume) == pytest.approx(12.0 + 8.0, abs=1e-6)

        C = np.asarray(result.mesh.triangles_center, float)
        on_c = C[:, 0] > 4.5
        assert on_c.sum() > 0
        assert set(result.source[on_c].tolist()) == {2}
        # a and b fused into one seamless solid over their shared slab —
        # both their own sources appear, but neither appears where the
        # OTHER's own material exclusively stands
        only_a = C[:, 0] < -0.5
        only_b = (C[:, 0] > 1.5) & (C[:, 0] < 4.5)
        assert only_a.sum() > 0 and only_b.sum() > 0
        assert set(result.source[only_a].tolist()) == {0}
        assert set(result.source[only_b].tolist()) == {1}

    def test_needs_at_least_one_mesh(self):
        kernel = ManifoldKernel()
        with pytest.raises(ValueError):
            kernel.union_tracked([])

    def test_a_single_mesh_unions_to_itself_with_one_source(self):
        kernel = ManifoldKernel()
        cube = _cube()
        result = kernel.union_tracked([cube])
        assert float(result.mesh.volume) == pytest.approx(float(cube.volume), abs=1e-6)
        assert set(result.source.tolist()) == {0}


class TestTrackedKernelPartOfTheProtocol:
    def test_the_default_kernel_carries_both_tracked_operations(self):
        kernel = default_kernel()
        assert hasattr(kernel, "difference_tracked")
        assert hasattr(kernel, "union_tracked")


class TestMinkowskiSphere:
    """W2 (boolean-engine plan, 2026-08-14): the true morphological
    dilation replacing ``exact_cap_punch``'s vertex-normal push. Pinned
    against a UNIT cube's own closed-form Steiner volume, derived by direct
    geometric decomposition (not fit against any reference run): the
    dilated solid is the cube itself, plus a flat SLAB of thickness r on
    each of its 6 unit-area faces (6 * 1 * r = 6r), plus a QUARTER-CYLINDER
    of radius r and length 1 along each of its 12 edges
    ((1/4) * pi * r^2 * 1 per edge = 3*pi*r^2 total), plus an EIGHTH-SPHERE
    of radius r at each of its 8 corners ((1/8) * (4/3) * pi * r^3 per
    corner = (4/3)*pi*r^3 total):

        V(r) = 1 + 6r + 3*pi*r^2 + (4/3)*pi*r^3

    The icosphere OPERAND is a polyhedral approximation INSCRIBED in the
    true ball (every facet sits strictly inside the sphere it approximates),
    so the measured sum always falls a little SHORT of this closed form,
    never over — measured at r=0.3mm with the default subdivisions=3 sphere
    (2026-08-14, this repo's own pin run): 0.005277mm short, comfortably
    inside the 0.01mm tolerance below (measured shortfall at r=0.1:
    0.000514mm; at r=0.5: 0.016584mm — it grows with r, as the chord-error
    arithmetic in ``minkowski_sphere``'s own docstring predicts)."""

    def test_on_a_unit_cube_matches_the_closed_form_steiner_volume(self):
        kernel = ManifoldKernel()
        r = 0.3
        out = kernel.minkowski_sphere(_unit_cube(), r)
        assert out.is_watertight
        closed_form = 1.0 + 6 * r + 3 * math.pi * r**2 + (4.0 / 3.0) * math.pi * r**3
        shortfall = closed_form - float(out.volume)
        assert 0.0 < shortfall < 0.01, \
            f"measured volume {out.volume:.6f} vs closed form " \
            f"{closed_form:.6f} (shortfall {shortfall:.6f}) — an inscribed " \
            "icosphere operand must fall a LITTLE short, never over, and " \
            "never by much"

    def test_at_radius_zero_is_identity(self):
        kernel = ManifoldKernel()
        out = kernel.minkowski_sphere(_unit_cube(), 0.0)
        assert out.is_watertight
        assert abs(float(out.volume) - 1.0) < 1e-9

    def test_refuses_a_negative_radius(self):
        kernel = ManifoldKernel()
        with pytest.raises(ValueError):
            kernel.minkowski_sphere(_unit_cube(), -0.1)

    def test_refuses_a_non_watertight_operand(self):
        """The verified binding behaviour this guards: an open shell
        handed straight to ``manifold3d.Manifold()`` reads back
        ``Error.NotManifold``, and ``minkowski_sum`` on that returns an
        EMPTY mesh with no exception at all — the quietest possible wrong
        answer. This pin holds that ``minkowski_sphere`` intercepts it."""
        kernel = ManifoldKernel()
        with pytest.raises(ValueError):
            kernel.minkowski_sphere(_open_box(), 0.3)

    def test_is_part_of_the_default_kernels_protocol(self):
        assert hasattr(default_kernel(), "minkowski_sphere")


class TestEngineSwitch:
    """``default_kernel()``'s own half of the ``CASE_PREP_BOOLEAN_KERNEL``
    contract (this slice, 2026-08-15). Every test resets the module's two
    private caches (``_engine_name``, ``_kernels_by_engine``) via
    ``monkeypatch`` — never by hand-mutating them without restoration — so
    a test earlier in this file (or later in the same session) that
    already resolved ``default_kernel()`` to the plain manifold singleton
    is not disturbed by anything below."""

    @pytest.fixture(autouse=True)
    def _reset_engine_cache(self, monkeypatch):
        monkeypatch.setattr(kernel_module, "_engine_name", None)
        monkeypatch.setattr(kernel_module, "_kernels_by_engine", {})
        monkeypatch.delenv("CASE_PREP_BOOLEAN_KERNEL", raising=False)

    def test_unset_returns_the_plain_manifold_kernel_untouched(self):
        kernel = kernel_module.default_kernel()
        assert type(kernel) is ManifoldKernel, (
            "the manifold path must be byte-identical to before this "
            "slice — no wrapper, no proxy, the exact same class")

    def test_explicit_manifold_is_the_same_as_unset(self, monkeypatch):
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "manifold")
        assert type(kernel_module.default_kernel()) is ManifoldKernel

    def test_an_unset_default_kernel_is_still_the_process_singleton(self):
        assert kernel_module.default_kernel() is kernel_module.default_kernel()

    def test_selecting_meshlib_without_the_package_raises_naming_the_env_var_and_the_license(
            self, monkeypatch):
        if importlib.util.find_spec("meshlib") is not None:
            pytest.skip("meshlib IS importable in this environment — this "
                       "pin is specifically the missing-package path, "
                       "exercised by the production venv this repo ships")
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "meshlib")
        with pytest.raises(ImportError) as excinfo:
            kernel_module.default_kernel()
        message = str(excinfo.value)
        assert "CASE_PREP_BOOLEAN_KERNEL" in message
        assert "license" in message.lower()

    def test_an_unknown_engine_name_is_refused_by_name(self, monkeypatch):
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "not-a-real-engine")
        with pytest.raises(ValueError) as excinfo:
            kernel_module.default_kernel()
        message = str(excinfo.value)
        assert "CASE_PREP_BOOLEAN_KERNEL" in message
        assert "not-a-real-engine" in message

    def test_the_env_var_is_read_once_not_re_read_on_every_call(self, monkeypatch):
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "manifold")
        first = kernel_module.default_kernel()
        assert type(first) is ManifoldKernel
        # mutating the variable AFTER the first resolution must change
        # nothing — a running process reads it exactly once
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "not-a-real-engine")
        second = kernel_module.default_kernel()
        assert second is first
