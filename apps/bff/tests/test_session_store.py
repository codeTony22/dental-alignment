"""THE SESSION STORE (plan §3, grill AM-4): per-case flow state that survives a restart.

What these tests pin, and why it matters at the money-adjacent step:

  - persistence + rehydration: a BFF restart mid-morning loses nothing;
  - a corrupt session file REFUSES loudly instead of silently resetting to a fresh
    session — a reset would forget ``payment_authorized`` and the confirmation record;
  - a case id can never step outside the store root (the id appears in a path);
  - defaults are fail-closed: fresh sessions carry no confirmation, no payment;
  - saves are COMPARE-AND-SWAP (slice 5a): the document carries a version, and a save
    whose loaded version is no longer the disk's refuses with the named conflict error
    instead of silently clobbering the writer that got there first. Slice 4's detect
    route dodged one such lost update by hand (re-load after the derivation); with
    system and declaration writers joining in 5a, the store itself is the durable
    answer — the commit 1c4af60 note said exactly this.

Client-writability is not tested here because it is STRUCTURAL: no endpoint accepts
session fields from a request body — see test_case_sessions for the route-shape guard.
"""
from __future__ import annotations

import pytest

from bff.session import (CaseSession, RunSession, SessionConflict, SessionStore,
                         SiteSession, SiteStatus)


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


class TestCompareAndSwap:
    """The version field and the CAS save (slice 5a). Two writers may both fresh-load;
    only the first save lands — the second gets ``SessionConflict``, never a silent
    clobber. This is the write-write protection AM-4's client-claim rule implies."""

    def test_a_fresh_session_starts_at_version_zero_and_save_bumps_it(self, tmp_path):
        store = SessionStore(tmp_path)
        s = store.load("case-a")
        assert s.version == 0
        store.save(s)
        assert store.load("case-a").version == 1
        store.save(store.load("case-a"))
        assert store.load("case-a").version == 2

    def test_a_stale_save_refuses_with_the_named_conflict(self, tmp_path):
        store = SessionStore(tmp_path)
        first = store.load("case-a")
        second = store.load("case-a")   # both writers hold version 0
        first.adjust_visited = True
        store.save(first)               # lands; disk is now version 1
        second.sites["13"] = SiteSession(status=SiteStatus.DECLARED,
                                         declared_variant="5020")
        with pytest.raises(SessionConflict) as exc:
            store.save(second)          # still claims version 0 — the disk moved on
        # the error names the case and both versions, so a handler's 409 can say
        # what changed underneath instead of a bare "conflict"
        assert "case-a" in str(exc.value)
        assert exc.value.expected == 0
        assert exc.value.found == 1
        # and the refused write left no trace — the first writer's fact survives
        persisted = store.load("case-a")
        assert persisted.adjust_visited is True
        assert persisted.sites == {}

    def test_a_saved_object_may_save_again_without_reloading(self, tmp_path):
        # save syncs the in-memory version with the disk's, so a handler that
        # mutates twice in one request keeps working without a wasted re-load
        store = SessionStore(tmp_path)
        s = store.load("case-a")
        store.save(s)
        s.adjust_visited = True
        store.save(s)   # no conflict: the object rode along with its own bump
        assert store.load("case-a").adjust_visited is True

    def test_the_conflict_is_per_case_not_global(self, tmp_path):
        store = SessionStore(tmp_path)
        a = store.load("case-a")
        b = store.load("case-b")
        store.save(a)
        store.save(b)   # a's bump must not poison b's save
        assert store.load("case-b").version == 1
