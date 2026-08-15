"""THE RIM BORDER-POINTS INTAKE AID (§10-AL, client: "we lost the tool we had in the
demo where we made points around the border of the healing cap in the scan").

The demo let the operator click points around a cap's rim; the fit fed the rim
diameter (variant identification) and the centre. §10-AH's own measurement (every
pair-shaped re-mark seed LOST to the bare click on the DEV metric) scoped the
product's restoration to an INTAKE capture aid, not a seat input: this route records
WHERE the operator clicked, never derives a pose from it.

What this file pins:

  1. validation — 3..12 points, each an [x, y, z] triple, extra=forbid;
  2. set + echo — ``PUT`` persists and ``SiteView.rim_points`` serves it back;
  3. clear — ``DELETE`` reverses it, refusing 422 over nothing standing;
  4. idempotence — an identical re-PUT records no second act;
  5. the run request carries the points beside ``marked_centers`` (the wire is
     forward-compatible even though nothing downstream reads the key yet — see
     ``bff.ports.worker.InProcessWorker._selection``'s own docstring comment for
     why consuming it further is out of this slice's scope).
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore

from conftest import make_data_tree
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for

CASE = "neodent-gm"
THREE_POINTS = [[1.0, 0.0, 3.0], [1.0, 1.0, 3.0], [0.0, 1.0, 3.0]]


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def put_points(client, tooth: int, points):
    return client.put(f"/api/case-sessions/{CASE}/sites/{tooth}/rim-points",
                      json={"points": points})


class TestValidation:
    def test_fewer_than_three_points_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = put_points(client, 4, THREE_POINTS[:2])
        assert r.status_code == 422, r.text
        assert "between 3 and 12" in r.text

    def test_more_than_twelve_points_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        thirteen = [[float(i), 0.0, 0.0] for i in range(13)]
        r = put_points(client, 4, thirteen)
        assert r.status_code == 422, r.text
        assert "between 3 and 12" in r.text

    def test_exactly_three_and_twelve_are_both_accepted(self, settings):
        client = client_with(settings, FakeWorker())
        assert put_points(client, 4, THREE_POINTS).status_code == 200
        twelve = [[float(i), 0.0, 0.0] for i in range(12)]
        assert put_points(client, 13, twelve).status_code == 200

    def test_a_point_that_is_not_three_numbers_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = put_points(client, 4, [[1.0, 0.0], [1.0, 1.0, 3.0], [0.0, 1.0, 3.0]])
        assert r.status_code == 422, r.text

    def test_a_non_finite_point_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = client.put(
            f"/api/case-sessions/{CASE}/sites/4/rim-points",
            content='{"points": [[0.0, 0.0, NaN], [1.0, 1.0, 3.0], [0.0, 1.0, 3.0]]}',
            headers={"content-type": "application/json"})
        assert r.status_code == 422, r.text

    def test_the_body_cannot_carry_anything_else(self, settings):
        client = client_with(settings, FakeWorker())
        r = client.put(f"/api/case-sessions/{CASE}/sites/4/rim-points",
                       json={"points": THREE_POINTS, "status": "ready"})
        assert r.status_code == 422, r.text

    def test_an_unknown_tooth_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = put_points(client, 42, THREE_POINTS)
        assert r.status_code == 404, r.text


class TestSetAndEcho:
    def test_set_persists_and_serves_on_the_site_view(self, settings, product_root):
        client = client_with(settings, FakeWorker())
        r = put_points(client, 4, THREE_POINTS)
        assert r.status_code == 200, r.text
        by_tooth = {s["tooth"]: s for s in r.json()["sites"]}
        assert by_tooth[4]["rim_points"] == THREE_POINTS
        assert by_tooth[13]["rim_points"] is None
        persisted = SessionStore(product_root).load(CASE)
        assert persisted.sites["4"].rim_points == THREE_POINTS

    def test_a_session_only_marked_site_also_echoes_its_points(
            self, settings, product_root):
        # a cap the detector missed (POST .../sites) still gets rim points
        client = client_with(settings, FakeWorker())
        marked = client.post(f"/api/case-sessions/{CASE}/sites",
                             json={"tooth": 7, "center": [1.0, 1.0, 1.0]})
        assert marked.status_code == 200, marked.text
        r = put_points(client, 7, THREE_POINTS)
        assert r.status_code == 200, r.text
        by_tooth = {s["tooth"]: s for s in r.json()["sites"]}
        assert by_tooth[7]["rim_points"] == THREE_POINTS

    def test_setting_records_one_activity_entry(self, settings, product_root):
        client = client_with(settings, FakeWorker())
        before = SessionStore(product_root).load(CASE).activity_recorded
        assert put_points(client, 4, THREE_POINTS).status_code == 200
        after = SessionStore(product_root).load(CASE).activity_recorded
        assert after == before + 1

    def test_an_identical_re_put_records_no_second_act(self, settings, product_root):
        client = client_with(settings, FakeWorker())
        assert put_points(client, 4, THREE_POINTS).status_code == 200
        before = SessionStore(product_root).load(CASE).activity_recorded
        assert put_points(client, 4, THREE_POINTS).status_code == 200
        after = SessionStore(product_root).load(CASE).activity_recorded
        assert after == before


class TestClear:
    def test_clear_reverses_a_standing_set(self, settings, product_root):
        client = client_with(settings, FakeWorker())
        assert put_points(client, 4, THREE_POINTS).status_code == 200
        r = client.delete(f"/api/case-sessions/{CASE}/sites/4/rim-points")
        assert r.status_code == 200, r.text
        by_tooth = {s["tooth"]: s for s in r.json()["sites"]}
        assert by_tooth[4]["rim_points"] is None
        persisted = SessionStore(product_root).load(CASE)
        assert persisted.sites["4"].rim_points is None

    def test_clearing_nothing_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = client.delete(f"/api/case-sessions/{CASE}/sites/4/rim-points")
        assert r.status_code == 422, r.text

    def test_clearing_an_unknown_tooth_refuses(self, settings):
        client = client_with(settings, FakeWorker())
        r = client.delete(f"/api/case-sessions/{CASE}/sites/42/rim-points")
        assert r.status_code == 404, r.text


class TestTheRunRequestCarriesThePoints:
    """THE PORT-THREADING PIN: rim points ride the authorized run's submitted
    ``selection`` beside ``marked_centers`` and ``alignment_evidence`` — additive,
    forward-compatible plumbing (see ``bff.ports.worker.InProcessWorker._selection``
    for why nothing downstream reads the key past this dict yet)."""

    def test_the_submitted_selection_carries_rim_points(self, settings, product_root):
        client = client_with(settings, FakeWorker(summary=summary_for(
            [row(4), row(13)])))
        store = SessionStore(product_root)
        seed_ready(product_root)
        s = store.load(CASE)
        s.sites["4"].rim_points = THREE_POINTS
        store.save(s)

        res = client.post(f"/api/case-sessions/{CASE}/run")
        assert res.status_code == 200, res.text
        ((_case_id, request),) = client.app.state.worker.submitted
        assert request["selection"]["rim_points"] == {"4": THREE_POINTS}

    def test_no_site_holding_points_ships_an_empty_map(self, settings, product_root):
        client = client_with(settings, FakeWorker(summary=summary_for(
            [row(4), row(13)])))
        seed_ready(product_root)
        res = client.post(f"/api/case-sessions/{CASE}/run")
        assert res.status_code == 200, res.text
        ((_case_id, request),) = client.app.state.worker.submitted
        assert request["selection"]["rim_points"] == {}
