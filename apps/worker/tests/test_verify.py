"""THE STANDING FLEET VERIFICATION (§10-AH's automation ask) — the pure rules.

The physics rides ``run_case`` + the published DEV metric and is exercised by
running the report itself; what is pinned here is what the report DECIDES: which
run dir is the baseline, which proposal may speak for a tooth (the adopt door's
own guard — cap7020's "9mm disagreement" was its NEIGHBOUR), which seed variants
a site offers, and what counts as an improvement (beating the shipped pose by
more than the noise floor — a tie defends nothing).
"""
from __future__ import annotations

import json

from case_prep.application.detection import DetectedSite
from case_prep.application.verify import (MIN_GAIN_RMS_MM, PICK_RADIUS_MM,
                                          _seed_variants, improvement_of,
                                          latest_run_dir, marked_centers_of,
                                          proposal_for)


def proposal(center, tooth_guess=None):
    return DetectedSite(center=tuple(center), void_ratio=0.4,
                        rim_below_cusps_mm=0.5, tooth_guess=tooth_guess,
                        capture={})


class TestLatestRunDir:
    def test_no_runs_is_none(self, tmp_path):
        assert latest_run_dir(tmp_path, "case-x") is None
        (tmp_path / "case-x" / "runs").mkdir(parents=True)
        assert latest_run_dir(tmp_path, "case-x") is None

    def test_the_newest_run_with_implant_records_wins(self, tmp_path):
        runs = tmp_path / "case-x" / "runs"
        for name, complete in (("20260801-a", True), ("20260803-b", False),
                               ("20260802-c", True)):
            d = runs / name
            d.mkdir(parents=True)
            if complete:
                (d / "case-x-4-implant.json").write_text("{}")
        # 20260803-b is newest but EMPTY (a withdrawn or refused landing) —
        # the baseline is the newest run that actually landed records
        assert latest_run_dir(tmp_path, "case-x").name == "20260802-c"


class TestMarkedCenters:
    def test_absent_or_corrupt_sessions_read_as_no_marks(self, tmp_path):
        assert marked_centers_of(tmp_path, "case-x") == {}
        (tmp_path / "case-x").mkdir(parents=True)
        (tmp_path / "case-x" / "session.json").write_text("not json")
        assert marked_centers_of(tmp_path, "case-x") == {}

    def test_only_sites_with_marks_appear(self, tmp_path):
        (tmp_path / "case-x").mkdir(parents=True)
        (tmp_path / "case-x" / "session.json").write_text(json.dumps({
            "sites": {"4": {"marked_center": [1.0, 2.0, 3.0]}, "13": {}}}))
        assert marked_centers_of(tmp_path, "case-x") == {4: [1.0, 2.0, 3.0]}


class TestProposalFor:
    CENTRE = [10.0, 0.0, 0.0]

    def test_an_unguessed_proposal_beyond_the_radius_is_another_cap(self):
        # the cap7020 pin, the adopt door's own rule mirrored
        far = proposal([10.0 + PICK_RADIUS_MM + 3.0, 0, 0], tooth_guess=None)
        assert proposal_for([far], 3, self.CENTRE) is None

    def test_a_guessed_proposal_may_disagree_by_more_than_the_radius(self):
        far = proposal([19.0, 0, 0], tooth_guess=3)
        assert proposal_for([far], 3, self.CENTRE) == [19.0, 0, 0]

    def test_the_nearest_allowed_proposal_wins(self):
        near = proposal([11.0, 0, 0])
        nearer = proposal([10.4, 0, 0])
        assert proposal_for([near, nearer], 3, self.CENTRE) == [10.4, 0, 0]


class TestSeedVariants:
    SITE = {"tooth": 4, "center": [10.0, 0.0, 0.0],
            "center_mark": [10.1, 0, 0], "rim_mark": [13.0, 0, 0]}

    def test_the_baseline_re_runs_the_record_as_is(self):
        (label, siteover), = _seed_variants(dict(self.SITE), 4, {}, [])
        assert label == "baseline (record)"
        assert siteover["center_mark"] == [10.1, 0, 0]

    def test_the_operator_mark_seeds_alone(self):
        # the §10-AH rule: the record's pair belongs to the record's own centre
        variants = _seed_variants(dict(self.SITE), 4, {4: [9.0, 1.0, 0.0]}, [])
        labels = [label for label, _ in variants]
        assert labels == ["baseline (record)", "operator mark"]
        marked = dict(variants[1][1])
        assert marked["center"] == [9.0, 1.0, 0.0]
        assert "center_mark" not in marked
        assert "rim_mark" not in marked

    def test_a_detector_proposal_agreeing_with_the_centre_is_a_null_lever(self):
        # measured on cap6020: 0.006mm apart moved the axis 0.04° — re-running
        # it would report noise as a variant
        same = proposal([10.02, 0, 0], tooth_guess=4)
        variants = _seed_variants(dict(self.SITE), 4, {}, [same])
        assert [label for label, _ in variants] == ["baseline (record)"]

    def test_a_disagreeing_detector_proposal_is_a_variant_seeding_alone(self):
        det = proposal([12.0, 0, 0], tooth_guess=4)
        variants = _seed_variants(dict(self.SITE), 4, {}, [det])
        assert [label for label, _ in variants] == [
            "baseline (record)", "detector"]
        seeded = dict(variants[1][1])
        assert seeded["center"] == [12.0, 0, 0]
        assert "center_mark" not in seeded


class TestImprovementOf:
    ROW = {"shipped_rms": 0.4157, "variants": [
        {"seed": "baseline (record)", "rms": 0.4160, "p90": 0.68},
        {"seed": "operator mark", "rms": 0.3053, "p90": 0.44},
        {"seed": "detector", "refused": "AdjustRefused: nope"},
    ]}

    def test_the_best_beating_variant_is_named(self):
        assert improvement_of(dict(self.ROW))["seed"] == "operator mark"

    def test_a_tie_or_noise_level_gain_is_not_an_improvement(self):
        row = {"shipped_rms": 0.31, "variants": [
            {"seed": "x", "rms": 0.31 - MIN_GAIN_RMS_MM / 2, "p90": 0.5}]}
        assert improvement_of(row) is None

    def test_refusals_never_count(self):
        row = {"shipped_rms": 0.31,
               "variants": [{"seed": "x", "refused": "boom"}]}
        assert improvement_of(row) is None
