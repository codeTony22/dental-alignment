"""THE DISCLOSURE GATES (plan §4 Deliver, §6; grill AM-1/AM-10/AM-12): the
confirmation over sealed evidence, the payment stub, release-as-disclosure, and the
gated artifact endpoints — slice 8-ii.

The chain under test, end to end:

  POST /confirm (dispositions + per-flag acknowledgments; seals the evidence bundle
  TRANSACTIONALLY) → POST /payment (the honest stub) → POST /release (re-derives the
  evidence and refuses on ANY drift) → GET /runs/current/artifacts[/{filename}] (the
  deliverable class, disclosed at last; withheld sites excluded).

Confirm → change → release must 409 — pinned here both ways the case can change:
a reset boundary clearing the run pointer, and an evidence drift the pointer
survives (a withdrawn review tick, a mutated QC byte).

NO OPERATOR HEADER ANYWHERE (client 2026-07-27: "WE dont need operator name the
checkmark is sufficient"). AM-11's X-Operator requirement is GONE — deliberately,
not by oversight — and TestIdentityIsNoLongerClaimed below is where that decision
is pinned so nobody restores the 422 as a "regression fix".
"""
from __future__ import annotations

import json

import pytest

from bff.config import Settings
from bff.resources.deliver import TERMS_VERSION
from bff.session import SessionStore

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client, with_note
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def deliverable_client(settings, product_root, rows=None, files=PACKAGE_FILES):
    """A landed client whose run directory also holds the DELIVERABLE files, so the
    artifact endpoints have real bytes to (refuse to) serve."""
    rows = rows if rows is not None else [row(4), row(13)]
    client = landed_client(settings, product_root, rows, files=files)
    run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
    run_dir = product_root / "neodent-gm" / "runs" / run_id
    for name in files:
        if not name.endswith(".png"):
            (run_dir / name).write_bytes(b"STL:" + name.encode())
    return client


def confirm_body(dispositions=None, acknowledged=(), terms_accepted=True):
    return {"dispositions": dispositions if dispositions is not None
            else {"4": "release", "13": "release"},
            "acknowledged_flags": list(acknowledged),
            "terms_accepted": terms_accepted}


def confirm(client, body=None):
    return client.post("/api/case-sessions/neodent-gm/confirm",
                       json=body if body is not None else confirm_body())


def pay(client):
    return client.post("/api/case-sessions/neodent-gm/payment",
                       json={"authorize": True})


def release(client):
    return client.post("/api/case-sessions/neodent-gm/release")


def confirmed_paid_client(settings, product_root, dispositions=None,
                          acknowledged=()):
    client = deliverable_client(settings, product_root)
    assert confirm(client, confirm_body(dispositions, acknowledged)).status_code == 200
    assert pay(client).status_code == 200
    return client


# --- identity, DELIBERATELY REMOVED (client 2026-07-27) --------------------------------

class TestIdentityIsNoLongerClaimed:
    """THE DELETED REQUIREMENT, pinned so it is never "restored" as a regression fix.

    Client, verbatim: "WE dont need operator name the checkmark is sufficient."

    The reasoning, because a reader deserves it: a self-typed name behind no
    authentication was never identity — it was a text field. Recording it made the
    records LOOK rigorous while proving nothing (anyone could type anyone), and a
    record that looks like proof and is not is worse than one that claims less.
    What the records now stand on is the ATTESTATION ACT itself — a run authorized
    only by per-site review ticks, a confirmation sealed over re-derivable evidence.
    Real identity arrives with real auth (plan §8 / phase-2), where a name will
    mean something. A deliberate reduction, not an oversight.

    Every test below used to assert a 422. They assert the act instead."""

    def test_confirming_with_no_header_at_all_seals_the_record(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record is not None
        assert record.at   # the timestamp stays: WHEN is a fact the act produced

    @pytest.mark.parametrize("method,path", [
        ("POST", "/api/case-sessions/neodent-gm/payment"),
        ("POST", "/api/case-sessions/neodent-gm/release"),
        ("GET", "/api/case-sessions/neodent-gm/runs/current/artifacts"),
        ("GET", "/api/case-sessions/neodent-gm/runs/current/artifacts/"
                "neodent-gm-4-healingcap-aligned.stl"),
    ])
    def test_no_gating_endpoint_asks_who_you_are(
            self, settings, product_root, method, path):
        """Whatever these refuse, it is never "who is acting?" — the 422 that used
        to greet an unnamed caller is gone from every one of them."""
        client = deliverable_client(settings, product_root)
        res = client.request(
            method, path, json={"authorize": True} if "payment" in path else None)
        assert res.status_code != 422
        assert "names its actor" not in res.text

    def test_a_sent_header_is_simply_ignored_never_recorded(
            self, settings, product_root):
        # a stale client (or a curl someone kept) may still send X-Operator: the
        # server neither refuses it nor keeps it — an unauthenticated name is not a
        # fact worth persisting, and a nullable column that never fills would be a
        # lie about intent
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert client.post("/api/case-sessions/neodent-gm/payment",
                           json={"authorize": True},
                           headers={"X-Operator": "Ana Petrova"}).status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert "Ana Petrova" not in session.model_dump_json()

    @pytest.mark.parametrize("record", ["ConfirmationRecord", "PaymentRecord",
                                        "ReleaseRecord"])
    def test_the_three_records_carry_no_operator_field_at_all(self, record):
        """STRUCTURAL: the field is GONE, not nullable. A column that can only ever
        hold None documents an intention nobody has."""
        import bff.session as session_module
        model = getattr(session_module, record)
        assert "operator" not in model.model_fields
        assert "at" in model.model_fields   # the timestamp is what survives


# --- the confirmation (AM-10, AM-12) ---------------------------------------------------

class TestConfirmRefusals:
    def test_without_a_done_current_run_there_is_nothing_to_confirm(
            self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker())
        res = confirm(client)
        assert res.status_code == 409
        assert "no completed current run" in res.json()["detail"]

    def test_an_omitted_disposition_means_RELEASE_never_a_refusal(
            self, settings, product_root):
        """Client 2026-07-27: "What is disposition release vs withhold" — on a
        single-site case (7 of the 9 real ones) the question was friction with one
        sane answer. A case that reached Deliver is a case being delivered; the
        default is release and only a WITHHOLD must be said. The record still
        carries a complete map — the default is resolved once, server-side."""
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body({"4": "release"})).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.dispositions == {"4": "release", "13": "release"}

    def test_an_empty_body_confirms_a_clean_case_entirely(
            self, settings, product_root):
        # "empty" here means no dispositions/acknowledgments — terms_accepted is
        # the one field that is never optional (plan §10-A: the agreement moved
        # here, and it is given, not assumed)
        client = deliverable_client(settings, product_root)
        assert client.post("/api/case-sessions/neodent-gm/confirm",
                           json={"terms_accepted": True}).status_code == 200
        assert SessionStore(product_root).load(
            "neodent-gm").confirmation.dispositions == {"4": "release",
                                                        "13": "release"}

    def test_a_disposition_for_a_tooth_the_run_does_not_carry_is_refused(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body(
            {"4": "release", "13": "release", "30": "release"}))
        assert res.status_code == 422
        assert "tooth 30" in res.json()["detail"]

    def test_a_disposition_value_outside_the_two_acts_is_refused(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "ship-it", "13": "release"}))
        assert res.status_code == 422

    def test_a_smuggled_extra_field_is_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/confirm",
                          json={**confirm_body(), "status": "confirmed"})
        assert res.status_code == 422


# --- the agreement moves here from Declare (plan §10-A) --------------------------------

class TestConfirmRequiresAcceptingTheTerms:
    """Client, verbatim: "Delivery should be confirm and accept alginment and term
    and conditions, payment, and released artifacts." Plan §10-A: the agreement
    moves OFF Declare's per-site ticks onto this ONE commercial signature —
    "confirm and accept terms" is one act, mirroring ``PaymentIn.authorize``'s
    fail-closed shape rather than a second endpoint."""

    def test_omitting_terms_accepted_entirely_is_refused(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/confirm",
                          json={"dispositions": {"4": "release", "13": "release"}})
        assert res.status_code == 422
        assert SessionStore(product_root).load("neodent-gm").confirmation is None

    def test_terms_accepted_false_is_refused_in_words(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body(terms_accepted=False))
        assert res.status_code == 422
        assert "terms" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").confirmation is None

    def test_a_refused_terms_act_costs_no_session_load(
            self, settings, product_root):
        # the check sits OUTSIDE the CAS mutation (mirrors authorize_payment): a
        # request that will refuse regardless of session state must not pay for
        # a load it never needed
        seed_ready(product_root)
        client = client_with(settings, FakeWorker())   # no done run at all
        res = confirm(client, confirm_body(terms_accepted=False))
        assert res.status_code == 422
        assert "terms" in res.json()["detail"]
        # NOT "no completed current run" — the terms refusal fires first, before
        # the run precondition is ever consulted
        assert "no completed current run" not in res.json()["detail"]

    def test_accepting_the_terms_records_the_version_with_the_seal(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client)
        assert res.status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.terms_accepted is True
        assert record.terms_version   # a non-empty version tag, whatever it is
        view = res.json()["session"]["confirmation"]
        assert view["terms_accepted"] is True
        assert view["terms_version"] == record.terms_version

    def test_the_terms_version_rides_in_the_sealed_bundle(
            self, settings, product_root):
        """Plan §10-A: "recorded with its timestamp and the evidence hash it was
        given over" — the acceptance is part of what confirming seals, the same
        way the Delivery-vs-Skip fork is (bff/evidence.py)."""
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        bundle = json.loads(
            (product_root / "neodent-gm" / "runs" / record.run_id / "evidence"
             / f"{record.evidence_sha256}.json").read_bytes())
        assert bundle["terms_version"] == record.terms_version
        assert bundle["terms_version"] is not None


class TestFlagsAcknowledgeRowByRow:
    """AM-12: a flag is confirmed row-by-row, never in bulk — releasing a flagged
    site demands ITS OWN acknowledgment, and the refusal names exactly the teeth
    still unacknowledged."""

    def _flagged_client(self, settings, product_root):
        # both sites flagged: tooth 4 attention, tooth 13 action-needed
        return deliverable_client(settings, product_root,
                                  rows=[row(4, level="attention"),
                                        row(13, level="action-needed")])

    def test_releasing_a_flagged_site_without_its_acknowledgment_is_refused(
            self, settings, product_root):
        client = self._flagged_client(settings, product_root)
        res = confirm(client, confirm_body(acknowledged=[4]))
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13" in detail and "acknowledg" in detail
        assert "tooth 4" not in detail  # 4 IS acknowledged — only 13 is named

    def test_each_flagged_release_acknowledged_confirms(
            self, settings, product_root):
        client = self._flagged_client(settings, product_root)
        assert confirm(client, confirm_body(acknowledged=[4, 13])).status_code == 200

    def test_the_refusal_names_ONLY_acknowledgments_never_a_disposition(
            self, settings, product_root):
        """The 422's words follow the relaxation (client 2026-07-27): a flagged
        site released BY DEFAULT still needs its row acknowledgment, and that is the
        only thing the refusal may ask for — never a disposition the operator was
        not obliged to give."""
        client = self._flagged_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/confirm",
                          json={"terms_accepted": True})
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "acknowledgment" in detail
        assert "tooth 4" in detail and "tooth 13" in detail
        assert "disposition" not in detail

    def test_a_withheld_flagged_site_needs_no_acknowledgment(
            self, settings, product_root):
        # withholding is not releasing: the site drops from the released set and
        # stays open — there is no release to acknowledge
        client = self._flagged_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"},
                                           acknowledged=[4]))
        assert res.status_code == 200

    def test_acknowledging_an_unflagged_site_is_refused(
            self, settings, product_root):
        # tooth 13 is READY here — an acknowledgment of a flag that does not exist
        # is a claim about nothing, refused rather than silently dropped
        client = deliverable_client(settings, product_root,
                                    rows=[row(4, level="attention"), row(13)])
        res = confirm(client, confirm_body(acknowledged=[4, 13]))
        assert res.status_code == 422
        assert "tooth 13" in res.json()["detail"]


class TestAProductionNoteAlsoDemandsAcknowledgment:
    """THE FLAG-VS-ANNOTATE DECISION (plan §10-E), enforced: a multi-variant
    case's shared-construction-part conflict is not merely displayed, it is
    GATED — the same AM-12 row-by-row rule a truly flagged site earns, even
    though the run's own guidance called every one of these sites ready. The
    note's own words are "cannot match", not "differs slightly"; an operator
    must not be able to confirm and pay past that sentence in silence."""

    def _noted_client(self, settings, product_root):
        # both sites READY per the run's guidance — the ONLY thing making them
        # need acknowledgment is the shared-part note
        return deliverable_client(settings, product_root,
                                  rows=[with_note(row(4)), with_note(row(13))])

    def test_a_ready_but_noted_site_cannot_be_released_unacknowledged(
            self, settings, product_root):
        client = self._noted_client(settings, product_root)
        res = confirm(client)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "acknowledgment" in detail
        assert "tooth 4" in detail and "tooth 13" in detail

    def test_acknowledging_both_noted_sites_confirms(
            self, settings, product_root):
        client = self._noted_client(settings, product_root)
        assert confirm(client, confirm_body(acknowledged=[4, 13])).status_code == 200

    def test_withholding_a_noted_site_needs_no_acknowledgment(
            self, settings, product_root):
        # exactly the flagged-site rule: withholding means there is no release
        # to acknowledge
        client = self._noted_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"},
                                           acknowledged=[4]))
        assert res.status_code == 200

    def test_a_clean_case_needs_no_such_acknowledgment(
            self, settings, product_root):
        # the control: no note, no extra demand — this is the existing
        # single-variant behavior, unmoved
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200


class TestConfirmSealsTheEvidence:
    def test_the_record_and_the_bundle_land_together(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        record = session.confirmation
        assert record is not None
        assert record.at   # ISO stamp — the record's own fact, no actor beside it
        assert record.run_id == session.run.run_id
        assert record.dispositions == {"4": "release", "13": "withhold"}
        assert record.acknowledged_flags == []
        # the bundle is ON DISK, content-addressed under the run dir (AM-10)
        bundle_path = (product_root / "neodent-gm" / "runs" / record.run_id /
                       "evidence" / f"{record.evidence_sha256}.json")
        payload = json.loads(bundle_path.read_bytes())
        assert payload["assurance"]["run_id"] == record.run_id
        assert set(payload["qc_sha256"]) == {
            n for n in PACKAGE_FILES if n.endswith(".png")}
        # and the response's session view says so, for the UI's sealed state
        view = res.json()["session"]
        assert view["confirmed"] is True
        assert "operator" not in view["confirmation"]   # the wire dropped it too
        assert view["confirmation"]["at"] == record.at
        assert view["confirmation"]["evidence_sha256"] == record.evidence_sha256

    def test_a_missing_qc_image_refuses_the_whole_confirmation(
            self, settings, product_root):
        """Transactional (AM-10): a bundle that cannot cover its images is never
        sealed — the confirmation refuses and NOTHING persists."""
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
        (product_root / "neodent-gm" / "runs" / run_id /
         "neodent-gm-13-deviation.png").unlink()
        res = confirm(client)
        assert res.status_code == 409
        assert "neodent-gm-13-deviation.png" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").confirmation is None

    def test_re_confirming_replaces_the_record_over_the_same_evidence(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        res = confirm(client, confirm_body({"4": "release", "13": "release"}))
        assert res.status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.dispositions == {"4": "release", "13": "release"}


# --- the payment stub (AM-11) ----------------------------------------------------------

class TestPaymentStub:
    def test_fail_closed_by_default(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        detail = client.get("/api/case-sessions/neodent-gm").json()
        assert detail["session"]["payment_authorized"] is False

    def test_the_stub_records_provider_and_time(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        res = pay(client)
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.payment is not None
        assert session.payment.provider == "stub"   # permanently distinguishable
        assert session.payment.at
        view = res.json()["session"]
        assert view["payment_authorized"] is True
        assert view["payment"]["provider"] == "stub"

    def test_authorize_false_authorizes_nothing(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": False})
        assert res.status_code == 422
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_an_extra_field_is_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True, "amount": 0})
        assert res.status_code == 422


class TestPaymentIsGatedOnTheTerms:
    """Plan §10-A: "Payment (and therefore release) is gated on it [the terms
    acceptance]" — a REAL server-side precondition, not the progression's screen
    order. Payment now requires a standing confirmation whose OWN
    ``terms_accepted`` is true; since confirm itself refuses without
    ``terms_accepted: true`` (TestConfirmRequiresAcceptingTheTerms), any
    confirmation reachable through the API already satisfies this — the gate
    exists to refuse the states no client path can normally reach: no
    confirmation at all, or one sealed before the concept existed."""

    def test_no_confirmation_at_all_refuses_payment(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = pay(client)
        assert res.status_code == 409
        assert "confirm" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_a_confirmation_that_never_accepted_terms_still_refuses_payment(
            self, settings, product_root):
        """The pre-field case (a confirmation sealed before this slice, or one
        forged straight onto the store): ``terms_accepted`` reads False
        honestly, and payment refuses exactly as if there were no confirmation
        at all — under-claiming is the safe direction, same as every other
        pre-field record in this codebase."""
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.confirmation.terms_accepted = False
        store.save(session)
        res = pay(client)
        assert res.status_code == 409
        assert "confirm" in res.json()["detail"]

    def test_a_real_confirmation_unlocks_payment(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200


# --- the checkout return leg — THE SECURITY RULE (plan §10-A) --------------------------

def checkout_return(client, body=None):
    return client.post("/api/case-sessions/neodent-gm/checkout/return",
                       json=body if body is not None else {"reference": "chk_abc123"})


class TestTheCheckoutReturnAssertsNothingAboutPayment:
    """THE RULE, stated in the task and enforced here: the return from checkout
    carries an identifier and means "re-read this case" — NOTHING about whether
    payment happened. Only the BFF's own server-side state (a landed
    ``PaymentRecord``) decides that. This is the forged-success test: a client
    that never called ``POST .../payment`` cannot manufacture payment, or an
    artifact release, by hitting the return leg with any shape of "it worked"
    it can dream up."""

    def test_a_forged_status_field_is_structurally_refused(
            self, settings, product_root):
        # the wire shape has no field a "success" claim could ride in on —
        # extra="forbid" refuses it before the handler ever runs
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        res = checkout_return(client, {"reference": "chk_abc123",
                                       "status": "success"})
        assert res.status_code == 422
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_a_well_formed_return_with_no_prior_payment_call_authorizes_nothing(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        # THE FORGERY: a "return" from checkout, never preceded by the actual
        # stub-authorize call — exactly what a forged/replayed redirect would
        # look like from the server's point of view
        res = checkout_return(client)
        assert res.status_code == 200
        assert res.json()["session"]["payment_authorized"] is False
        assert SessionStore(product_root).load("neodent-gm").payment is None
        # and the consequence holds all the way down the chain: no release,
        # no artifacts — a forged return buys nothing
        assert release(client).status_code == 409
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts"
        ).status_code == 409

    def test_the_return_mutates_nothing_it_is_a_re_read(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        before = SessionStore(product_root).load("neodent-gm").version
        checkout_return(client)
        checkout_return(client, {"reference": "a-different-one-entirely"})
        assert SessionStore(product_root).load("neodent-gm").version == before

    def test_a_real_payment_still_shows_true_after_the_return(
            self, settings, product_root):
        """The return is not ADVERSARIAL to a real payment either — it just
        never CAUSES one. Authorize for real, then return: the return's
        response reflects the truth it re-read, nothing it asserted."""
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        res = checkout_return(client)
        assert res.status_code == 200
        assert res.json()["session"]["payment_authorized"] is True

    def test_an_empty_reference_is_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        res = checkout_return(client, {"reference": ""})
        assert res.status_code == 422

    def test_an_unknown_case_is_a_404(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/nope/checkout/return",
                          json={"reference": "chk_abc123"})
        assert res.status_code == 404


# --- release-as-disclosure (AM-1) ------------------------------------------------------

class TestReleaseGates:
    def test_release_without_a_confirmation_names_the_missing_piece(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        pay(client)
        res = release(client)
        assert res.status_code == 409
        assert "confirm" in res.json()["detail"]

    def test_release_without_payment_names_the_missing_piece(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        confirm(client)
        res = release(client)
        assert res.status_code == 409
        assert "payment" in res.json()["detail"]

    def test_a_valid_chain_releases_and_records_the_act(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root,
                                       {"4": "release", "13": "withhold"})
        res = release(client)
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        record = session.release
        assert record is not None
        assert record.at
        assert record.run_id == session.run.run_id
        assert record.evidence_sha256 == session.confirmation.evidence_sha256
        assert record.released_teeth == [4]   # the withheld site stays open
        view = res.json()["session"]
        assert view["released"] is True
        assert view["release"]["released_teeth"] == [4]


class TestConfirmThenChangeThenRelease:
    """THE PIN the slice demands: confirm → change → release must 409, whichever way
    the case changed. Validity is re-derivation, never trust in the record."""

    def test_a_reset_boundary_clearing_the_run_blocks_release(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        # the operator re-declares a variant: the boundary clears the run pointer
        assert client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "5030"}).status_code == 200
        res = release(client)
        assert res.status_code == 409
        assert "no completed current run" in res.json()["detail"]

    def test_an_evidence_drift_the_pointer_survives_blocks_release(
            self, settings, product_root):
        """A withdrawn review tick moves a site ready→previewed WITHOUT clearing
        the run pointer — the confirmed bundle no longer matches the re-derived
        evidence, and release refuses in the stated words."""
        client = confirmed_paid_client(settings, product_root)
        assert client.delete(
            "/api/case-sessions/neodent-gm/sites/13/review").status_code == 200
        res = release(client)
        assert res.status_code == 409
        assert "changed since it was confirmed" in res.json()["detail"]
        assert "re-confirm" in res.json()["detail"]

    def test_a_mutated_qc_image_blocks_release(self, settings, product_root):
        """The QC images are part of what was signed (AM-10): one changed bit in a
        render re-derives to a different bundle, and release refuses."""
        client = confirmed_paid_client(settings, product_root)
        run_id = SessionStore(product_root).load("neodent-gm").run.run_id
        qc = (product_root / "neodent-gm" / "runs" / run_id /
              "neodent-gm-4-clockview.png")
        qc.write_bytes(qc.read_bytes() + b"\x00")
        res = release(client)
        assert res.status_code == 409
        assert "changed since it was confirmed" in res.json()["detail"]

    def test_changing_the_adjust_decision_blocks_release(
            self, settings, product_root):
        """THE FORK IS EVIDENCE (client 2026-07-27): the decision word is part of
        the sealed bundle, so confirm → decide differently → release travels the
        SAME re-derivation path as a moved number. Whoever confirmed said "these
        fits, skipped"; a later "adjusted" is a different statement about the same
        case, and the seal must stop covering it."""
        client = deliverable_client(settings, product_root)
        assert client.post("/api/case-sessions/neodent-gm/adjust-decision",
                           json={"decision": "skip"}).status_code == 200
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert client.post("/api/case-sessions/neodent-gm/adjust-decision",
                           json={"decision": "adjust"}).status_code == 200
        res = release(client)
        assert res.status_code == 409
        assert "changed since it was confirmed" in res.json()["detail"]

    def test_the_bundle_on_disk_states_what_happened_to_the_adjustments(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        client.post("/api/case-sessions/neodent-gm/adjust-decision",
                    json={"decision": "skip"})
        assert confirm(client).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        bundle = json.loads(
            (product_root / "neodent-gm" / "runs" / record.run_id / "evidence"
             / f"{record.evidence_sha256}.json").read_bytes())
        assert bundle["adjustments"] == "skip"
        # ONCE, and beside the run's facts rather than inside them: the served
        # assurance now carries the word for the READER's sake (a hash shows
        # nobody anything), and the confirm route drops it from the projection it
        # seals so the canonical bytes still state the act exactly once
        assert "adjustments" not in bundle["assurance"]
        # the record says what it sealed, in the open — the display half reads
        # this to notice a fork clicked after the fact
        assert record.adjustments == "skip"

    def test_re_confirming_over_the_current_evidence_unblocks_release(
            self, settings, product_root):
        """WITHDRAWING A REVIEW moves the evidence AND unresolves the site, so the
        whole chain closes: release refuses on the drift, and the confirmation refuses
        until the operator attests the site again (review 2026-07-28, finding F — that
        second refusal used to live only in flow.ts, and a case could be re-confirmed
        and released with a site standing on no verdict at all)."""
        client = confirmed_paid_client(settings, product_root)
        client.delete("/api/case-sessions/neodent-gm/sites/13/review")
        assert release(client).status_code == 409
        refused = confirm(client)
        assert refused.status_code == 422
        assert "tooth 13 is previewed" in refused.json()["detail"]
        # the operator re-reads the evidence as it now stands, re-attests, re-confirms
        assert client.post(
            "/api/case-sessions/neodent-gm/sites/13/review").status_code == 200
        assert confirm(client).status_code == 200
        assert release(client).status_code == 200


# --- the artifact endpoints (the deliverable class) ------------------------------------

class TestArtifactsAreGated:
    @pytest.mark.parametrize("path", [
        "/api/case-sessions/neodent-gm/runs/current/artifacts",
        "/api/case-sessions/neodent-gm/runs/current/artifacts/"
        "neodent-gm-4-healingcap-aligned.stl",
    ])
    def test_no_release_no_disclosure_with_the_missing_pieces_named(
            self, settings, product_root, path):
        client = deliverable_client(settings, product_root)
        res = client.get(path)
        assert res.status_code == 409
        assert "release" in res.json()["detail"]

    def test_a_release_for_a_previous_run_does_not_disclose_the_current_one(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        # the case changes and a NEW run lands: the old release must not carry over
        client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                   json={"variant": "5030"})
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        from bff.session import SeatedSelection, SiteStatus
        s.sites["4"].status = SiteStatus.READY
        # the re-preview + re-review this seeding stands in for records its seat
        # (the 2026-07-28 drift guard would otherwise refuse the new run)
        s.sites["4"].seated_selection = SeatedSelection(
            model="neodent-gm", construction_path="dess/neodent-gm-scanbody.stl",
            variant="5030", jaw="upper", gingival_offset_mm=0.2)
        store.save(s)
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert res.status_code == 409

    def test_evidence_drift_after_release_closes_the_door_again(
            self, settings, product_root):
        """The artifact gate re-derives too: released, then a review withdrawn —
        the evidence no longer hashes to what was sealed, so disclosure stops
        until the operator re-confirms and re-releases over what is actually
        there."""
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        client.delete("/api/case-sessions/neodent-gm/sites/13/review")
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert res.status_code == 409


class TestArtifactsDisclose:
    def _released(self, settings, product_root,
                  dispositions=None) -> "TestClient":
        client = confirmed_paid_client(settings, product_root, dispositions)
        assert release(client).status_code == 200
        return client

    def test_the_list_is_the_deliverables_qc_images_are_evidence_not_artifacts(
            self, settings, product_root):
        client = self._released(settings, product_root)
        body = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert body["run_id"]
        assert [f["name"] for f in body["files"]] == [
            "neodent-gm-4-healingcap-aligned.stl",
            "neodent-gm-13-healingcap-aligned.stl",
            "neodent-gm-upper-overlay.stl",
            "neodent-gm-manifest.json",
            "neodent-gm-upper.stl",
            "view.html"]
        assert body["withheld_teeth"] == []
        # a full release ships the case-wide files: nothing withheld, nothing held
        assert body["withheld_case_files"] == []

    def test_each_listed_file_carries_its_size_and_its_site(
            self, settings, product_root):
        """Client 2026-07-27 #6 ("good UI for ... release of information /
        artifacts"): the surface groups deliverables BY SITE with sizes, so the
        listing must carry both — attributed by the gate's own anchored rule, never
        by the surface re-parsing filenames."""
        client = self._released(settings, product_root)
        files = {f["name"]: f for f in client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").json()["files"]}
        cap = files["neodent-gm-4-healingcap-aligned.stl"]
        assert cap["tooth"] == 4
        assert cap["size_bytes"] == len(b"STL:neodent-gm-4-healingcap-aligned.stl")
        # case-wide files belong to no site and say so
        assert files["neodent-gm-manifest.json"]["tooth"] is None

    def test_a_file_the_package_claims_but_disk_lost_reports_no_size(
            self, settings, product_root):
        # an honest gap beats a zero: the operator sees that something is missing
        client = self._released(settings, product_root)
        run_id = SessionStore(product_root).load("neodent-gm").run.run_id
        (product_root / "neodent-gm" / "runs" / run_id /
         "view.html").unlink()
        files = {f["name"]: f for f in client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").json()["files"]}
        assert files["view.html"]["size_bytes"] is None

    def test_withholding_a_site_withholds_every_case_wide_file_too(
            self, settings, product_root):
        """The overlay merges ALL aligned components (the worker's own note,
        output_package.py) and the manifest carries every site's row and hashes —
        so under a partial release NOTHING case-wide ships: only files attributed
        to a released tooth leave, and the list names what is held and why."""
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        body = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert [f["name"] for f in body["files"]] == [
            "neodent-gm-4-healingcap-aligned.stl"]
        assert body["withheld_teeth"] == [13]
        assert body["withheld_case_files"] == ["neodent-gm-upper-overlay.stl",
                                               "neodent-gm-manifest.json",
                                               "neodent-gm-upper.stl",
                                               "view.html"]

    def test_a_case_wide_file_refuses_its_bytes_while_any_site_is_withheld(
            self, settings, product_root):
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        for name in ("neodent-gm-upper-overlay.stl", "neodent-gm-manifest.json",
                     "view.html"):
            res = client.get("/api/case-sessions/neodent-gm/runs/current/"
                             f"artifacts/{name}")
            assert res.status_code == 403, name
            detail = res.json()["detail"]
            assert "case-wide" in detail
            assert "tooth 13" in detail   # the withheld site is NAMED

    def test_a_full_release_serves_the_case_wide_bytes(
            self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-upper-overlay.stl")
        assert res.status_code == 200
        assert res.content == b"STL:neodent-gm-upper-overlay.stl"

    def test_a_released_file_serves_its_bytes(self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 200
        assert res.content == b"STL:neodent-gm-4-healingcap-aligned.stl"

    def test_a_withheld_sites_file_refuses_with_its_status(
            self, settings, product_root):
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-13-healingcap-aligned.stl")
        assert res.status_code == 403
        assert "withheld" in res.json()["detail"]

    def test_a_qc_image_refuses_here_and_points_at_the_evidence_class(
            self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-4-clockview.png")
        assert res.status_code == 403
        assert "QC image" in res.json()["detail"]

    def test_unknown_and_traversal_shaped_names_are_404(
            self, settings, product_root):
        client = self._released(settings, product_root)
        for name in ("nope.stl", "..%2Fsession.json"):
            res = client.get("/api/case-sessions/neodent-gm/runs/current/"
                             f"artifacts/{name}")
            assert res.status_code == 404, name


# --- file→site attribution is anchored, never a substring scan -------------------------

class TestToothAttribution:
    """The gate's attribution stands on the worker's OWN construction
    (output_package.py: every per-tooth file is ``f"{case_id}-{tooth}-…"``), so it
    anchors on ``{case_id}-{tooth}-`` — at most one tooth can match, whatever order
    the teeth arrive in. An anywhere-substring scan attributed by ascending-tooth
    luck: a case id ending in ``-4`` claimed every other tooth's file."""

    def test_anchoring_beats_the_ascending_order_substring_scan(self):
        from bff.session import tooth_of_file as _tooth_of_file
        name = "smith-4-13-healingcap-aligned.stl"
        assert _tooth_of_file(name, "smith-4", [4, 13]) == 13
        assert _tooth_of_file(name, "smith-4", [13, 4]) == 13   # order-independent

    def test_a_case_id_ending_in_a_tooth_number_claims_no_case_wide_file(self):
        from bff.session import tooth_of_file as _tooth_of_file
        assert _tooth_of_file("smith-4-upper.stl", "smith-4", [4, 13]) is None
        assert _tooth_of_file("smith-4-upper-overlay.stl", "smith-4",
                              [4, 13]) is None
        assert _tooth_of_file("smith-4-manifest.json", "smith-4", [4, 13]) is None

    def test_worker_shaped_names_attribute_exactly(self):
        from bff.session import tooth_of_file as _tooth_of_file
        assert _tooth_of_file("neodent-gm-4-healingcap-aligned.stl",
                              "neodent-gm", [4, 13]) == 4
        assert _tooth_of_file("neodent-gm-13-clockview.png",
                              "neodent-gm", [4, 13]) == 13
        assert _tooth_of_file("neodent-gm-upper.stl",
                              "neodent-gm", [4, 13]) is None


# --- a re-confirm retires the release --------------------------------------------------

class TestAReconfirmRetiresTheRelease:
    """The release record is valid only while it still covers the CURRENT
    confirmation (plan §4: validity is re-derivation, never trust in a record).
    Dispositions are deliberately NOT in the evidence bundle — so a re-confirm
    that changes one moves no hash, and the gate must compare the records
    themselves: the operator's newest signed act wins, disclosure stops until an
    explicit re-release."""

    def test_a_re_confirm_that_withholds_a_site_closes_disclosure(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert res.status_code == 200
        # the display half flips with the record: the rail tick is rail truth
        assert res.json()["session"]["released"] is False
        listing = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert listing.status_code == 409
        assert "confirmation changed after release" in listing.json()["detail"]
        assert "re-release" in listing.json()["detail"]
        fetched = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts/"
            "neodent-gm-13-healingcap-aligned.stl")
        assert fetched.status_code == 409   # the gate closes before per-file logic

    def test_an_explicit_re_release_re_opens_over_the_new_dispositions(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert release(client).status_code == 200
        body = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert body["withheld_teeth"] == [13]
        assert "neodent-gm-13-healingcap-aligned.stl" not in [
            f["name"] for f in body["files"]]

    def test_an_identical_re_confirm_keeps_the_release_current(
            self, settings, product_root):
        # nothing material changed — same run, same evidence, same released set:
        # closing the door here would punish a re-read, not protect anyone
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        res = confirm(client)
        assert res.status_code == 200
        assert res.json()["session"]["released"] is True
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").status_code == 200

    def test_the_worklist_released_chip_unticks_with_the_retired_release(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        release(client)
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["released"] is False


# --- the fork is the OTHER newest-act-wins path ----------------------------------------

class TestAPostReleaseForkClickRetiresTheRelease:
    """Declare stays reachable after release and its fork is one click away, so
    "adjustments were skipped" can be re-answered over a case that has already
    shipped. The gate always closed on it — the word is in the evidence hash, so
    the artifact endpoints re-derive and 409 — but the DISPLAY half compared only
    records and kept saying "Released ✓" beside the error box.

    Two ways to retire a release, and both must LOOK retired: a disposition change
    (records, compared by ``release_matches_confirmation``) and a fork click (the
    evidence, whose cheap re-derivable half is the decision word the confirmation
    now records). The expensive half — the QC bytes — stays where it was, at the
    artifact endpoints; this is the part that costs no disk read."""

    def decided(self, client, decision):
        return client.post("/api/case-sessions/neodent-gm/adjust-decision",
                           json={"decision": decision})

    def released_after_fork(self, settings, product_root, first, second):
        client = deliverable_client(settings, product_root)
        assert self.decided(client, first).status_code == 200
        assert confirm(client).status_code == 200
        assert pay(client).status_code == 200
        assert release(client).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["released"] is True
        res = self.decided(client, second)
        assert res.status_code == 200
        return client, res.json()["session"]

    def test_changing_the_decision_after_release_unticks_released(
            self, settings, product_root):
        client, session = self.released_after_fork(
            settings, product_root, "skip", "adjust")
        assert session["released"] is False
        listing = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert listing.status_code == 409
        # the display half and the gate now agree — no "Released ✓" over an error
        assert "evidence changed after release" in listing.json()["detail"]

    def test_re_stating_the_same_decision_keeps_the_release_current(
            self, settings, product_root):
        # values only (the SeatedSelection precedent): saying "skip" twice
        # describes the same case and must cost nobody their release
        client, session = self.released_after_fork(
            settings, product_root, "skip", "skip")
        assert session["released"] is True
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").status_code == 200

    def test_a_case_that_never_faced_the_fork_stays_released(
            self, settings, product_root):
        # None is an answer, not a missing one: a release sealed with the fork
        # unfaced is not retired by the absence continuing
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["released"] is True

    def test_the_worklist_released_chip_unticks_with_it(
            self, settings, product_root):
        client, _ = self.released_after_fork(
            settings, product_root, "skip", "adjust")
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["released"] is False

    def test_a_confirmation_sealed_before_the_word_was_recorded_reads_as_drift(
            self, settings, product_root):
        """The one-slice window, answered the way bff/evidence.py answers its own
        shape change. A confirmation that never recorded the fork cannot be checked
        against one, so the display half says not-released and the honest path is a
        re-confirm. UNDER-claiming is the safe direction and the gate is untouched —
        the bundle's bytes did not move, so what was disclosed stays disclosable."""
        client, _ = self.released_after_fork(
            settings, product_root, "skip", "skip")
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.confirmation.adjustments = None      # a pre-field record, as loaded
        store.save(session)
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["released"] is False
        # the gate never depended on the record's copy: it re-derives the bundle
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").status_code == 200
        # and one re-confirm restores the display half to the truth
        assert confirm(client).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["released"] is True

    def test_a_re_release_over_the_new_decision_re_opens_disclosure(
            self, settings, product_root):
        # the honest path back: re-confirm over what is there NOW, then re-release
        client, _ = self.released_after_fork(
            settings, product_root, "skip", "adjust")
        assert release(client).status_code == 409
        assert confirm(client).status_code == 200
        assert release(client).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["released"] is True


# --- signing acts are one-winner -------------------------------------------------------

class TestSigningActsAreOneWinner:
    """A CAS loss on a SIGNING act never silently retries: re-applying a
    signature over a rival's write would erase the rival's record while both
    callers hold a 200 — two winners with contradictory receipts. The loser
    gets a 409 that says a rival act landed first AND WHEN; disk holds exactly
    the winner's record.

    WHEN, not WHO, since the identity removal (client 2026-07-27): the rival
    record no longer carries a name to print, and its timestamp is the fact the
    loser can actually check against what they are re-reading."""

    @staticmethod
    def _racing_save(monkeypatch, product_root, rival_write):
        """Arrange a rival write to land between the route's load and its save:
        the first save through the store performs ``rival_write`` first, so the
        route's own save loses the CAS — deterministically, no threads."""
        orig = SessionStore.save
        fired = {"done": False}

        def save(self, session):
            if not fired["done"]:
                fired["done"] = True
                rival_write(SessionStore(product_root), orig)
            return orig(self, session)

        monkeypatch.setattr(SessionStore, "save", save)

    def test_a_rival_confirmation_wins_and_the_loser_is_told_when(
            self, settings, product_root, monkeypatch):
        from bff.session import ConfirmationRecord
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]

        def rival_write(store, orig_save):
            rival = store.load("neodent-gm")
            rival.confirmation = ConfirmationRecord(
                at="2026-07-27T00:00:00+00:00",
                run_id=run_id, evidence_sha256="0" * 64,
                dispositions={"4": "withhold", "13": "withhold"})
            orig_save(store, rival)

        self._racing_save(monkeypatch, product_root, rival_write)
        res = confirm(client)   # the release-everything confirmation
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert "2026-07-27T00:00:00+00:00" in detail and "landed first" in detail
        # ONE winner on disk: the withhold-everything record stands untouched
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.at == "2026-07-27T00:00:00+00:00"
        assert record.dispositions == {"4": "withhold", "13": "withhold"}

    def test_a_rival_release_wins_and_the_loser_is_told_when(
            self, settings, product_root, monkeypatch):
        from bff.session import ReleaseRecord
        client = confirmed_paid_client(settings, product_root)
        session = SessionStore(product_root).load("neodent-gm")
        sha = session.confirmation.evidence_sha256

        def rival_write(store, orig_save):
            rival = store.load("neodent-gm")
            rival.release = ReleaseRecord(
                at="2026-07-27T00:00:00+00:00",
                run_id=session.run.run_id, evidence_sha256=sha,
                released_teeth=[4, 13])
            orig_save(store, rival)

        self._racing_save(monkeypatch, product_root, rival_write)
        res = release(client)
        assert res.status_code == 409
        assert "2026-07-27T00:00:00+00:00" in res.json()["detail"]
        assert SessionStore(product_root).load(
            "neodent-gm").release.at == "2026-07-27T00:00:00+00:00"

    def test_a_non_signing_rival_still_costs_the_act_one_honest_409(
            self, settings, product_root, monkeypatch):
        # ANY interleaved write means the signer did not sign over what is there
        # now — no rival to name, but the act still refuses instead of retrying
        def rival_write(store, orig_save):
            orig_save(store, store.load("neodent-gm"))   # a bare version bump

        client = deliverable_client(settings, product_root)
        self._racing_save(monkeypatch, product_root, rival_write)
        res = confirm(client)
        assert res.status_code == 409
        assert "repeat the act" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").confirmation is None


# --- the read models tell the chain's truth --------------------------------------------

class TestTheViewsCarryTheChain:
    def test_the_worklist_confirmed_chip_is_real_and_released_rides_beside_it(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["confirmed"] is True
        assert row_["released"] is False
        assert release(client).status_code == 200
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["released"] is True

    def test_released_reports_false_after_the_run_pointer_clears(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        release(client)
        client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                   json={"variant": "5030"})
        detail = client.get("/api/case-sessions/neodent-gm").json()
        # the record survives as history, but "released" is a CURRENT-run verdict
        assert detail["session"]["released"] is False


# --- what a release WOULD disclose, said before the act --------------------------------

class TestTheReleasePreview:
    """Client 2026-07-27 #6: the release step must name what will be disclosed
    BEFORE the act. Derived from the standing confirmation through the artifact
    gate's own split (session.split_released_files), so the promise and the
    disclosure are one derivation — and counts only, because names ARE the
    disclosure being described."""

    def test_absent_until_a_confirmation_covers_the_current_run(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["release_preview"] is None

    def test_a_full_release_promises_every_deliverable_and_no_withholding(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        preview = client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["release_preview"]
        assert preview == {"file_count": 6, "teeth": [4, 13],
                           "withheld_teeth": [], "withheld_case_file_count": 0}

    def test_a_withhold_shows_in_the_promise_before_anything_is_disclosed(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client, confirm_body(
            {"4": "release", "13": "withhold"})).status_code == 200
        preview = client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["release_preview"]
        assert preview["teeth"] == [4]
        assert preview["withheld_teeth"] == [13]
        assert preview["file_count"] == 1
        # the case-wide files ride back with the withheld site — counted, so the
        # step can say so without naming them
        assert preview["withheld_case_file_count"] == 4

    def test_the_promise_matches_what_the_gate_actually_discloses(
            self, settings, product_root):
        # ONE derivation, asserted as one: whatever the preview promised is exactly
        # what the artifact list hands over
        client = confirmed_paid_client(settings, product_root,
                                       {"4": "release", "13": "withhold"})
        preview = client.get("/api/case-sessions/neodent-gm").json()[
            "session"]["release_preview"]
        assert release(client).status_code == 200
        body = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert len(body["files"]) == preview["file_count"]
        assert body["withheld_teeth"] == preview["withheld_teeth"]
        assert len(body["withheld_case_files"]) == preview[
            "withheld_case_file_count"]


class TestTheDemosDoorBack:
    """POST /{case}/delivery/reset (client 2026-07-30: "once paid i cant go back").
    The records stay server-side truth; the door back is an explicit act that
    withdraws all three together."""

    def test_reset_after_payment_reopens_the_whole_flow(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert client.post("/api/case-sessions/neodent-gm/payment",
                           json={"authorize": True}).status_code == 200

        res = client.post("/api/case-sessions/neodent-gm/delivery/reset")
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.confirmation is None
        assert session.payment is None
        assert session.release is None
        # and the gates all hold again: paying now refuses (no confirmed terms),
        # releasing refuses, artifacts refuse — the second walk is not cheaper
        assert client.post("/api/case-sessions/neodent-gm/payment",
                           json={"authorize": True}).status_code == 409
        assert release(client).status_code == 409
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts"
        ).status_code == 409

    def test_reset_after_release_withdraws_the_disclosure_too(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert client.post("/api/case-sessions/neodent-gm/payment",
                           json={"authorize": True}).status_code == 200
        assert release(client).status_code == 200

        assert client.post(
            "/api/case-sessions/neodent-gm/delivery/reset").status_code == 200
        assert SessionStore(product_root).load("neodent-gm").release is None
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts"
        ).status_code == 409

    def test_reset_with_nothing_signed_refuses_in_words(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/delivery/reset")
        assert res.status_code == 409
        assert "nothing to start over from" in res.json()["detail"]

    def test_the_run_and_the_site_rungs_survive_a_reset(self, settings, product_root):
        # the door back withdraws SIGNATURES, not work: the run stays current and
        # every site keeps its rung, so re-walking starts at re-confirm, not re-run
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        before = SessionStore(product_root).load("neodent-gm")
        statuses = {k: s.status for k, s in before.sites.items()}
        assert client.post(
            "/api/case-sessions/neodent-gm/delivery/reset").status_code == 200
        after = SessionStore(product_root).load("neodent-gm")
        assert after.run is not None and after.run.state == "done"
        assert {k: s.status for k, s in after.sites.items()} == statuses


class TestTheTermsResolve:
    """A recorded terms_version must resolve to the text it names (client
    2026-07-30: "shouldn't term and condition be a link and if clicked route to
    the proper pages")."""

    def test_the_current_terms_are_served_with_their_version(self, client):
        res = client.get("/api/terms")
        assert res.status_code == 200
        body = res.json()
        assert body["version"] == TERMS_VERSION
        assert body["status"] == "placeholder"
        assert "PLACEHOLDER" in body["body"]

    def test_a_confirmations_recorded_version_resolves_to_its_text(
            self, settings, product_root):
        # the whole point: read the version out of a sealed confirmation, then GET it
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        sealed = SessionStore(product_root).load("neodent-gm").confirmation
        assert sealed is not None and sealed.terms_version is not None
        res = client.get(f"/api/terms/{sealed.terms_version}")
        assert res.status_code == 200
        assert res.json()["version"] == sealed.terms_version

    def test_an_unknown_version_404s_and_names_what_this_build_carries(self, client):
        res = client.get("/api/terms/not-a-version")
        assert res.status_code == 404
        assert TERMS_VERSION in res.json()["detail"]


class TestResettingTheWholeCase:
    """POST /{case}/reset (client 2026-07-30: "resetting the cases persistance") —
    back to fresh intake, while the immutable run directories stay history."""

    def test_reset_returns_the_session_to_fresh_intake(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        before = SessionStore(product_root).load("neodent-gm")
        assert before.run is not None and before.sites and before.confirmation

        res = client.post("/api/case-sessions/neodent-gm/reset")
        assert res.status_code == 200
        after = SessionStore(product_root).load("neodent-gm")
        assert after.run is None
        assert after.sites == {}
        assert after.system is None
        assert after.detection is None
        assert after.confirmation is None and after.payment is None
        assert after.release is None
        assert after.adjust_decision is None and after.adjust_visited is False

    def test_the_CAS_version_carries_FORWARD_so_a_stale_rival_still_loses(
            self, settings, product_root):
        # a reset must not become a way to make a stale write look current
        client = deliverable_client(settings, product_root)
        before = SessionStore(product_root).load("neodent-gm").version
        assert client.post("/api/case-sessions/neodent-gm/reset").status_code == 200
        assert SessionStore(product_root).load("neodent-gm").version > before

    def test_the_run_DIRECTORY_survives_the_reset(self, settings, product_root):
        # AM-1: a landed run is history; re-walking a demo does not erase it
        client = deliverable_client(settings, product_root)
        run_id = SessionStore(product_root).load("neodent-gm").run.run_id
        run_dir = product_root / "neodent-gm" / "runs" / run_id
        assert run_dir.is_dir()
        assert client.post("/api/case-sessions/neodent-gm/reset").status_code == 200
        assert run_dir.is_dir(), "the immutable run directory must survive"
