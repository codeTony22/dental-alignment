"""The capture gate's server surfacing (master plan §1 SCAN / §8 item 11).

Intake ADVISORY in the demo: per-site capture blocks ride the propose payload (every
proposal + the case's curated suggested sites) and the run payload (per confirmed
tooth), derived at serve time and cached with the case — pipeline behavior unchanged.
Helper-level tests run on synthetic clouds; the endpoint test replays the real
zimmer-4.5 live-demo artifacts (t7, the measured rescan exemplar) when present.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import cKDTree

import case_prep.server as srv

REAL_OUT = srv.OUT  # captured at import, before any monkeypatching


# --- synthetic cap site (same IOS-class density the gate is calibrated at) -----------

def _disc(r0, r1, z, step=0.15):
    xs = np.arange(-r1, r1 + step, step)
    X, Y = np.meshgrid(xs, xs)
    P = np.c_[X.ravel(), Y.ravel(), np.full(X.size, float(z))]
    rr = np.linalg.norm(P[:, :2], axis=1)
    return P[(rr >= r0) & (rr <= r1)]


def _cap_cloud(rim_r=3.0, rim_z=0.0, tissue_z=-1.5):
    top = _disc(0.8, rim_r, rim_z)
    wall = np.concatenate([_disc(rim_r - 0.05, rim_r + 0.05, rim_z - dz)
                           for dz in (0.3, 0.6, 0.9)])
    tissue = _disc(rim_r + 0.4, rim_r + 4.0, tissue_z)
    return np.vstack([top, wall, tissue])


@pytest.fixture()
def syn_cfg(tmp_path, monkeypatch):
    """A synthetic case cfg with a precomputed capture context — no STL, no _assets."""
    monkeypatch.setattr(srv, "OUT", tmp_path)
    srv._cache.pop("capture:case-syn", None)
    L = _cap_cloud()
    cfg = {
        "suggested_sites": [{"tooth": 7, "center": [0.0, 0.0, 0.0],
                             "center_mark": [0.0, 0.0, 0.0],
                             "rim_mark": [3.0, 0.0, 0.0]}],
        "capture_ctx": (np.eye(3), np.zeros(3), L, cKDTree(L[:, :2])),
    }
    return cfg


class TestSiteCaptureInputs:
    def test_centre_plus_rim_mark_pair_is_used_as_given(self, syn_cfg):
        centre_xy, hint = srv._site_capture_inputs(
            syn_cfg, [0.0, 0.0, 0.0], center_mark=[0.1, 0.0, 0.0],
            rim_mark=[3.1, 0.0, 0.0])
        assert centre_xy == pytest.approx([0.1, 0.0])
        assert hint == pytest.approx(3.0)

    def test_border_circle_fit_wins_when_three_points_present(self, syn_cfg):
        ring = [[3.0, 0.0, 0.0], [-3.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, -3.0, 0.0]]
        centre_xy, hint = srv._site_capture_inputs(
            syn_cfg, [1.0, 1.0, 0.0], rim_points=ring)
        assert centre_xy == pytest.approx([0.0, 0.0], abs=1e-6)
        assert hint == pytest.approx(3.0, abs=1e-6)

    def test_bare_centre_falls_back_to_the_measured_rim(self, syn_cfg):
        from case_prep.adapters.cap_detection import measure_rim_diameter

        _, _, L, xy_tree = syn_cfg["capture_ctx"]
        expected = measure_rim_diameter(L, xy_tree, np.zeros(3)) / 2.0
        _, hint = srv._site_capture_inputs(syn_cfg, [0.0, 0.0, 0.0])
        assert hint == pytest.approx(expected)  # the estimator, not the 2.6 default


class TestCaptureBlocks:
    def test_propose_payload_gains_capture_per_proposal_and_suggested(self, syn_cfg):
        result = {"proposals": [{"center": [0.0, 0.0, 0.0], "void_ratio": 0.1,
                                 "rim_below_cusps_mm": 5.0}], "duration_s": 1.0}
        out = srv._with_capture(syn_cfg, "case-syn", result)
        assert out["proposals"][0]["capture"]["verdict"] == "pass"
        assert [c["name"] for c in out["proposals"][0]["capture"]["checks"]] == [
            "rim_arc", "code_band", "collar_exposure"]
        assert out["suggested_capture"][0]["tooth"] == 7
        assert out["suggested_capture"][0]["capture"]["verdict"] == "pass"
        # the original cached result is layered, not mutated (serve-time derivation)
        assert "capture" not in result["proposals"][0]

    def test_run_capture_is_keyed_by_tooth(self, syn_cfg):
        sites = [srv.SiteIn(tooth=7, center=[0.0, 0.0, 0.0],
                            center_mark=[0.0, 0.0, 0.0], rim_mark=[3.0, 0.0, 0.0])]
        blocks = srv._run_sites_capture(syn_cfg, "case-syn", sites)
        assert set(blocks) == {"7"}
        assert blocks["7"]["verdict"] == "pass"
        assert blocks["7"]["checks"][2]["value"] == pytest.approx(1.5, abs=0.2)

    def test_blocks_are_cached_with_the_case(self, syn_cfg, tmp_path):
        calls = {"n": 0}
        real = srv.assess_capture

        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        srv.assess_capture = counting
        try:
            srv._capture_block(syn_cfg, "case-syn", np.zeros(2), 3.0)
            srv._capture_block(syn_cfg, "case-syn", np.zeros(2), 3.0)
        finally:
            srv.assess_capture = real
        assert calls["n"] == 1
        store = json.loads((tmp_path / "case-syn" / "capture.json").read_text())
        assert list(store.values())[0]["verdict"] == "pass"


CASE_ID = "zimmer-4.5"


@pytest.fixture()
def real_demo(tmp_path, monkeypatch):
    """A disposable copy of the zimmer-4.5 live-demo proposals, real scan attached."""
    src = REAL_OUT / CASE_ID
    if CASE_ID not in srv.CASES or not (src / "proposals.json").exists():
        pytest.skip("zimmer-4.5 live-demo artifacts not present on this machine")
    (tmp_path / CASE_ID).mkdir()
    shutil.copy(src / "proposals.json", tmp_path / CASE_ID / "proposals.json")
    monkeypatch.setattr(srv, "OUT", tmp_path)
    srv._cache.pop(f"propose:{CASE_ID}", None)
    srv._cache.pop(f"capture:{CASE_ID}", None)
    yield tmp_path
    srv._cache.pop(f"propose:{CASE_ID}", None)
    srv._cache.pop(f"capture:{CASE_ID}", None)


class TestProposeEndpointRealCase:
    def test_t7_surfaces_rescan_in_the_propose_payload(self, real_demo):
        """The measured failure exemplar reaches the demo UI at intake: t7's curated
        site must carry a RESCAN capture block in the propose response — the check
        that was discovered at the END of the pipeline now fires at step 2."""
        out = srv.propose(CASE_ID)
        assert out["cached"] is True  # served from the copied live-demo cache
        assert all("capture" in p for p in out["proposals"])
        t7 = next(s for s in out["suggested_capture"] if s["tooth"] == 7)
        assert t7["capture"]["verdict"] == "rescan"
        rim = next(c for c in t7["capture"]["checks"] if c["name"] == "rim_arc")
        assert rim["verdict"] == "rescan"
        assert rim["value"] == pytest.approx(0.54, abs=0.03)
        assert "% of the ring is missing" in rim["message"]
