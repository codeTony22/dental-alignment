"""THE INVOICE, DERIVED (design flow.dc.html payLines/payTotal 1475-1480; gap
``per-site-pricing-model``, 2026-07-31).

The sharpest doctrine point on the whole Deliver surface: a client that could POST an
amount could pay $0 for a released case — a status-shaped claim wearing a currency
symbol. So the amount is a SERVER derivation off the run's own assurance, ``PaymentIn``
still carries nothing but ``authorize``, and the priced amount is recorded ON the
payment record so a receipt is re-derivable afterwards.

The RATES are placeholders (the client has supplied none), marked as such on the wire
exactly like ``TERMS_TEXT_PLACEHOLDER`` — these tests pin the DERIVATION and the
doctrine, and deliberately read the numbers from the module's own rate card rather than
hard-coding dollars a later client conversation will replace.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.pricing import (CURRENCY, EXCEPTION_NUMERATOR, EXCEPTION_DENOMINATOR,
                         RATE_CARD_STATUS, RATE_CARD_VERSION, unit_amount_cents)
from bff.session import SessionStore

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client
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


def invoice_of(client):
    res = client.get("/api/case-sessions/neodent-gm/invoice")
    assert res.status_code == 200, res.text
    return res.json()


def lines_by_key(body) -> dict:
    return {line["key"]: line for line in body["lines"]}


def exception_cents(turnaround: str) -> int:
    return (unit_amount_cents(turnaround) * EXCEPTION_NUMERATOR
            // EXCEPTION_DENOMINATOR)


class TestTheInvoiceIsAProjection:
    """It reads the run's assurance and the case's turnaround choice, and nothing
    else. No physics, no new verdicts — the same posture as the assurance table it
    prices."""

    def test_no_current_run_is_a_404_with_words(self, settings):
        from test_run_resource import FakeWorker, client_with
        client = client_with(settings, FakeWorker())
        res = client.get("/api/case-sessions/neodent-gm/invoice")
        assert res.status_code == 404
        assert "no completed current run" in res.json()["detail"]

    def test_an_unknown_case_is_a_404(self, settings):
        from test_run_resource import FakeWorker, client_with
        client = client_with(settings, FakeWorker())
        assert client.get("/api/case-sessions/nope/invoice").status_code == 404

    def test_reading_the_invoice_writes_nothing(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        before = SessionStore(product_root).load("neodent-gm").version
        invoice_of(client)
        assert SessionStore(product_root).load("neodent-gm").version == before

    def test_two_clean_sites_bill_at_the_standard_unit(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = invoice_of(client)
        unit = unit_amount_cents("standard")
        released = lines_by_key(body)["released_sites"]
        assert released["quantity"] == 2
        assert released["unit_amount_cents"] == unit
        assert released["amount_cents"] == 2 * unit
        assert released["billed"] is True
        assert body["total_cents"] == 2 * unit
        assert body["currency"] == CURRENCY

    def test_a_flagged_site_is_an_exception_at_half_the_unit(
            self, settings, product_root):
        # an exception is a site the operator had to ACKNOWLEDGE row by row
        # (_needs_acknowledgment) — the same predicate the confirm gate stands on,
        # so what the invoice charges half for and what the operator had to face
        # can never be two different sets
        client = landed_client(settings, product_root,
                               [row(4), row(13, level="attention")])
        lines = lines_by_key(invoice_of(client))
        assert lines["released_sites"]["quantity"] == 1
        assert lines["exception_sites"]["quantity"] == 1
        assert lines["exception_sites"]["unit_amount_cents"] == exception_cents(
            "standard")
        assert (invoice_of(client)["total_cents"]
                == unit_amount_cents("standard") + exception_cents("standard"))

    def test_a_line_with_nothing_in_it_is_not_rendered_as_zero(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        keys = set(lines_by_key(invoice_of(client)))
        # no exceptions and nothing withheld on this case — the invoice says so by
        # not carrying the lines, rather than by carrying "0 exceptions"
        assert "exception_sites" not in keys
        assert "withheld_sites" not in keys
        assert "turnaround" in keys   # always stated: it is what the rate keys on

    def test_the_rates_are_marked_placeholder_not_shipped_as_fact(
            self, settings, product_root):
        # the client has supplied no price list; inventing one and calling it a
        # price would be the TERMS_TEXT_PLACEHOLDER mistake with a currency symbol
        body = invoice_of(landed_client(settings, product_root, [row(4)]))
        assert body["status"] == RATE_CARD_STATUS == "placeholder"
        assert body["rate_card_version"] == RATE_CARD_VERSION
        assert "PLACEHOLDER" in body["note"]


class TestTurnaroundPricesTheCase:
    def test_the_standing_default_is_standard_and_the_source_says_so(
            self, settings, product_root):
        body = invoice_of(landed_client(settings, product_root, [row(4)]))
        assert body["turnaround"] == "standard"
        assert body["turnaround_source"] == "default"

    def test_choosing_rush_reprices_every_line(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.2,
            "turnaround": "rush"}).status_code == 200
        body = invoice_of(client)
        assert body["turnaround"] == "rush"
        assert body["turnaround_source"] == "chosen"
        assert body["total_cents"] == 2 * unit_amount_cents("rush")
        assert unit_amount_cents("rush") > unit_amount_cents("standard")


class TestWithheldSitesAreNotBilled:
    def test_a_withheld_site_leaves_the_billed_lines_and_says_it_is_not_billed(
            self, settings, product_root):
        from test_deliver import confirm, confirm_body, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body({"4": "release",
                                             "13": "withhold"})).status_code == 200
        lines = lines_by_key(invoice_of(client))
        assert lines["released_sites"]["quantity"] == 1
        assert lines["withheld_sites"]["quantity"] == 1
        assert lines["withheld_sites"]["amount_cents"] == 0
        assert lines["withheld_sites"]["billed"] is False
        assert invoice_of(client)["total_cents"] == unit_amount_cents("standard")

    def test_before_any_confirmation_every_site_defaults_to_released(
            self, settings, product_root):
        # confirm's own "omission means release" rule (client 2026-07-27 #4),
        # resolved ONCE — the invoice must not invent a second answer
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert lines_by_key(invoice_of(client))["released_sites"]["quantity"] == 2


class TestTheAmountIsNeverAClientClaim:
    """AM-4 at the money edge. ``PaymentIn`` carries one boolean; the server prices
    at authorization time and RECORDS what it charged."""

    def test_the_payment_body_cannot_carry_an_amount(self, settings, product_root):
        from test_deliver import confirm, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True, "amount_cents": 0})
        assert res.status_code == 422

    def test_authorizing_records_the_priced_amount_on_the_record(
            self, settings, product_root):
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        expected = invoice_of(client)["total_cents"]
        assert pay(client).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").payment
        assert record is not None
        assert record.amount_cents == expected
        assert record.currency == CURRENCY
        assert record.rate_card_version == RATE_CARD_VERSION
        assert record.turnaround == "standard"

    def test_the_invoice_reports_what_was_actually_charged_afterwards(
            self, settings, product_root):
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        body = invoice_of(client)
        assert body["paid"] is not None
        assert body["paid"]["amount_cents"] == body["total_cents"]
        assert body["paid"]["turnaround"] == "standard"

    def test_the_receipt_survives_a_later_turnaround_change(
            self, settings, product_root):
        """A turnaround change AFTER payment reprices the case going forward; the
        RECORD keeps what was charged. Two answers on purpose — the current price
        and the receipt — because collapsing them would either forge a receipt or
        deny the new choice."""
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        charged = SessionStore(product_root).load("neodent-gm").payment.amount_cents
        assert client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.2,
            "turnaround": "rush"}).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").payment
        assert record.amount_cents == charged
        assert record.turnaround == "standard"

    def test_paying_after_a_reset_boundary_refuses_in_the_act_s_own_voice(
            self, settings, product_root):
        """THE GATE THIS CHANGE ADDED, PINNED (2026-07-31). Pricing needs a done
        current run, and so does the ACT. The path is reachable and was not
        covered: ``clear_current_run`` fires at three boundaries in
        ``case_sessions`` (a choices change, a system switch, a re-declaration)
        and none of them clears the CONFIRMATION — so a confirmed case can lose
        the physics its confirmation was sealed over and still look payable.

        It must refuse as a 409 in this module's own sentence, not leak the read
        helper's 404 out of a POST: the case exists, the act does not apply to it.
        Under-claiming is the safe direction — release already required a done run
        (``_require_done_run_for_act(..., "release")``), so without this gate the
        operator could be charged for a case that could never be released."""
        from test_deliver import confirm, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        # a choices change is a reset boundary: it clears the run pointer and
        # leaves the confirmation standing
        assert client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.25}).status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.run is None, "the boundary must have cleared the run"
        assert session.confirmation is not None, "and left the confirmation"

        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True})
        assert res.status_code == 409
        assert "pay for" in res.json()["detail"]
        # and nothing was charged
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_the_session_view_carries_the_charged_amount(
            self, settings, product_root):
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        payment = client.get(
            "/api/case-sessions/neodent-gm").json()["session"]["payment"]
        assert payment["amount_cents"] > 0
        assert payment["currency"] == CURRENCY
        assert payment["rate_card_version"] == RATE_CARD_VERSION


class TestPricingIsPureArithmeticInCents:
    """No floats anywhere near money: the half-rate exception is integer division of
    a cents unit, so a rate card whose unit is odd can never mint a half-cent."""

    @pytest.mark.parametrize("turnaround", ["standard", "rush"])
    def test_every_rate_card_unit_halves_exactly(self, turnaround):
        unit = unit_amount_cents(turnaround)
        assert isinstance(unit, int)
        assert unit * EXCEPTION_NUMERATOR % EXCEPTION_DENOMINATOR == 0

    def test_an_unknown_turnaround_word_refuses_rather_than_guessing(self):
        with pytest.raises(KeyError):
            unit_amount_cents("overnight")
