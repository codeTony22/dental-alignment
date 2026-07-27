"""The doctor verification layer on the live-demo server.

Two contracts: (1) every served run row carries its acceptance evaluation (derived at
serve time, never persisted), and (2) POST /confirm-alignment records the doctor's
manual sign-off — into the site row, run.json and the run-history provenance stream —
without ever touching a pose, a gate computation, or a shipped artifact. Exercised
against the real live-demo artifacts (cap7030), handlers called directly — the pattern
of tests/test_server_nudge.py.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import case_prep.server as srv
from case_prep.server import ConfirmAlignmentIn, RunIn, SiteIn

CASE_ID = "cap7030-zimmer-4.5"
TOOTH = 29
REAL_OUT = srv.OUT  # captured at import, before any monkeypatching


@pytest.fixture()
def demo_out(tmp_path, monkeypatch):
    """A disposable copy of the case's live-demo artifacts + an empty run cache, so
    confirmations never mutate the real demo package and cache state is per-test."""
    src = REAL_OUT / CASE_ID
    if CASE_ID not in srv.CASES or not (src / "run.json").exists():
        pytest.skip("cap7030 live-demo artifacts not present on this machine")
    shutil.copytree(src, tmp_path / CASE_ID)
    monkeypatch.setattr(srv, "OUT", tmp_path)
    monkeypatch.setattr(srv, "_cache", {})
    return tmp_path


def _cached_body(out: Path) -> RunIn:
    """A run request whose payload hash matches the copied run.json, WITHOUT running the
    pipeline: rewrite the saved _key to the hash of a minimal request for the same site
    (same technique the server itself uses to key the cache). The request carries the
    operator's DECODING SELECTION explicitly — since 2026-07-25 a run without one is a
    422, and the selection is part of the cache key."""
    cfg = srv.CASES[CASE_ID]
    body = RunIn(sites=[SiteIn(tooth=TOOTH, center=[12.41, 7.62, 18.36])],
                 model=cfg["suggested_model"],
                 construction_path=cfg["suggested_construction"])
    key = srv._run_cache_key(CASE_ID, body, body.model, body.construction_path,
                             cfg["jaw"])
    disk = out / CASE_ID / "run.json"
    saved = json.loads(disk.read_text())
    saved["_key"] = key
    disk.write_text(json.dumps(saved, default=str))
    return body


def _package_digest(out: Path) -> str:
    pkg = out / CASE_ID / "package"
    h = hashlib.sha256()
    for f in sorted(pkg.rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _run_row(out: Path) -> dict:
    saved = json.loads((out / CASE_ID / "run.json").read_text())
    return next(r for r in saved["summary"]["sites"] if r["tooth"] == TOOTH)


def _confirm_events(out: Path):
    hist = out / "run-history.jsonl"
    if not hist.exists():
        return []
    return [json.loads(ln) for ln in hist.read_text().strip().splitlines()
            if json.loads(ln).get("event") == "confirm-alignment"]


class TestAcceptanceOnRunPayload:
    def test_served_run_rows_carry_the_acceptance_evaluation(self, demo_out):
        out = srv.run(CASE_ID, _cached_body(demo_out))
        assert out["cached"] is True
        row = next(r for r in out["summary"]["sites"] if r["tooth"] == TOOTH)
        acceptance = row["acceptance"]
        keys = [m["key"] for m in acceptance["metrics"]]
        assert "fit_avg_mm" in keys and "rotation_deg" in keys
        fit = next(m for m in acceptance["metrics"] if m["key"] == "fit_avg_mm")
        # cap7030's real fit avg is ~0.42 — inside the 0.8 pass band
        assert fit["band"] == "pass"
        assert fit["industry_ref"]["value"].startswith("RealGUIDE")
        assert acceptance["overall"]["band"] in ("pass", "review", "fail")
        assert isinstance(acceptance["overall"]["missing"], list)

    def test_acceptance_is_derived_never_persisted_into_run_json(self, demo_out):
        srv.run(CASE_ID, _cached_body(demo_out))
        assert "acceptance" not in _run_row(demo_out)


class TestConfirmAlignmentContract:
    def test_unknown_case_404s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.confirm_alignment("no-such-case", TOOTH,
                                  ConfirmAlignmentIn(confirmed=True))
        assert exc.value.status_code == 404

    def test_unknown_tooth_404s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.confirm_alignment(CASE_ID, 99, ConfirmAlignmentIn(confirmed=True))
        assert exc.value.status_code == 404
        assert "run the automation first" in exc.value.detail

    def test_case_without_a_run_404s(self, demo_out):
        (demo_out / CASE_ID / "run.json").unlink()
        with pytest.raises(HTTPException) as exc:
            srv.confirm_alignment(CASE_ID, TOOTH, ConfirmAlignmentIn(confirmed=True))
        assert exc.value.status_code == 404

    def test_note_beyond_the_cap_is_rejected(self):
        with pytest.raises(ValidationError, match="500"):
            ConfirmAlignmentIn(confirmed=True, note="x" * 501)

    def test_blank_note_collapses_to_none(self):
        assert ConfirmAlignmentIn(confirmed=True, note="   ").note is None

    def test_confirm_records_sign_off_without_touching_any_artifact(self, demo_out):
        pkg_before = _package_digest(demo_out)
        out = srv.confirm_alignment(
            CASE_ID, TOOTH,
            ConfirmAlignmentIn(confirmed=True, note="codes visually aligned"))

        assert out["tooth"] == TOOTH
        assert out["doctor_confirmation"]["confirmed"] is True
        assert out["doctor_confirmation"]["note"] == "codes visually aligned"
        assert out["doctor_confirmation"]["ts"]
        assert out["acceptance_overall"] in ("pass", "review", "fail", "missing")

        # persisted into the site row on disk...
        rec = _run_row(demo_out)["doctor_confirmation"]
        assert rec["confirmed"] is True
        assert rec["note"] == "codes visually aligned"
        # ...audited in the provenance stream, with what the numbers said at sign-off...
        events = _confirm_events(demo_out)
        assert len(events) == 1
        assert events[0]["confirmed"] is True
        assert events[0]["acceptance_overall"] == out["acceptance_overall"]
        # ...and every shipped artifact byte-identical: a confirmation is a recorded
        # human judgment, never a pose or gate change
        assert _package_digest(demo_out) == pkg_before

    def test_reconfirm_and_retract_update_the_record(self, demo_out):
        srv.confirm_alignment(CASE_ID, TOOTH,
                              ConfirmAlignmentIn(confirmed=True, note="first look"))
        srv.confirm_alignment(CASE_ID, TOOTH, ConfirmAlignmentIn(confirmed=False))
        rec = _run_row(demo_out)["doctor_confirmation"]
        assert rec["confirmed"] is False
        assert rec["note"] is None
        events = _confirm_events(demo_out)
        assert [e["confirmed"] for e in events] == [True, False]

    def test_confirmation_comes_back_with_the_run_payload(self, demo_out):
        """The reload path: confirm, then serve the (cached) run — the row carries both
        the persisted confirmation and the fresh acceptance evaluation."""
        body = _cached_body(demo_out)
        srv.confirm_alignment(CASE_ID, TOOTH,
                              ConfirmAlignmentIn(confirmed=True, note="ok"))
        out = srv.run(CASE_ID, body)
        row = next(r for r in out["summary"]["sites"] if r["tooth"] == TOOTH)
        assert row["doctor_confirmation"]["confirmed"] is True
        assert row["doctor_confirmation"]["note"] == "ok"
        assert row["acceptance"]["overall"]["band"] in ("pass", "review", "fail")


def test_measured_wave_fields_reach_the_served_acceptance_payload():
    """Panel-completion (§8 item 12), serve-time contract: a run row carrying the
    2026-07-24 measured fields comes back with those metrics BANDED in the derived
    acceptance payload — no server field-plumbing required (evaluate_acceptance reads
    the row generically), which is exactly what this pins. No demo artifacts needed:
    _with_verification is pure on the result dict."""
    row = {"tooth": 29,
           "fit": {"avg_mm": 0.42, "max_mm": 1.2},
           "deviation_rms_mm": 0.19,
           "rim_off_centre": 0.004,
           "delivered_channel_vs_recess": 0.31,
           "delivered_channel_vs_cap_channel": 0.02,
           "variant": {"identified": "6030", "declared": "6030",
                       "candidates_too_close": False}}
    served = srv._with_verification({"summary": {"sites": [row]}})
    acceptance = served["summary"]["sites"][0]["acceptance"]
    bands = {m["key"]: m["band"] for m in acceptance["metrics"]}
    assert bands["deviation_rms_mm"] == "pass"
    assert bands["rim_off_centre_mm"] == "pass"
    assert bands["delivered_channel_vs_recess_mm"] == "pass"
    missing = set(acceptance["overall"]["missing"])
    assert not ({"deviation_rms_mm", "rim_off_centre_mm",
                 "delivered_channel_vs_recess_mm"} & missing)
