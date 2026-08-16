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
from case_prep.application.detection import (CaptureContext, CandidateEvidence,
                                             DetectedSite,
                                             DetectionResult, FALLBACK_RIM_RADIUS_MM,
                                             ScanUnreadable, SuggestedSiteCapture,
                                             candidate_evidence_for,
                                             capture_context, detect,
                                             jaw_from_crown_axis, measured_cap_height_mm,
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


class TestJawFromCrownAxis:
    """The measured convention (§10-AM): crown-up reads jaw-signed across the fleet --
    +z for a lower arch, -z for an upper one -- within a 60-degree cone of either pole.
    Outside that cone the reading is an honest ``None``, never a coin-flip guess (the
    tooth_guess_for discipline applied to the jaw). This is a SUGGESTION only: nothing
    here writes the declared jaw or touches scan bytes."""

    def test_a_z_aligned_crown_axis_reads_lower(self):
        assert jaw_from_crown_axis([0.0, 0.0, 1.0]) == "lower"

    def test_a_minus_z_crown_axis_reads_upper(self):
        assert jaw_from_crown_axis([0.0, 0.0, -1.0]) == "upper"

    def test_a_horizontal_axis_makes_no_claim(self):
        assert jaw_from_crown_axis([1.0, 0.0, 0.0]) is None

    def test_the_cone_boundary_is_inclusive_toward_lower(self):
        # z-component exactly cos(60deg) = 0.5 -- the >= boundary
        axis = [np.sqrt(1.0 - 0.5 ** 2), 0.0, 0.5]
        assert jaw_from_crown_axis(axis) == "lower"

    def test_the_cone_boundary_is_inclusive_toward_upper(self):
        axis = [np.sqrt(1.0 - 0.5 ** 2), 0.0, -0.5]
        assert jaw_from_crown_axis(axis) == "upper"

    def test_just_inside_the_cone_makes_no_claim(self):
        axis = [np.sqrt(1.0 - 0.49 ** 2), 0.0, 0.49]
        assert jaw_from_crown_axis(axis) is None


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


class TestCandidateEvidenceFor:
    """Stage-1 slice 1a (clinical-pipeline-plan.md): the discriminator evidence that
    justified a PROPOSAL must reach a CURATED site too, so Intake can say WHY —
    but only when the density stack actually found something there. The reverse
    of ``tooth_guess_for`` (there a proposal inherits a site's tooth; here a site
    borrows a proposal's numbers) with the same one-cap-width radius and the same
    honesty rule: a site the automatic pass never proposed (human-marked, or a
    recall miss) has no ring density to show, and a nearby but DISTINCT candidate's
    numbers are never borrowed in its place."""

    PROPOSALS = (
        DetectedSite(center=(0.0, 0.0, 0.0), void_ratio=0.10, rim_below_cusps_mm=6.0,
                    tooth_guess=None, capture={}),
        DetectedSite(center=(3.0, 0.0, 0.0), void_ratio=0.50, rim_below_cusps_mm=5.0,
                    tooth_guess=None, capture={}),
    )

    def test_a_curated_site_near_a_proposal_borrows_its_evidence(self):
        ev = candidate_evidence_for([0.5, 0.0, 0.0], self.PROPOSALS)
        assert ev.rim_below_cusps_mm == pytest.approx(6.0)
        assert ev.void_ratio == pytest.approx(0.10)

    def test_the_nearest_proposal_wins(self):
        ev = candidate_evidence_for([1.0, 0.0, 0.0], self.PROPOSALS)
        # 1.0mm from the first proposal, 2.0mm from the second -- the first wins
        assert ev.rim_below_cusps_mm == pytest.approx(6.0)
        assert ev.void_ratio == pytest.approx(0.10)

    def test_beyond_the_radius_there_is_no_evidence(self):
        assert candidate_evidence_for([50.0, 50.0, 0.0], self.PROPOSALS) == CandidateEvidence()

    def test_no_proposals_no_evidence(self):
        assert candidate_evidence_for([0.0, 0.0, 0.0], ()) == CandidateEvidence()

    def test_a_site_without_a_center_borrows_nothing(self):
        assert candidate_evidence_for(None, self.PROPOSALS) == CandidateEvidence()

    def test_a_matching_proposal_lends_density_prior_and_dp_fields(self):
        # P4.1: density_prior_used / DP gap / per-bearing margin ride the same
        # borrow as rim/void — a curated site the detector found gets the
        # proposal's own honesty numbers, never invented zeros.
        proposals = (
            DetectedSite(center=(0.0, 0.0, 0.0), void_ratio=0.10,
                         rim_below_cusps_mm=6.0, tooth_guess=None, capture={},
                         density_prior_used=True, dp_gap_fraction=0.25,
                         bearing_margin=(0.4, 0.1, 0.8)),
        )
        ev = candidate_evidence_for([0.2, 0.0, 0.0], proposals)
        assert ev.density_prior_used is True
        assert ev.dp_gap_fraction == pytest.approx(0.25)
        assert ev.bearing_margin == (0.4, 0.1, 0.8)

    def test_no_match_is_honest_none_never_false_or_zero(self):
        ev = candidate_evidence_for([50.0, 50.0, 0.0], self.PROPOSALS)
        assert ev.density_prior_used is None
        assert ev.dp_gap_fraction is None
        assert ev.bearing_margin is None


class TestSuggestedSiteCaptureEvidenceFields:
    """1a: the fields default to None -- an old persisted detection record (written
    before this slice) still constructs the dataclass unchanged, the same
    additivity ``measured_rim_diameter_mm`` already relies on -- and round-trip the
    given value otherwise."""

    def test_the_evidence_fields_default_to_none(self):
        site = SuggestedSiteCapture(tooth=4, center=(0.0, 0.0, 0.0), capture={})
        assert site.rim_below_cusps_mm is None
        assert site.void_ratio is None
        # P4.1 — additive curve-honesty fields: an old constructor still
        # builds, and absence is None (never False / 0.0 standing in).
        assert site.density_prior_used is None
        assert site.dp_gap_fraction is None
        assert site.bearing_margin is None

    def test_the_evidence_fields_round_trip_when_given(self):
        site = SuggestedSiteCapture(tooth=4, center=(0.0, 0.0, 0.0), capture={},
                                    rim_below_cusps_mm=6.1, void_ratio=0.12,
                                    density_prior_used=False, dp_gap_fraction=0.18,
                                    bearing_margin=(0.2, 0.05))
        assert site.rim_below_cusps_mm == pytest.approx(6.1)
        assert site.void_ratio == pytest.approx(0.12)
        assert site.density_prior_used is False
        assert site.dp_gap_fraction == pytest.approx(0.18)
        assert site.bearing_margin == (0.2, 0.05)

    def test_detected_site_curve_fields_default_without_inventing_a_prior(self):
        # A proposal always has a density_prior_used bool (False when the
        # informativeness gate was off). DP fields stay None until island ran.
        site = DetectedSite(center=(0.0, 0.0, 0.0), void_ratio=0.1,
                            rim_below_cusps_mm=0.5, tooth_guess=None, capture={})
        assert site.density_prior_used is False
        assert site.dp_gap_fraction is None
        assert site.bearing_margin is None


class TestMeasuredCapHeight:
    """The missing second axis (client escalation 2026-08-09, cap
    297589851-neodent-gm tooth 20): detection measured the rim DIAMETER per site
    and nothing about HEIGHT, so nothing could catch a TALL variant declared over a
    visibly SHORT cap. Reuses the capture gate's own collar reading rather than a
    new sampler — the site's height and its capture verdict can never disagree
    about where the collar sits."""

    def _known_cap(self, collar_z: float, apex_h: float, footprint_r: float = 2.5):
        """A flat sheet plus a KNOWN cap: a level ring of points at ``collar_z``
        (the collar) and one point at the true apex, ``apex_h`` above it — both
        within ``footprint_r`` of the origin, so the expected reading is exact."""
        rng = np.random.default_rng(4)
        ring = np.array([[footprint_r * 0.9 * np.cos(a), footprint_r * 0.9 * np.sin(a),
                          collar_z]
                         for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)])
        filler = np.c_[rng.uniform(-1, 1, 30), rng.uniform(-1, 1, 30),
                       np.full(30, collar_z + apex_h * 0.6)]
        apex = np.array([[0.0, 0.0, collar_z + apex_h]])
        sheet = np.c_[rng.uniform(-20, 20, 100), rng.uniform(-20, 20, 100),
                      np.zeros(100)]  # surrounding tissue, well outside the footprint
        return _identity_ctx(np.vstack([ring, filler, apex, sheet]))

    def test_a_known_cap_measures_exactly_its_own_height_above_the_collar(self):
        ctx = self._known_cap(collar_z=0.5, apex_h=2.1)
        height = measured_cap_height_mm(ctx, [0.0, 0.0], 2.5, collar_z=0.5)
        assert height == pytest.approx(2.1, abs=1e-9)

    def test_a_taller_known_cap_measures_taller(self):
        ctx = self._known_cap(collar_z=0.5, apex_h=4.3)
        height = measured_cap_height_mm(ctx, [0.0, 0.0], 2.5, collar_z=0.5)
        assert height == pytest.approx(4.3, abs=1e-9)

    def test_no_collar_reading_means_no_height(self):
        # the same starved-site refusal assess_capture already gives (rim_z=None)
        ctx = self._known_cap(collar_z=0.5, apex_h=2.1)
        assert measured_cap_height_mm(ctx, [0.0, 0.0], 2.5, collar_z=None) is None

    def test_a_footprint_with_too_few_points_is_unmeasurable(self):
        # a footprint radius so small it excludes everything but the lone apex point
        ctx = self._known_cap(collar_z=0.5, apex_h=2.1)
        assert measured_cap_height_mm(ctx, [0.0, 0.0], 0.01, collar_z=0.5) is None

    def test_a_non_positive_reading_is_never_served(self):
        # the footprint's own top does not clear the collar it sits on — noise, not
        # a cap; never guessed at as a height
        ctx = self._known_cap(collar_z=2.0, apex_h=2.1)
        assert measured_cap_height_mm(ctx, [0.0, 0.0], 2.5, collar_z=5.0) is None


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
            # honest types on real geometry: a float or None, never a guess wearing
            # a number's clothes — see TestMeasuredCapHeight for the geometry pin
            assert s.measured_cap_height_mm is None or s.measured_cap_height_mm > 0.0
            assert s.proposed_variant is None or isinstance(s.proposed_variant, str)
            # 1a: a curated site the detector also proposed borrows that proposal's
            # own discriminator evidence -- honestly None when it never proposed one
            assert s.rim_below_cusps_mm is None or isinstance(s.rim_below_cusps_mm, float)
            assert s.void_ratio is None or isinstance(s.void_ratio, float)
            # P4.1: False is a real "prior off"; None is honest absence
            assert s.density_prior_used is None or isinstance(s.density_prior_used, bool)
            assert s.dp_gap_fraction is None or isinstance(s.dp_gap_fraction, float)
            assert s.bearing_margin is None or isinstance(s.bearing_margin, tuple)
        assert len(result.crown_axis) == 3
        assert result.jaw_reading in (None, "upper", "lower")

    def test_detection_is_deterministic_given_the_case(self):
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        a, b = detect(case), detect(case)
        assert [p.center for p in a.proposals] == [p.center for p in b.proposals]
        assert [s.capture for s in a.suggested] == [s.capture for s in b.suggested]
        assert ([s.measured_cap_height_mm for s in a.suggested]
                == [s.measured_cap_height_mm for s in b.suggested])
        assert ([s.proposed_variant for s in a.suggested]
                == [s.proposed_variant for s in b.suggested])
        assert ([s.rim_below_cusps_mm for s in a.suggested]
                == [s.rim_below_cusps_mm for s in b.suggested])
        assert ([s.void_ratio for s in a.suggested]
                == [s.void_ratio for s in b.suggested])
        assert ([s.density_prior_used for s in a.suggested]
                == [s.density_prior_used for s in b.suggested])
        assert ([s.dp_gap_fraction for s in a.suggested]
                == [s.dp_gap_fraction for s in b.suggested])
        assert ([s.bearing_margin for s in a.suggested]
                == [s.bearing_margin for s in b.suggested])


@real_only
@pytest.mark.slow  # parses the real scan and runs the detector end to end
class TestMeasuredHeightOnTheEscalationCase:
    """The client escalation itself (2026-08-09): case 297589851-neodent-gm tooth 20
    served ``suggested_variant: None`` with NO height fact behind it at all, an
    operator declared the SUPERSEDED, TALL ``superseded-2026-07-13--5030`` over a
    visibly SHORT cap, and the preview seated a 5.4mm barrel onto a ~3.4mm cap (DEV
    RMS 2.065).

    This pins the fix's HONESTY on the real regression scan, not a guess at its
    outcome: the site now carries a real, positive height reading where the old
    code measured nothing — but the diameter this scan reads (a documented
    characteristic of THIS data: marks/rim are cut from the VISIBLE, submerged rim,
    which under-reads a cap's native size — sites.json's own note) sits within
    ``classify_diameter``'s own honesty margin of two rival Ø classes on the
    CURRENT neodent-gm shelf, so the proposal correctly REFUSES rather than pick a
    family by coin flip. None is still strictly better than the old silence: the
    height fact now on the wire is real evidence an operator can weigh, where
    before there was nothing to catch the mismatch at all."""

    def test_tooth_20_carries_a_real_height_and_refuses_to_guess_the_family(self):
        case = next(c for c in discover_cases(REAL) if c.id == "297589851-neodent-gm")
        result = detect(case)
        (site,) = result.suggested
        assert site.tooth == 20
        assert site.measured_cap_height_mm is not None
        assert site.measured_cap_height_mm > 0.0
        assert site.proposed_variant is None
        # the SUPERSEDED variant the operator was driven to declare must never be
        # what this catalog-current-shelf proposal could answer, even by accident
        assert site.proposed_variant != "5030"


@real_only
@pytest.mark.slow  # parses the real scan and derives the crown axis
class TestJawReadingOnTheRealTree:
    """§10-AM's one real catch: this case's scan filename carries no "lower", so
    ``discover_cases`` defaults its jaw to "upper" -- but the geometry itself, read
    off the crowns' own axis, says "lower". This is the gap the cross-check exists
    to close (never silently correct -- surface the contradiction and let the
    operator fix it in one click).

    The fixture case was RETIRED from ``data/real/scans`` on 2026-08-15 (the
    rehearse-gate resolution, 3f22e12: the client's upload experiments moved to
    ``scans-retired`` so the frozen demo's gate stops flagging them). The
    geometry that makes this pin valuable still exists there, so the test
    builds a one-case data root around the retired folder and runs the SAME
    discovery path -- it skips only if the retired tree itself is ever gone."""

    def test_the_arch_upload_geometry_reads_lower_though_its_filename_says_upper(self, tmp_path):
        retired = REAL / "scans-retired" / "297589851-neodent-gm-arch-with-healingcaps"
        if not retired.is_dir():
            pytest.skip("retired upload-experiment case not present")
        root = tmp_path / "root"
        (root / "scans").mkdir(parents=True)
        (root / "scans" / retired.name).symlink_to(retired)
        (root / "library").symlink_to(REAL / "library")
        case = next(c for c in discover_cases(root)
                   if c.id == "297589851-neodent-gm-arch-with-healingcaps")
        assert case.jaw == "upper"  # the filename heuristic's wrong default
        result = detect(case)
        assert result.jaw_reading == "lower"
