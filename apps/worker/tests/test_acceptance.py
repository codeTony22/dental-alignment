"""The acceptance-numbers catalog: band evaluation for the doctor verification panel.

Behavioral contract of domain/acceptance.py: every catalog metric judges a run-site row
into pass|review|fail|missing, missing values are reported honestly (never counted as a
pass), and the overall verdict is the worst evaluated band. Fixtures mirror the real
run.json row shape the live-demo server persists (cap7030's own field layout).
"""
from __future__ import annotations

import math

from case_prep.domain.acceptance import (CATALOG, CLICK_PRECISION_CONTEXT, FAIL,
                                         MISSING, PASS, REVIEW,
                                         evaluate_acceptance)


def _row(**overrides):
    """A healthy full-rim site in the persisted run-row shape; overrides poke one field."""
    base = {
        "tooth": 29,
        "auto_delta_mm": 0.39,
        "fit": {"avg_mm": 0.42, "max_mm": 1.24},
        "seat_method": "rim",
        "rim_arc_bins": 12,
        "rim_agreement_mm": 0.34,
        "top_face_agreement_mm": 0.34,
        "confidence": {"grade": "medium", "pose_pos_spread_mm": 0.87,
                       "pose_axis_spread_deg": 10.8},
        "clocking": {"notch_shift_deg": -1.9, "notch_corr": 0.61,
                     "notch_prominence": 0.14, "evidence": "codes",
                     "consistency_deg": None, "rotation_unverified": False},
        "variant": {"identified": "7030", "declared": "7030"},
    }
    base.update(overrides)
    return base


def _metric(result, key):
    return next(m for m in result["metrics"] if m["key"] == key)


class TestCatalogIntegrity:
    def test_every_metric_has_a_cited_industry_reference(self):
        for spec in CATALOG:
            assert spec.industry_ref.value, spec.key
            assert spec.industry_ref.source, spec.key

    def test_keys_are_unique_and_evaluation_preserves_catalog_order(self):
        keys = [s.key for s in CATALOG]
        assert len(keys) == len(set(keys))
        out = evaluate_acceptance(_row())
        assert [m["key"] for m in out["metrics"]] == keys

    def test_banded_metrics_expose_their_thresholds_on_the_payload(self):
        out = evaluate_acceptance(_row())
        fit = _metric(out, "fit_avg_mm")
        assert fit["bands"] == {"pass": 0.8, "review": 1.5}
        assert fit["industry_ref"]["value"].startswith("RealGUIDE")

    def test_context_row_rides_along_as_copy_not_a_chip(self):
        out = evaluate_acceptance(_row())
        assert out["context"] == CLICK_PRECISION_CONTEXT
        assert all(m["key"] != "click_precision" for m in out["metrics"])


class TestThresholdBands:
    def test_fit_avg_pass_review_fail_edges(self):
        assert _metric(evaluate_acceptance(_row(fit={"avg_mm": 0.8, "max_mm": 1.0})),
                       "fit_avg_mm")["band"] == PASS
        assert _metric(evaluate_acceptance(_row(fit={"avg_mm": 1.2, "max_mm": 1.0})),
                       "fit_avg_mm")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(fit={"avg_mm": 1.6, "max_mm": 1.0})),
                       "fit_avg_mm")["band"] == FAIL

    def test_rim_agreement_fail_edge_is_the_shipped_band_refusal_constant(self):
        # 1.6 is _NUDGE_BAND_REFUSAL_MM — the doctor number and the pipeline guard agree
        assert _metric(evaluate_acceptance(_row(rim_agreement_mm=1.6)),
                       "rim_agreement_mm")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(rim_agreement_mm=1.61)),
                       "rim_agreement_mm")["band"] == FAIL

    def test_top_face_fail_edge_is_the_certification_bound(self):
        assert _metric(evaluate_acceptance(_row(top_face_agreement_mm=1.5)),
                       "top_face_p90_mm")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(top_face_agreement_mm=1.51)),
                       "top_face_p90_mm")["band"] == FAIL

    def test_display_carries_the_unit(self):
        assert _metric(evaluate_acceptance(_row()), "fit_avg_mm")["display"] == "0.42 mm"


class TestMissingHonesty:
    def test_absent_field_is_missing_never_pass(self):
        out = evaluate_acceptance(_row(fit=None))
        m = _metric(out, "fit_avg_mm")
        assert m["band"] == MISSING
        assert m["value"] is None
        assert "fit_avg_mm" in out["overall"]["missing"]

    def test_non_finite_value_is_missing_not_judged(self):
        out = evaluate_acceptance(_row(rim_agreement_mm=math.nan))
        assert _metric(out, "rim_agreement_mm")["band"] == MISSING

    def test_delivered_channel_missing_on_old_cache_rows(self):
        # rows persisted before the G3 fields landed (2026-07-24) carry no
        # delivered_channel_* keys — honestly missing, never fabricated
        m = _metric(evaluate_acceptance(_row()), "delivered_channel_vs_recess_mm")
        assert m["band"] == MISSING
        assert m["value"] is None

    def test_empty_row_is_all_missing_and_overall_missing(self):
        out = evaluate_acceptance({})
        assert out["overall"]["band"] == MISSING
        bands = {m["band"] for m in out["metrics"]
                 if m["key"] != "cap_identity"}
        assert bands == {MISSING}


class TestRotationBands:
    """Binon screw-joint anchors: <=2 with codes evidence passes, 2-5 or recess-only
    reviews, >5 or unverified fails (the recess instrument's azimuth bias is
    phantom-sim-convicted, so it can never anchor a pass)."""

    def _clock(self, **kw):
        base = {"notch_shift_deg": 1.0, "notch_corr": 0.61, "notch_prominence": 0.14,
                "evidence": "codes", "consistency_deg": None,
                "rotation_unverified": False}
        base.update(kw)
        return base

    def test_small_residual_with_codes_evidence_passes(self):
        out = evaluate_acceptance(_row(clocking=self._clock(notch_shift_deg=-1.9)))
        assert _metric(out, "rotation_deg")["band"] == PASS

    def test_between_two_and_five_degrees_reviews(self):
        out = evaluate_acceptance(_row(clocking=self._clock(notch_shift_deg=3.1)))
        assert _metric(out, "rotation_deg")["band"] == REVIEW

    def test_recess_only_evidence_reviews_even_when_small(self):
        out = evaluate_acceptance(
            _row(clocking=self._clock(notch_shift_deg=0.5, evidence="recess")))
        assert _metric(out, "rotation_deg")["band"] == REVIEW

    def test_beyond_five_degrees_fails(self):
        out = evaluate_acceptance(
            _row(clocking=self._clock(notch_shift_deg=23.8, evidence="recess")))
        assert _metric(out, "rotation_deg")["band"] == FAIL

    def test_unverified_rotation_fails(self):
        out = evaluate_acceptance(
            _row(clocking=self._clock(rotation_unverified=True)))
        assert _metric(out, "rotation_deg")["band"] == FAIL

    def test_icp_seat_without_clocking_is_missing(self):
        out = evaluate_acceptance(_row(clocking=None))
        assert _metric(out, "rotation_deg")["band"] == MISSING

    def test_consistency_routes_attention_at_the_shipped_rule(self):
        out = evaluate_acceptance(
            _row(clocking=self._clock(consistency_deg=24.0)))
        assert _metric(out, "rotation_consistency_deg")["band"] == FAIL
        out = evaluate_acceptance(
            _row(clocking=self._clock(consistency_deg=15.0)))
        assert _metric(out, "rotation_consistency_deg")["band"] == REVIEW


class TestCustomEvaluators:
    def test_confidence_grade_maps_high_medium_low(self):
        for grade, band in (("high", PASS), ("medium", REVIEW), ("low", FAIL)):
            out = evaluate_acceptance(_row(confidence={
                "grade": grade, "pose_pos_spread_mm": 0.5,
                "pose_axis_spread_deg": 5.0}))
            m = _metric(out, "confidence_grade")
            assert m["band"] == band
            assert m["value"] == grade

    def test_rim_arc_full_passes_partial_reviews_sparse_fails(self):
        assert _metric(evaluate_acceptance(_row(rim_arc_bins=12)),
                       "rim_arc_visibility")["band"] == PASS
        assert _metric(evaluate_acceptance(_row(rim_arc_bins=8)),
                       "rim_arc_visibility")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(rim_arc_bins=5)),
                       "rim_arc_visibility")["band"] == FAIL

    def test_code_band_gates_met_passes_below_gates_recess_reviews(self):
        out = evaluate_acceptance(_row())
        assert _metric(out, "code_band_readability")["band"] == PASS
        out = evaluate_acceptance(_row(clocking={
            "notch_shift_deg": 23.8, "notch_corr": 0.50, "notch_prominence": 0.08,
            "evidence": "recess", "rotation_unverified": False}))
        assert _metric(out, "code_band_readability")["band"] == REVIEW
        out = evaluate_acceptance(_row(clocking={
            "notch_shift_deg": None, "notch_corr": 0.20, "notch_prominence": 0.05,
            "evidence": "none", "rotation_unverified": True}))
        assert _metric(out, "code_band_readability")["band"] == FAIL

    def test_identity_match_passes_mismatch_reviews_undeclared_fails(self):
        assert _metric(evaluate_acceptance(_row()), "cap_identity")["band"] == PASS
        out = evaluate_acceptance(
            _row(variant={"identified": "7030", "declared": "6030"}))
        assert _metric(out, "cap_identity")["band"] == REVIEW
        out = evaluate_acceptance(
            _row(variant={"identified": "7030", "declared": None}))
        assert _metric(out, "cap_identity")["band"] == FAIL

    def test_machine_agreement_prefers_island_probe_and_fails_unconverged(self):
        out = evaluate_acceptance(_row(island={
            "machine_centre_offset_mm": 0.26, "converged": True}))
        m = _metric(out, "machine_agreement_mm")
        assert (m["value"], m["band"]) == (0.26, PASS)
        out = evaluate_acceptance(_row(island={
            "machine_centre_offset_mm": 0.26, "converged": False}))
        assert _metric(out, "machine_agreement_mm")["band"] == FAIL

    def test_machine_agreement_falls_back_to_auto_delta(self):
        out = evaluate_acceptance(_row(auto_delta_mm=2.04))
        m = _metric(out, "machine_agreement_mm")
        assert (m["value"], m["band"]) == (2.04, FAIL)


class TestPanelCompletion:
    """Master plan §8 item 12: the previously-'missing' panel rows become banded the
    moment the run row carries the measured fields (auto_flow writes them since
    2026-07-24); rows from older caches stay honestly missing (covered above)."""

    def test_deviation_rms_bands_at_the_misfit_line_and_map_clamp(self):
        # pass edge 0.2 = the published misfit-acceptability line; fail edge 0.5 =
        # the ±0.5 map convention (catalog receipts, metric 3)
        assert _metric(evaluate_acceptance(_row(deviation_rms_mm=0.18)),
                       "deviation_rms_mm")["band"] == PASS
        assert _metric(evaluate_acceptance(_row(deviation_rms_mm=0.35)),
                       "deviation_rms_mm")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(deviation_rms_mm=0.62)),
                       "deviation_rms_mm")["band"] == FAIL

    def test_rim_off_centre_reads_the_row_field(self):
        out = evaluate_acceptance(_row(rim_off_centre=0.004))
        m = _metric(out, "rim_off_centre_mm")
        assert m["band"] == PASS
        assert "rim_off_centre_mm" not in out["overall"]["missing"]
        assert _metric(evaluate_acceptance(_row(rim_off_centre=0.45)),
                       "rim_off_centre_mm")["band"] == FAIL

    def test_delivered_channel_adopts_the_screw_recess_bands(self):
        # DELIBERATE (2026-07-24): was a placeholder (always missing); now banded at
        # the screw-recess landing edges 0.5/0.75 — exactly what the placeholder's
        # own note promised once the metric existed
        assert _metric(evaluate_acceptance(_row(delivered_channel_vs_recess=0.11)),
                       "delivered_channel_vs_recess_mm")["band"] == PASS
        assert _metric(evaluate_acceptance(_row(delivered_channel_vs_recess=0.62)),
                       "delivered_channel_vs_recess_mm")["band"] == REVIEW
        assert _metric(evaluate_acceptance(_row(delivered_channel_vs_recess=0.9)),
                       "delivered_channel_vs_recess_mm")["band"] == FAIL

    def test_delivered_channel_display_carries_the_vs_cap_read(self):
        m = _metric(evaluate_acceptance(_row(
            delivered_channel_vs_recess=0.11, delivered_channel_vs_cap_channel=0.018)),
            "delivered_channel_vs_recess_mm")
        assert m["display"] == "0.11 mm (vs cap channel 0.02)"

    def test_completed_row_shrinks_the_missing_set(self):
        out = evaluate_acceptance(_row(
            deviation_rms_mm=0.18, rim_off_centre=0.01,
            delivered_channel_vs_recess=0.11))
        assert not ({"deviation_rms_mm", "rim_off_centre_mm",
                     "delivered_channel_vs_recess_mm"}
                    & set(out["overall"]["missing"]))


class TestOverall:
    def test_all_healthy_measured_metrics_give_overall_pass(self):
        out = evaluate_acceptance(_row(
            confidence={"grade": "high", "pose_pos_spread_mm": 0.4,
                        "pose_axis_spread_deg": 5.0},
            rim_agreement_mm=0.3))
        assert out["overall"]["band"] == PASS
        assert out["overall"]["counts"][FAIL] == 0

    def test_one_fail_dominates_overall(self):
        out = evaluate_acceptance(_row(top_face_agreement_mm=2.4))
        assert out["overall"]["band"] == FAIL

    def test_review_beats_pass_but_not_fail(self):
        out = evaluate_acceptance(_row())  # confidence medium -> review
        assert out["overall"]["band"] == REVIEW

    def test_missing_metrics_are_listed_and_never_lift_the_verdict(self):
        out = evaluate_acceptance(_row())
        assert set(out["overall"]["missing"]) >= {
            "deviation_rms_mm", "rim_off_centre_mm", "bore_void_off_mm",
            "delivered_channel_vs_recess_mm"}
        assert out["overall"]["counts"][MISSING] == len(out["overall"]["missing"])
