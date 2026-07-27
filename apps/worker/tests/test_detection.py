"""AUTOMATIC DETECTION FOR THE PRODUCT'S INTAKE — case_prep.application.detection.

Plan §4 Intake / §7 slice 4: a case opens INTO Intake and detection fires automatically;
capture-gate verdicts surface BEFORE any work is invested. This module is the THIRD
TRANCHE of the server.py lift (copy-debt ledger row 6): the demo's capture assembly +
propose orchestration (server.py:733-857), restated as deterministic functions over
``case_prep.pipeline``/``domain`` — no HTTP types, no serve-time caches, refusals raise.

Synthetic tests pin the RULES (the centre+radius precedence, the tooth-guess matching,
the refusal) on hand-built geometry — milliseconds, no meshes parsed beyond a byte-empty
refusal fixture. The full ``detect(case)`` walk needs a real scan and is real-tree +
slow-marked, exactly like the relief-ceiling read in test_application.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.detection import (CaptureContext, DetectionResult,
                                             FALLBACK_RIM_RADIUS_MM, ScanUnreadable,
                                             capture_context, detect,
                                             site_capture_inputs, tooth_guess_for)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")


def _identity_ctx(points_local: np.ndarray) -> CaptureContext:
    """A ctx whose local frame IS the world frame — precedence rules read directly."""
    return CaptureContext(frame=np.eye(3), origin=np.zeros(3),
                          local_points=points_local,
                          xy_tree=cKDTree(points_local[:, :2]))


def _sparse_cloud() -> np.ndarray:
    """Too sparse for measure_rim_diameter (< 60 ring points) — forces the fallback."""
    rng = np.random.default_rng(7)
    return rng.uniform(-10, 10, size=(30, 3))


class TestSiteCaptureInputs:
    """The centre+radius precedence, lifted verbatim from server.py's
    ``_site_capture_inputs``: border-circle fit > centre+rim marks > measured rim >
    the 2.6mm crop fallback. The pair is passed to the gate AS GIVEN — capture
    assessment never re-centres a human mark (the re-click pair-integrity record)."""

    def test_three_or_more_rim_points_win_with_a_fitted_circle(self):
        ctx = _identity_ctx(_sparse_cloud())
        angles = np.linspace(0, 2 * np.pi, 5)[:-1]
        rim_points = [[1.0 + 3.0 * np.cos(a), 2.0 + 3.0 * np.sin(a), 0.0]
                      for a in angles]
        centre_xy, rim_r = site_capture_inputs(
            ctx, center=[9.0, 9.0, 0.0], rim_points=rim_points)
        assert np.allclose(centre_xy, [1.0, 2.0], atol=1e-6)  # NOT the center argument
        assert rim_r == pytest.approx(3.0, abs=1e-6)

    def test_centre_mark_plus_rim_mark_give_the_human_pair_as_given(self):
        ctx = _identity_ctx(_sparse_cloud())
        centre_xy, rim_r = site_capture_inputs(
            ctx, center=[0.0, 0.0, 0.0],
            center_mark=[5.0, 5.0, 1.0], rim_mark=[8.0, 5.0, 1.0])
        assert np.allclose(centre_xy, [5.0, 5.0])  # the mark beats the detector centre
        assert rim_r == pytest.approx(3.0)

    def test_one_or_two_rim_points_average_the_radius_about_the_centre(self):
        ctx = _identity_ctx(_sparse_cloud())
        centre_xy, rim_r = site_capture_inputs(
            ctx, center=[1.0, 1.0, 0.0], rim_points=[[3.0, 1.0, 0.0], [1.0, 5.0, 0.0]])
        assert np.allclose(centre_xy, [1.0, 1.0])
        assert rim_r == pytest.approx((2.0 + 4.0) / 2.0)

    def test_no_marks_and_no_measurable_rim_fall_back_to_the_crop_radius(self):
        ctx = _identity_ctx(_sparse_cloud())
        centre_xy, rim_r = site_capture_inputs(ctx, center=[0.0, 0.0, 0.0])
        assert np.allclose(centre_xy, [0.0, 0.0])
        assert rim_r == FALLBACK_RIM_RADIUS_MM


class TestCaptureContext:
    def test_frame_is_right_handed_and_local_points_are_consistent(self):
        # A tilted plane of points with upward normals: whatever axis crown_up_axis
        # reads, the contract is an orthonormal RIGHT-HANDED frame (det=+1 — the
        # slice-3 mirror lesson) and local coords that invert back to world.
        rng = np.random.default_rng(3)
        pts = np.c_[rng.uniform(-20, 20, 400), rng.uniform(-20, 20, 400),
                    rng.normal(0, 0.1, 400)]
        normals = np.tile([0.0, 0.0, 1.0], (400, 1))
        ctx = capture_context(pts, normals)
        assert np.linalg.det(ctx.frame) == pytest.approx(1.0, abs=1e-9)
        assert np.allclose(ctx.frame.T @ ctx.frame, np.eye(3), atol=1e-9)
        back = ctx.local_points @ ctx.frame.T + ctx.origin
        assert np.allclose(back, pts, atol=1e-9)


class TestToothGuess:
    """NEW product logic (recorded as a divergence in ledger row 6): the demo's
    proposals carry no tooth — its operator assigns one at confirmation. Intake's site
    list is keyed by tooth, so a proposal near a CURATED suggested site inherits that
    tooth as a NON-BINDING guess; anywhere else it is honestly None (the lab chooses,
    the software never guesses — a guess is labelled a guess)."""

    SITES = ({"tooth": 4, "center": [0.0, 0.0, 0.0]},
             {"tooth": 13, "center": [10.0, 0.0, 0.0]})

    def test_a_proposal_near_a_curated_site_inherits_its_tooth(self):
        assert tooth_guess_for([1.0, 1.0, 0.5], self.SITES) == 4

    def test_the_nearest_curated_site_wins(self):
        assert tooth_guess_for([6.0, 0.0, 0.0], self.SITES) == 13

    def test_beyond_the_radius_there_is_no_guess(self):
        assert tooth_guess_for([50.0, 50.0, 0.0], self.SITES) is None

    def test_no_curated_sites_no_guess(self):
        assert tooth_guess_for([0.0, 0.0, 0.0], ()) is None

    def test_a_curated_site_without_a_center_cannot_anchor_a_guess(self):
        assert tooth_guess_for([0.0, 0.0, 0.0], ({"tooth": 4},)) is None


class TestDetectRefuses:
    def test_an_unreadable_scan_raises_with_a_human_sentence(self, tmp_path):
        empty = tmp_path / "scans" / "doctor-x" / "upper.stl"
        empty.parent.mkdir(parents=True)
        empty.touch()  # zero bytes -> trimesh yields an EMPTY mesh, not an arch
        case = CaseRecord(id="x", doctor="Doctor X", jaw="upper", scan=empty,
                          data_root=tmp_path, suggested_model=None,
                          suggested_construction=None)
        with pytest.raises(ScanUnreadable, match="upper.stl"):
            detect(case)


@real_only
@pytest.mark.slow  # parses the real scan and runs the detector end to end
class TestDetectOnTheRealTree:
    def test_the_shipped_case_detects_sites_with_capture_verdicts(self):
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        result = detect(case)
        assert isinstance(result, DetectionResult)
        assert len(result.proposals) >= 1
        for p in result.proposals:
            assert len(p.center) == 3
            assert p.capture["verdict"] in ("pass", "marginal", "rescan")
            assert len(p.capture["checks"]) == 3  # rim_arc, code_band, collar
        # the curated sites (teeth 4 and 13) each carry their own assessment
        assert [s.tooth for s in result.suggested] == [4, 13]
        for s in result.suggested:
            assert s.capture["verdict"] in ("pass", "marginal", "rescan")

    def test_detection_is_deterministic_given_the_case(self):
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        a, b = detect(case), detect(case)
        assert [p.center for p in a.proposals] == [p.center for p in b.proposals]
        assert [s.capture for s in a.suggested] == [s.capture for s in b.suggested]
