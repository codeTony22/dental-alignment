"""THE CASE-SESSION READ MODEL (plan §3/§7 slice 1): the worklist and the flow-shaped
case resource, derived from worker facts + the session store — never from a client.

The one structural promise these tests must keep enforceable (grill AM-4): site-queue
statuses are DERIVED. There is no route through which an HTTP client can write a status,
a verdict, or a gate outcome — asserted on the ROUTE TABLE (GET-only), not on handler
politeness, so a future PATCH cannot slip in unnoticed.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from bff.main import create_app
from bff.session import RunSession, SessionStore, SiteSession, SiteStatus


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


class TestStatusesAreNeverClientWritable:
    def test_every_case_session_route_is_read_only(self, client):
        """STRUCTURAL (AM-4): a presentational app PATCHing a flagged site to ready must
        be impossible, not merely unstyled. Asserted on the route table itself."""
        offenders = [
            (route.path, sorted(m for m in route.methods if m not in ("HEAD", "OPTIONS")))
            for route in client.app.routes
            if getattr(route, "path", "").startswith("/api/case-sessions")
            and set(getattr(route, "methods", ())) - {"GET", "HEAD", "OPTIONS"}
        ]
        assert offenders == []
        # and the resource exists at all — an empty route table would pass vacuously
        assert any(getattr(r, "path", "").startswith("/api/case-sessions")
                   for r in client.app.routes)

    def test_reading_writes_nothing_to_the_product_data_plane(self, client, product_root):
        client.get("/api/case-sessions")
        client.get("/api/case-sessions/neodent-gm")
        assert not product_root.exists()
