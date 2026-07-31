"""THE FOUR ADJUST TOOLS — case_prep.application.adjust (plan §4 Adjust / §7 slice 6).

The demo's operator-rework endpoints lifted as refusal-raising calls (copy-debt ledger
row 5; server.py:1268-2244), plus the one piece of genuinely new physics in the lift:
the TWO-POINT SPAN (plan §5, client ask 2026-07-26).

Two lanes, deliberately:

  - THE SPAN MATHS and every VALIDATION refusal are pure and synthetic — hand-computed
    angles, milliseconds, no mesh parsed. That is where the new physics lives, so that
    is where it is pinned hardest: a span and an equivalent single centre point must
    agree on the midpoint observation EXACTLY (the span is an addition, never a
    re-interpretation of the existing circular mean), and a chordal span's direction
    must drop out with its reason rather than poison the fit.
  - THE ADOPTION PATH needs a real shipped run (a scan, a library template, the
    pipeline's own kinematics), so it is slow-marked and skips when the warmed product
    run is absent. It runs against a COPY of that run directory: an adjustment rewrites
    the site record in place, and a test may not mutate a warmed run.

The gate-refusal branch is not fakeable and is not faked: the real-data test accepts
EITHER outcome and asserts the invariant that must hold in both — an applied
adjustment leaves the proof, the record and the manifest updated; a refused one leaves
every byte exactly where it was.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from case_prep.application.adjust import (MIN_SPAN_MM, SPAN_RADIAL_TOLERANCE_DEG,
                                          STALE_AFTER_REWORK, AdjustInvalid,
                                          AdjustRefused, AlreadyOptimal, Correspondence,
                                          SiteClicks, align_to_correspondence,
                                          align_to_mark, anchor_certified_pose,
                                          azimuth_deg, best_fit_refusal, best_fit_site,
                                          circular_mean_deg, clock_landmarks,
                                          clock_reference, direction_delta,
                                          landmark_point, load_site, observation_weight,
                                          observations_for, rederived_reading,
                                          require_clock_lever, reset_discards,
                                          reset_target, residual_rows, rotate_site,
                                          seated_payload, site_clicks, span_readings,
                                          validate_span)
from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.domain.part_features import (MIN_LEVER_ARM_MM, PartFeature)
from case_prep.domain.clock_signature import (canon_point_to_world,
                                              template_signature, wrap_deg)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
PRODUCT = Path(__file__).resolve().parents[1] / "reports" / "product"
WARMED_CASE = "295811960-neodent-gm"
WARMED_RUN = PRODUCT / WARMED_CASE / "runs" / "20260728-224101-47bb54"
WARMED_TOOTH = 29

warmed_only = pytest.mark.skipif(
    not (REAL / "library").is_dir() or not WARMED_RUN.is_dir(),
    reason="real data tree / warmed product run not present")


def _case(tmp_path: Path) -> CaseRecord:
    return CaseRecord(
        id="case-x", doctor="Doctor X", jaw="upper",
        scan=tmp_path / "scan.stl", data_root=tmp_path,
        suggested_model=None, suggested_construction=None, suggested_sites=())


# --- the span maths: hand-computed, no mesh anywhere -------------------------------------

class TestAzimuth:
    def test_azimuth_is_ccw_about_the_given_centre(self):
        assert azimuth_deg((1.0, 0.0), (0.0, 0.0)) == pytest.approx(0.0)
        assert azimuth_deg((0.0, 2.0), (0.0, 0.0)) == pytest.approx(90.0)
        assert azimuth_deg((-3.0, 0.0), (0.0, 0.0)) == pytest.approx(180.0)

    def test_the_centre_is_honoured_not_assumed_to_be_the_origin(self):
        # the measured rim centre is never (0,0) on a real scan; a reading about the
        # wrong centre is the whole class of bug this argument exists to prevent
        assert azimuth_deg((2.0, 1.0), (1.0, 1.0)) == pytest.approx(0.0)


class TestCanonPointToWorld:
    """plan §10-F: composing a canonical-frame point (``scan_rim_centre``'s own xy, at
    a template's ``ztop``) through a WORLD pose — the exact operation that exposes the
    scan-side lever guard's measured rim centre without changing what the guard
    measures. Hand-computed: no mesh, no scan, just the linear algebra the domain
    function performs."""

    def test_an_identity_rotation_only_translates(self):
        pose = np.eye(4)
        pose[:3, 3] = [1.0, 2.0, 3.0]
        world = canon_point_to_world((5.0, -2.0), 0.75, pose)
        assert world == pytest.approx([6.0, 0.0, 3.75])

    def test_a_quarter_turn_about_z_rotates_the_canonical_x_axis_onto_world_y(self):
        # pose columns are the WORLD images of the canon x/y/z axes (canon->world);
        # a 90deg CCW turn about z sends canon +x to world +y, by hand
        pose = np.eye(4)
        pose[:3, :3] = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        world = canon_point_to_world((1.0, 0.0), 0.0, pose)
        assert world == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)

    def test_z_composes_through_the_poses_own_axis_column(self):
        pose = np.eye(4)
        pose[:3, :3] = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
        pose[:3, 3] = [0.0, 0.0, 10.0]
        world = canon_point_to_world((0.0, 0.0), 2.0, pose)
        assert world == pytest.approx([0.0, 0.0, 12.0])

    def test_the_composition_inverts_exactly_recovering_the_canonical_point(self):
        """THE FRAME PROOF this module exists for: composing a canonical point through
        a pose and then reading it back through that SAME pose's inverse (its
        transpose — a pose's rotation is orthonormal by construction, see
        ``_crowns_frame``'s right-handed-frame note) must recover the exact xy/z it
        started from. A wrong composition would still look plausible here — this is
        why the real-data round trip below (against ``require_clock_lever``'s own
        computed radius) is the test that actually proves the exposure is correct."""
        rng = np.random.default_rng(2026_07_29)
        for _ in range(20):
            axis = rng.normal(size=3)
            axis /= np.linalg.norm(axis)
            theta = rng.uniform(-np.pi, np.pi)
            k = np.array([[0.0, -axis[2], axis[1]],
                          [axis[2], 0.0, -axis[0]],
                          [-axis[1], axis[0], 0.0]])
            rot = np.eye(3) + np.sin(theta) * k + (1 - np.cos(theta)) * (k @ k)
            pose = np.eye(4)
            pose[:3, :3] = rot
            pose[:3, 3] = rng.normal(size=3) * 5.0
            xy = rng.normal(size=2) * 3.0
            z = float(rng.normal() * 2.0)
            world = canon_point_to_world(xy, z, pose)
            recovered = pose[:3, :3].T @ (world - pose[:3, 3])
            assert recovered[:2] == pytest.approx(xy, abs=1e-9)
            assert recovered[2] == pytest.approx(z, abs=1e-9)


class TestSpanReadings:
    """Hand-computed: a radial span along +x, the same span rotated a quarter turn,
    and a chord across it."""

    def test_a_radial_span_reads_its_own_azimuth_as_its_direction(self):
        r = span_readings((1.0, 0.0), (3.0, 0.0), (0.0, 0.0))
        assert r.midpoint_azimuth_deg == pytest.approx(0.0)
        assert r.direction_deg == pytest.approx(0.0)
        assert r.radial_offset_deg == pytest.approx(0.0)

    def test_a_quarter_turn_rotates_both_readings_together(self):
        r = span_readings((0.0, 1.0), (0.0, 3.0), (0.0, 0.0))
        assert r.midpoint_azimuth_deg == pytest.approx(90.0)
        assert r.direction_deg == pytest.approx(90.0)
        # the radial offset is ROTATION-INVARIANT — that is what makes it a usable
        # test of the model rather than another unknown
        assert r.radial_offset_deg == pytest.approx(0.0)

    def test_a_span_is_undirected_so_click_order_cannot_change_the_reading(self):
        forward = span_readings((1.0, 0.0), (3.0, 0.0), (0.0, 0.0))
        backward = span_readings((3.0, 0.0), (1.0, 0.0), (0.0, 0.0))
        assert backward.direction_deg == pytest.approx(forward.direction_deg)
        assert backward.midpoint_azimuth_deg == pytest.approx(
            forward.midpoint_azimuth_deg)

    def test_a_chord_across_the_feature_reads_ninety_degrees_off_its_radius(self):
        # both ends of a HOLE's diameter: the midpoint is the hole's centre (the whole
        # value of the span), the direction names no clock angle
        r = span_readings((2.0, -1.0), (2.0, 1.0), (0.0, 0.0))
        assert r.midpoint_azimuth_deg == pytest.approx(0.0)
        assert abs(r.radial_offset_deg) == pytest.approx(90.0)
        assert abs(r.radial_offset_deg) > SPAN_RADIAL_TOLERANCE_DEG

    def test_a_span_and_a_single_click_at_its_midpoint_agree_exactly(self):
        """THE COMPATIBILITY PROMISE: the midpoint observation IS the existing
        single-point observation, computed at the averaged click. A span adds a second
        reading; it never re-interprets the first."""
        a, b, centre = (1.3, 0.4), (2.9, 1.6), (0.2, -0.1)
        midpoint = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        assert span_readings(a, b, centre).midpoint_azimuth_deg == pytest.approx(
            azimuth_deg(midpoint, centre))


class TestDirectionDelta:
    """The direction is precise but only modulo a half-turn; the midpoint is
    unambiguous. The disambiguation is the division of labour between them."""

    def test_the_representative_nearest_the_midpoint_wins(self):
        assert direction_delta(100.0, 10.0, 88.0) == pytest.approx(90.0)
        assert direction_delta(100.0, 10.0, -88.0) == pytest.approx(-90.0)

    def test_an_aligned_span_asks_for_no_rotation(self):
        assert direction_delta(30.0, 30.0, 0.5) == pytest.approx(0.0)


class TestCircularMean:
    def test_the_mean_crosses_the_seam_a_plain_average_would_break(self):
        # an arithmetic mean of 170 and -170 is 0 — the exact opposite of the truth
        assert abs(circular_mean_deg([170.0, -170.0])) == pytest.approx(180.0)

    def test_one_observation_is_its_own_mean(self):
        assert circular_mean_deg([-17.5]) == pytest.approx(-17.5)


class TestSpanValidation:
    def test_coincident_clicks_are_refused_in_words(self):
        with pytest.raises(AdjustInvalid) as exc:
            validate_span([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], "trench-01", 8.0)
        assert "no direction to read" in str(exc.value)
        assert f"{MIN_SPAN_MM:.1f}mm" in str(exc.value)

    def test_a_span_longer_than_the_cap_is_refused_in_words(self):
        with pytest.raises(AdjustInvalid) as exc:
            validate_span([0.0, 0.0, 0.0], [20.0, 0.0, 0.0], "trench-01", 8.0)
        assert "longer than the cap itself" in str(exc.value)

    def test_a_non_finite_end_is_refused(self):
        with pytest.raises(AdjustInvalid) as exc:
            validate_span([0.0, 0.0, 0.0], [math.inf, 0.0, 0.0], "trench-01", 8.0)
        assert "non-finite" in str(exc.value)

    def test_a_two_coordinate_end_is_refused(self):
        with pytest.raises(AdjustInvalid):
            validate_span([0.0, 0.0, 0.0], [2.0, 0.0], "trench-01", 8.0)

    def test_a_valid_span_returns_its_length(self):
        assert validate_span([0.0, 0.0, 0.0], [3.0, 4.0, 0.0], "t", 8.0) == \
            pytest.approx(5.0)


# --- THE SCAN-SIDE LEVER ARM (review 2026-07-28, finding A) ------------------------------


class TestScanSideLeverArm:
    """The part half has refused an axis-hugging landmark since the annotator landed
    (``PartFeature.defines_rotation``). The SCAN half did not — and the screw access,
    the one feature an operator is most likely to span, sits ON the part axis."""

    def test_a_scan_mark_inside_the_lever_arm_names_the_axis(self):
        with pytest.raises(AdjustInvalid) as exc:
            require_clock_lever(0.21, "point-1", span=False)
        assert "names the axis, not a clock angle" in str(exc.value)
        assert f"{MIN_LEVER_ARM_MM}mm" in str(exc.value)

    def test_a_span_refusal_names_the_screw_access_and_what_to_span_instead(self):
        with pytest.raises(AdjustInvalid) as exc:
            require_clock_lever(0.08, "point-2", span=True)
        assert "SCREW ACCESS" in str(exc.value)
        assert "coded trench" in str(exc.value)

    def test_a_mark_out_on_the_coded_band_passes_and_returns_its_arm(self):
        assert require_clock_lever(2.0, "trench-01", span=False) == pytest.approx(2.0)

    def test_the_radiality_gate_alone_is_blind_at_the_axis(self):
        """WHY THE GUARD EXISTS AT ALL. A span across the axis-centred screw access is
        a diameter through the rim centre: its midpoint lands ON that centre, where
        ``azimuth_deg`` degenerates and the radial offset reads a perfect 0° — the
        gate reports the most radial span it will ever see and hands the direction
        through. Only the LEVER ARM tells the two apart."""
        r = span_readings((-1.2, 0.0), (1.2, 0.0), (0.0, 0.0))
        assert abs(r.radial_offset_deg) == pytest.approx(0.0)      # blind
        assert abs(r.radial_offset_deg) < SPAN_RADIAL_TOLERANCE_DEG
        assert r.midpoint_lever_mm == pytest.approx(0.0)            # the discriminator

    def test_the_baseline_is_the_span_in_the_plane_the_direction_was_read_in(self):
        """A span running down the cap's WALL covers more click distance than it does
        clock arc. The weight must divide by the baseline the direction was actually
        read over, or a wall span would be trusted as though it were a long radial one.
        """
        r = span_readings((1.0, 0.0), (2.0, 0.0), (0.0, 0.0))
        assert r.baseline_mm == pytest.approx(1.0)

    def test_an_off_axis_hole_still_reads_as_the_chord_it_is(self):
        """The guard must not swallow the case the span was designed for: a hole OUT
        on the part still has a usable midpoint, and its diameter still reads chordal.
        """
        r = span_readings((2.0, -1.0), (2.0, 1.0), (0.0, 0.0))
        assert r.midpoint_lever_mm == pytest.approx(2.0)
        assert abs(r.radial_offset_deg) > SPAN_RADIAL_TOLERANCE_DEG


# --- THE OBSERVATION WEIGHTS (review 2026-07-28, finding B) ------------------------------


class TestObservationWeights:
    """Inverse variance, from one assumption (iid click noise) with the noise itself
    cancelling out. Equal weighting threw the averaged midpoint away by pairing it with
    an observation up to 2.6x noisier."""

    def test_a_single_click_is_weighted_by_its_lever_arm_squared(self):
        assert observation_weight("point", 2.0) == pytest.approx(4.0)
        assert observation_weight("point", 1.0) == pytest.approx(1.0)

    def test_a_span_midpoint_is_worth_two_single_clicks_at_the_same_radius(self):
        # averaging two clicks halves the positional variance — no more, no less
        assert observation_weight("midpoint", 2.0) == pytest.approx(
            2.0 * observation_weight("point", 2.0))

    def test_a_direction_earns_the_midpoints_weight_exactly_at_twice_the_radius(self):
        """The whole claim in one number: a span is worth its second click when it is
        as long as the diameter of the circle its midpoint sits on."""
        lever = 1.75
        assert observation_weight("direction", lever, span_length_mm=2.0 * lever) == \
            pytest.approx(observation_weight("midpoint", lever))

    def test_a_short_span_direction_is_worth_far_less_than_its_own_midpoint(self):
        # the measured fleet case: r 1.5->2.5, so lever 2.0 and length 1.0
        midpoint = observation_weight("midpoint", 2.0)
        direction = observation_weight("direction", 2.0, span_length_mm=1.0)
        assert direction < midpoint / 15.0

    def test_every_admissible_observation_carries_a_strictly_positive_weight(self):
        # the two floors that make this safe: the lever guard and MIN_SPAN_MM
        assert observation_weight("point", MIN_LEVER_ARM_MM) > 0.0
        assert observation_weight("direction", MIN_LEVER_ARM_MM,
                                  span_length_mm=MIN_SPAN_MM) > 0.0

    def test_an_unknown_observation_kind_is_a_programming_error_not_a_guess(self):
        with pytest.raises(KeyError):
            observation_weight("vibes", 2.0)

    def test_a_second_reading_can_never_make_the_answer_worse(self):
        """THE GUARANTEE THE WEIGHTS EXIST FOR. Under inverse variance the combined
        variance is 1/(w1+w2), which is below either reading's own for any positive
        pair — so a span's direction is a gain at best and free at worst. Under EQUAL
        weighting there is no such floor, and the measured span on a 1.8→2.9mm trench
        came out worse than a single centre click."""
        for lever, length in ((2.0, 1.0), (2.35, 1.1), (0.5, 1.0), (2.0, 4.0)):
            midpoint = observation_weight("midpoint", lever)
            direction = observation_weight("direction", lever, span_length_mm=length)
            combined_variance = 1.0 / (midpoint + direction)
            assert combined_variance < 1.0 / midpoint
            assert combined_variance < 1.0 / direction


class TestWeightedCircularMean:
    def test_equal_weights_reproduce_the_unweighted_mean_exactly(self):
        """DEMO PARITY, stated as a test: a coded cap's trenches all share one band
        radius, so their weights are equal and the lifted circular mean is untouched."""
        deltas = [12.0, -3.0, 7.5]
        assert circular_mean_deg(deltas, [4.0, 4.0, 4.0]) == pytest.approx(
            circular_mean_deg(deltas))

    def test_a_heavier_observation_pulls_the_mean_toward_itself(self):
        assert circular_mean_deg([0.0, 40.0], [9.0, 1.0]) < \
            circular_mean_deg([0.0, 40.0])

    def test_the_weighted_mean_still_crosses_the_seam(self):
        assert abs(circular_mean_deg([170.0, -170.0], [2.0, 2.0])) == \
            pytest.approx(180.0)

    def test_one_observation_is_its_own_mean_at_any_weight(self):
        """The COMMONEST fit is one pair, and its answer must be the demo's exactly: a
        single observation's weight scales both sums and cancels inside the atan2."""
        for weight in (0.25, 1.0, 8.0):
            assert circular_mean_deg([-17.5], [weight]) == pytest.approx(-17.5)

    def test_a_weight_per_observation_is_required_or_nothing_is_computed(self):
        with pytest.raises(ValueError):
            circular_mean_deg([1.0, 2.0], [1.0])


# --- one pair's observations, on an identity frame ---------------------------------------


class _FlatSite:
    """A site whose canonical frame IS the world frame: the click mapping becomes the
    identity, so every number below is hand-computable without parsing a mesh."""

    frame = np.eye(3)
    origin = np.zeros(3)
    pose_local = np.eye(4)


def _flat_clicks(centre_xy=(0.0, 0.0)) -> SiteClicks:
    return SiteClicks(context=_FlatSite(), rim_centre_xy=np.asarray(centre_xy, float))


class TestObservationsForOnePair:
    def test_a_single_point_pair_yields_one_observation_at_its_part_lever(self):
        audit: dict = {}
        obs = observations_for(
            Correspondence(scan_point=[2.0, 0.0, 0.0], part_point=[2.0, 0.0, 1.0]),
            "point-1", part_azimuth=-10.0, lever_mm=2.0, clicks=_flat_clicks(),
            max_span_mm=8.0, audit=audit)
        assert [o.kind for o in obs] == ["point"]
        assert obs[0].delta_deg == pytest.approx(10.0)
        assert obs[0].lever_mm == pytest.approx(2.0)
        assert obs[0].weight == pytest.approx(observation_weight("point", 2.0))
        assert obs[0].note is None

    def test_a_scan_click_on_the_axis_is_refused_like_a_part_landmark_there(self):
        with pytest.raises(AdjustInvalid) as exc:
            observations_for(
                Correspondence(scan_point=[0.1, 0.0, 0.0], part_point=[2.0, 0.0, 1.0]),
                "point-1", part_azimuth=0.0, lever_mm=2.0, clicks=_flat_clicks(),
                max_span_mm=8.0, audit={})
        assert "names the axis, not a clock angle" in str(exc.value)

    def test_a_radial_span_yields_two_observations_weighted_by_their_own_noise(self):
        audit: dict = {}
        obs = observations_for(
            Correspondence(scan_point=[1.5, 0.0, 0.0], scan_point_end=[2.5, 0.0, 0.0],
                           part_point=[2.0, 0.0, 1.0]),
            "point-1", part_azimuth=0.0, lever_mm=2.0, clicks=_flat_clicks(),
            max_span_mm=8.0, audit=audit)
        assert [o.kind for o in obs] == ["midpoint", "direction"]
        assert obs[0].weight == pytest.approx(observation_weight("midpoint", 2.0))
        assert obs[1].weight == pytest.approx(
            observation_weight("direction", 2.0, span_length_mm=1.0))
        assert audit["span"]["baseline_mm"] == pytest.approx(1.0)
        # FINDING C: both readings report their miss at the PART's own lever arm — the
        # arc the marked feature actually moves. Reporting the direction at its own
        # half-length made the noisiest observation read as the tidiest.
        assert obs[1].lever_mm == pytest.approx(obs[0].lever_mm)
        assert audit["span"]["direction_used"] is True

    def test_a_span_down_the_wall_is_weighted_by_its_in_plane_baseline(self):
        """The clicks are 1.9mm apart in space but only 1.0mm apart in the plane the
        direction is read in — weighting by the click distance would trust it 3.6x too
        much."""
        audit: dict = {}
        obs = observations_for(
            Correspondence(scan_point=[1.5, 0.0, 0.0],
                           scan_point_end=[2.5, 0.0, 1.615],
                           part_point=[2.0, 0.0, 1.0]),
            "point-1", part_azimuth=0.0, lever_mm=2.0, clicks=_flat_clicks(),
            max_span_mm=8.0, audit=audit)
        direction = next(o for o in obs if o.kind == "direction")
        assert audit["span"]["length_mm"] == pytest.approx(1.9, abs=1e-2)
        assert audit["span"]["baseline_mm"] == pytest.approx(1.0)
        assert direction.weight == pytest.approx(
            observation_weight("direction", 2.0, span_length_mm=1.0))

    def test_a_span_across_the_axis_is_refused_by_its_midpoints_lever(self):
        with pytest.raises(AdjustInvalid) as exc:
            observations_for(
                Correspondence(scan_point=[-1.2, 0.0, 0.0],
                               scan_point_end=[1.2, 0.0, 0.0],
                               part_point=[2.0, 0.0, 1.0]),
                "point-1", part_azimuth=0.0, lever_mm=2.0, clicks=_flat_clicks(),
                max_span_mm=8.0, audit={})
        assert "SCREW ACCESS" in str(exc.value)

    def test_a_chordal_span_drops_its_direction_and_says_so_on_the_row_itself(self):
        """FINDING (suites): the reason was written to disk and nowhere else. The
        operator spends a whole extra click to buy the rotational constraint — being
        given one observation without a word is exactly the silent no-op the doctrine
        forbids."""
        audit: dict = {}
        obs = observations_for(
            Correspondence(scan_point=[2.0, -1.0, 0.0], scan_point_end=[2.0, 1.0, 0.0],
                           part_point=[2.0, 0.0, 1.0]),
            "point-1", part_azimuth=0.0, lever_mm=2.0, clicks=_flat_clicks(),
            max_span_mm=8.0, audit=audit)
        assert [o.kind for o in obs] == ["midpoint"]
        assert audit["span"]["direction_used"] is False
        assert obs[0].note is not None
        assert "off its own radius" in obs[0].note
        assert obs[0].note == audit["span"]["direction_note"]


class TestResidualRows:
    def _obs(self, kind, delta, lever, weight, note=None):
        from case_prep.application.adjust import Observation
        return Observation(label="point-1", kind=kind, part_azimuth_deg=0.0,
                           observed_deg=delta, delta_deg=delta, lever_mm=lever,
                           weight=weight, note=note)

    def test_equal_angular_misses_read_as_equal_millimetres(self):
        """The QC number an operator judges by must not flatter the noisiest reading:
        two observations that disagree with the adopted rotation by the same angle
        miss the marked feature by the same arc."""
        rows, _rms = residual_rows(
            [self._obs("midpoint", 4.0, 2.0, 8.0),
             self._obs("direction", -4.0, 2.0, 0.5)], applied=0.0)
        assert rows[0]["residual_mm"] == pytest.approx(rows[1]["residual_mm"])

    def test_the_rows_carry_the_weight_that_produced_the_rotation(self):
        rows, _rms = residual_rows([self._obs("point", 0.0, 2.0, 4.0)], applied=0.0)
        assert rows[0]["weight"] == pytest.approx(4.0)

    def test_a_dropped_directions_reason_rides_on_the_row_the_operator_reads(self):
        rows, _rms = residual_rows(
            [self._obs("midpoint", 0.0, 2.0, 8.0, note="the span runs 47° off …")],
            applied=0.0)
        assert rows[0]["note"] == "the span runs 47° off …"

    def test_a_row_with_nothing_to_explain_carries_no_note_key(self):
        rows, _rms = residual_rows([self._obs("point", 0.0, 2.0, 4.0)], applied=0.0)
        assert "note" not in rows[0]


# --- RESET IS NOT A FREE ACT (review 2026-07-28, finding D) ------------------------------


def _moved_pose(dx: float = 0.4) -> list:
    m = np.eye(4)
    m[0, 3] = dx
    return m.tolist()


class TestAnchorCertifiedPose:
    """The anchor a Reset restores. ``best_fit_site`` reasoned about this ordering in
    a comment and nothing tested it (suites 2026-07-28) — and it cannot be tested on
    the warmed runs, whose certified poses are already optimal, so it is pinned where
    it actually lives."""

    def test_a_virgin_record_anchors_on_the_pose_the_pipeline_shipped(self):
        record = {"pose_matrix": np.eye(4).tolist()}
        assert np.allclose(anchor_certified_pose(record), np.eye(4))
        assert record["nudge"]["base_pose_matrix"] == np.eye(4).tolist()

    def test_the_captured_anchor_survives_the_caller_rewriting_the_pose(self):
        """THE WHOLE POINT OF CAPTURING FIRST: after the act overwrites pose_matrix the
        certified pose is gone from the record, and an anchor taken then would be the
        operator's own output — Reset would 'restore' what it was asked to undo."""
        record = {"pose_matrix": np.eye(4).tolist()}
        anchor_certified_pose(record)
        record["pose_matrix"] = _moved_pose()          # the act, re-emitting
        assert np.allclose(anchor_certified_pose(record), np.eye(4))

    def test_a_second_act_does_not_re_anchor_to_the_first_ones_result(self):
        record = {"pose_matrix": np.eye(4).tolist()}
        anchor_certified_pose(record)
        record["pose_matrix"] = _moved_pose(0.4)
        anchor_certified_pose(record)                  # a second tool
        record["pose_matrix"] = _moved_pose(0.9)
        assert np.allclose(anchor_certified_pose(record), np.eye(4))


class TestResetTarget:
    """Reset rewrites the cap STL, drops the site to ADJUSTED and retires the case's
    confirmation AND release. On a site nobody has touched it would pay that whole
    price to move the pose by 1.8e-15mm."""

    def test_a_site_still_on_the_certified_pose_has_nothing_to_reset(self):
        with pytest.raises(AdjustInvalid) as exc:
            reset_target({"pose_matrix": np.eye(4).tolist()})
        assert "nothing to reset" in str(exc.value)
        assert "already stands on the pipeline's certified pose" in str(exc.value)

    def test_a_rotated_site_can_be_reset(self):
        record = {"pose_matrix": _moved_pose(),
                  "nudge": {"cumulative_deg": 5.0,
                            "base_pose_matrix": np.eye(4).tolist()}}
        assert reset_target(record)["cumulative_deg"] == pytest.approx(5.0)

    def test_a_best_fitted_site_can_be_reset_although_it_rotated_by_nothing(self):
        """The guard reads the POSE, not the angle: a best-fit moves the part in 6 DoF
        and books no rotation at all, so a cumulative-degrees test would refuse the one
        reset with the most to undo."""
        record = {"pose_matrix": _moved_pose(),
                  "nudge": {"base_pose_matrix": np.eye(4).tolist()},
                  "best_fit": {"matching_diameter_mm": 0.6}}
        assert reset_target(record) is not None

    def test_a_site_already_reset_once_is_refused_a_second_time(self):
        """The anchor survives a reset (the acts are history), so the bookkeeping alone
        would wave this through — and pay a confirmation for another 1.8e-15mm."""
        record = {"pose_matrix": np.eye(4).tolist(),
                  "nudge": {"cumulative_deg": 0.0,
                            "base_pose_matrix": np.eye(4).tolist()}}
        with pytest.raises(AdjustInvalid):
            reset_target(record)

    def test_a_nudge_block_without_an_anchor_cannot_restore_anything(self):
        with pytest.raises(AdjustInvalid):
            reset_target({"pose_matrix": _moved_pose(),
                          "nudge": {"cumulative_deg": 5.0}})


class TestResetSaysWhatItDiscards:
    def test_a_rotation_only_reset_names_the_rotation(self):
        assert "+7.0° of operator rotation" in reset_discards({}, 7.0)

    def test_a_reset_after_a_best_fit_names_both_acts(self):
        words = reset_discards({"best_fit": {"matching_diameter_mm": 0.6}}, 5.0)
        assert "+5.0° of operator rotation" in words
        assert "Ø0.60mm" in words

    def test_a_best_fit_alone_is_not_described_as_a_rotation(self):
        words = reset_discards({"best_fit": {"matching_diameter_mm": 0.6}}, 0.0)
        assert "rotation" not in words
        assert "best-fit" in words


class TestBestFitRefusalsNameTheirDial:
    """server.py:2084-2090: the demo prefixed EVERY best-fit refusal with the dial it
    was refused at. Half the branches arrived as bare gate sentences after the lift."""

    def test_the_refusal_carries_the_matching_diameter_and_the_reason(self):
        exc = best_fit_refusal(0.6, "the top face would pull off the scan")
        assert isinstance(exc, AdjustRefused)
        assert str(exc) == ("best-fit at a 0.60mm matching diameter refused: the top "
                            "face would pull off the scan")

    def test_the_already_optimal_pass_is_not_dressed_as_one(self):
        # AlreadyOptimal is a PASS: it must never inherit the refusal's prefix
        assert not issubclass(AlreadyOptimal, type(None))
        assert "refused" not in str(AlreadyOptimal("already the best fit", 0.3, 0.6))


# --- WHAT AN ADJUSTMENT RE-DERIVES (review 2026-07-28, finding E) ------------------------


class TestRederivedReading:
    """The run row's numbers describe a pose. When a tool moves that pose, a row left
    alone describes a cap that is no longer there — and the confirmation seals it under
    a freshly derived hash, which gives a stale document a false air of freshness."""

    def test_the_deviation_scalars_come_off_the_panes_own_payload(self):
        """Same instrument, by construction: ``deviation_payload`` publishes the
        acceptance scalars from ``site_deviation_stats`` — literally the function the
        run row's own numbers came from — so the row and the pane can no longer
        disagree about the same cap."""
        assert rederived_reading({"stats": {"rms_mm": 0.231, "p90_mm": 0.371}}) == {
            "deviation_rms_mm": 0.231, "deviation_p90_mm": 0.371}

    def test_a_payload_with_no_scalars_re_derives_nothing_rather_than_zero(self):
        assert rederived_reading({"stats": {}}) == {"deviation_rms_mm": None,
                                                    "deviation_p90_mm": None}

    def test_the_metrics_that_cannot_be_re_derived_are_named_not_left_unsaid(self):
        assert "rim_agreement_mm" in STALE_AFTER_REWORK
        assert "guidance" in STALE_AFTER_REWORK

    def test_a_re_derived_metric_is_not_also_claimed_stale(self):
        assert "deviation_rms_mm" not in STALE_AFTER_REWORK
        assert "deviation_p90_mm" not in STALE_AFTER_REWORK


# --- the refusals that fire before any mesh is parsed ------------------------------------

class TestRefusalsBeforeAnyPhysics:
    """The refusal order runs cheapest-first, like the preview and the run: an
    impossible ask never costs a mesh parse."""

    def test_a_step_past_forty_five_degrees_is_refused_verbatim(self, tmp_path):
        with pytest.raises(AdjustInvalid) as exc:
            rotate_site(_case(tmp_path), tmp_path, 13, step_deg=46.0)
        assert "±45°" in str(exc.value)

    def test_a_non_finite_step_is_refused(self, tmp_path):
        with pytest.raises(AdjustInvalid):
            rotate_site(_case(tmp_path), tmp_path, 13, step_deg=float("nan"))

    def test_a_diameter_outside_the_operator_band_is_refused_verbatim(self, tmp_path):
        with pytest.raises(AdjustInvalid) as exc:
            best_fit_site(_case(tmp_path), tmp_path, 13, matching_diameter_mm=2.5)
        assert "matching_diameter_mm must be between 0.05 and 2.0mm" in str(exc.value)

    def test_no_pairs_is_refused_in_the_demos_sentence(self, tmp_path):
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_case(tmp_path), tmp_path, 13, [])
        assert "name at least one correspondence" in str(exc.value)

    def test_more_than_eight_pairs_is_refused(self, tmp_path):
        pairs = [Correspondence(scan_point=[0.0, 0.0, 0.0], feature_id=f"t-{i}")
                 for i in range(9)]
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_case(tmp_path), tmp_path, 13, pairs)
        assert "capped at 8 pairs" in str(exc.value)

    def test_one_feature_named_twice_is_refused(self, tmp_path):
        pairs = [Correspondence(scan_point=[0.0, 0.0, 0.0], feature_id="trench-01"),
                 Correspondence(scan_point=[1.0, 0.0, 0.0], feature_id="trench-01")]
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_case(tmp_path), tmp_path, 13, pairs)
        assert "named twice" in str(exc.value)

    def test_a_run_with_no_shipped_pose_for_the_tooth_refuses(self, tmp_path):
        with pytest.raises(AdjustInvalid) as exc:
            load_site(_case(tmp_path), tmp_path, 13)
        assert "no shipped pose" in str(exc.value)
        assert "nothing aligned to adjust" in str(exc.value)


# --- the adoption path, against a COPY of a warmed run -----------------------------------

@pytest.fixture
def warmed_run(tmp_path: Path) -> Path:
    """A private copy of the warmed product run: an adjustment rewrites the site
    record, the cap STL and the manifest IN PLACE, and a test may never mutate the
    warmed directory those bytes came from."""
    target = tmp_path / "run"
    shutil.copytree(WARMED_RUN, target)
    return target


def _real_case() -> CaseRecord:
    case = next((c for c in discover_cases(REAL) if c.id == WARMED_CASE), None)
    assert case is not None, f"{WARMED_CASE} is not in the real data tree"
    return case


def _fingerprint(run_dir: Path) -> dict:
    return {p.name: p.stat().st_size for p in sorted(run_dir.iterdir()) if p.is_file()}


@pytest.mark.slow
@warmed_only
class TestSeatedPayload:
    def test_the_shipped_pose_reads_as_the_panes_own_payload(self, warmed_run):
        payload = seated_payload(_real_case(), warmed_run, WARMED_TOOTH)
        # the SAME builder Declare's preview uses — one instrument, one scale
        assert payload["tooth"] == WARMED_TOOTH
        assert set(payload["pose"]) == {"axis", "x_axis", "origin"}
        assert payload["points"] and payload["faces"]
        assert len(payload["deviation_mm"]) == payload["n_points"]
        # ...but this colouring describes a SHIPPED pose, not a pre-run seat
        assert payload["preview"] is False
        # plan §10-F: the scan-side lever guard's own reference, beside the pose
        assert set(payload["clock_reference"]) == {"rim_centre", "min_lever_mm"}
        assert len(payload["clock_reference"]["rim_centre"]) == 3
        assert payload["clock_reference"]["min_lever_mm"] == MIN_LEVER_ARM_MM

    def test_reading_the_seated_pose_writes_nothing(self, warmed_run):
        before = _fingerprint(warmed_run)
        seated_payload(_real_case(), warmed_run, WARMED_TOOTH)
        assert _fingerprint(warmed_run) == before


@pytest.mark.slow
@warmed_only
class TestClockReferenceIsTheGuardsOwnQuantity:
    """plan §10-F: exposing the measured rim centre only matters if it is PROVABLY the
    same quantity ``require_clock_lever`` measures against — not a plausible-looking
    point a few millimetres off (this project has shipped exactly that kind of wrong
    number before: an axis estimator that read 26.9deg/48.3deg off, an occlusal proxy
    off by up to 42deg). Real fleet geometry, not a synthetic identity."""

    def test_the_payload_field_equals_the_guards_own_canonical_point_composed_through_the_pose(
            self, warmed_run):
        case = _real_case()
        ctx = load_site(case, warmed_run, WARMED_TOOTH)
        sig = template_signature(ctx.template)
        clicks = site_clicks(ctx, sig)
        pose_world = np.asarray(ctx.record["pose_matrix"], float)
        expected = canon_point_to_world(clicks.rim_centre_xy, sig.ztop, pose_world)

        payload = seated_payload(case, warmed_run, WARMED_TOOTH)
        assert payload["clock_reference"]["rim_centre"] == pytest.approx(
            expected.tolist(), abs=1e-5)
        # ``clock_reference`` (the function) is exactly what the payload carries —
        # pinned so the two cannot drift apart under a future edit
        assert clock_reference(ctx) == {
            "rim_centre": [round(float(v), 6) for v in expected],
            "min_lever_mm": MIN_LEVER_ARM_MM,
        }

    def test_the_exposed_reference_is_a_real_measurement_not_the_pose_origin_repeated(
            self, warmed_run):
        # the whole point of §10-F: pose.origin is close to the measured rim centre
        # but is not it (that gap is why the client could only WARN, never refuse)
        payload = seated_payload(_real_case(), warmed_run, WARMED_TOOTH)
        origin = np.array(payload["pose"]["origin"])
        rim = np.array(payload["clock_reference"]["rim_centre"])
        gap = float(np.linalg.norm(origin - rim))
        assert 0.0 < gap < 5.0, (
            f"expected a small but non-zero gap between the seat origin and the "
            f"measured rim centre, got {gap:.3f}mm")

    def test_a_mark_the_guard_accepts_reads_the_same_radius_the_exposed_reference_predicts(
            self, warmed_run):
        """THE ROUND TRIP this repo's standard of evidence asks for: a point at a
        KNOWN canonical-frame distance from the measured rim centre must read the
        SAME radius whether it is measured INTERNALLY (``require_clock_lever``'s own
        basis, ``SiteClicks.to_canon_xy``) or EXTERNALLY, using nothing but the wire
        payload's published ``pose`` and ``clock_reference`` fields — the exact
        computation a client would run to refuse a span locally, before it is ever
        placed. Both an ACCEPTED mark and a REFUSED one are checked: the exposed
        reference must predict both outcomes, not just the convenient one."""
        case = _real_case()
        ctx = load_site(case, warmed_run, WARMED_TOOTH)
        sig = template_signature(ctx.template)
        clicks = site_clicks(ctx, sig)
        pose_world = np.asarray(ctx.record["pose_matrix"], float)
        payload = seated_payload(case, warmed_run, WARMED_TOOTH)

        pose_origin = np.array(payload["pose"]["origin"])
        pose_axis = np.array(payload["pose"]["axis"])
        pose_x = np.array(payload["pose"]["x_axis"])
        pose_y = np.cross(pose_axis, pose_x)
        rim_world = np.array(payload["clock_reference"]["rim_centre"])
        min_lever = payload["clock_reference"]["min_lever_mm"]

        def client_canon_xy(point_world: np.ndarray) -> np.ndarray:
            """What a client with ONLY the wire payload's pose/clock_reference
            fields would compute — no canonical frame, no SiteContext, no scan."""
            rel = np.asarray(point_world) - pose_origin
            return np.array([rel @ pose_x, rel @ pose_y])

        for dx, expect_accept in ((MIN_LEVER_ARM_MM + 2.0, True),
                                  (MIN_LEVER_ARM_MM - 0.1, False)):
            canon_xy = clicks.rim_centre_xy + np.array([dx, 0.0])
            point_world = canon_point_to_world(canon_xy, sig.ztop, pose_world)

            internal_radius = float(np.linalg.norm(
                clicks.to_canon_xy(point_world) - clicks.rim_centre_xy))
            predicted_radius = float(np.linalg.norm(
                client_canon_xy(point_world) - client_canon_xy(rim_world)))
            assert predicted_radius == pytest.approx(internal_radius, abs=1e-5)

            if expect_accept:
                assert require_clock_lever(internal_radius, "t", span=False) == \
                    pytest.approx(internal_radius)
                assert predicted_radius >= min_lever
            else:
                with pytest.raises(AdjustInvalid):
                    require_clock_lever(internal_radius, "t", span=False)
                assert predicted_radius < min_lever


@pytest.mark.slow
@warmed_only
class TestRotationIsAGatedProposal:
    def test_a_step_either_lands_with_its_proof_or_refuses_leaving_every_byte(
            self, warmed_run):
        """THE DOCTRINE, both branches: the gates own the outcome. Applied, the site
        record grows an adjustment, the proof is drawn and the manifest re-registers
        the rewritten files. Refused, NOTHING changed — not a byte."""
        case = _real_case()
        before = _fingerprint(warmed_run)
        try:
            outcome = rotate_site(case, warmed_run, WARMED_TOOTH, step_deg=1.0)
        except AdjustRefused as exc:
            assert str(exc).strip(), "a refusal must carry the gate's own sentence"
            assert _fingerprint(warmed_run) == before
            return
        assert outcome.applied is True
        assert outcome.applied_delta_deg == pytest.approx(1.0)
        assert outcome.cumulative_deg == pytest.approx(1.0)
        proof = f"{WARMED_CASE}-{WARMED_TOOTH}-alignment-proof.png"
        assert proof in outcome.files
        assert (warmed_run / proof).is_file()
        assert outcome.clocking is not None and "notch_shift_deg" in outcome.clocking
        assert outcome.pane_payload is not None
        record = json.loads(
            (warmed_run / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json").read_text())
        assert record["adjustments"][-1]["operation"] == "rotation"
        # the record names no identity AND says so — the honest half
        assert "no identity" in record["adjustments"][-1]["who"]

    def test_reset_restores_the_pipelines_own_certified_pose(self, warmed_run):
        case = _real_case()
        base = json.loads(
            (warmed_run / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json").read_text()
        )["pose_matrix"]
        try:
            rotate_site(case, warmed_run, WARMED_TOOTH, step_deg=1.0)
        except AdjustRefused:
            pytest.skip("this site's gates refuse a 1° step — nothing to reset")
        outcome = rotate_site(case, warmed_run, WARMED_TOOTH, reset=True)
        assert outcome.cumulative_deg == pytest.approx(0.0)
        restored = json.loads(
            (warmed_run / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json").read_text()
        )["pose_matrix"]
        assert np.allclose(np.asarray(restored, float), np.asarray(base, float),
                           atol=1e-9)

    def test_reset_on_an_untouched_site_refuses_and_leaves_every_byte(self, warmed_run):
        """FINDING D: the price of Reset is a rewritten cap, a dropped rung and a
        retired confirmation. On a site standing on the pipeline's own pose it bought
        nothing at all — measured at 1.8e-15mm of movement."""
        before = _fingerprint(warmed_run)
        with pytest.raises(AdjustInvalid) as exc:
            rotate_site(_real_case(), warmed_run, WARMED_TOOTH, reset=True)
        assert "nothing to reset" in str(exc.value)
        assert _fingerprint(warmed_run) == before


@pytest.mark.slow
@warmed_only
class TestMarkTrench:
    def test_a_mark_across_the_arch_is_refused_naming_the_distance(self, warmed_run):
        with pytest.raises(AdjustInvalid) as exc:
            align_to_mark(_real_case(), warmed_run, WARMED_TOOTH,
                          [500.0, 500.0, 500.0])
        assert "click the coded trench on the cap itself" in str(exc.value)
        assert "within 15mm" in str(exc.value)


@pytest.mark.slow
@warmed_only
class TestFitByPointsAndSpans:
    def _site_point(self, run_dir: Path, offset) -> list:
        record = json.loads(
            (run_dir / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json").read_text())
        pos = np.asarray(record["pose_matrix"], float)[:3, 3]
        return (pos + np.asarray(offset, float)).tolist()

    def test_a_span_end_across_the_arch_is_refused_like_any_other_mark(
            self, warmed_run):
        pairs = [Correspondence(scan_point=self._site_point(warmed_run, (1.0, 0, 0)),
                                scan_point_end=[500.0, 500.0, 500.0],
                                part_point=[1.5, 0.0, 1.0])]
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_real_case(), warmed_run, WARMED_TOOTH, pairs)
        assert "within 15mm" in str(exc.value)

    def test_a_coincident_span_is_refused_before_any_rotation_is_formed(
            self, warmed_run):
        point = self._site_point(warmed_run, (1.0, 0.2, 0.0))
        pairs = [Correspondence(scan_point=point, scan_point_end=list(point),
                                part_point=[1.5, 0.0, 1.0])]
        before = _fingerprint(warmed_run)
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_real_case(), warmed_run, WARMED_TOOTH, pairs)
        assert "no direction to read" in str(exc.value)
        assert _fingerprint(warmed_run) == before

    def test_a_free_point_inside_the_lever_arm_names_the_axis_not_a_clock_angle(
            self, warmed_run):
        pairs = [Correspondence(scan_point=self._site_point(warmed_run, (1.0, 0, 0)),
                                part_point=[0.0, 0.0, 1.0])]
        with pytest.raises(AdjustInvalid) as exc:
            align_to_correspondence(_real_case(), warmed_run, WARMED_TOOTH, pairs)
        assert "names the axis, not a clock angle" in str(exc.value)

    def test_a_span_records_both_ends_and_its_observations_for_replay(self, warmed_run):
        """The audit half of the ask: whichever way the gates go, the geometry must be
        replayable from what was recorded — or nothing was recorded at all."""
        case = _real_case()
        a = self._site_point(warmed_run, (1.4, 0.0, 0.4))
        b = self._site_point(warmed_run, (2.6, 0.0, 0.4))
        pairs = [Correspondence(scan_point=a, scan_point_end=b,
                                part_point=[1.5, 0.0, 1.0])]
        before = _fingerprint(warmed_run)
        try:
            outcome = align_to_correspondence(case, warmed_run, WARMED_TOOTH, pairs)
        except AdjustRefused as exc:
            assert str(exc).strip()
            assert _fingerprint(warmed_run) == before
            return
        record = json.loads(
            (warmed_run / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json").read_text())
        evidence = record["adjustments"][-1]["evidence"]
        span = evidence["pairs"][0]["span"]
        assert span["scan_point"] == [round(c, 3) for c in a]
        assert span["scan_point_end"] == [round(c, 3) for c in b]
        assert span["length_mm"] == pytest.approx(1.2, abs=1e-3)
        assert "direction_used" in span
        kinds = {row["observation"] for row in outcome.pairs}
        assert "midpoint" in kinds
        # a radial span contributes its direction as well; a chordal one says why not
        if span["direction_used"]:
            assert "direction" in kinds
        else:
            assert "direction_note" in span


@pytest.mark.slow
@warmed_only
class TestBestFit:
    def test_measure_only_never_touches_a_byte(self, warmed_run):
        before = _fingerprint(warmed_run)
        try:
            outcome = best_fit_site(_real_case(), warmed_run, WARMED_TOOTH,
                                    matching_diameter_mm=0.3, apply=False)
        except AdjustRefused:
            assert _fingerprint(warmed_run) == before
            return
        assert outcome.applied is False
        assert outcome.files == []
        assert outcome.best_fit is not None
        assert outcome.pane_payload is None
        assert _fingerprint(warmed_run) == before

    def test_the_already_optimal_pass_carries_its_widen(self, warmed_run):
        """The one refusal that is really a confirmation (client ask 2026-07-26): at
        the tightest band the certified pose usually already IS the best fit, and the
        pass must arrive with the numbers a green surface needs."""
        try:
            best_fit_site(_real_case(), warmed_run, WARMED_TOOTH,
                          matching_diameter_mm=0.05, apply=False)
        except AlreadyOptimal as exc:
            assert exc.matching_diameter_mm == pytest.approx(0.05)
            assert exc.suggested_diameter_mm == pytest.approx(0.1)
            assert "already the best fit" in str(exc)
            # a PASS must never wear the refusal's prefix
            assert "refused" not in str(exc)
        except AdjustRefused:
            pytest.skip("this site's tightest band refuses for another reason")

    def test_a_real_refusal_names_the_dial_it_was_refused_at(self, warmed_run):
        """server.py's ``_refuse_best_fit`` prefixed every branch. The widest band is
        where the fleet's real refusal lives (measured: trust-region at Ø2.0mm)."""
        try:
            best_fit_site(_real_case(), warmed_run, WARMED_TOOTH,
                          matching_diameter_mm=2.0, apply=False)
        except AlreadyOptimal:
            pytest.skip("this site is already optimal at the ceiling — a pass, not a "
                        "refusal")
        except AdjustRefused as exc:
            assert str(exc).startswith("best-fit at a 2.00mm matching diameter "
                                       "refused: ")

    def test_the_reset_anchor_survives_a_best_fit_whatever_the_gates_say(
            self, warmed_run):
        """THE ANCHOR ``best_fit_site`` REASONS ABOUT, on real data (suites 2026-07-28
        named it untested; the ordering itself is pinned purely in
        ``TestAnchorCertifiedPose``, which is where it can be pinned unconditionally —
        a warmed run's certified pose IS its own best fit, so the landing branch is not
        reachable here and a test that only ran when it was would prove nothing).

        What IS reachable, and what matters: a best-fit asked for AFTER a rotation must
        not re-anchor. Landed or refused, Reset must still find the pipeline's own pose
        — and must leave no ``best_fit`` block describing a pose that is gone."""
        case = _real_case()
        record_path = warmed_run / f"{WARMED_CASE}-{WARMED_TOOTH}-implant.json"
        certified = json.loads(record_path.read_text())["pose_matrix"]
        try:
            rotate_site(case, warmed_run, WARMED_TOOTH, step_deg=5.0)
        except AdjustRefused:
            pytest.skip("this site's gates refuse a 5° step — nothing to anchor")
        for diameter in (0.3, 0.6, 1.0):
            try:
                best_fit_site(case, warmed_run, WARMED_TOOTH,
                              matching_diameter_mm=diameter)
            except AdjustRefused:
                continue
        outcome = rotate_site(case, warmed_run, WARMED_TOOTH, reset=True)
        assert "restored the pipeline's certified pose" in outcome.detail
        restored = json.loads(record_path.read_text())
        assert np.allclose(np.asarray(restored["pose_matrix"], float),
                           np.asarray(certified, float), atol=1e-9)
        assert "best_fit" not in restored


class TestTheLandmarksTheSoftwareProposes:
    """clock_landmarks / landmark_point (client 2026-07-29 item 3): the machine offers
    the part half, so the operator only does the half a human is needed for."""

    def _feature(self, fid, azimuth, radius, z=1.0, kind="trench"):
        return PartFeature(id=fid, kind=kind, azimuth_deg=azimuth,
                           radius_mm=radius, z_mm=z)

    def test_a_landmark_is_the_inverse_of_the_azimuth_radius_it_was_measured_as(self):
        # 0 degrees at radius 2 about the origin is +x, by hand
        p = landmark_point(self._feature("f1", 0.0, 2.0, z=0.5), (0.0, 0.0))
        assert p == pytest.approx((2.0, 0.0, 0.5))

    def test_ninety_degrees_lands_on_plus_y(self):
        p = landmark_point(self._feature("f1", 90.0, 3.0), (0.0, 0.0))
        assert p[0] == pytest.approx(0.0, abs=1e-9)
        assert p[1] == pytest.approx(3.0)

    def test_the_centre_is_HONOURED_not_assumed_to_be_the_origin(self):
        # the same failure the azimuth helper guards: a wrong centre puts every
        # landmark on a ghost ring offset from the part
        p = landmark_point(self._feature("f1", 0.0, 2.0), (10.0, -4.0))
        assert p[0] == pytest.approx(12.0)
        assert p[1] == pytest.approx(-4.0)

    def test_a_landmark_round_trips_through_the_azimuth_it_came_from(self):
        centre = (1.5, -2.5)
        for azimuth in (0.0, 37.0, 180.0, -95.0, 359.0):
            f = self._feature("f", azimuth, 2.75)
            x, y, _ = landmark_point(f, centre)
            assert azimuth_deg((x, y), centre) == pytest.approx(
                wrap_deg(azimuth), abs=1e-6)

    def test_z_rides_through_untouched(self):
        assert landmark_point(self._feature("f", 12.0, 2.0, z=-3.25), (0, 0))[2] == -3.25
