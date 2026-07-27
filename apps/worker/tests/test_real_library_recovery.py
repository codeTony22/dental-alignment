"""Regression guard for real-library recovery through the PRODUCTION path.

Loads the clean Certain scan-abutment CAD from the client drop (adapters/client_data),
canonicalizes it, places it at known 6-DoF poses, simulates a scan (clean, then noise+occlusion),
and asserts the production localize->register path recovers position AND axis to clinical
tolerance. This locks in two findings:

  1. The clean library reference closes the real-data gap: 2.6 mm (noisy self-comparison) ->
     ~20 microns position / ~1-2 deg axis with a clean reference.
  2. The registration multi-start must search an AXIS CONE, not clocking only. A near-symmetric
     coded body otherwise lets ICP settle in a wrong basin ~40 deg off (even on a clean scan);
     seeding axis tilts lets ICP reach the true basin, which then wins on plain surface RMSE.

Skipped automatically when the gitignored CAD file is absent (CI without the data).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters import client_data
from case_prep.adapters import open3d_engine as engine
from case_prep.adapters.ingest import canonicalize_library
from case_prep.domain.geometry import Axis, RigidTransform
from case_prep.domain.metrics import axis_error_deg, position_error_mm
from case_prep.domain.poses import Retention

CAD = client_data.LEGACY_SHELF_CAD
pytestmark = pytest.mark.skipif(not CAD.exists(), reason="real vendor CAD not present (gitignored)")

_POSES = [  # near-vertical implants (small tilt) at varied clocking + position, like real cases
    (8, -6, 35, (2.0, -1.0, 3.0)),
    (-10, 5, 120, (-3.0, 2.0, -1.0)),
    (4, 9, 250, (1.0, 4.0, 0.5)),
    (-5, -8, 300, (0.0, -2.0, 2.0)),
    (12, 3, 80, (3.0, 1.0, -2.0)),
]


def _pose(tilt_x_deg, tilt_y_deg, clock_deg, t) -> RigidTransform:
    r = (
        RigidTransform.from_axis_angle([1, 0, 0], tilt_x_deg).rotation
        @ RigidTransform.from_axis_angle([0, 1, 0], tilt_y_deg).rotation
        @ RigidTransform.from_axis_angle([0, 0, 1], clock_deg).rotation
    )
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = np.asarray(t, float)
    return RigidTransform(m)


def _recover(local_mesh, pose, noise_mm, rng, retention=Retention.CEMENT):
    placed = local_mesh.copy()
    placed.vertices = pose.apply(np.asarray(local_mesh.vertices, float))
    pts, _ = trimesh.sample.sample_surface(placed, 4000)
    pts = np.asarray(pts, float)
    keep = rng.random(len(pts)) > (0.30 if noise_mm > 0 else 0.0)  # occlusion only on noisy scans
    pts = pts[keep] + rng.normal(0.0, noise_mm, (int(keep.sum()), 3))
    # This test guards REGISTER on the clean library part, so it builds the Localization directly
    # from the isolated body (no surrounding teeth). The real-arch ROI isolation that
    # localize_from_seed performs is guarded separately by tests/test_embedded_case.py.
    centroid = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - centroid, full_matrices=False)
    axis = vt[0] / np.linalg.norm(vt[0])
    if axis @ [0, 0, 1.0] < 0:
        axis = -axis
    proj = pts @ axis
    base = centroid + axis * (proj.min() - float(centroid @ axis))
    loc = engine.Localization(centroid, axis, base, pts)
    t_est, _ = engine.register(loc, local_mesh, retention)
    pos = position_error_mm(t_est.apply(np.zeros(3)), pose.apply(np.zeros(3)))
    axis = axis_error_deg(
        Axis.from_vector(t_est.rotation @ [0, 0, 1.0]),
        Axis.from_vector(pose.rotation @ [0, 0, 1.0]),
    )
    return pos, axis


def _run(noise_mm, seed=7):
    np.random.seed(seed)  # trimesh.sample_surface draws from the global RNG; pin it for determinism
    local, _ = canonicalize_library(trimesh.load(CAD, force="mesh"))
    rng = np.random.default_rng(seed)
    pos, axis = [], []
    for p in _POSES:
        pe, ae = _recover(local, _pose(*p), noise_mm, rng)
        pos.append(pe)
        axis.append(ae)
    return np.array(pos), np.array(axis)


@pytest.mark.parametrize(
    "noise_mm,max_pos_mm,max_axis_deg",
    [(0.0, 0.05, 3.0), (0.05, 0.10, 6.0)],
)
@pytest.mark.slow
def test_clean_library_recovers_to_clinical_tolerance(noise_mm, max_pos_mm, max_axis_deg):
    pos, axis = _run(noise_mm)
    assert np.median(pos) < max_pos_mm, f"median position {np.median(pos):.3f}mm (all={np.round(pos,3)})"
    assert np.median(axis) < max_axis_deg, f"median axis {np.median(axis):.2f}deg (all={np.round(axis,2)})"
