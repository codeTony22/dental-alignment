"""build_embedded_case: place the clean library CAD into an arch at a known pose, degraded, and
use that CAD as the registration reference. Guards the real-geometry end-to-end builder.

Uses a synthetic gingiva arch as a self-contained stand-in (the real Teeth3DS arch is gitignored)
and the real vendor CAD as the library (skipped when absent). Asserts the case is built correctly
and the production localize->register path runs through it. NOTE: clinical recovery accuracy on
real dental structure is gated on ROI isolation (separating the body from surrounding teeth) --
that is measured/tracked in the embedded-arch evaluation, not asserted as a tight bound here.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters import client_data
from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.real_case import build_embedded_case
from case_prep.adapters.synthetic import make_gingiva_arch
from case_prep.domain.geometry import Axis
from case_prep.domain.metrics import axis_error_deg, position_error_mm
from case_prep.domain.poses import Retention

CAD = client_data.LEGACY_SHELF_CAD
ARCH = Path(__file__).resolve().parents[1] / "data/real/QSS7S0G2_lower.obj"
pytestmark = pytest.mark.skipif(not CAD.exists(), reason="real vendor CAD not present (gitignored)")


@pytest.mark.slow
def test_build_embedded_case_emits_artifacts_and_runs(tmp_path):
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)

    case = tmp_path / "case"
    gt = build_embedded_case(arch_path, CAD, case, n_implants=1, retention=Retention.CEMENT, seed=1)

    # the real-geometry case artifacts exist, with the CLEAN CAD as the reference library
    assert (case / "scan.stl").exists()
    lib_mesh = case / "library" / "certain3i_4_1" / "mesh.stl"
    assert lib_mesh.exists()
    assert (case / "ground_truth.json").exists()
    assert (case / "case.json").exists()
    assert len(gt.poses) == 1

    # the production path runs end-to-end through the embedded case (operator seed = truth)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = trimesh.load(lib_mesh, force="mesh")
    seed = np.asarray(gt.poses[0].position, float)
    loc = engine.localize_from_seed(np.asarray(scan.vertices, float), seed, radius=5.5)
    assert loc is not None
    transform, conf = engine.register(loc, lib, Retention.CEMENT)
    assert transform.matrix.shape == (4, 4)
    assert 0.0 <= conf.icp_fitness <= 1.0


def test_embedded_body_is_degraded_not_pristine(tmp_path):
    """The placed body must be degraded (noise+occlusion) -- registering a clean CAD against a
    clean copy of itself would be trivially perfect and prove nothing."""
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    case = tmp_path / "case"
    build_embedded_case(arch_path, CAD, case, n_implants=1, seed=1, noise_mm=0.04, occlusion=0.30)

    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = trimesh.load(case / "library" / "certain3i_4_1" / "mesh.stl", force="mesh")
    arch = trimesh.load(arch_path, force="mesh")
    # the scan = arch + a degraded body, so it has MORE vertices than the bare arch...
    assert len(scan.vertices) > len(arch.vertices)
    # ...but fewer body points than a pristine placement (occlusion dropped ~30% of faces)
    added = len(scan.vertices) - len(arch.vertices)
    assert added < len(lib.vertices)


@pytest.mark.slow
@pytest.mark.skipif(not ARCH.exists(), reason="real Teeth3DS arch not present (gitignored)")
def test_body_isolation_recovers_among_real_teeth(tmp_path):
    """Body isolation guard: the clean CAD localized among REAL teeth recovers to clinical
    tolerance. With a naive sphere crop this was 1.53 mm / 64deg (ROI ~3/4 tissue); the vertical-
    cylinder + surface-normal ROI + occlusal-normal axis seed brings it to ~0.1 mm / ~4deg."""
    np.random.seed(7)  # trimesh sampling uses the global RNG; pin it or the test is order-dependent
    pos, axis = [], []
    for s in range(5):
        case = tmp_path / f"case{s}"
        gt = build_embedded_case(ARCH, CAD, case, n_implants=1, retention=Retention.CEMENT, seed=s)
        scan = trimesh.load(case / "scan.stl", force="mesh")
        lib = trimesh.load(case / "library" / "certain3i_4_1" / "mesh.stl", force="mesh")
        truth = gt.poses[0]
        loc = engine.localize_from_seed(
            np.asarray(scan.vertices, float), np.asarray(truth.position, float),
            normals=np.asarray(scan.vertex_normals, float),
        )
        assert loc is not None
        t_est, _ = engine.register(loc, lib, Retention.CEMENT)
        pos.append(position_error_mm(t_est.apply(np.zeros(3)), np.asarray(truth.position, float)))
        axis.append(axis_error_deg(Axis.from_vector(t_est.rotation @ [0, 0, 1.0]),
                                   Axis.from_vector(np.asarray(truth.axis, float))))
    pos, axis = np.array(pos), np.array(axis)
    # was 1.53mm/64deg; guard the isolation win with headroom for the residual tissue contamination
    assert np.median(pos) < 0.25, f"median pos {np.median(pos):.3f}mm (all={np.round(pos,3)})"
    assert np.median(axis) < 8.0, f"median axis {np.median(axis):.2f}deg (all={np.round(axis,2)})"


@pytest.mark.slow
@pytest.mark.skipif(not ARCH.exists(), reason="real Teeth3DS arch not present (gitignored)")
def test_confidence_signals_separate_wrong_poses_after_isolation(tmp_path):
    """The gate-calibration property (docs/engagement/gate-calibration-findings.md): WITH body
    isolation, a position-wrong registration no longer produces confident surface signals —
    the mechanism behind the documented 1.75 mm false-confidence PASS is gone. Guard the
    separation band: wrong poses (>0.5 mm) sit at fitness <= ~0.35, good poses at >= ~0.59;
    a future validated-embedded gate would thread it at ~0.45. n is small (one arch/part), so
    this guards the MECHANISM — it does not promote the embedded class to VALIDATED."""
    np.random.seed(7)
    rng = np.random.default_rng(11)
    case = tmp_path / "case"
    gt = build_embedded_case(ARCH, CAD, case, n_implants=2, retention=Retention.CEMENT, seed=1)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = trimesh.load(case / "library" / "certain3i_4_1" / "mesh.stl", force="mesh")
    pts = np.asarray(scan.vertices, float)
    nrm = np.asarray(scan.vertex_normals, float)

    from case_prep.domain.metrics import position_error_mm
    for p in gt.poses:
        truth = np.asarray(p.position, float)
        for seed in (truth, truth + rng.normal(0, 1.0, 3) + np.array([2.5, 0.8, 0.0])):
            loc = engine.localize_from_seed(pts, seed, normals=nrm)
            assert loc is not None
            t_est, conf = engine.register(loc, lib, Retention.CEMENT)
            err = position_error_mm(t_est.apply(np.zeros(3)), truth)
            if err > 0.5:      # a wrong pose must NOT look confident
                assert conf.icp_fitness < 0.45, (
                    f"false-confidence regression: {err:.2f}mm-wrong pose at "
                    f"fitness {conf.icp_fitness:.2f}")
            elif err < 0.3:    # a good pose must clear the future validated band
                assert conf.icp_fitness > 0.45, (
                    f"good pose ({err:.2f}mm) below the separation band "
                    f"(fitness {conf.icp_fitness:.2f})")


@pytest.mark.slow
@pytest.mark.skipif(not ARCH.exists(), reason="real Teeth3DS arch not present (gitignored)")
@pytest.mark.parametrize("n_bodies", [2, 3])
def test_auto_localize_finds_all_bodies_no_false_positives(tmp_path, n_bodies):
    """Auto-localization guard: template-matching the CAD along the ridge finds every embedded
    body among real teeth and rejects the teeth (no operator seed). Bodies fit ~0.65, teeth ~0.2."""
    np.random.seed(7)  # pin the global RNG (trimesh sampling) for order-independence
    case = tmp_path / "case"
    gt = build_embedded_case(ARCH, CAD, case, n_implants=n_bodies, retention=Retention.CEMENT, seed=3)
    scan = trimesh.load(case / "scan.stl", force="mesh")
    lib = trimesh.load(case / "library" / "certain3i_4_1" / "mesh.stl", force="mesh")
    truths = np.array([p.position for p in gt.poses])

    dets = engine.auto_localize(
        np.asarray(scan.vertices, float), lib, max_bodies=n_bodies + 2,
        normals=np.asarray(scan.vertex_normals, float),
    )
    matched = sum(1 for d in dets
                  if np.linalg.norm(truths - d.localization.centroid, axis=1).min() < 2.5)
    assert len(dets) == n_bodies, f"detected {len(dets)}, expected {n_bodies}"  # count (no false+)
    assert matched == n_bodies, f"only {matched}/{n_bodies} detections near a true body"  # full recall
