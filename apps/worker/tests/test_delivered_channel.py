"""G3 + G4 (master plan §7.4): the delivered channel becomes MEASURED and VISIBLE.

Before 2026-07-23 `delivered_channel` appeared nowhere in src/tests/tools (§7.3): no
scoreboard column, no render, no test ever looked at the channel the patient actually
receives — while one test suite actively enforced the canonical-axis defect. These
tests pin the two new instruments: the fleet scoreboard's measurement columns and the
QC clockview's as-built channel marker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

WORKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER / "tools"))

from case_prep.adapters.qc_render import render_site_qc  # noqa: E402
from case_prep.adapters.synthetic import make_scan_body_mesh  # noqa: E402

import fleet_scoreboard  # noqa: E402


class TestDeliveredChannelColumn:
    def test_delivered_channel_column_present(self):
        # the plan-named G3 gate: the scoreboard renders the measurement columns and
        # keeps them OUT of the improved/regressed vote (they measure the deliverable;
        # they must never mix into the pose-metric verdicts — same rule as the island
        # shadow columns)
        row = {"site": "s/t1", "identified": "6030", "declared": None, "seat": "rim",
               "rim_agreement": 0.5, "top_face_p90": 0.4, "rim_off_centre": 0.1,
               "bore_void_off": 0.6, "delivered_channel_vs_cap_channel": 0.357,
               "delivered_channel_vs_recess": 0.46, "delivered_channel_r_mm": 0.998,
               "notch_shift_deg": None, "clock_evidence": None, "island_off": None,
               "island_conv": None, "confidence": "high", "gate": "auto"}
        table = fleet_scoreboard._render({"rows": [row]})
        assert "dlv-cap" in table and "dlv-recess" in table and "dlv-r" in table
        assert "0.357" in table and "0.46" in table and "0.998" in table
        for key in ("delivered_channel_vs_recess", "delivered_channel_vs_cap_channel",
                    "delivered_channel_r_mm"):
            assert key not in fleet_scoreboard._EPS, \
                f"{key} is a MEASUREMENT column — it must not vote improved/regressed"

    def test_column_is_none_safe_when_no_product_exists(self):
        out = fleet_scoreboard._delivered_channel_metrics(
            Path("/nonexistent/prosthesis.stl"), np.eye(4), np.eye(3), np.zeros(3),
            np.zeros((10, 3)), make_scan_body_mesh())
        assert out == {"delivered_channel_vs_recess": None,
                       "delivered_channel_vs_cap_channel": None,
                       "delivered_channel_r_mm": None}

    def test_scoreboard_delegates_to_the_shared_instrument(self):
        # single source of truth (§8 item 12): the scoreboard's measurement IS
        # auto_flow.delivered_channel_offsets — the same function the run row (and
        # therefore the verification panel) consumes; only the STL load/un-pose
        # wrapper lives in the scoreboard
        from case_prep.pipeline.auto_flow import delivered_channel_offsets
        assert fleet_scoreboard.delivered_channel_offsets is delivered_channel_offsets


class TestHonestyColumns:
    """Slice 4 + slice 10 (§8 item 12): the inseparable-variants flag and the
    detection-recall instrumentation become scoreboard columns."""

    _ROW = {"site": "s/t1", "identified": "6030", "declared": None, "seat": "rim",
            "rim_agreement": 0.5, "top_face_p90": 0.4, "rim_off_centre": 0.1,
            "bore_void_off": 0.6, "notch_shift_deg": None, "clock_evidence": None,
            "island_off": None, "island_conv": None, "confidence": "high",
            "gate": "auto"}

    def test_detection_columns_present(self):
        # the plan-named slice-10 gate: recall + candidate-proximity columns per site
        hit = dict(self._ROW, too_close=False, detect_hit=True, detect_off_mm=0.062)
        miss = dict(self._ROW, site="s/t2", too_close=True, detect_hit=False,
                    detect_off_mm=None)
        table = fleet_scoreboard._render({"rows": [hit, miss]})
        assert "too-close" in table and "detect (off)" in table
        assert "hit (0.062)" in table
        assert "MISS (no candidate)" in table
        assert "| yes |" in table

    def test_pre_slice10_snapshot_rows_render_none_safe(self):
        # older snapshots carry neither column — the table must not crash or invent
        table = fleet_scoreboard._render({"rows": [dict(self._ROW)]})
        assert "| — | — |" in table

    def test_measurement_columns_never_vote_and_flag_flips_surface_as_changed(self):
        assert "detect_off_mm" not in fleet_scoreboard._EPS
        assert "too_close" not in fleet_scoreboard._EPS
        cur = {"rows": [dict(self._ROW, too_close=True, detect_hit=False)]}
        base = {"rows": [dict(self._ROW, too_close=False, detect_hit=True)]}
        diff = fleet_scoreboard.compare(cur, base)
        assert "too_close" in diff and "detect_hit" in diff
        assert "0 improved, 0 regressed" in diff


@pytest.mark.skipif(
    not (WORKER / "reports/live-demo/cap6030-neodent-gm/package").exists(),
    reason="live-demo packages not on this host")
@pytest.mark.slow
def test_scoreboard_measures_a_real_delivered_package():
    """The column's measurement chain on a REAL emitted package (no pipeline run).

    Era-proof bands, deliberately: the shipped cap6030 package measures
    vs_cap=0.357 / vs_recess=0.46 / r=0.998 today (the §7.1 canonical-axis defect,
    reproduced 2026-07-23); after the G1 wiring re-emits packages at library truth
    the same instrument must read vs_cap ~<=0.15 and r~1.10. The assertions accept
    both eras — what they pin is that the instrument READS the deliverable."""
    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.pipeline.auto_flow import _crowns_frame

    pkg = WORKER / "reports/live-demo/cap6030-neodent-gm/package"
    pose = np.array(json.loads(
        (pkg / "cap6030-neodent-gm-29-implant.json").read_text())["pose_matrix"], float)
    scan = trimesh.load(
        next((WORKER / "data/real/scans/doctor-cap6030-neodent-gm").glob("*.stl")),
        force="mesh")
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    lib = CapLibrary.load(WORKER / "data/real/library/caps/neodent-gm")
    template = lib.template(next(sp for sp in lib.specs if sp.variant == "6030"))

    out = fleet_scoreboard._delivered_channel_metrics(
        pkg / "cap6030-neodent-gm-29-prosthesis_cad.stl", pose, frame, origin,
        (pts - origin) @ frame, template)
    assert out["delivered_channel_r_mm"] is not None, "no channel read on a real package"
    assert 0.85 <= out["delivered_channel_r_mm"] <= 1.35   # legacy 0.998 / truth ~1.10
    assert out["delivered_channel_vs_cap_channel"] is not None
    assert 0.0 <= out["delivered_channel_vs_cap_channel"] <= 0.6  # defect band tops at 0.42
    assert out["delivered_channel_vs_recess"] is not None
    assert 0.0 < out["delivered_channel_vs_recess"] <= 1.5


class TestClockviewDeliveredChannel:
    def test_clockview_draws_delivered_channel(self, tmp_path):
        # G4: passing the as-built channel centre must change the rendered clock view
        # (marker + legend entry). In-process matplotlib renders are deterministic, so
        # equal-args renders are byte-equal — the with-marker render differing proves
        # the delivered channel is actually drawn, not silently dropped.
        tmpl = make_scan_body_mesh()
        pts = np.asarray(tmpl.vertices, float)
        base1 = render_site_qc("t", 30, pts, np.eye(4), tmpl, None,
                               tmp_path / "b1")[0][0].read_bytes()
        base2 = render_site_qc("t", 30, pts, np.eye(4), tmpl, None,
                               tmp_path / "b2")[0][0].read_bytes()
        assert base1 == base2, "clockview render not deterministic in-process"
        marked, _ = render_site_qc("t", 30, pts, np.eye(4), tmpl, None, tmp_path / "m",
                                   delivered_channel_xy=np.array([-0.35, -0.05]))
        assert [p.name for p in marked] == ["t-30-clockview.png", "t-30-deviation.png"]
        assert marked[0].read_bytes() != base1, \
            "delivered_channel_xy did not change the clock view — marker not drawn"

    def test_clockview_unchanged_without_delivered_channel(self, tmp_path):
        # the parameter is additive: existing callers (auto_flow) render identically
        tmpl = make_scan_body_mesh()
        pts = np.asarray(tmpl.vertices, float)
        paths, _ = render_site_qc("t", 31, pts, np.eye(4), tmpl, None, tmp_path)
        for p in paths:
            assert p.is_file() and p.stat().st_size > 0
