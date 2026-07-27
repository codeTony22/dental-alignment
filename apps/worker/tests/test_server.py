"""The live-demo API's input hardening.

The brush patch (``marked_points``) crosses the trust boundary: the web client subsamples
to 400 points, but the API must enforce its own bound — an unbounded array would flow into
the registration ROI and (pre-hashing) into a process-lifetime cache key.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from case_prep.server import MAX_MARKED_POINTS, RunIn, SiteIn


def _site(**overrides):
    base = {"tooth": 7, "center": [1.0, 2.0, 3.0]}
    base.update(overrides)
    return SiteIn(**base)


class TestMarkedPointsBound:
    def test_accepts_a_patch_at_the_cap(self):
        site = _site(marked_points=[[0.0, 0.0, 0.0]] * MAX_MARKED_POINTS)
        assert len(site.marked_points) == MAX_MARKED_POINTS

    def test_rejects_a_patch_over_the_cap(self):
        with pytest.raises(ValidationError, match="capped"):
            _site(marked_points=[[0.0, 0.0, 0.0]] * (MAX_MARKED_POINTS + 1))

    def test_rejects_non_xyz_triples(self):
        with pytest.raises(ValidationError, match="triples"):
            _site(marked_points=[[0.0, 1.0]])

    def test_absent_patch_is_fine(self):
        assert _site().marked_points is None


class TestRimPointsBound:
    """The multi-point rim border (client spec 2026-07-14) crosses the same trust
    boundary as the brush: bounded count, [x, y, z] triples only."""

    def test_accepts_a_border_ring(self):
        site = _site(rim_points=[[0.0, 0.0, 0.0]] * 12)
        assert len(site.rim_points) == 12

    def test_rejects_too_many_points(self):
        with pytest.raises(ValidationError, match="capped"):
            _site(rim_points=[[0.0, 0.0, 0.0]] * 13)

    def test_rejects_non_xyz_triples(self):
        with pytest.raises(ValidationError, match="triples"):
            _site(rim_points=[[0.0, 1.0]])

    def test_absent_is_fine(self):
        assert _site().rim_points is None


class TestRunHistory:
    """Every alignment attempt is kept (client ask 2026-07-14): inputs as sent,
    outcome rows, cached-or-live — one JSONL line per attempt, for post-hoc analysis
    of what went wrong."""

    def test_every_attempt_is_appended_with_inputs_and_outcomes(self, tmp_path,
                                                                monkeypatch):
        import json as _json

        import case_prep.server as srv

        monkeypatch.setattr(srv, "OUT", tmp_path)
        body = srv.RunIn(sites=[{"tooth": 3, "center": [1.0, 2.0, 3.0],
                                 "center_mark": [1.0, 2.0, 3.5]}])
        srv._append_run_history("case-x", body,
                                {"summary": {"sites": [{"tooth": 3, "seat_method": "rim"}]},
                                 "duration_s": 1.2}, cached=True)
        srv._append_run_history("case-x", body,
                                {"summary": {"sites": [{"tooth": 3, "seat_method": "rim"}]},
                                 "duration_s": 9.9}, cached=False)
        lines = (tmp_path / "run-history.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        first, second = (_json.loads(ln) for ln in lines)
        assert first["case_id"] == "case-x" and first["cached"] is True
        assert first["sites_in"][0]["center_mark"] == [1.0, 2.0, 3.5]
        assert first["sites_out"][0]["seat_method"] == "rim"
        assert second["cached"] is False and second["duration_s"] == 9.9


class TestPackageFileCaching:
    def test_package_files_are_never_browser_cached(self, tmp_path, monkeypatch):
        """Package files are OVERWRITTEN at the same URL on every run — a browser
        that cached an aligned STL from an earlier run showed a stale sideways seat
        next to fresh table metrics (client screenshots, 2026-07-14)."""
        import case_prep.server as srv

        monkeypatch.setattr(srv, "OUT", tmp_path)
        monkeypatch.setattr(srv, "_case", lambda cid: {"id": cid})
        pkg = tmp_path / "c1" / "package"
        pkg.mkdir(parents=True)
        (pkg / "part.stl").write_bytes(b"solid x\nendsolid x\n")
        resp = srv.get_file("c1", "part.stl")
        assert resp.headers.get("cache-control") == "no-store"


class TestRoot:
    def test_bare_api_visit_points_at_the_demo(self):
        from case_prep.server import root

        info = root()
        assert info["demo_ui"] == "http://localhost:5173"
        assert info["cases"] == "/api/cases"


class TestDiscovery:
    def test_two_doctors_same_implant_model_are_separate_cases(self, tmp_path):
        """Regression: cases were keyed by MODEL, so a second doctor folder using the same
        implant system silently replaced the first in the demo."""
        from case_prep.server import _discover_cases

        caps = tmp_path / "library/caps/acme-1"
        caps.mkdir(parents=True)
        (caps / "acme-1-5020.stl").write_bytes(b"")
        con = tmp_path / "library/construction/vend"
        con.mkdir(parents=True)
        (con / "acme-1-scanbody.stl").write_bytes(b"")
        for doc in ["doctor-alpha-acme-1", "doctor-beta-acme-1"]:
            d = tmp_path / "scans" / doc
            d.mkdir(parents=True)
            (d / "upper_jaw.stl").write_bytes(b"")

        cases = _discover_cases(tmp_path)
        assert len(cases) == 2
        assert {c["model"] for c in cases.values()} == {"acme-1"}
        assert set(cases) == {"alpha-acme-1", "beta-acme-1"}


class TestLibraryPicker:
    def test_variants_listed_with_dims_and_mesh_urls(self, tmp_path, monkeypatch):
        import trimesh

        from case_prep import server

        caps = tmp_path / "library/caps/acme-1"
        caps.mkdir(parents=True)
        for code in ["5020", "5030"]:
            trimesh.creation.cylinder(radius=2.3, height=3.4).export(caps / f"acme-1-{code}.stl")
        con = tmp_path / "library/construction/vend"
        con.mkdir(parents=True)
        trimesh.creation.cylinder(radius=1.5, height=8.0).export(con / "acme-1-scanbody.stl")
        d = tmp_path / "scans/doctor-x-acme-1"
        d.mkdir(parents=True)
        trimesh.creation.box(extents=[30, 20, 6]).export(d / "upper_jaw.stl")

        monkeypatch.setattr(server, "CASES", server._discover_cases(tmp_path))
        out = server.library_variants("x-acme-1")
        assert [v["variant"] for v in out] == ["5020", "5030"]
        assert all(v["rim_diameter_mm"] and v["height_mm"] and "mesh" in v["mesh_url"]
                   for v in out)
        resp = server.library_mesh("x-acme-1", "5030")
        assert str(resp.path).endswith("acme-1-5030.stl")


class TestDuplicateTeeth:
    def test_duplicate_tooth_numbers_are_rejected_politely(self):
        with pytest.raises(ValidationError, match="duplicate tooth"):
            RunIn(sites=[_site(tooth=8), _site(tooth=8)])

    def test_distinct_teeth_pass(self):
        assert len(RunIn(sites=[_site(tooth=8), _site(tooth=9)]).sites) == 2


class TestMarks:
    def test_marks_must_be_triples(self):
        with pytest.raises(ValidationError, match="triple"):
            _site(center_mark=[1.0, 2.0])

    def test_valid_marks_pass(self):
        s = _site(center_mark=[1.0, 2.0, 3.0], rim_mark=[4.0, 2.0, 3.0])
        assert s.rim_mark == [4.0, 2.0, 3.0]


class TestExportRefusalsReachTheOperator:
    """A pipeline REFUSAL is an answer, not a server fault (2026-07-25). The export gates
    fail closed with a human message — the gingival relief that ate the screw channel
    names the part and says to lower the offset — and that message is worthless if it
    reaches the UI as an anonymous 500."""

    def _case(self, tmp_path, monkeypatch):
        import trimesh

        import case_prep.server as srv

        scan = trimesh.creation.box(extents=[30.0, 20.0, 6.0])
        monkeypatch.setattr(srv, "OUT", tmp_path)
        monkeypatch.setattr(srv, "_cache", {})
        monkeypatch.setattr(srv, "CASES", {"c": {"id": "c", "jaw": "upper",
                                                 "scan": tmp_path / "scan.stl"}})
        monkeypatch.setattr(srv, "_scan_mesh", lambda cfg: scan)
        monkeypatch.setattr(srv, "_library_for", lambda cfg, model, variants=None: object())
        monkeypatch.setattr(srv, "_construction_for", lambda cfg, path_id: object())
        return srv

    def test_a_gate_refusal_becomes_a_409_carrying_the_gate_s_words(self, tmp_path,
                                                                    monkeypatch):
        srv = self._case(tmp_path, monkeypatch)
        message = ("gingival-relief gate: the 0.20mm gingival relief ate the screw "
                   "channel of tooth 29 (atlantis/zimmer-4.5 7030) ... re-run with a "
                   "smaller gingival offset (asked 0.20mm) — package NOT emitted")

        def _refuse(**kwargs):
            raise ValueError(message)

        monkeypatch.setattr(srv, "run_auto_case", _refuse)
        with pytest.raises(HTTPException) as exc:
            srv.run("c", srv.RunIn(sites=[_site(tooth=29)], model="zimmer-4.5",
                                   construction_path="atlantis/zimmer-4.5-scanbody.stl"))
        assert exc.value.status_code == 409
        assert exc.value.detail == message
        assert "smaller gingival offset" in exc.value.detail
        # a refused run must not leave a result behind for the next request to serve
        assert not (tmp_path / "c" / "run.json").exists()
