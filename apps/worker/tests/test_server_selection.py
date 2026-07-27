"""THE LAB CHOOSES, THE SOFTWARE NEVER GUESSES (client directive, 2026-07-25).

Two silent case-drops used to live in ``server._discover_cases``:

  (a) the implant MODEL was read out of the scan FOLDER NAME
      (``model = next(m for m in models if m in folder.name)``) and a folder matching
      nothing was skipped — a real upload named ``patient-4471`` could never be opened;
  (b) the CONSTRUCTION part was name-resolved (``*/<model>-scanbody.stl``) and the case
      was skipped again when no filename matched.

Both are gone. This suite pins what replaced them: a case is discoverable from its scan
alone, the name match survives only as a NON-BINDING suggestion, the construction catalog
lists what is on disk, the run REFUSES a missing decoding selection, and an archived
(``superseded-*``) part the operator explicitly names actually loads and aligns.

The tree is synthetic and self-contained (a real arch stand-in with one embedded cap), so
the suite runs anywhere — no dependency on the doctor data being present.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

import case_prep.server as srv

client = TestClient(srv.app)

MODEL = "acme-1"
# two diameter classes (like a real catalog) and, inside the small class, a CURRENT 8020
# and an ARCHIVED 8020 of different height — so "which file loaded" is measurable
CURRENT_H, ARCHIVED_H = 3.4, 5.4
SMALL_R, LARGE_R = 4.0, 4.5
DOME_MM = 1.2                              # the dome _squat adds on top of the cylinder
ARCHIVE_DIR = "superseded-2026-01-01"
ARCHIVED_ID = f"{ARCHIVE_DIR}--8020"
CONSTRUCTION_ID = "vend-a/generic-abutment.stl"
TOOTH = 8


def _squat(height: float, radius: float = SMALL_R) -> trimesh.Trimesh:
    """A healing-cap-shaped revolute part: open collar, domed top (the shape the rim
    seater is built for). Same construction the auto-flow suite uses."""
    cyl = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    keep = cyl.triangles_center[:, 2] > -height * 0.49
    m = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    m.remove_unreferenced_vertices()
    v = np.asarray(m.vertices, float).copy()
    top = v[:, 2] > height * 0.49
    v[top, 2] += DOME_MM * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / radius) ** 2)
    return trimesh.Trimesh(v, m.faces.copy(), process=False)


def _vendor_body() -> trimesh.Trimesh:
    """An open-shell vendor construction part with real wall margin — thick enough to
    survive the client's 0.20mm gingival relief (the thin synthetic scan body is not)."""
    shell = trimesh.creation.cylinder(radius=2.5, height=8.0, sections=48)
    keep = shell.face_normals[:, 2] < 0.9  # open the top, vendor-CAD style
    return trimesh.Trimesh(shell.vertices, shell.faces[keep], process=False)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """A miniature data root exercising every no-inference case:

      * ``scans/patient-4471`` — the folder name matches NO model (the client's example);
      * ``scans/doctor-x-acme-1`` — the name matches a model, but NO construction file is
        named ``acme-1-scanbody.stl``, so the old code dropped it too;
      * ``library/caps/acme-1`` with a superseded archive holding a DIFFERENT 8020;
      * two vendor construction parts, neither named after any model.
    """
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case
    from case_prep.adapters.synthetic import make_gingiva_arch

    root = tmp_path_factory.mktemp("data")
    out = tmp_path_factory.mktemp("out")

    caps = root / "library/caps" / MODEL
    (caps / ARCHIVE_DIR).mkdir(parents=True)
    _squat(CURRENT_H, SMALL_R).export(caps / f"{MODEL}-8020.stl")
    _squat(CURRENT_H, LARGE_R).export(caps / f"{MODEL}-8030.stl")
    _squat(ARCHIVED_H, SMALL_R).export(caps / ARCHIVE_DIR / f"{MODEL}-8020.stl")

    cons = root / "library/construction"
    (cons / "vend-a").mkdir(parents=True)
    (cons / "vend-b").mkdir(parents=True)
    _vendor_body().export(cons / "vend-a/generic-abutment.stl")
    _vendor_body().export(cons / "vend-b/other-part.stl")

    # the scan carries the ARCHIVED part, so naming it is the choice that actually fits
    np.random.seed(0)
    arch_path = root / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = root / "cap.stl"
    _squat(ARCHIVED_H, SMALL_R).export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, root / "_case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan_bytes = (root / "_case/scan.stl").read_bytes()

    for folder, name in (("patient-4471", "upper_jaw.stl"),
                         ("doctor-x-acme-1", "lower_jaw.stl")):
        d = root / "scans" / folder
        d.mkdir(parents=True)
        (d / name).write_bytes(scan_bytes)

    mp = pytest.MonkeyPatch()
    mp.setattr(srv, "DATA", root)
    mp.setattr(srv, "OUT", out)
    mp.setattr(srv, "CASES", srv._discover_cases(root))
    mp.setattr(srv, "_cache", {})
    yield {"root": root, "out": out,
           "centre": [float(c) for c in gt.poses[0].position]}
    mp.undo()


class TestNoInferenceDiscovery:
    def test_a_folder_named_after_the_patient_is_discoverable(self, demo):
        # THE CLIENT'S EXAMPLE: 'patient-4471' spells no implant model, so the old
        # `next(m for m in models if m in folder.name)` skipped it outright
        assert "patient-4471" in srv.CASES
        cfg = srv.CASES["patient-4471"]
        assert cfg["suggested_model"] is None
        assert cfg["suggested_construction"] is None

    def test_a_case_with_no_name_matching_construction_still_loads(self, demo):
        # the second drop: no file is named 'acme-1-scanbody.stl' anywhere, so the old
        # glob returned None and the case vanished — despite a perfectly good scan
        assert "x-acme-1" in srv.CASES
        cfg = srv.CASES["x-acme-1"]
        assert cfg["suggested_model"] == MODEL          # the name match still SUGGESTS
        assert cfg["suggested_construction"] is None    # but names no construction

    def test_the_scan_is_the_only_requirement(self, demo):
        empty = demo["root"] / "scans/no-stl-here"
        empty.mkdir()
        (empty / "notes.txt").write_text("no mesh in here")
        assert "no-stl-here" not in srv._discover_cases(demo["root"])
        assert {"patient-4471", "x-acme-1"} <= set(srv._discover_cases(demo["root"]))

    def test_jaw_is_surfaced_per_case(self, demo):
        assert srv.CASES["patient-4471"]["jaw"] == "upper"
        assert srv.CASES["x-acme-1"]["jaw"] == "lower"

    def test_the_listing_withholds_nothing_and_labels_the_suggestions(self, demo):
        rows = {c["id"]: c for c in client.get("/api/cases").json()}
        assert {"patient-4471", "x-acme-1"} <= set(rows)
        p = rows["patient-4471"]
        assert p["suggested_model"] is None and p["suggested_construction"] is None
        assert p["jaw"] == "upper" and p["scan_filename"] == "upper_jaw.stl"
        assert rows["x-acme-1"]["suggested_model"] == MODEL


class TestConstructionCatalog:
    def test_lists_every_part_under_every_vendor(self, demo):
        rows = client.get("/api/constructions").json()
        assert [r["path_id"] for r in rows] == [CONSTRUCTION_ID,
                                                "vend-b/other-part.stl"]
        first = rows[0]
        assert first["vendor"] == "vend-a"
        assert first["filename"] == "generic-abutment.stl"
        assert first["label"] == "vend-a — generic-abutment"

    def test_a_path_id_resolves_back_to_its_file(self, demo):
        from case_prep.adapters import construction_catalog

        path = construction_catalog.resolve_construction(demo["root"], CONSTRUCTION_ID)
        assert path is not None and path.name == "generic-abutment.stl"

    def test_anything_not_in_the_catalog_resolves_to_nothing(self, demo):
        from case_prep.adapters import construction_catalog

        for bogus in ("../../etc/passwd", "/etc/passwd", "vend-a/missing.stl",
                      "vend-a", ""):
            assert construction_catalog.resolve_construction(demo["root"], bogus) is None


class TestRequiredSelection:
    """The run refuses a missing DECODING SELECTION — 422, in words, never a fallback."""

    def _body(self, demo, **over):
        base = {"sites": [{"tooth": TOOTH, "center": demo["centre"]}],
                "model": MODEL, "construction_path": CONSTRUCTION_ID}
        base.update(over)
        return base

    def test_a_run_without_a_model_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, model=None))
        assert res.status_code == 422
        assert "implant system" in res.json()["detail"]
        assert "will not pick one for you" in res.json()["detail"]

    def test_a_run_without_a_construction_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, construction_path=None))
        assert res.status_code == 422
        assert "construction part" in res.json()["detail"]

    def test_the_refusal_offers_the_suggestion_without_applying_it(self, demo):
        # x-acme-1 HAS a suggested model — the refusal names it, and still refuses
        res = client.post("/api/cases/x-acme-1/run",
                          json=self._body(demo, model=None, construction_path=None))
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "suggests model='acme-1'" in detail
        assert "a suggestion only" in detail

    def test_an_unknown_implant_system_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, model="not-a-system"))
        assert res.status_code == 422
        assert "unknown implant system" in res.json()["detail"]

    def test_an_unknown_construction_part_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, construction_path="vend-a/nope.stl"))
        assert res.status_code == 422
        assert "unknown construction part" in res.json()["detail"]

    def test_a_variant_outside_the_library_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run", json=self._body(
            demo, sites=[{"tooth": TOOTH, "center": demo["centre"],
                          "declared_variant": "9999"}]))
        assert res.status_code == 422
        assert "is not a part of" in res.json()["detail"]

    def test_an_absurd_gingival_offset_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, gingival_offset_mm=5.0))
        assert res.status_code == 422

    def test_an_unknown_jaw_is_refused(self, demo):
        res = client.post("/api/cases/patient-4471/run",
                          json=self._body(demo, jaw="sideways"))
        assert res.status_code == 422


class TestLibraryResolution:
    def test_the_top_level_catalog_is_unchanged_by_the_archive(self, demo):
        cfg = srv.CASES["patient-4471"]
        variants = {sp.variant for sp in srv._library_for(cfg, MODEL).specs}
        assert variants == {"8020", "8030"}, \
            "the archived part leaked into the default catalog — the glob widened?"

    def test_an_explicitly_named_archived_part_joins_the_library(self, demo):
        cfg = srv.CASES["patient-4471"]
        lib = srv._library_for(cfg, MODEL, [ARCHIVED_ID])
        assert {sp.variant for sp in lib.specs} == {"8020", "8030", ARCHIVED_ID}
        dims = lib.variant_dimensions()
        # the archived 8020 is a DIFFERENT part from the current one — proof the file
        # that loaded is the archived one, not the same-named top-level file
        assert dims[ARCHIVED_ID][1] == pytest.approx(ARCHIVED_H + DOME_MM, abs=0.3)
        assert dims["8020"][1] == pytest.approx(CURRENT_H + DOME_MM, abs=0.3)

    def test_the_per_case_picker_can_be_pointed_at_any_system(self, demo):
        rows = client.get("/api/cases/patient-4471/library",
                          params={"model": MODEL}).json()
        assert [r["variant"] for r in rows] == ["8020", "8030"]
        assert all(r["rim_diameter_mm"] and r["height_mm"] for r in rows)

    def test_the_picker_says_so_when_the_case_suggests_nothing(self, demo):
        res = client.get("/api/cases/patient-4471/library")
        assert res.status_code == 409
        assert "no suggested implant system" in res.json()["detail"]

    def test_the_implant_system_is_a_membership_lookup_not_a_path_join(self, demo):
        """The model names a SYSTEM, not a directory to walk to (adversarial review
        2026-07-25). Joining it onto ``library/caps/`` let a traversal escape the root:
        ``"<model>/<archive-dir>"`` loaded the whole superseded archive as if it were a
        current system — defeating CapLibrary.load's top-level-only glob, which exists so an
        archived part joins a run one explicitly-named part at a time — and ``"../caps/x"``
        shipped a package whose ``implant_model`` (the paid record's audit key) was the
        traversal string itself."""
        cfg = srv.CASES["patient-4471"]
        for escape in (f"{MODEL}/{ARCHIVE_DIR}", f"../caps/{MODEL}", f"./{MODEL}", "..",
                       "../construction"):
            with pytest.raises(Exception) as exc:
                srv._library_for(cfg, escape)
            assert getattr(exc.value, "status_code", None) == 422, escape
            assert "unknown implant system" in str(getattr(exc.value, "detail", "")), escape

    def test_the_run_refuses_a_traversal_shaped_implant_system(self, demo):
        res = client.post("/api/cases/patient-4471/run", json={
            "sites": [{"tooth": TOOTH, "center": demo["centre"]}],
            "model": f"{MODEL}/{ARCHIVE_DIR}", "construction_path": CONSTRUCTION_ID})
        assert res.status_code == 422
        assert "unknown implant system" in res.json()["detail"]

    def test_an_archived_part_is_servable_as_a_mesh(self, demo):
        res = client.get(f"/api/cases/patient-4471/library/{ARCHIVED_ID}/mesh",
                         params={"model": MODEL})
        assert res.status_code == 200
        mesh = trimesh.load(trimesh.util.wrap_as_stream(res.content), file_type="stl")
        assert mesh.extents[2] == pytest.approx(ARCHIVED_H + DOME_MM, abs=0.3)


@pytest.fixture(scope="module")
def archived_run(demo):
    """ONE real run of the case nobody could open before, under a fully explicit
    selection whose cap variant lives in the superseded archive."""
    res = client.post("/api/cases/patient-4471/run", json={
        "sites": [{"tooth": TOOTH, "center": demo["centre"],
                   "declared_variant": ARCHIVED_ID}],
        "model": MODEL, "construction_path": CONSTRUCTION_ID, "jaw": "upper"})
    assert res.status_code == 200, res.text
    return res.json()


class TestExplicitSelectionDrivesTheRun:
    @pytest.mark.slow
    def test_the_archived_variant_loads_and_aligns(self, archived_run):
        row = archived_run["summary"]["sites"][0]
        assert "error" not in row
        assert row["variant"]["identified"] == ARCHIVED_ID
        assert row["variant"]["declared"] == ARCHIVED_ID
        assert row["seat_method"] in ("rim", "icp")
        assert row["fit"]["avg_mm"] < 1.0, \
            f"the archived part did not seat: {row['fit']}"

    def test_the_chosen_construction_is_the_one_that_ships(self, archived_run, demo):
        # the vendor comes from the CHOSEN path_id — nothing here is named after a model,
        # so a name-matching pipeline could not have produced this file at all
        names = set(archived_run["summary"]["package_files"])
        assert f"patient-4471-{TOOTH}-scanbody-vend-a.stl" in names
        assert f"patient-4471-{TOOTH}-prosthesis_cad.stl" in names

    def test_the_selection_is_echoed_back_for_the_acknowledgment_panel(self,
                                                                      archived_run):
        sel = archived_run["selection"]
        assert sel["model"] == MODEL
        assert sel["construction_path"] == CONSTRUCTION_ID
        assert sel["vendor"] == "vend-a"
        assert sel["jaw"] == "upper"
        assert sel["gingival_offset_mm"] == 0.20      # the client's default value
        assert sel["variants"] == {str(TOOTH): ARCHIVED_ID}

    def test_the_relief_used_rides_in_the_row_and_the_paid_record(self, archived_run,
                                                                  demo):
        row = archived_run["summary"]["sites"][0]
        assert row["production"]["gingival_offset_mm"] == 0.20
        rec = json.loads((demo["out"] / "patient-4471/package"
                          / f"patient-4471-{TOOTH}-implant.json").read_text())
        assert rec["audit"]["gingival_offset_mm"] == 0.20
        assert rec["implant_model"] == MODEL
        assert rec["variant_code"] == ARCHIVED_ID

    def test_the_history_stream_records_the_selection(self, archived_run, demo):
        lines = (demo["out"] / "run-history.jsonl").read_text().strip().splitlines()
        rec = json.loads(lines[-1])
        assert rec["selection"]["model"] == MODEL
        assert rec["selection"]["construction_path"] == CONSTRUCTION_ID

    def test_a_different_construction_is_a_different_cached_run(self, archived_run,
                                                                demo):
        # the selection is part of the cache key: the same marks against another vendor
        # part must never be served from the first selection's cache
        from case_prep.server import RunIn, SiteIn

        site = SiteIn(tooth=TOOTH, center=demo["centre"], declared_variant=ARCHIVED_ID)
        a = srv._run_cache_key("patient-4471", RunIn(sites=[site]), MODEL,
                               CONSTRUCTION_ID, "upper")
        b = srv._run_cache_key("patient-4471", RunIn(sites=[site]), MODEL,
                               "vend-b/other-part.stl", "upper")
        assert a != b


class TestThreePanelDeviation:
    """The union panel's colouring: per-vertex signed deviation of the posed cap against
    the scan, on the acceptance PNG's own scale."""

    def test_the_endpoint_returns_a_renderable_coloured_mesh(self, archived_run):
        res = client.get(f"/api/cases/patient-4471/sites/{TOOTH}/deviation")
        assert res.status_code == 200
        body = res.json()
        _p, _i, _rec, template, *_ = srv._load_rotation_site("patient-4471", TOOTH)
        # one value per template VERTEX, and the faces that index them — the web can
        # build the union overlay from this alone, with no ordering guesswork
        assert body["n_points"] == len(template.vertices)
        assert body["n_points"] == len(body["points"]) == len(body["deviation_mm"])
        assert len(body["faces"]) == len(template.faces)
        assert all(len(p) == 3 for p in body["points"][:20])
        assert max(max(f) for f in body["faces"]) < body["n_points"]
        assert body["variant"] == ARCHIVED_ID
        assert body["frame"] == "jaw-scan world frame"
        assert body["reporting_only"] is True

    def test_the_colorbar_bounds_are_the_acceptance_scale(self, archived_run):
        from case_prep.adapters import qc_render

        scale = client.get(
            f"/api/cases/patient-4471/sites/{TOOTH}/deviation").json()["scale"]
        assert scale["clamp_mm"] == qc_render.DEVIATION_CLAMP_MM
        assert (scale["min_mm"], scale["max_mm"]) == (-scale["clamp_mm"],
                                                      scale["clamp_mm"])
        assert scale["colormap"] == qc_render.DEVIATION_COLORMAP
        assert scale["sign_convention"].startswith("+ = scan outside")
        assert scale["data_min_mm"] <= scale["data_max_mm"]

    def test_the_points_are_posed_into_the_jaw_frame(self, archived_run, demo):
        body = client.get(
            f"/api/cases/patient-4471/sites/{TOOTH}/deviation").json()
        pts = np.asarray(body["points"], float)
        rec = json.loads((demo["out"] / "patient-4471/package"
                          / f"patient-4471-{TOOTH}-implant.json").read_text())
        pose_origin = np.asarray(rec["position"], float)
        # the cap sits AT the site, not at the canonical origin
        assert float(np.linalg.norm(pts.mean(axis=0) - pose_origin)) < 5.0

    def test_the_published_stats_are_the_difference_maps_own_numbers(self, archived_run,
                                                                     demo):
        """ONE site, ONE published RMS. The panel's scalars must be the acceptance
        numbers the deviation PNG prints and the run row carries — NOT a re-derivation
        over the CAD's vertices, which weights features differently and reads a different
        millimetre on a real site (measured cap7030 tooth 29: 0.361 vs 0.427mm RMS). The
        vertex set's own coverage is reported separately, under its own name."""
        from case_prep.adapters.qc_render import site_deviation_stats

        cfg = srv.CASES["patient-4471"]
        _p, _i, rec, template, *_ = srv._load_rotation_site("patient-4471", TOOTH)
        png_stats = site_deviation_stats(
            np.asarray(srv._scan_mesh(cfg).vertices, float),
            np.asarray(rec["pose_matrix"], float), template)
        body = client.get(f"/api/cases/patient-4471/sites/{TOOTH}/deviation").json()
        served = body["stats"]
        assert served["n_samples"] == png_stats["n_samples"]
        assert served["n_footprint"] == png_stats["n_footprint"]
        for field in ("rms_mm", "p90_mm"):
            expected = (None if png_stats[field] is None
                        else round(float(png_stats[field]), 3))
            assert served[field] == expected
        assert "vertex_footprint_points" in body
        assert body["vertex_footprint_points"] <= body["n_points"]

    def test_a_site_that_was_never_run_is_a_404(self, archived_run):
        res = client.get("/api/cases/patient-4471/sites/31/deviation")
        assert res.status_code == 404


class TestPreviewAlignmentBeforeAnyRun:
    """VERIFY MUST WORK ON THE FIRST PASS (client, 2026-07-26).

    The three-panel verify is read BEFORE Process, but its union pane could only ever
    colour a SHIPPED pose — so on a case nobody had processed the pane said "no seated
    result for this site", exactly when the operator most needs to see whether the part
    they chose matches the cap that was scanned.

    ``preview-alignment`` is that read. It is the SAME alignment pass, for one site, with
    nothing emitted — so what these tests pin is that it is honest (a real seat, on the
    acceptance scale) and that it ships NOTHING (no package, no run row).
    """

    def _body(self, demo, **over):
        base = {"sites": [{"tooth": TOOTH, "center": demo["centre"],
                           "declared_variant": ARCHIVED_ID}],
                "model": MODEL, "construction_path": CONSTRUCTION_ID, "jaw": "upper"}
        base.update(over)
        return base

    @pytest.fixture(scope="class")
    def preview(self, demo):
        """A preview of the case in its UNPROCESSED state — this fixture deliberately
        does NOT depend on ``archived_run``, which is the whole point."""
        res = client.post(f"/api/cases/x-acme-1/sites/{TOOTH}/preview-alignment",
                          json={"sites": [{"tooth": TOOTH, "center": demo["centre"],
                                           "declared_variant": ARCHIVED_ID}],
                                "model": MODEL,
                                "construction_path": CONSTRUCTION_ID, "jaw": "lower"})
        assert res.status_code == 200, res.text
        return res.json()

    @pytest.mark.slow
    def test_the_union_pane_is_populated_with_no_run_at_all(self, preview, demo):
        # nothing has ever been processed for this case…
        assert not (demo["out"] / "x-acme-1/package").exists()
        assert not (demo["out"] / "x-acme-1/run.json").exists()
        # …and the pane still has a renderable, coloured mesh to show
        assert preview["n_points"] == len(preview["points"]) \
            == len(preview["deviation_mm"])
        assert max(max(f) for f in preview["faces"]) < preview["n_points"]
        assert preview["variant"] == ARCHIVED_ID
        assert preview["preview"] is True

    @pytest.mark.slow
    def test_it_reads_on_the_very_same_scale_as_the_shipped_deviation(self, preview):
        from case_prep.adapters import qc_render

        scale = preview["scale"]
        assert scale["clamp_mm"] == qc_render.DEVIATION_CLAMP_MM
        assert scale["colormap"] == qc_render.DEVIATION_COLORMAP
        assert scale["sign_convention"].startswith("+ = scan outside")
        # the acceptance scalars come from the SAME instrument the difference map and the
        # run row publish (a synthetic footprint can legitimately yield no samples, which
        # the pane states rather than inventing a number)
        assert preview["stats"]["source"].startswith("area-uniform surface samples")
        assert preview["reporting_only"] is True
        assert preview["frame"] == "jaw-scan world frame"

    @pytest.mark.slow
    def test_it_is_a_real_seat_not_a_placeholder(self, preview, demo):
        # the coloured cap sits AT the marked site, and the seat numbers the results
        # table would print after Process ride along with it
        pts = np.asarray(preview["points"], float)
        assert float(np.linalg.norm(pts.mean(axis=0)
                                    - np.asarray(demo["centre"], float))) < 5.0
        assert preview["seat"]["seat_method"] in ("rim", "icp")

    @pytest.mark.slow
    def test_a_preview_ships_nothing(self, preview, demo):
        """The preview is not a back door around the run gate: it emits no package the
        file endpoint can serve, and records no run row a reload could mistake for one."""
        assert not (demo["out"] / "x-acme-1/package").exists()
        assert not (demo["out"] / "x-acme-1/run.json").exists()
        assert (demo["out"] / "x-acme-1/preview").is_dir()   # its own scratch space
        res = client.get(f"/api/cases/x-acme-1/files/x-acme-1-{TOOTH}-implant.json")
        assert res.status_code == 404
        # …and the shipped read still refuses, because nothing has been shipped
        assert client.get(
            f"/api/cases/x-acme-1/sites/{TOOTH}/deviation").status_code == 404

    def test_it_refuses_the_same_incomplete_selection_the_run_does(self, demo):
        res = client.post(f"/api/cases/patient-4471/sites/{TOOTH}/preview-alignment",
                          json=self._body(demo, model=None))
        assert res.status_code == 422
        assert "implant system" in res.json()["detail"]

    def test_it_refuses_a_site_with_no_declared_cap(self, demo):
        res = client.post(f"/api/cases/patient-4471/sites/{TOOTH}/preview-alignment",
                          json=self._body(demo, sites=[{"tooth": TOOTH,
                                                        "center": demo["centre"]}]))
        assert res.status_code == 422
        assert "declared cap variant" in res.json()["detail"]

    def test_it_refuses_a_tooth_that_was_not_sent(self, demo):
        res = client.post("/api/cases/patient-4471/sites/31/preview-alignment",
                          json=self._body(demo))
        assert res.status_code == 422
        assert "not among the marked sites" in res.json()["detail"]
