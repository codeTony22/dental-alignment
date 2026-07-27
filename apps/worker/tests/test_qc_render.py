"""QC acceptance renders: every packaged site ships a clock view + signed difference
map PNG, hashed into the manifest like any deliverable; the deviation read-out is
deterministic, RNG-state-safe and REPORTING ONLY (it never moves a pose).

MODULE NOTE — ``gingival_offset_mm=0.0`` on the runs below (2026-07-25): the stand-in
construction part (``make_scan_body_mesh``) is too thin for the client's 0.20mm gingival
relief and the G5 export gate rightly fails it closed; the relief's own contract lives in
``test_final_product.py::TestGingivalProfileOffset``."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.qc_render import render_site_qc, signed_deviation
from case_prep.adapters.synthetic import make_gingiva_arch, make_scan_body_mesh
from case_prep.domain.cap_catalog import CapSpec
from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case


def _embedded_case(tmp_path, n=1):
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
                            trimesh.load(case / "library/certain3i_4_1/mesh.stl",
                                         force="mesh"))
    return scan, lib, gt


@pytest.mark.slow
def test_qc_renders_land_in_package_and_hashed_manifest(tmp_path):
    scan, lib, gt = _embedded_case(tmp_path)
    out = tmp_path / "out"
    summary = run_auto_case(
        case_id="qc", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[ConfirmedSite(tooth=8,
                                 center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=out)

    manifest = json.loads((out / "qc-manifest.json").read_text())
    by_name = {f["name"]: f for f in manifest["files"]}
    for name in ("qc-8-clockview.png", "qc-8-deviation.png"):
        p = out / name
        assert p.is_file() and p.stat().st_size > 0, f"{name} missing or empty"
        assert name in by_name, f"{name} not in the hashed manifest"
        assert by_name[name]["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest(), \
            f"{name}: manifest hash does not verify against the file on disk"
        assert name in summary["package_files"], \
            f"{name} absent from the report's package file list"


@pytest.mark.slow
def test_render_qc_false_omits_renders(tmp_path):
    scan, lib, gt = _embedded_case(tmp_path)
    out = tmp_path / "out"
    summary = run_auto_case(
        case_id="noqc", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[ConfirmedSite(tooth=8,
                                 center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=out, render_qc=False)

    assert not list(out.glob("*.png")), "render_qc=False must not write PNGs"
    assert not any(n.endswith(".png") for n in summary["package_files"])


def test_render_site_qc_writes_files_even_without_clocking(tmp_path):
    """icp-seated sites carry clocking=None — the renders must still land (labelled
    n/a), because the package promises both PNGs for every site."""
    tmpl = make_scan_body_mesh()
    pts = np.asarray(tmpl.vertices, float)  # a perfect "scan" in canonical frame
    paths, stats = render_site_qc("t", 30, pts, np.eye(4), tmpl, None, tmp_path)
    assert [p.name for p in paths] == ["t-30-clockview.png", "t-30-deviation.png"]
    for p in paths:
        assert p.is_file() and p.stat().st_size > 0, f"{p.name} missing or empty"
    assert set(stats) >= {"rms_mm", "p90_mm", "n_footprint", "n_samples"}


def test_row_and_renderer_share_one_deviation_source(tmp_path):
    """Panel-completion contract (§8 item 12): the scalars the run row stashes
    (site_deviation_stats, the render_qc=False path) must be EXACTLY the stats the
    render call returns — one instrument, two consumers, no drift."""
    from case_prep.adapters.qc_render import site_deviation_stats

    tmpl = make_scan_body_mesh()
    np.random.seed(11)
    pts, _ = trimesh.sample.sample_surface(tmpl, 40000)
    pts = (np.asarray(pts, float)
           + np.random.default_rng(7).normal(0.0, 0.02, (len(pts), 3)))
    _, rendered_stats = render_site_qc("t", 30, pts, np.eye(4), tmpl, None, tmp_path)
    assert site_deviation_stats(pts, np.eye(4), tmpl) == rendered_stats


def test_site_deviation_stats_deterministic_and_rng_state_safe():
    """The stats-only path holds the same house rules as signed_deviation: ambient
    RNG cannot change the reading, and the global stream is restored bit-exact."""
    from case_prep.adapters.qc_render import site_deviation_stats

    tmpl = make_scan_body_mesh()
    np.random.seed(11)
    pts, _ = trimesh.sample.sample_surface(tmpl, 40000)
    pts = (np.asarray(pts, float)
           + np.random.default_rng(7).normal(0.0, 0.02, (len(pts), 3)))

    np.random.seed(123)
    a = site_deviation_stats(pts, np.eye(4), tmpl)
    np.random.seed(999)
    b = site_deviation_stats(pts, np.eye(4), tmpl)
    assert a == b, "deviation stats depend on ambient RNG state"
    assert a["rms_mm"] is not None and a["p90_mm"] is not None

    np.random.seed(42)
    expected = np.random.get_state()
    np.random.seed(42)
    site_deviation_stats(pts, np.eye(4), tmpl)
    after = np.random.get_state()
    for e, x in zip(expected, after):
        assert np.array_equal(e, x), "site_deviation_stats perturbed the global RNG"


def test_deviation_stats_deterministic_and_rng_state_safe():
    tmpl = make_scan_body_mesh()
    # dense synthetic "scan" ON the template surface (+20um noise) — bare vertices are
    # too sparse: nearest-vertex distance would measure mesh resolution, not deviation
    np.random.seed(5)
    pts, _ = trimesh.sample.sample_surface(tmpl, 60000)
    pts = (np.asarray(pts, float)
           + np.random.default_rng(3).normal(0.0, 0.02, (len(pts), 3)))

    np.random.seed(123)
    _, signed_a, stats_a = signed_deviation(pts, tmpl)
    np.random.seed(999)  # a different ambient stream must not change the reading
    _, signed_b, stats_b = signed_deviation(pts, tmpl)
    assert stats_a == stats_b, "deviation stats depend on ambient RNG state"
    assert np.array_equal(signed_a, signed_b)

    # house rule: sampling must save/restore the global RNG stream mid-pipeline
    np.random.seed(42)
    expected = np.random.get_state()
    np.random.seed(42)
    signed_deviation(pts, tmpl)
    after = np.random.get_state()
    for e, a in zip(expected, after):
        assert np.array_equal(e, a), "signed_deviation perturbed the global RNG state"

    # behavioural: a near-perfect seat reads near-zero footprint deviation
    assert stats_a["n_footprint"] >= 20
    assert stats_a["p90_mm"] < 0.15, \
        f"p90 {stats_a['p90_mm']:.2f}mm on a 0.02mm-noise self-scan — sign/units wrong?"


@pytest.mark.skipif(
    not (Path(__file__).parents[1]
         / "data/real/scans/doctor-295811960-neodent-gm").exists(),
    reason="real client scan not on this host")
@pytest.mark.slow
def test_real_site_qc_renders_no_crash(tmp_path):
    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(root / "scans/doctor-295811960-neodent-gm/lower_jaw.stl",
                        force="mesh")
    out = run_auto_case(
        case_id="rqc", scan=scan,
        library=CapLibrary.load(root / "library/caps/neodent-gm"),
        construction_mesh=trimesh.load(
            root / "library/construction/dess/neodent-gm-scanbody.stl", force="mesh"),
        vendor="dess", confirmed=[ConfirmedSite(29, (12.3, 9.8, 19.4))],
        jaw_label="lower", out_dir=tmp_path / "out")
    for name in ("rqc-29-clockview.png", "rqc-29-deviation.png"):
        p = tmp_path / "out" / name
        assert p.is_file() and p.stat().st_size > 0, f"{name} missing or empty"
        assert name in out["package_files"]


class TestAlignmentProof:
    """The picture of an operator-adjusted pose. The audit block already records WHAT was
    done; this renders it — occlusal + one oblique, provenance printed on the image — and
    ONLY for a site a human touched (a clean automatic run emits nothing here; that side
    of the contract is pinned in tests/test_server_best_fit.py)."""

    @staticmethod
    def _adjustments(n=1):
        return [{"ts": "2026-07-25T10:0%d:00" % i, "operation": "best-fit",
                 "who": "operator (this API captures no identity)",
                 "detail": "moved 0.190mm / 1.75 deg"} for i in range(n)]

    def test_writes_the_named_proof_png(self, tmp_path):
        from case_prep.adapters.qc_render import render_alignment_proof

        tmpl = make_scan_body_mesh()
        pts = np.asarray(tmpl.vertices, float)
        path = render_alignment_proof("prf", 30, pts, np.eye(4), tmpl,
                                      self._adjustments(), tmp_path)
        assert path.name == "prf-30-alignment-proof.png"
        assert path.is_file() and path.stat().st_size > 0

    def test_the_provenance_block_names_who_what_and_how_much(self):
        from case_prep.adapters.qc_render import _provenance_text

        text = _provenance_text(self._adjustments(4))
        assert "operator adjustments: 4" in text        # how many
        assert "showing the last 3" in text             # ...and that it is truncating
        assert "best-fit" in text                       # what
        assert "this API captures no identity" in text  # who — honestly
        assert "0.190mm / 1.75 deg" in text             # how much
        assert _provenance_text([]) == "no operator adjustment recorded"

    def test_the_render_is_deterministic_and_rng_state_safe(self, tmp_path):
        """It draws the part from its own VERTICES and the scan from evenly spaced
        indices — no sampling at all — so the pinned pipeline stream cannot be touched
        and two renders of one pose draw the same points."""
        from case_prep.adapters.qc_render import _thin, render_alignment_proof

        tmpl = make_scan_body_mesh()
        np.random.seed(3)
        pts, _ = trimesh.sample.sample_surface(tmpl, 30000)
        pts = np.asarray(pts, float)

        np.random.seed(5)
        before = np.random.rand(4).tolist()
        np.random.seed(5)
        render_alignment_proof("prf", 30, pts, np.eye(4), tmpl,
                               self._adjustments(), tmp_path)
        assert np.random.rand(4).tolist() == before, "the render consumed the RNG stream"
        assert np.array_equal(_thin(pts, 100), _thin(pts, 100))

    def test_the_oblique_view_is_a_different_projection_of_the_same_points(self):
        # the second panel must actually show another side — an oblique that collapsed
        # back onto the occlusal would be a duplicate panel dressed as evidence
        from case_prep.adapters.qc_render import _oblique

        tmpl = make_scan_body_mesh()
        v = np.asarray(tmpl.vertices, float)
        u, w, depth = _oblique(v)
        assert len(u) == len(w) == len(depth) == len(v)
        # height separates in the oblique (it cannot in a top-down view)
        top, bottom = v[:, 2] > v[:, 2].max() - 0.5, v[:, 2] < v[:, 2].min() + 0.5
        assert w[top].mean() > w[bottom].mean() + 1.0


# --- THE DEVIATION INSTRUMENT IS ONE INSTRUMENT ---------------------------------------
# The three-panel verify view (client's library-selection flow, 2026-07-25) colours the
# union overlay by per-vertex deviation while the acceptance PNG colours seeded surface
# samples. Both must be the SAME reading: qc_render.deviation_at_points is the single
# kernel, and these tests pin that it is — exactly on identical points, and numerically
# on a real catalog cap where the two point sets differ.

_REAL_CAPS = Path(__file__).parents[1] / "data/real/library/caps/neodent-gm"


class TestDeviationInstrumentAgreement:
    def test_the_png_path_is_the_shared_kernel_verbatim(self):
        from case_prep.adapters.qc_render import deviation_at_points

        tmpl = make_scan_body_mesh()
        np.random.seed(5)
        pts, _ = trimesh.sample.sample_surface(tmpl, 40000)
        pts = (np.asarray(pts, float)
               + np.random.default_rng(3).normal(0.0, 0.02, (len(pts), 3)))

        samples, signed, stats = signed_deviation(pts, tmpl)
        # re-read the SAME points through the kernel the vertex path calls: byte-equal,
        # or the two panels are showing the doctor two different instruments
        normals = _sample_normals(tmpl, len(samples))
        again, again_stats = deviation_at_points(pts, samples, normals, tmpl)
        assert np.array_equal(signed, again)
        assert stats == again_stats

    def test_the_vertex_path_reads_the_kernel_at_the_template_vertices(self):
        from case_prep.adapters.qc_render import (deviation_at_points,
                                                  vertex_deviation)

        tmpl = make_scan_body_mesh()
        np.random.seed(5)
        pts, _ = trimesh.sample.sample_surface(tmpl, 40000)
        pts = np.asarray(pts, float)

        posed, signed, stats = vertex_deviation(pts, np.eye(4), tmpl)
        # pose = identity, so the posed points ARE the template's vertices
        assert np.allclose(posed, np.asarray(tmpl.vertices, float))
        direct, direct_stats = deviation_at_points(
            pts, np.asarray(tmpl.vertices, float),
            np.asarray(tmpl.vertex_normals, float), tmpl)
        assert np.array_equal(signed, direct)
        assert stats == direct_stats

    def test_the_vertex_path_carries_the_pose_into_the_jaw_frame(self):
        from case_prep.adapters.qc_render import vertex_deviation

        tmpl = make_scan_body_mesh()
        pose = np.eye(4)
        pose[:3, 3] = [10.0, -4.0, 2.5]
        np.random.seed(5)
        pts, _ = trimesh.sample.sample_surface(tmpl, 20000)
        posed, _signed, _stats = vertex_deviation(
            np.asarray(pts, float) + pose[:3, 3], pose, tmpl)
        assert np.allclose(posed, np.asarray(tmpl.vertices, float) + pose[:3, 3])

    def test_the_vertex_path_is_deterministic(self):
        from case_prep.adapters.qc_render import vertex_deviation

        tmpl = make_scan_body_mesh()
        np.random.seed(5)
        pts = np.asarray(trimesh.sample.sample_surface(tmpl, 20000)[0], float)
        np.random.seed(11)
        _, a, sa = vertex_deviation(pts, np.eye(4), tmpl)
        np.random.seed(777)  # a different ambient stream must not change the reading
        _, b, sb = vertex_deviation(pts, np.eye(4), tmpl)
        assert np.array_equal(a, b) and sa == sb

    @pytest.mark.skipif(not _REAL_CAPS.is_dir(),
                        reason="the real cap library is not on this host")
    def test_the_two_point_sets_are_different_aggregates_of_the_same_reading(self):
        """The kernel is shared; the AGGREGATES are not interchangeable, and saying so is
        the point of this test. The PNG samples the surface by AREA (12k seeded points);
        a CAD mesh's vertices crowd around features and thin out on flat walls, so the
        footprint RMS over the vertices is a DIFFERENT weighting of the same distances
        (measured on the real cap7030 site: 0.361 vertex-weighted vs 0.427 area-uniform).

        The API therefore publishes the AREA-UNIFORM scalars for the three-panel view
        (server.site_deviation, ``stats``) and uses the vertex values only for colour.
        Anyone tempted to "simplify" by publishing the vertex aggregate instead should
        fail here first."""
        from case_prep.adapters.qc_render import vertex_deviation

        lib = CapLibrary.load(_REAL_CAPS)
        spec = next(sp for sp in lib.specs if sp.variant == "5020")
        tmpl = lib.template(spec)
        np.random.seed(5)
        pts = np.asarray(trimesh.sample.sample_surface(tmpl, 80000)[0], float)
        pts = pts + np.random.default_rng(3).normal(0.0, 0.02, (len(pts), 3))

        _s, _sig, png_stats = signed_deviation(pts, tmpl)
        _p, vsigned, vertex_stats = vertex_deviation(pts, np.eye(4), tmpl)
        assert png_stats["n_samples"] == 12000                    # the seeded draw
        assert vertex_stats["n_samples"] == len(tmpl.vertices)    # the CAD's own points
        assert png_stats["n_footprint"] >= 20 and vertex_stats["n_footprint"] >= 20
        # same instrument, same surface: both must land in the same millimetre world on
        # a 20um-noise self-scan — a sign flip or a unit error would blow this apart
        assert vertex_stats["rms_mm"] < 0.15 and png_stats["rms_mm"] < 0.15
        assert float(np.abs(vsigned).max()) < 1.0


def _sample_normals(template, n):
    """The face normals ``signed_deviation`` pairs with its own seeded samples — the
    same seeded draw, replayed, so a kernel comparison uses identical inputs."""
    state = np.random.get_state()
    try:
        np.random.seed(7)
        _samples, fidx = trimesh.sample.sample_surface(template, 12000)
    finally:
        np.random.set_state(state)
    assert len(fidx) == n
    return np.asarray(template.face_normals, float)[np.asarray(fidx, int)]
