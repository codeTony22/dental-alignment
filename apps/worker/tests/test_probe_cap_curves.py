"""Pure/fast tests for tools/probe_cap_curves.py — the measurement appendix probe.

Pins the three instruments the healing-cap curve design cites: STL colour (attribute
bytes + trimesh visuals), local triangle density (cap ball vs tissue annulus), and
dihedral rim closure (24 bearings). Fixtures are synthetic meshes and hand-written
binary STLs; the real fleet is a separate slow class that pins the qualitative
claims (colour is absent; t4 density inverts; most rims close at 20° not 30°).

`tools/` isn't on pythonpath (only `src` is, per pyproject.toml), so this file inserts
`tools/` onto sys.path itself rather than touching shared config (fle_study precedent).
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import probe_cap_curves as probe  # noqa: E402  (path bootstrap must run first)

REAL_SCANS = Path(__file__).resolve().parents[1] / "data" / "real" / "scans"
real_scans_only = pytest.mark.skipif(
    not REAL_SCANS.is_dir(), reason="real scan tree not present")


# ----------------------------------------------------------------------------------
# Binary STL helpers
# ----------------------------------------------------------------------------------

def _write_binary_stl(path: Path, verts: np.ndarray, faces: np.ndarray,
                      attrs: np.ndarray, header: bytes = b"RealGUIDE (Binary STL)") -> None:
    """Write a binary STL with explicit per-facet attribute bytes (the colour channel)."""
    n = int(len(faces))
    hdr = header[:80].ljust(80, b"\0")
    buf = bytearray(hdr)
    buf += struct.pack("<I", n)
    v = np.asarray(verts, dtype=np.float32)
    f = np.asarray(faces, dtype=np.int64)
    a = np.asarray(attrs, dtype=np.uint16)
    for i, tri in enumerate(f):
        p0, p1, p2 = v[tri[0]], v[tri[1]], v[tri[2]]
        nrm = np.cross(p1 - p0, p2 - p0)
        nlen = float(np.linalg.norm(nrm))
        if nlen > 0:
            nrm = nrm / nlen
        buf += struct.pack("<12f", *nrm, *p0, *p1, *p2)
        buf += struct.pack("<H", int(a[i]))
    path.write_bytes(bytes(buf))


def _two_triangles() -> tuple[np.ndarray, np.ndarray]:
    verts = np.array([[0.0, 0.0, 0.0],
                      [1.0, 0.0, 0.0],
                      [0.0, 1.0, 0.0],
                      [1.0, 1.0, 0.0]], dtype=float)
    faces = np.array([[0, 1, 2], [1, 3, 2]], dtype=int)
    return verts, faces


# ----------------------------------------------------------------------------------
# Colour
# ----------------------------------------------------------------------------------

class TestStlColour:
    def test_zero_attribute_bytes_read_as_no_colour(self, tmp_path):
        verts, faces = _two_triangles()
        path = tmp_path / "plain.stl"
        _write_binary_stl(path, verts, faces, attrs=np.zeros(len(faces), dtype=np.uint16))
        reading = probe.read_stl_colour(path)
        assert reading.attr_nonzero == 0
        assert reading.n_faces == 2
        assert "RealGUIDE" in reading.header
        assert reading.distinct_vertex_colors == 0
        assert reading.distinct_face_colors == 0

    def test_nonzero_attribute_bytes_are_counted(self, tmp_path):
        verts, faces = _two_triangles()
        path = tmp_path / "tinted.stl"
        _write_binary_stl(path, verts, faces, attrs=np.array([0, 0x8000], dtype=np.uint16))
        reading = probe.read_stl_colour(path)
        assert reading.attr_nonzero == 1
        assert reading.n_faces == 2


# ----------------------------------------------------------------------------------
# Density
# ----------------------------------------------------------------------------------

def _grid_patch(origin: np.ndarray, size: float, n: int, z: float = 0.0):
    """Axis-aligned square of `n x n` quads (2 n^2 triangles) centred at origin."""
    xs = np.linspace(-size / 2, size / 2, n + 1) + origin[0]
    ys = np.linspace(-size / 2, size / 2, n + 1) + origin[1]
    verts = np.array([[x, y, z] for y in ys for x in xs], dtype=float)
    faces = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            b = a + 1
            c = a + (n + 1)
            d = c + 1
            faces.append([a, b, c])
            faces.append([b, d, c])
    return verts, np.array(faces, dtype=int)


def _stack_meshes(*parts):
    verts = []
    faces = []
    offset = 0
    for v, f in parts:
        verts.append(v)
        faces.append(f + offset)
        offset += len(v)
    return np.vstack(verts), np.vstack(faces)


class TestLocalDensity:
    def test_fine_cap_against_coarse_tissue_reads_ratio_above_one(self):
        # Fine 4 mm patch at the origin (inside the 3 mm cap ball) vs a coarse
        # 6 mm patch centred 9 mm away (inside the 6–12 mm tissue annulus).
        fine_v, fine_f = _grid_patch(np.zeros(3), size=4.0, n=20)
        coarse_v, coarse_f = _grid_patch(np.array([9.0, 0.0, 0.0]), size=6.0, n=2)
        v, f = _stack_meshes((fine_v, fine_f), (coarse_v, coarse_f))
        reading = probe.local_density(v, f, center=np.zeros(3))
        assert reading.ratio > 5.0
        assert reading.cap_tri_per_mm2 > reading.tissue_tri_per_mm2

    def test_inverted_tessellation_reads_ratio_below_one(self):
        coarse_v, coarse_f = _grid_patch(np.zeros(3), size=4.0, n=2)
        fine_v, fine_f = _grid_patch(np.array([9.0, 0.0, 0.0]), size=6.0, n=20)
        v, f = _stack_meshes((coarse_v, coarse_f), (fine_v, fine_f))
        reading = probe.local_density(v, f, center=np.zeros(3))
        assert reading.ratio < 1.0


# ----------------------------------------------------------------------------------
# Dihedral closure
# ----------------------------------------------------------------------------------

class TestDihedralClosure:
    def test_cylinder_rim_closes_most_bearings_at_twenty_degrees(self):
        cyl = trimesh.creation.cylinder(radius=2.5, height=4.0, sections=48)
        # Top rim is z = +2; centre on the top face, rim radius 2.5 mm.
        reading = probe.dihedral_closure(
            np.asarray(cyl.vertices, dtype=float),
            np.asarray(cyl.faces, dtype=int),
            center=np.array([0.0, 0.0, 2.0]),
            rim_r_mm=2.5,
        )
        assert reading.bearings_hit_20deg >= 20
        assert reading.n_bearings == 24

    def test_stl_exploded_vertices_still_close_the_rim(self):
        # Binary STL does not share vertices. Adjacency is empty until weld.
        cyl = trimesh.creation.cylinder(radius=2.5, height=4.0, sections=48)
        exploded = cyl.vertices[cyl.faces].reshape(-1, 3)
        faces = np.arange(len(exploded)).reshape(-1, 3)
        reading = probe.dihedral_closure(
            exploded, faces,
            center=np.array([0.0, 0.0, 2.0]),
            rim_r_mm=2.5,
        )
        assert reading.bearings_hit_20deg >= 20

    def test_smooth_sphere_closes_few_bearings_at_twenty_degrees(self):
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=5.0)
        reading = probe.dihedral_closure(
            np.asarray(sphere.vertices, dtype=float),
            np.asarray(sphere.faces, dtype=int),
            center=np.zeros(3),
            rim_r_mm=3.0,
        )
        assert reading.bearings_hit_20deg <= 4

    def test_thirty_degree_threshold_is_stricter_than_twenty(self):
        cyl = trimesh.creation.cylinder(radius=2.5, height=4.0, sections=48)
        reading = probe.dihedral_closure(
            np.asarray(cyl.vertices, dtype=float),
            np.asarray(cyl.faces, dtype=int),
            center=np.array([0.0, 0.0, 2.0]),
            rim_r_mm=2.5,
        )
        assert reading.bearings_hit_30deg <= reading.bearings_hit_20deg


# ----------------------------------------------------------------------------------
# Fleet walk (sites.json)
# ----------------------------------------------------------------------------------

class TestFleetDiscovery:
    def test_loads_sites_and_stl_from_a_doctor_folder(self, tmp_path):
        case = tmp_path / "doctor-acme-1"
        case.mkdir()
        (case / "sites.json").write_text(
            '{"suggested_sites": [{"tooth": 7, "center": [1, 2, 3], '
            '"center_mark": [1, 2, 3], "rim_mark": [4, 2, 3]}]}')
        verts, faces = _two_triangles()
        _write_binary_stl(case / "upper_jaw.stl", verts, faces,
                          attrs=np.zeros(len(faces), dtype=np.uint16))
        rows = probe.discover_fleet(tmp_path)
        assert len(rows) == 1
        assert rows[0].case_id == "acme-1"
        assert rows[0].tooth == 7
        assert rows[0].rim_r_mm == pytest.approx(3.0)


# ----------------------------------------------------------------------------------
# Real fleet — qualitative pins the design cites. Slow: nine 240k–466k face STLs.
# ----------------------------------------------------------------------------------

@real_scans_only
@pytest.mark.slow
class TestRealFleetQualitative:
    @pytest.fixture(scope="class")
    def report(self):
        return probe.probe_fleet(REAL_SCANS)

    def test_every_doctor_stl_has_zero_colour(self, report):
        assert report.colour, "probe found no STLs"
        for row in report.colour:
            assert row.attr_nonzero == 0, row.path
            assert row.distinct_vertex_colors == 0, row.path
            assert row.distinct_face_colors == 0, row.path

    def test_neodent_gm_t4_density_inverts(self, report):
        t4 = next(r for r in report.density
                  if r.case_id == "neodent-gm" and r.tooth == 4)
        assert t4.ratio < 1.0

    def test_most_sites_are_denser_on_the_cap_than_the_tissue(self, report):
        denser = [r for r in report.density if r.ratio > 1.2]
        assert len(denser) >= 7

    def test_median_twenty_degree_closure_is_a_partial_arc(self, report):
        hits = sorted(r.bearings_hit_20deg for r in report.closure)
        median = hits[len(hits) // 2]
        assert 14 <= median <= 24
        thirty = sorted(r.bearings_hit_30deg for r in report.closure)
        assert thirty[len(thirty) // 2] < median
