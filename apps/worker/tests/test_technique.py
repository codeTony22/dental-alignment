"""Deterministic vs Intelligence — two strategies, one adjust seam."""
from __future__ import annotations

from pathlib import Path

import pytest

from case_prep.application.adjust import AdjustOutcome, AdjustRefused, AlreadyOptimal
from case_prep.application.signals import SIGNAL_GROUPS
from case_prep.application.technique import (MODE_DETERMINISTIC, MODE_INTELLIGENCE,
                                            TOOL_COMMIT, TOOL_DRY_RUN, TOOL_READ,
                                            TechniqueAsk, run_technique)
from case_prep.application.cases import CaseRecord


def _case() -> CaseRecord:
    return CaseRecord(
        id="neodent-gm", doctor="Doctor Neodent GM", jaw="upper",
        scan=Path("/tmp/upper_jaw.stl"), data_root=Path("/tmp"),
        suggested_model="neodent-gm", suggested_construction=None,
        suggested_sites=(),
    )


def _row(tooth: int = 4) -> dict:
    return {
        "tooth": tooth, "seat_method": "rim-seat",
        "fit": {"avg_mm": 0.21, "max_mm": 0.62, "n": 10},
        "rim_agreement_mm": 0.07, "rim_arc_bins": 12,
        "clocking": {"evidence": "codes", "rotation_unverified": False,
                     "notch_corr": 0.51, "notch_prominence": 0.16},
        "guidance": {"level": "ready", "actions": []},
        "confidence": {"grade": "high"},
        "variant": {"identified": "5020", "declared": "5020"},
        "deviation_rms_mm": 0.43, "deviation_p90_mm": 0.71,
    }


def _outcome(**overrides) -> AdjustOutcome:
    values = dict(
        tooth=4, operation="best-fit", detail="refined 0.12 mm",
        applied=True, best_fit={"rms_mm": 0.18, "n_matched": 40},
        deviation={"deviation_rms_mm": 0.40, "deviation_p90_mm": 0.66},
    )
    values.update(overrides)
    return AdjustOutcome(**values)


@pytest.fixture
def patched(monkeypatch):
    calls = []

    def best_fit(case, run_dir, tooth, matching_diameter_mm=0.3, apply=True):
        calls.append({"tool": "best_fit", "apply": apply,
                      "diameter": matching_diameter_mm, "tooth": tooth})
        return _outcome(applied=apply, detail="measured" if not apply else "refined 0.12 mm")

    monkeypatch.setattr("case_prep.application.technique.best_fit_site", best_fit)
    monkeypatch.setattr(
        "case_prep.application.technique.clock_landmarks",
        lambda template: [{"id": "code-1", "kind": "notch", "point": [0, 0, 1],
                           "lever_arm_mm": 2.1, "azimuth_deg": 12.0}])
    monkeypatch.setattr(
        "case_prep.application.technique.load_site",
        lambda case, run_dir, tooth: type("Ctx", (), {"template": object()})())
    monkeypatch.setattr(
        "case_prep.application.technique.seated_payload",
        lambda case, run_dir, tooth: {"tooth": tooth, "preview": False,
                                      "stats": {"rms_mm": 0.43, "p90_mm": 0.71}})
    return calls


def test_unknown_mode_is_invalid():
    with pytest.raises(Exception) as exc:
        run_technique(_case(), Path("/tmp/run"), 4, _row(),
                      TechniqueAsk(mode="magic"))
    assert "deterministic" in str(exc.value)


def test_deterministic_is_one_best_fit_and_still_emits_every_signal_group(patched):
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(mode=MODE_DETERMINISTIC, apply=True))
    assert result.status == "applied"
    assert [c["tool"] for c in patched] == ["best_fit"]
    assert patched[0]["apply"] is True
    assert result.signals_after["group_names"] == list(SIGNAL_GROUPS)
    assert [step.name for step in result.trace] == ["commit_best_fit"]
    assert result.trace[0].classification == TOOL_COMMIT


def test_deterministic_ignores_operator_pairs(monkeypatch, patched):
    from case_prep.application.adjust import Correspondence

    def boom(*_a, **_k):
        raise AssertionError("deterministic must not walk fit-by-points")

    monkeypatch.setattr("case_prep.application.technique.align_to_correspondence", boom)
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(
            mode=MODE_DETERMINISTIC, apply=True,
            pairs=[Correspondence(scan_point=[1, 2, 3], feature_id="code-1")]))
    assert result.status == "applied"
    assert "commit_fit_by_points" not in [step.name for step in result.trace]


def test_intelligence_walks_every_read_then_dry_run_then_commit(patched):
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(mode=MODE_INTELLIGENCE, apply=True))
    names = [step.name for step in result.trace]
    assert names[:4] == [
        "get_landmarks", "get_seated", "get_site_signals", "get_acceptance",
    ]
    assert names.count("dry_run_best_fit") == 1
    assert names.count("commit_best_fit") == 1
    assert {step.classification for step in result.trace if step.name.startswith("get_")} == {TOOL_READ}
    assert any(step.classification == TOOL_DRY_RUN for step in result.trace)
    assert result.signals_after["groups"]["landmarks"]["items"][0]["id"] == "code-1"
    assert result.proposals["landmarks"][0]["id"] == "code-1"
    assert patched[0]["apply"] is False
    assert patched[1]["apply"] is True


def test_intelligence_already_optimal_does_not_commit(monkeypatch):
    def refuse(*_a, **_k):
        raise AlreadyOptimal("already the best fit in this band",
                             matching_diameter_mm=0.3, suggested_diameter_mm=0.6)

    monkeypatch.setattr("case_prep.application.technique.best_fit_site", refuse)
    monkeypatch.setattr(
        "case_prep.application.technique.clock_landmarks", lambda template: [])
    monkeypatch.setattr(
        "case_prep.application.technique.load_site",
        lambda *a, **k: type("Ctx", (), {"template": object()})())
    monkeypatch.setattr(
        "case_prep.application.technique.seated_payload",
        lambda *a, **k: {"stats": {}})
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(mode=MODE_INTELLIGENCE, apply=True))
    assert result.status == "already_optimal"
    assert result.refusals[0]["kind"] == "already_optimal"
    assert result.refusals[0]["suggested_diameter_mm"] == 0.6
    assert "commit_best_fit" not in [step.name for step in result.trace]


def test_intelligence_commits_operator_pairs_via_the_adjust_tool(monkeypatch, patched):
    from case_prep.application.adjust import Correspondence

    calls = []

    def fit(case, run_dir, tooth, pairs, **_k):
        calls.append(pairs)
        return _outcome(operation="fit-by-points", detail="fitted two pairs")

    monkeypatch.setattr("case_prep.application.technique.align_to_correspondence", fit)
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(
            mode=MODE_INTELLIGENCE, apply=True,
            pairs=[Correspondence(scan_point=[1.0, 2.0, 3.0], feature_id="code-1")]))
    assert calls, "Intelligence must call align_to_correspondence with the supplied pairs"
    assert "commit_fit_by_points" in [step.name for step in result.trace]
    assert result.status == "applied"
    assert result.outcome is not None
    assert result.outcome.operation == "fit-by-points"


def test_intelligence_refuses_without_inventing_a_metric(monkeypatch):
    def refuse(*_a, **_k):
        raise AdjustRefused("the refinement left the trust region")

    monkeypatch.setattr("case_prep.application.technique.best_fit_site", refuse)
    monkeypatch.setattr(
        "case_prep.application.technique.clock_landmarks", lambda template: [])
    monkeypatch.setattr(
        "case_prep.application.technique.load_site",
        lambda *a, **k: type("Ctx", (), {"template": object()})())
    monkeypatch.setattr(
        "case_prep.application.technique.seated_payload",
        lambda *a, **k: {"stats": {}})
    result = run_technique(
        _case(), Path("/tmp/run"), 4, _row(),
        TechniqueAsk(mode=MODE_INTELLIGENCE, apply=True))
    assert result.status == "refused"
    assert "trust region" in result.detail
    # residue stays the row's own number — the refusal did not mint a substitute
    assert result.signals_after["groups"]["residue"]["deviation_rms_mm"] == 0.43
