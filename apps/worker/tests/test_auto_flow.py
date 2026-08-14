"""The seamless clinical flow: PROPOSE -> (human) CONFIRM -> align -> measure -> package.

Detection on real arches is auto-propose + human-confirm (measured decision, 2026-07-03: no
fully-automatic arbiter separates low-profile caps from tissue artifacts at n=2 arches — the
operator confirms each proposed site in one click). Everything downstream of confirmation is
automatic: template alignment, interproximal site measurement, advisory gating, and the
industry-grounded 3-file output package.

Tests are self-contained (synthetic arch + synthetic cap CAD); real-arch behaviour is guarded
by the detection/e2e suites.

MODULE NOTE — ``gingival_offset_mm=0.0`` on the runs below (2026-07-25). These tests pass
``make_scan_body_mesh()`` as a STAND-IN vendor construction part; its anti-rotation flat sits
0.4mm off the axis, so the r=1.0 bore already cuts through it and the client's 0.20mm gingival
relief leaves 3 disconnected bodies — which the G5 export gate correctly refuses (fail-closed,
nothing written). None of these tests is about the relief, so they build the product with none;
the relief's own contract (0.0 byte-identity, 0.20 measurably relieves, a fragmenting relief
fails the export closed) lives in ``test_final_product.py::TestGingivalProfileOffset``.

EXTENDED to the REAL-FLEET runs (2026-07-25, same wave). The relief-gate promotion in
``output_package._relief_block_reason`` fails the export CLOSED when the relief destroys or
undercuts the as-built screw channel, and the real vendor parts hit that at the client's
0.20mm default: MEASURED, atlantis/zimmer-4.5-scanbody bored at the 7030 cap's channel goes
from a wall of 0.224mm to NO measurable channel, and dess/neodent-gm-scanbody bored at the
5020 cap's channel goes 0.389 -> 0.105mm wall. Every fleet test below is about SEATING,
CLOCKING or IDENTIFICATION — none reads the production set — so they run with no relief and
the gate's own contract stays in ``test_output_package.py::TestGingivalReliefBlock``, which
pins those two measurements on the real parts. The finding itself (the client's default is
not safe on every catalog part) is a product decision, not a test-fixture problem.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.synthetic import make_gingiva_arch, make_scan_body_mesh
from case_prep.domain.cap_catalog import CapSpec
from case_prep.pipeline.auto_flow import ConfirmedSite, propose_sites, run_auto_case


def _embedded_case(tmp_path, n=2):
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
def test_run_auto_case_emits_package_and_report(tmp_path):
    scan, lib, gt = _embedded_case(tmp_path)
    confirmed = [ConfirmedSite(tooth=19 + i, center=tuple(map(float, p.position)))
                 for i, p in enumerate(gt.poses)]

    out = tmp_path / "out"
    summary = run_auto_case(
        case_id="case-001", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=confirmed, jaw_label="upper", out_dir=out)

    # every confirmed site aligned, measured, advisory-gated
    assert len(summary["sites"]) == 2
    for site in summary["sites"]:
        assert site["advisory"] is True                      # real data class: never auto-passes
        assert site["spec"] == "certain-4.1"
        assert site["alignment_error_mm"] < 2.5              # aligned near the confirmed center
        assert "md_span_mm" in site["site_measurement"]      # interproximal gap measured

    # the industry package landed: raw jaw + per-site records + manifest
    files = {p.name for p in out.iterdir()}
    assert "case-001-upper.stl" in files
    assert "case-001-manifest.json" in files
    assert any(f.endswith("-implant.json") for f in files)
    manifest = json.loads((out / "case-001-manifest.json").read_text())
    assert manifest["sites"][0]["advisory"] is True

    # the auto-report captures the full decision trail
    report = json.loads((out / "case-001-auto-report.json").read_text())
    assert report["mode"] == "propose+confirm"
    assert len(report["confirmed_sites"]) == 2


# THE EIGHT BOOLEAN-COMPOSITE ARTIFACTS a run may write (client spec 2026-07-11
# through 2026-08-11): the arch fused with caps/constructions, the two capless/
# platform composites, their socketless/dish/platform layers, and the closed
# model. Named here once so both the run-lane and re-emit-lane pins (test_emit.py)
# check the same list.
_COMPOSITE_SUFFIXES = ("arch-with-healingcaps", "arch-with-constructions",
                      "arch-capless", "arch-platform", "arch-socketless",
                      "socket-dish", "socket-platform", "model-closed")


@pytest.mark.slow
def test_manifest_seals_the_boolean_composites_the_run_emitted(tmp_path):
    """W4 measurement (2026-08-14, ledgered in the product-app-plan): a fleet read
    found 21 emitted files but a manifest that sealed only 10 of them — NONE of the
    eight boolean composites the seal exists to attest. Pin, on a real run through
    ``run_auto_case`` (not a hand-built manifest): every composite this run actually
    wrote is in ``manifest['files']`` with a hash that verifies against the on-disk
    bytes, and a composite this run did NOT write is absent from the seal too — the
    seal must never claim a file that was never emitted."""
    scan, lib, gt = _embedded_case(tmp_path)
    confirmed = [ConfirmedSite(tooth=19 + i, center=tuple(map(float, p.position)))
                 for i, p in enumerate(gt.poses)]

    out = tmp_path / "out"
    case_id = "case-050"
    run_auto_case(
        case_id=case_id, scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=confirmed, jaw_label="upper", out_dir=out)

    manifest = json.loads((out / f"{case_id}-manifest.json").read_text())
    sealed = {f["name"]: f for f in manifest["files"]}
    on_disk = {p.name for p in out.iterdir()}
    composite_names = [f"{case_id}-{suffix}.stl" for suffix in _COMPOSITE_SUFFIXES]

    emitted = [name for name in composite_names if name in on_disk]
    assert emitted, "this run must exercise at least one boolean composite"
    for name in emitted:
        assert name in sealed, f"{name} is on disk but the manifest never sealed it"
        assert sealed[name]["sha256"] == hashlib.sha256(
            (out / name).read_bytes()).hexdigest()
        assert sealed[name]["bytes"] == (out / name).stat().st_size

    absent = [name for name in composite_names if name not in on_disk]
    assert absent, "the fixture is expected to skip at least one composite"
    for name in absent:
        assert name not in sealed, \
            f"{name} was never emitted — it must not be hallucinated into the seal"


def test_run_auto_case_requires_confirmed_sites(tmp_path):
    scan, lib, _ = _embedded_case(tmp_path)
    with pytest.raises(ValueError):
        run_auto_case(case_id="c", scan=scan, library=lib,
                      construction_mesh=make_scan_body_mesh(), vendor="dess",
                      gingival_offset_mm=0.0,  # stand-in body — see module note
                      confirmed=[], jaw_label="upper", out_dir=tmp_path / "out")


@pytest.mark.slow
def test_propose_sites_returns_ranked_candidates_on_a_ring_scene():
    """propose_sites surfaces the generator's candidates (with evidence) for the operator —
    on a scene with one cap ring, the ring is the (top) proposal."""
    rng = np.random.default_rng(3)
    n = int(40 * 20 * 40)
    ging = np.c_[rng.uniform(-20, 20, n), rng.uniform(-10, 10, n), rng.normal(0, 0.05, n)]
    teeth = []
    for cx in (-6.5, 6.5):
        d = rng.normal(size=(7000, 3))
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        d[:, 2] = np.abs(d[:, 2])
        t = np.asarray([cx, 0, 2.0]) + d * 3.0
        t[:, 2] += 2.0 + rng.normal(0, 0.25, 7000)
        teeth.append(t)
    m = 3000
    ang = rng.uniform(0, 2 * np.pi, m)
    rad = rng.uniform(1.2, 2.6, m)
    ring = np.c_[rad * np.cos(ang), rad * np.sin(ang), rng.normal(2.0, 0.15, m)]
    wall = np.c_[2.6 * np.cos(ang), 2.6 * np.sin(ang), rng.uniform(0, 1.8, m)]
    cloud = np.vstack([ging, *teeth, ring, wall])
    normals = np.tile([0.0, 0.0, 1.0], (len(cloud), 1))

    proposals = propose_sites(cloud, normals=normals)
    assert len(proposals) >= 1
    best = proposals[0]  # ranked: best evidence first
    assert np.linalg.norm(np.asarray(best.center[:2])) < 2.5
    assert best.void_ratio <= 0.9


@pytest.mark.slow
def test_declared_variant_mismatch_is_flagged(tmp_path):
    """The billing/clinical gate: the doctor declares a variant; if the scan identifies a
    different one, the site row carries an explainable flag — never a silent guess."""
    scan, lib, gt = _embedded_case(tmp_path, n=1)
    p = gt.poses[0]
    ok = run_auto_case(
        case_id="ok", scan=scan, library=lib, construction_mesh=make_scan_body_mesh(),
        gingival_offset_mm=0.0,  # stand-in body — see module note
        vendor="dess", jaw_label="upper", out_dir=tmp_path / "ok",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, p.position)),
                                 declared_variant="4.1")])
    assert ok["sites"][0]["variant"]["identified"] == "4.1"
    assert ok["sites"][0]["variant"]["flags"] == []

    bad = run_auto_case(
        case_id="bad", scan=scan, library=lib, construction_mesh=make_scan_body_mesh(),
        gingival_offset_mm=0.0,  # stand-in body — see module note
        vendor="dess", jaw_label="upper", out_dir=tmp_path / "bad",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, p.position)),
                                 declared_variant="6030")])
    flags = bad["sites"][0]["variant"]["flags"]
    assert any("6030" in f and "declared" in f for f in flags)


@pytest.mark.slow
def test_brush_marked_region_drives_alignment_and_reports_comparison(tmp_path):
    """RealGUIDE-style brush (client spec): the operator PAINTS the healing-cap area; the
    painted patch becomes the registration ROI directly — the human-loop guarantee — and the
    result reports the seed source plus the delta to the automation's own proposal so the
    two can be compared."""
    scan, lib, gt = _embedded_case(tmp_path, n=1)
    truth = np.asarray(gt.poses[0].position, float)
    pts = np.asarray(scan.vertices, float)
    patch = pts[np.linalg.norm(pts - truth, axis=1) < 4.0]  # the "painted" cap area
    assert len(patch) > 100

    summary = run_auto_case(
        case_id="brush", scan=scan, library=lib, construction_mesh=make_scan_body_mesh(),
        gingival_offset_mm=0.0,  # stand-in body — see module note
        vendor="dess", jaw_label="upper", out_dir=tmp_path / "out",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, truth)),
                                 marked_points=[list(map(float, p)) for p in patch[::5]])],
        proposals=[list(map(float, truth + [0.8, 0.0, 0.0]))])  # automation's own proposal

    row = summary["sites"][0]
    assert row["seed_source"] == "brush"
    assert row["alignment_error_mm"] < 2.5           # the painted ROI aligned the cap
    # the comparison is LIKE-FOR-LIKE: the human's site reference (painted-patch centroid)
    # vs the automation's proposal center — never the component pose origin, which would
    # bake a constant collar-height bias into the client-facing number
    marked = np.asarray(patch[::5], float)
    expected = float(np.linalg.norm(marked.mean(axis=0) - (truth + [0.8, 0.0, 0.0])))
    assert row["auto_delta_mm"] == pytest.approx(expected, abs=1e-9)


@pytest.mark.slow
def test_run_auto_case_is_deterministic_across_ambient_rng_state(tmp_path):
    """Clinical requirement: same inputs -> same outputs. Template registration and coverage
    scoring sample surfaces through numpy's GLOBAL RNG; left unpinned, the measured pose and
    the identified variant wobble between runs (observed on real arches: rim-diameter class
    flips across the 0.8mm boundary). The flow must pin its own seed."""
    scan, lib, gt = _embedded_case(tmp_path)
    confirmed = [ConfirmedSite(tooth=19 + i, center=tuple(map(float, p.position)))
                 for i, p in enumerate(gt.poses)]

    def one_run(tag, ambient_seed):
        np.random.seed(ambient_seed)  # deliberately different ambient state per run
        return run_auto_case(case_id="case-det", scan=scan, library=lib,
                             construction_mesh=make_scan_body_mesh(), vendor="dess",
                             gingival_offset_mm=0.0,  # stand-in body — see module note
                             confirmed=confirmed, jaw_label="upper",
                             out_dir=tmp_path / tag)

    a, b = one_run("a", 123), one_run("b", 999)
    assert len(a["sites"]) == len(b["sites"]) == 2
    for sa, sb in zip(a["sites"], b["sites"]):
        assert sa["variant"]["identified"] == sb["variant"]["identified"]
        assert sa["coverage"] == pytest.approx(sb["coverage"], abs=1e-12)
        assert sa["alignment_error_mm"] == pytest.approx(sb["alignment_error_mm"], abs=1e-9)


@pytest.mark.slow
def test_squat_cap_recovered_axis_matches_ground_truth(tmp_path):
    """The user-visible bug (2026-07-11 screenshots): squat healing caps canonicalized by
    tallest-PCA-axis carry a DIAMETER on local +z, so the aligned pose's z — trusted by the
    implant record, cap-region removal and construction seating — pointed sideways (~67-89
    deg off occlusal on the real cases). The cap frame must be the rotational-symmetry axis."""
    from case_prep.adapters.real_case import build_embedded_case

    # squat like the vendor caps (8 wide, 3.5 tall) WITH a domed top — a featureless
    # flat-top cylinder is perfectly flip-symmetric from its visible side, which no
    # registration could orient; real caps carry the dome/bevel that breaks the tie
    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    r = np.linalg.norm(v[top, :2], axis=1)
    v[top, 2] += 1.2 * (1.0 - (r / 4.0) ** 2)  # parabolic dome, apex +1.2mm
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    from case_prep.adapters.ingest import canonicalize_revolute
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")

    out = tmp_path / "out"
    run_auto_case(case_id="squat", scan=scan,
                  library=CapLibrary.single(CapSpec("acme", "7020"), cap),
                  construction_mesh=make_scan_body_mesh(), vendor="dess",
                  gingival_offset_mm=0.0,  # stand-in body — see module note
                  confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, gt.poses[0].position)))],
                  jaw_label="upper", out_dir=out)

    rec = json.loads((out / "squat-8-implant.json").read_text())
    gt_axis = np.asarray(gt.poses[0].axis, float)
    axis = np.asarray(rec["axis"], float)
    # SIGNED: an upside-down cap (axis pointing gingivally) is exactly as wrong as a
    # sideways one — measured on the real Zimmer arch before the occlusal axis seed
    tilt = np.degrees(np.arccos(np.clip(axis @ gt_axis, -1.0, 1.0)))
    assert tilt < 25.0, f"pose z is {tilt:.0f} deg off the true cap axis (signed)"


@pytest.mark.skipif(
    not (__import__("pathlib").Path(__file__).parents[1]
         / "data/real/scans/doctor-zimmer-4.5").exists(),
    reason="real client scan not on this host")
@pytest.mark.slow
def test_real_zimmer_cap_seats_occlusally(tmp_path):
    """Real-arch guard for the user-reported bug (2026-07-11): the aligned Zimmer cap
    rendered tilted/upside-down in the deliverables. The aligned pose axis must point
    occlusally, within implant-plausible tilt of crowns-up."""
    from pathlib import Path

    from case_prep.pipeline.auto_flow import _crowns_frame

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(next((root / "scans/doctor-zimmer-4.5").glob("*.stl")), force="mesh")
    lib = CapLibrary.load(root / "library/caps/zimmer-4.5")
    sites = json.loads((root / "scans/doctor-zimmer-4.5/sites.json").read_text())["suggested_sites"]

    run_auto_case(case_id="zg", scan=scan, library=lib,
                  construction_mesh=trimesh.load(
                      root / "library/construction/atlantis/zimmer-4.5-scanbody.stl", force="mesh"),
                  vendor="atlantis",
                  confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]),
                                           s.get("declared_variant"))
                             for s in sites],
                  gingival_offset_mm=0.0,  # real vendor part — see module note
                  jaw_label="upper", out_dir=tmp_path / "out")

    frame, _, _ = _crowns_frame(np.asarray(scan.vertices, float),
                                np.asarray(scan.vertex_normals, float))
    up = frame @ np.array([0.0, 0.0, 1.0])
    rec = json.loads((tmp_path / "out" / "zg-7-implant.json").read_text())
    tilt = np.degrees(np.arccos(np.clip(np.asarray(rec["axis"], float) @ up, -1.0, 1.0)))
    assert tilt < 35.0, f"real zimmer cap axis {tilt:.0f} deg from occlusal (signed)"


@pytest.mark.skipif(
    not (__import__("pathlib").Path(__file__).parents[1]
         / "data/real/scans/doctor-295811960-neodent-gm").exists(),
    reason="real client scan not on this host")
@pytest.mark.slow
def test_real_295811960_cap_seats_on_the_visible_cap(tmp_path):
    """Real-arch seat guard (user-reported, 2026-07-11): the aligned template must COVER the
    scanned cap's visible surface — a fit whose top merely grazes the dome while the body
    pokes out of the buccal ridge slope reads fine on trimmed RMSE but is visibly wrong.
    Metric: p90 distance from the visible cap surface to the posed template."""
    from pathlib import Path

    from scipy.spatial import cKDTree

    from case_prep.pipeline.auto_flow import _crowns_frame

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(root / "scans/doctor-295811960-neodent-gm/lower_jaw.stl", force="mesh")
    center = [12.3, 9.8, 19.4]  # curated sites.json center
    run_auto_case(case_id="sg", scan=scan,
                  library=CapLibrary.load(root / "library/caps/neodent-gm"),
                  construction_mesh=trimesh.load(
                      root / "library/construction/dess/neodent-gm-scanbody.stl", force="mesh"),
                  vendor="dess", confirmed=[ConfirmedSite(29, tuple(center))],
                  gingival_offset_mm=0.0,  # real vendor part — see module note
                  jaw_label="lower", out_dir=tmp_path / "out")

    tmpl = trimesh.load(tmp_path / "out" / "sg-29-healingcap-aligned.stl", force="mesh")
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    site = frame.T @ (np.asarray(center, float) - origin)
    d_xy = np.linalg.norm(L[:, :2] - site[:2], axis=1)
    # seat metric over the RIM ANNULUS only: the screw recess is excluded because the
    # template has a BORE there (no surface to be near — a perfect seat still reads ~1mm
    # on recess points), and points below the rim band are collar/tissue
    near = L[d_xy < 2.4]
    rim_z = np.percentile(near[:, 2], 80)
    ann_local = L[(d_xy > 1.0) & (d_xy < 2.5) & (L[:, 2] > rim_z - 1.2)]
    ann_world = ann_local @ frame.T + origin
    d = cKDTree(np.asarray(tmpl.vertices, float)).query(ann_world)[0]
    p90 = float(np.percentile(d, 90))
    # 1.2mm bar: the user-reported graze-and-poke fit reads >=1.5 here; a seated top with
    # the cap's own ~10-16 deg surface tilt reads ~1.0
    assert p90 < 1.2, f"rim-band p90 distance to template {p90:.2f}mm — not seated"


@pytest.mark.slow
def test_sparse_brush_marks_align_like_a_click(tmp_path):
    """Client spec (2026-07-11): the brush marks POINT AT the cap — the first mark can be
    just its center. A few dabs must produce the same seat as a full patch or a click:
    the marks seed the location, the SCAN provides the surface. (Regression: sparse dabs
    fed raw into registration left the cap floating sideways.)"""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    truth = np.asarray(gt.poses[0].position, float)

    # FIVE sparse dabs: the center + four points on the cap top — pointers, not a patch
    pts = np.asarray(scan.vertices, float)
    near = pts[np.linalg.norm(pts - truth, axis=1) < 3.0]
    dabs = [list(map(float, truth))] + [list(map(float, near[i])) for i in
                                        np.linspace(0, len(near) - 1, 4).astype(int)]

    out = tmp_path / "out"
    summary = run_auto_case(case_id="dabs", scan=scan,
                            library=CapLibrary.single(CapSpec("acme", "7020"), cap),
                            construction_mesh=make_scan_body_mesh(), vendor="dess",
                            gingival_offset_mm=0.0,  # stand-in body — see module note
                            confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, truth)),
                                                     marked_points=dabs)],
                            jaw_label="upper", out_dir=out)
    row = summary["sites"][0]
    assert row["seed_source"] == "brush"
    assert row["alignment_error_mm"] < 2.5
    rec = json.loads((out / "dabs-8-implant.json").read_text())
    tilt = np.degrees(np.arccos(np.clip(
        np.asarray(rec["axis"], float) @ np.asarray(gt.poses[0].axis, float), -1.0, 1.0)))
    assert tilt < 25.0, f"sparse-dab brush seated {tilt:.0f} deg off (signed)"


@pytest.mark.slow
def test_declared_variant_drives_alignment_and_fit_stats_are_reported(tmp_path):
    """RealGUIDE-parity flow (client spec, 2026-07-12): the doctor CHOOSES the variant from
    the library (6 per model) and alignment uses exactly that template; the row reports
    registration-error stats (avg/max mm) like RealGUIDE's Registration Error dialog."""
    scan, lib, gt = _embedded_case(tmp_path, n=1)
    p = gt.poses[0]
    out = run_auto_case(
        case_id="pick", scan=scan, library=lib, construction_mesh=make_scan_body_mesh(),
        gingival_offset_mm=0.0,  # stand-in body — see module note
        vendor="dess", jaw_label="upper", out_dir=tmp_path / "out",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, p.position)),
                                 declared_variant="4.1")])
    row = out["sites"][0]
    assert row["variant"]["identified"] == "4.1"   # the doctor's pick drove the template
    fit = row["fit"]
    assert 0.0 < fit["avg_mm"] < 1.0               # seated: sub-mm average error
    assert fit["max_mm"] >= fit["avg_mm"]


@pytest.mark.slow
def test_rows_carry_actionable_guidance(tmp_path):
    """The advisory gate GUIDES (client spec, 2026-07-12): every site row carries a
    guidance verdict + concrete operator actions, and the seat method is visible."""
    scan, lib, gt = _embedded_case(tmp_path, n=1)
    out = run_auto_case(
        case_id="g", scan=scan, library=lib, construction_mesh=make_scan_body_mesh(),
        gingival_offset_mm=0.0,  # stand-in body — see module note
        vendor="dess", jaw_label="upper", out_dir=tmp_path / "out",
        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, gt.poses[0].position)))])
    row = out["sites"][0]
    assert row["seat_method"] in ("rim", "icp")
    g = row["guidance"]
    assert g["level"] in ("ready", "attention", "action-needed")
    assert g["actions"] and all(isinstance(a, str) and a for a in g["actions"])


@pytest.mark.slow
def test_rim_seated_sites_report_per_variant_candidates(tmp_path):
    """Billing honesty (loop item, 2026-07-12): a rim-seated site reports EVERY candidate
    variant's seat residual — when two heights are inseparable the row says so instead of
    silently picking one (the known height-within-class wobble, made explicit)."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    def squat(height):
        cyl = trimesh.creation.cylinder(radius=4.0, height=height, sections=48)
        keep = cyl.triangles_center[:, 2] > -height * 0.49
        m = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
        m.remove_unreferenced_vertices()
        v = np.asarray(m.vertices, float).copy()
        top = v[:, 2] > height * 0.49
        v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
        return trimesh.Trimesh(v, m.faces.copy(), process=False)

    lib_dir = tmp_path / "caps/acme-1"
    lib_dir.mkdir(parents=True)
    squat(3.4).export(lib_dir / "acme-1-8020.stl")
    squat(5.4).export(lib_dir / "acme-1-8030.stl")
    lib = CapLibrary.load(lib_dir)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    squat(3.4).export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")

    out = run_auto_case(case_id="cand", scan=scan, library=lib,
                        construction_mesh=make_scan_body_mesh(), vendor="dess",
                        gingival_offset_mm=0.0,  # stand-in body — see module note
                        confirmed=[ConfirmedSite(tooth=8,
                                                 center=tuple(map(float, gt.poses[0].position)))],
                        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    if row["seat_method"] == "rim":
        cands = row["variant"]["candidates"]
        assert len(cands) == 2
        assert cands == sorted(cands, key=lambda c: c["seat_residual_mm"])
        assert {c["variant"] for c in cands} == {"8020", "8030"}


@pytest.mark.slow
def test_report_surfaces_candidates_too_close(tmp_path):
    """Slice 4 (master plan §8 item 12, plan-named test): the inseparable-variants
    verdict — computed since 2026-07-14 but consumed only by guidance (an invisible
    high-blocker) — is SURFACED on the row. Known-tie fixture: two library heights
    0.1mm apart are inseparable by physics on a squat cap's visible surface; the row
    flag must agree with the shipped tie rule applied to the row's own reported
    candidates, and a tie routes the doctor's confirmation through guidance."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    def squat(height):
        cyl = trimesh.creation.cylinder(radius=4.0, height=height, sections=48)
        keep = cyl.triangles_center[:, 2] > -height * 0.49
        m = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
        m.remove_unreferenced_vertices()
        v = np.asarray(m.vertices, float).copy()
        top = v[:, 2] > height * 0.49
        v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
        return trimesh.Trimesh(v, m.faces.copy(), process=False)

    lib_dir = tmp_path / "caps/acme-1"
    lib_dir.mkdir(parents=True)
    squat(3.4).export(lib_dir / "acme-1-8020.stl")
    squat(3.5).export(lib_dir / "acme-1-8021.stl")  # 0.1mm apart: a physics tie
    lib = CapLibrary.load(lib_dir)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    squat(3.4).export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1,
                             seed=1, canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")

    out = run_auto_case(case_id="tie", scan=scan, library=lib,
                        construction_mesh=make_scan_body_mesh(), vendor="dess",
                        gingival_offset_mm=0.0,  # stand-in body — see module note
                        confirmed=[ConfirmedSite(
                            tooth=8, center=tuple(map(float, gt.poses[0].position)))],
                        jaw_label="upper", out_dir=tmp_path / "out", render_qc=False)
    row = out["sites"][0]
    if row["seat_method"] != "rim":
        pytest.skip("fixture did not rim-seat — the tie rule only exists on rim seats")
    cands = row["variant"]["candidates"]
    assert len(cands) == 2
    # the surfaced flag == the shipped tie rule on the row's own candidate residuals
    tie = (cands[1]["seat_residual_mm"] - cands[0]["seat_residual_mm"]
           < max(0.05, 0.1 * cands[0]["seat_residual_mm"]))
    assert row["variant"]["candidates_too_close"] is tie
    assert tie, "0.1mm-apart heights must be inseparable — fixture no longer a tie"
    # guidance still consumes it (visibility added, behavior unchanged)
    assert row["guidance"]["level"] != "ready"


def _all_real_sites():
    root = Path(__file__).parents[1] / "data/real/scans"
    if not root.exists():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        sj = folder / "sites.json"
        if not sj.exists():
            continue
        for s in json.loads(sj.read_text())["suggested_sites"]:
            out.append((folder.name, s["tooth"], tuple(s["center"]),
                        s.get("declared_variant"), s.get("center_mark"), s.get("rim_mark")))
    return out


from pathlib import Path  # noqa: E402  (test helper import)


@pytest.mark.parametrize("folder,tooth,center,declared,cmark,rmark",
                         [s for s in _all_real_sites() if s[4] and s[5]],
                         ids=[f"{f.replace('doctor-','')}-t{t}"
                              for f, t, _, _, cm, rm in _all_real_sites() if cm and rm])
@pytest.mark.slow
def test_reclicked_centre_seats_within_physical_bounds(tmp_path, folder, tooth, center,
                                                       declared, cmark, rmark):
    """Client complaint (2026-07-14 screenshots): re-placing the centre mark by CLICKING
    the cap seated the part sideways. A click is the curated centre ±1mm at the scan
    surface — marks are pointers, the scan supplies the geometry, so ANY click on the
    cap top must yield a seat inside the same PHYSICAL bounds as the curated pair
    (tilt in the plausible cone, template on the visible rim band), and a click must
    not silently flip the identified diameter class (measured pre-fix: 40-59 deg
    seats, 6020->4030 flips). Identity to the curated seat was deliberately NOT the
    contract: partial/submerged rims are geometrically bistable at the millimetre
    level — correctness, not identity, is what the doctor needs."""
    from case_prep.pipeline.auto_flow import _crowns_frame

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    model = next(m for m in ["neodent-gm", "zimmer-4.5"] if m in folder)
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    library = CapLibrary.load(root / "library/caps" / model)
    construction = trimesh.load(vendor_dir, force="mesh")
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    cm_local = frame.T @ (np.asarray(cmark, float) - origin)

    def seat(mark, tag):
        # the UI keeps the pair CONSISTENT: re-placing the centre translates the rim
        # mark with it, preserving the doctor's measured radius (the pair is ONE
        # measurement — pairing a fresh centre with a stale rim bakes the click error
        # into the radius, which no downstream check could reliably catch)
        rim = list(np.asarray(rmark, float) + np.asarray(mark, float)
                   - np.asarray(cmark, float))
        out = run_auto_case(case_id=f"rc-{tag}", scan=scan, library=library,
                            construction_mesh=construction, vendor=vendor_dir.parent.name,
                            confirmed=[ConfirmedSite(tooth, center, declared,
                                                     center_mark=mark, rim_mark=rim)],
                            gingival_offset_mm=0.0,  # real vendor part — see module note
                            jaw_label="upper", out_dir=tmp_path / tag)
        row = out["sites"][0]
        assert row.get("error") is None, f"{tag}: {row.get('error')}"
        violation = _seat_bounds_violation(
            scan, center, cmark, rmark,
            tmp_path / tag / f"rc-{tag}-{tooth}-implant.json",
            tmp_path / tag / f"rc-{tag}-{tooth}-healingcap-aligned.stl",
            f"{folder} t{tooth} {tag}")
        return (row.get("variant", {}).get("identified"),
                (row.get("guidance") or {}).get("level"), violation,
                row.get("variant", {}).get("measured_rim_diameter_mm"))

    base_id, base_level, base_violation, _ = seat(list(map(float, cmark)), "curated")
    # curated marks are GOOD marks: the seat must be inside bounds, no excuses
    assert base_violation is None, base_violation and base_violation["msg"]
    # a doctor's click = the top scan-surface point AT the aim point: aiming at the
    # visible centre lands within ~0.8mm (the raycast hits the surface exactly where
    # they click); the 1.2mm fallback only covers very sparse mesh regions
    for tag, (dx, dy) in {"click0": (0.0, 0.0), "clickx": (1.0, 0.0)}.items():
        target = cm_local[:2] + np.array([dx, dy])
        d_t = np.linalg.norm(L[:, :2] - target, axis=1)
        near = np.where(d_t < 0.8)[0]
        if not len(near):
            near = np.where(d_t < 1.2)[0]
        if not len(near):
            continue
        hit = pts[near[np.argmax(L[near, 2])]]
        ident, level, violation, measured = seat(list(map(float, hit)), tag)
        # click0 IS the doctor's gesture (the cap's top centre) — it must seat within
        # the physical bounds, full stop; that is the client's "alignment must work"
        # ask and the fleet delivers it with consistent pairs. clickx (a DELIBERATE
        # 1mm-off click) is held to the class-stability contract below but not to hard
        # bounds: on a partial-rim terminal site the scan geometrically cannot pin an
        # off-centre pair (measured: t4 clickx reads band 2.85 with a full 12-bin ring
        # of wall points — no internal signal separates it), and the advisory policy
        # (visually confirm view 1) covers deliberate mis-marks.
        # DEPTH is the one exception, with the same honest-attention escape as the
        # class check below: a pair on a tall deeply-ambiguous cap cannot always pin
        # depth (zimmer t7 post-axis-fix: polish recovers 2.49 -> 0.82, top face 1.61
        # — imperfect and the gate SAYS so, steering to border clicks, which pin
        # depth exactly). In-bounds, or honestly not READY.
        if tag == "click0":
            if violation is not None and violation.get("kind") == "depth":
                assert level != "ready", \
                    f"{violation['msg']} — and the gate presented READY"
            else:
                assert violation is None, violation and violation["msg"]
        # billing honesty: a click must not silently change the diameter class — either
        # the class holds, the gate refuses to present READY, or (post-axis-fix) the
        # BASE identification was itself ambiguous (non-ready) AND the click's own
        # identification is MEASUREMENT-ANCHORED — its native rim diameter matches the
        # scan-measured visible rim (297589851 t20: curated 4020 sits 0.045 from its
        # runner-up with native dia 3.8 against a measured 5.2, honest ATTENTION; the
        # click's 6020 measures 5.5 native vs 5.40 measured with a clear margin — the
        # click run's evidence is coherent and READY is not a lie).
        if base_id and ident and ident[:2] != base_id[:2] and level == "ready":
            dims = {k.split("-")[-1]: v
                    for k, v in library.variant_dimensions().items()}
            native_dia = (dims.get(ident) or (None,))[0]
            anchored = (base_level != "ready" and measured is not None
                        and native_dia is not None
                        and abs(native_dia - measured) <= 0.8)
            assert anchored, \
                (f"{folder} t{tooth} {tag}: click flipped identified {base_id} -> "
                 f"{ident} yet the gate presented READY (native dia {native_dia} vs "
                 f"measured {measured}, base level {base_level})")


class TestFitCircleXY:
    """The multi-point rim measurement: a Kasa fit through the doctor's border clicks
    recovers centre AND radius, averaging out per-click error."""

    def test_recovers_a_noisy_circle(self):
        from case_prep.pipeline.auto_flow import _fit_circle_xy

        rng = np.random.default_rng(3)
        ang = np.linspace(0, 2 * np.pi, 6, endpoint=False)
        pts = np.c_[10 + 3.2 * np.cos(ang), -4 + 3.2 * np.sin(ang)]
        pts += rng.normal(0, 0.4, pts.shape)  # each click ~±1mm-class error
        out = _fit_circle_xy(pts)
        assert out is not None
        centre, r = out
        assert np.linalg.norm(centre - [10, -4]) < 0.5
        assert abs(r - 3.2) < 0.5

    def test_refuses_one_sided_points(self):
        from case_prep.pipeline.auto_flow import _fit_circle_xy

        ang = np.linspace(0.0, 0.6, 4)  # all clicks bunched on one side
        pts = np.c_[3.0 * np.cos(ang), 3.0 * np.sin(ang)]
        assert _fit_circle_xy(pts) is None

    def test_refuses_fewer_than_three(self):
        from case_prep.pipeline.auto_flow import _fit_circle_xy

        assert _fit_circle_xy(np.array([[0.0, 3.0], [0.0, -3.0]])) is None

    def test_refuses_unphysical_radius(self):
        from case_prep.pipeline.auto_flow import _fit_circle_xy

        ang = np.linspace(0, 2 * np.pi, 6, endpoint=False)
        pts = np.c_[20.0 * np.cos(ang), 20.0 * np.sin(ang)]  # no cap is Ø40
        assert _fit_circle_xy(pts) is None


@pytest.mark.parametrize("folder,tooth,center,declared,cmark,rmark",
                         [s for s in _all_real_sites() if s[4] and s[5]],
                         ids=[f"{f.replace('doctor-','')}-t{t}"
                              for f, t, _, _, cm, rm in _all_real_sites() if cm and rm])
@pytest.mark.slow
def test_multipoint_rim_gesture_seats_within_bounds(tmp_path, folder, tooth, center,
                                                    declared, cmark, rmark):
    """Client spec (2026-07-14): the rim tool is MULTIPLE clicks around the cap's
    visible border; the fitted circle is the measurement. Simulate the doctor's
    gesture — 5 border clicks at scan-surface points near the true rim circle, each
    with click-scale error, plus an imprecise centre click — and the seat must land
    within the same physical bounds as the curated pair on EVERY real site."""
    from case_prep.pipeline.auto_flow import _crowns_frame

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    model = next(m for m in ["neodent-gm", "zimmer-4.5"] if m in folder)
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    cm_local = frame.T @ (np.asarray(cmark, float) - origin)
    rm_local = frame.T @ (np.asarray(rmark, float) - origin)
    true_r = float(np.linalg.norm((rm_local - cm_local)[:2]))

    # five border clicks: nearest scan-surface points to the true circle at spread
    # angles, each aim jittered like a real click
    rng = np.random.default_rng(11)
    rim_clicks = []
    for a in np.linspace(0, 2 * np.pi, 5, endpoint=False):
        aim = cm_local[:2] + (true_r + rng.normal(0, 0.3)) * np.array([np.cos(a),
                                                                       np.sin(a)])
        d = np.linalg.norm(L[:, :2] - aim, axis=1)
        near = np.where(d < 1.0)[0]
        if not len(near):
            continue
        hit = near[np.argmax(L[near, 2])]  # the raycast lands on the top surface
        rim_clicks.append(list(map(float, pts[hit])))
    if len(rim_clicks) < 3:
        pytest.skip("scan too sparse at the rim for a 5-click simulation")
    d_c = np.linalg.norm(L[:, :2] - (cm_local[:2] + [0.5, -0.4]), axis=1)
    centre_click = pts[np.where(d_c < 1.0)[0][np.argmax(L[np.where(d_c < 1.0)[0], 2])]]

    out = run_auto_case(case_id="mp", scan=scan,
                        library=CapLibrary.load(root / "library/caps" / model),
                        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
                        vendor=vendor_dir.parent.name,
                        confirmed=[ConfirmedSite(tooth, center, declared,
                                                 center_mark=list(map(float, centre_click)),
                                                 rim_points=rim_clicks)],
                        gingival_offset_mm=0.0,  # real vendor part — see module note
                        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None, row.get("error")
    assert row["seed_source"] == "marks"
    # the doctor-facing alignment number: mm of rim agreement, not coverage %
    # (a perfect seat on this data reads ~40% coverage — structurally misleading).
    # Presence only: it is anchored at the CLICKED circle, so on a partial-rim site
    # noisy clicks legitimately read high — that IS its message ("re-click the
    # border"); seat QUALITY is asserted against the curated truth below.
    assert row["rim_agreement_mm"] is not None, "rim agreement missing for marked site"
    # the cap-footprint surface % (the honest 'how much is covered' number)
    pct = row["cap_surface_explained_pct"]
    assert pct is not None and 0.0 <= pct <= 100.0, f"cap surface pct {pct}"
    violation = _seat_bounds_violation(
        scan, center, cmark, rmark,
        tmp_path / "out" / f"mp-{tooth}-implant.json",
        tmp_path / "out" / f"mp-{tooth}-healingcap-aligned.stl",
        f"{folder} t{tooth} multipoint")
    # A DEPTH violation is acceptable ONLY when the gate says so out loud: a noisy
    # simulated gesture on a tall deeply-ambiguous cap can land the ring band on the
    # part's flank a couple of mm up (zimmer t7, post-axis-fix), and the top-face
    # guidance then routes the doctor to re-click — the honest-attention contract,
    # same escape the class-stability check below/above has always had. Tilt and
    # band violations have no such excuse.
    if violation is not None and violation.get("kind") == "depth":
        assert row["guidance"]["level"] != "ready", \
            f"{violation['msg']} — and the gate presented READY"
    else:
        assert violation is None, violation and violation["msg"]


@pytest.mark.parametrize("folder,tooth,center,declared,cmark,rmark", _all_real_sites(),
                         ids=[f"{f.replace('doctor-','')}-t{t}"
                              for f, t, _, _, _, _ in _all_real_sites()])
@pytest.mark.slow
def test_every_real_site_seats_within_bounds(tmp_path, folder, tooth, center, declared,
                                             cmark, rmark):
    """Loop guard (2026-07-12): EVERY curated real site must seat sanely — signed tilt
    within the plausible cone, and (when the rim seat ran) the visible rim band close to
    the posed template. New doctor scans extend this guard automatically via sites.json."""
    from scipy.spatial import cKDTree

    from case_prep.pipeline.auto_flow import _crowns_frame

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    model = next(m for m in ["neodent-gm", "zimmer-4.5"] if m in folder)
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    out = run_auto_case(case_id="sg2", scan=scan,
                        library=CapLibrary.load(root / "library/caps" / model),
                        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
                        vendor=vendor_dir.parent.name,
                        confirmed=[ConfirmedSite(tooth, center, declared,
                                                 center_mark=cmark, rim_mark=rmark)],
                        gingival_offset_mm=0.0,  # real vendor part — see module note
                        jaw_label="upper", out_dir=tmp_path / "out")
    _assert_seat_within_bounds(scan, center, cmark, rmark,
                               tmp_path / "out" / f"sg2-{tooth}-implant.json",
                               tmp_path / "out" / f"sg2-{tooth}-healingcap-aligned.stl",
                               f"{folder} t{tooth}")


def _assert_seat_within_bounds(scan, center, cmark, rmark, rec_path, tmpl_path, label):
    v = _seat_bounds_violation(scan, center, cmark, rmark, rec_path, tmpl_path, label)
    assert v is None, v and v["msg"]


def _seat_bounds_violation(scan, center, cmark, rmark, rec_path, tmpl_path, label):
    """The PHYSICAL seat bounds shared by the curated-marks and re-click guards: signed
    tilt inside the plausible cone, the scan's visible rim band (located by the
    CURATED marks — the physical cap does not move) close to the posed template, and
    the posed part's TOP FACE on the scan (the DEPTH bound — the band and tilt are
    both geometrically blind to a slide along a straight-walled part's own axis: the
    wall passes through the band at any height. Client screenshot 2026-07-15: a 6030
    seated ~2mm HIGH read band p90 1.22/tilt 9.6 — inside every old bound — while its
    top face floated 1.96mm off the scan and the part looked '90 deg rotated').
    Returns a violation description, or None when the seat is inside bounds."""
    from scipy.spatial import cKDTree

    from case_prep.pipeline.auto_flow import _crowns_frame

    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    rec = json.loads(Path(rec_path).read_text())
    up = frame @ np.array([0.0, 0.0, 1.0])
    tilt = np.degrees(np.arccos(np.clip(np.asarray(rec["axis"], float) @ up, -1.0, 1.0)))
    if tilt >= 46.0:
        return {"msg": f"{label}: signed tilt {tilt:.0f} deg", "p90": None,
                "kind": "tilt"}
    # seat quality is checked for EVERY method — icp seats must not hide
    tmpl = trimesh.load(tmpl_path, force="mesh")
    # DEPTH bound: the top face is the cap's always-visible surface (it is what the
    # doctor marks), so a correct seat puts it ON the scan for every submergence level
    # (measured healthy fleet: p90 0.31-0.89; the two axial-slide failures: 2.38/2.94)
    tv = np.asarray(tmpl.vertices, float)
    h = (tv - np.asarray(rec["position"], float)) @ np.asarray(rec["axis"], float)
    top_p90 = float(np.percentile(
        cKDTree(pts).query(tv[h > h.max() - 1.2])[0], 90))
    # (zimmer t7 briefly carried a relaxed bar here as a "known outlier" — its
    # band-vs-top-face conflict turned out to be the 27-degree-TILTED 7030 template
    # from the old canonicalization, not the site; with the axis fix it reads 0.60
    # and the uniform bound applies everywhere.)
    if top_p90 >= 1.5:
        return {"msg": f"{label}: top-face p90 {top_p90:.2f}mm — the part rides off "
                       "the scan along its own axis", "p90": top_p90,
                "kind": "depth"}
    L = (pts - origin) @ frame
    site = frame.T @ (np.asarray(center, float) - origin)
    # the band must sit at THIS cap's rim: radius from the curated marks (a fixed
    # 1.0-2.5mm band measured the dome on Ø7 caps and let offset seats pass)
    if cmark and rmark:
        rim_r = float(np.linalg.norm(
            (frame.T @ (np.asarray(rmark, float) - origin)
             - frame.T @ (np.asarray(cmark, float) - origin))[:2]))
    else:
        rim_r = 2.3
    d_xy = np.linalg.norm(L[:, :2] - site[:2], axis=1)
    near = L[d_xy < rim_r + 0.3]
    rim_z = np.percentile(near[:, 2], 80)
    # TILT-FAIR band: a flat crowns-frame slice clips a tilted cap's ring and grabs
    # gingiva on the low side (a correct 27-deg seat read p90 1.54). Take a wide
    # slab, then inlier-refine to the ring's own plane — the same trick the seat uses.
    band_local = L[(d_xy > max(0.8, rim_r - 0.8)) & (d_xy < rim_r + 0.4)
                   & (np.abs(L[:, 2] - rim_z) < 2.5)]
    c0 = band_local.mean(axis=0)
    for _ in range(3):
        _, _, vt = np.linalg.svd(band_local - c0, full_matrices=False)
        keep = np.abs((band_local - c0) @ vt[2]) < 0.6
        if keep.all() or keep.sum() < 40:
            break
        band_local = band_local[keep]
        c0 = band_local.mean(axis=0)
    ann = band_local @ frame.T + origin
    p90 = float(np.percentile(
        cKDTree(np.asarray(tmpl.vertices, float)).query(ann)[0], 90))
    # bar 1.6: deeply SUBMERGED caps have a geometric floor ~1.5 — the scan's
    # visible ring meets the part's FLANK, not its rim (t13: visible rim 2.36 vs
    # part rim 2.73, correct seat reads 1.47). Genuinely bad seats read >= 2.
    if p90 >= 1.6:
        return {"msg": f"{label}: rim-band p90 {p90:.2f}mm", "p90": p90,
                "kind": "band"}
    return None


class TestRimSeatGates:
    """The rim seat must REFUSE rather than ship a confident-looking bad pose (sweep
    finding, 2026-07-12): tilted rim plane -> refuse (fall through to bounded ICP);
    depth search railing at its boundary -> refuse; residual beyond calibration -> refuse."""

    def _ring_patch(self, tilt_deg=0.0, n=600, r=3.0):
        rng = np.random.default_rng(5)
        ang = rng.uniform(0, 2 * np.pi, n)
        pts = np.c_[r * np.cos(ang), r * np.sin(ang), rng.normal(0, 0.05, n)]
        pts = np.vstack([pts, np.c_[rng.uniform(-2, 2, n), rng.uniform(-2, 2, n),
                                    rng.normal(1.0, 0.1, n)]])  # dome fill
        if tilt_deg:
            R = trimesh.transformations.rotation_matrix(
                np.radians(tilt_deg), [1, 0, 0])[:3, :3]
            pts = pts @ R.T
        return pts

    def _template(self):
        return trimesh.creation.cylinder(radius=3.0, height=3.5, sections=32)

    def test_level_ring_seats(self):
        from case_prep.pipeline.auto_flow import _rim_seat

        np.random.seed(0)
        out = _rim_seat(self._ring_patch(), np.zeros(2), 3.0, self._template())
        assert out is not None

    def test_tilted_rim_plane_refuses(self):
        from case_prep.pipeline.auto_flow import _rim_seat

        np.random.seed(0)
        out = _rim_seat(self._ring_patch(tilt_deg=60.0), np.zeros(2), 3.0, self._template())
        assert out is None, "a 60-degree rim plane is outside the seating cone"

    def test_bad_residual_refuses(self):
        from case_prep.pipeline.auto_flow import _rim_seat

        np.random.seed(0)
        rng = np.random.default_rng(9)
        blob = rng.uniform(-4, 4, (900, 3))  # ring band exists radially but no cap shape
        ang = rng.uniform(0, 2 * np.pi, 400)
        blob = np.vstack([blob, np.c_[3.0 * np.cos(ang), 3.0 * np.sin(ang),
                                      rng.uniform(-3, 3, 400)]])
        out = _rim_seat(blob, np.zeros(2), 3.0, self._template())
        # the returned value is the CALIBRATED score (seat + 2x visible-coverage): a
        # garbage patch must either be refused or carry a visibly bad score — it must
        # never look like a real seat (real seats read ~0.9-1.5 on this scale)
        assert out is None or out[1] > 1.2, "a garbage patch scored like a real seat"


@pytest.mark.slow
def test_center_and_rim_marks_drive_a_rim_seat(tmp_path):
    """Client spec (2026-07-12): two precise marks — cap CENTER + WIDE-END (rim edge) —
    hand the rim seat its center and radius directly (RealGUIDE registration-point
    style). With human-vouched geometry the seat must go rim-first, not ICP."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    truth = np.asarray(gt.poses[0].position, float)
    gt_axis = np.asarray(gt.poses[0].axis, float)
    # the human's marks: the cap centre, and a point on the widest rim (radius 4.0)
    t0 = np.cross(gt_axis, [0.0, 0.0, 1.0]); t0 /= np.linalg.norm(t0)
    rim_point = truth + t0 * 4.0 + gt_axis * (3.5 / 2.0)

    out = run_auto_case(case_id="marks", scan=scan,
                        library=CapLibrary.single(CapSpec("acme", "8020"), cap),
                        construction_mesh=make_scan_body_mesh(), vendor="dess",
                        gingival_offset_mm=0.0,  # stand-in body — see module note
                        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, truth)),
                                                 center_mark=list(map(float, truth)),
                                                 rim_mark=list(map(float, rim_point)))],
                        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row["seed_source"] == "marks"
    assert row["seat_method"] == "rim", "human-vouched centre+radius must seat rim-first"
    rec = json.loads((tmp_path / "out" / "marks-8-implant.json").read_text())
    tilt = np.degrees(np.arccos(np.clip(
        np.asarray(rec["axis"], float) @ gt_axis, -1.0, 1.0)))
    assert tilt < 25.0


@pytest.mark.slow
def test_rim_points_pin_the_seat_to_the_border_circle(tmp_path):
    """Client spec (2026-07-14 screenshots: 'width needs to match and depth needs to
    match'): the border clicks define the cap's visible ring COMPLETELY — centre,
    radius, plane, depth. The seat must PIN the template's matching ring onto that
    circle, so the clicked border lies ON the posed template by construction (no
    depth search, no band selection left to drift)."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    truth = np.asarray(gt.poses[0].position, float)
    gt_axis = np.asarray(gt.poses[0].axis, float)

    # five border clicks around the cap's TOP EDGE (radius 4.0 at the top face), each
    # with realistic click error
    t0 = np.cross(gt_axis, [0.0, 0.0, 1.0])
    t0 /= np.linalg.norm(t0)
    t1 = np.cross(gt_axis, t0)
    rng = np.random.default_rng(7)
    border = [truth + (4.0 + rng.normal(0, 0.15)) * (np.cos(a) * t0 + np.sin(a) * t1)
              + gt_axis * (3.5 / 2.0)
              for a in np.linspace(0, 2 * np.pi, 5, endpoint=False)]

    out = run_auto_case(case_id="pin", scan=scan,
                        library=CapLibrary.single(CapSpec("acme", "8020"), cap),
                        construction_mesh=make_scan_body_mesh(), vendor="dess",
                        gingival_offset_mm=0.0,  # stand-in body — see module note
                        confirmed=[ConfirmedSite(tooth=8, center=tuple(map(float, truth)),
                                                 center_mark=list(map(float, truth)),
                                                 rim_points=[list(map(float, p))
                                                             for p in border])],
                        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None, row.get("error")
    assert row["seat_method"] == "rim"
    rec = json.loads((tmp_path / "out" / "pin-8-implant.json").read_text())
    axis = np.asarray(rec["axis"], float)
    tilt = np.degrees(np.arccos(np.clip(float(axis @ gt_axis), -1.0, 1.0)))
    assert tilt < 8.0, f"pinned seat tilted {tilt:.0f} deg off the border plane"
    pos_err = float(np.linalg.norm(np.asarray(rec["position"], float) - truth))
    assert pos_err < 0.8, f"pinned seat centre {pos_err:.2f}mm off truth"
    # THE CONTRACT: the doctor's clicked border lies ON the posed template — width and
    # depth match by construction
    tmpl = trimesh.load(tmp_path / "out" / "pin-8-healingcap-aligned.stl", force="mesh")
    from scipy.spatial import cKDTree
    d = cKDTree(np.asarray(tmpl.vertices, float)).query(np.asarray(border, float))[0]
    assert float(d.max()) < 0.6, \
        f"clicked border sits {d.max():.2f}mm off the posed template"


@pytest.mark.parametrize("folder", ["doctor-cap7030-zimmer-4.5",
                                    "doctor-cap6030-neodent-gm"],
                         ids=["cap7030", "cap6030"])
@pytest.mark.slow
def test_coded_face_clocking_is_recovered(tmp_path, folder):
    """The NEW library caps carry CODED FACES (client screenshots 2026-07-14: a
    well-positioned seat LOOKED sideways because the coded cutout landed at an
    arbitrary rotation — measured on cap7030: top-face p90 1.39mm shipped vs 0.82mm
    at the right clocking). For an asymmetric cap the seat must also recover the
    rotation about its own axis. Real labeled arches are the guard — a synthetic
    fin surrogate defeated the revolute-axis canonicalization (known surrogate
    limitation in this project)."""
    from scipy.spatial import cKDTree

    root = Path(__file__).parents[1] / "data/real"
    if not (root / "scans" / folder).exists():
        pytest.skip("labeled arch not present")
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    model = next(m for m in ["neodent-gm", "zimmer-4.5"] if m in folder)
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    s = json.loads((root / "scans" / folder / "sites.json").read_text(
        ))["suggested_sites"][0]
    out = run_auto_case(case_id="clk", scan=scan,
                        library=CapLibrary.load(root / "library/caps" / model),
                        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
                        vendor=vendor_dir.parent.name,
                        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]),
                                                 s.get("declared_variant"),
                                                 center_mark=s.get("center_mark"),
                                                 rim_mark=s.get("rim_mark"))],
                        gingival_offset_mm=0.0,  # real vendor part — see module note
                        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None and row["seat_method"] == "rim"
    rec = json.loads((tmp_path / "out" / f"clk-{s['tooth']}-implant.json").read_text())
    tmpl = trimesh.load(tmp_path / "out" / f"clk-{s['tooth']}-healingcap-aligned.stl",
                        force="mesh")
    tv = np.asarray(tmpl.vertices, float)
    axis_w = np.asarray(rec["axis"], float)
    pos_w = np.asarray(rec["position"], float)
    axial = (tv - pos_w) @ axis_w
    top_w = tv[axial > axial.max() - 1.2]  # the coded face
    pts = np.asarray(scan.vertices, float)
    scan_tree = cKDTree(pts)
    good = float(np.percentile(scan_tree.query(top_w)[0], 90))
    # DISCRIMINATION: the shipped clocking must clearly beat a deliberate 90-degree
    # rotation of the same seat (pre-fix, shipped was as bad as any rotation)
    rot90 = trimesh.transformations.rotation_matrix(np.pi / 2.0, axis_w, pos_w)
    top_rot = top_w @ rot90[:3, :3].T + rot90[:3, 3]
    bad = float(np.percentile(scan_tree.query(top_rot)[0], 90))
    assert good < bad, \
        f"{folder}: shipped clocking {good:.2f} not better than rotated {bad:.2f}"
    if folder == "doctor-cap7030-zimmer-4.5":
        # the measured mis-clock case: pre-fix shipped 1.39; the optimum reads ~0.82
        assert good < 1.0, f"cap7030 coded face p90 {good:.2f} — still mis-clocked"


class TestBorderOutlierRejection:
    """Client run-report (2026-07-14, cap6030): one of four border clicks landed
    1.3mm below the rim edge (on the slope) — the fitted plane tilted 13 degrees to
    pass through it and the pinned seat followed. With >=4 points the fit must
    detect and drop such an outlier (leave-one-out): the doctor's gesture becomes
    self-healing instead of silently tilted."""

    def test_the_users_exact_points_get_the_outlier_dropped(self):
        """Real-data arbitration: geometry alone cannot pick the outlier at n=4 —
        the SCAN decides (the true rim circle hugs the scan surface)."""
        from scipy.spatial import cKDTree

        from case_prep.pipeline.auto_flow import _crowns_frame, _fit_circle_3d

        root = Path(__file__).parents[1] / "data/real/scans/doctor-cap6030-neodent-gm"
        if not root.exists():
            pytest.skip("labeled arch not present")
        scan = trimesh.load(next(root.glob("*.stl")), force="mesh")
        pts = np.asarray(scan.vertices, float)
        frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
        L = (pts - origin) @ frame
        # the exact four border clicks from the client's run report (world coords)
        P_world = np.array([[14.0, 16.4, 21.3], [10.3, 14.8, 21.2],
                            [12.3, 12.7, 21.2], [15.7, 13.8, 19.9]])
        P = (P_world - origin) @ frame
        out = _fit_circle_3d(P, scan_tree=cKDTree(L))
        assert out is not None and len(out) == 2, \
            "the suspected-outlier alternate circle must be offered"
        tilts = sorted(float(np.degrees(np.arccos(min(1.0, abs(c[1][2])))))
                       for c in out)
        assert tilts[0] < 8.0, \
            f"no level candidate among the circles (tilts {tilts})"

    @pytest.mark.slow
    def test_the_users_exact_run_seats_within_bounds(self, tmp_path):
        """End to end: the client's exact centre + 4 border clicks (one off the edge)
        must produce a seat inside the physical bounds — the seat score chooses
        between the outlier-dropped and full circles."""
        root = Path(__file__).parents[1] / "data/real"
        folder = "doctor-cap6030-neodent-gm"
        if not (root / "scans" / folder).exists():
            pytest.skip("labeled arch not present")
        scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
        vendor_dir = next((root / "library/construction").glob(
            "*/neodent-gm-scanbody.stl"))
        s = json.loads((root / "scans" / folder / "sites.json").read_text(
            ))["suggested_sites"][0]
        out = run_auto_case(
            case_id="usr", scan=scan,
            library=CapLibrary.load(root / "library/caps/neodent-gm"),
            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
            vendor=vendor_dir.parent.name,
            confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]),
                                     s.get("declared_variant"),
                                     center_mark=[13.1, 14.2, 21.3],
                                     rim_points=[[14.0, 16.4, 21.3],
                                                 [10.3, 14.8, 21.2],
                                                 [12.3, 12.7, 21.2],
                                                 [15.7, 13.8, 19.9]])],
            gingival_offset_mm=0.0,  # real vendor part — see module note
            jaw_label="upper", out_dir=tmp_path / "out")
        row = out["sites"][0]
        assert row.get("error") is None
        _assert_seat_within_bounds(
            scan, s["center"], s.get("center_mark"), s.get("rim_mark"),
            tmp_path / "out" / f"usr-{s['tooth']}-implant.json",
            tmp_path / "out" / f"usr-{s['tooth']}-healingcap-aligned.stl",
            f"{folder} users-exact-run")

    @pytest.mark.slow
    def test_a_sub_rms_outlier_still_offers_the_alternate(self):
        """Client run-report round 2 (276794487-zimmer redo, 2026-07-14): one of four
        border clicks sat 0.89mm above the others' plane, but at n=4 the LSQ plane
        SPLITS a single outlier's error across all points — full-fit rms read 0.206
        and stayed UNDER the 0.25 gate, so the alternate circle was never generated
        and the seat shipped 12deg tilted (rim seat 0.64 -> 1.08 across the redo).
        The trigger must consider the leave-one-out disagreement (the signal that
        actually measures ONE click disagreeing), not only the whole-plane rms."""
        from scipy.spatial import cKDTree

        from case_prep.pipeline.auto_flow import _crowns_frame, _fit_circle_3d

        root = Path(__file__).parents[1] / "data/real/scans/doctor-276794487-zimmer-4.5"
        if not root.exists():
            pytest.skip("real arch not present")
        scan = trimesh.load(next(root.glob("*.stl")), force="mesh")
        pts = np.asarray(scan.vertices, float)
        frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
        L = (pts - origin) @ frame
        # the exact four border clicks from the client's pasted run report (world coords)
        P_world = np.array([[24.008, 13.450, 21.204], [23.455, 9.159, 21.322],
                            [26.227, 11.269, 22.201], [21.296, 11.744, 21.161]])
        P = (P_world - origin) @ frame
        out = _fit_circle_3d(P, scan_tree=cKDTree(L))
        assert out is not None and len(out) == 2, \
            "a 0.89mm leave-one-out outlier must offer the alternate circle"
        tilts = sorted(float(np.degrees(np.arccos(min(1.0, abs(c[1][2])))))
                       for c in out)
        assert tilts[0] < tilts[1] - 3.0, \
            f"the alternate should be meaningfully flatter (tilts {tilts})"

    @pytest.mark.slow
    def test_the_zimmer_redo_run_ships_the_less_tilted_seat(self, tmp_path):
        """End to end on the client's exact redo gesture (run-history 22:34): the pin
        contract + calibrated seat score must now arbitrate between both circles and
        ship the better seat (measured: rim agreement 1.08 tilted -> ~0.75 level),
        the row must carry the click-disagreement measurement, and the gate must not
        present READY while the doctor's own clicks disagree by ~0.9mm."""
        root = Path(__file__).parents[1] / "data/real"
        folder = "doctor-276794487-zimmer-4.5"
        if not (root / "scans" / folder).exists():
            pytest.skip("real arch not present")
        scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
        vendor_dir = next((root / "library/construction").glob(
            "*/zimmer-4.5-scanbody.stl"))
        s = json.loads((root / "scans" / folder / "sites.json").read_text(
            ))["suggested_sites"][0]
        out = run_auto_case(
            case_id="redo", scan=scan,
            library=CapLibrary.load(root / "library/caps/zimmer-4.5"),
            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
            vendor=vendor_dir.parent.name,
            confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), None,
                                     center_mark=[23.62, 11.37, 21.46],
                                     rim_points=[[24.008, 13.450, 21.204],
                                                 [23.455, 9.159, 21.322],
                                                 [26.227, 11.269, 22.201],
                                                 [21.296, 11.744, 21.161]])],
            gingival_offset_mm=0.0,  # real vendor part — see module note
            jaw_label="upper", out_dir=tmp_path / "out")
        row = out["sites"][0]
        assert row.get("error") is None
        # the SHIPPED POSE is the contract: the level alternate seats 11.5deg in the
        # crowns frame vs 16.1deg for the outlier-tilted circle (rim_agreement_mm is
        # NOT asserted tightly here — it is anchored at the all-clicks circle, which
        # includes the outlier, so it under-separates the two poses by design)
        from case_prep.pipeline.auto_flow import _crowns_frame
        rec = json.loads((tmp_path / "out" / f"redo-{s['tooth']}-implant.json"
                          ).read_text())
        pts = np.asarray(scan.vertices, float)
        frame, _, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
        up = frame @ np.array([0.0, 0.0, 1.0])
        tilt = float(np.degrees(np.arccos(np.clip(
            np.asarray(rec["axis"], float) @ up, -1.0, 1.0))))
        assert tilt <= 13.5, \
            f"shipped tilt {tilt:.1f} deg — the outlier circle won over the alternate"
        assert row["border_click_disagreement_mm"] == pytest.approx(0.89, abs=0.06)
        assert row["guidance"]["level"] != "ready", \
            "clicks disagreeing by ~0.9mm must not present READY"
        assert any("border click" in a.lower() for a in row["guidance"]["actions"])
        _assert_seat_within_bounds(
            scan, s["center"], s.get("center_mark"), s.get("rim_mark"),
            tmp_path / "out" / f"redo-{s['tooth']}-implant.json",
            tmp_path / "out" / f"redo-{s['tooth']}-healingcap-aligned.stl",
            f"{folder} zimmer-redo-run")

    def test_border_click_disagreement_is_measured(self):
        """The reporting helper: max leave-one-out plane distance at n>=4 (None below —
        three clicks always define their plane exactly). Values from the client's real
        runs: the good prefill gesture reads ~0.33, the bad redo ~0.89."""
        from case_prep.pipeline.auto_flow import _border_click_disagreement

        good = np.array([[23.847, 13.612, 21.219], [21.087, 11.670, 21.196],
                         [23.660, 9.423, 21.289], [26.014, 10.846, 21.581]])
        bad = np.array([[24.008, 13.450, 21.204], [23.455, 9.159, 21.322],
                        [26.227, 11.269, 22.201], [21.296, 11.744, 21.161]])
        assert _border_click_disagreement(good) == pytest.approx(0.33, abs=0.05)
        assert _border_click_disagreement(bad) == pytest.approx(0.89, abs=0.05)
        assert _border_click_disagreement(bad[:3]) is None

    def test_a_genuinely_tilted_but_coplanar_ring_is_respected(self):
        from case_prep.pipeline.auto_flow import _fit_circle_3d

        # a REAL tilted rim: 5 points perfectly on a 20-degree-tilted circle — no
        # outlier to drop; the tilt is signal, not noise
        ang = np.linspace(0, 2 * np.pi, 5, endpoint=False)
        ring = np.c_[2.5 * np.cos(ang), 2.5 * np.sin(ang), np.zeros(5)]
        R = trimesh.transformations.rotation_matrix(np.radians(20.0), [1, 0, 0])[:3, :3]
        P = ring @ R.T + np.array([10.0, 5.0, 20.0])
        out = _fit_circle_3d(P)
        assert out is not None and len(out) == 1, \
            "coplanar points must yield exactly the one true circle"
        _, n, r = out[0]
        tilt = float(np.degrees(np.arccos(min(1.0, abs(n[2])))))
        assert 14.0 < tilt < 26.0, f"legitimate 20-deg rim read {tilt:.0f} deg"
        assert abs(r - 2.5) < 0.2


@pytest.mark.slow
def test_the_cap6030_pair_run_seats_to_depth(tmp_path):
    """Client report + screenshot (2026-07-15): the labeled 6030 arch, seeded by the
    curated centre+rim PAIR, shipped a seat ~2mm HIGH — axis 9.6 deg (fine), band p90
    1.22 (fine), but the coded top face floated 1.96mm above the scanned cap, so the
    tall part with its cutout exposed read as '90 deg rotated / sideways'. The 1-D
    depth search's patch->template objective is blind on tall straight walls (the wall
    explains itself at any height; measured: its own minimum IS the bad pose, while
    the calibrated symmetric score bottoms 1.75-2mm lower at 1.71 vs 3.37). The
    winner-only depth polish must land the top face ON the scan without changing the
    identified variant."""
    root = Path(__file__).parents[1] / "data/real"
    folder = "doctor-cap6030-neodent-gm"
    if not (root / "scans" / folder).exists():
        pytest.skip("labeled arch not present")
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    vendor_dir = next((root / "library/construction").glob("*/neodent-gm-scanbody.stl"))
    s = json.loads((root / "scans" / folder / "sites.json").read_text())["suggested_sites"][0]
    out = run_auto_case(
        case_id="d6030", scan=scan,
        library=CapLibrary.load(root / "library/caps/neodent-gm"),
        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
        vendor=vendor_dir.parent.name,
        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), s.get("declared_variant"),
                                 center_mark=s.get("center_mark"),
                                 rim_mark=s.get("rim_mark"))],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="lower", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None
    assert row["variant"]["identified"] == "6030"  # ranking untouched by the polish
    # the honest depth read-out ships on the row and reads SEATED here (was 1.96)
    assert row["top_face_agreement_mm"] is not None and row["top_face_agreement_mm"] < 1.0
    assert not any("top" in a.lower() and "◐" in a for a in row["guidance"]["actions"])
    from scipy.spatial import cKDTree
    rec = json.loads((tmp_path / "out" / f"d6030-{s['tooth']}-implant.json").read_text())
    tmpl = trimesh.load(tmp_path / "out" / f"d6030-{s['tooth']}-healingcap-aligned.stl",
                        force="mesh")
    tv = np.asarray(tmpl.vertices, float)
    h = (tv - np.asarray(rec["position"], float)) @ np.asarray(rec["axis"], float)
    top_p90 = float(np.percentile(
        cKDTree(np.asarray(scan.vertices, float)).query(tv[h > h.max() - 1.2])[0], 90))
    assert top_p90 < 1.0, \
        f"top face floats {top_p90:.2f}mm off the scan — the part rides high again"
    _assert_seat_within_bounds(
        scan, s["center"], s.get("center_mark"), s.get("rim_mark"),
        tmp_path / "out" / f"d6030-{s['tooth']}-implant.json",
        tmp_path / "out" / f"d6030-{s['tooth']}-healingcap-aligned.stl",
        f"{folder} pair-depth")


@pytest.mark.slow
def test_the_zimmer_t7_site_seats_to_depth_with_the_upright_template(tmp_path):
    """zimmer t7 spent two days on the books as 'the sloped-cap calibration outlier'
    (band-vs-top-face conflict, refinement refused, top face floating 2.45mm). The
    axis-canonicalization fix revealed the truth: the 7030 TEMPLATE was tilted 27
    degrees off its saved axis — the site was never sloped. With the upright template
    it must rim-seat with its top face ON the scan and present READY; this pins the
    recovery so the outlier can never quietly return."""
    root = Path(__file__).parents[1] / "data/real"
    folder = "doctor-zimmer-4.5"
    if not (root / "scans" / folder).exists():
        pytest.skip("real arch not present")
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    vendor_dir = next((root / "library/construction").glob("*/zimmer-4.5-scanbody.stl"))
    s = json.loads((root / "scans" / folder / "sites.json").read_text())["suggested_sites"][0]
    out = run_auto_case(
        case_id="zt7", scan=scan,
        library=CapLibrary.load(root / "library/caps/zimmer-4.5"),
        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
        vendor=vendor_dir.parent.name,
        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), s.get("declared_variant"),
                                 center_mark=s.get("center_mark"),
                                 rim_mark=s.get("rim_mark"))],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None
    assert row["seat_method"] == "rim"
    assert row["variant"]["identified"] == "7030"
    assert row["top_face_agreement_mm"] is not None and row["top_face_agreement_mm"] < 1.0
    _assert_seat_within_bounds(
        scan, s["center"], s.get("center_mark"), s.get("rim_mark"),
        tmp_path / "out" / f"zt7-{s['tooth']}-implant.json",
        tmp_path / "out" / f"zt7-{s['tooth']}-healingcap-aligned.stl",
        f"{folder} t7-upright-template")


class TestSeatConfidence:
    """Per-site pose-stability confidence (Spec A, 2026-07-15): the bootstrap re-seats the
    winner under click noise and grades the spread together with the fit residuals. It is
    OPT-IN (off keeps the battery fast) and ADVISORY (read-only, never changes the pose or
    variant). Guards: off by default, discriminates good vs sloppy gestures, deterministic."""

    _RANK = {"low": 0, "medium": 1, "high": 2}

    def _run(self, tmp_path, tag, center_mark, rim_mark, confidence):
        root = Path(__file__).parents[1] / "data/real"
        folder = "doctor-295811960-neodent-gm"
        if not (root / "scans" / folder).exists():
            pytest.skip("real arch not present")
        scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
        vendor_dir = next((root / "library/construction").glob("*/neodent-gm-scanbody.stl"))
        s = json.loads((root / "scans" / folder / "sites.json").read_text())["suggested_sites"][0]
        out = run_auto_case(
            case_id=tag, scan=scan,
            library=CapLibrary.load(root / "library/caps/neodent-gm"),
            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
            vendor=vendor_dir.parent.name,
            confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), "6020",
                                     center_mark=center_mark, rim_mark=rim_mark)],
            gingival_offset_mm=0.0,  # real vendor part — see module note
            jaw_label="lower", out_dir=tmp_path / tag, compute_confidence=confidence)
        return out["sites"][0], s

    def _curated(self, tmp_path):
        root = Path(__file__).parents[1] / "data/real"
        if not (root / "scans/doctor-295811960-neodent-gm/sites.json").exists():
            pytest.skip("real arch not present")
        s = json.loads((root / "scans/doctor-295811960-neodent-gm/sites.json"
                        ).read_text())["suggested_sites"][0]
        return s.get("center_mark"), s.get("rim_mark")

    @pytest.mark.slow
    def test_confidence_is_off_by_default(self, tmp_path):
        cm, rm = self._curated(tmp_path)
        row, _ = self._run(tmp_path, "off", cm, rm, confidence=False)
        assert row["confidence"] is None, "confidence must be opt-in (off keeps the battery fast)"

    @pytest.mark.slow
    def test_good_gesture_outgrades_a_sloppy_one(self, tmp_path):
        cm, rm = self._curated(tmp_path)
        good, _ = self._run(tmp_path, "good", cm, rm, confidence=True)
        # a sloppy operator: shove both marks 1.2mm off in the occlusal plane
        cm2 = [cm[0] + 1.2, cm[1] - 0.6, cm[2]]
        rm2 = [rm[0] - 0.6, rm[1] + 1.2, rm[2]]
        sloppy, _ = self._run(tmp_path, "sloppy", cm2, rm2, confidence=True)
        assert good["confidence"] is not None and sloppy["confidence"] is not None
        assert self._RANK[good["confidence"]["grade"]] >= self._RANK[sloppy["confidence"]["grade"]], \
            (f"curated {good['confidence']} did not out-grade sloppy {sloppy['confidence']}")
        # the raw stability number must also move the right way
        assert (sloppy["confidence"]["pose_pos_spread_mm"]
                >= good["confidence"]["pose_pos_spread_mm"] - 0.05)

    @pytest.mark.slow
    def test_confidence_is_deterministic_across_ambient_rng(self, tmp_path):
        cm, rm = self._curated(tmp_path)
        np.random.seed(123)
        a, _ = self._run(tmp_path, "det-a", cm, rm, confidence=True)
        np.random.seed(456)
        b, _ = self._run(tmp_path, "det-b", cm, rm, confidence=True)
        assert a["confidence"] == b["confidence"], \
            "per-tooth local RNG must make confidence independent of the ambient seed"


class TestVoidClocking:
    """Screw-recess VOID clocking (client report 2026-07-18: "screw channels are not being
    considered and rotated properly ... the actual center is never really centered"). The
    scanned recess dip is richly detectable (measured fleet: 547-8356 void points,
    0.76-3.5mm deep), and an ECCENTRIC bore's landing point is a function of clocking.

    LOOP-TRUTH RETIREMENT (2026-07-23): the "bores sit 0.43-0.76mm off the axis" premise
    was the poisoned centroid estimator's own artifact. Read from the CAD boundary loops
    (domain/channel.py), every real catalog bore is nearly CONCENTRIC with the rim ring
    (|bore - ring| 0.02-0.11mm, below the pass's 0.15mm lever floor), so on today's
    catalog the pass refuses everywhere — covered by
    test_catalog_bores_are_ring_concentric_so_the_pass_refuses. The kinematics tests
    below PIN a genuinely eccentric bore (the part class the pass stays alive for) onto
    the real 6020 geometry, so the ring-fixed mechanics, incumbent gate, stability
    refusal and no-recess fallback keep their coverage."""

    @staticmethod
    def _pin_eccentric_bore(monkeypatch, tmpl):
        """Pin _template_bore_centre to a bore 0.6mm off the REAL 6020 rim-ring centre
        (at the real mouth height): a hypothetical eccentric-channel part carried by
        real band/ring geometry — the tilt fixtures need the real z-asymmetric band."""
        import case_prep.pipeline.auto_flow as af

        ring3 = af._ring_centre_3d(tmpl)
        mouth_z = float(af._template_bore_centre(tmpl)[2])
        bore = np.array([float(ring3[0]) + 0.6, float(ring3[1]), mouth_z])
        monkeypatch.setattr(af, "_template_bore_centre", lambda t: bore.copy())
        return bore, ring3

    def test_catalog_bores_are_ring_concentric_so_the_pass_refuses(self):
        """The 2026-07-23 re-read, as a contract: with the loop-truth bore the real
        6020 lever is 0.073mm (< the 0.15mm floor; centroid-era read: 0.924mm), so
        even a perfect deep dip AT the true bore yields no clocking information and
        the pass must refuse. If a future catalog part trips this premise, the
        retirement story in _recess_clocking's docstring needs revisiting."""
        from case_prep.pipeline.auto_flow import (_ring_centre_3d,
                                                  _template_bore_centre, _recess_clocking)

        tmpl = self._load_6020()
        bore = _template_bore_centre(tmpl)
        ring3 = _ring_centre_3d(tmpl)
        lever = float(np.linalg.norm((bore - ring3)[:2]))
        assert lever < 0.15, \
            (f"premise: loop-truth 6020 lever should be ~0.073mm, measured {lever:.3f} "
             f"— an eccentric part entered the catalog or the bore read regressed")
        scan_pts = self._surface_and_dip(tmpl, bore)
        assert _recess_clocking(scan_pts, tmpl, np.eye(3), np.zeros(3)) is None, \
            "a ring-concentric bore carries no clocking information — must refuse"

    def test_recovers_a_known_clocking_from_the_recess(self, monkeypatch):
        from case_prep.pipeline.auto_flow import _recess_clocking

        tmpl = self._load_6020()
        bore, ring3 = self._pin_eccentric_bore(monkeypatch, tmpl)
        assert bore is not None and ring3 is not None
        assert np.linalg.norm((bore - ring3)[:2]) > 0.25, \
            "the pinned bore is off the ring centre — the premise of void clocking"

        # the "scan" = the template surface at a KNOWN clocking, PLUS the deep channel dip
        # a real scanner records at the bore (the CAD models only a ~0.7mm counterbore,
        # but the measured real-scan voids run 0.8-3.5mm deep — that dip is the signal
        # production gates are tuned to, so the fixture must carry it)
        np.random.seed(0)
        samp, _ = trimesh.sample.sample_surface(tmpl, 20000)
        pts = np.asarray(samp, float)
        rng = np.random.default_rng(0)
        ang = rng.uniform(0, 2 * np.pi, 400)
        rad = rng.uniform(0.0, 0.5, 400)
        depth = rng.uniform(0.5, 2.2, 400)
        dip = np.c_[bore[0] + rad * np.cos(ang), bore[1] + rad * np.sin(ang),
                    pts[:, 2].max() - depth]
        # clock the truth ABOUT THE RING AXIS — production reality: the seat/centering
        # passes have already landed the ring on the scanned rim, so the ring position
        # is KNOWN-GOOD and only the clocking about it is unresolved (ring-fixed
        # kinematics is exactly the production pass's rotation)
        phi_true = np.radians(117.0)
        c, s = np.cos(phi_true), np.sin(phi_true)
        rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        scan_pts = (np.vstack([pts, dip]) - ring3) @ rz.T + ring3

        # seed pose with WRONG (identity) clocking: void clocking must recover phi_true
        R0, T0 = np.eye(3), np.zeros(3)
        m1 = _recess_clocking(scan_pts, tmpl, R0, T0)
        assert m1 is not None, "a deep synthetic recess must be usable"
        bore_posed = (m1[:3, :3] @ bore + m1[:3, 3])[:2]
        bore_truth = (rz @ (bore - ring3) + ring3)[:2]
        assert np.linalg.norm(bore_posed - bore_truth) < 0.25, \
            "void clocking did not land the bore on the recess"
        from case_prep.pipeline.auto_flow import _posed_rim_centre
        ring_before = _posed_rim_centre(tmpl, np.eye(4))
        ring_after = _posed_rim_centre(tmpl, m1)
        assert np.linalg.norm(ring_after - ring_before) < 0.02, \
            ("ring-fixed clocking must hold the MEASURED rim centre (the quantity the "
             "centering pass drives and the rim guards measure) in place — the 0.2mm "
             "fixed-point leak this kinematics exists to prevent")

    @staticmethod
    def _load_6020():
        root = Path(__file__).parents[1] / "data/real/library/caps/zimmer-4.5"
        if not root.exists():
            pytest.skip("library not present")
        lib = CapLibrary.load(root)
        return lib.template(next(s for s in lib.specs if s.variant == "6020"))

    @staticmethod
    def _surface_and_dip(tmpl, bore):
        """Template surface sample + the deep recess dip a real scanner records at the
        bore (canonical frame; caller poses them)."""
        np.random.seed(0)
        samp, _ = trimesh.sample.sample_surface(tmpl, 20000)
        pts = np.asarray(samp, float)
        rng = np.random.default_rng(0)
        ang = rng.uniform(0, 2 * np.pi, 400)
        rad = rng.uniform(0.0, 0.5, 400)
        depth = rng.uniform(0.5, 2.2, 400)
        dip = np.c_[bore[0] + rad * np.cos(ang), bore[1] + rad * np.sin(ang),
                    pts[:, 2].max() - depth]
        return np.vstack([pts, dip])

    @staticmethod
    def _band_kasa(tmpl, R):
        """The measured rim centre of pose (R, 0) — same band definition as production."""
        v = np.asarray(tmpl.vertices, float)
        rmax = float(np.percentile(np.linalg.norm(v[:, :2], axis=1), 97))
        band = v[np.linalg.norm(v[:, :2], axis=1) > rmax - 0.4]
        uv = (band @ R.T)[:, :2]
        A = np.c_[2.0 * uv, np.ones(len(uv))]
        sol, *_ = np.linalg.lstsq(A, (uv ** 2).sum(axis=1), rcond=None)
        return sol[:2]

    def test_recovers_a_known_clocking_under_a_tilted_seat(self, monkeypatch):
        """The zero-tilt fixture is BLIND to a fixed-point-compensation regression (at
        identity pose, measured-Kasa and fixed-point compensation coincide by rotation
        equivariance — verified: the reverted bug passes it with ring_move 0.000). Under
        a tilted seat they diverge (the projected band Kasa drifts as the strip clocks);
        this fixture measured the regression at ring_move 0.031 (> 0.02 bar) while the
        shipped per-angle re-measure holds 0.003 (review 2026-07-20)."""
        from case_prep.pipeline.auto_flow import (_posed_rim_centre, _recess_clocking)

        tmpl = self._load_6020()
        bore, ring3 = self._pin_eccentric_bore(monkeypatch, tmpl)
        assert bore is not None and ring3 is not None
        t = np.radians(8.0)
        R0 = np.array([[1, 0, 0],
                       [0, np.cos(t), -np.sin(t)],
                       [0, np.sin(t), np.cos(t)]])
        # truth built by the production forward model itself (reachable by
        # construction): clock in the template frame, slide so the MEASURED rim
        # centre of the seed pose is preserved
        phi = np.radians(117.0)
        c, s = np.cos(phi), np.sin(phi)
        rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        R_true = R0 @ rz
        slide = self._band_kasa(tmpl, R0) - self._band_kasa(tmpl, R_true)
        cloud = self._surface_and_dip(tmpl, bore)
        scan_pts = cloud @ R_true.T
        scan_pts[:, :2] += slide

        m1 = _recess_clocking(scan_pts, tmpl, R0, np.zeros(3))
        assert m1 is not None, "a deep synthetic recess must be usable under tilt"
        bore_truth = (R_true @ bore)[:2] + slide
        bore_posed = (m1[:3, :3] @ bore + m1[:3, 3])[:2]
        assert np.linalg.norm(bore_posed - bore_truth) < 0.25, \
            "void clocking did not land the bore on the recess under a tilted seat"
        M0 = np.eye(4)
        M0[:3, :3] = R0
        ring_move = np.linalg.norm(_posed_rim_centre(tmpl, m1)
                                   - _posed_rim_centre(tmpl, M0))
        assert ring_move < 0.02, \
            (f"measured rim centre moved {ring_move:.3f}mm under a tilted clock — the "
             f"per-angle compensation regressed to a fixed-point stand-in")

    def test_keeps_the_incumbent_when_it_already_beats_the_sweep(self, monkeypatch):
        """INCUMBENT GATE (review 2026-07-20): the pass exists to REDUCE screw-hole
        error, never to trade it. With the recess already AT the current pose's bore,
        no rotation can improve on the incumbent, so the pass must refuse (measured
        motivating case: cap7030, incumbent 0.312 vs sweep-best 0.455)."""
        from case_prep.pipeline.auto_flow import _recess_clocking

        tmpl = self._load_6020()
        bore, _ = self._pin_eccentric_bore(monkeypatch, tmpl)
        scan_pts = self._surface_and_dip(tmpl, bore)  # dip at the CURRENT bore position
        assert _recess_clocking(scan_pts, tmpl, np.eye(3), np.zeros(3)) is None, \
            "the incumbent pose already lands the bore on the recess — must refuse"

    def test_refuses_when_the_ring_measure_goes_unstable(self, monkeypatch):
        """STABILITY REFUSAL (review 2026-07-20, previously zero direct coverage): when
        the measured compensation disagrees with the geometry-predicted ring swing by
        > 0.35mm — a heavily tilted band projection — the site cannot support
        ring-fixed clocking and the pass must refuse rather than slide the part
        sideways (t13 re-click shipped a 1.4-1.7mm 'compensation' before this guard)."""
        from case_prep.pipeline.auto_flow import _recess_clocking

        tmpl = self._load_6020()
        bore, ring3 = self._pin_eccentric_bore(monkeypatch, tmpl)
        t = np.radians(25.0)
        R0 = np.array([[1, 0, 0],
                       [0, np.cos(t), -np.sin(t)],
                       [0, np.sin(t), np.cos(t)]])
        # fixture premise: find a clock angle whose compensation-vs-prediction excess
        # trips the 0.35 bar (production math, production helpers)
        g0 = self._band_kasa(tmpl, R0)
        best_phi, best_excess = None, 0.0
        for phi in np.linspace(0.0, 2 * np.pi, 144, endpoint=False):
            c, s = np.cos(phi), np.sin(phi)
            rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
            corr = g0 - self._band_kasa(tmpl, R0 @ rz)
            pred = (R0 @ (rz @ ring3 - ring3))[:2]
            excess = float(np.linalg.norm(corr + pred))
            if excess > best_excess:
                best_phi, best_excess = phi, excess
        assert best_excess > 0.40, \
            f"fixture premise: 25deg tilt must produce a >0.40 excess (got {best_excess:.2f})"
        c, s = np.cos(best_phi), np.sin(best_phi)
        rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        R_true = R0 @ rz
        # top-face band + dip ONLY: at 25deg tilt the template's own cutout pockets
        # read as competing deep clusters and hijack the void search (a real
        # characteristic, but this test targets the refusal branch, so the void must
        # be unambiguous — same amputation as the no-recess fixture)
        cloud = self._surface_and_dip(tmpl, bore)
        top_z = np.asarray(tmpl.vertices, float)[:, 2].max()
        cloud = cloud[(cloud[:, 2] > top_z - 0.6) | (cloud[:, 2] < top_z - 1.0)]
        cloud = cloud[~((cloud[:, 2] < top_z - 1.0)
                        & (np.linalg.norm(cloud[:, :2] - bore[:2], axis=1) > 0.6))]
        scan_pts = cloud @ R_true.T
        scan_pts[:, :2] += g0 - self._band_kasa(tmpl, R_true)
        assert _recess_clocking(scan_pts, tmpl, R0, np.zeros(3)) is None, \
            "an unstable ring measure must refuse the clock, not slide the part"

    def test_no_recess_returns_none_for_fallback(self, monkeypatch):
        from case_prep.pipeline.auto_flow import _recess_clocking

        tmpl = self._load_6020()
        # pinned eccentric bore: without it the LEVER floor refuses first (real 6020
        # is ring-concentric since the loop-truth read) and this test would pass for
        # the wrong reason — it exists to cover the NO-RECESS branch
        self._pin_eccentric_bore(monkeypatch, tmpl)
        np.random.seed(0)
        samp, _ = trimesh.sample.sample_surface(tmpl, 20000)
        pts = np.asarray(samp, float)
        # amputate the dip: keep only points at/above the top-face level -> no void signal
        flat = pts[pts[:, 2] > pts[:, 2].max() - 0.6]
        assert _recess_clocking(flat, tmpl, np.eye(3), np.zeros(3)) is None, \
            "without a detectable recess the caller must fall back to the top-face sweep"


# (folder, model, tooth, flagged_ceiling): the ceiling bounds the bore-void offset on
# sites that pass via a FLAG rather than a verified rotation — so a regression can
# never hide behind an unrelated flag (review 2026-07-20). Since the coded-feature
# clock became primary (client report 2026-07-20 + e8 validation), the FIRST-CLASS
# pass condition is a code-verified rotation: the coded cutouts are what a lab tech
# judges, and the recess-void AZIMUTH was measured systematically biased (its clock
# had rotated away from the codes on 5 of 7 sites). Expected modes on this fleet:
# t3/t20/cap6030 codes-verified; cap7030 and t7 flagged rotation_unverified —
# cap7030's old recess-only anchor retired 2026-07-23 with the loop-truth bore
# (ring-concentric bores carry no recess-clocking information; codes still occluded).
#
# CEILINGS DELIBERATELY RE-RECORDED 2026-07-23 (G2, estimator un-poisoned): the bore
# end of the metric moved from the hole-repelled centroid (0.87-1.06mm wrong, ~174deg)
# to the CAD boundary-loop truth, so every ceiling was re-measured on a fresh run —
# old -> new (measured): t3 0.5 -> 0.8 (0.679); t20 0.75 -> 0.5 (0.397); cap6030
# 0.5 -> 1.1 (0.962); cap7030 0.5 -> 1.45 (1.313, was recess-anchored mode-2 before);
# t7 2.6 -> 1.6 (1.434 — the old 2.24 read was mostly estimator bias). The numbers
# are NOT comparable across the estimator change; they now measure the true channel
# mouth against the raw scanned dip (whose own scan-side azimuth bias the phantom
# still arbitrates).
_VOID_CLOCK_SITES = [
    ("doctor-276794487-zimmer-4.5", "zimmer-4.5", 3, 0.8),
    ("doctor-297589851-neodent-gm", "neodent-gm", 20, 0.5),
    ("doctor-cap6030-neodent-gm", "neodent-gm", 29, 1.1),
    ("doctor-cap7030-zimmer-4.5", "zimmer-4.5", 29, 1.45),
    ("doctor-zimmer-4.5", "zimmer-4.5", 7, 1.6),
]


@pytest.mark.parametrize("folder,model,tooth,ceiling", _VOID_CLOCK_SITES,
                         ids=[f.replace("doctor-", "")
                              for f, _, _, _ in _VOID_CLOCK_SITES])
@pytest.mark.slow
def test_shipped_bore_lands_on_the_scanned_void(tmp_path, folder, model, tooth, ceiling):
    """Fleet guard for the screw-channel complaint: every guard site ships either a
    CODE-VERIFIED rotation, or a bore on the scanned recess (<= 0.5mm), or an honest
    FLAG with the offset bounded by its measured per-site ceiling — deliver, or say so.
    Since 2026-07-23 the bore is the LOOP-TRUTH channel mouth (domain/channel.py), so
    the offset finally compares the real channel against the scanned dip: the old
    "optima 0.06-0.31mm / pre-fix 0.5-1.8mm" record was the poisoned centroid
    estimator measuring itself. The residual 0.4-1.4mm reads on this fleet are
    position error plus the dip centroid's own scan-side bias (phantom arbitrates) —
    exactly the C2 gap the G3 column and G1 boring fix take up next."""
    from case_prep.pipeline.auto_flow import _template_bore_centre

    root = Path(__file__).parents[1] / "data/real"
    if not (root / "scans" / folder).exists():
        pytest.skip("real arch not present")
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    lib = CapLibrary.load(root / "library/caps" / model)
    s = json.loads((root / "scans" / folder / "sites.json").read_text())["suggested_sites"][0]
    out = run_auto_case(
        case_id="vc", scan=scan, library=lib,
        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
        vendor=vendor_dir.parent.name,
        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), s.get("declared_variant"),
                                 center_mark=s.get("center_mark"),
                                 rim_mark=s.get("rim_mark"))],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="x", out_dir=tmp_path / "out", compute_confidence=True)
    row = out["sites"][0]
    assert row.get("error") is None
    from scipy.spatial import cKDTree
    from case_prep.pipeline.auto_flow import _crowns_frame

    rec = json.loads((tmp_path / "out" / f"vc-{tooth}-implant.json").read_text())
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    pose_w = np.array(rec["pose_matrix"], float)
    Rl = frame.T @ pose_w[:3, :3]
    Tl = frame.T @ (pose_w[:3, 3] - origin)
    tmpl = lib.template(next(sp for sp in lib.specs
                             if sp.variant == row["variant"]["identified"]))
    from case_prep.pipeline.auto_flow import _ring_centre_3d, _screw_recess_centre

    bore = _template_bore_centre(tmpl)
    assert bore is not None
    ring3 = _ring_centre_3d(tmpl)
    ring3 = ring3 if ring3 is not None else np.zeros(3)
    g0 = (Rl @ ring3 + Tl)[:2]
    tv = np.asarray(tmpl.vertices, float)
    top = tv[tv[:, 2] > tv[:, 2].max() - 1.0]
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
    # RAW dip read (no reachability): changed DELIBERATELY 2026-07-23 with the
    # loop-truth bore. The old read mirrored the production pass's ring-relative
    # reachability, but the true bores are ring-concentric (levers 0.02-0.11mm), so
    # that window shrank to ~0.9mm and the cap7030/t7 dips (1.34-1.46mm from the
    # ring) became honest production Nones — while THIS guard still needs the dip's
    # position to bound a flagged site's offset. The raw read is the same instrument,
    # minus the gate that no longer describes a live production convention.
    void_c = _screw_recess_centre(L, g0, rmax, expected_radius=None)
    assert void_c is not None, "these guard sites all have deep detectable voids"
    off = float(np.linalg.norm((Rl @ bore + Tl)[:2] - void_c))
    grade = (row.get("confidence") or {}).get("grade")
    # The contract is NO SILENT MISPLACEMENT, in priority order of instruments:
    # (1) the rotation is CODE-VERIFIED — the coded-cutout clock (the instrument a
    #     lab tech's eye uses; the only one that passed two-pose validation) read
    #     evidence and the shipped residual is <= 12 deg; or
    # (2) the bore lands on the recess (<= 0.5mm) — recess-anchored sites where the
    #     codes gave no evidence; or
    # (3) the site is FLAGGED (grade low / gate attention / rotation_unverified) AND
    #     the bore stays under its measured per-site ceiling, so a regression can
    #     never hide behind an unrelated flag.
    ck = row.get("clocking") or {}
    code_verified = (str(ck.get("evidence", "")).startswith("codes")
                     and ck.get("notch_shift_deg") is not None
                     and abs(ck["notch_shift_deg"]) <= 12.0
                     and not ck.get("rotation_unverified"))
    flagged = (grade == "low" or row["guidance"]["level"] == "attention"
               or bool(ck.get("rotation_unverified")))
    assert code_verified or off <= 0.5 or (flagged and off <= ceiling), \
        (f"{folder} t{tooth}: rotation not code-verified (clocking {ck}), bore sits "
         f"{off:.2f}mm from the scanned recess (ceiling {ceiling}, confidence "
         f"{grade!r}, gate {row['guidance']['level']!r})")


class TestDepthPolish:
    """Winner-only axial-depth polish (client report 2026-07-15, cap6030 riding ~2mm
    high): after ranking is decided, 1-D search along the winner's own axis over the
    CALIBRATED symmetric score, adopted only when both the score and the top-face
    agreement strictly improve — a correct seat (any submergence) is already at its
    top-face minimum, so it refuses and the seed stands."""

    def _tall_cap(self):
        cyl = trimesh.creation.cylinder(radius=3.0, height=5.5, sections=48)
        keep = cyl.triangles_center[:, 2] > -5.5 * 0.49
        cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
        cap.remove_unreferenced_vertices()
        return cap

    def _patch_at_truth(self, cap):
        np.random.seed(0)
        sampled, _ = trimesh.sample.sample_surface(cap, 4000)
        pts = np.asarray(sampled, float)
        # the scanner sees the top + upper wall only (a cap in a mouth, not floating)
        return pts[pts[:, 2] > -1.0]

    def test_pulls_a_high_seat_down_to_the_surface(self):
        from case_prep.pipeline.auto_flow import _refine_depth

        cap = self._tall_cap()
        patch = self._patch_at_truth(cap)
        m = np.eye(4)
        m[:3, 3] = np.array([0.0, 0.0, 2.0])  # riding 2mm high, the measured failure
        polished = _refine_depth(patch, cap, m)
        assert polished is not None, "a 2mm-high seat must be pulled down"
        assert abs(polished[:3, 3][2]) < 0.4, \
            f"depth polish landed at z={polished[:3, 3][2]:.2f}, truth is 0"

    def test_leaves_a_correct_seat_alone(self):
        from case_prep.pipeline.auto_flow import _refine_depth

        cap = self._tall_cap()
        patch = self._patch_at_truth(cap)
        polished = _refine_depth(patch, cap, np.eye(4))
        assert polished is None or abs(polished[:3, 3][2]) < 0.15, \
            "an already-correct seat must not be moved"


def _mark_scan_rim_centre(scan, cmark, rmark):
    """The GUARD's independent estimate of the scanned cap's rim centre: a Kasa fit of the
    scan's visible rim band about the curated CENTRE mark at the curated pair radius, in the
    crowns-local occlusal plane. Deliberately anchored on the marks (not the seat's internal
    seed) so it is an outside check on where the physical cap sits."""
    from case_prep.pipeline.auto_flow import _crowns_frame

    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    cm = frame.T @ (np.asarray(cmark, float) - origin)
    rm = frame.T @ (np.asarray(rmark, float) - origin)
    rim_r = float(np.linalg.norm((rm - cm)[:2]))
    d = np.linalg.norm(L[:, :2] - cm[:2], axis=1)
    band = L[np.abs(d - rim_r) < 0.6]
    band = band[band[:, 2] > np.percentile(band[:, 2], 50) - 1.0]
    uv = band[:, :2]
    A = np.c_[2 * uv, np.ones(len(uv))]
    sol, *_ = np.linalg.lstsq(A, (uv ** 2).sum(1), rcond=None)
    return frame, origin, sol[:2]


def _posed_rim_centre_local(scan, lib, rec):
    from case_prep.pipeline.auto_flow import _crowns_frame

    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    spec = next(s for s in lib.specs if s.variant == rec["variant_code"])
    tv = np.asarray(lib.template(spec).vertices, float)
    rmax = np.percentile(np.linalg.norm(tv[:, :2], axis=1), 97)
    ring = tv[np.linalg.norm(tv[:, :2], axis=1) > rmax - 0.4]
    pose = np.array(rec["pose_matrix"], float)
    ringl = ((ring @ pose[:3, :3].T + pose[:3, 3]) - origin) @ frame
    uv = ringl[:, :2]
    A = np.c_[2 * uv, np.ones(len(uv))]
    sol, *_ = np.linalg.lstsq(A, (uv ** 2).sum(1), rcond=None)
    return sol[:2]


# Full-clean-rim sites: the user's three reported off-centre sites plus the labeled arches.
# The rim is a complete visible ring here, so its centre is reliably measurable from the
# marks alone — exactly the sites where an off-centre seat is unambiguous. Partial/pocket-
# polluted sites (neodent t4/t13, zimmer t7 — where the seat's seed legitimately mean-shifts
# away from the mark) are covered by the rim-band + top-face bounds instead.
_CENTERED_SITES = [
    ("doctor-276794487-zimmer-4.5", "zimmer-4.5", 3),
    ("doctor-295811960-neodent-gm", "neodent-gm", 29),
    ("doctor-297589851-neodent-gm", "neodent-gm", 20),
    ("doctor-cap6020-neodent-gm", "neodent-gm", 29),
    ("doctor-cap6030-neodent-gm", "neodent-gm", 29),
    ("doctor-cap7020-zimmer-4.5", "zimmer-4.5", 3),
    ("doctor-cap7030-zimmer-4.5", "zimmer-4.5", 29),
]


@pytest.mark.parametrize("folder,model,tooth", _CENTERED_SITES,
                         ids=[f"{f.replace('doctor-','')}" for f, _, _ in _CENTERED_SITES])
@pytest.mark.slow
def test_seats_are_centered_on_the_scanned_rim(tmp_path, folder, model, tooth):
    """Client report (2026-07-15, three sites 'a bit off centre', all prefill marks, no
    manual): the posed cap's rim must sit ON the scanned cap's rim. ROOT CAUSE was that
    canonicalize_revolute centres a cap on its mesh CENTROID, 0.2-0.58mm off the true
    rotational axis for these coded caps, so the seat (origin -> scan rim centre) left the
    visible rim offset by that much (measured 0.29-0.51mm, matching the client's ordering).
    The winner-only centering pass must land the posed rim within a fifth of a millimetre of
    the scanned rim on every full-clean-rim site."""
    root = Path(__file__).parents[1] / "data/real"
    if not (root / "scans" / folder).exists():
        pytest.skip("real arch not present")
    scan = trimesh.load(next((root / "scans" / folder).glob("*.stl")), force="mesh")
    vendor_dir = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    s = json.loads((root / "scans" / folder / "sites.json").read_text())["suggested_sites"][0]
    lib = CapLibrary.load(root / "library/caps" / model)
    out = run_auto_case(
        case_id="ctr", scan=scan, library=lib,
        construction_mesh=trimesh.load(vendor_dir, force="mesh"),
        vendor=vendor_dir.parent.name,
        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]), s.get("declared_variant"),
                                 center_mark=s.get("center_mark"),
                                 rim_mark=s.get("rim_mark"))],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    assert row.get("error") is None
    rec = json.loads((tmp_path / "out" / f"ctr-{tooth}-implant.json").read_text())
    _, _, scan_c = _mark_scan_rim_centre(scan, s["center_mark"], s["rim_mark"])
    posed_c = _posed_rim_centre_local(scan, lib, rec)
    off = float(np.linalg.norm(posed_c - scan_c))
    assert off < 0.20, \
        f"{folder} t{tooth}: posed cap rim sits {off:.2f}mm off the scanned rim centre"


class TestBestFitRefinement:
    """The optimization stage (client ask 2026-07-14, industry pattern): after the
    coarse human-guided seat, a dense best-fit minimisation over the cap surface —
    bounded to a trust region and adopted only when it STRICTLY improves surface
    agreement, so the historical ICP failure (wandering to ridge-wall basins) is
    excluded by construction."""

    def _cap(self):
        cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
        keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
        cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
        cap.remove_unreferenced_vertices()
        v = np.asarray(cap.vertices, float).copy()
        top = v[:, 2] > 3.5 * 0.49
        v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
        return trimesh.Trimesh(v, cap.faces.copy(), process=False)

    def test_pulls_a_perturbed_seat_back_to_truth(self):
        from case_prep.pipeline.auto_flow import _refine_best_fit

        cap = self._cap()
        np.random.seed(0)
        truth = np.eye(4)
        truth[:3, 3] = [3.0, -2.0, 1.0]
        patch, _ = trimesh.sample.sample_surface(cap, 1500)
        patch = np.asarray(patch, float) @ truth[:3, :3].T + truth[:3, 3]
        patch += np.random.default_rng(2).normal(0, 0.03, patch.shape)
        # visible-shell patch only (a scan never sees the underside)
        patch = patch[patch[:, 2] > truth[2, 3] - 0.5]

        off = trimesh.transformations.rotation_matrix(np.radians(4.0), [1, 0, 0])
        off[:3, 3] = [0.5, -0.4, 0.3]
        m_init = off @ truth
        refined = _refine_best_fit(patch, cap, m_init)
        assert refined is not None, "a clear improvement inside the trust region must be adopted"
        err_before = float(np.linalg.norm(m_init[:3, 3] - truth[:3, 3]))
        err_after = float(np.linalg.norm(refined[:3, 3] - truth[:3, 3]))
        assert err_after < err_before * 0.5, \
            f"refinement barely moved: {err_before:.2f} -> {err_after:.2f}mm"

    def test_a_far_basin_is_refused(self):
        from case_prep.pipeline.auto_flow import _refine_best_fit

        cap = self._cap()
        np.random.seed(0)
        patch, _ = trimesh.sample.sample_surface(cap, 1500)
        patch = np.asarray(patch, float)
        m_init = np.eye(4)
        m_init[:3, 3] = [4.0, 0.0, 0.0]  # a 4mm-off start is a different basin,
        # not a refinement — the trust region must refuse whatever ICP finds
        reasons = []
        out = _refine_best_fit(patch, cap, m_init, on_reject=reasons.append)
        assert out is None
        # ...and the caller can tell WHY (review 2026-07-26): a trust-region exit
        # proved nothing about the seed being optimal, so the operator endpoint must
        # not report it as "already the best fit" — only "no-improvement" is a pass
        assert reasons == ["trust-region"]

    def test_an_already_tight_seat_is_left_alone(self):
        from case_prep.pipeline.auto_flow import _refine_best_fit

        cap = self._cap()
        np.random.seed(0)
        patch, _ = trimesh.sample.sample_surface(cap, 1500)
        patch = np.asarray(patch, float)
        reasons = []
        out = _refine_best_fit(patch, cap, np.eye(4), on_reject=reasons.append)
        # at the optimum there is no strict improvement to adopt
        assert out is None or float(np.linalg.norm(out[:3, 3])) < 0.15
        if out is None:
            # the None every operator sees at a tight dial IS the confirmation case
            # (review 2026-07-26): distinguishable from a trust-region exit by reason
            assert reasons == ["no-improvement"]


def _labeled_arches():
    root = Path(__file__).parents[1] / "data/real/scans"
    if not root.exists():
        return []
    out = []
    for folder in sorted(root.glob("doctor-cap*")):
        s = json.loads((folder / "sites.json").read_text())["suggested_sites"][0]
        out.append((folder.name, s))
    return out


@pytest.mark.parametrize("folder,site", _labeled_arches(),
                         ids=[f for f, _ in _labeled_arches()])
@pytest.mark.slow
def test_blind_identification_matches_the_label(tmp_path, folder, site):
    """GROUND-TRUTH guard (client-labeled arches, 2026-07-13): with the label hidden,
    auto identification must land on the doctor's declared cap. Two systematic biases
    once broke this (1/4): patch->template residual favours OVERSIZED templates, and
    hard visible-rim class restriction excluded deeply submerged true variants."""
    root = Path(__file__).parents[1] / "data/real"
    model = next(m for m in ["neodent-gm", "zimmer-4.5"] if m in folder)
    con = next((root / "library/construction").glob(f"*/{model}-scanbody.stl"))
    scan = trimesh.load(next((root / "scans" / folder).glob("*_jaw.stl")), force="mesh")
    out = run_auto_case(
        case_id="bl", scan=scan, library=CapLibrary.load(root / "library/caps" / model),
        construction_mesh=trimesh.load(con, force="mesh"), vendor=con.parent.name,
        confirmed=[ConfirmedSite(site["tooth"], tuple(site["center"]), None,
                                 center_mark=site["center_mark"],
                                 rim_mark=site["rim_mark"])],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="upper", out_dir=tmp_path / "out")
    row = out["sites"][0]
    identified = row["variant"]["identified"]
    truth = site["declared_variant"]
    # THE HONEST CONTRACT (measured on the client's labeled arches): the scan always
    # determines the DIAMETER class; the collar HEIGHT of a submerged cap is physically
    # invisible (a 30-cap shows a 20-cap's shell), so a height twin may rank first —
    # but then the gate must demand the doctor's declaration, never present as ready.
    # With the upright templates (axis-canonicalization fix, 2026-07-15) the same
    # escape extends to a DIAMETER-NEIGHBOUR TIE: on cap7020 the blind winner 8030
    # leads the true 7020 by 0.012 — inside the too-close rule's own margin — and the
    # gate demands the declaration. A wrong class that the scan genuinely cannot
    # separate must behave exactly like a height twin: candidate present at a
    # too-close margin AND never READY. (Restoring outright 4/4 class separation is
    # the score-recalibration follow-up.)
    if identified[:2] != truth[:2]:
        cands = row["variant"].get("candidates") or []
        by_variant = {c["variant"]: c["seat_residual_mm"] for c in cands}
        truth_class = [v for v in by_variant if v[:2] == truth[:2]]
        assert truth_class, \
            f"{folder}: no truth-class candidate at all (identified {identified})"
        best = min(by_variant.values())
        truth_best = min(by_variant[v] for v in truth_class)
        margin = max(0.05, 0.10 * best)
        assert truth_best - best <= margin, \
            (f"{folder}: class {identified[:2]} beat truth {truth[:2]} by "
             f"{truth_best - best:.3f} — beyond the too-close margin {margin:.3f}, "
             "a genuine mis-identification")
        assert row["guidance"]["level"] != "ready", \
            f"{folder}: ambiguous class {identified[:2]} vs {truth[:2]} presented READY"
    elif identified != truth:
        assert row["guidance"]["level"] != "ready", \
            f"{folder}: height twin {identified} for {truth} presented as READY"


@pytest.mark.slow
def test_center_mark_depth_is_ignored(tmp_path):
    """Client fix (2026-07-14): the centre mark identifies the cap's TOP CENTRE — the
    depth the raycast happened to hit (viewing angle, scanner position) must not matter.
    A mark displaced 8mm along z must yield the same seat as the true one."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    truth = np.asarray(gt.poses[0].position, float)

    poses, deltas = [], []
    for dz in (0.0, 8.0):
        out = run_auto_case(
            case_id=f"dz{int(dz)}", scan=scan,
            library=CapLibrary.single(CapSpec("acme", "8020"), cap),
            construction_mesh=make_scan_body_mesh(), vendor="dess",
            gingival_offset_mm=0.0,  # stand-in body — see module note
            confirmed=[ConfirmedSite(8, tuple(map(float, truth)),
                                     center_mark=[truth[0], truth[1], truth[2] + dz])],
            jaw_label="upper", out_dir=tmp_path / f"out{int(dz)}",
            proposals=[list(map(float, truth))])
        rec = json.loads((tmp_path / f"out{int(dz)}" / f"dz{int(dz)}-8-implant.json").read_text())
        poses.append(np.asarray(rec["pose_matrix"], float))
        deltas.append(out["sites"][0]["auto_delta_mm"])
    assert np.allclose(poses[0], poses[1], atol=1e-6), \
        "click depth changed the seat — marks must snap to the cap top"
    # the reported Δ-auto is measured from the SNAPPED seed, not the raw click — a
    # client-facing number must not re-import the depth the seat just ignored
    assert deltas[0] == deltas[1], "auto_delta_mm still reads the click depth"


@pytest.mark.slow
def test_center_mark_depth_is_ignored_on_sparse_scans(tmp_path):
    """Review 2026-07-14: fewer than 20 scan vertices within 5mm of the mark used to
    skip the depth snap entirely, silently keeping the raycast depth (and feeding it to
    the localize fallback's ±5mm axial window). The depth must be re-read from the
    nearest scan points however sparse the mesh — identical marks at different click
    depths must produce identical rows."""
    g = np.arange(-28.0, 28.1, 7.0)  # 7mm pitch: ~1 plane vertex within 5mm of the mark
    gx, gy = np.meshgrid(g, g)
    nv = len(g)
    pv = np.c_[gx.ravel(), gy.ravel(), np.zeros(nv * nv)]
    pf = [[r * nv + c, r * nv + c + 1, (r + 1) * nv + c + 1]
          for r in range(nv - 1) for c in range(nv - 1)]
    pf += [[r * nv + c, (r + 1) * nv + c + 1, (r + 1) * nv + c]
           for r in range(nv - 1) for c in range(nv - 1)]
    plane = trimesh.Trimesh(pv, np.asarray(pf), process=False)
    coarse_cap = trimesh.creation.cylinder(radius=4.0, height=4.0, sections=8)
    coarse_cap.apply_translation([0.0, 0.0, 2.0])
    scan = trimesh.util.concatenate([plane, coarse_cap])

    rows = []
    for dz in (0.0, 8.0):
        out = run_auto_case(
            case_id="sparse", scan=scan,
            library=CapLibrary.single(CapSpec("acme", "8020"),
                                      trimesh.creation.cylinder(radius=4.0, height=4.0,
                                                                sections=32)),
            construction_mesh=make_scan_body_mesh(), vendor="dess",
            gingival_offset_mm=0.0,  # stand-in body — see module note
            confirmed=[ConfirmedSite(8, (0.0, 0.0, 4.0),
                                     center_mark=[0.0, 0.0, 4.0 + dz])],
            jaw_label="upper", out_dir=tmp_path / f"sparse{int(dz)}")
        rows.append(json.dumps(out["sites"][0], sort_keys=True, default=str))
    assert rows[0] == rows[1], \
        "click depth changed the outcome on a sparse scan — snap must not need 20 points"


@pytest.mark.slow
def test_brush_patch_never_leaks_across_sites(tmp_path):
    """Review 2026-07-14 (HIGH): a site may carry BOTH a centre mark and brush dabs
    (the demo UI sends both). Its registration surface must come from ITS OWN
    marks/scan — never a previous site's painted patch (silent wrong-tooth deliverable)
    — and the mixed combination must not crash when no earlier site brushed."""
    from case_prep.adapters.ingest import canonicalize_revolute
    from case_prep.adapters.real_case import build_embedded_case

    cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
    keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
    cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
    cap.remove_unreferenced_vertices()
    v = np.asarray(cap.vertices, float).copy()
    top = v[:, 2] > 3.5 * 0.49
    v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
    cap = trimesh.Trimesh(v, cap.faces.copy(), process=False)

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    cap.export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1,
                             canonicalize=canonicalize_revolute)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    truth = np.asarray(gt.poses[0].position, float)

    pts = np.asarray(scan.vertices, float)
    dense = pts[(np.linalg.norm(pts[:, :2] - truth[:2], axis=1) < 6.0)
                & (pts[:, 2] > truth[2] - 2.0)]
    assert len(dense) >= 60, "fixture: brush patch must be dense"
    off_mark = truth + np.array([40.0, 40.0, 0.0])  # nowhere near any cap

    # site A brushes the real cap; site B carries a centre mark OFF the arch plus a few
    # dabs — the mixed-field site whose patch fallback used to read A's brush
    out = run_auto_case(
        case_id="leak", scan=scan,
        library=CapLibrary.single(CapSpec("acme", "7020"), cap),
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[
            ConfirmedSite(7, tuple(map(float, truth)),
                          marked_points=[list(map(float, p)) for p in dense]),
            ConfirmedSite(9, tuple(map(float, off_mark)),
                          center_mark=list(map(float, off_mark)),
                          marked_points=[list(map(float, off_mark))] * 5),
        ],
        jaw_label="upper", out_dir=tmp_path / "out")
    row_a, row_b = out["sites"]
    assert row_a.get("error") is None, "the brushed site must still seat"
    if row_b.get("error") is None:
        rec = json.loads((tmp_path / "out" / "leak-9-implant.json").read_text())
        d_from_a = float(np.linalg.norm(np.asarray(rec["position"], float) - truth))
        assert d_from_a > 5.0, \
            "site B was seated at site A's cap — stale brush patch leaked across sites"


@pytest.mark.slow
def test_honesty_wave_row_fields_present_on_every_aligned_site(tmp_path):
    """Panel-completion wave (master plan §8 item 12): every aligned row carries the
    surfaced/measured fields — candidates_too_close (slice 4, was guidance-only), the
    deviation scalars (shared with the QC map; render_qc=False exercises the
    stats-without-render path), rim_off_centre (None-honest without a centre+rim mark
    pair), and the delivered-channel G3 fields measured from the emitted product."""
    scan, lib, gt = _embedded_case(tmp_path, n=1)
    out = run_auto_case(
        case_id="hw", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[ConfirmedSite(tooth=8,
                                 center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=tmp_path / "out", render_qc=False)

    (row,) = out["sites"]
    assert row.get("error") is None
    assert isinstance(row["variant"]["candidates_too_close"], bool)
    # deviation scalars: same instrument as the deviation PNG, no PNG written
    assert row["deviation_rms_mm"] is not None
    assert row["deviation_p90_mm"] is not None
    assert 0.0 <= row["deviation_rms_mm"] <= row["deviation_p90_mm"] + 1e-9
    # no centre+rim mark pair on this site -> marks-anchored metric honestly withheld
    assert "rim_off_centre" in row and row["rim_off_centre"] is None
    # G3 fields exist on the row. Values are None-HONEST here: the r=1.0 bore
    # breaches the synthetic scan-body's thin wall, so the section outline is a
    # single C-shape and the as-built instrument refuses (measured: 1 loop/level) —
    # exactly its contract; the real-fleet test below asserts measured values
    for key in ("delivered_channel_vs_recess", "delivered_channel_vs_cap_channel",
                "delivered_channel_r_mm"):
        assert key in row


@pytest.mark.slow
def test_delivered_channel_offsets_reads_a_sound_bore():
    """The shared G3 instrument (auto_flow.delivered_channel_offsets — row and
    scoreboard both call it) reads the as-built radius on a part whose walls survive
    the bore, and withholds the vs-recess number when the scan shows nothing."""
    from case_prep.pipeline.auto_flow import delivered_channel_offsets
    from case_prep.pipeline.final_product import build_final_product

    body = trimesh.creation.cylinder(radius=4.0, height=8.0, sections=64)
    prod = build_final_product(body)  # canonical-axis bore, r=1.0
    out = delivered_channel_offsets(prod, np.eye(4), np.eye(3), np.zeros(3),
                                    np.zeros((10, 3)), make_scan_body_mesh())
    assert out["delivered_channel_r_mm"] == pytest.approx(1.0, abs=0.15)
    assert out["delivered_channel_vs_recess"] is None  # empty scan -> withheld


@pytest.mark.skipif(
    not (__import__("pathlib").Path(__file__).parents[1]
         / "data/real/scans/doctor-cap6030-neodent-gm").exists(),
    reason="real client scan not on this host")
@pytest.mark.slow
def test_honesty_wave_real_site_measures_the_previously_missing_panel_rows(tmp_path):
    """On a real marked case the three panel rows that read 'missing' before
    2026-07-24 (deviation_rms_mm, rim_off_centre_mm, delivered_channel_vs_recess_mm)
    are measured and banded by the acceptance catalog."""
    from pathlib import Path

    from case_prep.domain.acceptance import MISSING, evaluate_acceptance

    root = Path(__file__).parents[1] / "data/real"
    scan = trimesh.load(next((root / "scans/doctor-cap6030-neodent-gm").glob("*.stl")),
                        force="mesh")
    sites = json.loads((root / "scans/doctor-cap6030-neodent-gm/sites.json"
                        ).read_text())["suggested_sites"]
    out = run_auto_case(
        case_id="hwr", scan=scan,
        library=CapLibrary.load(root / "library/caps/neodent-gm"),
        construction_mesh=trimesh.load(
            root / "library/construction/dess/neodent-gm-scanbody.stl", force="mesh"),
        vendor="dess",
        confirmed=[ConfirmedSite(s["tooth"], tuple(s["center"]),
                                 s.get("declared_variant"),
                                 center_mark=s.get("center_mark"),
                                 rim_mark=s.get("rim_mark"))
                   for s in sites],
        gingival_offset_mm=0.0,  # real vendor part — see module note
        jaw_label="lower", out_dir=tmp_path / "out", render_qc=False)

    (row,) = out["sites"]
    assert row.get("error") is None
    assert row["deviation_rms_mm"] is not None
    assert row["rim_off_centre"] is not None, \
        "centre+rim marks present — the rim-centring number must be measured"
    assert row["delivered_channel_vs_recess"] is not None, \
        "cap6030's recess dip is measured signal (scoreboard reads it) — no None here"

    bands = {m["key"]: m["band"]
             for m in evaluate_acceptance(row)["metrics"]}
    for key in ("deviation_rms_mm", "rim_off_centre_mm",
                "delivered_channel_vs_recess_mm"):
        assert bands[key] != MISSING, f"{key} still reads missing on a measured row"


# ---------------------------------------------------------------------------------
# MACHINE-ANCHORED QA DUAL-REPORT (master plan slices 14-15, §8 item 6)
#
# The measured defect these tests close: QA anchored to the doctor's clicks grades
# the pose against the very gesture that drove it (invariant Q2 violation) — on the
# t13 re-click a 1.09mm-off pose IMPROVED click-anchored rim_agreement 0.62->0.88.
# The dual-report adds machine-anchored twins (anchored to the island shadow's ring,
# segmented from the SCAN) next to the click-anchored numbers, which remain the
# tracked pair until promotion (slice 29 sunset).
# ---------------------------------------------------------------------------------

_BLIND_CENTRE = np.array([1.3, -0.7])   # the planted cap (test_island's geometry)
_BLIND_RIM_R = 2.5
_BLIND_RIM_Z = 3.0
_BLIND_SHIFT = np.array([0.6, 0.0])     # the +0.6x shifted gesture (plan slice 15)


def _blindness_cloud() -> np.ndarray:
    """The t13-style scene: a clean cap (top annulus + empty recess + short wall +
    gingiva beyond an unscanned sulcus) PLUS a tissue collar at rim height on the +x
    side — the structure a drifted gesture lands on. Deterministic polar/grid
    sampling, no RNG."""
    cx, cy = _BLIND_CENTRE
    pts = []
    for r in np.arange(0.75, _BLIND_RIM_R + 1e-9, 0.1):   # cap top (recess r<0.7 empty)
        n = max(int(round(2 * np.pi * r / 0.12)), 8)
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + r * np.cos(th), cy + r * np.sin(th),
                         np.full(n, _BLIND_RIM_Z)])
    for r in np.arange(0.1, 0.65, 0.15):                  # recess floor
        n = max(int(round(2 * np.pi * r / 0.2)), 6)
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + r * np.cos(th), cy + r * np.sin(th),
                         np.full(n, _BLIND_RIM_Z - 2.0)])
    for z in np.arange(_BLIND_RIM_Z - 1.0, _BLIND_RIM_Z - 0.05, 0.25):  # wall
        n = int(round(2 * np.pi * _BLIND_RIM_R / 0.25))
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + _BLIND_RIM_R * np.cos(th),
                         cy + _BLIND_RIM_R * np.sin(th), np.full(n, z)])
    g = np.arange(-8.0, 8.01, 0.2)                        # gingiva past the sulcus gap
    gx, gy = np.meshgrid(g, g)
    gx, gy = gx.ravel() + cx, gy.ravel() + cy
    keep = np.hypot(gx - cx, gy - cy) > _BLIND_RIM_R + 0.7
    pts.append(np.c_[gx[keep], gy[keep], np.zeros(int(keep.sum()))])
    for r in np.arange(3.2, 3.61, 0.1):                   # tissue collar, +x sector
        th = np.arange(-np.pi / 3, np.pi / 3 + 1e-9, 0.1 / r)
        pts.append(np.c_[cx + r * np.cos(th), cy + r * np.sin(th),
                         np.full(len(th), _BLIND_RIM_Z)])
    return np.vstack(pts)


def _blindness_template() -> trimesh.Trimesh:
    """Vertex-dense cap CAD matching the planted cap (canonical frame: wall r=2.5
    spanning z 0..3, top annulus at z=3). The rim QA instruments read template
    VERTICES only — no faces, no surface sampling, no RNG."""
    pts = []
    for z in np.arange(0.0, 3.001, 0.15):
        n = int(round(2 * np.pi * _BLIND_RIM_R / 0.1))
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[_BLIND_RIM_R * np.cos(th), _BLIND_RIM_R * np.sin(th),
                         np.full(n, z)])
    for r in np.arange(0.8, _BLIND_RIM_R + 1e-9, 0.15):
        n = max(int(round(2 * np.pi * r / 0.1)), 8)
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[r * np.cos(th), r * np.sin(th), np.full(n, 3.0)])
    return trimesh.Trimesh(vertices=np.vstack(pts), process=False)


def test_machine_rim_agreement_worsens_on_shifted_pose():
    """THE BLINDNESS-CLOSURE CONTRACT (master plan slice 15, plan-named): on a pose
    deliberately offset toward a shifted gesture, the MACHINE-anchored metric must
    WORSEN while the click-anchored one improves — the t13-measured regression
    (1.09mm-off pose, click-anchored rim_agreement 'improved') that the dual-report
    exists to expose. Anchors and poses are constructed directly: the contract under
    test is the QA anchoring (invariant Q2), not the seat or the segmentation."""
    from case_prep.domain.island import IslandReading
    from case_prep.pipeline.auto_flow import (_machine_qa_twins, _rim_agreement_mm,
                                              _rim_off_centre_anchor_mm)

    L = _blindness_cloud()
    tmpl = _blindness_template()
    pose_true = np.eye(4)
    pose_true[:2, 3] = _BLIND_CENTRE
    pose_shifted = np.eye(4)                      # the pose FOLLOWED the bad gesture
    pose_shifted[:2, 3] = _BLIND_CENTRE + _BLIND_SHIFT
    click_anchor = _BLIND_CENTRE + _BLIND_SHIFT   # pair integrity keeps the radius

    # the click-anchored instrument (exactly what the row computes for a centre+rim
    # pair): anchored to the shifted clicks, it FLATTERS the pose that followed them
    click_true = _rim_agreement_mm(L, click_anchor, _BLIND_RIM_R, tmpl, pose_true)
    click_shifted = _rim_agreement_mm(L, click_anchor, _BLIND_RIM_R, tmpl, pose_shifted)
    assert click_true is not None and click_shifted is not None
    assert click_shifted < click_true - 0.2, (
        f"fixture lost the blindness it must exhibit: click-anchored read "
        f"{click_true:.2f} (true pose) vs {click_shifted:.2f} (0.6mm-off pose) — "
        f"the corrupted pose must read BETTER on the click-anchored number")

    # the machine anchor: a converged island reading at the cap's actual ring
    reading = IslandReading(
        converged=True, reason="ok",
        centre_xy=(float(_BLIND_CENTRE[0]), float(_BLIND_CENTRE[1])),
        radius=_BLIND_RIM_R, island_r=_BLIND_RIM_R + 0.2, rim_z=_BLIND_RIM_Z,
        plane=(0.0, 0.0, _BLIND_RIM_Z), bins_hit=48)
    tw_true = _machine_qa_twins(L, reading, tmpl, pose_true)
    tw_shifted = _machine_qa_twins(L, reading, tmpl, pose_shifted)
    m_true = tw_true["rim_agreement_machine_mm"]
    m_shifted = tw_shifted["rim_agreement_machine_mm"]
    assert m_true is not None and m_shifted is not None
    assert m_shifted > m_true + 0.2, (
        f"BLINDNESS NOT CLOSED: machine-anchored rim agreement read {m_true:.2f} "
        f"(true pose) vs {m_shifted:.2f} (0.6mm-off pose) — the twin must worsen "
        f"where the click-anchored number flatters")

    # the centring twin sees the actual pose error; the click-anchored copy sees ~none
    oc_shifted = tw_shifted["rim_off_centre_machine_mm"]
    assert oc_shifted is not None and oc_shifted == pytest.approx(0.6, abs=0.1)
    oc_click = _rim_off_centre_anchor_mm(L, click_anchor, _BLIND_RIM_R, tmpl,
                                         pose_shifted)
    assert oc_click is not None and oc_click < 0.15, (
        "fixture drift: the click-anchored centring number should flatter the "
        "shifted pose (that blindness is the point)")


def _fake_island(converged: bool):
    """A segment_island stand-in for the WIRING tests: the dual-report must consume
    whatever reading the shadow computed — these tests pin the row contract without
    depending on segmentation behaviour on synthetic scan bodies (builder-B domain)."""
    from case_prep.domain.island import IslandReading

    def fake(L, seed_xy, radius_hint=None, n_bins=48):
        if not converged:
            return IslandReading(converged=False, reason="weak_recess_evidence")
        r = float(radius_hint) if radius_hint else 2.5
        return IslandReading(converged=True, reason="ok",
                             centre_xy=(float(seed_xy[0]), float(seed_xy[1])),
                             radius=r, island_r=r + 0.2, rim_z=0.0,
                             plane=(0.0, 0.0, 0.0), bins_hit=48,
                             contamination_est=0.3)
    return fake


@pytest.mark.slow
def test_dual_report_row_carries_machine_twins_when_island_converges(
        tmp_path, monkeypatch):
    """Row presence (transition dual-report): a converged island puts BOTH machine-
    anchored twins on the row, measured, next to the click-anchored fields — the row
    carries both anchorings, and the reason field is honestly empty."""
    from case_prep.pipeline import auto_flow

    scan, lib, gt = _embedded_case(tmp_path, n=1)
    monkeypatch.setattr(auto_flow, "segment_island", _fake_island(converged=True))
    out = run_auto_case(
        case_id="dr", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[ConfirmedSite(tooth=8,
                                 center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=tmp_path / "out",
        generate_product=False, render_qc=False)

    (row,) = out["sites"]
    assert row.get("error") is None
    assert row["island"]["converged"] is True
    # the machine-anchored twins are measured against the machine ring
    assert row["rim_agreement_machine_mm"] is not None
    assert row["rim_off_centre_machine_mm"] is not None
    assert row["machine_anchor_reason"] is None
    # the click-anchored fields REMAIN — dual-report, not replacement (slice 29
    # deletes; until then both anchorings ride the row)
    assert "rim_agreement_mm" in row
    assert "rim_off_centre" in row


@pytest.mark.slow
def test_dual_report_unconverged_island_reports_none_plus_reason(
        tmp_path, monkeypatch):
    """Unconverged honesty: no converged island -> no machine anchor -> both twins
    None with the gate's name in the reason. Converged-or-absent, never a twin
    computed against a partially-trusted ring."""
    from case_prep.pipeline import auto_flow

    scan, lib, gt = _embedded_case(tmp_path, n=1)
    monkeypatch.setattr(auto_flow, "segment_island", _fake_island(converged=False))
    out = run_auto_case(
        case_id="du", scan=scan, library=lib,
        construction_mesh=make_scan_body_mesh(), vendor="dess",
        gingival_offset_mm=0.0,  # stand-in body — see module note
        confirmed=[ConfirmedSite(tooth=8,
                                 center=tuple(map(float, gt.poses[0].position)))],
        jaw_label="upper", out_dir=tmp_path / "out",
        generate_product=False, render_qc=False)

    (row,) = out["sites"]
    assert row.get("error") is None
    assert row["island"] == {"converged": False, "reason": "weak_recess_evidence"}
    assert row["rim_agreement_machine_mm"] is None
    assert row["rim_off_centre_machine_mm"] is None
    assert row["machine_anchor_reason"] == "island unconverged: weak_recess_evidence"


def test_scoreboard_machine_twin_columns_present_and_never_vote():
    """Scoreboard dual-report (slices 14-15): the machine-anchored twins are rendered
    columns, read from the row fields, and deliberately NOT in _EPS while the dual-
    report runs — the click-anchored columns stay the tracked metrics until promotion
    makes the machine variants the tracked ones (slice 29 sunsets the click pair)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import fleet_scoreboard

    row = {"site": "s/t1", "identified": "6030", "declared": None, "seat": "rim",
           "rim_agreement": 0.5, "rim_agreement_machine": 0.41, "top_face_p90": 0.4,
           "rim_off_centre": 0.1, "rim_off_centre_machine": 0.607,
           "bore_void_off": 0.6, "notch_shift_deg": None, "clock_evidence": None,
           "island_off": None, "island_conv": None, "confidence": "high",
           "gate": "auto"}
    table = fleet_scoreboard._render({"rows": [row]})
    assert "rim-M" in table and "off-ctr-M" in table
    assert "0.41" in table and "0.607" in table
    for key in ("rim_agreement_machine", "rim_off_centre_machine"):
        assert key not in fleet_scoreboard._EPS, (
            f"{key} must not vote improved/regressed during the dual-report period "
            f"— promotion (DR1) is the deliberate switch-over point")
    # pre-slice-15 snapshots carry neither column — None-safe render, no invention
    old = {k: v for k, v in row.items()
           if k not in ("rim_agreement_machine", "rim_off_centre_machine")}
    assert "| — |" in fleet_scoreboard._render({"rows": [old]})


def test_acceptance_rim_seating_note_names_the_machine_twin():
    """The verification panel's rim-seating row tells the doctor the machine-anchored
    twin exists — and the BANDED value stays click-anchored (which value bands is a
    promotion decision, deliberately untouched here; bands are pinned by
    test_acceptance's edge tests)."""
    from case_prep.domain.acceptance import CATALOG

    spec = next(s for s in CATALOG if s.key == "rim_agreement_mm")
    assert "rim_agreement_machine_mm" in (spec.note or "")
    assert spec.bands.pass_max == 0.5 and spec.bands.review_max == 1.6, (
        "dual-report must not move the click-anchored bands — promotion decides")
