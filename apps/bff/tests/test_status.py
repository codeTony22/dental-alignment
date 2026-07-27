"""THE SITE STATUS MACHINE (plan §2, slice 5a): the ladder
``detected → declared → previewed → ready | flagged → adjusted → ready``, as pure
event functions with refusals for every illegal jump.

Tested EXHAUSTIVELY — every (event × current status) pair — because the module is
tiny and the whole point of extracting it is that no resource ever pokes a status
string again: whatever a handler can express, this table has already judged.

The two always-legal events are deliberate, not lax:

  - ``declare`` from ANY rung: a declaration is the reset boundary — the operator
    re-describing the part invalidates every later-ladder fact about the old one
    (the resource clears those facts; today there are none, the rule exists so
    5b/5c inherit it instead of rediscovering it).
  - ``regress_to_detected`` from ANY rung: the case-level system switch resets every
    site (AM-8's visible-reset semantics, server-side).
"""
from __future__ import annotations

import pytest

from bff import status
from bff.session import SiteStatus

S = SiteStatus

# Every event with its legal (current → next) pairs. The parametrization below walks
# the FULL cross product; a pair absent here must refuse.
LADDER = {
    status.declare: {
        S.DETECTED: S.DECLARED,
        S.DECLARED: S.DECLARED,   # re-declaration of a different variant KEEPS declared
        S.PREVIEWED: S.DECLARED,  # …and from any later rung, drops back: the part changed
        S.READY: S.DECLARED,
        S.FLAGGED: S.DECLARED,
        S.ADJUSTED: S.DECLARED,
    },
    status.regress_to_detected: {
        S.DETECTED: S.DETECTED,   # idempotent — a system switch may hit fresh sites
        S.DECLARED: S.DETECTED,
        S.PREVIEWED: S.DETECTED,
        S.READY: S.DETECTED,
        S.FLAGGED: S.DETECTED,
        S.ADJUSTED: S.DETECTED,
    },
    status.preview: {
        S.DECLARED: S.PREVIEWED,  # the ladder's one preview edge; 5b widens it only
    },                            # if re-preview becomes a real act
    status.review_ready: {
        S.PREVIEWED: S.READY,     # the operator's tick over the live panes (5b)
        S.ADJUSTED: S.READY,      # re-verify after an adjust tool (slice 6)
    },
    status.flag: {
        S.PREVIEWED: S.FLAGGED,   # plan §2's fork: previewed → ready | flagged
        S.READY: S.FLAGGED,       # a run's verdict may downgrade a reviewed site (5c)
    },
    status.adjust: {
        S.FLAGGED: S.ADJUSTED,    # only flagged sites open in Adjust (plan §4)
    },
}

EVERY_PAIR = [(event, current) for event in LADDER for current in S]


@pytest.mark.parametrize("event,current", EVERY_PAIR,
                         ids=[f"{e.__name__}-from-{c.value}" for e, c in EVERY_PAIR])
def test_every_event_status_pair_is_judged(event, current):
    legal = LADDER[event]
    if current in legal:
        assert event(current) is legal[current]
    else:
        with pytest.raises(status.IllegalTransition) as exc:
            event(current)
        # the refusal names both the act and where the site actually stands,
        # so an endpoint can serve it as a sentence rather than a stack trace
        assert current.value in str(exc.value)
        assert event.__name__ in str(exc.value)


def test_the_table_above_is_the_whole_module():
    """No event escapes the exhaustive walk: every public transition function in
    bff.status is covered by LADDER, so adding one without testing it here fails."""
    import inspect

    public = {name for name, fn in inspect.getmembers(status, inspect.isfunction)
              if not name.startswith("_")}
    assert public == {fn.__name__ for fn in LADDER}
