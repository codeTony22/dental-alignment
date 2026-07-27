"""THE CASE-SESSION RESOURCE (plan §3/§7 slices 1+4): the worklist, the flow-shaped
case resource, and the first ACTIONS — detect (a compute trigger) and choices (operator
acts) — derived from worker facts + the session store, never from a client's claims.

The one structural promise these tests must keep enforceable (grill AM-4): site-queue
statuses, verdicts and gate outcomes are DERIVED. Slice 4 deliberately ends GET-only —
the new invariant is stronger than the old one, not weaker: every non-GET route sits on
an explicit allowlist, and NO allowlisted request model carries a status-shaped field —
asserted on the route table AND the Pydantic models, so a future PATCH (or a "status"
field slipped into a legitimate write) cannot arrive unnoticed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bff.main import create_app
from bff.resources import case_sessions
from bff.session import RunSession, SessionStore, SiteSession, SiteStatus
from case_prep.application.detection import (DetectedSite, DetectionResult,
                                             ScanUnreadable, SuggestedSiteCapture)

CAP_PASS = {"verdict": "pass", "rim_z_mm": 1.2, "checks": []}
CAP_RESCAN = {"verdict": "rescan", "rim_z_mm": None,
              "checks": [{"name": "rim_arc", "value": 0.31, "bound_pass": 0.75,
                          "bound_rescan": 0.5, "verdict": "rescan",
                          "message": "Only 31% of the rim arc is captured."}]}


def stub_detection() -> DetectionResult:
    """A detection result shaped exactly like the application layer's — teeth 4 and 13
    match the conftest tree's curated sites; one extra proposal has no tooth to inherit."""
    return DetectionResult(
        proposals=(
            DetectedSite(center=(1.0, 2.0, 3.0), void_ratio=0.10,
                         rim_below_cusps_mm=0.5, tooth_guess=4, capture=CAP_PASS),
            DetectedSite(center=(40.0, 2.0, 3.0), void_ratio=0.35,
                         rim_below_cusps_mm=1.1, tooth_guess=None, capture=CAP_RESCAN),
        ),
        suggested=(
            SuggestedSiteCapture(tooth=4, center=(1.0, 2.0, 3.0), capture=CAP_PASS),
            SuggestedSiteCapture(tooth=13, center=(4.0, 5.0, 6.0), capture=CAP_RESCAN),
        ),
    )


class TestWorklist:
    def test_one_row_per_case_with_the_site_rollup(self, client):
        rows = client.get("/api/case-sessions").json()
        assert len(rows) == 1
        (row,) = rows
        assert row["id"] == "neodent-gm"
        assert row["doctor"] == "Doctor Neodent GM"
        assert row["jaw"] == "upper"
        assert row["suggested_model"] == "neodent-gm"
        assert row["sites"] == {"total": 2, "declared": 0, "ready": 0, "flagged": 0}
        assert row["run_state"] == "none"
        assert row["confirmed"] is False

    def test_persisted_session_state_reaches_the_rollup(self, settings):
        # state changes arrive ONLY via the server-side store — this is the same door
        # later slices use, and the worklist must reflect it on the next read
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["13"] = SiteSession(status=SiteStatus.FLAGGED, declared_variant="5020")
        s.run = RunSession(job_id="job-1", state="done")
        store.save(s)
        client = TestClient(create_app(settings))
        (row,) = client.get("/api/case-sessions").json()
        assert row["sites"] == {"total": 2, "declared": 1, "ready": 0, "flagged": 1}
        assert row["run_state"] == "done"


class TestCaseSessionDetail:
    def test_an_unknown_case_is_a_404(self, client):
        assert client.get("/api/case-sessions/no-such-case").status_code == 404

    def test_the_flow_shape(self, client):
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["case"] == {
            "id": "neodent-gm",
            "doctor": "Doctor Neodent GM",
            "jaw": "upper",
            "scan_filename": "upper_jaw.stl",
            "suggested_model": "neodent-gm",
            "suggested_construction": "dess/neodent-gm-scanbody.stl",
        }
        assert [s["tooth"] for s in body["sites"]] == [4, 13]
        assert all(s["status"] == "detected" for s in body["sites"])
        assert body["sites"][0]["center"] == [1.0, 2.0, 3.0]
        # the catalog rides along so Declare can render without a second round of calls
        assert {g["model"] for g in body["catalog"]["groups"]} == {"neodent-gm"}
        assert [c["path_id"] for c in body["catalog"]["constructions"]] == [
            "dess/neodent-gm-scanbody.stl"]
        # nothing declared -> no ceilings to read
        assert body["relief_ceilings"] == []
        # detection has not run; choices not yet made — both honestly empty, never guessed
        assert body["detection"] is None
        assert body["choices"] == {
            "construction_path": None,
            "jaw": None,
            "gingival_offset_mm": None,
            "gingival_offset_default_mm": 0.2,
            "complete": False,
        }
        assert body["session"] == {
            "tenant_id": "local",
            "adjust_visited": False,
            "run_state": "none",
            "confirmed": False,
            "payment_authorized": False,
        }

    def test_session_statuses_overlay_the_detected_sites(self, settings):
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["13"] = SiteSession(status=SiteStatus.READY, declared_variant="5020")
        store.save(s)
        client = TestClient(create_app(settings))
        sites = {v["tooth"]: v for v in
                 client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        assert sites[13]["status"] == "ready"
        assert sites[13]["declared_variant"] == "5020"
        assert sites[4]["status"] == "detected"

    def test_a_declared_variant_the_catalog_does_not_carry_is_an_error_row(
            self, tmp_path, product_root):
        # the ceiling column must not take the whole resource down: the refusal is a row
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data2", declared=(None, "9999"))
        client = TestClient(create_app(Settings(data_root=data, product_root=product_root)))
        (ceiling,) = client.get("/api/case-sessions/neodent-gm").json()["relief_ceilings"]
        assert ceiling["variant"] == "9999"
        assert ceiling["max_safe_mm"] is None
        assert "9999" in ceiling["error"]


class TestCaseScan:
    """GET /{id}/scan (plan §7 slice 3): the product's main stage streams the doctor's
    scan through the BFF — the application layer's CaseRecord.scan path, never a
    client-supplied one (no path parameter reaches the filesystem)."""

    @staticmethod
    def _tiny_stl() -> bytes:
        # A REAL (if minimal) binary STL: 80-byte header, uint32 triangle count = 1,
        # one 50-byte triangle record — enough for a parser to accept, small enough
        # to compare byte-for-byte.
        import struct
        header = b"tiny fixture stl".ljust(80, b"\0")
        triangle = struct.pack(
            "<12fH",
            0.0, 0.0, 1.0,        # normal
            0.0, 0.0, 0.0,        # v0
            1.0, 0.0, 0.0,        # v1
            0.0, 1.0, 0.0,        # v2
            0,                    # attribute byte count
        )
        return header + struct.pack("<I", 1) + triangle

    def test_streams_the_case_scan_bytes(self, settings):
        stl = self._tiny_stl()
        (settings.data_root / "scans/doctor-neodent-gm/upper_jaw.stl").write_bytes(stl)
        client = TestClient(create_app(settings))
        res = client.get("/api/case-sessions/neodent-gm/scan")
        assert res.status_code == 200
        assert res.content == stl
        assert res.headers["content-type"] == "model/stl"

    def test_an_unknown_case_scan_is_the_same_404_refusal(self, client):
        res = client.get("/api/case-sessions/no-such-case/scan")
        assert res.status_code == 404
        assert "unknown case" in res.json()["detail"]


class TestDetect:
    """POST /{id}/detect (plan §4): detection fires automatically on Intake; the route
    is a compute TRIGGER that persists what the application layer derived. The physics
    is the worker's (test_detection.py pins it on the real tree); what belongs here is
    orchestration — run-once, persist, refuse, re-derive on explicit ask — so the
    application function is stubbed at the resource seam."""

    def _client_with_stub(self, settings, monkeypatch, result=None):
        calls = []

        def stub(case):
            calls.append(case.id)
            if isinstance(result, Exception):
                raise result
            return result or stub_detection()

        monkeypatch.setattr(case_sessions, "detect", stub)
        return TestClient(create_app(settings)), calls

    def test_an_unknown_case_is_a_404(self, client):
        assert client.post("/api/case-sessions/no-such-case/detect").status_code == 404

    def test_detect_runs_persists_and_returns_the_updated_detail(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        body = client.post("/api/case-sessions/neodent-gm/detect").json()
        assert calls == ["neodent-gm"]
        # the proposals ride along, tooth guesses honest (None where nothing matched)
        assert [p["tooth_guess"] for p in body["detection"]["proposals"]] == [4, None]
        # every curated site now carries its capture verdict — the chair-side fact
        sites = {s["tooth"]: s for s in body["sites"]}
        assert sites[4]["capture"]["verdict"] == "pass"
        assert sites[13]["capture"]["verdict"] == "rescan"
        # and the store has it: a fresh app (a restart) serves the same facts
        rows = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert rows[0]["detected"] is True

    def test_re_post_returns_current_state_without_rederiving(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        client.post("/api/case-sessions/neodent-gm/detect")
        body = client.post("/api/case-sessions/neodent-gm/detect").json()
        assert calls == ["neodent-gm"]  # ONCE — idempotent, not a re-run per click
        assert body["detection"] is not None

    def test_fresh_is_the_explicit_re_ask(self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        client.post("/api/case-sessions/neodent-gm/detect")
        client.post("/api/case-sessions/neodent-gm/detect?fresh=1")
        assert calls == ["neodent-gm", "neodent-gm"]

    def test_an_unreadable_scan_is_a_422_in_the_workers_words(
            self, settings, monkeypatch):
        client, _ = self._client_with_stub(
            settings, monkeypatch,
            result=ScanUnreadable("the scan upper_jaw.stl holds no surface to detect on"))
        res = client.post("/api/case-sessions/neodent-gm/detect")
        assert res.status_code == 422
        assert "holds no surface" in res.json()["detail"]
        # a refusal persists nothing — the next POST may try again
        assert TestClient(create_app(settings)).get(
            "/api/case-sessions").json()[0]["detected"] is False


class TestChoices:
    """PUT /{id}/choices (plan §4/§6): the case-level operator choices, re-validated by
    the BFF in the demo's own words — the UI is untrusted (AM-9, ledger row 4)."""

    def test_valid_choices_persist_and_the_detail_echoes_them(self, settings):
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper",
            "gingival_offset_mm": 0.15,
        }).json()
        assert body["choices"] == {
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper",
            "gingival_offset_mm": 0.15,
            "gingival_offset_default_mm": 0.2,
            "complete": True,
        }
        # persisted: a fresh app serves the same choices and the worklist's fact
        row, = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert row["choices_complete"] is True

    def test_partial_choices_are_honest_not_complete(self, client):
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "lower"}).json()
        assert body["choices"]["jaw"] == "lower"
        assert body["choices"]["construction_path"] is None
        assert body["choices"]["complete"] is False

    def test_an_unknown_construction_part_is_refused_by_catalog_membership(self, client):
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"construction_path": "dess/../../../etc/passwd"})
        assert res.status_code == 422
        assert "unknown construction part" in res.json()["detail"]

    def test_a_bad_jaw_is_refused_in_the_demos_words(self, client):
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"jaw": "sideways"})
        assert res.status_code == 422
        assert "jaw must be one of upper, lower" in res.text

    def test_relief_out_of_bounds_is_refused_in_the_demos_words(self, client):
        for bad in (-0.1, 1.5):
            res = client.put("/api/case-sessions/neodent-gm/choices",
                             json={"gingival_offset_mm": bad})
            assert res.status_code == 422
            assert "clearance between 0 and 1.0mm" in res.text

    def test_a_non_finite_relief_is_refused(self, client):
        # the corpus' finiteness rule (server.py:260-266): NaN is a typo, not a choice.
        # The refusal itself must SERIALIZE — FastAPI's default 422 handler echoes the
        # offending input and json.dumps(allow_nan=False) turned the refusal into a 500
        # (bff.main's validation_refusal handler exists for exactly this).
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         content='{"gingival_offset_mm": NaN}',
                         headers={"content-type": "application/json"})
        assert res.status_code == 422
        assert "clearance between 0 and 1.0mm" in res.text

    def test_an_unknown_case_is_a_404(self, client):
        assert client.put("/api/case-sessions/no-such-case/choices",
                          json={"jaw": "upper"}).status_code == 404

    def test_the_ceiling_follows_the_chosen_construction(
            self, tmp_path, product_root, monkeypatch):
        """Plan §4: the relief input lives beside ITS ceiling — the one for the part the
        operator picked, not the name-matched suggestion. The ceiling read is stubbed
        (its physics is the worker's own real-tree test); what is pinned here is which
        construction the resource asks about."""
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data2", declared=("5020", None))
        atlantis = data / "library/construction/atlantis"
        atlantis.mkdir(parents=True)
        (atlantis / "zimmer-4.5-scanbody.stl").touch()
        asked = []

        def stub_ceiling(data_root, construction_path, model, variant):
            asked.append(construction_path)
            return {"variant": variant, "construction_path": construction_path,
                    "model": model, "max_safe_mm": 0.5}

        monkeypatch.setattr(case_sessions, "relief_ceiling", stub_ceiling)
        client = TestClient(create_app(Settings(data_root=data,
                                                product_root=product_root)))
        client.get("/api/case-sessions/neodent-gm")
        assert asked == ["dess/neodent-gm-scanbody.stl"]  # the suggestion, pre-choice
        body = client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "atlantis/zimmer-4.5-scanbody.stl"}).json()
        assert asked[-1] == "atlantis/zimmer-4.5-scanbody.stl"
        assert body["relief_ceilings"][0]["construction_path"] == \
            "atlantis/zimmer-4.5-scanbody.stl"


class TestStatusesAreNeverClientWritable:
    """STRUCTURAL (AM-4), slice-4 form. The old invariant was "the route table is
    GET-only"; slice 4 updates it DELIBERATELY, not around: choices and compute triggers
    are legitimate writes — claimed OUTCOMES are not. So (1) every non-GET route must
    sit on the explicit allowlist below, and (2) no allowlisted route's request model
    may carry a status-shaped field, walked recursively so a nested model cannot smuggle
    one. A presentational app PATCHing a flagged site to ready stays impossible — there
    is no such route, and no legitimate route's body could express it."""

    ACTION_ALLOWLIST = {
        ("POST", "/api/case-sessions/{case_id}/detect"),   # compute trigger, no body
        ("PUT", "/api/case-sessions/{case_id}/choices"),   # operator acts (plan §4)
    }
    STATUS_SHAPED = {"status", "state", "verdict", "gate", "flagged", "ready",
                     "confirmed"}

    @staticmethod
    def _field_names(model, seen=None):
        """Every field name of a Pydantic model, recursing into nested models."""
        import typing

        from pydantic import BaseModel

        seen = seen if seen is not None else set()
        if model in seen:  # cycles cannot hide a field either
            return set()
        seen.add(model)
        names = set()
        for name, field in model.model_fields.items():
            names.add(name)
            stack = [field.annotation]
            while stack:
                t = stack.pop()
                if isinstance(t, type) and issubclass(t, BaseModel):
                    names |= TestStatusesAreNeverClientWritable._field_names(t, seen)
                else:
                    stack.extend(typing.get_args(t))
        return names

    def _case_session_routes(self, client):
        return [r for r in client.app.routes
                if getattr(r, "path", "").startswith("/api/case-sessions")]

    def test_every_non_get_route_is_on_the_allowlist(self, client):
        offenders = []
        for route in self._case_session_routes(client):
            for method in set(route.methods) - {"GET", "HEAD", "OPTIONS"}:
                if (method, route.path) not in self.ACTION_ALLOWLIST:
                    offenders.append((method, route.path))
        assert offenders == []
        # and both directions hold: the allowlist names real routes, not wishes
        present = {(m, r.path) for r in self._case_session_routes(client)
                   for m in r.methods}
        assert self.ACTION_ALLOWLIST <= present

    def test_no_action_request_model_carries_a_status_shaped_field(self, client):
        offenders = []
        for route in self._case_session_routes(client):
            if not ({(m, route.path) for m in route.methods} & self.ACTION_ALLOWLIST):
                continue
            body_field = getattr(route, "body_field", None)
            if body_field is None:
                continue  # the detect trigger: no body at all — nothing to claim with
            shaped = (self._field_names(body_field.field_info.annotation)
                      & self.STATUS_SHAPED)
            if shaped:
                offenders.append((route.path, sorted(shaped)))
        assert offenders == []

    def test_reading_writes_nothing_to_the_product_data_plane(self, client, product_root):
        client.get("/api/case-sessions")
        client.get("/api/case-sessions/neodent-gm")
        assert not product_root.exists()
