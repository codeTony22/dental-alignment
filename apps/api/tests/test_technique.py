"""Technique + adjust routes — stubbed physics, full signal envelope."""
from __future__ import annotations

from case_prep.application.adjust import AdjustOutcome, AdjustRefused, AlreadyOptimal
from case_prep.application.signals import SIGNAL_GROUPS
from case_prep.application.technique import TechniqueAsk, TechniqueResult

from conftest import CASE


def outcome(**overrides) -> AdjustOutcome:
    values = dict(
        tooth=4, operation="best-fit", detail="refined 0.12 mm", applied=True,
        best_fit={"rms_mm": 0.18},
        deviation={"deviation_rms_mm": 0.40, "deviation_p90_mm": 0.66},
        translation_mm=None, fit_version=None, seat_branch=None, seat_band_mm=None,
    )
    values.update(overrides)
    return AdjustOutcome(**values)


def stub_best_fit(monkeypatch, result=None, raises=None):
    calls = []

    def stub(case, run_dir, tooth, matching_diameter_mm=0.3, apply=True):
        calls.append({"apply": apply, "diameter": matching_diameter_mm, "tooth": tooth})
        if raises is not None:
            raise raises
        return result if result is not None else outcome(applied=apply)

    monkeypatch.setattr("case_api.resources.adjust.best_fit_site", stub)
    monkeypatch.setattr("case_prep.application.technique.best_fit_site", stub)
    return calls


def stub_reads(monkeypatch):
    monkeypatch.setattr(
        "case_api.resources.adjust.clock_landmarks",
        lambda template: [{"id": "code-1", "kind": "notch"}])
    monkeypatch.setattr(
        "case_api.resources.adjust.load_site",
        lambda *a, **k: type("C", (), {"template": object()})())
    monkeypatch.setattr(
        "case_api.resources.adjust.seated_payload",
        lambda *a, **k: {"tooth": 4, "stats": {"rms_mm": 0.43}})
    monkeypatch.setattr(
        "case_prep.application.technique.clock_landmarks",
        lambda template: [{"id": "code-1", "kind": "notch"}])
    monkeypatch.setattr(
        "case_prep.application.technique.load_site",
        lambda *a, **k: type("C", (), {"template": object()})())
    monkeypatch.setattr(
        "case_prep.application.technique.seated_payload",
        lambda *a, **k: {"tooth": 4, "stats": {"rms_mm": 0.43}})


class TestCases:
    def test_lists_the_synthetic_case(self, client):
        res = client.get("/api/v1/cases")
        assert res.status_code == 200
        assert res.json()["cases"][0]["id"] == CASE

    def test_unknown_case_is_404(self, client):
        assert client.get("/api/v1/cases/nope").status_code == 404


class TestSignals:
    def test_full_taxonomy(self, client, monkeypatch):
        stub_reads(monkeypatch)
        res = client.get(f"/api/v1/cases/{CASE}/sites/4/signals")
        assert res.status_code == 200
        body = res.json()
        assert body["group_names"] == list(SIGNAL_GROUPS)
        for name in SIGNAL_GROUPS:
            assert name in body["groups"]
        assert body["groups"]["acceptance"]["catalog_keys"]
        assert body["groups"]["landmarks"]["items"][0]["id"] == "code-1"

    def test_a_tooth_the_run_never_aligned_is_422(self, client):
        res = client.get(f"/api/v1/cases/{CASE}/sites/99/signals")
        assert res.status_code == 422
        assert "never aligned" in res.json()["detail"]


class TestAdjustActs:
    def test_best_fit_measure_only(self, client, monkeypatch):
        stub_best_fit(monkeypatch, result=outcome(applied=False, detail="measured"))
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/best-fit",
            json={"matching_diameter_mm": 0.3, "apply": False})
        assert res.status_code == 200
        assert res.json()["outcome"]["applied"] is False
        assert "translation_mm" in res.json()["outcome"]

    def test_already_optimal_is_409_structured(self, client, monkeypatch):
        stub_best_fit(monkeypatch, raises=AlreadyOptimal(
            "already the best fit", 0.3, 0.6))
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/best-fit",
            json={"matching_diameter_mm": 0.3, "apply": True})
        assert res.status_code == 409
        assert res.json()["detail"]["kind"] == "already_optimal"
        assert res.json()["detail"]["suggested_diameter_mm"] == 0.6

    def test_gate_refusal_is_409(self, client, monkeypatch):
        stub_best_fit(monkeypatch, raises=AdjustRefused("trust region"))
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/best-fit",
            json={"matching_diameter_mm": 0.3})
        assert res.status_code == 409
        assert "trust region" in res.json()["detail"]

    def test_extra_fields_are_forbidden(self, client):
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/rotation",
            json={"step_deg": 1.0, "status": "ready"})
        assert res.status_code == 422


class TestTechnique:
    def test_unknown_mode_is_422(self, client):
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/technique",
            json={"mode": "magic"})
        assert res.status_code == 422

    def test_deterministic_returns_every_signal_group(self, client, monkeypatch):
        stub_reads(monkeypatch)
        stub_best_fit(monkeypatch, result=outcome())
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/technique",
            json={"mode": "deterministic", "apply": True})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["mode"] == "deterministic"
        assert body["status"] == "applied"
        assert body["signal_groups"] == list(SIGNAL_GROUPS)
        assert body["signals_after"]["group_names"] == list(SIGNAL_GROUPS)

    def test_intelligence_walks_the_mcp_tools(self, client, monkeypatch):
        stub_reads(monkeypatch)
        stub_best_fit(monkeypatch, result=outcome(applied=False, detail="measured"))

        def run(case, run_dir, tooth, row, ask: TechniqueAsk):
            assert ask.mode == "intelligence"
            return TechniqueResult(
                mode="intelligence", status="measured",
                detail="walked",
                signals_before={"group_names": list(SIGNAL_GROUPS), "groups": {}},
                signals_after={"group_names": list(SIGNAL_GROUPS), "groups": {}},
            )

        monkeypatch.setattr("case_api.resources.adjust.run_technique", run)
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/technique",
            json={"mode": "intelligence", "apply": False})
        assert res.status_code == 200
        assert res.json()["mode"] == "intelligence"
        assert res.json()["signal_groups"] == list(SIGNAL_GROUPS)

    def test_live_intelligence_path_emits_read_trace(self, client, monkeypatch):
        stub_reads(monkeypatch)
        stub_best_fit(monkeypatch, result=outcome(applied=False, detail="measured"))
        res = client.post(
            f"/api/v1/cases/{CASE}/sites/4/technique",
            json={"mode": "intelligence", "apply": False})
        assert res.status_code == 200, res.text
        names = [step["name"] for step in res.json()["trace"]]
        assert "get_site_signals" in names
        assert "get_landmarks" in names
        assert "get_acceptance" in names
        assert "dry_run_best_fit" in names
        assert "commit_best_fit" not in names
