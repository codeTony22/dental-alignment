"""MCP tool handlers — stubbed physics, real caseflow + signal envelope."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alignment_mcp.tools import ToolContext, ToolError, call_tool
from case_prep.application.adjust import AdjustOutcome
from case_prep.application.signals import SIGNAL_GROUPS


CASE = "neodent-gm"


def _tree(tmp_path: Path):
    data = tmp_path / "data"
    (data / "library/caps/neodent-gm").mkdir(parents=True)
    (data / "library/caps/neodent-gm/neodent-gm-5020.stl").touch()
    scans = data / "scans/doctor-neodent-gm"
    scans.mkdir(parents=True)
    (scans / "upper_jaw.stl").touch()
    (scans / "sites.json").write_text(json.dumps({
        "suggested_sites": [{"tooth": 4, "center": [1, 2, 3]}],
    }))
    product = tmp_path / "product"
    run_id = "run-1"
    run_dir = product / CASE / "runs" / run_id
    run_dir.mkdir(parents=True)
    row = {
        "tooth": 4, "seat_method": "rim-seat",
        "fit": {"avg_mm": 0.21, "max_mm": 0.62, "n": 10},
        "rim_agreement_mm": 0.07, "rim_arc_bins": 12,
        "clocking": {"evidence": "codes", "rotation_unverified": False,
                     "notch_corr": 0.51, "notch_prominence": 0.16},
        "guidance": {"level": "ready", "actions": []},
        "confidence": {"grade": "high"},
        "variant": {"identified": "5020", "declared": "5020"},
        "deviation_rms_mm": 0.43, "deviation_p90_mm": 0.71,
    }
    (product / CASE / "session.json").write_text(json.dumps({
        "run": {"state": "done", "run_id": run_id, "job_id": run_id,
                "summary": {"sites": [row]}},
    }))
    return ToolContext(data, product), row


def _outcome(**overrides) -> AdjustOutcome:
    values = dict(tooth=4, operation="best-fit", detail="refined", applied=True)
    values.update(overrides)
    return AdjustOutcome(**values)


@pytest.fixture
def ctx(tmp_path):
    return _tree(tmp_path)[0]


def test_list_cases_reads_directory_shape(ctx):
    payload = call_tool("list_cases", {}, ctx)
    assert payload["cases"][0]["id"] == CASE


def test_get_site_signals_emits_every_group(monkeypatch, ctx):
    monkeypatch.setattr(
        "alignment_mcp.tools.clock_landmarks",
        lambda template: [{"id": "code-1"}])
    monkeypatch.setattr(
        "alignment_mcp.tools.load_site",
        lambda *a, **k: type("C", (), {"template": object()})())
    monkeypatch.setattr(
        "alignment_mcp.tools.seated_payload",
        lambda *a, **k: {"stats": {"rms_mm": 0.4}})
    payload = call_tool("get_site_signals", {"case_id": CASE, "tooth": 4}, ctx)
    assert payload["group_names"] == list(SIGNAL_GROUPS)
    assert payload["groups"]["landmarks"]["items"][0]["id"] == "code-1"


def test_dry_run_best_fit_does_not_apply(monkeypatch, ctx):
    seen = []

    def stub(case, run_dir, tooth, matching_diameter_mm=0.3, apply=True):
        seen.append(apply)
        return _outcome(applied=apply)

    monkeypatch.setattr("alignment_mcp.tools.best_fit_site", stub)
    payload = call_tool(
        "dry_run_best_fit",
        {"case_id": CASE, "tooth": 4, "matching_diameter_mm": 0.3}, ctx)
    assert seen == [False]
    assert payload["outcome"]["applied"] is False


def test_unknown_case_is_404(ctx):
    with pytest.raises(ToolError) as exc:
        call_tool("get_case", {"case_id": "nope"}, ctx)
    assert exc.value.code == 404


def test_technique_intelligence_uses_the_shared_runner(monkeypatch, ctx):
    from case_prep.application.technique import TechniqueResult

    seen = []

    def stub(case, run_dir, tooth, row, ask):
        seen.append(ask.mode)
        return TechniqueResult(
            mode=ask.mode, status="measured", detail="walked",
            signals_before={"group_names": list(SIGNAL_GROUPS)},
            signals_after={"group_names": list(SIGNAL_GROUPS)},
        )

    monkeypatch.setattr("alignment_mcp.tools.run_technique", stub)
    payload = call_tool(
        "run_alignment_technique",
        {"case_id": CASE, "tooth": 4, "mode": "intelligence", "apply": False},
        ctx)
    assert seen == ["intelligence"]
    assert payload["mode"] == "intelligence"
    assert payload["signal_groups"] == list(SIGNAL_GROUPS)
