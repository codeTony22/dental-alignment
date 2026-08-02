"""THE INVOICE, DERIVED (design flow.dc.html payLines/payTotal 1475-1480; gap
``per-site-pricing-model``, 2026-07-31).

The sharpest doctrine point on the whole Deliver surface: a client that could POST an
amount could pay $0 for a released case — a status-shaped claim wearing a currency
symbol. So the amount is a SERVER derivation off the run's own assurance, ``PaymentIn``
still carries nothing but ``authorize``, and the priced amount is recorded ON the
payment record so a receipt is re-derivable afterwards.

The RATES are the client's confirmed card (in-chat 2026-08-02, §10-AB.1) — "final" on
the wire. These tests pin the DERIVATION and the doctrine, and deliberately read the
numbers from the module's own rate card rather than hard-coding dollars a later client
conversation would replace.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.pricing import (CURRENCY, EXCEPTION_NUMERATOR, EXCEPTION_DENOMINATOR,
                         RATE_CARD_STATUS, RATE_CARD_VERSION, unit_amount_cents)
from bff.session import (SeatedSelection, SessionConflict, SessionStore,
                         SiteSession, SiteStatus)

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


CHOICES = {"construction_path": "dess/neodent-gm-scanbody.stl", "jaw": "upper",
           "gingival_offset_mm": 0.2}


def put_choices(client, **overrides):
    return client.put("/api/case-sessions/neodent-gm/choices",
                      json={**CHOICES, **overrides})


def materialize_run(client, product_root, files=PACKAGE_FILES) -> str:
    """Lay down the CURRENT run's package bytes — QC images (the evidence the
    confirmation hashes) and deliverables alike. ``deliverable_client`` does this for
    the first run; a SECOND run lands in a fresh directory that nobody has filled."""
    run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
    run_dir = product_root / "neodent-gm" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        run_dir.joinpath(name).write_bytes(
            (b"\x89PNG:" if name.endswith(".png") else b"STL:") + name.encode())
    return run_id


def rerun_across_a_boundary(client, product_root, offset: float = 0.25) -> str:
    """Take the case through a REAL reset boundary onto a SECOND done run, exactly as
    an operator would: a choices change clears the run pointer (and deliberately
    leaves any standing confirmation), the sites are re-previewed and re-reviewed,
    and a fresh run is authorized. Returns the new run id.

    The re-review is written through the store because there is no client path to a
    READY rung by design (``seed_ready``'s own rule) — the seat record mirrors what
    the preview route persists, so the authorized gate accepts it."""
    assert put_choices(client, gingival_offset_mm=offset).status_code == 200
    store = SessionStore(product_root)
    session = store.load("neodent-gm")
    assert session.run is None, "the boundary must have cleared the run pointer"
    for tooth in ("4", "13"):
        session.sites[tooth] = SiteSession(
            status=SiteStatus.READY, declared_variant="5020",
            seat_method="rim-seat", rim_agreement_mm=0.07,
            seated_selection=SeatedSelection(
                model="neodent-gm",
                construction_path="dess/neodent-gm-scanbody.stl",
                variant="5020", jaw="upper", gingival_offset_mm=offset))
    store.save(session)
    assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
    return materialize_run(client, product_root)


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

    def test_the_rates_are_the_clients_confirmed_card(
            self, settings, product_root):
        # CONFIRMED (client in-chat, 2026-08-02, §10-AB.1): "$32/site standard, $48
        # rush, exceptions at half" — the placeholder figures ratified as the price
        # list. The wire says "final"; the note records WHO confirmed and WHEN, and
        # the not-a-quotation hedge is gone with the placeholder status.
        body = invoice_of(landed_client(settings, product_root, [row(4)]))
        assert body["status"] == RATE_CARD_STATUS == "final"
        assert body["rate_card_version"] == RATE_CARD_VERSION == "client-2026-08-02-v1"
        assert "PLACEHOLDER" not in body["note"]
        assert "2026-08-02" in body["note"]


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


class TestTheChargeStandsOnWhatWasSigned:
    """THE THREE MONEY HOLES the 2026-07-31 audit walked, pinned as the failures they
    actually were. Every one of them let the amount charged and the document the
    operator signed describe different cases, and every one of them was reachable
    through the public API with no race and no forged body.
    """

    def test_paying_over_a_run_the_confirmation_never_named_refuses(
            self, settings, product_root):
        """AUDIT FINDING 1. ``_require_done_run_for_act(..., "pay for")`` asks only
        that SOME run be done — never that the standing confirmation names THAT run.
        One reset boundary and one re-run later, a confirmation sealed over run A sat
        beside a done run B, and ``_billing_dispositions`` failed OPEN on the
        mismatch: every withhold the operator signed was dropped and every site
        priced as released, on evidence nobody had confirmed.

        Measured before the fix: 200, and ``amount_cents`` twice the confirmed
        invoice — for a case whose release could then never succeed, because the
        evidence sha re-derives over run B and can never equal run A's."""
        from test_deliver import confirm, confirm_body, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body({"4": "release",
                                             "13": "withhold"})).status_code == 200
        signed_total = invoice_of(client)["total_cents"]
        assert signed_total == unit_amount_cents("standard")   # one site released
        run_a = SessionStore(product_root).load("neodent-gm").confirmation.run_id

        run_b = rerun_across_a_boundary(client, product_root)
        assert run_b != run_a
        session = SessionStore(product_root).load("neodent-gm")
        assert session.confirmation.run_id == run_a, "the confirmation still stands"

        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True})
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert run_a in detail and run_b in detail
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_an_invoice_read_against_a_foreign_confirmation_refuses_not_defaults(
            self, settings, product_root):
        """The same finding's read half. "No confirmation at all" legitimately
        defaults to release (confirm's own omission rule). "A confirmation naming
        ANOTHER run" is not that state — it is a case whose signature no longer
        applies — and quietly re-pricing it at the full released rate is the
        over-claiming direction. The invoice says so instead."""
        from test_deliver import confirm, confirm_body, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body({"4": "release",
                                             "13": "withhold"})).status_code == 200
        rerun_across_a_boundary(client, product_root)
        res = client.get("/api/case-sessions/neodent-gm/invoice")
        assert res.status_code == 409
        assert "re-confirm" in res.json()["detail"]

    def test_releasing_more_than_was_paid_for_refuses_with_the_shortfall(
            self, settings, product_root):
        """AUDIT FINDING 2. Dispositions sit OUTSIDE the evidence hash by design, so
        re-confirming four withholds into releases moves no sha at all — the release
        gate's byte comparison passes unchanged, and it gated on the payment BOOLEAN.
        Measured before the fix: a 200 release disclosing every site, against a
        receipt for one."""
        from test_deliver import confirm, confirm_body, deliverable_client, pay, release
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body({"4": "release",
                                             "13": "withhold"})).status_code == 200
        assert pay(client).status_code == 200
        paid = SessionStore(product_root).load("neodent-gm").payment.amount_cents
        assert paid == unit_amount_cents("standard")

        # the same evidence, a wider release — a supported act, and one that moves no
        # hash (test_evidence pins that dispositions never enter the bytes)
        before = SessionStore(product_root).load("neodent-gm").confirmation
        assert confirm(client, confirm_body({"4": "release",
                                             "13": "release"})).status_code == 200
        after = SessionStore(product_root).load("neodent-gm").confirmation
        assert after.evidence_sha256 == before.evidence_sha256, "no drift to catch"

        res = release(client)
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert str(paid) in detail and str(invoice_of(client)["total_cents"]) in detail
        assert SessionStore(product_root).load("neodent-gm").release is None

    def test_releasing_a_rush_case_paid_at_the_standard_rate_refuses(
            self, settings, product_root):
        """The same hole through the turnaround door: ``turnaround`` is client-settable
        and fires no reset boundary (deliberately — it touches no geometry), so pay
        standard, upgrade to rush, release used to ship rush work at the standard
        rate with nothing comparing the two numbers."""
        from test_deliver import confirm, deliverable_client, pay, release
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert put_choices(client, turnaround="rush").status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.run is not None, "a turnaround change fires no boundary"
        assert session.confirmation is not None

        res = release(client)
        assert res.status_code == 409
        assert "re-authorize" in res.json()["detail"]

    def test_a_release_at_exactly_the_priced_amount_still_passes(
            self, settings, product_root):
        """The re-pricing gate must not become a wall in front of the ordinary
        walk: paid == priced releases, as it always did."""
        from test_deliver import confirm, deliverable_client, pay, release
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert release(client).status_code == 200

    def test_a_second_authorization_refuses_instead_of_overwriting_the_receipt(
            self, settings, product_root):
        """AUDIT FINDING 3. Nothing checked ``session.payment is None``, so a second
        POST re-priced off the CURRENT document and replaced the record. With
        turnaround settable and boundary-free, that let the recorded charge be
        lowered after the work was billed high — destroying the only record of what
        was charged. Measured before the fix: the rush receipt became a standard one
        and the rush charge existed nowhere."""
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert put_choices(client, turnaround="rush").status_code == 200
        assert pay(client).status_code == 200
        charged = SessionStore(product_root).load("neodent-gm").payment
        assert charged.amount_cents == 2 * unit_amount_cents("rush")

        assert put_choices(client, turnaround="standard").status_code == 200
        res = pay(client)
        assert res.status_code == 409
        assert "already paid" in res.json()["detail"]
        assert "/delivery/reset" in res.json()["detail"]
        again = SessionStore(product_root).load("neodent-gm").payment
        assert again.amount_cents == charged.amount_cents
        assert again.turnaround == "rush" and again.at == charged.at

    def test_the_door_back_still_reopens_a_second_authorization(
            self, settings, product_root):
        """The refusal above must not wedge the demo: ``POST /delivery/reset``
        withdraws all three records together and the flow is walkable again."""
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert client.post(
            "/api/case-sessions/neodent-gm/delivery/reset").status_code == 200
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200

    def test_a_lost_race_refuses_rather_than_silently_re_pricing(
            self, settings, product_root, monkeypatch):
        """AUDIT FINDING 7's minimum, and finding 3's other half. Payment rode
        ``_mutate_session``, which RE-LOADS and RE-APPLIES after a lost CAS — so a
        turnaround PUT landing in that window re-derived the price upward and
        returned 200, charging a number the authorizing act never saw.

        A signature-shaped record does not get a retry: the act refuses and the
        operator re-reads. Simulated here by losing the first save, which is exactly
        what a rival write does."""
        from test_deliver import confirm, deliverable_client, pay
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200

        real_save = SessionStore.save
        saves = {"n": 0}

        def flaky(self, session):
            saves["n"] += 1
            if saves["n"] == 1:
                raise SessionConflict(session.case_id, session.version,
                                      session.version + 1)
            return real_save(self, session)

        monkeypatch.setattr(SessionStore, "save", flaky)
        res = pay(client)
        assert res.status_code == 409
        monkeypatch.undo()
        assert SessionStore(product_root).load("neodent-gm").payment is None


# --- the price you READ is the price you are CHARGED (audit 2026-07-31) ----------------

class TestTheAuthorizationNamesTheInvoiceItRead:
    """Nothing bound the two together. ``turnaround`` is client-settable and fires no
    reset boundary (deliver.py says so explicitly), so a PUT from a second tab or a
    second operator after the checkout rendered moved the server price from standard
    to rush while the sticky bar still read the standard figure — and the click
    charged the rush figure and returned 200. ``_mutate_signing`` cannot see it: that
    write landed BEFORE the POST, so no CAS was lost.

    The precondition is a VERSION, never an amount (doctrine rightly forbids an
    amount on the wire): the opaque digest the invoice itself served."""

    def test_the_invoice_carries_a_fingerprint_and_no_amount_rides_the_wire(
            self, settings, product_root):
        from bff.resources.deliver import PaymentIn
        client = landed_client(settings, product_root, [row(4)],
                               files=PACKAGE_FILES)
        assert len(invoice_of(client)["fingerprint"]) == 64
        # the precondition is a DIGEST: nothing on this body can express an amount
        assert set(PaymentIn.model_fields) == {"authorize", "invoice_fingerprint"}

    def test_the_fingerprint_moves_when_the_price_moves(self, settings,
                                                        product_root):
        from test_deliver import deliverable_client
        client = deliverable_client(settings, product_root)
        before = invoice_of(client)
        assert client.put("/api/case-sessions/neodent-gm/choices",
                          json={"turnaround": "rush"}).status_code == 200
        after = invoice_of(client)
        assert after["total_cents"] != before["total_cents"]
        assert after["fingerprint"] != before["fingerprint"]

    def test_a_turnaround_change_after_the_dialog_rendered_refuses_the_charge(
            self, settings, product_root):
        """THE WALKED FAILURE. Read the invoice, have a rival PUT rush, click Pay
        with the figure that was on screen: the charge must refuse rather than
        silently bill the higher rate."""
        from test_deliver import confirm, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        displayed = invoice_of(client)["fingerprint"]
        assert client.put("/api/case-sessions/neodent-gm/choices",
                          json={"turnaround": "rush"}).status_code == 200
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True,
                                "invoice_fingerprint": displayed})
        assert res.status_code == 409
        assert "the price moved since you read it" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_the_matching_fingerprint_authorizes_at_that_figure(
            self, settings, product_root):
        from test_deliver import confirm, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        displayed = invoice_of(client)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True,
                                "invoice_fingerprint": displayed["fingerprint"]})
        assert res.status_code == 200
        record = SessionStore(product_root).load("neodent-gm").payment
        assert record.amount_cents == displayed["total_cents"]

    def test_the_fingerprint_is_checked_last_so_better_refusals_keep_their_words(
            self, settings, product_root):
        """A case that is unpayable for a stronger reason must still refuse in that
        reason's own words — an operator told "the price moved" about a case with no
        confirmation at all has been sent to fix the wrong thing."""
        from test_deliver import deliverable_client
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True,
                                "invoice_fingerprint": "0" * 64})
        assert res.status_code == 409
        assert "requires a confirmation" in res.json()["detail"]

    def test_the_receipt_is_not_part_of_the_document_being_fingerprinted(
            self, settings, product_root):
        """``paid`` is a RECEIPT, not a price. Folding it in would make every
        invoice its own fingerprint the moment payment landed, which says nothing
        about whether the case was repriced."""
        from test_deliver import confirm, deliverable_client
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        before = invoice_of(client)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True,
                                "invoice_fingerprint": before["fingerprint"]})
        assert res.status_code == 200
        after = invoice_of(client)
        assert after["paid"] is not None
        assert after["fingerprint"] == before["fingerprint"]
