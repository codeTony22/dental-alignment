"""THE SITE STATUS MACHINE (plan §2, slice 5a): the ladder
``detected → declared → previewed → ready | flagged → adjusted → ready``, as pure
event functions with refusals for every illegal jump.

Tested EXHAUSTIVELY — every (event × current status) pair — because the module is
tiny and the whole point of extracting it is that no resource ever pokes a status
string again: whatever a handler can express, this table has already judged.

The three always-legal events are deliberate, not lax:

  - ``declare`` from ANY rung: a declaration is the reset boundary — the operator
    re-describing the part invalidates every later-ladder fact about the old one
    (the resource clears those facts alongside — since 5b they exist: the preview's
    seat facts).
  - ``regress_to_detected`` from ANY rung: the case-level system switch resets every
    site (AM-8's visible-reset semantics, server-side).
  - ``invalidate_preview`` from ANY rung (5b): a case-level choices CHANGE — the
    demo's rule #1, construction/jaw/relief all describe the same shipped part — drops
    every rung past DECLARED back to DECLARED and leaves earlier rungs standing.
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
        S.DECLARED: S.PREVIEWED,  # the first render for a declaration
        S.PREVIEWED: S.PREVIEWED, # a re-render — 5b's auto-fire re-asks after a reload
        S.READY: S.READY,         # the same re-render over a REVIEWED site: the
                                  # derivation is deterministic over an unchanged
                                  # declaration+choices (the reset boundaries guarantee
                                  # they are unchanged), so a page reload must never
                                  # silently untick an operator's review
    },
    status.reseat_preview: {
        S.DECLARED: S.PREVIEWED,  # a first render lands exactly as ``preview`` does
        S.PREVIEWED: S.PREVIEWED, # …and so does a re-render over an unticked site
        S.READY: S.PREVIEWED,     # but a render whose SEAT differs from the recorded
                                  # one is NEW physics (the 2026-07-28 effective-
                                  # default drift finding): the review attested the
                                  # OLD seat, so the tick falls VISIBLY instead of
                                  # the panes repainting under it
    },
    status.review_ready: {
        S.PREVIEWED: S.READY,     # the operator's tick over the live panes (5b)
        S.ADJUSTED: S.READY,      # re-verify after an adjust tool (slice 6)
    },
    status.withdraw_review: {
        S.READY: S.PREVIEWED,     # the tick is two-way (the demo's checkbox): an
                                  # operator may take their attestation back
    },
    status.invalidate_preview: {
        S.DETECTED: S.DETECTED,   # never refuses — a choices change sweeps EVERY site,
        S.DECLARED: S.DECLARED,   # so fresh rungs pass through untouched
        S.PREVIEWED: S.DECLARED,  # the preview described choices no longer chosen
        S.READY: S.DECLARED,      # …and so did the review over it
        S.FLAGGED: S.DECLARED,    # a flag is run evidence about the OLD choices (5c)
        S.ADJUSTED: S.DECLARED,
    },
    status.flag: {
        S.PREVIEWED: S.FLAGGED,   # plan §2's fork: previewed → ready | flagged
        S.READY: S.FLAGGED,       # a run's verdict may downgrade a reviewed site (5c)
    },
    status.adjust: {
        S.FLAGGED: S.ADJUSTED,    # the stage's reason for existing (plan §4)
        # WIDENED in slice 6, deliberately. Adjust is a rework SURFACE, not a penalty
        # box: the plan's queue lists clean sites below the flagged ones, visibly
        # optional, and a tool that lands on one moves the pose its review attested —
        # so READY falls to ADJUSTED and the operator re-confirms over the new panes
        # (review_ready above draws that edge already). ADJUSTED→ADJUSTED is the
        # second tool on one site: refit, then nudge.
        S.READY: S.ADJUSTED,
        S.ADJUSTED: S.ADJUSTED,
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
