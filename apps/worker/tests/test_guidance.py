"""The advisory gate as GUIDANCE (client spec, 2026-07-12): instead of a bare ADVISORY
label, each site tells the operator WHAT TO DO — derived from the pipeline's own signals,
explainable, and never a silent auto-pass."""
from __future__ import annotations

from case_prep.domain.guidance import advisory_guidance


def _signals(**over):
    base = dict(seat_method="rim", fit_avg_mm=0.5, fit_max_mm=2.0,
                declared=None, dia_class_confident=True,
                measurement_disputes_declared=False, variant_ambiguous=False,
                axis_violation=False, seed_source="click")
    base.update(over)
    return base


class TestAdvisoryGuidance:
    def test_clean_site_is_ready_with_visual_check_action(self):
        g = advisory_guidance(**_signals(declared="5020"))
        assert g["level"] == "ready"
        assert any("view 1" in a or "visually" in a for a in g["actions"])

    def test_non_ready_centre_only_marks_point_to_border_clicks(self):
        """Client semantics (2026-07-14): the centre mark is an INDICATOR, not the
        exact centre (hollow caps swallow the click; neighbours shadow it) — when a
        marks-seeded site is not clean, steer the doctor to the border clicks, which
        ARE the measurement."""
        g = advisory_guidance(**_signals(seed_source="marks", variant_ambiguous=True,
                                         dia_class_confident=False))
        assert g["level"] == "attention"
        assert any("border" in a.lower() for a in g["actions"])

    def test_border_seeded_sites_do_not_get_the_border_tip(self):
        g = advisory_guidance(**_signals(seed_source="marks", variant_ambiguous=True,
                                         dia_class_confident=False,
                                         border_points_given=True))
        assert not any("border" in a.lower() for a in g["actions"])

    def test_ready_marks_sites_are_not_nagged_about_borders(self):
        g = advisory_guidance(**_signals(seed_source="marks", declared="5020"))
        assert g["level"] == "ready"
        assert not any("border" in a.lower() for a in g["actions"])

    def test_floating_top_face_demands_border_clicks(self):
        """Client report (2026-07-15, zimmer t7): a seat whose TOP FACE floats off the
        scan (the depth signals conflict — the sloped-cap outlier) presented READY.
        The top face is the cap's always-visible surface: when it does not sit on the
        scan the seat is not visually acceptable, whatever the band says — downgrade
        and route to border clicks, which pin the depth authoritatively."""
        g = advisory_guidance(**_signals(declared="7030", seed_source="marks",
                                         top_face_off_mm=2.45))
        assert g["level"] == "attention"
        assert any("top" in a.lower() and "◐" in a for a in g["actions"])

    def test_seated_top_face_stays_silent(self):
        g = advisory_guidance(**_signals(declared="6030", seed_source="marks",
                                         top_face_off_mm=0.25))
        assert g["level"] == "ready"
        assert not any("top face" in a.lower() for a in g["actions"])

    def test_disagreeing_border_clicks_demand_a_recheck(self):
        """Client redo run (276794487, 2026-07-14): one border click 0.89mm off the
        others' plane tilted the seat 12deg, yet the gate presented READY. Clicks
        that disagree beyond the click-noise floor (~0.3 measured on good gestures)
        must downgrade to attention and name the concrete remedy."""
        g = advisory_guidance(**_signals(seed_source="marks",
                                         border_points_given=True,
                                         border_clicks_disagree_mm=0.89))
        assert g["level"] == "attention"
        assert any("border click" in a.lower() and "0.89" in a for a in g["actions"])

    def test_agreeing_border_clicks_stay_silent(self):
        """The good prefill gesture measures ~0.33 leave-one-out — plain click noise,
        no nag."""
        g = advisory_guidance(**_signals(declared="6020", seed_source="marks",
                                         border_points_given=True,
                                         border_clicks_disagree_mm=0.33))
        assert g["level"] == "ready"
        assert not any("border click" in a.lower() for a in g["actions"])

    def test_axis_violation_blocks_with_brush_or_reject(self):
        g = advisory_guidance(**_signals(axis_violation=True))
        assert g["level"] == "action-needed"
        assert any("brush" in a.lower() for a in g["actions"])
        assert any("reject" in a.lower() for a in g["actions"])

    def test_measurement_dispute_asks_to_confirm_with_doctor(self):
        g = advisory_guidance(**_signals(declared="7030",
                                         measurement_disputes_declared=True))
        assert g["level"] == "attention"
        assert any("doctor" in a.lower() or "library" in a.lower() for a in g["actions"])

    def test_no_declaration_and_ambiguous_asks_for_picker(self):
        g = advisory_guidance(**_signals(declared=None, variant_ambiguous=True,
                                         dia_class_confident=False))
        assert g["level"] == "attention"
        assert any("picker" in a.lower() or "choose" in a.lower() for a in g["actions"])

    def test_high_fit_error_suggests_brush(self):
        g = advisory_guidance(**_signals(fit_avg_mm=1.4))
        assert g["level"] == "attention"
        assert any("brush" in a.lower() for a in g["actions"])

    def test_icp_fallback_on_click_suggests_brush(self):
        g = advisory_guidance(**_signals(seat_method="icp", seed_source="click"))
        assert g["level"] == "attention"
        assert any("brush" in a.lower() for a in g["actions"])

    def test_brush_seeded_icp_fallback_stays_honest_but_calmer(self):
        # the human already painted; ICP fallback alone should not nag for more brushing
        g = advisory_guidance(**_signals(seat_method="icp", seed_source="brush"))
        assert g["level"] in ("ready", "attention")
        assert not any("brush the cap" in a.lower() for a in g["actions"])


class TestVariantCandidatesTooClose:
    def test_inseparable_candidates_demand_the_doctors_confirmation(self):
        g = advisory_guidance(**_signals(candidates_too_close=True))
        assert g["level"] == "attention"
        assert any("declaration" in a.lower() or "doctor" in a.lower() for a in g["actions"])

    def test_separable_candidates_stay_quiet(self):
        g = advisory_guidance(**_signals(candidates_too_close=False, declared="5020"))
        assert g["level"] == "ready"
