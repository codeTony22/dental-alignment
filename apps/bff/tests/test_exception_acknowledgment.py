"""ACCEPT AS FLAGGED EXCEPTION, IN ADVANCE (client ruling 2026-08-02).

The comp's amber "accept as flagged exception" button moves onto the Adjustment page.
THE DESIGN DECISION, already taken: this is a persisted DRAFT acknowledgment —
``withhold_intent``'s sibling (the drop's own draft), not a second exclusion or
acknowledgment concept — that PRE-FILLS Deliver's row-by-row checkboxes. It is NOT a
signature: AM-12's ``ConfirmIn.acknowledged_flags`` stays required and stays the only
thing that seals a released flagged row.

What this file pins, in the order the operator meets it:

  1. the happy pair — draft given, shown on both surfaces, withdrawn;
  2. the 422s: not eligible (an unflagged, unnoted site), no run at all, withdrawing a
     draft nobody gave;
  3. the eligibility check is ``session.needs_acknowledgment`` — the SAME predicate
     ``deliver.confirm_case``'s gate stands on, exercised here over BOTH the reasons
     it can fire (a flagged verdict, a shared-part production note);
  4. the assurance exposure, and that the draft never rides into the sealed bundle
     (``AssuranceSite.withhold_intent``'s own precedent, extended);
  5. the run reset boundary — UNLIKE ``withhold_intent``, this draft does not survive
     the run it was given over ceasing to be current, and the reason is stated where
     the clearing lives (``session.clear_exception_intents``);
  6. ConfirmIn is UNCHANGED: a draft alone never satisfies the confirm gate.
"""
from __future__ import annotations

import json

import pytest

from bff.config import Settings
from bff.session import SessionStore, SiteStatus

from conftest import make_data_tree
from test_assurance import landed_client, with_note
from test_deliver import confirm, confirm_body, deliverable_client
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


def acknowledge(client, tooth: int = 13):
    return client.post(f"/api/case-sessions/neodent-gm/sites/{tooth}/acknowledge")


def withdraw(client, tooth: int = 13):
    return client.delete(f"/api/case-sessions/neodent-gm/sites/{tooth}/acknowledge")


def site_of(detail: dict, tooth: int) -> dict:
    return next(s for s in detail["sites"] if s["tooth"] == tooth)


def stored(product_root):
    return SessionStore(product_root).load("neodent-gm")


def flagged_client(settings, product_root):
    # tooth 4 clean/ready, tooth 13 flagged ("attention") — one eligible row, one not
    return landed_client(settings, product_root, [row(4), row(13, level="attention")])


# --- the happy pair: draft given, shown, withdrawn --------------------------------------

class TestTheActAndItsReversal:
    def test_a_flagged_site_can_be_acknowledged_in_advance(
            self, settings, product_root):
        client = flagged_client(settings, product_root)
        res = acknowledge(client, tooth=13)
        assert res.status_code == 200
        assert site_of(res.json(), 13)["exception_acknowledged"] is True
        assert stored(product_root).sites["13"].exception_intent is not None

    def test_the_detail_shows_it_and_only_it(self, settings, product_root):
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        detail = client.get("/api/case-sessions/neodent-gm").json()
        assert site_of(detail, 13)["exception_acknowledged"] is True
        assert site_of(detail, 4)["exception_acknowledged"] is False

    def test_withdrawing_the_draft_is_the_same_pair(self, settings, product_root):
        client = flagged_client(settings, product_root)
        assert acknowledge(client, tooth=13).status_code == 200
        res = withdraw(client, tooth=13)
        assert res.status_code == 200
        assert site_of(res.json(), 13)["exception_acknowledged"] is False
        assert stored(product_root).sites["13"].exception_intent is None

    def test_both_directions_land_in_the_activity_log(
            self, settings, product_root):
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        withdraw(client, tooth=13)
        events = [e.event for e in stored(product_root).activity]
        assert "site-exception-acknowledged" in events
        assert "site-exception-withdrawn" in events

    def test_re_acknowledging_the_same_draft_records_no_second_act(
            self, settings, product_root):
        """An identical re-act is not an act (the SeatedSelection precedent,
        ``withhold_intent``'s own reading of it)."""
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        acknowledge(client, tooth=13)
        events = [e.event for e in stored(product_root).activity]
        assert events.count("site-exception-acknowledged") == 1

    def test_a_shared_part_production_note_is_also_eligible(
            self, settings, product_root):
        # both sites READY per guidance — the shared-part conflict is the ONLY
        # thing making them need acknowledgment (deliver.py's own fixture pattern)
        client = landed_client(settings, product_root,
                               [with_note(row(4)), with_note(row(13))])
        res = acknowledge(client, tooth=4)
        assert res.status_code == 200
        assert stored(product_root).sites["4"].exception_intent is not None


# --- the 422s ----------------------------------------------------------------------------

class TestRefusals:
    def test_no_run_at_all_is_refused_in_words(self, settings):
        client = client_with(settings, FakeWorker())
        res = acknowledge(client, tooth=13)
        assert res.status_code == 422
        assert "no completed current run" in res.json()["detail"]

    def test_an_unflagged_unnoted_site_is_refused_naming_the_rule(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        res = acknowledge(client, tooth=13)
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "needs no acknowledgment" in detail
        assert "did not flag it" in detail
        assert "shared-construction-part conflict" in detail

    def test_withdrawing_a_draft_nobody_gave_is_refused(
            self, settings, product_root):
        client = flagged_client(settings, product_root)
        res = withdraw(client, tooth=13)
        assert res.status_code == 422
        assert "no standing exception acknowledgment" in res.json()["detail"]

    def test_an_unknown_tooth_is_a_404(self, settings, product_root):
        client = flagged_client(settings, product_root)
        assert acknowledge(client, tooth=99).status_code == 404
        assert withdraw(client, tooth=99).status_code == 404

    def test_an_unknown_case_is_a_404(self, settings, product_root):
        client = flagged_client(settings, product_root)
        res = client.post("/api/case-sessions/nope/sites/13/acknowledge")
        assert res.status_code == 404
        res = client.delete("/api/case-sessions/nope/sites/13/acknowledge")
        assert res.status_code == 404


# --- the assurance exposure ---------------------------------------------------------------

class TestTheAssuranceExposure:
    def assurance(self, client):
        res = client.get("/api/case-sessions/neodent-gm/assurance")
        assert res.status_code == 200, res.text
        return {s["tooth"]: s for s in res.json()["sites"]}

    def test_the_draft_pre_fills_the_assurance_row(self, settings, product_root):
        client = flagged_client(settings, product_root)
        assert self.assurance(client)[13]["exception_acknowledged"] is False
        acknowledge(client, tooth=13)
        assert self.assurance(client)[13]["exception_acknowledged"] is True
        # and the row's own status is untouched — the draft states an act, never
        # what the site IS
        assert self.assurance(client)[13]["status"] == "flagged"

    def test_the_draft_never_reaches_the_sealed_bytes(
            self, settings, product_root):
        """The ``withhold_intent`` precedent (``TestADispositionIsNotEvidence``),
        extended: a projection field an operator may still change AFTER confirming
        (this is a draft, never a signature) must sit outside the hash, or
        withdrawing it would read as evidence drift at release time."""
        from bff.resources.case_sessions import _case_or_404
        from bff.resources.deliver import derive_assurance

        client = deliverable_client(settings, product_root,
                                    rows=[row(4), row(13, level="attention")])
        case = _case_or_404(settings, "neodent-gm")
        store = SessionStore(product_root)
        before = derive_assurance(case, store.load("neodent-gm")).sealed_facts()
        assert acknowledge(client, tooth=13).status_code == 200
        after = derive_assurance(case, store.load("neodent-gm")).sealed_facts()
        assert after == before
        assert "exception_acknowledged" not in json.dumps(after)


# --- the run reset boundary (2026-08-02: DIFFERS from withhold_intent, deliberately) -----

class TestTheDraftDoesNotSurviveARework:
    """UNLIKE ``withhold_intent`` (which survives every boundary here on purpose —
    a drop is a standing preference independent of any run's verdict), this draft
    is an attestation ABOUT one specific run's specific verdict, and cannot honestly
    survive that run ceasing to be current. See ``session.clear_exception_intents``
    for why it needs TWO call sites where ``withhold_intent`` needed none."""

    def test_a_choices_change_clears_the_draft(self, settings, product_root):
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"construction_path": "dess/neodent-gm-scanbody.stl",
                               "jaw": "upper", "gingival_offset_mm": 0.35})
        assert res.status_code == 200
        assert stored(product_root).sites["13"].exception_intent is None

    def test_a_system_switch_clears_the_draft(self, settings, product_root):
        # a second system for the switch to land on (test_case_sessions'
        # ``_second_model`` fixture pattern, reproduced here)
        caps = settings.data_root / "library/caps/astra-ev"
        caps.mkdir(parents=True)
        (caps / "astra-ev-3010.stl").touch()
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        res = client.put("/api/case-sessions/neodent-gm/system",
                         json={"model": "astra-ev"})
        assert res.status_code == 200
        assert stored(product_root).sites["13"].exception_intent is None

    def test_a_remark_clears_the_draft(self, settings, product_root):
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        res = client.put("/api/case-sessions/neodent-gm/sites/13/mark",
                         json={"center": [9.0, 9.0, 9.0]})
        assert res.status_code == 200
        assert stored(product_root).sites["13"].exception_intent is None

    def test_a_fresh_run_authorized_over_a_done_one_clears_every_draft(
            self, settings, product_root):
        """THE PATH ``clear_current_run`` NEVER SEES (client 2026-08-02): a done
        run may be re-authorized directly, with no reset boundary in between —
        exactly the gap a single call site would have missed."""
        worker = FakeWorker(summary=summary_for([row(4), row(13, level="attention")]))
        client = client_with(settings, worker)
        seed_ready(product_root)
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        assert acknowledge(client, tooth=13).status_code == 200
        assert stored(product_root).sites["13"].exception_intent is not None

        # wedge tooth 13 back to READY so the SECOND run is authorized directly
        # over the still-``done`` first one (getting there via the real ladder —
        # adjust, then re-review — is a different module's own tests; this pins
        # ``claim``'s boundary, not the path to it)
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.sites["13"].status = SiteStatus.READY
        store.save(session)

        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        assert stored(product_root).sites["13"].exception_intent is None

    def test_a_full_case_reset_clears_it_with_everything_else(
            self, settings, product_root):
        client = flagged_client(settings, product_root)
        acknowledge(client, tooth=13)
        assert client.post(
            "/api/case-sessions/neodent-gm/reset").status_code == 200
        assert stored(product_root).sites == {}


# --- ConfirmIn is unchanged: a draft alone never satisfies the confirm gate -------------

class TestConfirmIsUnchanged:
    """AM-12's row-by-row rule stays intact: the draft PRE-FILLS the checkbox, it
    does not tick it. ``acknowledged_flags`` omitting a drafted site still refuses,
    in exactly the words it always has."""

    def test_a_drafted_site_without_its_own_acknowledged_flag_still_refuses(
            self, settings, product_root):
        client = deliverable_client(settings, product_root,
                                    rows=[row(4), row(13, level="attention")])
        assert acknowledge(client, tooth=13).status_code == 200
        res = confirm(client, confirm_body(acknowledged=()))
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13" in detail and "acknowledg" in detail

    def test_the_row_by_row_acknowledgment_still_confirms_it(
            self, settings, product_root):
        client = deliverable_client(settings, product_root,
                                    rows=[row(4), row(13, level="attention")])
        assert acknowledge(client, tooth=13).status_code == 200
        assert confirm(client, confirm_body(acknowledged=[13])).status_code == 200

    def test_withdrawing_the_draft_does_not_touch_a_standing_confirmation(
            self, settings, product_root):
        """The draft's only job was pre-filling; once ``acknowledged_flags`` has
        sealed, withdrawing the note-to-self has no bearing on what was signed —
        unlike a contradicted ``withhold_intent``, which DOES retire a standing
        confirmation because dispositions are folded into the sealed map itself.
        This draft never rides into the sealed bytes at all (see
        ``TestTheAssuranceExposure``), so there is nothing for a withdrawal to
        contradict."""
        client = deliverable_client(settings, product_root,
                                    rows=[row(4), row(13, level="attention")])
        assert acknowledge(client, tooth=13).status_code == 200
        assert confirm(client, confirm_body(acknowledged=[13])).status_code == 200
        sealed = stored(product_root).confirmation
        assert sealed is not None
        assert withdraw(client, tooth=13).status_code == 200
        assert stored(product_root).confirmation == sealed
