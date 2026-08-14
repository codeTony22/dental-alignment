"""Adapter: the industry-grounded case OUTPUT PACKAGE emitter.

Package = scan layer (raw jaw scan, byte-faithful) + per-site implant record
(scan-body CAD carrying the pose in-mesh, plus a JSON sidecar) + an optional
production set (only when a final prosthesis mesh is available) + a manifest
(SHA-256 over every emitted file) + an optional QC-only overlay mesh.
Synthetic tiny meshes only; no gitignored data, no engine/pipeline coupling.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.output_package import SitePackageSpec, emit_case_package


def _pose(translation=(0.0, 0.0, 0.0), axis_deg=0.0) -> np.ndarray:
    """A 4x4 local->world pose: rotate about Z by axis_deg, then translate."""
    theta = np.radians(axis_deg)
    c, s = np.cos(theta), np.sin(theta)
    m = np.eye(4)
    m[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    m[:3, 3] = translation
    return m


def _site(tooth: int, translation=(5.0, 0.0, 0.0), scan_coverage: float = 0.9,
         advisory: bool = False) -> SitePackageSpec:
    return SitePackageSpec(
        tooth=tooth,
        implant_model="neodent-gm",
        variant_code="5020",
        vendor="dess",
        pose_matrix=_pose(translation, axis_deg=30.0),
        scan_coverage=scan_coverage,
        advisory=advisory,
    )


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def jaw_scan() -> trimesh.Trimesh:
    return trimesh.creation.box(extents=[30.0, 20.0, 5.0])


@pytest.fixture
def healing_cap() -> trimesh.Trimesh:
    return trimesh.creation.cylinder(radius=2.0, height=3.0, sections=16)


@pytest.fixture
def construction_body() -> trimesh.Trimesh:
    return trimesh.creation.cylinder(radius=1.5, height=6.0, sections=16)


class TestFileInventory:
    def test_one_site_case_emits_scan_implant_record_and_manifest(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        site = _site(tooth=19)
        manifest = emit_case_package(
            "case-001", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        expected_names = {
            "case-001-lower.stl",
            "case-001-19-healingcap-aligned.stl",
            "case-001-19-scanbody-dess.stl",
            "case-001-19-implant.json",
            "case-001-manifest.json",
        }
        on_disk = {p.name for p in tmp_path.iterdir()}
        assert on_disk == expected_names
        # manifest.files enumerates every file it hashes, i.e. everything except
        # itself (it cannot hash its own bytes before they are written)
        assert {f.name for f in manifest.files} == expected_names - {"case-001-manifest.json"}

    def test_two_site_case_emits_one_record_per_site(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        sites = [
            (_site(tooth=19, translation=(5.0, 0.0, 0.0)), healing_cap, construction_body),
            (_site(tooth=30, translation=(-5.0, 0.0, 0.0)), healing_cap, construction_body),
        ]
        manifest = emit_case_package("case-002", jaw_scan, "lower", sites, tmp_path, overlay=False)

        for tooth in (19, 30):
            assert (tmp_path / f"case-002-{tooth}-healingcap-aligned.stl").exists()
            assert (tmp_path / f"case-002-{tooth}-scanbody-dess.stl").exists()
            assert (tmp_path / f"case-002-{tooth}-implant.json").exists()
        assert (tmp_path / "case-002-lower.stl").exists()
        assert (tmp_path / "case-002-manifest.json").exists()
        assert len(manifest.sites) == 2


class TestScanLayerUnmodified:
    def test_raw_scan_is_exported_byte_faithful(self, tmp_path, jaw_scan, healing_cap, construction_body):
        emit_case_package(
            "case-003", jaw_scan, "upper",
            [(_site(tooth=8), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        scan_path = tmp_path / "case-003-upper.stl"
        reloaded = trimesh.load(scan_path, force="mesh", process=False)

        # Same triangle soup (as a set, order-independent) within STL's float32 precision —
        # the hard norm is "never alter the source scan geometry", not "byte-for-byte file".
        orig_tris = np.sort(jaw_scan.vertices[jaw_scan.faces].reshape(-1))
        new_tris = np.sort(reloaded.vertices[reloaded.faces].reshape(-1))
        assert orig_tris.shape == new_tris.shape
        assert np.allclose(orig_tris, new_tris, atol=1e-4)

    def test_scan_export_does_not_mutate_the_input_mesh(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        before = jaw_scan.vertices.copy()
        emit_case_package(
            "case-004", jaw_scan, "upper",
            [(_site(tooth=8), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        assert np.array_equal(jaw_scan.vertices, before)


class TestAlignedMeshesAreTransformed:
    def test_healing_cap_centroid_moves_by_pose_translation(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        site = _site(tooth=19, translation=(12.0, -4.0, 2.0))
        emit_case_package(
            "case-005", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        aligned = trimesh.load(tmp_path / "case-005-19-healingcap-aligned.stl", force="mesh")
        expected_centroid = site.pose_matrix[:3, :3] @ healing_cap.centroid + site.pose_matrix[:3, 3]
        assert np.allclose(aligned.centroid, expected_centroid, atol=1e-3)
        assert not np.allclose(aligned.centroid, healing_cap.centroid, atol=1e-3)

    def test_scanbody_centroid_moves_by_pose_translation(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        site = _site(tooth=19, translation=(12.0, -4.0, 2.0))
        emit_case_package(
            "case-006", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        aligned = trimesh.load(tmp_path / "case-006-19-scanbody-dess.stl", force="mesh")
        expected_centroid = (
            site.pose_matrix[:3, :3] @ construction_body.centroid + site.pose_matrix[:3, 3]
        )
        assert np.allclose(aligned.centroid, expected_centroid, atol=1e-3)


class TestImplantJson:
    def test_contents_and_pose_round_trip(self, tmp_path, jaw_scan, healing_cap, construction_body):
        site = _site(tooth=19, translation=(12.0, -4.0, 2.0), scan_coverage=0.87,
                     advisory=False)
        emit_case_package(
            "case-007", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        payload = json.loads((tmp_path / "case-007-19-implant.json").read_text())
        assert payload["case_id"] == "case-007"
        assert payload["tooth"] == 19
        assert payload["implant_model"] == "neodent-gm"
        assert payload["variant_code"] == "5020"
        assert payload["vendor"] == "dess"
        assert payload["scan_coverage"] == pytest.approx(0.87)
        assert payload["advisory"] is False
        assert payload["units"] == "mm"
        assert payload["frame"] == "jaw-scan world frame"

        pose_back = np.array(payload["pose_matrix"])
        assert pose_back.shape == (4, 4)
        assert np.allclose(pose_back, site.pose_matrix)

        assert np.allclose(payload["position"], site.pose_matrix[:3, 3])
        expected_axis = site.pose_matrix[:3, :3] @ np.array([0.0, 0.0, 1.0])
        assert np.allclose(payload["axis"], expected_axis)

    def test_package_keys_say_what_they_carry(self, tmp_path, jaw_scan, healing_cap,
                                              construction_body):
        """DELIBERATE RENAME sweep (master plan §1 DELIVER row + §8 item 12/slice 11):
        the coverage figure ships as ``scan_coverage`` — a fresh implant.json (or
        manifest) carrying the old mislabeled ``fitness`` key, or a dual-write of
        both, FAILS here. And ``pose_origin`` — the honesty field that existed on
        SitePackageSpec but never reached the sidecar — must now be written, so a
        consumer can never mistake a component pose for the implant platform."""
        emit_case_package(
            "case-keys", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        payload = json.loads((tmp_path / "case-keys-19-implant.json").read_text())
        assert "fitness" not in payload, \
            "the mislabeled 'fitness' key reappeared in a fresh implant.json"
        assert payload["scan_coverage"] == pytest.approx(0.9)
        assert payload["pose_origin"] == "component"

        manifest = json.loads((tmp_path / "case-keys-manifest.json").read_text())
        (site_row,) = manifest["sites"]
        assert "fitness" not in site_row, \
            "the mislabeled 'fitness' key reappeared in a fresh manifest site row"
        assert site_row["scan_coverage"] == pytest.approx(0.9)


class TestManifest:
    def test_hashes_verify_against_emitted_files(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        manifest = emit_case_package(
            "case-008", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )

        payload = json.loads((tmp_path / "case-008-manifest.json").read_text())
        assert payload["case_id"] == "case-008"
        assert payload["jaw"] == "lower"
        assert payload["units"] == "mm"
        assert payload["tooth_numbering"] == "universal"

        for entry in payload["files"]:
            on_disk = tmp_path / entry["name"]
            assert on_disk.exists()
            assert entry["sha256"] == _sha256(on_disk)
            assert entry["bytes"] == on_disk.stat().st_size

        # the manifest lists itself too, and every entry is reachable from the manifest object
        names_in_json = {f["name"] for f in payload["files"]}
        names_in_manifest = {f.name for f in manifest.files}
        assert names_in_json == names_in_manifest

    def test_advisory_propagates_from_any_site(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        sites = [
            (_site(tooth=19, translation=(5.0, 0.0, 0.0), advisory=False), healing_cap, construction_body),
            (_site(tooth=30, translation=(-5.0, 0.0, 0.0), advisory=True), healing_cap, construction_body),
        ]
        emit_case_package("case-009", jaw_scan, "lower", sites, tmp_path, overlay=False)

        payload = json.loads((tmp_path / "case-009-manifest.json").read_text())
        assert payload["advisory_note"] == "advisory mode: all sites routed to human review"
        site_rows = {s["tooth"]: s for s in payload["sites"]}
        assert site_rows[19]["advisory"] is False
        assert site_rows[30]["advisory"] is True

    def test_no_advisory_note_when_all_sites_clear(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        emit_case_package(
            "case-010", jaw_scan, "lower",
            [(_site(tooth=19, advisory=False), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        payload = json.loads((tmp_path / "case-010-manifest.json").read_text())
        assert "advisory_note" not in payload


class TestProductionSet:
    def test_absent_without_final_product_mesh(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        emit_case_package(
            "case-011", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        assert not (tmp_path / "case-011-19-prosthesis_cad.stl").exists()
        assert not (tmp_path / "case-011-19-construction.json").exists()

    def test_present_with_final_product_mesh(self, tmp_path, jaw_scan, healing_cap, construction_body):
        prosthesis = trimesh.creation.box(extents=[6.0, 6.0, 8.0])
        site = _site(tooth=19)
        manifest = emit_case_package(
            "case-012", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, final_product_mesh={19: prosthesis}, overlay=False,
        )

        cad_path = tmp_path / "case-012-19-prosthesis_cad.stl"
        sidecar_path = tmp_path / "case-012-19-construction.json"
        assert cad_path.exists()
        assert sidecar_path.exists()
        assert {f.name for f in manifest.files} >= {cad_path.name, sidecar_path.name}

        payload = json.loads(sidecar_path.read_text())
        expected_axis = site.pose_matrix[:3, :3] @ np.array([0.0, 0.0, 1.0])
        assert np.allclose(payload["insertion_axis"], expected_axis)
        assert np.allclose(payload["implant_direction"], expected_axis)
        assert payload["implant_model"] == "neodent-gm"
        assert payload["variant_code"] == "5020"
        assert payload["vendor"] == "dess"
        assert payload["margin"] is None
        assert payload["material"] is None
        assert "library_ref" in payload

        aligned_prosthesis = trimesh.load(cad_path, force="mesh")
        # exocad `_cad.stl` naming convention: the mesh itself carries the aligned geometry too
        assert not np.allclose(aligned_prosthesis.centroid, prosthesis.centroid, atol=1e-3) or \
            np.allclose(site.pose_matrix[:3, 3], [0, 0, 0])


class TestQcOverlay:
    def test_overlay_defaults_on_and_contains_summed_vertices(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        site = _site(tooth=19)
        emit_case_package(
            "case-013", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path,
        )

        overlay_path = tmp_path / "case-013-lower-overlay.stl"
        assert overlay_path.exists()
        # default (welding) load: STL itself has no vertex-sharing concept, so an
        # unprocessed reload always yields 3 vertices/face regardless of topology;
        # welding recovers the shared-vertex mesh, which is what "sum of vertices"
        # means for these geometrically-disjoint parts.
        overlay = trimesh.load(overlay_path, force="mesh")

        expected_total = len(jaw_scan.vertices) + len(healing_cap.vertices) + len(construction_body.vertices)
        assert len(overlay.vertices) == expected_total

    def test_overlay_omitted_when_disabled(self, tmp_path, jaw_scan, healing_cap, construction_body):
        emit_case_package(
            "case-014", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        assert not (tmp_path / "case-014-lower-overlay.stl").exists()


class TestExtraFiles:
    """``extra_files`` ride in the hashed manifest like any deliverable — so the
    manifest contract (every listed name is in the package dir, every hash verifies)
    must be enforced at the door, not assumed of the caller."""

    def _emit(self, tmp_path, jaw_scan, healing_cap, construction_body, extras):
        return emit_case_package(
            "case-020", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False, extra_files=extras,
        )

    def test_extra_file_is_hashed_into_the_manifest(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        extra = tmp_path / "case-020-19-clockview.png"
        extra.write_bytes(b"png-bytes")
        manifest = self._emit(tmp_path, jaw_scan, healing_cap, construction_body, [extra])
        rec = {f.name: f for f in manifest.files}["case-020-19-clockview.png"]
        assert rec.sha256 == _sha256(extra), "extra file's manifest hash must verify"

    def test_missing_extra_file_refused(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        with pytest.raises(ValueError, match="missing on disk"):
            self._emit(tmp_path, jaw_scan, healing_cap, construction_body,
                       [tmp_path / "never-written.png"])

    def test_extra_file_outside_package_dir_refused(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        stray = elsewhere / "stray.png"
        stray.write_bytes(b"png-bytes")
        with pytest.raises(ValueError, match="outside the package dir"):
            self._emit(tmp_path / "pkg", jaw_scan, healing_cap, construction_body,
                       [stray])

    def test_extra_file_shadowing_an_emitted_name_refused(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        # the emitter itself writes case-020-lower.stl; an extra with that name would
        # put two entries under one manifest key
        with pytest.raises(ValueError, match="duplicates a package file name"):
            self._emit(tmp_path, jaw_scan, healing_cap, construction_body,
                       [tmp_path / "case-020-lower.stl"])


class TestDesignRuleGate:
    """G5 wiring: every production part runs the pre-export design-rule gate BEFORE
    any file is written — advisory findings land in the manifest's ``design_rules``
    block; a catastrophic (unmanufacturable) part fails CLOSED with nothing emitted."""

    @staticmethod
    def _sealed_lumen_tube() -> trimesh.Trimesh:
        """DESS-shaped construction part: designed lumen r=2.0 recorded by a single
        open boundary loop (same fixture family as tests/test_design_rules.py)."""
        outer = trimesh.creation.revolve(
            np.array([[0.0, 12.0], [3.0, 12.0], [3.0, 0.0], [0.0, 0.0]]), sections=64)
        inner = trimesh.creation.revolve(
            np.array([[0.0, 9.0], [2.0, 9.0], [2.0, 0.0]]), sections=64)
        return trimesh.util.concatenate([outer, inner])

    def test_manifest_carries_advisory_design_rules_block(
        self, tmp_path, jaw_scan, healing_cap
    ):
        # emitted channel r=1.0 vs the vendor's designed lumen r=2.0 — the halved-
        # lumen defect must ride in the manifest as an ADVISORY flag (never a block)
        construction = self._sealed_lumen_tube()
        halved_bore_product = trimesh.creation.annulus(
            r_min=1.0, r_max=3.0, height=10.0, sections=64)
        site = _site(tooth=19)
        manifest = emit_case_package(
            "case-030", jaw_scan, "lower",
            [(site, healing_cap, construction)],
            tmp_path, final_product_mesh={19: halved_bore_product}, overlay=False,
        )

        payload = json.loads((tmp_path / "case-030-manifest.json").read_text())
        assert payload["design_rules"] == list(manifest.design_rules)
        (row,) = payload["design_rules"]
        assert row["tooth"] == 19
        assert row["verdict"] == "flag"
        by_rule = {c["rule"]: c for c in row["checks"]}
        assert set(by_rule) == {"channel_lumen_match", "min_wall_thickness",
                                "channel_angulation", "seal_census"}
        lumen = by_rule["channel_lumen_match"]
        assert lumen["verdict"] == "flag"
        assert lumen["value"] == pytest.approx(1.0, abs=0.05)
        assert lumen["bound"] == pytest.approx(2.0, abs=0.05)
        assert by_rule["seal_census"]["verdict"] == "pass"
        assert "19" in payload["design_rule_note"]
        # advisory means advisory: the flagged package still shipped in full
        assert (tmp_path / "case-030-19-prosthesis_cad.stl").exists()

    def test_catastrophic_violation_fails_closed(self, tmp_path, jaw_scan, healing_cap):
        # a fragmented (two-body) "product" is not manufacturable: the gate must
        # refuse the WHOLE package before a single file exists on disk
        fragmented = trimesh.util.concatenate([
            trimesh.creation.box(extents=[4.0, 4.0, 8.0]),
            trimesh.creation.box(extents=[4.0, 4.0, 8.0]).apply_translation([10.0, 0.0, 0.0]),
        ])
        out = tmp_path / "pkg"
        with pytest.raises(ValueError, match="catastrophic"):
            emit_case_package(
                "case-031", jaw_scan, "lower",
                [(_site(tooth=19), healing_cap, self._sealed_lumen_tube())],
                out, final_product_mesh={19: fragmented}, overlay=False,
            )
        assert not out.exists(), "fail-closed means NOTHING emitted, not a partial package"

    def test_no_design_rules_block_without_production_set(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        manifest = emit_case_package(
            "case-032", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        payload = json.loads((tmp_path / "case-032-manifest.json").read_text())
        assert "design_rules" not in payload
        assert "design_rule_note" not in payload
        assert manifest.design_rules == ()


REAL_LIBRARY = Path(__file__).resolve().parents[1] / "data" / "real" / "library"


def _real_product(construction_rel: str, model: str, variant: str, offset_mm: float):
    """The real vendor construction part built exactly as the pipeline builds it: bored
    at the identified cap's loop-truth channel (G1), relieved by ``offset_mm``."""
    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.domain.channel import channel_from_boundary_loops
    from case_prep.pipeline.final_product import build_final_product

    library = CapLibrary.load(REAL_LIBRARY / "caps" / model)
    spec = next(sp for sp in library.specs if sp.variant == variant)
    channel = channel_from_boundary_loops(library.template(spec))
    vendor = trimesh.load(REAL_LIBRARY / "construction" / construction_rel, force="mesh")
    return vendor, build_final_product(vendor, library_channel=channel,
                                       gingival_offset_mm=offset_mm)


@pytest.mark.skipif(not REAL_LIBRARY.is_dir(), reason="real library not present")
class TestGingivalReliefBlock:
    """The relief is a PROPOSAL the export gate still judges (2026-07-25).

    MEASURED, on the real vendor parts at the client's 0.20mm default:
      atlantis/zimmer-4.5-scanbody  wall 0.224mm at offset 0 -> the relief eats the
                                    channel and the as-built channel is UNMEASURABLE,
                                    while G5's worst verdict is still only "flag"
      dess/neodent-gm-scanbody      wall 0.568 -> 0.330mm, channel intact throughout

    So a part whose channel the relief DESTROYED fails closed; a part whose wall the
    relief merely thinned stays advisory — blocking that would refuse the client's own
    default configuration and is the design-rule flag's job, not the gate's."""

    def test_the_client_offset_blocks_the_atlantis_part(self, tmp_path, jaw_scan,
                                                        healing_cap):
        vendor, product = _real_product("atlantis/zimmer-4.5-scanbody.stl",
                                        "zimmer-4.5", "7030", 0.20)
        relief = product.metadata["gingival_offset"]
        # the receipts this block rests on, re-measured here rather than asserted from a
        # comment: measurable before the relief, gone after
        assert relief["pre_offset"]["measurable"] is True
        assert relief["pre_offset"]["min_wall_mm"] == pytest.approx(0.224, abs=0.02)
        assert relief["post_offset"]["measurable"] is False

        site = SitePackageSpec(tooth=29, implant_model="zimmer-4.5",
                               variant_code="7030", vendor="atlantis",
                               pose_matrix=np.eye(4), scan_coverage=0.6, advisory=True)
        out = tmp_path / "pkg"
        with pytest.raises(ValueError, match="package NOT emitted") as exc:
            emit_case_package("atl", jaw_scan, "lower",
                              [(site, healing_cap, vendor)], out,
                              final_product_mesh={29: product}, overlay=False)
        message = str(exc.value)
        assert "gingival-relief gate" in message
        assert "tooth 29 (atlantis/zimmer-4.5 7030)" in message, \
            "the refusal must name the part a human has to act on"
        assert "smaller gingival offset" in message
        assert not out.exists(), "fail-closed means NOTHING emitted"

    def test_the_same_atlantis_part_ships_at_offset_zero(self, tmp_path, jaw_scan,
                                                         healing_cap):
        # offset 0 leaves the vendor part's OWN thin wall (0.224mm) — under the 0.5mm
        # rule and flagged as such, but nothing the relief did, so it ships advisory
        # exactly as before this gate existed
        vendor, product = _real_product("atlantis/zimmer-4.5-scanbody.stl",
                                        "zimmer-4.5", "7030", 0.0)
        site = SitePackageSpec(tooth=29, implant_model="zimmer-4.5",
                               variant_code="7030", vendor="atlantis",
                               pose_matrix=np.eye(4), scan_coverage=0.6, advisory=True)
        manifest = emit_case_package("atl0", jaw_scan, "lower",
                                     [(site, healing_cap, vendor)], tmp_path,
                                     final_product_mesh={29: product}, overlay=False)
        assert (tmp_path / "atl0-29-prosthesis_cad.stl").exists()
        (row,) = manifest.design_rules
        wall = next(c for c in row["checks"] if c["rule"] == "min_wall_thickness")
        assert wall["verdict"] == "flag" and wall["value"] < 0.5
        assert row["verdict"] == "flag"        # advisory, not a block

    def test_the_dess_part_ships_at_the_client_offset(self, tmp_path, jaw_scan,
                                                      healing_cap):
        vendor, product = _real_product("dess/neodent-gm-scanbody.stl",
                                        "neodent-gm", "6030", 0.20)
        relief = product.metadata["gingival_offset"]
        assert relief["pre_offset"]["min_wall_mm"] == pytest.approx(0.568, abs=0.02)
        assert relief["post_offset"]["min_wall_mm"] == pytest.approx(0.330, abs=0.02)

        site = SitePackageSpec(tooth=29, implant_model="neodent-gm",
                               variant_code="6030", vendor="dess",
                               pose_matrix=np.eye(4), scan_coverage=0.6, advisory=True)
        manifest = emit_case_package("dss", jaw_scan, "lower",
                                     [(site, healing_cap, vendor)], tmp_path,
                                     final_product_mesh={29: product}, overlay=False)
        assert (tmp_path / "dss-29-prosthesis_cad.stl").exists()
        # thinned under the rule BY the relief — advisory, deliberately not a block
        (row,) = manifest.design_rules
        wall = next(c for c in row["checks"] if c["rule"] == "min_wall_thickness")
        assert wall["verdict"] == "flag" and wall["value"] == pytest.approx(0.33, abs=0.02)

        # ...and the ACHIEVED clearance rides in the paid record and the manifest
        payload = json.loads((tmp_path / "dss-manifest.json").read_text())
        (clearance,) = payload["gingival_clearance"]
        assert clearance["tooth"] == 29
        assert clearance["requested_mm"] == 0.20
        assert 0.05 < clearance["achieved_median_mm"] < 0.20
        assert "gingival_clearance_note" in payload
        rec = json.loads((tmp_path / "dss-29-implant.json").read_text())
        assert rec["audit"]["gingival_clearance"]["achieved_median_mm"] == \
            clearance["achieved_median_mm"]
        assert "tooth" not in rec["audit"]["gingival_clearance"]

    def test_the_same_dess_part_blocks_on_a_cap_whose_wall_had_no_margin(
        self, tmp_path, jaw_scan, healing_cap
    ):
        """The block is about the PART AS BORED, not about the vendor's name: the same
        dess construction bored at the 5020 cap's channel starts at a 0.389mm wall — under
        the 0.5mm rule before any relief — and the client's 0.20mm takes it to 0.105mm.
        A wall with no margin to give is the case rule (b) exists for."""
        vendor, product = _real_product("dess/neodent-gm-scanbody.stl",
                                        "neodent-gm", "5020", 0.20)
        relief = product.metadata["gingival_offset"]
        assert relief["pre_offset"]["min_wall_mm"] == pytest.approx(0.389, abs=0.02)
        assert relief["post_offset"]["min_wall_mm"] == pytest.approx(0.105, abs=0.02)
        assert relief["post_offset"]["measurable"] is True, \
            "this is the WALL arm — the channel itself survived"

        site = SitePackageSpec(tooth=13, implant_model="neodent-gm",
                               variant_code="5020", vendor="dess",
                               pose_matrix=np.eye(4), scan_coverage=0.6, advisory=True)
        out = tmp_path / "pkg"
        with pytest.raises(ValueError, match="already-undersized channel wall") as exc:
            emit_case_package("dss5", jaw_scan, "lower",
                              [(site, healing_cap, vendor)], out,
                              final_product_mesh={13: product}, overlay=False)
        assert "tooth 13 (dess/neodent-gm 5020)" in str(exc.value)
        assert not out.exists()

    def test_a_product_without_relief_receipts_is_never_blocked(self, tmp_path, jaw_scan,
                                                                healing_cap):
        # the gate reads receipts the builder measured; a product from anywhere else
        # (an older package, a hand-made mesh) is emitted, never blocked on absence
        product = trimesh.creation.annulus(r_min=1.0, r_max=3.0, height=10.0,
                                           sections=64)
        assert "gingival_offset" not in product.metadata
        emit_case_package("noreceipt", jaw_scan, "lower",
                          [(_site(tooth=19), healing_cap,
                            TestDesignRuleGate._sealed_lumen_tube())],
                          tmp_path, final_product_mesh={19: product}, overlay=False)
        assert (tmp_path / "noreceipt-19-prosthesis_cad.stl").exists()


def test_registering_files_rehashes_them_into_an_existing_manifest(tmp_path, jaw_scan,
                                                                   healing_cap,
                                                                   construction_body):
    """An operator adjustment rewrites the site's cap STL / implant.json in place and
    adds the alignment proof — ``register_package_files`` keeps the manifest's own
    contract ("every listed name exists and its hash verifies") true afterwards."""
    from case_prep.adapters.output_package import register_package_files

    emit_case_package("reg", jaw_scan, "lower",
                      [(_site(tooth=19), healing_cap, construction_body)],
                      tmp_path, overlay=False)
    manifest_path = tmp_path / "reg-manifest.json"
    cap = tmp_path / "reg-19-healingcap-aligned.stl"
    stale = {f["name"]: f["sha256"]
             for f in json.loads(manifest_path.read_text())["files"]}[cap.name]

    cap.write_bytes(cap.read_bytes() + b"\n")          # the re-emit
    proof = tmp_path / "reg-19-alignment-proof.png"
    proof.write_bytes(b"not really a png")             # the new deliverable
    records = register_package_files(manifest_path, [cap, proof])
    assert [r.name for r in records] == [cap.name, proof.name]

    files = {f["name"]: f for f in json.loads(manifest_path.read_text())["files"]}
    assert files[cap.name]["sha256"] != stale          # replaced, not duplicated
    assert files[cap.name]["sha256"] == _sha256(cap)
    assert files[proof.name]["sha256"] == _sha256(proof)
    assert len([f for f in json.loads(manifest_path.read_text())["files"]
                if f["name"] == cap.name]) == 1
    # every other record still verifies — a targeted update, not a rewrite
    for name, rec in files.items():
        assert rec["sha256"] == _sha256(tmp_path / name)


def test_registering_a_file_outside_the_package_is_refused(tmp_path, jaw_scan,
                                                           healing_cap,
                                                           construction_body):
    from case_prep.adapters.output_package import register_package_files

    out = tmp_path / "pkg"
    emit_case_package("reg2", jaw_scan, "lower",
                      [(_site(tooth=19), healing_cap, construction_body)],
                      out, overlay=False)
    stray = tmp_path / "elsewhere.png"
    stray.write_bytes(b"x")
    with pytest.raises(ValueError, match="outside the package dir"):
        register_package_files(out / "reg2-manifest.json", [stray])
    with pytest.raises(ValueError, match="not on disk"):
        register_package_files(out / "reg2-manifest.json", [out / "missing.png"])


def test_implant_record_carries_the_audit_trail(tmp_path):
    """Business item (ROI loop it.2): the paid per-site record must carry the numbers the
    demo shows — registration error, seed provenance, seat method, guidance outcome,
    declared-vs-identified — not just the pose. ``audit_by_tooth`` merges them in."""
    import trimesh

    from case_prep.adapters.output_package import SitePackageSpec, emit_case_package

    jaw = trimesh.creation.box(extents=[30, 20, 6])
    cap = trimesh.creation.cylinder(radius=2.5, height=4.0)
    body = trimesh.creation.cylinder(radius=1.5, height=8.0)
    spec = SitePackageSpec(tooth=8, implant_model="acme-1", variant_code="5020",
                           vendor="dess", pose_matrix=np.eye(4), scan_coverage=0.5,
                           advisory=True)
    audit = {8: {"fit": {"avg_mm": 0.42, "max_mm": 1.9}, "seed_source": "brush",
                 "seat_method": "rim", "guidance_level": "ready",
                 "declared_variant": "5020"}}
    emit_case_package("audit-case", jaw, "upper", [(spec, cap, body)], tmp_path,
                      audit_by_tooth=audit)
    rec = json.loads((tmp_path / "audit-case-8-implant.json").read_text())
    assert rec["audit"]["fit"]["avg_mm"] == 0.42
    assert rec["audit"]["seed_source"] == "brush"
    assert rec["audit"]["seat_method"] == "rim"
    assert rec["audit"]["guidance_level"] == "ready"


class TestArtifactFacts:
    """ARTIFACT FACTS IN THE MANIFEST (boolean-engine plan 4c / clinical-pipeline-plan
    Stage 5): every emitted STL's manifest entry grows an optional ``facts`` object —
    ``triangle_count`` and ``watertight`` (trimesh's own reading AT WRITE TIME — this
    IS the open/closed fact: an open-arch artifact reads False, a closed model reads
    True). Non-STL files (json/png/html) carry no ``facts`` key at all — absence, not
    an empty object. No third ``notes`` field: the fallback/degradation notes already
    flow per ROW (production block), keyed by tooth, not by artifact filename — a
    composite note can cover several files or none, so threading it onto one file's
    facts would duplicate or silently drop the many-to-many cases."""

    def test_every_stl_entry_carries_facts_matching_the_actual_on_disk_mesh(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        prosthesis = trimesh.creation.box(extents=[6.0, 6.0, 8.0])
        site = _site(tooth=19)
        emit_case_package(
            "case-040", jaw_scan, "lower",
            [(site, healing_cap, construction_body)],
            tmp_path, final_product_mesh={19: prosthesis},
        )  # overlay defaults on — exercises the overlay STL's facts too

        payload = json.loads((tmp_path / "case-040-manifest.json").read_text())
        by_name = {f["name"]: f for f in payload["files"]}
        stl_names = {n for n in by_name if n.endswith(".stl")}
        assert stl_names == {
            "case-040-lower.stl",
            "case-040-19-healingcap-aligned.stl",
            "case-040-19-scanbody-dess.stl",
            "case-040-19-prosthesis_cad.stl",
            "case-040-lower-overlay.stl",
        }
        for name in stl_names:
            entry = by_name[name]
            assert "facts" in entry, f"{name} carries no facts block"
            reloaded = trimesh.load(tmp_path / name, force="mesh")
            assert entry["facts"]["triangle_count"] == len(reloaded.faces)
            assert entry["facts"]["watertight"] == bool(reloaded.is_watertight)

    def test_non_stl_entries_carry_no_facts_key(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        prosthesis = trimesh.creation.box(extents=[6.0, 6.0, 8.0])
        emit_case_package(
            "case-041", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, final_product_mesh={19: prosthesis}, overlay=False,
        )
        payload = json.loads((tmp_path / "case-041-manifest.json").read_text())
        by_name = {f["name"]: f for f in payload["files"]}
        for name in ("case-041-19-implant.json", "case-041-19-construction.json"):
            assert "facts" not in by_name[name], \
                f"{name} is not a mesh — it must carry no facts block, not an empty one"

    def test_an_open_surface_reads_false_a_closed_solid_reads_true(
        self, tmp_path, healing_cap, construction_body
    ):
        """The literal client fact this block exists to carry: an open-arch artifact
        (a scan surface, not a solid) reads watertight False; a genuinely closed
        solid reads True. The stock fixtures (box/cylinder primitives) are all
        watertight by construction, so this test builds its own open mesh — one
        triangle deleted from a closed box leaves a hole."""
        box = trimesh.creation.box(extents=[30.0, 20.0, 5.0])
        open_scan = trimesh.Trimesh(vertices=box.vertices.copy(),
                                    faces=box.faces[:-1].copy(), process=False)
        assert not open_scan.is_watertight, "fixture sanity: must actually be open"

        emit_case_package(
            "case-042", open_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        payload = json.loads((tmp_path / "case-042-manifest.json").read_text())
        by_name = {f["name"]: f for f in payload["files"]}
        assert by_name["case-042-lower.stl"]["facts"]["watertight"] is False
        assert by_name["case-042-19-healingcap-aligned.stl"]["facts"]["watertight"] is True

    def test_package_manifest_dataclass_mirrors_the_same_facts(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        manifest = emit_case_package(
            "case-043", jaw_scan, "lower",
            [(_site(tooth=19), healing_cap, construction_body)],
            tmp_path, overlay=False,
        )
        payload = json.loads((tmp_path / "case-043-manifest.json").read_text())
        json_facts = {f["name"]: f.get("facts") for f in payload["files"]}
        for record in manifest.files:
            if record.facts is None:
                assert json_facts[record.name] is None
            else:
                assert json_facts[record.name] == record.facts.as_json()


class TestRegisterPackageFilesFacts:
    """``register_package_files`` — the composite-artifact seam (arch/socket/model
    layers, scanned-cap isolation) — carries the SAME facts contract: caller-provided
    facts ride verbatim (no reload of the file the call just re-hashed), an omitted
    STL falls back to loading the file it just hashed, and a non-STL name carries no
    facts at all."""

    def test_caller_provided_facts_ride_verbatim_with_no_disk_reload(
        self, tmp_path, jaw_scan, healing_cap, construction_body, monkeypatch
    ):
        import case_prep.adapters.output_package as op
        from case_prep.adapters.output_package import MeshFacts, register_package_files

        emit_case_package("reg-facts", jaw_scan, "lower",
                          [(_site(tooth=19), healing_cap, construction_body)],
                          tmp_path, overlay=False)
        composite = tmp_path / "reg-facts-composite.stl"
        trimesh.creation.icosphere(subdivisions=1).export(composite)

        calls = []
        monkeypatch.setattr(op, "_facts_from_disk", lambda p: calls.append(p))

        # deliberately WRONG relative to what the file on disk would measure — this
        # proves the caller's own reading rides verbatim rather than being silently
        # recomputed, not merely that SOME facts landed
        provided = MeshFacts(triangle_count=999999, watertight=False)
        records = register_package_files(
            tmp_path / "reg-facts-manifest.json", [composite],
            facts_by_name={composite.name: provided})

        assert calls == [], "the load fallback must not fire when facts are provided"
        assert records[0].facts == provided
        payload = json.loads((tmp_path / "reg-facts-manifest.json").read_text())
        entry = next(f for f in payload["files"] if f["name"] == composite.name)
        assert entry["facts"] == {"triangle_count": 999999, "watertight": False}

    def test_an_omitted_stl_falls_back_to_loading_the_file_it_just_hashed(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        from case_prep.adapters.output_package import register_package_files

        emit_case_package("reg-fb", jaw_scan, "lower",
                          [(_site(tooth=19), healing_cap, construction_body)],
                          tmp_path, overlay=False)
        composite = tmp_path / "reg-fb-composite.stl"
        trimesh.creation.icosphere(subdivisions=1).export(composite)

        records = register_package_files(tmp_path / "reg-fb-manifest.json", [composite])
        reloaded = trimesh.load(composite, force="mesh")
        assert records[0].facts.triangle_count == len(reloaded.faces)
        assert records[0].facts.watertight == bool(reloaded.is_watertight)

    def test_a_non_stl_registered_file_carries_no_facts(
        self, tmp_path, jaw_scan, healing_cap, construction_body
    ):
        from case_prep.adapters.output_package import register_package_files

        emit_case_package("reg-png", jaw_scan, "lower",
                          [(_site(tooth=19), healing_cap, construction_body)],
                          tmp_path, overlay=False)
        proof = tmp_path / "reg-png-proof.png"
        proof.write_bytes(b"not really a png")

        records = register_package_files(tmp_path / "reg-png-manifest.json", [proof])
        assert records[0].facts is None
        payload = json.loads((tmp_path / "reg-png-manifest.json").read_text())
        entry = next(f for f in payload["files"] if f["name"] == proof.name)
        assert "facts" not in entry

    def test_an_old_manifest_without_facts_still_parses_and_untouched_entries_stay_bare(
        self, tmp_path
    ):
        """Schema additivity, pinned: a manifest written BEFORE this feature existed
        carries no ``facts`` key on any entry. ``register_package_files`` must still
        read it, update only the entries it is asked to touch, and leave every other
        entry's OLD shape exactly as it was — a reader keying off "absence means
        predates facts" must never see a fact silently invented for a file nobody
        re-measured."""
        from case_prep.adapters.output_package import register_package_files

        old_manifest = {
            "case_id": "old-case", "jaw": "lower", "units": "mm",
            "files": [{"name": "old-case-lower.stl", "sha256": "deadbeef", "bytes": 123}],
            "sites": [],
        }
        manifest_path = tmp_path / "old-case-manifest.json"
        manifest_path.write_text(json.dumps(old_manifest, indent=2))

        new_file = tmp_path / "old-case-19-alignment-proof.png"
        new_file.write_bytes(b"proof")
        register_package_files(manifest_path, [new_file])

        payload = json.loads(manifest_path.read_text())
        by_name = {f["name"]: f for f in payload["files"]}
        assert "facts" not in by_name["old-case-lower.stl"], \
            "an entry this call never touched must keep its pre-facts shape verbatim"
        assert "facts" not in by_name["old-case-19-alignment-proof.png"]
