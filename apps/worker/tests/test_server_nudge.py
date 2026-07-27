"""The operator rotation nudge at the review gate.

The nudge is a PROPOSAL: the same ring-fixed kinematics and certification gates that
judge the pipeline's own clocking judge the operator's rotation — refusals are 409s
with the reason, adoptions re-emit the site's shipped record (aligned-cap STL +
implant.json) and land in run-history.jsonl. Exercised against the real live-demo
artifacts (cap7030), same data the demo serves; handlers are called directly, the
pattern of tests/test_server.py.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import case_prep.server as srv
from case_prep.server import NudgeIn

CASE_ID = "cap7030-zimmer-4.5"
TOOTH = 29
REAL_OUT = srv.OUT  # captured at import, before any monkeypatching


@pytest.fixture()
def demo_out(tmp_path, monkeypatch):
    """A disposable copy of the case's live-demo artifacts, so nudges never mutate
    the real demo package."""
    src = REAL_OUT / CASE_ID
    if CASE_ID not in srv.CASES or not (src / "package").exists():
        pytest.skip("cap7030 live-demo artifacts not present on this machine")
    shutil.copytree(src, tmp_path / CASE_ID)
    monkeypatch.setattr(srv, "OUT", tmp_path)
    return tmp_path


def _implant(out: Path) -> dict:
    return json.loads(
        (out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-implant.json").read_text())


def _history_events(out: Path):
    hist = out / "run-history.jsonl"
    if not hist.exists():
        return []
    return [json.loads(ln) for ln in hist.read_text().strip().splitlines()
            if json.loads(ln).get("event") == "nudge-rotation"]


class TestNudgeContract:
    def test_unknown_tooth_404s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.nudge_rotation(CASE_ID, 99, NudgeIn(delta_deg=3.0))
        assert exc.value.status_code == 404
        assert "run the automation first" in exc.value.detail

    def test_step_beyond_45_degrees_is_rejected(self):
        with pytest.raises(ValidationError, match="45"):
            NudgeIn(delta_deg=90.0)

    def test_nudge_applies_then_reset_restores_the_certified_pose(self, demo_out):
        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()

        out = srv.nudge_rotation(CASE_ID, TOOTH, NudgeIn(delta_deg=3.0))
        assert out["applied_delta_deg"] == 3.0
        assert out["cumulative_deg"] == 3.0
        assert out["stability_excess_mm"] is not None
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        # the codes are re-read at the nudged pose for the operator's residual display
        assert "notch_shift_deg" in out["clocking"]
        assert "notch_corr" in out["clocking"]

        after = _implant(demo_out)
        R0 = np.asarray(before["pose_matrix"], float)[:3, :3]
        R1 = np.asarray(after["pose_matrix"], float)[:3, :3]
        # a rotation about the part's OWN axis: the axis itself must not move...
        assert float(R0[:, 2] @ R1[:, 2]) > 0.999
        # ...while the pose genuinely rotated by ~3 degrees
        rel = R0.T @ R1
        angle = float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0])))
        assert angle == pytest.approx(3.0, abs=0.3)
        assert after["nudge"]["cumulative_deg"] == 3.0
        assert cap.read_bytes() != cap_before, "the viewer's STL must be re-emitted"

        # the cached run row carries the nudged state so a page reload is honest
        run = json.loads((demo_out / CASE_ID / "run.json").read_text())
        row = next(r for r in run["summary"]["sites"] if r["tooth"] == TOOTH)
        assert row["nudge"]["cumulative_deg"] == 3.0
        assert "notch_shift_deg" in row["clocking"]

        reset = srv.nudge_rotation(CASE_ID, TOOTH, NudgeIn(reset=True))
        assert reset["cumulative_deg"] == 0.0
        restored = _implant(demo_out)
        assert np.allclose(np.asarray(restored["pose_matrix"], float),
                           np.asarray(before["pose_matrix"], float), atol=1e-9)

        events = _history_events(demo_out)
        assert [e["outcome"] for e in events] == ["applied", "applied"]
        assert events[0]["delta_deg"] == 3.0
        assert events[1]["cumulative_deg"] == 0.0

    def test_unjudgeable_gates_fail_closed(self, demo_out):
        """A site the face/p90/band gates cannot judge (no scan points near the pose)
        must be refused — never adopted on the stability bound alone."""
        implant = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-implant.json"
        rec = json.loads(implant.read_text())
        W = np.asarray(rec["pose_matrix"], float)
        W[:3, 3] += 200.0  # a pure translation: ring-fixed excess is unchanged,
        implant.write_text(  # but the 8mm site crop around the pose is empty
            json.dumps({**rec, "pose_matrix": W.tolist()}))
        before = implant.read_bytes()

        with pytest.raises(HTTPException) as exc:
            srv.nudge_rotation(CASE_ID, TOOTH, NudgeIn(delta_deg=3.0))
        assert exc.value.status_code == 409
        assert "too few scan points" in exc.value.detail
        assert implant.read_bytes() == before, "a refusal must not touch the record"
        assert _history_events(demo_out)[-1]["outcome"] == "refused"

    def test_unstable_rotation_is_refused_with_reason_and_no_side_effects(
            self, demo_out, monkeypatch):
        """The gates judge the proposal — an excess over 0.35mm must 409 and leave
        every shipped artifact byte-identical."""
        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()
        monkeypatch.setattr(srv, "_ring_fixed_candidate",
                            lambda *a, **k: (np.eye(4), 0.9))

        with pytest.raises(HTTPException) as exc:
            srv.nudge_rotation(CASE_ID, TOOTH, NudgeIn(delta_deg=15.0))
        assert exc.value.status_code == 409
        assert "refused" in exc.value.detail
        assert "0.90mm" in exc.value.detail

        assert _implant(demo_out) == before
        assert cap.read_bytes() == cap_before
        events = _history_events(demo_out)
        assert events[-1]["outcome"] == "refused"
        assert events[-1]["delta_deg"] == 15.0
