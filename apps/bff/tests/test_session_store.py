"""THE SESSION STORE (plan §3, grill AM-4): per-case flow state that survives a restart.

What these tests pin, and why it matters at the money-adjacent step:

  - persistence + rehydration: a BFF restart mid-morning loses nothing;
  - a corrupt session file REFUSES loudly instead of silently resetting to a fresh
    session — a reset would forget ``payment_authorized`` and the confirmation record;
  - a case id can never step outside the store root (the id appears in a path);
  - defaults are fail-closed: fresh sessions carry no confirmation, no payment.

Client-writability is not tested here because it is STRUCTURAL: no endpoint accepts
session fields from a request body — see test_case_sessions for the route-shape guard.
"""
from __future__ import annotations

import pytest

from bff.session import CaseSession, RunSession, SessionStore, SiteSession, SiteStatus


def test_a_missing_session_starts_fresh_and_fail_closed(tmp_path):
    store = SessionStore(tmp_path)
    s = store.load("case-a")
    assert s.case_id == "case-a"
    assert s.sites == {}
    assert s.adjust_visited is False
    assert s.confirmation is None
    assert s.payment_authorized is False
    assert s.run is None
    # a read is a read: nothing was written for merely asking
    assert not (tmp_path / "case-a").exists()


def test_save_then_load_round_trips_every_field(tmp_path):
    store = SessionStore(tmp_path)
    s = store.load("case-a")
    s.sites["13"] = SiteSession(status=SiteStatus.FLAGGED, declared_variant="5020")
    s.adjust_visited = True
    s.run = RunSession(job_id="job-1", state="refused", refusal="gate said no")
    store.save(s)
    again = store.load("case-a")
    assert again.sites["13"].status is SiteStatus.FLAGGED
    assert again.sites["13"].declared_variant == "5020"
    assert again.adjust_visited is True
    assert again.run is not None and again.run.refusal == "gate said no"
    assert (tmp_path / "case-a" / "session.json").is_file()


def test_save_leaves_no_partial_files_beside_the_session(tmp_path):
    store = SessionStore(tmp_path)
    store.save(store.load("case-a"))
    assert [p.name for p in (tmp_path / "case-a").iterdir()] == ["session.json"]


def test_rehydrate_finds_every_persisted_session(tmp_path):
    store = SessionStore(tmp_path)
    store.save(store.load("case-a"))
    store.save(store.load("case-b"))
    assert set(store.rehydrate()) == {"case-a", "case-b"}


def test_rehydrate_of_a_store_that_never_wrote_is_empty(tmp_path):
    assert SessionStore(tmp_path / "nowhere-yet").rehydrate() == {}


@pytest.mark.parametrize("evil", ["../escape", "a/b", "", ".", "..", ".hidden"])
def test_a_case_id_that_could_leave_the_store_root_is_refused(tmp_path, evil):
    store = SessionStore(tmp_path)
    with pytest.raises(ValueError):
        store.load(evil)
    with pytest.raises(ValueError):
        store.save(CaseSession(case_id=evil))


def test_a_corrupt_session_refuses_loudly_instead_of_resetting(tmp_path):
    # silently replacing a corrupt file with a fresh session would forget the
    # confirmation and payment state — refuse and name the file instead
    (tmp_path / "case-a").mkdir(parents=True)
    (tmp_path / "case-a" / "session.json").write_text("{this is not json")
    with pytest.raises(ValueError, match="session"):
        SessionStore(tmp_path).load("case-a")
