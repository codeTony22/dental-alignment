"""Adapter: the filesystem CapLibrary + library-driven cap detection.

Library layout: a directory of STLs named ``<type>-<diameter>.stl`` (e.g. ``certain-4.1.stl``).
Detection = template-match every library entry along the arch, then domain resolve_sites gives
count + center + type. Synthetic tests are self-contained; the real-arch test uses the client's
gitignored data when present.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters import client_data
from case_prep.adapters.cap_library import CapLibrary, detect_caps, parse_spec_filename
from case_prep.adapters.synthetic import make_scan_body_mesh
from case_prep.domain.cap_catalog import CapSpec

REAL_ARCH = Path(__file__).resolve().parents[1] / "data/real/QSS7S0G2_lower.obj"
REAL_CAD = client_data.LEGACY_SHELF_CAD


class TestParseSpecFilename:
    def test_parses_type_and_diameter(self):
        assert parse_spec_filename("certain-4.1.stl") == CapSpec("certain", "4.1")
        assert parse_spec_filename("tsv-4.5.stl") == CapSpec("tsv", "4.5")
        assert parse_spec_filename("neodent-gm-5020.stl") == CapSpec("neodent-gm", "5020")

    def test_rejects_unknown_type_or_malformed_name(self):
        for bad in ("certain.stl", "certain-abc.stl", "notes.txt", "UPPER-4.1.stl"):
            assert parse_spec_filename(bad) is None


class TestCapLibrary:
    def test_loads_templates_from_directory(self, tmp_path):
        make_scan_body_mesh().export(tmp_path / "certain-4.1.stl")
        make_scan_body_mesh().export(tmp_path / "tsv-4.5.stl")
        (tmp_path / "readme.txt").write_text("not a template")

        lib = CapLibrary.load(tmp_path)
        assert set(lib.specs) == {CapSpec("certain", "4.1"), CapSpec("tsv", "4.5")}

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(ValueError):
            CapLibrary.load(tmp_path)

    def test_single_constructor_for_stand_in_template(self):
        lib = CapLibrary.single(CapSpec("certain", "4.1"), make_scan_body_mesh())
        assert lib.specs == [CapSpec("certain", "4.1")]

    def test_subdirectories_are_not_globbed(self, tmp_path):
        """The archive directories (``superseded-YYYY-MM-DD/``) stay OUT of the default
        catalog: a widened glob would fold archived parts into every case's
        auto-identification candidate set and collide with the same-named current one."""
        make_scan_body_mesh().export(tmp_path / "certain-4.1.stl")
        (tmp_path / "superseded-2026-01-01").mkdir()
        make_scan_body_mesh().export(
            tmp_path / "superseded-2026-01-01/certain-4.1.stl")
        assert CapLibrary.load(tmp_path).specs == [CapSpec("certain", "4.1")]

    def test_an_explicitly_named_part_joins_the_catalog(self, tmp_path):
        """The 2026-07-25 escape hatch: the operator NAMES an archived part (label +
        file) and it loads alongside the current catalog — nothing is discovered."""
        make_scan_body_mesh().export(tmp_path / "certain-4.1.stl")
        archive = tmp_path / "superseded-2026-01-01"
        archive.mkdir()
        make_scan_body_mesh().export(archive / "certain-4.1.stl")

        lib = CapLibrary.load(tmp_path, extra={
            "superseded-2026-01-01--4.1": archive / "certain-4.1.stl"})
        assert set(lib.specs) == {CapSpec("certain", "4.1"),
                                  CapSpec("certain", "superseded-2026-01-01--4.1")}
        # the named part keeps the directory's model family — an explicit pick never
        # renames the system it belongs to
        assert {sp.model for sp in lib.specs} == {"certain"}
        assert "superseded-2026-01-01--4.1" in lib.variant_dimensions()

    def test_an_explicit_label_that_collides_is_refused(self, tmp_path):
        make_scan_body_mesh().export(tmp_path / "certain-4.1.stl")
        with pytest.raises(ValueError, match="duplicate cap template"):
            CapLibrary.load(tmp_path, extra={"4.1": tmp_path / "certain-4.1.stl"})


@pytest.mark.slow
def test_detect_caps_counts_and_types_on_synthetic_arch(tmp_path):
    """Self-contained gate for detect_caps (review finding: the core adapter had no
    deterministic green test): embed synthetic caps in a synthetic arch, detect, and check
    count + type + center."""
    from case_prep.adapters.real_case import build_embedded_case
    from case_prep.adapters.synthetic import make_gingiva_arch

    np.random.seed(0)  # trimesh surface sampling draws from the global RNG
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    make_scan_body_mesh().export(cad_path)

    case = tmp_path / "case"
    gt = build_embedded_case(arch_path, cad_path, case, n_implants=2, seed=1)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = CapLibrary.single(CapSpec("certain", "4.1"),
                            trimesh.load(case / "library/certain3i_4_1/mesh.stl", force="mesh"))

    sites = detect_caps(np.asarray(scan.vertices, float), lib,
                        normals=np.asarray(scan.vertex_normals, float))

    truths = np.array([p.position for p in gt.poses])
    assert len(sites) == 2
    for s in sites:
        assert s.spec == CapSpec("certain", "4.1")
        assert np.linalg.norm(truths - np.asarray(s.center), axis=1).min() < 2.5


@pytest.mark.skipif(not (REAL_ARCH.exists() and REAL_CAD.exists()),
                    reason="real arch/CAD data not present (gitignored)")
@pytest.mark.slow
def test_detect_caps_counts_and_types_on_real_arch(tmp_path):
    """The client flow, end-to-end: arch scan in -> how many caps + center + type out.
    Caps embedded in a real toothed arch; library = the real vendor CAD as certain-4.1."""
    from case_prep.adapters.real_case import build_embedded_case

    np.random.seed(0)  # pin the global RNG (trimesh sampling) for order-independence
    case = tmp_path / "case"
    gt = build_embedded_case(REAL_ARCH, REAL_CAD, case, n_implants=3, seed=3)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = CapLibrary.single(CapSpec("certain", "4.1"),
                            trimesh.load(case / "library/certain3i_4_1/mesh.stl", force="mesh"))

    sites = detect_caps(np.asarray(scan.vertices, float), lib,
                        normals=np.asarray(scan.vertex_normals, float))

    truths = np.array([p.position for p in gt.poses])
    assert len(sites) == 3  # the COUNT
    for s in sites:
        assert s.spec == CapSpec("certain", "4.1")  # the TYPE
        d = np.linalg.norm(truths - np.asarray(s.center), axis=1).min()
        assert d < 2.5, f"site center {s.center} is {d:.1f}mm from any true cap"  # the CENTER


def _squat_open_cap(diameter=8.0, height=3.5):
    """A low-profile healing cap as vendors ship them: cylindrical shell, closed top,
    OPEN base rim (the gingival side) — wider than tall."""
    cyl = trimesh.creation.cylinder(radius=diameter / 2.0, height=height, sections=48)
    keep = cyl.triangles_center[:, 2] > -height * 0.49  # drop the bottom disc -> open rim
    shell = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    shell.remove_unreferenced_vertices()
    return shell


class TestRevoluteCanonicalization:
    """Healing caps are SQUAT rotational parts: the tallest PCA axis is a DIAMETER, so
    PCA canonicalization puts a diameter on +z and every consumer of pose-z (implant
    axis record, cap-region removal, construction seating) inherits a sideways frame.
    The cap frame must come from the ROTATIONAL-SYMMETRY axis, open rim down."""

    def test_symmetry_axis_lands_on_z_regardless_of_input_pose(self):
        from case_prep.adapters.ingest import canonicalize_revolute

        cap = _squat_open_cap(diameter=8.0, height=3.5)
        spun = cap.copy()
        spun.apply_transform(
            trimesh.transformations.rotation_matrix(1.1, [1.0, 0.4, 0.2], [0, 0, 0]))
        spun.apply_translation([12.0, -7.0, 30.0])

        local, _ = canonicalize_revolute(spun)
        ext = local.bounds[1] - local.bounds[0]
        assert ext[2] == pytest.approx(3.5, abs=0.3)          # z = the cap HEIGHT
        assert ext[0] == pytest.approx(8.0, abs=0.3)          # x/y = the rim diameter
        assert ext[1] == pytest.approx(8.0, abs=0.3)

    def test_open_rim_faces_down(self):
        from case_prep.adapters.ingest import canonicalize_revolute

        cap = _squat_open_cap()
        flipped = cap.copy()
        flipped.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0], [0, 0, 0]))
        for mesh in (cap, flipped):
            local, _ = canonicalize_revolute(mesh)
            rim_z = np.concatenate([np.asarray(d, float) for d in local.outline().discrete])[:, 2]
            assert rim_z.mean() < 0.0  # gingival rim at the bottom of the local frame

    def test_idempotent(self):
        from case_prep.adapters.ingest import canonicalize_revolute

        once, _ = canonicalize_revolute(_squat_open_cap())
        twice, placement = canonicalize_revolute(once)
        assert np.allclose(np.asarray(once.vertices), np.asarray(twice.vertices))
        assert np.allclose(placement.matrix, np.eye(4))

    @pytest.mark.slow
    def test_cap_catalogs_stay_rim_seatable_whatever_their_aspect(self):
        """With the canonicalization fixed (axes no longer tilted), the narrow-tall
        neodent caps read taller than wide — the old aspect heuristic reclassified the
        whole catalog as 'scan bodies' and silently disabled the calibrated rim-first
        seating (measured: every neodent site fell to ICP). Aspect cannot separate a
        4030 cap (ratio 0.70) from a real scan body (the vendor scan body 0.97); the catalog's
        CONSTRUCTION is the truth — a directory of <model>-<variant> caps is a
        healing-cap library. The geometric fallback remains only for single-template
        stand-ins."""
        from case_prep.adapters.cap_library import CapLibrary
        from case_prep.domain.cap_catalog import CapSpec

        root = Path(__file__).parents[1] / "data/real/library/caps"
        if root.exists():
            for lib_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                assert CapLibrary.load(lib_dir).rim_seatable, \
                    f"{lib_dir.name}: a loaded cap catalog must seat rim-first"
        # stand-ins keep the geometric default: squat -> rim-seatable, tall -> not
        squat = CapLibrary.single(CapSpec("acme", "1"), _squat_open_cap(8.0, 3.5))
        assert squat.rim_seatable
        tall = trimesh.creation.cylinder(radius=2.5, height=9.0, sections=32)
        body = CapLibrary.single(CapSpec("acme", "2"), tall)
        assert not body.rim_seatable

    @pytest.mark.slow
    def test_real_library_files_keep_their_saved_axis(self):
        """Client audit ask (2026-07-15: 'make sure they are all top and down') — and
        the audit vindicated the client's files: EVERY manufacturer cap is saved
        axis-aligned (revolution error about file-z 0.05-0.09, near-perfect), while
        the PCA-candidate axis search TILTED every canonical template off it (4.1 to
        88.1 deg — the 6030s loaded fully SIDEWAYS, which is what made their seats
        look '90 deg rotated' and made zimmer t7 read as a 'sloped-cap outlier').
        The heavily-coded cutouts skew the covariance so no PCA axis is the symmetry
        axis. Canonicalization must keep the saved axis whenever the file verifies as
        axis-aligned; this guard names any future file that arrives rotated."""
        from case_prep.adapters.ingest import canonicalize_revolute

        root = Path(__file__).parents[1] / "data/real/library/caps"
        if not root.exists():
            pytest.skip("real cap libraries not present")
        checked = 0
        for lib_dir in sorted(root.iterdir()):
            if not lib_dir.is_dir():
                continue
            for path in sorted(lib_dir.glob("*.stl")):
                mesh = trimesh.load(path, force="mesh")
                _, placement = canonicalize_revolute(mesh)
                canon_z_in_file = np.asarray(placement.matrix)[:3, :3] @ np.array(
                    [0.0, 0.0, 1.0])
                tilt = float(np.degrees(np.arccos(
                    np.clip(abs(canon_z_in_file[2]), -1.0, 1.0))))
                assert tilt < 2.0, \
                    (f"{lib_dir.name}/{path.name}: canonical axis {tilt:.1f} deg off "
                     "the file's saved axis — either the loader broke the convention "
                     "again, or this file arrived rotated and must be fixed at intake")
                checked += 1
        assert checked >= 10, f"expected the full cap catalog, found {checked} files"

    def test_library_load_gives_caps_the_revolute_frame(self, tmp_path):
        d = tmp_path / "acme-1"
        d.mkdir()
        _squat_open_cap(diameter=8.0, height=3.5).export(d / "acme-1-7020.stl")
        lib = CapLibrary.load(d)
        ext_zip = [lib.template(s).bounds[1] - lib.template(s).bounds[0] for s in lib.specs]
        assert ext_zip[0][2] == pytest.approx(3.5, abs=0.3)   # squat cap: z = height, not Ø
