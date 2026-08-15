"""Port-conformance pins for ``case_prep.pipeline.meshlib_kernel`` (this
slice, 2026-08-15): ``MeshLibKernel``, the ``BooleanKernel`` port's second
concrete engine, and ``guard_boolean_output``, the mandatory post-condition
the kernel decision memo (§3.2) requires on every boolean it performs.

SKIPS CLEANLY WHEN MESHLIB IS ABSENT. The production venv this repo ships
does not carry meshlib and never will (the free evaluation tier is
non-commercial-only) — every test that needs a real ``MeshLibKernel``
instance is marked ``requires_meshlib`` and skips there. What does NOT
skip: the module import itself (the adapter's own lazy-import contract),
``guard_boolean_output`` (a pure function over trimesh meshes with no
meshlib dependency of its own), and the pyproject pin at the bottom
(text-matched, per this repo's own ``test_pyproject_pins.py`` convention,
that no meshlib dependency was ever added — asserting meshlib is NOT
importable would be wrong on the scratch evaluation venv this same file
runs under during the scoreboard; asserting the dependency was never
declared is true in both places).

Fixtures are built LOCALLY, per this suite's own no-test-to-test-import
convention (``test_kernel.py``'s cube helpers, ``test_degeneracy.py``'s own
copies of its shapes) — this file does not import ``csg.py``. The one
exception worth naming: the coplanar guard fixture below is NOT simply "the
lidded punch" — reproducing the degeneracy corpus's actual MeshLib failure
needed the production choreography's own missing ingredient
(``exact_cap_punch``'s unconditional self-heal, ``ManifoldKernel().union([
punch, punch])``, csg.py's own call) BEFORE the coplanar difference is
tested; that discovery, and why, is recorded on ``_degeneracy_case1_punch``
below.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.pipeline.kernel import BooleanKernel, ManifoldKernel
import case_prep.pipeline.kernel as kernel_module
from case_prep.pipeline import meshlib_kernel
from case_prep.pipeline.meshlib_kernel import (GUARD_VOLUME_TOLERANCE_MM3,
                                               guard_boolean_output)

MESHLIB_AVAILABLE = importlib.util.find_spec("meshlib") is not None
requires_meshlib = pytest.mark.skipif(
    not MESHLIB_AVAILABLE,
    reason="meshlib is not installed in this venv — the production venv "
           "this repo ships never carries it (see "
           "TestPyprojectDeclaresNoMeshlibDependency below); this pin "
           "exercises the real package and runs for real only under the "
           "scratch evaluation venv")


# --------------------------------------------------------------------------
# local fixtures — no test-to-test import
# --------------------------------------------------------------------------
def _cube(shift=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    box = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
    box.apply_translation(shift)
    return box


def _open_box() -> trimesh.Trimesh:
    """A box with one triangle dropped — a genuine boundary hole (mirrors
    ``test_kernel.py``'s own fixture of the same name and purpose)."""
    box = trimesh.creation.box(extents=[2.0, 2.0, 2.0])
    faces = np.asarray(box.faces)
    keep = np.ones(len(faces), bool)
    keep[0] = False
    return trimesh.Trimesh(np.asarray(box.vertices, float).copy(),
                           faces[keep].copy(), process=False)


def _lidded_bore_punch(top_z: float = 3.0, radius: float = 2.0,
                       bore_radius: float = 0.6, height: float = 4.0,
                       seg: int = 32) -> trimesh.Trimesh:
    """Local build of the degeneracy battery's case #1 punch shape (PLAN
    W3 #1, ``test_degeneracy.py``'s ``TestCoplanarBoreLidOnAMachinedFloor``)
    — closed side wall, bottom disc, and a flat annulus-plus-fan top whose
    surface sits bit-exactly on ``top_z``, built directly rather than via
    ``test_degeneracy.py``'s two-step open-then-lid (this file owns no
    dependency on ``csg.py``'s ``_lid_boundary_loops``)."""
    ang = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    bot = np.column_stack([radius * ca, radius * sa,
                           np.full(seg, top_z - height)])
    top_outer = np.column_stack([radius * ca, radius * sa, np.full(seg, top_z)])
    top_inner = np.column_stack([bore_radius * ca, bore_radius * sa,
                                 np.full(seg, top_z)])
    base_centre = np.array([[0.0, 0.0, top_z - height]])
    lid_centre = np.array([[0.0, 0.0, top_z]])
    verts = np.vstack([bot, top_outer, top_inner, base_centre, lid_centre])
    n = seg
    base_ci = 3 * n
    lid_ci = 3 * n + 1
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j])                   # outer wall
        faces.append([i, n + j, n + i])
        faces.append([n + i, 2 * n + i, 2 * n + j])    # top annulus
        faces.append([n + i, 2 * n + j, n + j])
        faces.append([j, i, base_ci])                  # bottom disc fan
        faces.append([2 * n + i, 2 * n + j, lid_ci])    # lid fan, closes the bore
    punch = trimesh.Trimesh(verts, np.asarray(faces, int), process=False)
    trimesh.repair.fix_normals(punch)
    return punch


def _flat_topped_block(top_z: float = 3.0, half: float = 10.0,
                       depth: float = 12.0) -> trimesh.Trimesh:
    """Local build of the same case's floor block — top face's z is the
    literal ``top_z``, never derived a second way."""
    bot_z = top_z - depth
    top = np.array([[-half, -half, top_z], [half, -half, top_z],
                    [half, half, top_z], [-half, half, top_z]])
    bot = np.array([[-half, -half, bot_z], [half, -half, bot_z],
                    [half, half, bot_z], [-half, half, bot_z]])
    verts = np.vstack([top, bot])
    faces = np.array([
        [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
        [0, 4, 1], [1, 4, 5], [1, 5, 2], [2, 5, 6],
        [2, 6, 3], [3, 6, 7], [3, 7, 0], [0, 7, 4]])
    block = trimesh.Trimesh(verts, faces, process=False)
    trimesh.repair.fix_normals(block)
    return block


def _degeneracy_case1_punch(top_z: float = 3.0) -> trimesh.Trimesh:
    """THE ACTUAL TRIGGER, found by exploration before this pin was
    written (this slice, 2026-08-15): the raw fan-lidded punch above,
    undifferenced, cuts CORRECTLY under MeshLib even at bit-exact
    coplanarity with the block below — the silent no-op needs
    ``exact_cap_punch``'s own unconditional self-heal
    (``default_kernel().union([punch, punch])``, csg.py:594, which fires
    regardless of ``offset_mm``) to have already round-tripped the punch
    through manifold3d BEFORE the coplanar difference is attempted. Built
    with ``ManifoldKernel()`` directly here — never ``default_kernel()``
    — so this fixture's own construction can never depend on whichever
    engine ``CASE_PREP_BOOLEAN_KERNEL`` currently selects in the same
    process."""
    punch = _lidded_bore_punch(top_z)
    return ManifoldKernel().union([punch, punch])


# --------------------------------------------------------------------------
# the module's own lazy-import contract
# --------------------------------------------------------------------------
class TestModuleImportsWithoutMeshlib:
    def test_the_module_itself_imports_cleanly_regardless(self):
        # already imported at the top of this file — if that import had
        # required meshlib, collection itself would have failed above.
        assert hasattr(meshlib_kernel, "MeshLibKernel")
        assert hasattr(meshlib_kernel, "guard_boolean_output")

    def test_constructing_the_kernel_is_the_one_place_meshlib_is_required(self):
        if MESHLIB_AVAILABLE:
            pytest.skip("meshlib IS importable here — this pin is "
                       "specifically the missing-package path")
        with pytest.raises(ImportError) as excinfo:
            meshlib_kernel.MeshLibKernel()
        message = str(excinfo.value)
        assert "meshlib" in message.lower()
        assert "license" in message.lower()


# --------------------------------------------------------------------------
# the guard — pure function, no meshlib needed
# --------------------------------------------------------------------------
class TestGuardBooleanOutput:
    """``guard_boolean_output`` (kernel-decision-memo §3.2) over plain
    trimesh meshes — every branch pinned without meshlib installed."""

    def test_an_empty_result_raises_naming_the_guard_and_face_counts(self):
        a = _cube()
        b = _cube((1.0, 0.0, 0.0))
        empty = trimesh.Trimesh(np.zeros((0, 3)), np.zeros((0, 3), int),
                                process=False)
        with pytest.raises(ValueError) as excinfo:
            guard_boolean_output("difference", [a, b], empty)
        message = str(excinfo.value)
        assert "guard" in message.lower()
        assert "EMPTY" in message
        assert str(len(a.faces)) in message
        assert str(len(b.faces)) in message

    def test_an_operand_returned_unchanged_raises_naming_the_guard_and_face_counts(self):
        a = _cube()
        b = _cube((10.0, 0.0, 0.0))  # far away, irrelevant to the match
        unchanged = a.copy()  # same face count, same volume as `a`
        with pytest.raises(ValueError) as excinfo:
            guard_boolean_output("difference", [a, b], unchanged)
        message = str(excinfo.value)
        assert "guard" in message.lower()
        assert "UNCHANGED" in message
        assert str(len(a.faces)) in message
        assert str(len(b.faces)) in message

    def test_a_result_that_actually_differs_from_every_operand_does_not_raise(self):
        a = _cube()
        b = _cube((1.0, 0.0, 0.0))
        actually_cut = ManifoldKernel().difference(a, [b])
        guard_boolean_output("difference", [a, b], actually_cut)  # no raise

    def test_same_face_count_but_a_genuinely_different_volume_does_not_raise(self):
        """The guard's SECOND condition (volume) matters on its own: a
        same-face-count coincidence with a materially different volume
        must not false-positive."""
        a = _cube()
        bigger = trimesh.creation.box(extents=[2.0, 2.0, 2.1])  # same topology
        assert len(bigger.faces) == len(a.faces)
        assert abs(float(bigger.volume) - float(a.volume)) > 0.1
        guard_boolean_output("union", [a], bigger)  # no raise

    def test_the_tolerance_is_exactly_the_memos_1e_minus_9(self):
        assert GUARD_VOLUME_TOLERANCE_MM3 == 1e-9


# --------------------------------------------------------------------------
# cube algebra — mirrors test_kernel.py's own exact-volume pins
# --------------------------------------------------------------------------
@requires_meshlib
class TestMeshLibKernelCubeAlgebra:
    """Same fixtures, same exact inclusion-exclusion arithmetic as
    ``test_kernel.py``'s ``TestManifoldKernel*`` classes — two 2x2x2 cubes
    shifted by 1mm share a 1x2x2=4 slab: union=12, difference=4,
    intersection=4, by construction."""

    def test_union_of_two_overlapping_cubes(self):
        kernel = meshlib_kernel.MeshLibKernel()
        out = kernel.union([_cube(), _cube((1.0, 0.0, 0.0))])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(12.0, abs=1e-6)

    def test_a_single_mesh_unions_to_itself(self):
        kernel = meshlib_kernel.MeshLibKernel()
        cube = _cube()
        out = kernel.union([cube])
        assert float(out.volume) == pytest.approx(float(cube.volume), abs=1e-6)

    def test_difference_of_two_overlapping_cubes(self):
        kernel = meshlib_kernel.MeshLibKernel()
        out = kernel.difference(_cube(), [_cube((1.0, 0.0, 0.0))])
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(4.0, abs=1e-6)

    def test_intersection_of_two_overlapping_cubes(self):
        kernel = meshlib_kernel.MeshLibKernel()
        out = kernel.intersection(_cube(), _cube((1.0, 0.0, 0.0)))
        assert out.is_watertight
        assert float(out.volume) == pytest.approx(4.0, abs=1e-6)

    def test_union_needs_at_least_one_mesh(self):
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(ValueError):
            kernel.union([])

    def test_difference_needs_at_least_one_tool(self):
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(ValueError):
            kernel.difference(_cube(), [])


@requires_meshlib
class TestMeshLibKernelIsValidSolid:
    def test_a_closed_cube_is_a_valid_solid(self):
        kernel = meshlib_kernel.MeshLibKernel()
        assert kernel.is_valid_solid(_cube()) is True

    def test_an_open_mesh_is_not_a_valid_solid(self):
        kernel = meshlib_kernel.MeshLibKernel()
        open_mesh = _open_box()
        assert not open_mesh.is_watertight, \
            "the fixture must genuinely be open, or this pin proves nothing"
        assert kernel.is_valid_solid(open_mesh) is False


@requires_meshlib
class TestMeshLibKernelSatisfiesTheProtocol:
    def test_isinstance_of_boolean_kernel(self):
        assert isinstance(meshlib_kernel.MeshLibKernel(), BooleanKernel)


@requires_meshlib
class TestMeshLibKernelTrackedOpsRefuseRatherThanFakeProvenance:
    def test_difference_tracked_names_the_provenance_gap(self):
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(NotImplementedError) as excinfo:
            kernel.difference_tracked(_cube(), [_cube((1.0, 0.0, 0.0))])
        message = str(excinfo.value).lower()
        assert "provenance" in message
        assert "fallback" in message

    def test_union_tracked_names_the_provenance_gap(self):
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(NotImplementedError) as excinfo:
            kernel.union_tracked([_cube(), _cube((1.0, 0.0, 0.0))])
        message = str(excinfo.value).lower()
        assert "provenance" in message
        assert "fallback" in message


@requires_meshlib
class TestMeshLibKernelMinkowskiSphereIsNotThisSlice:
    def test_names_sharp_offset_as_the_future_lane(self):
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(NotImplementedError) as excinfo:
            kernel.minkowski_sphere(_cube(), 0.3)
        assert "sharpoffset" in str(excinfo.value).lower()


# --------------------------------------------------------------------------
# the guard, exercised for real — the coplanar no-op and an empty result
# --------------------------------------------------------------------------
@requires_meshlib
class TestGuardCatchesTheCoplanarSilentNoOp:
    """PLAN W3 #1 replayed under MeshLibKernel (kernel-decision-memo §3.2,
    §A.1): on this exact fixture MeshLib's own mesh boolean returns the
    base UNCHANGED — no exception, a watertight output, every one of its
    own health signals green. The guard exists precisely to turn that
    silence into this loud refusal."""

    TOP_Z = 3.0

    def test_the_fixtures_own_top_surfaces_are_bit_identical_before_the_cut(self):
        """The degenerate contact itself, verified BEFORE the cut runs —
        this suite's own discipline, matching ``test_degeneracy.py``'s."""
        punch = _degeneracy_case1_punch(self.TOP_Z)
        block = _flat_topped_block(self.TOP_Z)
        assert punch.is_watertight
        assert block.is_watertight
        assert float(punch.vertices[:, 2].max()) == self.TOP_Z
        assert float(block.vertices[:, 2].max()) == self.TOP_Z

    def test_meshlib_difference_at_the_exact_coplanar_seam_raises_the_guard_not_silence(self):
        punch = _degeneracy_case1_punch(self.TOP_Z)
        block = _flat_topped_block(self.TOP_Z)
        kernel = meshlib_kernel.MeshLibKernel()

        with pytest.raises(ValueError) as excinfo:
            kernel.difference(block, [punch])
        message = str(excinfo.value)
        assert "guard" in message.lower()
        assert str(len(block.faces)) in message


@requires_meshlib
class TestGuardCatchesAnEmptyResult:
    """A boolean whose result is genuinely empty (two disjoint cubes'
    intersection) — the guard's OTHER branch, independent of the coplanar
    no-op above."""

    def test_intersection_of_disjoint_cubes_raises_the_guard_not_an_empty_mesh(self):
        a = _cube()
        b = _cube((100.0, 0.0, 0.0))
        kernel = meshlib_kernel.MeshLibKernel()
        with pytest.raises(ValueError) as excinfo:
            kernel.intersection(a, b)
        message = str(excinfo.value)
        assert "guard" in message.lower()
        assert "EMPTY" in message


# --------------------------------------------------------------------------
# the env-switch pins — the adapter's own side of CASE_PREP_BOOLEAN_KERNEL
# --------------------------------------------------------------------------
class TestEngineSwitchFromTheAdaptersSide:
    """``kernel.py``'s own half (default untouched, unknown value refused,
    read-once) is pinned in ``test_kernel.py::TestEngineSwitch``. These
    pins are the adapter's own side of the same contract."""

    @pytest.fixture(autouse=True)
    def _reset_engine_cache(self, monkeypatch):
        monkeypatch.setattr(kernel_module, "_engine_name", None)
        monkeypatch.setattr(kernel_module, "_kernels_by_engine", {})
        monkeypatch.delenv("CASE_PREP_BOOLEAN_KERNEL", raising=False)

    def test_default_untouched_when_unset(self):
        assert type(kernel_module.default_kernel()) is ManifoldKernel

    @requires_meshlib
    def test_meshlib_selected_returns_a_meshlib_kernel(self, monkeypatch):
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "meshlib")
        kernel = kernel_module.default_kernel()
        assert isinstance(kernel, meshlib_kernel.MeshLibKernel)

    def test_meshlib_selected_without_the_package_raises_immediately(self, monkeypatch):
        if MESHLIB_AVAILABLE:
            pytest.skip("meshlib IS importable here — this pin is "
                       "specifically the missing-package path")
        monkeypatch.setenv("CASE_PREP_BOOLEAN_KERNEL", "meshlib")
        with pytest.raises(ImportError) as excinfo:
            kernel_module.default_kernel()
        message = str(excinfo.value)
        assert "CASE_PREP_BOOLEAN_KERNEL" in message
        assert "license" in message.lower()


# --------------------------------------------------------------------------
# the pyproject pin — text-matched, per test_pyproject_pins.py's convention
# --------------------------------------------------------------------------
class TestPyprojectDeclaresNoMeshlibDependency:
    """Asserting meshlib is NOT importable would be wrong on the scratch
    evaluation venv this same file also runs under (the scoreboard run) —
    so, per ``test_pyproject_pins.py``'s own text-matched idiom (no TOML
    parser is a declared dependency), pin instead that ``pyproject.toml``
    never gained a meshlib dependency. This is true in every venv."""

    PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

    @staticmethod
    def _section(text: str, start: str, end: str) -> str:
        return text.split(start, 1)[1].split(end, 1)[0]

    def test_no_meshlib_dependency_in_project_dependencies(self):
        text = self.PYPROJECT.read_text()
        deps = self._section(text, "dependencies = [",
                             "[project.optional-dependencies]")
        assert not re.search(r'"meshlib', deps, re.IGNORECASE), (
            "meshlib must never be added to [project.dependencies] — the "
            "adapter is EVALUATION-tier only (kernel-decision-memo §4) "
            "and is imported lazily, inside MeshLibKernel.__init__, "
            "never at module import time")

    def test_no_meshlib_dependency_in_the_dev_extra(self):
        text = self.PYPROJECT.read_text()
        dev_list = self._section(text, "dev = [", "]")
        assert not re.search(r'"meshlib', dev_list, re.IGNORECASE)
