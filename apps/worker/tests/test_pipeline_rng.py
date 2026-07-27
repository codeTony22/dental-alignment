"""THE RUN OWNS ITS RANDOMNESS.

Surface sampling is the seating pipeline's only source of randomness, and it used to come
from numpy's PROCESS-GLOBAL stream. ``run_auto_case`` compensated by calling
``np.random.seed(0)`` on entry — which bought determinism at two prices:

  * it TRAMPLED the caller. Anyone who had seeded numpy for their own reasons (a study
    harness, a fixture, an offline benchmark) silently had their stream replaced by ours,
    mid-process, as a side effect of aligning a case;
  * it was a discipline, not a guarantee. Any stage that reseeded — or any second case
    interleaved in the same process — reopened the hole it was closing, and the failure
    mode is a run that quietly disagrees with itself in the third significant figure.

``adapters/rng.PipelineRng`` replaces it with an injected, owned stream. These are the
behavioural claims, not the implementation: the same inputs give byte-identical poses no
matter what the ambient stream was, and the ambient stream comes back untouched.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.synthetic import make_gingiva_arch, make_scan_body_mesh
from case_prep.domain.cap_catalog import CapSpec
from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case
from case_prep.adapters.rng import DEFAULT_SEED, PipelineRng, sample_surface


class TestTheOwnedStream:
    def test_two_streams_on_one_seed_draw_the_same_points(self):
        mesh = trimesh.creation.icosphere(subdivisions=2)
        a, b = PipelineRng(7), PipelineRng(7)
        for _ in range(3):  # the stream ADVANCES — equality must hold call after call
            assert np.array_equal(a.sample_surface(mesh, 64),
                                  b.sample_surface(mesh, 64))

    def test_the_stream_advances_rather_than_repeating(self):
        mesh = trimesh.creation.icosphere(subdivisions=2)
        rng = PipelineRng(7)
        assert not np.array_equal(rng.sample_surface(mesh, 64),
                                  rng.sample_surface(mesh, 64)), \
            "a stream that repeats itself is a constant, not a sample"

    def test_different_seeds_draw_differently(self):
        mesh = trimesh.creation.icosphere(subdivisions=2)
        assert not np.array_equal(PipelineRng(1).sample_surface(mesh, 64),
                                  PipelineRng(2).sample_surface(mesh, 64))

    def test_drawing_leaves_the_ambient_stream_exactly_as_found(self):
        mesh = trimesh.creation.icosphere(subdivisions=2)
        np.random.seed(4321)
        before = np.random.get_state()
        PipelineRng().sample_surface(mesh, 128)
        after = np.random.get_state()
        assert before[0] == after[0] and np.array_equal(before[1], after[1])
        assert before[2:] == after[2:]

    def test_the_ambient_stream_cannot_reach_into_the_owned_one(self):
        mesh = trimesh.creation.icosphere(subdivisions=2)
        np.random.seed(11)
        first = PipelineRng().sample_surface(mesh, 64)
        np.random.seed(999999)
        np.random.random(500)          # ambient churn between the two draws
        assert np.array_equal(first, PipelineRng().sample_surface(mesh, 64))

    def test_the_shipped_stream_matches_the_legacy_global_seeding(self):
        """The migration's zero-diff claim, stated as a test: the owned stream on the
        shipped seed is the SAME stream ``np.random.seed(0)`` used to install, so every
        pose/coverage/residual the acceptance bands were calibrated on is unchanged."""
        mesh = trimesh.creation.icosphere(subdivisions=2)
        np.random.seed(DEFAULT_SEED)
        legacy_a, _ = trimesh.sample.sample_surface(mesh, 200)
        legacy_b, _ = trimesh.sample.sample_surface(mesh, 200)
        owned = PipelineRng()
        assert np.array_equal(np.asarray(legacy_a, float), owned.sample_surface(mesh, 200))
        assert np.array_equal(np.asarray(legacy_b, float), owned.sample_surface(mesh, 200))

    def test_the_migration_shim_falls_back_to_the_ambient_stream(self):
        """Helpers shared with not-yet-migrated callers (server.best_fit, the offline
        strategy benchmarks) must keep their old behaviour when handed no stream."""
        mesh = trimesh.creation.icosphere(subdivisions=2)
        np.random.seed(5)
        expected, _ = trimesh.sample.sample_surface(mesh, 64)
        np.random.seed(5)
        assert np.array_equal(np.asarray(expected, float), sample_surface(None, mesh, 64))


@pytest.fixture(scope="module")
def synthetic_case(tmp_path_factory):
    from case_prep.adapters.real_case import build_embedded_case

    root = tmp_path_factory.mktemp("rng-case")
    arch = root / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch)
    cad = root / "cap.stl"
    make_scan_body_mesh().export(cad)
    gt = build_embedded_case(arch, cad, root / "case", n_implants=1, seed=1)
    scan = trimesh.load(root / "case/scan.stl", force="mesh")
    lib = CapLibrary.single(
        CapSpec("certain", "4.1"),
        trimesh.load(root / "case/library/certain3i_4_1/mesh.stl", force="mesh"))
    return scan, lib, [ConfirmedSite(tooth=19, center=tuple(map(float, gt.poses[0].position)))]


def _poses(summary_dir) -> list:
    """Exact bytes of every shipped pose in the emitted package."""
    import json
    out = []
    for path in sorted(summary_dir.glob("*-implant.json")):
        rec = json.loads(path.read_text())
        out.append([float(v).hex()
                    for v in np.asarray(rec["pose_matrix"], float).reshape(-1)])
    return out


def _run(case, out_dir):
    scan, lib, confirmed = case
    run_auto_case(case_id="rng", scan=scan, library=lib,
                  construction_mesh=make_scan_body_mesh(), vendor="dess",
                  gingival_offset_mm=0.0, confirmed=confirmed, jaw_label="upper",
                  out_dir=out_dir, render_qc=False)
    return _poses(out_dir)


@pytest.mark.slow
class TestTheRunIsIndependentOfAmbientRandomness:
    def test_two_runs_under_different_ambient_seeds_ship_identical_poses(
            self, synthetic_case, tmp_path):
        np.random.seed(1234)
        first = _run(synthetic_case, tmp_path / "a")
        np.random.seed(98765)
        np.random.random(1000)   # and leave the ambient stream mid-sequence, not at a seed
        second = _run(synthetic_case, tmp_path / "b")
        assert first and first == second, \
            "the shipped pose moved when only the ambient RNG differed"

    def test_a_run_does_not_trample_the_callers_global_stream(self, synthetic_case,
                                                              tmp_path):
        """The property the old ``np.random.seed(0)`` could not offer: aligning a case
        is not allowed to reach into the caller's randomness."""
        np.random.seed(2468)
        before = np.random.get_state()
        _run(synthetic_case, tmp_path / "c")
        after = np.random.get_state()
        assert before[0] == after[0] and np.array_equal(before[1], after[1]), \
            "run_auto_case replaced the caller's numpy stream"
        assert before[2:] == after[2:]

    def test_an_explicit_seed_is_honoured_end_to_end(self, synthetic_case, tmp_path):
        """The stream is an INPUT: a different seed is allowed to move the pose (that is
        what makes the default one a real choice rather than decoration)."""
        scan, lib, confirmed = synthetic_case
        shipped = _run(synthetic_case, tmp_path / "d")
        other = tmp_path / "e"
        run_auto_case(case_id="rng", scan=scan, library=lib,
                      construction_mesh=make_scan_body_mesh(), vendor="dess",
                      gingival_offset_mm=0.0, confirmed=confirmed, jaw_label="upper",
                      out_dir=other, render_qc=False, rng=PipelineRng(seed=DEFAULT_SEED))
        assert _poses(other) == shipped, "the explicit shipped seed must reproduce it"
