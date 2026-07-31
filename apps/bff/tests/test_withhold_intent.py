"""DROPPING A CAP FROM ADJUST (design flow.dc.html dropSite 1345-1354, queue row
1183-1191; gap ``drop-a-cap-from-adjust``, 2026-07-31).

The design words it "drop this cap — don't align or bill it", reversible with "bring
this cap back into the case". The product ALREADY had the act: a confirmation-time
per-site disposition ``release | withhold``. What it did not have was REACH — the act
was only expressible from Deliver, at signing time, and an operator reworking a
stubborn cap at Adjust had to carry the decision all the way there to record it.

So there is no second exclusion concept here. There is ONE, with a draft stage: a
per-site WITHHOLD INTENT that PRE-FILLS the confirmation's dispositions. The
confirmation still signs; the intent is what the operator says before there is
anything to sign.

What this file pins, in the order the operator meets it:

  1. the act and its reversal, both reachable, both server-recorded;
  2. the intent PRE-FILLS confirm, and the body still OVERRIDES it (a draft never
     outranks a signature);
  3. the invoice quotes the intent BEFORE a confirmation exists — so what the
     operator reads and what they are charged cannot diverge (deliver.py's own rule);
  4. an intent that CONTRADICTS a standing confirmation retires it, and the payment
     record survives (money is not evidence — clear_confirmation's rule);
  5. it is not status-shaped: it says what the operator DOES, never what the site IS.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES
from test_deliver import (confirm, confirm_body, deliverable_client, pay,
                          release)
from test_run_resource import row


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


WITHHOLD = "/api/case-sessions/neodent-gm/sites/13/withhold"


def drop(client, withhold: bool = True, tooth: int = 13):
    return client.put(f"/api/case-sessions/neodent-gm/sites/{tooth}/withhold",
                      json={"withhold": withhold})


def site_of(detail: dict, tooth: int) -> dict:
    return next(s for s in detail["sites"] if s["tooth"] == tooth)


def stored(product_root):
    return SessionStore(product_root).load("neodent-gm")


# --- the act, and its reversal ----------------------------------------------------------

class TestTheActAndItsReversal:
    def test_a_fresh_site_intends_nothing(self, client):
        detail = client.get("/api/case-sessions/neodent-gm").json()
        assert site_of(detail, 13)["withhold_intent"] is False

    def test_dropping_a_cap_records_the_intent(self, client, product_root):
        res = drop(client)
        assert res.status_code == 200
        assert site_of(res.json(), 13)["withhold_intent"] is True
        assert stored(product_root).sites["13"].withhold_intent is True

    def test_bringing_it_back_is_the_same_route(self, client, product_root):
        assert drop(client).status_code == 200
        res = drop(client, withhold=False)
        assert res.status_code == 200
        assert site_of(res.json(), 13)["withhold_intent"] is False
        assert stored(product_root).sites["13"].withhold_intent is False

    def test_the_intent_needs_no_run_no_preview_and_no_declaration(self, client):
        """The whole point of the draft: the decision is recordable AT THE MOMENT it
        is taken, not only once there is a confirmation to fold it into."""
        assert drop(client).status_code == 200

    def test_an_unknown_tooth_is_a_404(self, client):
        res = client.put("/api/case-sessions/neodent-gm/sites/99/withhold",
                         json={"withhold": True})
        assert res.status_code == 404

    def test_an_unknown_case_is_a_404(self, client):
        res = client.put("/api/case-sessions/nope/sites/13/withhold",
                         json={"withhold": True})
        assert res.status_code == 404

    def test_the_body_forbids_anything_but_the_act(self, client):
        res = client.put(WITHHOLD, json={"withhold": True, "status": "flagged"})
        assert res.status_code == 422

    def test_both_directions_land_in_the_activity_log(self, client, product_root):
        drop(client)
        drop(client, withhold=False)
        events = [e.event for e in stored(product_root).activity]
        assert events.count("site-withhold-intent") == 2

    def test_re_asserting_the_same_intent_records_no_second_act(
            self, client, product_root):
        """An identical re-act is not an act (the SeatedSelection precedent): it
        must not spend the log's bounded window on a line describing nothing."""
        drop(client)
        drop(client)
        events = [e.event for e in stored(product_root).activity]
        assert events.count("site-withhold-intent") == 1

    def test_the_log_line_never_claims_the_site_was_not_aligned(
            self, client, product_root):
        """THE DESIGN'S OWN WORDS ARE HALF A LIE POST-RUN (design 1352: "dropped —
        not aligned, not billed"). The alignment already ran; what is true is that
        nothing is released for it and it is not billed."""
        drop(client)
        entry = stored(product_root).activity[-1]
        assert entry.tooth == 13
        assert "not aligned" not in entry.detail
        assert "released" in entry.detail and "billed" in entry.detail


# --- the intent is a DRAFT; the confirmation is the act ---------------------------------

class TestTheIntentPreFillsTheConfirmation:
    def test_an_intent_pre_fills_an_unnamed_site_as_withheld(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert drop(client).status_code == 200
        assert confirm(client, confirm_body(dispositions={})).status_code == 200
        record = stored(product_root).confirmation
        assert record is not None
        assert record.dispositions == {"4": "release", "13": "withhold"}

    def test_the_body_still_signs_and_overrides_the_draft(
            self, settings, product_root):
        """An intent is not a signature. A confirmation that names the site
        explicitly is the operator saying so AT SIGNING TIME, and it wins."""
        client = deliverable_client(settings, product_root)
        assert drop(client).status_code == 200
        assert confirm(client, confirm_body(
            dispositions={"13": "release"},
            acknowledged=(),
        )).status_code == 200
        record = stored(product_root).confirmation
        assert record is not None
        assert record.dispositions["13"] == "release"

    def test_a_dropped_flagged_site_needs_no_acknowledgment(
            self, settings, product_root):
        """AM-12's row-by-row acknowledgment is a gate on RELEASING a flagged site.
        A dropped one is not released, so there is nothing to acknowledge — and
        confirming must not demand an acknowledgment nobody owes."""
        client = deliverable_client(settings, product_root,
                                    rows=[row(4), row(13, level="attention")])
        assert confirm(client, confirm_body(dispositions={})).status_code == 422
        assert drop(client).status_code == 200
        assert confirm(client, confirm_body(dispositions={})).status_code == 200

    def test_clearing_the_intent_puts_the_site_back_in_the_next_confirmation(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        drop(client)
        drop(client, withhold=False)
        assert confirm(client, confirm_body(dispositions={})).status_code == 200
        record = stored(product_root).confirmation
        assert record is not None
        assert record.dispositions == {"4": "release", "13": "release"}


# --- the money the operator reads before they sign --------------------------------------

class TestTheInvoiceQuotesTheDraft:
    def test_an_intent_discounts_the_invoice_before_any_confirmation(
            self, settings, product_root):
        """deliver.py's own rule, applied to the draft: what the operator READ and
        what they were CHARGED cannot diverge. Quoting a dropped cap at the full
        release rate right up until the confirmation lands would be exactly that."""
        client = deliverable_client(settings, product_root)
        before = client.get("/api/case-sessions/neodent-gm/invoice").json()
        assert drop(client).status_code == 200
        after = client.get("/api/case-sessions/neodent-gm/invoice").json()
        assert after["total_cents"] < before["total_cents"]

    def test_the_quoted_price_equals_what_confirming_the_draft_charges(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        drop(client)
        quoted = client.get("/api/case-sessions/neodent-gm/invoice").json()
        assert confirm(client, confirm_body(dispositions={})).status_code == 200
        sealed = client.get("/api/case-sessions/neodent-gm/invoice").json()
        assert sealed["total_cents"] == quoted["total_cents"]


# --- what a drop does to a standing signature -------------------------------------------

class TestADropRetiresAContradictedConfirmation:
    def test_dropping_a_released_site_retires_confirmation_and_release(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert release(client).status_code == 200
        assert drop(client).status_code == 200
        session = stored(product_root)
        assert session.confirmation is None
        assert session.release is None

    def test_the_payment_record_survives(self, settings, product_root):
        """Money is not evidence (clear_confirmation's rule): the honest path after
        a drop is re-confirm + re-release, never re-charge."""
        client = deliverable_client(settings, product_root)
        confirm(client)
        pay(client)
        drop(client)
        assert stored(product_root).payment is not None

    def test_an_intent_the_confirmation_already_agrees_with_retires_nothing(
            self, settings, product_root):
        """An identical re-act must flip no equality and cost nobody a
        re-confirmation (the SeatedSelection precedent)."""
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body(
            dispositions={"13": "withhold"})).status_code == 200
        sealed = stored(product_root).confirmation
        assert drop(client).status_code == 200
        assert stored(product_root).confirmation == sealed

    def test_bringing_a_withheld_site_back_also_retires_the_confirmation(
            self, settings, product_root):
        """Both directions, symmetrically: a standing confirmation stands only
        while it still describes the operator's intent."""
        client = deliverable_client(settings, product_root)
        drop(client)
        assert confirm(client, confirm_body(dispositions={})).status_code == 200
        assert drop(client, withhold=False).status_code == 200
        assert stored(product_root).confirmation is None

    def test_the_retirement_is_recorded_in_the_log(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        confirm(client)
        drop(client)
        entry = stored(product_root).activity[-1]
        assert entry.event == "site-withhold-intent"
        assert "confirmation" in entry.detail


# --- the intent is an ACT, and geometry boundaries do not touch it ----------------------

class TestTheIntentSurvivesTheGeometryBoundaries:
    def test_a_choices_change_leaves_the_intent_standing(
            self, client, product_root):
        """A drop is a commercial/disclosure act about a SITE, like the turnaround
        ask: it describes no geometry, so the boundaries that retire previews and
        runs have nothing to say about it. Dropping the operator's decision because
        the relief moved would be a fabricated reversal."""
        drop(client)
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"construction_path": "dess/neodent-gm-scanbody.stl",
                               "jaw": "upper", "gingival_offset_mm": 0.35})
        assert res.status_code == 200
        assert stored(product_root).sites["13"].withhold_intent is True

    def test_a_full_case_reset_clears_it_with_everything_else(
            self, client, product_root):
        drop(client)
        assert client.post("/api/case-sessions/neodent-gm/reset").status_code == 200
        assert stored(product_root).sites == {}


# --- the doctrine ------------------------------------------------------------------------

class TestItIsNotStatusShaped:
    def test_the_route_cannot_express_a_verdict(self, client):
        """The body carries WHAT THE OPERATOR DOES and nothing else — there is no
        field a claimed fit-outcome could ride in on. Pinned here beside the act;
        the structural sweep over every route lives in test_case_sessions'
        allowlist."""
        from bff.resources.case_sessions import WithholdIntentIn

        assert set(WithholdIntentIn.model_fields) == {"withhold"}

    def test_a_dropped_site_keeps_climbing_the_same_ladder(self, client):
        """A drop buys the operator nothing on the status ladder: the site's rung
        is where it was, derived exactly as before."""
        before = site_of(client.get("/api/case-sessions/neodent-gm").json(), 13)
        after = site_of(drop(client).json(), 13)
        assert after["status"] == before["status"]


# --- the run still runs it (there is no second exclusion concept) -----------------------

class TestTheRunIsUntouched:
    def test_the_authorized_run_still_carries_a_dropped_site(
            self, settings, product_root):
        """DELIBERATE. The intent governs RELEASE and BILLING, never the pipeline:
        making it skip the alignment would be the second exclusion concept this
        design exists to avoid, and it would also destroy the operator's ability to
        change their mind (an unaligned site cannot be brought back without a
        re-run). The physics is cheap; the decision is reversible."""
        client = deliverable_client(settings, product_root)
        drop(client)
        summary = client.get("/api/case-sessions/neodent-gm/run").json()
        assert sorted(s["tooth"] for s in summary["sites"]) == [4, 13]
        assert PACKAGE_FILES  # the package is untouched too
