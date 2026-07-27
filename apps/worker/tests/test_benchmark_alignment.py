"""Fast unit tests for the offline alignment-strategy benchmark (research code
only — never imported by production). No full-protocol runs here; those are
driven by ``tools/benchmark_alignment.py`` directly.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh
from scipy.spatial.transform import Rotation

from case_prep.research.benchmark_strategies import (delta_to_pose, gnc_circle_fit,
                                                      pose_to_delta,
                                                      s3_dense_constrained_search)


def _plane_tilt_deg(n: np.ndarray) -> float:
    """Angle (deg) between a fitted plane normal and the true +z axis."""
    n = n / np.linalg.norm(n)
    return float(np.degrees(np.arccos(np.clip(abs(n[2]), -1.0, 1.0))))


def _plain_lsq_plane_normal(P: np.ndarray) -> np.ndarray:
    c0 = P.mean(axis=0)
    _, _, vt = np.linalg.svd(P - c0, full_matrices=False)
    n = vt[2] / np.linalg.norm(vt[2])
    if n[2] < 0:
        n = -n
    return n


class TestGncCircleFit:
    """Survey candidate 1 (section 3(a)): a Geman-McClure IRLS robust circle fit
    should anneal one outlier click toward zero weight instead of letting it
    tilt the fitted plane — the exact failure mode measured in production
    (0.89mm-out click, 12-degree tilt, see auto_flow._fit_circle_3d docstring)."""

    def _ring(self, n_clicks: int = 8, r: float = 2.4) -> np.ndarray:
        theta = np.linspace(0, 2 * np.pi, n_clicks, endpoint=False)
        pts = np.c_[r * np.cos(theta), r * np.sin(theta), np.zeros(n_clicks)]
        return pts

    def test_one_outlier_click_gnc_stays_flat_plain_lsq_tilts(self):
        pts = self._ring()
        pts_outlier = pts.copy()
        pts_outlier[0, 2] += 1.0  # one click pushed 1.0mm out of plane

        _centre, n_gnc, _r, w = gnc_circle_fit(pts_outlier)
        n_lsq = _plain_lsq_plane_normal(pts_outlier)

        tilt_gnc = _plane_tilt_deg(n_gnc)
        tilt_lsq = _plane_tilt_deg(n_lsq)

        assert tilt_gnc < 3.0, f"GNC plane tilted {tilt_gnc:.2f} deg (expected < 3)"
        # NOTE: measured plain-LSQ tilt for this exact 8-click/r=2.4/1.0mm-push
        # configuration is 6.11 deg, not >8 deg as a first-principles estimate might
        # suggest — 1/8 of a click's z-error splits across all 8 points' plane fit,
        # so the achievable adversarial tilt at n=8 is lower than at production's
        # measured n=4 case (12 deg at the same 1.0mm push, see
        # auto_flow._fit_circle_3d's docstring). The >8deg wording in the task brief
        # does not hold empirically for n=8; this asserts what the geometry actually
        # produces (still a clearly non-trivial tilt) and lets GNC's contrast do the
        # work: GNC recovers to near-zero, plain LSQ does not.
        assert tilt_lsq > 5.0, f"plain LSQ plane only tilted {tilt_lsq:.2f} deg (expected > 5, " \
            "sanity check that the synthetic outlier is actually adversarial)"
        assert tilt_gnc < tilt_lsq / 2.0, \
            "GNC must recover a substantially flatter plane than plain LSQ"
        # the outlier click should be the most down-weighted of the eight
        assert int(np.argmin(w)) == 0

    def test_clean_ring_both_agree(self):
        pts = self._ring()
        _centre, n_gnc, _r, _w = gnc_circle_fit(pts)
        n_lsq = _plain_lsq_plane_normal(pts)

        tilt_gnc = _plane_tilt_deg(n_gnc)
        tilt_lsq = _plane_tilt_deg(n_lsq)

        assert tilt_gnc < 0.5, f"GNC plane tilted {tilt_gnc:.4f} deg on a clean ring"
        assert tilt_lsq < 0.5, f"plain LSQ plane tilted {tilt_lsq:.4f} deg on a clean ring"

    def test_recovers_known_radius_on_clean_ring(self):
        pts = self._ring(r=2.4)
        _centre, _n, r, _w = gnc_circle_fit(pts)
        assert abs(r - 2.4) < 1e-6


class TestPoseDeltaRoundTrip:
    """The 6-DoF delta parameterization (rotvec axis-angle + translation) used
    to bound S2's trust-region search must round-trip: apply a delta to a base
    pose, then recover the same delta from the resulting pose."""

    def test_round_trips_random_deltas(self):
        rng = np.random.default_rng(0)
        base = np.eye(4)
        base[:3, :3] = Rotation.from_euler("xyz", [12.0, -7.0, 30.0],
                                           degrees=True).as_matrix()
        base[:3, 3] = [1.5, -2.0, 0.4]

        for _ in range(20):
            rotvec = rng.normal(0, 0.1, 3)  # small angles, radians
            t = rng.normal(0, 1.0, 3)
            delta = np.concatenate([rotvec, t])

            pose = delta_to_pose(delta, base)
            recovered = pose_to_delta(pose, base)

            assert np.allclose(recovered, delta, atol=1e-8), \
                f"round-trip failed: {delta} -> {recovered}"

    def test_zero_delta_is_identity_on_base(self):
        base = np.eye(4)
        base[:3, :3] = Rotation.from_euler("xyz", [5.0, 10.0, -15.0],
                                           degrees=True).as_matrix()
        base[:3, 3] = [0.3, 0.6, 1.1]
        pose = delta_to_pose(np.zeros(6), base)
        assert np.allclose(pose, base, atol=1e-10)


class TestS3DenseConstrainedSearch:
    """Survey candidate 3 (section 3(b)/(c)): a dense grid search over the
    residual DoF (tilt cone x axial height) around a seed pose must recover a
    known tilt+height offset on a synthetic squat cap, since the grid brackets
    the true optimum by construction (no local-minimum escape needed)."""

    def _cap(self) -> trimesh.Trimesh:
        # mirrors tests/test_auto_flow.py TestBestFitRefinement._cap
        cyl = trimesh.creation.cylinder(radius=4.0, height=3.5, sections=48)
        keep = cyl.triangles_center[:, 2] > -3.5 * 0.49
        cap = trimesh.Trimesh(cyl.vertices.copy(), cyl.faces[keep], process=False)
        cap.remove_unreferenced_vertices()
        v = np.asarray(cap.vertices, float).copy()
        top = v[:, 2] > 3.5 * 0.49
        v[top, 2] += 1.2 * (1.0 - (np.linalg.norm(v[top, :2], axis=1) / 4.0) ** 2)
        return trimesh.Trimesh(v, cap.faces.copy(), process=False)

    def test_recovers_known_tilt_and_height_offset(self):
        cap = self._cap()
        np.random.seed(0)

        truth = np.eye(4)
        tilt_true = Rotation.from_rotvec(np.radians(6.0) * np.array([1.0, 0.0, 0.0]))
        truth[:3, :3] = tilt_true.as_matrix()
        truth[:3, 3] = [0.0, 0.0, 0.75]

        sampled, _ = trimesh.sample.sample_surface(cap, 1500)
        patch = np.asarray(sampled, float) @ truth[:3, :3].T + truth[:3, 3]
        # visible-shell patch only (a scan never sees the underside)
        patch = patch[patch[:, 2] > truth[2, 3] - 0.5]

        # synthetic clicks: a ring of border points at the cap's native rim radius,
        # posed by the SAME truth transform, feeding a circle-only seed pose
        theta = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        clicks_template = np.c_[4.0 * np.cos(theta), 4.0 * np.sin(theta), np.zeros(8)]
        clicks_local = clicks_template @ truth[:3, :3].T + truth[:3, 3]

        seed_pose = np.eye(4)  # deliberately un-tilted, un-shifted seed: the grid
        # must find the offset from scratch within its +-9deg / +-1.5mm window

        result = s3_dense_constrained_search(patch, clicks_local, cap,
                                             seed_pose=seed_pose)
        assert result.pose is not None

        axis_true = truth[:3, :3] @ np.array([0.0, 0.0, 1.0])
        axis_found = result.pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
        tilt_err_deg = float(np.degrees(np.arccos(
            np.clip(axis_true @ axis_found, -1.0, 1.0))))
        height_err_mm = abs(float(result.pose[2, 3]) - 0.75)

        assert tilt_err_deg < 3.0, f"tilt error {tilt_err_deg:.2f} deg (expected < 3)"
        assert height_err_mm < 0.4, f"height error {height_err_mm:.2f} mm (expected < 0.4)"
