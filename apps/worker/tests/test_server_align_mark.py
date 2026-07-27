"""ALIGN-TO-MARKED-TRENCH at the review gate.

The operator marks the cap's coded cutout/trench on the scan; the server rotates the
seated cap so its NEAREST code feature lands on that mark — a PROPOSAL through the
exact nudge machinery (ring-fixed kinematics, stability bound, certification gates).
Refusals are 409s with the reason and leave every shipped artifact byte-identical;
adoptions re-emit the site's shipped record and land in run-history.jsonl with the
click + feature-match geometry. Exercised against the real live-demo artifacts
(cap7030), handlers called directly — the pattern of tests/test_server_nudge.py.
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
from case_prep.domain.clock_signature import (scan_rim_centre, template_signature,
                                              wrap_deg)
from case_prep.pipeline.auto_flow import _crowns_frame
from case_prep.server import AlignToMarkIn

CASE_ID = "cap7030-zimmer-4.5"
TOOTH = 29
REAL_OUT = srv.OUT  # captured at import, before any monkeypatching


@pytest.fixture()
def demo_out(tmp_path, monkeypatch):
    """A disposable copy of the case's live-demo artifacts, so align-to-mark never
    mutates the real demo package."""
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
            if json.loads(ln).get("event") == "align-to-mark"]


def _site_geometry():
    """The shipped pose in the site-local frame plus the clock signature and measured
    rim centre — recomputed here the same deterministic way the server does, so the
    test can CONSTRUCT a click point at an exactly-known azimuth."""
    cfg = srv.CASES[CASE_ID]
    scan = srv._scan_mesh(cfg)
    rec = json.loads((REAL_OUT / CASE_ID / "package"
                      / f"{CASE_ID}-{TOOTH}-implant.json").read_text())
    # the library is resolved from the SHIPPED record's own model (the run's explicit
    # selection), the same way the server's re-pose path does it since 2026-07-25
    library = srv._library_for(cfg, rec["implant_model"], [rec["variant_code"]])
    spec = next(sp for sp in library.specs if sp.variant == rec["variant_code"])
    template = library.template(spec)
    sig = template_signature(template)
    pts = np.asarray(scan.vertices, float)
    frame, origin, _axis = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    W = np.asarray(rec["pose_matrix"], float)
    t_now = np.eye(4)
    t_now[:3, :3] = frame.T @ W[:3, :3]
    t_now[:3, 3] = frame.T @ (W[:3, 3] - origin)
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    canon = (crop - t_now[:3, 3]) @ t_now[:3, :3]
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)
    return sig, frame, origin, t_now, c0


def _expected_feature_azimuths(sig):
    """The test's OWN derivation of the template's code-feature azimuths from the
    signature image — per-theta mean relief, half-peak threshold, circular runs to
    depth-weighted centroids — so the endpoint's rotation is checked against an
    expectation the test constructed itself."""
    import warnings as _warnings
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        prof = np.nanmean(sig.image, axis=1)
    prof = np.nan_to_num(prof, nan=0.0)
    n = sig.image.shape[0]
    idx = np.where(prof >= 0.5 * prof.max())[0]
    runs, cur = [], [int(idx[0])]
    for i in idx[1:]:
        i = int(i)
        if i == cur[-1] + 1:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1:
        runs[0] = runs.pop() + runs[0]
    azs = []
    for run in runs:
        ang = np.radians((np.asarray(run, float) + 0.5) * (360.0 / n))
        w = prof[run]
        azs.append(wrap_deg(np.degrees(np.arctan2(
            (w * np.sin(ang)).sum(), (w * np.cos(ang)).sum()))))
    return sorted(azs)


def _world_click_at_azimuth(azimuth_deg: float):
    """A world-coordinate click on the cap's coded band at an exactly-known azimuth
    about the measured rim centre — the inverse of the server's click mapping."""
    sig, frame, origin, t_now, c0 = _site_geometry()
    r = 0.6 * sig.rmax  # mid coded band
    a = np.radians(azimuth_deg)
    p_canon = np.array([c0[0] + r * np.cos(a), c0[1] + r * np.sin(a), sig.ztop - 0.3])
    p_local = t_now[:3, :3] @ p_canon + t_now[:3, 3]
    return (origin + frame @ p_local).tolist()


class TestAlignToMarkContract:
    def test_unknown_tooth_404s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.align_to_mark(CASE_ID, 99, AlignToMarkIn(point=[0.0, 0.0, 0.0]))
        assert exc.value.status_code == 404
        assert "run the automation first" in exc.value.detail

    def test_malformed_point_is_rejected(self):
        with pytest.raises(ValidationError, match="triple"):
            AlignToMarkIn(point=[1.0, 2.0])
        with pytest.raises(ValidationError, match="finite"):
            AlignToMarkIn(point=[float("nan"), 0.0, 0.0])

    @pytest.mark.slow
    def test_far_point_422s_and_is_side_effect_free(self, demo_out):
        implant = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-implant.json"
        before = implant.read_bytes()
        pos = np.asarray(_implant(demo_out)["pose_matrix"], float)[:3, 3]
        far = (pos + np.array([0.0, 0.0, 50.0])).tolist()
        with pytest.raises(HTTPException) as exc:
            srv.align_to_mark(CASE_ID, TOOTH, AlignToMarkIn(point=far))
        assert exc.value.status_code == 422
        assert "within 15mm" in exc.value.detail
        assert implant.read_bytes() == before, "a rejected mark must not touch the record"
        assert _history_events(demo_out) == []

    def test_click_near_a_feature_applies_the_expected_rotation(self, demo_out):
        """A click placed 9° CCW of a known code feature must rotate the pose by ~+9°
        about the part's own axis (the nearest feature comes TO the mark), with the
        full nudge-grade re-emit + audit trail."""
        sig, *_ = _site_geometry()
        features = _expected_feature_azimuths(sig)
        assert features, "the 7030 template must carry coded relief"
        target_feature = features[-1]  # the feature nearest theta=0 on this template
        offset = 9.0
        click = _world_click_at_azimuth(target_feature + offset)

        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()

        out = srv.align_to_mark(CASE_ID, TOOTH, AlignToMarkIn(point=click))
        assert out["tooth"] == TOOTH
        assert out["applied_delta_deg"] == pytest.approx(offset, abs=0.3)
        assert out["matched_feature_azimuth_deg"] == pytest.approx(target_feature, abs=0.3)
        assert out["click_azimuth_deg"] == pytest.approx(target_feature + offset, abs=0.3)
        assert out["stability_excess_mm"] is not None
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        # the codes are re-read at the rotated pose for the operator's residual display
        assert "notch_shift_deg" in out["clocking"]
        assert "notch_corr" in out["clocking"]

        after = _implant(demo_out)
        R0 = np.asarray(before["pose_matrix"], float)[:3, :3]
        R1 = np.asarray(after["pose_matrix"], float)[:3, :3]
        # a rotation about the part's OWN axis: the axis itself must not move...
        assert float(R0[:, 2] @ R1[:, 2]) > 0.999
        # ...while the pose genuinely rotated by ~offset degrees, in the CCW direction
        rel = R0.T @ R1
        angle = float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0])))
        assert angle == pytest.approx(offset, abs=0.4)
        assert after["nudge"]["cumulative_deg"] == out["cumulative_deg"]
        assert cap.read_bytes() != cap_before, "the viewer's STL must be re-emitted"

        # the cached run row carries the rotated state so a page reload is honest
        run = json.loads((demo_out / CASE_ID / "run.json").read_text())
        row = next(r for r in run["summary"]["sites"] if r["tooth"] == TOOTH)
        assert row["nudge"]["cumulative_deg"] == out["cumulative_deg"]
        assert "notch_shift_deg" in row["clocking"]

        events = _history_events(demo_out)
        assert [e["outcome"] for e in events] == ["applied"]
        assert events[0]["point"] == pytest.approx(click, abs=0.01)
        assert events[0]["applied_delta_deg"] == out["applied_delta_deg"]
        assert events[0]["matched_feature_azimuth_deg"] == out["matched_feature_azimuth_deg"]
        assert events[0]["click_azimuth_deg"] == out["click_azimuth_deg"]

    def test_refused_rotation_is_side_effect_free_with_reason(self, demo_out, monkeypatch):
        """The gates judge the proposal — a stability excess over the bound must 409
        with the server's own sentence and leave every artifact byte-identical."""
        sig, *_ = _site_geometry()
        features = _expected_feature_azimuths(sig)
        click = _world_click_at_azimuth(features[-1] + 9.0)
        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()
        monkeypatch.setattr(srv, "_ring_fixed_candidate",
                            lambda *a, **k: (np.eye(4), 0.9))

        with pytest.raises(HTTPException) as exc:
            srv.align_to_mark(CASE_ID, TOOTH, AlignToMarkIn(point=click))
        assert exc.value.status_code == 409
        assert "refused" in exc.value.detail
        assert "0.90mm" in exc.value.detail

        assert _implant(demo_out) == before
        assert cap.read_bytes() == cap_before
        events = _history_events(demo_out)
        assert [e["outcome"] for e in events] == ["refused"]
        assert events[0]["click_azimuth_deg"] is not None
        assert events[0]["matched_feature_azimuth_deg"] is not None
