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
    values = dict(tooth=13, operation="fit-by-points", detail="re-applied",
                  files=["case-x-13-implant.json"], clocking={"deg": 3.0},
                  deviation={"deviation_rms_mm": 0.11}, stale_metrics=["guidance"],
                  applied=True)
    values.update(overrides)
    return SimpleNamespace(**values)


def _summary():
    return {"sites": [{"tooth": 13, "fit": {}, "clocking": {"deg": 9.0}}],
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
                            lambda case, run_dir, tooth, pairs:
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
        # the re-derived numbers fold into the row; the rewritten file is listed once
        assert summary["sites"][0]["clocking"] == {"deg": 3.0}
        assert summary["sites"][0]["deviation_rms_mm"] == 0.11
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
        assert summary["sites"][0]["clocking"] == {"deg": 9.0}

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
