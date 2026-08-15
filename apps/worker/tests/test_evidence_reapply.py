"""EVIDENCE RE-APPLY (§10-AD): a re-run receives the operator's persisted alignment
evidence and re-applies it AFTER automation, through the same application.adjust
functions the live tools use.

Fast tests pin the DISPATCH: kinds route to their functions in apply order, outcomes
fold into the summary (receipts, row numbers, package files), and every refusal is a
receipt — never an exception out of the run. The slow test is the feature on the
real tree: a run handed best-fit evidence lands ``evidence_reapplied`` on its
summary AND its on-disk report.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from case_prep.application import adjust
from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.run import (RunSelection, _reapply_evidence, run_case)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")


def _case(tmp_path: Path) -> CaseRecord:
    return CaseRecord(id="case-x", doctor="Doctor X", jaw="upper",
                      scan=tmp_path / "scan.stl", data_root=tmp_path,
                      suggested_model=None, suggested_construction=None,
                      suggested_sites=())


def _outcome(**overrides):
    # every field the canonical fold reads (AdjustOutcome's own defaults) — the
    # fold serves the live tools too, so the fake must wear the whole shape
    values = dict(tooth=13, operation="fit-by-points", detail="re-applied",
                  files=["case-x-13-implant.json"], clocking={"deg": 3.0},
                  deviation={"deviation_rms_mm": 0.11}, stale_metrics=["guidance"],
                  nudge=None, best_fit=None, pairs=[], residual_rms_mm=None,
                  translation_mm=None, fit_version=None,
                  applied=True)
    values.update(overrides)
    return SimpleNamespace(**values)


def _summary():
    # the pipeline's clocking block carries keys the tools never re-measure
    # (rotation_unverified above all) — the fold must MERGE, not replace
    return {"sites": [{"tooth": 13, "fit": {},
                       "clocking": {"deg": 9.0, "rotation_unverified": True,
                                    "evidence": "codes"}}],
            "package_files": ["case-x-manifest.json"]}


class TestTheDispatch:
    def test_each_kind_reaches_its_own_function_in_apply_order(
            self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(adjust, "align_to_mark",
                            lambda case, run_dir, tooth, point:
                            calls.append(("mark", tooth, list(point)))
                            or _outcome(operation="align-to-mark"))
        monkeypatch.setattr(adjust, "align_to_correspondence",
                            lambda case, run_dir, tooth, pairs, fit_version:
                            calls.append(("pairs", tooth, len(pairs)))
                            or _outcome())
        monkeypatch.setattr(adjust, "best_fit_site",
                            lambda case, run_dir, tooth, matching_diameter_mm,
                            apply: calls.append(("best_fit", tooth,
                                                 matching_diameter_mm))
                            or _outcome(operation="best-fit"))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "mark", "point": [1.0, 2.0, 3.0], "applied_at": "t1"},
            {"kind": "pairs", "applied_at": "t2",
             "pairs": [{"scan_point": [0.0, 0.0, 0.0]}]},
            {"kind": "best_fit", "matching_diameter_mm": 0.4, "applied_at": "t3"},
        ]}, summary)
        assert [c[0] for c in calls] == ["mark", "pairs", "best_fit"]
        receipts = summary["evidence_reapplied"]
        assert [r["outcome"] for r in receipts] == ["applied"] * 3
        # the re-derived numbers MERGE into the row (audit 2026-08-04: a replace
        # erased rotation_unverified and claimed a verified rotation), staleness
        # lands under rework — the ONE key the assurance projection reads — and
        # the rewritten file is listed once
        assert summary["sites"][0]["clocking"] == {
            "deg": 3.0, "rotation_unverified": True, "evidence": "codes"}
        assert summary["sites"][0]["deviation_rms_mm"] == 0.11
        assert summary["sites"][0]["rework"] == {"stale_metrics": ["guidance"]}
        assert "stale_metrics" not in summary["sites"][0]  # never the unread key
        assert summary["package_files"].count("case-x-13-implant.json") == 1

    def test_a_refusal_is_a_receipt_with_the_gates_words_never_a_raise(
            self, tmp_path, monkeypatch):
        def refuse(case, run_dir, tooth, point):
            raise adjust.AdjustRefused("the mark is 9.0mm from the site — too far")
        monkeypatch.setattr(adjust, "align_to_mark", refuse)
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path,
                          {13: [{"kind": "mark", "point": [0, 0, 0]}]}, summary)
        (receipt,) = summary["evidence_reapplied"]
        assert receipt["outcome"] == "refused"
        assert "too far" in receipt["detail"]
        # nothing folded: the row keeps the automation's own numbers
        assert summary["sites"][0]["clocking"]["deg"] == 9.0
        assert "rework" not in summary["sites"][0]

    def test_already_optimal_is_a_pass_shaped_receipt(self, tmp_path, monkeypatch):
        def optimal(case, run_dir, tooth, matching_diameter_mm, apply):
            raise adjust.AlreadyOptimal("already within the certified bound",
                                        matching_diameter_mm=0.3,
                                        suggested_diameter_mm=0.6)
        monkeypatch.setattr(adjust, "best_fit_site", optimal)
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path,
                          {13: [{"kind": "best_fit"}]}, summary)
        (receipt,) = summary["evidence_reapplied"]
        assert receipt["outcome"] == "already-optimal"

    def test_an_unknown_kind_refuses_by_name_instead_of_guessing(self, tmp_path):
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path,
                          {13: [{"kind": "telepathy"}]}, summary)
        (receipt,) = summary["evidence_reapplied"]
        assert receipt["outcome"] == "refused"
        assert "telepathy" in receipt["detail"]

    def test_no_evidence_leaves_the_summary_untouched(self, tmp_path):
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {}, summary)
        assert "evidence_reapplied" not in summary


class TestTheFoldMatchesTheLiveTools:
    """AUDIT 2026-08-04: the re-apply's hand-fold had drifted from the BFF's
    interactive fold on four shapes (rework key, clocking merge, nudge, best_fit).
    One function now serves both callers — ``adjust.fold_outcome_into_row`` — and
    these pin the shapes the assurance/receipt projections actually read
    (bff/resources/deliver.py reads rework.stale_metrics, clocking.evidence/
    rotation_unverified, nudge.cumulative_deg, best_fit.matching_diameter_mm)."""

    def test_a_rotating_tool_folds_its_nudge_but_a_best_fit_never_does(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(adjust, "align_to_mark",
                            lambda case, run_dir, tooth, point:
                            _outcome(operation="align-to-mark",
                                     nudge={"cumulative_deg": 4.0}))
        monkeypatch.setattr(adjust, "best_fit_site",
                            lambda case, run_dir, tooth, matching_diameter_mm,
                            apply: _outcome(operation="best-fit",
                                            nudge={"cumulative_deg": 9.9},
                                            best_fit={"matching_diameter_mm": 0.4}))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "mark", "point": [1.0, 2.0, 3.0]},
            {"kind": "best_fit", "matching_diameter_mm": 0.4},
        ]}, summary)
        row = summary["sites"][0]
        # the demo's 2026-07-25 rule, kept on re-apply: a best-fit is a 6-DoF
        # move, not a clock nudge — it must not overwrite the cumulative rotation
        assert row["nudge"] == {"cumulative_deg": 4.0}
        assert row["best_fit"] == {"matching_diameter_mm": 0.4}

    def test_a_pairs_fit_rebuilds_the_correspondence_block_it_stands_on(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            adjust, "align_to_correspondence",
            lambda case, run_dir, tooth, pairs, fit_version:
            _outcome(pairs=[{"observation": "midpoint"},
                            {"observation": "direction"}],
                     residual_rms_mm=0.05))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "pairs": [
                {"scan_point": [0.0, 0.0, 0.0], "scan_point_end": [1.0, 0.0, 0.0]},
                {"scan_point": [2.0, 0.0, 0.0]}]},
        ]}, summary)
        # the interactive fold's own block, from the entry's own pair count —
        # no longer the documented under-claim (§10-AD's "this increment")
        assert summary["sites"][0]["correspondence"] == {
            "pairs": 2, "observations": 2, "spans": 1, "directions_used": 1,
            "max_pairs": 8, "residual_rms_mm": 0.05,
            "cross_checked": adjust.cross_checked(2)}

    def test_a_matched_point_fit_folds_the_fold_it_was_read_by_and_what_it_moved(
            self, tmp_path, monkeypatch):
        """The client's ruling made the pair fold two folds (2026-08-15). A row that
        says only "3 pairs, 0.08mm RMS" no longer describes the act: the same numbers
        mean different things under the two, so the block names which one moved the
        part and by how far."""
        monkeypatch.setattr(
            adjust, "align_to_correspondence",
            lambda case, run_dir, tooth, pairs, fit_version:
            _outcome(pairs=[{"observation": "point"}, {"observation": "point"}],
                     residual_rms_mm=0.08, translation_mm=0.4123,
                     fit_version=adjust.PAIR_FIT_MATCHED_POINTS))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "pairs": [{"scan_point": [0.0, 0.0, 0.0]},
                                        {"scan_point": [2.0, 0.0, 0.0]}]},
        ]}, summary)
        block = summary["sites"][0]["correspondence"]
        assert block["fit_version"] == adjust.PAIR_FIT_MATCHED_POINTS
        assert block["translation_mm"] == 0.4123
        assert block["spans"] == 0 and block["directions_used"] == 0

    def test_an_azimuth_only_fit_carries_no_translation_key_at_all(
            self, tmp_path, monkeypatch):
        """A fold that cannot translate must not publish a 0.0 that reads as "we
        measured no movement" — the omission IS the honest statement."""
        monkeypatch.setattr(
            adjust, "align_to_correspondence",
            lambda case, run_dir, tooth, pairs, fit_version:
            _outcome(pairs=[{"observation": "midpoint"}], residual_rms_mm=None,
                     fit_version=adjust.PAIR_FIT_AZIMUTH_ONLY))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "pairs": [{"scan_point": [0.0, 0.0, 0.0],
                                         "scan_point_end": [1.0, 0.0, 0.0]}]},
        ]}, summary)
        block = summary["sites"][0]["correspondence"]
        assert block["fit_version"] == adjust.PAIR_FIT_AZIMUTH_ONLY
        assert "translation_mm" not in block


class TestEvidenceIsReAppliedUnderTheFoldItWasMeasuredUnder:
    """THE VERSIONING SEAM (client ruling 2026-08-15, the re-click doctrine applied to
    a semantics change). §10-AD promises that a re-run re-applies the operator's own
    measurements; §10-AR.1 records what happens when the meaning underneath them
    changes — the backend must NEVER self-correct calibrated operator input, so the
    honest move is to read old evidence the way it was recorded and say so.

    The marker rides the evidence entry itself (``fit_version``, stamped by the BFF at
    the moment of the act). An entry without one predates the ruling."""

    def _capture(self, monkeypatch):
        seen = []
        monkeypatch.setattr(
            adjust, "align_to_correspondence",
            lambda case, run_dir, tooth, pairs, fit_version:
            seen.append(fit_version) or _outcome())
        return seen

    def test_evidence_without_a_marker_re_applies_azimuth_only(
            self, tmp_path, monkeypatch):
        seen = self._capture(monkeypatch)
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "pairs": [{"scan_point": [0.0, 0.0, 0.0]}]}]},
            _summary())
        assert seen == [adjust.PAIR_FIT_AZIMUTH_ONLY]

    def test_evidence_stamped_by_todays_tool_re_applies_matched_points(
            self, tmp_path, monkeypatch):
        seen = self._capture(monkeypatch)
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "fit_version": adjust.PAIR_FIT_MATCHED_POINTS,
             "pairs": [{"scan_point": [0.0, 0.0, 0.0]}]}]},
            _summary())
        assert seen == [adjust.PAIR_FIT_MATCHED_POINTS]

    def test_an_unreadable_marker_falls_back_to_the_older_interpretation(
            self, tmp_path, monkeypatch):
        """Fail-closed on the SEMANTICS: a marker nobody can read is not a licence to
        re-interpret a recorded measurement."""
        seen = self._capture(monkeypatch)
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "fit_version": "two",
             "pairs": [{"scan_point": [0.0, 0.0, 0.0]}]}]},
            _summary())
        assert seen == [adjust.PAIR_FIT_AZIMUTH_ONLY]

    def test_the_block_belongs_to_the_act_that_produced_it(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            adjust, "align_to_correspondence",
            lambda case, run_dir, tooth, pairs, fit_version:
            _outcome(pairs=[{"observation": "midpoint"}], residual_rms_mm=None))
        monkeypatch.setattr(adjust, "align_to_mark",
                            lambda case, run_dir, tooth, point:
                            _outcome(operation="align-to-mark"))
        summary = _summary()
        _reapply_evidence(_case(tmp_path), tmp_path, {13: [
            {"kind": "pairs", "pairs": [{"scan_point": [0.0, 0.0, 0.0]}]},
            {"kind": "mark", "point": [1.0, 2.0, 3.0]},
        ]}, summary)
        # the later mark replaced the pose the pairs measured — the sealed row
        # must not keep describing a correspondence that no longer exists
        assert "correspondence" not in summary["sites"][0]


@real_only
@pytest.mark.slow  # one FULL run with evidence riding the selection
class TestReApplyOnTheRealTree:
    def test_a_run_handed_evidence_reports_its_receipts(self, tmp_path):
        cases = {c.id: c for c in discover_cases(REAL)}
        case = cases.get("neodent-gm") or cases.get("doctor-neodent-gm")
        assert case is not None, sorted(cases)
        teeth = [int(s["tooth"]) for s in case.suggested_sites][:1]
        selection = RunSelection(
            model="neodent-gm",
            construction_path="dess/neodent-gm-scanbody.stl",
            variants={t: "5020" for t in teeth}, jaw=None,
            gingival_offset_mm=0.2,
            alignment_evidence={teeth[0]: [
                {"kind": "best_fit", "applied_at": "2026-08-02T00:00:00+00:00"}]})
        out_dir = tmp_path / "runs" / "with-evidence"
        out_dir.mkdir(parents=True)
        summary = run_case(case, selection, out_dir)
        (receipt,) = summary["evidence_reapplied"]
        assert receipt["kind"] == "best_fit"
        # applied, or the automation already stood there — both are honest lands;
        # a refusal here would mean the tool's own gates said no, also a receipt
        assert receipt["outcome"] in ("applied", "already-optimal", "refused")
        # the on-disk report says exactly what the summary says
        report = json.loads(
            (out_dir / f"{case.id}-auto-report.json").read_text())
        assert report["evidence_reapplied"] == summary["evidence_reapplied"]
