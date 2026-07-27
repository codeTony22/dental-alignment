"""Pure/fast tests for tools/fle_study.py — the operator centre-click FLE study tool.

`tools/` isn't on pythonpath (only `src` is, per pyproject.toml), so this file inserts
`tools/` onto sys.path itself rather than touching shared config.

Fixtures build tiny synthetic run-history.jsonl + sites.json trees under tmp_path — no
dependency on the real reports/live-demo/run-history.jsonl or data/real/scans.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import fle_study  # noqa: E402  (path bootstrap must run first)


# ----------------------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------------------

def _write_sites_json(scans_dir: Path, case_id: str, tooth: int,
                       center_mark, rim_mark, center=None) -> None:
    case_dir = scans_dir / f"doctor-{case_id}"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "sites.json").write_text(json.dumps({
        "suggested_sites": [{
            "tooth": tooth,
            "center": center if center is not None else list(center_mark),
            "declared_variant": None,
            "center_mark": list(center_mark),
            "rim_mark": list(rim_mark),
        }],
    }))


def _rec(ts: str, case_id: str, tooth: int, center_mark=None, rim_mark=None,
         rim_points=None) -> dict:
    site = {"tooth": tooth, "center": center_mark, "declared_variant": None,
            "marked_points": None, "center_mark": center_mark, "rim_mark": rim_mark,
            "rim_points": rim_points}
    return {"ts": ts, "case_id": case_id, "cached": False, "fresh": False,
            "sites_in": [site], "sites_out": None, "duration_s": 1.0}


def _write_history(history_path: Path, records: List[dict]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# ----------------------------------------------------------------------------------
# Curated-replay exclusion
# ----------------------------------------------------------------------------------

class TestCuratedReplayExclusion:
    def test_identical_marks_dropped(self, tmp_path):
        scans_dir = tmp_path / "scans"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)

        records = [
            _rec("2026-07-18T10:00:00", "demo-case", 3, curated_center, curated_rim),
            _rec("2026-07-18T10:01:00", "demo-case", 3, curated_center, curated_rim),
            _rec("2026-07-18T10:02:00", "demo-case", 3, curated_center, curated_rim),
        ]
        run_records = [fle_study.RunRecord(i + 1, r["ts"], r["case_id"], r["sites_in"])
                        for i, r in enumerate(records)]
        refs = fle_study.load_site_references(scans_dir)

        extractions = fle_study.extract_fresh_marks(run_records, refs, "center_mark")
        ext = extractions[("demo-case", 3)]
        assert ext.fresh == []
        # every entry excluded, whether counted as curated or as a consecutive duplicate
        assert ext.curated_excluded + ext.duplicate_excluded == len(records)
        assert ext.curated_excluded >= 1  # at least the first occurrence is caught as curated

    def test_near_identical_within_tolerance_dropped(self, tmp_path):
        scans_dir = tmp_path / "scans"
        curated_center = [10.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, [12.0, 10.0, 5.0])
        # within 1e-6mm of the curated value -> still a replay, not a fresh click
        near_identical = [10.0 + 1e-9, 10.0, 5.0]
        records = [fle_study.RunRecord(1, "2026-07-18T10:00:00", "demo-case",
                                        [{"tooth": 3, "center_mark": near_identical}])]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "center_mark")
        assert extractions[("demo-case", 3)].fresh == []

    def test_genuinely_fresh_click_kept(self, tmp_path):
        scans_dir = tmp_path / "scans"
        curated_center = [10.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, [12.0, 10.0, 5.0])
        fresh_value = [10.4, 9.8, 5.0]  # 0.4+mm off — a genuinely fresh click
        records = [fle_study.RunRecord(1, "2026-07-18T10:00:00", "demo-case",
                                        [{"tooth": 3, "center_mark": fresh_value}])]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "center_mark")
        fresh = extractions[("demo-case", 3)].fresh
        assert len(fresh) == 1
        assert fresh[0].value == tuple(fresh_value)

    def test_center_mark_alongside_rim_points_is_a_derived_artifact_not_a_click(self, tmp_path):
        """fle-calibration.md S1's key trap: whenever a submission carries `rim_points`
        (a border-click gesture), its `center_mark` is an unrelated derived value, not the
        operator's centre-click aim -- it must never enter the centre-click channel, even
        though it is neither byte-identical to the curated mark nor a consecutive dup."""
        scans_dir = tmp_path / "scans"
        curated_center = [10.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, [12.0, 10.0, 5.0])
        gesture = [[12.0, 10.0, 5.0], [10.0, 12.0, 5.0], [8.0, 10.0, 5.0], [10.0, 8.0, 5.0]]
        # each entry's center_mark is a DIFFERENT derived value -- if not guarded, these
        # would look like 3 distinct fresh centre clicks
        records = [
            fle_study.RunRecord(1, "t0", "demo-case",
                                 [{"tooth": 3, "center_mark": [10.6, 9.5, 5.3],
                                   "rim_points": gesture}]),
            fle_study.RunRecord(2, "t1", "demo-case",
                                 [{"tooth": 3, "center_mark": [10.4, 9.6, 5.4],
                                   "rim_points": gesture}]),
            fle_study.RunRecord(3, "t2", "demo-case",
                                 [{"tooth": 3, "center_mark": [10.5, 9.55, 5.35],
                                   "rim_points": gesture}]),
        ]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "center_mark")
        ext = extractions[("demo-case", 3)]
        assert ext.fresh == []
        assert ext.derived_excluded == 3
        assert ext.curated_excluded == 0
        assert ext.duplicate_excluded == 0

    def test_rim_mark_channel_unaffected_by_rim_points_guard(self, tmp_path):
        """The rim_points guard is centre-channel-specific; rim_mark is untouched by it
        (and is None on those records anyway in real data, but verify no cross-talk)."""
        scans_dir = tmp_path / "scans"
        _write_sites_json(scans_dir, "demo-case", 3, [10.0, 10.0, 5.0], [12.0, 10.0, 5.0])
        gesture = [[12.0, 10.0, 5.0], [10.0, 12.0, 5.0], [8.0, 10.0, 5.0], [10.0, 8.0, 5.0]]
        fresh_rim = [12.3, 9.9, 5.0]
        records = [fle_study.RunRecord(1, "t0", "demo-case",
                                        [{"tooth": 3, "rim_mark": fresh_rim,
                                          "rim_points": gesture}])]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "rim_mark")
        fresh = extractions[("demo-case", 3)].fresh
        assert len(fresh) == 1
        assert fresh[0].value == tuple(fresh_rim)


# ----------------------------------------------------------------------------------
# Duplicate (cache re-submission) dedupe
# ----------------------------------------------------------------------------------

class TestDuplicateRunDedupe:
    def test_consecutive_identical_fresh_marks_collapsed(self, tmp_path):
        scans_dir = tmp_path / "scans"
        _write_sites_json(scans_dir, "demo-case", 3, [10.0, 10.0, 5.0], [12.0, 10.0, 5.0])
        fresh_a = [10.4, 9.8, 5.0]
        fresh_b = [9.6, 10.3, 5.0]
        records = [
            fle_study.RunRecord(1, "t0", "demo-case", [{"tooth": 3, "center_mark": fresh_a}]),
            fle_study.RunRecord(2, "t1", "demo-case", [{"tooth": 3, "center_mark": fresh_a}]),
            fle_study.RunRecord(3, "t2", "demo-case", [{"tooth": 3, "center_mark": fresh_a}]),
            fle_study.RunRecord(4, "t3", "demo-case", [{"tooth": 3, "center_mark": fresh_b}]),
        ]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "center_mark")
        ext = extractions[("demo-case", 3)]
        assert [m.value for m in ext.fresh] == [tuple(fresh_a), tuple(fresh_b)]
        assert ext.duplicate_excluded == 2  # the 2 re-submissions of fresh_a

    def test_non_consecutive_repeat_is_not_deduped(self, tmp_path):
        """A repeated value is only a 'cache re-submission' if it immediately follows
        the same raw value — A, B, A must keep both A's."""
        scans_dir = tmp_path / "scans"
        _write_sites_json(scans_dir, "demo-case", 3, [10.0, 10.0, 5.0], [12.0, 10.0, 5.0])
        a = [10.4, 9.8, 5.0]
        b = [9.6, 10.3, 5.0]
        records = [
            fle_study.RunRecord(1, "t0", "demo-case", [{"tooth": 3, "center_mark": a}]),
            fle_study.RunRecord(2, "t1", "demo-case", [{"tooth": 3, "center_mark": b}]),
            fle_study.RunRecord(3, "t2", "demo-case", [{"tooth": 3, "center_mark": a}]),
        ]
        refs = fle_study.load_site_references(scans_dir)
        extractions = fle_study.extract_fresh_marks(records, refs, "center_mark")
        fresh_values = [m.value for m in extractions[("demo-case", 3)].fresh]
        assert fresh_values == [tuple(a), tuple(b), tuple(a)]


# ----------------------------------------------------------------------------------
# Fresh-click clustering + percentiles on a known synthetic scatter
# ----------------------------------------------------------------------------------

class TestClusteringAndPercentiles:
    def test_planted_gaussian_recovers_expected_p68(self):
        sigma0 = 0.3
        rng = np.random.default_rng(42)
        n = 400
        centroid = np.array([50.0, 30.0])
        samples_xy = centroid + rng.normal(0.0, sigma0, size=(n, 2))
        marks = [fle_study.FreshMark(ts=f"t{i}", line_no=i,
                                      value=(float(x), float(y), 12.0))
                 for i, (x, y) in enumerate(samples_xy)]

        scatter = fle_study.compute_site_scatter("demo-case", 3, marks)
        assert scatter.percentiles is not None
        assert scatter.percentiles.n == n

        # theoretical Rayleigh p68 for scale sigma0
        expected_p68 = sigma0 * math.sqrt(-2.0 * math.log(1.0 - 0.68))
        assert scatter.percentiles.p68 == pytest.approx(expected_p68, rel=0.25)

        recovered_sigma = fle_study.invert_sigma(scatter.percentiles.p68, 0.68)
        assert recovered_sigma == pytest.approx(sigma0, abs=0.08)

    def test_insufficient_n_flagged_below_four(self):
        marks = [fle_study.FreshMark(ts=f"t{i}", line_no=i, value=(10.0 + 0.1 * i, 10.0, 5.0))
                 for i in range(3)]
        scatter = fle_study.compute_site_scatter("demo-case", 3, marks)
        assert scatter.insufficient is True
        assert scatter.percentiles.n == 3

    def test_no_marks_is_insufficient_with_no_percentiles(self):
        scatter = fle_study.compute_site_scatter("demo-case", 3, [])
        assert scatter.insufficient is True
        assert scatter.percentiles is None
        assert scatter.centroid_xy is None


# ----------------------------------------------------------------------------------
# Slip exclusion
# ----------------------------------------------------------------------------------

class TestSlipExclusion:
    def test_one_outlier_flagged_and_excluded_from_core(self):
        tight = [(10.0 + dx, 10.0 + dy, 5.0) for dx, dy in
                 [(0.05, -0.02), (-0.03, 0.04), (0.02, 0.03), (-0.04, -0.03),
                  (0.01, 0.02), (-0.02, -0.01)]]
        slip_point = (13.0, 10.0, 5.0)  # 3mm off the ~(10,10) cluster
        marks = [fle_study.FreshMark(ts=f"t{i}", line_no=i, value=v)
                 for i, v in enumerate(tight + [slip_point])]

        scatter = fle_study.compute_site_scatter("demo-case", 3, marks)
        assert scatter.n_fresh == 7
        assert len(scatter.slips) == 1
        assert scatter.slips[0].deviation_mm > fle_study.SLIP_THRESHOLD_MM
        assert len(scatter.core_deviations_mm) == 6
        assert all(d <= fle_study.SLIP_THRESHOLD_MM for d in scatter.core_deviations_mm)

    def test_no_slip_when_all_within_threshold(self):
        marks = [fle_study.FreshMark(ts=f"t{i}", line_no=i,
                                      value=(10.0 + 0.05 * i, 10.0, 5.0))
                 for i in range(6)]
        scatter = fle_study.compute_site_scatter("demo-case", 3, marks)
        assert scatter.slips == []
        assert len(scatter.core_deviations_mm) == 6


# ----------------------------------------------------------------------------------
# Sigma inversion math
# ----------------------------------------------------------------------------------

class TestSigmaInversion:
    @pytest.mark.parametrize("pct", [0.50, 0.68, 0.90])
    def test_round_trip_recovers_planted_sigma(self, pct):
        sigma0 = 0.37
        r = sigma0 * math.sqrt(-2.0 * math.log(1.0 - pct))
        assert fle_study.invert_sigma(r, pct) == pytest.approx(sigma0, rel=1e-9)

    def test_p68_matches_1_51_shorthand(self):
        sigma0 = 0.3
        r68 = sigma0 * 1.5095921854516636  # sqrt(-2*ln(0.32))
        assert fle_study.invert_sigma(r68, 0.68) == pytest.approx(sigma0, rel=1e-6)

    def test_rejects_out_of_range_pct(self):
        with pytest.raises(ValueError):
            fle_study.invert_sigma(1.0, 1.0)
        with pytest.raises(ValueError):
            fle_study.invert_sigma(1.0, 0.0)

    def test_sigma_estimate_mean_of_three_percentiles(self):
        sigma0 = 0.25
        pct = fle_study.Percentiles(
            n=50,
            p50=sigma0 * math.sqrt(-2.0 * math.log(1.0 - 0.50)),
            p68=sigma0 * math.sqrt(-2.0 * math.log(1.0 - 0.68)),
            p90=sigma0 * math.sqrt(-2.0 * math.log(1.0 - 0.90)),
            max=1.0,
        )
        est = fle_study.sigma_estimate(pct)
        assert est.at_p50 == pytest.approx(sigma0, rel=1e-9)
        assert est.at_p68 == pytest.approx(sigma0, rel=1e-9)
        assert est.at_p90 == pytest.approx(sigma0, rel=1e-9)
        assert est.mean == pytest.approx(sigma0, rel=1e-9)

    def test_verdict_holds_within_band(self):
        msg = fle_study.sigma_verdict(0.31)
        assert "holds" in msg

    def test_verdict_flags_departure(self):
        msg = fle_study.sigma_verdict(0.6)
        assert "holds" not in msg
        assert "higher" in msg

    def test_verdict_none_when_no_data(self):
        msg = fle_study.sigma_verdict(None)
        assert "insufficient" in msg


# ----------------------------------------------------------------------------------
# filter_range
# ----------------------------------------------------------------------------------

class TestFilterRange:
    def _records(self):
        return [
            fle_study.RunRecord(1, "2026-07-14T10:00:00", "c", []),
            fle_study.RunRecord(2, "2026-07-15T10:00:00", "c", []),
            fle_study.RunRecord(3, "2026-07-16T10:00:00", "c", []),
        ]

    def test_after_line(self):
        out = fle_study.filter_range(self._records(), after_line=1)
        assert [r.line_no for r in out] == [2, 3]

    def test_since(self):
        out = fle_study.filter_range(self._records(), since="2026-07-15T00:00:00")
        assert [r.line_no for r in out] == [2, 3]

    def test_both_combined(self):
        out = fle_study.filter_range(self._records(), since="2026-07-15T00:00:00", after_line=2)
        assert [r.line_no for r in out] == [3]

    def test_no_filters_returns_everything(self):
        out = fle_study.filter_range(self._records())
        assert len(out) == 3


# ----------------------------------------------------------------------------------
# Empty-range / no-data behavior
# ----------------------------------------------------------------------------------

class TestEmptyRangeBehavior:
    def test_no_history_file_reports_no_data(self, tmp_path):
        result = fle_study.analyze(tmp_path / "missing.jsonl", tmp_path / "missing_scans")
        assert result.has_fresh_data is False
        report = fle_study.render_report(result, generated_at="2026-07-18")
        assert fle_study.NO_DATA_MESSAGE in report

    def test_only_curated_replays_reports_no_data(self, tmp_path):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)
        _write_history(history_path, [
            _rec("2026-07-18T10:00:00", "demo-case", 3, curated_center, curated_rim),
            _rec("2026-07-18T10:01:00", "demo-case", 3, curated_center, curated_rim),
        ])
        result = fle_study.analyze(history_path, scans_dir)
        assert result.has_fresh_data is False
        report = fle_study.render_report(result, generated_at="2026-07-18")
        assert fle_study.NO_DATA_MESSAGE in report

    def test_after_line_beyond_file_end_reports_no_data(self, tmp_path):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        _write_sites_json(scans_dir, "demo-case", 3, [10.0, 10.0, 5.0], [12.0, 10.0, 5.0])
        _write_history(history_path, [
            _rec("2026-07-18T10:00:00", "demo-case", 3, [10.4, 9.8, 5.0], [12.1, 10.2, 5.0]),
        ])
        result = fle_study.analyze(history_path, scans_dir, after_line=99)
        assert result.has_fresh_data is False


# ----------------------------------------------------------------------------------
# End-to-end analyze() over a synthetic run-history with real fresh clicks
# ----------------------------------------------------------------------------------

class TestAnalyzeEndToEnd:
    def _build_study(self, tmp_path, n_clicks=8, sigma=0.3, seed=7):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)

        rng = np.random.default_rng(seed)
        records = [
            # a handful of curated replays that must NOT pollute the fresh set
            _rec("2026-07-18T09:00:00", "demo-case", 3, curated_center, curated_rim),
            _rec("2026-07-18T09:01:00", "demo-case", 3, curated_center, curated_rim),
        ]
        centroid = np.array(curated_center[:2])
        for i in range(n_clicks):
            xy = centroid + rng.normal(0.0, sigma, size=2)
            ts = f"2026-07-18T10:{i:02d}:00"
            records.append(_rec(ts, "demo-case", 3, [float(xy[0]), float(xy[1]), 5.0], curated_rim))
        _write_history(history_path, records)
        return history_path, scans_dir

    def test_fresh_clicks_produce_a_populated_report(self, tmp_path):
        history_path, scans_dir = self._build_study(tmp_path)
        result = fle_study.analyze(history_path, scans_dir)
        assert result.has_fresh_data is True
        site = result.center.site_scatters[("demo-case", 3)]
        assert site.n_fresh == 8
        report = fle_study.render_report(result, generated_at="2026-07-18")
        assert "## Centre-click channel (study of 2026-07-18)" in report
        assert "demo-case" in report
        assert fle_study.NO_DATA_MESSAGE not in report


# ----------------------------------------------------------------------------------
# Border rim_points gestures (bonus, deferred to existing border numbers)
# ----------------------------------------------------------------------------------

class TestRimPointsGestures:
    def test_fresh_gesture_detected_and_reported(self, tmp_path):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        _write_sites_json(scans_dir, "demo-case", 3, [10.0, 10.0, 5.0], [12.0, 10.0, 5.0])
        gesture = [[12.0, 10.0, 5.0], [10.0, 12.0, 5.0], [8.0, 10.0, 5.0], [10.0, 8.0, 5.0]]
        _write_history(history_path, [
            _rec("2026-07-18T10:00:00", "demo-case", 3, [10.4, 9.8, 5.0], None, rim_points=gesture),
        ])
        result = fle_study.analyze(history_path, scans_dir)
        assert len(result.rim_points_gestures) == 1
        assert result.rim_points_gestures[0].n_points == 4
        report = fle_study.render_report(result, generated_at="2026-07-18")
        assert "border" in report.lower()

    def test_consecutive_identical_gesture_deduped(self, tmp_path):
        scans_dir = tmp_path / "scans"
        gesture = [[12.0, 10.0, 5.0], [10.0, 12.0, 5.0], [8.0, 10.0, 5.0], [10.0, 8.0, 5.0]]
        records = [
            fle_study.RunRecord(1, "t0", "demo-case",
                                 [{"tooth": 3, "rim_points": gesture}]),
            fle_study.RunRecord(2, "t1", "demo-case",
                                 [{"tooth": 3, "rim_points": gesture}]),
        ]
        gestures = fle_study.collect_fresh_rim_points_gestures(records)
        assert len(gestures) == 1


# ----------------------------------------------------------------------------------
# rim_mark bonus pair-channel analysis
# ----------------------------------------------------------------------------------

class TestRimMarkChannel:
    def test_fresh_rim_mark_clustered_like_center(self, tmp_path):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)

        rng = np.random.default_rng(3)
        records = []
        for i in range(6):
            dxy = rng.normal(0.0, 0.3, size=2)
            rim = [12.0 + float(dxy[0]), 10.0 + float(dxy[1]), 5.0]
            records.append(_rec(f"2026-07-18T11:{i:02d}:00", "demo-case", 3,
                                 curated_center, rim))
        _write_history(history_path, records)

        result = fle_study.analyze(history_path, scans_dir)
        rim_site = result.rim.site_scatters[("demo-case", 3)]
        assert rim_site.n_fresh == 6
        # centre channel stayed all-curated (never diverged from sites.json)
        assert result.center.n_fresh_total == 0


# ----------------------------------------------------------------------------------
# Never writes without --write
# ----------------------------------------------------------------------------------

class TestNeverWritesWithoutFlag:
    def _study_env(self, tmp_path):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        doc_path = tmp_path / "fle-calibration.md"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)
        rng = np.random.default_rng(11)
        records = []
        for i in range(8):
            dxy = rng.normal(0.0, 0.3, size=2)
            records.append(_rec(f"2026-07-18T12:{i:02d}:00", "demo-case", 3,
                                 [10.0 + float(dxy[0]), 10.0 + float(dxy[1]), 5.0],
                                 curated_rim))
        _write_history(history_path, records)
        sentinel = "# Operator Click-Error (FLE) Calibration\n\nEXISTING CONTENT SENTINEL\n"
        doc_path.write_text(sentinel)
        return history_path, scans_dir, doc_path, sentinel

    def test_analyze_functions_alone_never_touch_doc(self, tmp_path, capsys):
        history_path, scans_dir, doc_path, sentinel = self._study_env(tmp_path)
        result = fle_study.analyze(history_path, scans_dir)
        fle_study.render_report(result, generated_at="2026-07-18")
        capsys.readouterr()
        assert doc_path.read_text() == sentinel  # untouched — analyze/render never write

    def test_cli_without_write_leaves_doc_untouched(self, tmp_path, capsys):
        history_path, scans_dir, doc_path, sentinel = self._study_env(tmp_path)
        rc = fle_study.main(["analyze", "--history", str(history_path),
                              "--scans-dir", str(scans_dir), "--doc", str(doc_path)])
        capsys.readouterr()
        assert rc == 0
        assert doc_path.read_text() == sentinel

    def test_cli_with_write_appends_and_preserves_existing_content(self, tmp_path, capsys):
        history_path, scans_dir, doc_path, sentinel = self._study_env(tmp_path)
        rc = fle_study.main(["analyze", "--history", str(history_path),
                              "--scans-dir", str(scans_dir), "--doc", str(doc_path), "--write"])
        capsys.readouterr()
        assert rc == 0
        written = doc_path.read_text()
        assert written.startswith(sentinel)
        assert "## Centre-click channel" in written

    def test_write_with_no_fresh_data_does_not_append(self, tmp_path, capsys):
        scans_dir = tmp_path / "scans"
        history_path = tmp_path / "run-history.jsonl"
        doc_path = tmp_path / "fle-calibration.md"
        curated_center = [10.0, 10.0, 5.0]
        curated_rim = [12.0, 10.0, 5.0]
        _write_sites_json(scans_dir, "demo-case", 3, curated_center, curated_rim)
        _write_history(history_path, [
            _rec("2026-07-18T10:00:00", "demo-case", 3, curated_center, curated_rim),
        ])
        sentinel = "SENTINEL\n"
        doc_path.write_text(sentinel)
        rc = fle_study.main(["analyze", "--history", str(history_path),
                              "--scans-dir", str(scans_dir), "--doc", str(doc_path), "--write"])
        capsys.readouterr()
        assert rc == 0
        assert doc_path.read_text() == sentinel


# ----------------------------------------------------------------------------------
# `instructions` rendering
# ----------------------------------------------------------------------------------

class TestInstructions:
    def test_mentions_protocol_essentials(self):
        text = fle_study.render_instructions(line_count=52)
        assert "52" in text
        assert "⊕ centre" in text
        assert "Recompute alignment" in text
        assert "6-8" in text
        for case_id, _tooth in fle_study.STUDY_CASES:
            assert case_id in text

    def test_count_lines(self, tmp_path):
        p = tmp_path / "run-history.jsonl"
        assert fle_study.count_lines(p) == 0
        p.write_text('{"a": 1}\n{"a": 2}\n\n')
        assert fle_study.count_lines(p) == 2

    def test_cli_instructions_runs(self, capsys):
        rc = fle_study.main(["instructions"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "PROTOCOL" in out
