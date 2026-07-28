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
                                          AdjustInvalid, AdjustRefused, AlreadyOptimal,
                                          Correspondence, align_to_correspondence,
                                          align_to_mark, azimuth_deg, best_fit_site,
                                          circular_mean_deg, direction_delta,
                                          load_site, rotate_site, seated_payload,
                                          span_readings, validate_span)
from case_prep.application.cases import CaseRecord, discover_cases

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

    def test_reading_the_seated_pose_writes_nothing(self, warmed_run):
        before = _fingerprint(warmed_run)
        seated_payload(_real_case(), warmed_run, WARMED_TOOTH)
        assert _fingerprint(warmed_run) == before


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
        except AdjustRefused:
            pytest.skip("this site's tightest band refuses for another reason")
