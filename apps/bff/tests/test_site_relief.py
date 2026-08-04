"""PER-SITE RELIEF (§10-B/C, landed on the §10-AC lane): one site's own relief ask,
set on Adjustment. Relief shapes the EMITTED part and nothing else, so the act moves
no rung and retires no review; over a DONE run it re-emits from the run's own poses
with ``site_reliefs`` riding the selection; without one it persists and rides the
next run. Null clears the override so the case-level value stands again.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore, SiteStatus

from conftest import make_data_tree
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for

CASE = "neodent-gm"


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def landed(settings, product_root):
    worker = FakeWorker(summary=summary_for([row(4), row(13)]))
    client = client_with(settings, worker)
    seed_ready(product_root)
    assert client.post(f"/api/case-sessions/{CASE}/run").status_code == 200
    return client, worker


def put_relief(client, tooth: int, value):
    return client.put(f"/api/case-sessions/{CASE}/sites/{tooth}/relief",
                      json={"gingival_offset_mm": value})


class TestTheOverridePersists:
    def test_set_and_serve(self, settings, product_root):
        client, _ = landed(settings, product_root)
        res = put_relief(client, 4, 0.05)
        assert res.status_code == 200, res.text
        by_tooth = {s["tooth"]: s for s in res.json()["sites"]}
        assert by_tooth[4]["gingival_offset_mm"] == 0.05
        assert by_tooth[13]["gingival_offset_mm"] is None

    def test_null_clears_it(self, settings, product_root):
        client, _ = landed(settings, product_root)
        put_relief(client, 4, 0.05)
        res = put_relief(client, 4, None)
        assert res.status_code == 200
        by_tooth = {s["tooth"]: s for s in res.json()["sites"]}
        assert by_tooth[4]["gingival_offset_mm"] is None

    def test_the_bounds_are_the_case_asks_own(self, settings, product_root):
        client, _ = landed(settings, product_root)
        res = put_relief(client, 4, 9.0)
        assert res.status_code == 422
        assert "clearance between 0 and" in res.text

    def test_an_unknown_tooth_is_refused(self, settings, product_root):
        client, _ = landed(settings, product_root)
        assert put_relief(client, 42, 0.05).status_code in (404, 422)


class TestTheActReEmits:
    def test_over_a_done_run_the_selection_carries_every_override(
            self, settings, product_root):
        client, worker = landed(settings, product_root)
        source = SessionStore(product_root).load(CASE).run.run_id
        assert put_relief(client, 4, 0.05).status_code == 200
        (_r1), (case_id, req) = worker.submitted
        assert case_id == CASE
        assert req["mode"] == "reemit"
        assert req["source_run_id"] == source
        assert req["selection"]["site_reliefs"] == {"4": 0.05}
        session = SessionStore(product_root).load(CASE)
        assert session.run.state == "done"
        # relief touches no pose: the rungs stand
        assert session.sites["4"].status is SiteStatus.READY
        assert session.sites["13"].status is SiteStatus.READY

    def test_without_a_run_it_simply_rides_the_next_one(
            self, settings, product_root):
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        seed_ready(product_root)
        assert put_relief(client, 4, 0.05).status_code == 200
        assert worker.submitted == []   # nothing re-emitted: nothing to re-emit
        # …and the next authorized run carries it
        assert client.post(f"/api/case-sessions/{CASE}/run").status_code == 200
        ((_case_id, req),) = worker.submitted
        assert req["selection"]["site_reliefs"] == {"4": 0.05}

    def test_an_identical_reassertion_is_not_an_act(self, settings, product_root):
        client, worker = landed(settings, product_root)
        put_relief(client, 4, 0.05)
        submits = len(worker.submitted)
        assert put_relief(client, 4, 0.05).status_code == 200
        assert len(worker.submitted) == submits   # no second re-emit

    def test_the_choices_reemit_carries_standing_overrides_too(
            self, settings, product_root):
        client, worker = landed(settings, product_root)
        put_relief(client, 4, 0.05)
        # a case-level relief change re-emits again — the site override rides it
        assert client.put(f"/api/case-sessions/{CASE}/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.1}).status_code == 200
        (_a, _b, (case_id, req)) = worker.submitted
        assert req["mode"] == "reemit"
        assert req["selection"]["gingival_offset_mm"] == 0.1
        assert req["selection"]["site_reliefs"] == {"4": 0.05}
