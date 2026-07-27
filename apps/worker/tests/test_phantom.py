"""Tests for the PRINTED PHANTOM protocol (tools/make_phantom.py, tools/evaluate_phantom.py)
— the path to a VALIDATED auto-pass line: a physical plate with library healing caps
FUSED IN at exactly-designed poses (ground truth BY CONSTRUCTION), scanned like a stone
model, then compared against the pipeline's shipped pose + confidence grade.

``tools/`` isn't on pythonpath (only ``src`` is, per pyproject.toml), so this file inserts
``tools/`` onto sys.path itself — the same bootstrap ``tests/test_fle_study.py`` uses.

Kept fast (coarse ``--voxel-mm`` + a 2-3 site mini-plate): the full 6-site fine-resolution
plate is CLI-only (``tools/make_phantom.py``), generated once as a VERIFY step, not part
of this suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import evaluate_phantom as ep  # noqa: E402  (path bootstrap must run first)
import make_phantom as mp  # noqa: E402

_COARSE_VOXEL_MM = 0.5
# The money test generates at the PRINT pitch: the coded-cutout relief (0.4-0.7mm
# dips) that the ROTATION validation reads does not survive a 0.5mm grid, and the
# print pitch is what the physical protocol actually validates. The fast generator
# invariants (determinism, watertightness, footprint) keep the coarse grid.
_PRINT_VOXEL_MM = 0.15
_MONEY_TEST_N_SITES = 3  # exposed, half, deep — one of each (see mp.SITES)


# -----------------------------------------------------------------------------------
# Deliverable 3.1 — generator invariants
# -----------------------------------------------------------------------------------
@pytest.mark.slow
def test_generator_is_deterministic(tmp_path):
    """No RNG anywhere in make_phantom.py (every design parameter is a fixed literal
    — see its module docstring): two runs must be byte-for-byte identical, a
    strictly stronger guarantee than seeded-RNG determinism."""
    truth_a = mp.generate_phantom(tmp_path / "a", voxel_mm=_COARSE_VOXEL_MM, n_sites=2)
    truth_b = mp.generate_phantom(tmp_path / "b", voxel_mm=_COARSE_VOXEL_MM, n_sites=2)

    mesh_a = trimesh.load(tmp_path / "a" / "phantom-plate.stl", force="mesh")
    mesh_b = trimesh.load(tmp_path / "b" / "phantom-plate.stl", force="mesh")
    assert mesh_a.vertices.shape == mesh_b.vertices.shape
    assert np.array_equal(np.asarray(mesh_a.vertices), np.asarray(mesh_b.vertices))
    assert np.array_equal(np.asarray(mesh_a.faces), np.asarray(mesh_b.faces))
    assert truth_a == truth_b


@pytest.mark.slow
def test_generator_plate_is_watertight(tmp_path):
    mesh, _records = mp.build_plate_solid(n_sites=2, voxel_mm=_COARSE_VOXEL_MM)
    assert mesh.is_watertight, "phantom plate must be watertight for slicing"
    # a sanity floor on volume: not a degenerate sliver
    assert mesh.volume > 10_000.0


@pytest.mark.slow
def test_generator_plate_footprint_and_height_within_spec():
    mesh, _records = mp.build_plate_solid(n_sites=1, voxel_mm=_COARSE_VOXEL_MM)
    ext = mesh.bounds[1] - mesh.bounds[0]
    assert 65.0 <= ext[0] <= 75.0  # ~70mm length
    assert 40.0 <= ext[1] <= 50.0  # ~45mm width
    assert 12.0 <= ext[2] <= 18.0  # 12-18mm tall


@pytest.mark.parametrize("level,height_mm,expected_fraction", [
    ("exposed", 4.0, 0.0),
    ("half", 4.0, 0.5),
    ("deep", 4.0, 0.75),   # (4 - 1) / 4
    ("deep", 2.0, 0.5),    # (2 - 1) / 2
])
def test_submergence_fraction_formula(level, height_mm, expected_fraction):
    assert mp.submergence_fraction(level, height_mm) == pytest.approx(expected_fraction)


@pytest.mark.slow
def test_submergence_levels_actually_differ_in_exposed_height():
    """The formula is monotonic (exposed < half < deep in material COVERAGE, i.e.
    exposed < half < deep in fraction-of-height covered) for every real variant
    height in the design table — not just the illustrative cases above."""
    libs = mp.load_cap_libraries()
    for site in mp.SITES:
        template = libs[site["model"]]._templates[
            next(sp for sp in libs[site["model"]].specs if sp.variant == site["variant"])]
        v = np.asarray(template.vertices, float)
        height = float(v[:, 2].max() - v[:, 2].min())
        fracs = [mp.submergence_fraction(level, height) for level in ("exposed", "half", "deep")]
        assert fracs[0] < fracs[1] < fracs[2], (site["label"], fracs)


@pytest.mark.slow
def test_designed_clock_angle_is_realized_in_the_pose():
    """`clock_deg` is ground truth BY CONSTRUCTION: the design pose must decompose as
    tilt @ Rz(clock_deg), i.e. stripping the designed tilt leaves exactly the designed
    clock twist about the canonical axis — and clocking must not move the axis."""
    libs = mp.load_cap_libraries()
    for site in mp.SITES:
        lib = libs[site["model"]]
        template = lib.template(next(sp for sp in lib.specs if sp.variant == site["variant"]))
        rim_r = lib.variant_dimensions()[site["variant"]][0] / 2.0
        geo = mp.compute_site_pose(site, template, rim_r)

        tilt_axis = [np.cos(np.radians(site["tilt_theta_deg"])),
                     np.sin(np.radians(site["tilt_theta_deg"])), 0.0]
        r_tilt = trimesh.transformations.rotation_matrix(
            np.radians(site["tilt_deg"]), tilt_axis)[:3, :3]
        rel = r_tilt.T @ geo["pose"][:3, :3]
        twist = np.degrees(np.arctan2(rel[1, 0], rel[0, 0])) % 360.0
        assert twist == pytest.approx(site["clock_deg"] % 360.0, abs=1e-6), site["site_id"]
        # the axis is a tilt-only quantity; the clock rotation must leave it unchanged
        assert np.allclose(geo["axis_world"], r_tilt @ [0.0, 0.0, 1.0], atol=1e-9)


@pytest.mark.slow
def test_generator_truth_matches_the_built_solid(tmp_path):
    """The posed template surface must lie ON (within a small epsilon of) the plate
    solid for its EXPOSED portion (above the collar line — nothing else covers it,
    so it IS the outer surface there), and be fully BURIED (inside the solid) for
    its covered portion — for every submergence level."""
    mesh, records = mp.build_plate_solid(n_sites=_MONEY_TEST_N_SITES, voxel_mm=_COARSE_VOXEL_MM)
    epsilon_mm = max(2.0 * _COARSE_VOXEL_MM, 0.4)
    levels_seen = set()

    for r in records:
        site = r["site"]
        levels_seen.add(site["submergence"])
        template = mp.load_cap_libraries()[site["model"]].template(
            next(sp for sp in mp.load_cap_libraries()[site["model"]].specs
                if sp.variant == site["variant"]))
        v = np.asarray(template.vertices, float)
        pose = r["pose"]

        exposed_local = v[v[:, 2] > r["collar_top_local_z"] + 0.3]
        buried_local = v[v[:, 2] < r["collar_top_local_z"] - 0.3]

        if len(exposed_local):
            exposed_world = exposed_local @ pose[:3, :3].T + pose[:3, 3]
            dist = mesh.nearest.on_surface(exposed_world)[1]
            # loose (95th pct, not max): a handful of coded-cutout vertices near the
            # collar boundary band can legitimately sit right at the covered/exposed
            # transition and read a slightly larger distance
            assert np.percentile(dist, 95) < epsilon_mm + 0.6, (site["label"], "exposed")

        if len(buried_local):
            buried_world = buried_local @ pose[:3, :3].T + pose[:3, 3]
            inside = mesh.contains(buried_world)
            assert inside.mean() > 0.85, (site["label"], "buried", inside.mean())

    assert levels_seen == {"exposed", "half", "deep"}, \
        f"mini-plate must cover all 3 submergence levels, got {levels_seen}"


# -----------------------------------------------------------------------------------
# Deliverable 3.2 — THE MONEY TEST: simulated round-trip
# -----------------------------------------------------------------------------------
def _simulate_scan(design: trimesh.Trimesh, seed: int, noise_mm: float = 0.04,
                   occlusion: float = 0.12) -> trimesh.Trimesh:
    """A random rigid transform + degrade, mirroring
    ``case_prep.adapters.real_case._degrade_body`` (Gaussian vertex noise + patchy
    face-drop occlusion). ALSO drops the flat bottom face before transforming: a
    real lab/desktop scan of a model resting on the scanner stage never captures
    that face either (single-sided capture, like a real intraoral scan) — and
    without dropping it, ``crown_up_axis`` (case_prep.adapters.cap_detection, used
    internally by the real pipeline) has no reliable up/down signal on a
    fully-enclosed solid (measured: the closed print solid's bottom face is large
    and flat enough to compete with the top for 'most common outward normal
    direction', occasionally flipping the recovered axis 180 degrees — a genuine
    scanning-protocol requirement now documented in phantom-protocol.md, not a
    generator defect)."""
    rng = np.random.default_rng(seed)
    v = np.asarray(design.vertices, float)
    keep_faces = ~np.all(np.abs(v[design.faces][:, :, 2]) < 0.05, axis=1)
    shell = design.copy()
    shell.update_faces(keep_faces)
    shell.remove_unreferenced_vertices()

    rot = trimesh.transformations.random_rotation_matrix(rng.uniform(size=3))[:3, :3]
    m_true = np.eye(4)
    m_true[:3, :3] = rot
    m_true[:3, 3] = rng.uniform(-40.0, 40.0, size=3)
    scan = shell.copy()
    scan.apply_transform(m_true)

    if occlusion > 0 and len(scan.faces) > 10:
        keep = rng.random(len(scan.faces)) > occlusion
        if keep.any():
            scan.update_faces(keep)
            scan.remove_unreferenced_vertices()
    if noise_mm > 0:
        scan.vertices = np.asarray(scan.vertices, float) + rng.normal(0, noise_mm, scan.vertices.shape)
    return scan


@pytest.mark.slow
def test_simulated_round_trip_proves_the_whole_loop(tmp_path):
    """Generate a mini-plate -> simulate a degraded, arbitrarily-transformed scan of
    it -> run evaluate_phantom end to end. This is the de-risk proof: it must all
    work BEFORE anything is printed.

    Bounds are loose and documented, per the mission: tight for the EXPOSED site
    (nothing hides its geometry), sanity-only (not tight) for half/deep — a
    submerged cap's visible boundary can sit anywhere along a NON-monotonic,
    non-circular real CAD profile, and the production pinned-rim-seat's depth
    resolution is measurably more sensitive there (see make_phantom.compute_site_pose's
    docstring) — exactly the kind of gap this phantom protocol exists to surface,
    not paper over with a generous assertion.

    ROTATION: the truth now fixes each cap's designed clock angle, and the evaluator
    reports the residual clock error via BOTH production instruments (coded-feature
    reading and recess-void bore azimuth). The exposed cap gates the coded reading at
    <= 5 deg; submerged caps gate on the extractor's own evidence flag (honest
    refusal is a pass; a confident-but-wrong read is a failure).
    """
    truth = mp.generate_phantom(tmp_path / "design", voxel_mm=_PRINT_VOXEL_MM,
                                n_sites=_MONEY_TEST_N_SITES)
    design = trimesh.load(tmp_path / "design" / "phantom-plate.stl", force="mesh")
    truth_path = tmp_path / "design" / "phantom-ground-truth.json"

    # ROTATION is ground truth by construction now: every site declares its designed
    # clock angle alongside the pose
    assert all("clock_deg" in s for s in truth["sites"])

    scan = _simulate_scan(design, seed=42)
    scan_path = tmp_path / "scan.stl"
    scan.export(scan_path)

    report = ep.evaluate_phantom(scan_path, truth_path, out_dir=tmp_path / "eval")

    # registration succeeded and is trustworthy
    reg = report["registration"]
    assert reg["icp_fitness"] > 0.3
    assert reg["icp_residual_mm"] < 1.0

    by_submergence = {s["submergence"]: s for s in report["sites"]}
    assert set(by_submergence) == {"exposed", "half", "deep"}

    exposed = by_submergence["exposed"]
    assert exposed["true_error"] is not None, "exposed site failed to seat at all"
    assert exposed["true_error"]["centre_mm"] < 1.2
    assert exposed["true_error"]["axis_deg"] < 8.0
    assert exposed["confidence"] is not None and exposed["confidence"]["grade"] in (
        "low", "medium", "high")

    # CLOCK: the coded-feature reading must recover the designed clock angle on the
    # fully-exposed cap (nothing hides its code band) to <= 5 deg — the phantom's
    # rotation deliverable, and the arbiter of the codes-vs-recess instrument
    # conflict. Measured at this seed/pitch: 1.5 deg codes vs 49 deg recess.
    clock = exposed["clock"]
    assert clock is not None, "exposed site shipped no pose to clock-check"
    assert clock["clock_err_codes_deg"] is not None, \
        "coded-feature instrument produced no reading on the fully-exposed cap"
    assert clock["clock_err_codes_deg"] <= 5.0, (
        f"coded reading missed the designed clocking by "
        f"{clock['clock_err_codes_deg']:.1f} deg (designed "
        f"{clock['designed_clock_deg']} deg)")

    # half/deep: sanity-only POSE bounds (catch a total pipeline failure; do not
    # assert tightness — see docstring). CLOCK on submerged caps is reported
    # honestly and gated ON EVIDENCE only: when the production evidence gate
    # (corr/prominence/occupancy) says the code read is trustworthy it must be
    # accurate; when it refuses, the refusal IS the correct behavior (measured at
    # this pitch: half reads 3.1 deg but corr 0.34 < 0.45 refuses; deep's covered
    # band reads garbage and refuses — both honest).
    for level in ("half", "deep"):
        row = by_submergence[level]
        assert row["true_error"] is not None, f"{level} site failed to seat at all"
        assert row["true_error"]["centre_mm"] < 10.0
        assert row["true_error"]["axis_deg"] < 90.0
        assert row["confidence"] is not None
        c = row["clock"]
        assert c is not None and "clock_err_codes_deg" in c and "evidence" in c
        if c["codes_evidence"]:
            assert c["clock_err_codes_deg"] <= 5.0, (
                f"{level}: evidence-passing coded reading was wrong by "
                f"{c['clock_err_codes_deg']:.1f} deg — the evidence gate lied")

    # the confidence-validation table itself is produced, with grades present
    verdict = report["confidence_validation"]
    assert verdict["n_graded_sites"] == 3
    assert (tmp_path / "eval" / "phantom-evaluation.md").exists()
    assert (tmp_path / "eval" / "phantom-evaluation.json").exists()
    md = (tmp_path / "eval" / "phantom-evaluation.md").read_text()
    assert "Confidence-validation table" in md
    assert "clock_err_codes_deg" in md and "clock_err_recess_deg" in md


@pytest.mark.slow
def test_evaluator_refuses_a_non_phantom_scan(tmp_path):
    """Feeding a scan that is NOT the phantom (a plain box) must abort at
    registration with a clear message — never a fabricated validation."""
    mp.generate_phantom(tmp_path / "design", voxel_mm=_COARSE_VOXEL_MM, n_sites=2)
    truth_path = tmp_path / "design" / "phantom-ground-truth.json"

    box = trimesh.creation.box(extents=[70.0, 45.0, 15.0])
    box = box.subdivide().subdivide().subdivide()
    assert len(box.vertices) >= 200, "need enough points to exercise the fiducial-match path"
    box_path = tmp_path / "garbage.stl"
    box.export(box_path)

    with pytest.raises(ep.RegistrationError, match="fiducial signature not found"):
        ep.evaluate_phantom(box_path, truth_path, out_dir=tmp_path / "eval-garbage")
