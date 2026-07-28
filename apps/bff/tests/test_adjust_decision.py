"""THE DELIVERY-vs-SKIP FORK (client 2026-07-27: "Skipping adjust should be optional
we should have two options one to skip and another to delivery — Delivery vs Skip
Adjustments") — POST /api/case-sessions/{id}/adjust-decision.

Declare's single Continue hid a decision. With nothing flagged it walked straight past
Adjust and nothing in the case's record could ever say whether the fits had been
reworked or waved through; with something flagged the operator had one button and no
way to state they had chosen to ship anyway. The fork makes the choice explicit and
KEEPS it.

What this route is and is not:

  - an ACT, not a status claim (the introspection allowlist's doctrine, extended in
    its own words): it moves no site, opens and closes no stage, and nothing about
    reachability reads it. Skip never blocks navigating to Adjust — pinned below.
  - REVERSIBLE: a later decision replaces the record; newest act wins (slice-8's rule).
  - keyed to the run: the run boundary clears it with the pointer, so a decision can
    never outlive the verdicts it was made over.
  - EVIDENCE: the decision word rides into the confirmation's bundle (test_deliver's
    pin), so what a client confirms includes whether adjustments were skipped.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore, SiteStatus

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client
from test_run_resource import FakeWorker, client_with, row, seed_ready


DECIDE = "/api/case-sessions/neodent-gm/adjust-decision"


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def decide(client, decision="skip"):
    return client.post(DECIDE, json={"decision": decision})


def forked_client(settings, product_root, rows=None):
    rows = rows if rows is not None else [row(4), row(13)]
    return landed_client(settings, product_root, rows, files=PACKAGE_FILES)


# --- the refusals name what the fork stands on ------------------------------------------

class TestTheForkNeedsVerdictsToForkOver:
    def test_an_unknown_case_is_a_404(self, settings):
        client = client_with(settings, FakeWorker())
        assert client.post("/api/case-sessions/nope/adjust-decision",
                           json={"decision": "skip"}).status_code == 404

    def test_without_a_done_run_there_is_nothing_to_decide_about(
            self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker())
        res = decide(client)
        assert res.status_code == 422
        assert "no completed current run" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").adjust_decision is None

    def test_a_site_short_of_a_verdict_refuses_and_names_it(
            self, settings, product_root):
        """Every site must carry a VERDICT (ready or flagged) — a site still at
        previewed has no fit to skip or rework, so the fork would be a choice made
        over half the case."""
        client = forked_client(settings, product_root)
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.sites["13"].status = SiteStatus.PREVIEWED
        store.save(session)
        res = decide(client)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13" in detail and "previewed" in detail

    @pytest.mark.parametrize("body", [
        {"decision": "maybe"},                    # not one of the two acts
        {"decision": "skip", "status": "ready"},  # a smuggled claim (extra=forbid)
        {},                                       # the act must be stated
    ])
    def test_the_body_carries_exactly_one_of_the_two_acts(
            self, settings, product_root, body):
        client = forked_client(settings, product_root)
        assert client.post(DECIDE, json=body).status_code == 422


# --- the act lands, and stays an act ----------------------------------------------------

class TestTheDecisionIsRecorded:
    @pytest.mark.parametrize("decision", ["skip", "adjust"])
    def test_the_record_carries_the_decision_the_time_and_the_run(
            self, settings, product_root, decision):
        client = forked_client(settings, product_root)
        res = decide(client, decision)
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        record = session.adjust_decision
        assert record.decision == decision
        assert record.at
        assert record.run_id == session.run.run_id
        # and the detail says so, for the surface that must show what was decided
        view = res.json()["session"]["adjust_decision"]
        assert view == {"decision": decision, "at": record.at,
                        "run_id": record.run_id}

    def test_a_later_decision_replaces_the_earlier_one(
            self, settings, product_root):
        # REVERSIBLE by construction (the slice-8 rule): the newest act wins, and
        # nothing about skipping is a door that shuts
        client = forked_client(settings, product_root)
        assert decide(client, "skip").status_code == 200
        assert decide(client, "adjust").status_code == 200
        assert SessionStore(product_root).load(
            "neodent-gm").adjust_decision.decision == "adjust"

    def test_deciding_to_skip_moves_no_site_and_touches_no_run(
            self, settings, product_root):
        """An ACT, not a status claim: the ladder and the run receipt are exactly
        where they were. Skip is a record of a choice, never a shortcut through
        anything the server derives."""
        client = forked_client(settings, product_root, rows=[row(4, level="attention"),
                                                            row(13)])
        before = SessionStore(product_root).load("neodent-gm")
        assert decide(client, "skip").status_code == 200
        after = SessionStore(product_root).load("neodent-gm")
        assert {t: s.status for t, s in after.sites.items()} == \
            {t: s.status for t, s in before.sites.items()}
        assert after.run.model_dump() == before.run.model_dump()

    def test_a_flagged_case_may_still_be_skipped(self, settings, product_root):
        # the client's own ask: skipping is OPTIONAL, not forbidden — a flagged fit
        # the lab chooses to ship is faced again at Deliver (per-row acknowledgment
        # or withhold), which is where that consequence belongs
        client = forked_client(settings, product_root,
                               rows=[row(4, level="action-needed"), row(13)])
        assert decide(client, "skip").status_code == 200


# --- the run boundary takes the decision with it ----------------------------------------

class TestTheDecisionFallsWithItsRun:
    def test_a_reset_boundary_clears_the_decision_with_the_run_pointer(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = forked_client(settings, product_root)
        assert decide(client, "skip").status_code == 200
        # a re-declaration is a reset boundary: the run pointer clears, and the
        # decision made over that run's verdicts cannot survive it
        assert client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "5030"}).status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.run is None
        assert session.adjust_decision is None

    def test_a_new_run_starts_the_fork_unfaced(self, settings, product_root):
        client = forked_client(settings, product_root)
        assert decide(client, "skip").status_code == 200
        seed_ready(product_root)   # re-ready the sites the first run flagged nothing on
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        assert SessionStore(product_root).load(
            "neodent-gm").adjust_decision is None
