"""Unit pins for ``case_prep.pipeline.isolation`` (clinical pipeline plan Stage 2
slice 2a, boolean plan 4d): the server-side mirror of the product's pane-2 matched
isolation rung, run once per resolved site so the lab can download exactly what the
scanner saw of the healing cap — ``{case}-{tooth}-scanned-cap.stl``.

The synthetic pins below hold the MECHANISM honest against a hand-built scene where
every triangle's fate is known in advance (a flat sheet standing in for the scan, a
hollow "cylinder-ish" tube standing in for the posed library cap). The emission pins
exercise both lanes that call the mechanism (``pipeline.auto_flow`` and
``application.emit``) through their own cheapest existing fixtures. The real-mesh pin
is the feature: on a real fleet arch the band + core rungs must actually trim
triangles off the raw cylinder pre-cut — the plan's own measured proof (tooth 20:
41,091 -> 31,550 -> 16,651) is exactly this claim, on a different site.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.synthetic import make_gingiva_arch, make_scan_body_mesh
from case_prep.domain.cap_catalog import CapSpec
from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case
from case_prep.pipeline.isolation import (CAP_MATCH_BAND_MM, isolate_scanned_cap,
                                          orphan_flap_mask,
                                          scanned_cap_face_mask)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"


# --- synthetic scene builders --------------------------------------------------

def _quad_patch(cx: float, cy: float, half: float = 0.05):
    """A tiny flat 2-triangle square centred at ``(cx, cy, 0)`` — a whole-triangle
    probe small enough to sit cleanly inside one rung's decision zone, whose exact
    vertex coordinates we can look for (or fail to find) in the result."""
    verts = np.array([
        [cx - half, cy - half, 0.0],
        [cx + half, cy - half, 0.0],
        [cx + half, cy + half, 0.0],
        [cx - half, cy + half, 0.0],
    ])
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    return verts, faces


def _sheet(*patches) -> trimesh.Trimesh:
    """Several disjoint patches concatenated into one flat "scan" — ``process=False``
    so no merge/re-index touches a single coordinate."""
    verts_all, faces_all, offset = [], [], 0
    for verts, faces in patches:
        verts_all.append(verts)
        faces_all.append(faces + offset)
        offset += len(verts)
    return trimesh.Trimesh(np.vstack(verts_all), np.vstack(faces_all), process=False)


def _cylinder_wall(radius: float, z_lo: float = -1.0, z_hi: float = 1.0,
                   sections: int = 128) -> trimesh.Trimesh:
    """A hollow cylinder SIDE WALL only — no end caps — the "cylinder-ish template"
    the plan asks for. At z=0 (inside ``[z_lo, z_hi]``) its nearest surface point to
    any query point is exactly radial distance ``|rho - radius|``, which is what
    makes the fixture's expected keep/drop zones exact rather than approximate."""
    ang = np.linspace(0.0, 2.0 * np.pi, sections, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    bot = np.column_stack([radius * ca, radius * sa, np.full(sections, z_lo)])
    top = np.column_stack([radius * ca, radius * sa, np.full(sections, z_hi)])
    verts = np.vstack([bot, top])
    faces = []
    n = sections
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j])
        faces.append([i, n + j, n + i])
    return trimesh.Trimesh(verts, np.asarray(faces, int), process=False)


def _has_vertex(mesh: trimesh.Trimesh, point) -> bool:
    return bool(np.any(np.all(np.isclose(mesh.vertices, point), axis=1)))


# rim_r = 5.0 -> core radius = max(5.0 - 1.0, 1.2) = 4.0 (the module's own formula)
RIM_R = 5.0


class TestIsolateScannedCap:
    """The scene: four disjoint patches at increasing distance from the axis —
    deep inside the core (radial ~0.07), in the "neither core nor band" middle
    ground (radial ~4.15-4.25, 0.75-0.85mm from the template), sitting AT the
    template's own radius (radial ~4.85-4.95, <=0.15mm away), and far past the
    catalog rim entirely (radial ~20). ``core_r=4.0`` and ``CAP_MATCH_BAND_MM=0.6``
    give every patch a >=0.1mm margin from its nearest decision boundary."""

    def _fixture(self):
        core = _quad_patch(0.0, 0.0)
        dropped = _quad_patch(0.0, 4.2)
        matched = _quad_patch(0.0, 4.90)
        outside = _quad_patch(0.0, 20.0)
        scan = _sheet(core, dropped, matched, outside)
        template = _cylinder_wall(radius=RIM_R)
        pose = np.eye(4)
        return scan, template, pose, {
            "core": core[0], "dropped": dropped[0],
            "matched": matched[0], "outside": outside[0],
        }

    def test_two_isolations_of_the_same_inputs_are_byte_identical(self):
        """W4's measured defect (2026-08-14): the unseeded template surface
        draw made face MEMBERSHIP re-roll on 22% of real re-emits (50% on the
        worst site) — the one nondeterministic file in the package, and the
        manifest sealed it. The draw is seeded now; two isolations must agree
        to the byte, not merely to the same shape."""
        scan, template, pose, _ = self._fixture()
        a = isolate_scanned_cap(scan, template, pose, RIM_R)
        b = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert a is not None and b is not None
        assert np.array_equal(a.vertices, b.vertices)
        assert np.array_equal(a.faces, b.faces)

    def test_core_keep_survives_far_from_the_template(self):
        scan, template, pose, patches = self._fixture()
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None
        for v in patches["core"]:
            assert _has_vertex(result, v), \
                "the recess-void analogue must survive unconditionally inside the core"

    def test_the_middle_ground_is_neither_core_nor_matched(self):
        scan, template, pose, patches = self._fixture()
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None
        for v in patches["dropped"]:
            assert not _has_vertex(result, v), \
                "outside the core and beyond the band, tissue must drop"

    def test_matched_band_keeps_the_surface_at_the_template(self):
        scan, template, pose, patches = self._fixture()
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None
        for v in patches["matched"]:
            assert _has_vertex(result, v), \
                "the surface actually AT the posed template must survive"

    def test_the_cylinder_pre_cut_excludes_unrelated_surface(self):
        scan, template, pose, patches = self._fixture()
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None
        for v in patches["outside"]:
            assert not _has_vertex(result, v), \
                "surface far past the catalog rim never reaches the band test at all"

    def test_whole_triangle_rule_invents_no_new_vertices(self):
        scan, template, pose, _patches = self._fixture()
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None
        scan_vertex_set = {tuple(v) for v in np.asarray(scan.vertices)}
        for v in np.asarray(result.vertices):
            assert tuple(v) in scan_vertex_set, \
                "every surviving vertex must be one of the scan's own, untouched"

    def test_a_pathological_pose_returns_none(self):
        """A pose whose axis stands nowhere near the scan (miles off) catches
        nothing at the cylinder pre-cut — the honest empty result the caller
        turns into a per-site note rather than an empty file."""
        scan, template, _pose, _patches = self._fixture()
        pose = np.eye(4)
        pose[:3, 3] = [1000.0, 1000.0, 1000.0]
        assert isolate_scanned_cap(scan, template, pose, RIM_R) is None

    def test_the_band_mirrors_the_products_own_constant(self):
        # apps/product/src/domain/declare.ts's CAP_MATCH_BAND_MM — the served
        # artifact must be the SAME rung the pane's own caption names
        assert CAP_MATCH_BAND_MM == 0.6


class TestScannedCapFaceMask:
    """THE SHARED CLASSIFIER (client-ruled defect 1, boolean-engine excision
    slice, 2026-08-15): ``isolate_scanned_cap``'s own mechanism, exposed as a
    per-face boolean mask so DEFECT 1's excision can apply the identical
    three-rung test to a boolean result's own scan-provenance faces, not just
    the raw scan. ``isolate_scanned_cap`` is now a thin wrapper over it —
    pinned here directly so the two can never silently drift apart."""

    def test_mask_shape_matches_the_meshs_own_face_count(self):
        scan, template, pose, _patches = TestIsolateScannedCap()._fixture()
        mask = scanned_cap_face_mask(scan, template, pose, RIM_R)
        assert mask.dtype == np.dtype(bool)
        assert mask.shape == (len(scan.faces),)

    def test_isolate_scanned_cap_keeps_exactly_the_faces_the_mask_marks(self):
        """The wrapper relationship, proved directly: every face
        ``isolate_scanned_cap`` returns is one the mask marked True, by exact
        vertex-coordinate identity (nothing is moved, so this is a coordinate
        comparison, not merely a count)."""
        scan, template, pose, _patches = TestIsolateScannedCap()._fixture()
        mask = scanned_cap_face_mask(scan, template, pose, RIM_R)
        result = isolate_scanned_cap(scan, template, pose, RIM_R)
        assert result is not None

        scan_v = np.asarray(scan.vertices, float)
        scan_f = np.asarray(scan.faces)
        masked_sigs = {
            tuple(sorted(tuple(np.round(scan_v[v], 6)) for v in f))
            for f in scan_f[mask]}
        result_v = np.asarray(result.vertices, float)
        result_f = np.asarray(result.faces)
        result_sigs = {
            tuple(sorted(tuple(np.round(result_v[v], 6)) for v in f))
            for f in result_f}
        assert result_sigs == masked_sigs

    def test_an_empty_mesh_returns_an_empty_mask_not_a_raise(self):
        _scan, template, pose, _patches = TestIsolateScannedCap()._fixture()
        mask = scanned_cap_face_mask(trimesh.Trimesh(), template, pose, RIM_R)
        assert mask.shape == (0,)

    def test_the_mask_reads_ANY_mesh_not_only_the_raw_scan(self):
        """DEFECT 1's own point: the classifier is mesh-agnostic geometry, so
        it can be applied to a boolean's own result (a DIFFERENT mesh than
        the scan that fed the boolean) to find scan-provenance crust there —
        exercised here by feeding a mesh built from the raw scan's own
        surviving faces, offset by nothing, and confirming the mask reads
        identically off it."""
        scan, template, pose, _patches = TestIsolateScannedCap()._fixture()
        mask = scanned_cap_face_mask(scan, template, pose, RIM_R)
        copy_mesh = trimesh.Trimesh(np.asarray(scan.vertices, float).copy(),
                                    np.asarray(scan.faces).copy(),
                                    process=False)
        mask_on_copy = scanned_cap_face_mask(copy_mesh, template, pose, RIM_R)
        assert np.array_equal(mask, mask_on_copy)


def _pose_at(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = [x, y, z]
    return m


class TestOrphanFlapMask:
    """DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
    2026-08-15). ``scanned_cap_face_mask``'s own 0.6mm template-match band
    misses cap-margin surface that deviates MORE than the band, in the
    annulus between the core-keep radius and the catalog rim — those
    triangles dodge the excision and survive as loose slivers. The scene:
    a dense flat "gum" sheet (the main body) plus a small BOX standing
    ``trimesh.util.concatenate``-disjoint from it (never welded, so it is
    its own connected component by construction) at radius 1.8mm about the
    axis — inside ``rim_r=2.2``'s annulus (``core_r = max(2.2-1.0, 1.2) =
    1.2``) and 0.8mm past a ``template_r=1.0`` cylinder's own wall, past
    ``CAP_MATCH_BAND_MM`` (0.6mm)."""

    RIM_R = 2.2
    TEMPLATE_R = 1.0

    def _scene(self, flap_centre=(1.8, 0.0, 2.0)):
        sheet = trimesh.creation.box(extents=[10.0, 10.0, 1.0])
        for _ in range(3):
            sheet = sheet.subdivide()
        flap = trimesh.creation.box(extents=[0.3, 0.3, 0.3])
        flap.apply_translation(flap_centre)
        mesh = trimesh.util.concatenate([sheet, flap])
        pose = _pose_at(0.0, 0.0, 2.0)
        return mesh, pose, len(sheet.faces)

    def test_the_deviated_flap_dodges_the_shared_classifier(self):
        """THE GAP THIS DEFECT CLOSES, proved first: at 0.8mm past the
        template's own wall the flap sits outside ``CAP_MATCH_BAND_MM``
        (0.6mm) and outside the core (radial 1.8 > core_r 1.2) — the
        existing rung genuinely misses it, which is why connectivity, not a
        wider band, is the fix."""
        mesh, pose, n_sheet = self._scene()
        template = trimesh.creation.cylinder(radius=self.TEMPLATE_R, height=4.0,
                                             sections=64)
        mask = scanned_cap_face_mask(mesh, template, pose, self.RIM_R)
        assert not mask[n_sheet:].any(), \
            "the flap must NOT be caught by the template-band classifier " \
            "alone — that is the defect, not a red herring"

    def test_the_orphan_component_is_flagged_whole(self):
        mesh, pose, n_sheet = self._scene()
        mask = orphan_flap_mask(mesh, [(pose, self.RIM_R)],
                                candidate=np.ones(len(mesh.faces), bool))
        assert mask[n_sheet:].all(), "every flap face must be flagged"
        assert not mask[:n_sheet].any(), "the main sheet must never be flagged"

    def test_the_main_body_is_never_a_candidate_even_inside_the_cylinder(self):
        """THE GUARD, NAMED EXPLICITLY: shrink the sheet so its own bulk sits
        entirely inside a generous cylinder — the biggest candidate
        component must still survive, however it reads against the radial
        test, because it IS the main body."""
        sheet = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
        for _ in range(2):
            sheet = sheet.subdivide()
        flap = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
        flap.apply_translation((0.6, 0.0, 0.0))
        mesh = trimesh.util.concatenate([sheet, flap])
        pose = np.eye(4)
        mask = orphan_flap_mask(mesh, [(pose, 5.0)],
                                candidate=np.ones(len(mesh.faces), bool))
        assert not mask[:len(sheet.faces)].any(), \
            "the largest candidate component must never be an orphan"
        assert mask[len(sheet.faces):].all(), \
            "the smaller, disconnected component must still be flagged"

    def test_a_component_reaching_outside_the_cylinder_is_kept(self):
        """THE OTHER HALF OF THE GUARD (the client's own words: "a connected
        gum tongue reaching into the cylinder: kept"): a disconnected sliver
        with even ONE face outside the cylinder is real, ordinary tissue —
        never dropped, however deep the rest of it sits inside."""
        mesh, pose, n_sheet = self._scene()
        tongue = trimesh.creation.box(extents=[0.3, 0.3, 6.0])
        # spans radius ~1.8 (inside the annulus) out past radius 3.0 —
        # ANY face outside rim_r=2.2 keeps the whole component
        tongue.apply_translation((3.0, 0.0, 2.0))
        scene = trimesh.util.concatenate([mesh, tongue])
        mask = orphan_flap_mask(scene, [(pose, self.RIM_R)],
                                candidate=np.ones(len(scene.faces), bool))
        assert not mask[len(mesh.faces):].any(), \
            "a component with a face outside the cylinder must be kept whole"
        # the original flap is still caught
        assert mask[n_sheet:len(mesh.faces)].all()

    def test_candidate_mask_excludes_a_face_from_eligibility(self):
        """A face the caller never marked candidate (a construction part's
        own surface, another consumer's already-moved material) can never
        be flagged, however it reads geometrically."""
        mesh, pose, n_sheet = self._scene()
        candidate = np.ones(len(mesh.faces), bool)
        candidate[n_sheet:] = False  # the flap is explicitly ineligible
        mask = orphan_flap_mask(mesh, [(pose, self.RIM_R)], candidate=candidate)
        assert not mask.any(), \
            "a face outside `candidate` must never be flagged as orphan"

    def test_no_site_poses_returns_all_false(self):
        mesh, _pose, _n = self._scene()
        mask = orphan_flap_mask(mesh, [])
        assert mask.shape == (len(mesh.faces),)
        assert not mask.any()

    def test_an_empty_mesh_returns_an_empty_mask_not_a_raise(self):
        mask = orphan_flap_mask(trimesh.Trimesh(), [(np.eye(4), 2.0)])
        assert mask.shape == (0,)

    def test_default_candidate_is_every_face(self):
        """``candidate=None`` (the default) considers every face of ``mesh``
        eligible — the same outcome as passing an all-True mask explicitly."""
        mesh, pose, n_sheet = self._scene()
        mask_default = orphan_flap_mask(mesh, [(pose, self.RIM_R)])
        mask_explicit = orphan_flap_mask(
            mesh, [(pose, self.RIM_R)], candidate=np.ones(len(mesh.faces), bool))
        assert np.array_equal(mask_default, mask_explicit)


# --- emission: the auto_flow.py lane --------------------------------------------

def _embedded_case(tmp_path, n: int = 1):
    """The cheapest existing emit fixture (``test_auto_flow.py``'s own helper,
    duplicated here so this module stands alone): real registration against real
    gum geometry, a synthetic (noised, partially occluded) cap embedded at a known
    pose — no real fleet data required."""
    from case_prep.adapters.real_case import build_embedded_case

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    make_scan_body_mesh().export(cad_path)
    case = tmp_path / "case"
    gt = build_embedded_case(arch_path, cad_path, case, n_implants=n, seed=1)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = CapLibrary.single(CapSpec("certain", "4.1"),
                            trimesh.load(case / "library/certain3i_4_1/mesh.stl", force="mesh"))
    return scan, lib, gt


@pytest.mark.slow
class TestEmissionOnTheAutoFlowLane:
    def test_the_artifact_lands_in_package_files_and_on_disk(self, tmp_path):
        scan, lib, gt = _embedded_case(tmp_path)
        confirmed = [ConfirmedSite(tooth=19, center=tuple(map(float, gt.poses[0].position)))]
        out = tmp_path / "out"
        summary = run_auto_case(
            case_id="iso-1", scan=scan, library=lib,
            construction_mesh=make_scan_body_mesh(), vendor="dess",
            gingival_offset_mm=0.0,  # stand-in body — see test_auto_flow.py's module note
            confirmed=confirmed, jaw_label="upper", out_dir=out)
        tooth = summary["sites"][0]["tooth"]
        name = f"iso-1-{tooth}-scanned-cap.stl"

        assert name in summary["package_files"]
        path = out / name
        assert path.is_file()
        isolated = trimesh.load(path, force="mesh")
        assert len(isolated.faces) > 0
        # a well-posed site never carries the empty-isolation note
        assert summary["sites"][0].get("production", {}).get("scanned_cap_note") is None

    def test_an_empty_isolation_lands_an_honest_note_and_no_file(self, tmp_path, monkeypatch):
        """The pose-catches-nothing path is honest degradation, not a real fleet
        hunt: the mechanism is already pinned directly above, so here the LANE's
        wiring is what's under test — patched to always report the empty result,
        exactly ``isolate_scanned_cap`` itself returns on a pathological pose."""
        import case_prep.pipeline.auto_flow as auto_flow_module

        monkeypatch.setattr(auto_flow_module, "isolate_scanned_cap",
                            lambda *args, **kwargs: None)
        scan, lib, gt = _embedded_case(tmp_path)
        confirmed = [ConfirmedSite(tooth=19, center=tuple(map(float, gt.poses[0].position)))]
        out = tmp_path / "out"
        summary = run_auto_case(
            case_id="iso-2", scan=scan, library=lib,
            construction_mesh=make_scan_body_mesh(), vendor="dess",
            gingival_offset_mm=0.0,
            confirmed=confirmed, jaw_label="upper", out_dir=out)
        tooth = summary["sites"][0]["tooth"]
        name = f"iso-2-{tooth}-scanned-cap.stl"

        assert name not in summary["package_files"]
        assert not (out / name).exists()
        note = summary["sites"][0]["production"]["scanned_cap_note"]
        assert note == ("site 1: the scanned-cap isolation caught nothing at this "
                        "pose — the artifact was not emitted")


# --- the real-mesh proof ---------------------------------------------------------

class TestOnTheRealTree:
    @pytest.mark.slow
    def test_the_band_does_real_work_on_zimmer_4_5(self, tmp_path):
        """On case 276794487-zimmer-4.5 the artifact must ship non-empty, and its
        triangle count must be BELOW the raw cylinder pre-cut's — the measured
        proof (plan Stage 2, tooth 20: 41,091 -> 31,550 -> 16,651) that the band
        and core rungs do real work rather than passing the pre-cut through."""
        from case_prep.pipeline.isolation import (_axis_and_origin,
                                                   _keep_faces_by_vertex_mask,
                                                   _radial_distances)

        folder, model = "doctor-276794487-zimmer-4.5", "zimmer-4.5"
        if not (REAL / "scans" / folder).exists():
            pytest.skip("real arch not present")
        scan = trimesh.load(next((REAL / "scans" / folder).glob("*.stl")), force="mesh")
        vendor_dir = next((REAL / "library/construction").glob(f"*/{model}-scanbody.stl"))
        lib = CapLibrary.load(REAL / "library/caps" / model)
        s = json.loads((REAL / "scans" / folder / "sites.json")
                       .read_text())["suggested_sites"][0]
        out_dir = tmp_path / "out"
        out = run_auto_case(
            case_id="sc", scan=scan, library=lib,
            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
            vendor=vendor_dir.parent.name,
            confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), s.get("declared_variant"),
                                     center_mark=s.get("center_mark"),
                                     rim_mark=s.get("rim_mark"))],
            gingival_offset_mm=0.0, jaw_label="x", out_dir=out_dir)
        row = out["sites"][0]
        assert row.get("error") is None
        tooth = row["tooth"]

        artifact = out_dir / f"sc-{tooth}-scanned-cap.stl"
        assert artifact.is_file(), "a real, well-posed site must ship the artifact"
        isolated = trimesh.load(artifact, force="mesh")
        assert len(isolated.faces) > 0

        rec = json.loads((out_dir / f"sc-{tooth}-implant.json").read_text())
        pose = np.array(rec["pose_matrix"], float)
        tmpl = lib.template(next(sp for sp in lib.specs
                                 if sp.variant == row["variant"]["identified"]))
        dims = lib.variant_dimensions().get(row["variant"]["identified"])
        if dims is None:
            ext = tmpl.bounds[1] - tmpl.bounds[0]
            rim_r = float(max(ext[0], ext[1])) / 2.0
        else:
            rim_r = float(dims[0]) / 2.0

        origin, axis = _axis_and_origin(pose)
        pre_cut = _keep_faces_by_vertex_mask(
            scan, _radial_distances(np.asarray(scan.vertices, float), origin, axis) <= rim_r)
        assert pre_cut is not None
        assert len(isolated.faces) < len(pre_cut.faces), \
            "the band + core rungs must trim triangles off the raw cylinder pre-cut"
