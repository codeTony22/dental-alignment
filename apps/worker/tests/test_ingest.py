"""Real-file ingest: real scans arrive in arbitrary orientation/scale (unlike the
synthetic z-up frame). Normalization recovers an occlusal-up, centred frame so the
rest of the pipeline runs unchanged."""
import numpy as np
import trimesh

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.adapters.loader import load_case
from case_prep.adapters.ingest import normalize_orientation, scale_ok


def _scan(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=7, n_implants=3))
    return load_case(tmp_path).scan


def test_normalize_puts_the_thin_occlusal_axis_on_z(tmp_path):
    scan = _scan(tmp_path)
    # tumble it into an arbitrary pose
    R = trimesh.transformations.rotation_matrix(0.9, [0.3, 0.8, 0.5])
    scan.apply_transform(R)

    out, _transform = normalize_orientation(scan)
    v = out.vertices
    # the occlusal (z) axis is the lowest-variance direction — the arch is a flat-ish
    # plate (scan bodies add z-EXTENT but little variance, so we check variance not extent)
    assert v[:, 2].std() <= v[:, 0].std() and v[:, 2].std() <= v[:, 1].std()


def test_normalize_orients_scan_bodies_toward_plus_z(tmp_path):
    scan = _scan(tmp_path)
    scan.apply_transform(trimesh.transformations.rotation_matrix(2.4, [1, 0.4, 0.2]))
    out, _ = normalize_orientation(scan)
    z = out.vertices[:, 2]
    # scan bodies protrude on the +z side: the positive tail is longer than the negative
    assert z.max() > abs(z.min())


def test_normalize_is_a_rigid_transform(tmp_path):
    scan = _scan(tmp_path)
    before = scan.volume
    out, transform = normalize_orientation(scan)
    assert out.volume == np_approx(before, rel=1e-6)  # rigid: volume preserved
    assert transform.matrix.shape == (4, 4)


def test_canonicalize_library_centres_and_round_trips():
    from case_prep.adapters.ingest import canonicalize_library
    # a library mesh sitting off in world coords (like a segmented real scan body)
    mesh = trimesh.creation.cylinder(radius=2.0, height=8.0)
    mesh.apply_translation([27.0, -2.0, 5.0])

    local, placement = canonicalize_library(mesh)
    assert np.linalg.norm(local.vertices.mean(axis=0)) < 1e-6      # centred at origin
    back = placement.apply(local.vertices)                          # placement restores world
    assert np.allclose(np.sort(back, axis=0), np.sort(mesh.vertices, axis=0), atol=1e-6)


def test_canonicalize_library_is_idempotent():
    """Canonicalizing an already-canonical mesh must be a no-op. PCA eigenvector signs are
    arbitrary, so without a deterministic sign convention a second canonicalization can flip
    axes and rotate the part (measured: an 11 mm vertex shift on the real vendor CAD), which
    silently breaks any caller that canonicalizes defensively (e.g. the cap library)."""
    from case_prep.adapters.ingest import canonicalize_library
    from case_prep.adapters.synthetic import make_scan_body_mesh

    once, _ = canonicalize_library(make_scan_body_mesh())
    twice, _ = canonicalize_library(once.copy())
    assert np.abs(np.asarray(twice.vertices) - np.asarray(once.vertices)).max() < 1e-6


def test_canonicalize_library_fixed_point_returns_identity_placement():
    """An already-canonical mesh is the projection's fixed point: it comes back unchanged with
    an IDENTITY placement (not merely a small rotation) — the guarantee callers that
    canonicalize defensively (e.g. the cap library) rely on. NOTE: no orientation-convergence
    is promised — SVD signs are arbitrary on first canonicalization; the frame is stable
    because re-canonicalization is a no-op, not because the frame is data-unique."""
    from case_prep.adapters.ingest import canonicalize_library
    from case_prep.adapters.synthetic import make_scan_body_mesh

    once, _ = canonicalize_library(make_scan_body_mesh())
    again, placement = canonicalize_library(once.copy())
    assert np.allclose(placement.matrix, np.eye(4), atol=1e-9)
    assert np.abs(np.asarray(again.vertices) - np.asarray(once.vertices)).max() < 1e-9


def test_scale_gate_accepts_a_human_arch_and_rejects_a_tiny_one(tmp_path):
    scan = _scan(tmp_path)
    assert scale_ok(scan)
    scan.apply_scale(0.01)  # 1/100th -> implausible
    assert not scale_ok(scan)


def np_approx(value, rel):
    import pytest
    return pytest.approx(value, rel=rel)
