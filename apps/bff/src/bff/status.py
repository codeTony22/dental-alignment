"""THE SITE STATUS MACHINE (plan §2, slice 5a): the site queue's ladder as pure
event functions — ``detected → declared → previewed → ready | flagged → adjusted →
ready`` — with a refusal for every jump the ladder does not draw.

Resources go through THESE functions and never poke status strings: the doctrine that
statuses are derived (AM-4) is only as strong as the derivation's discipline, and a
handler assigning ``SiteStatus.READY`` directly would be a claimed outcome wearing a
server-side hat. Each function is named for the ACT that moves a site (an operator's
declaration, a preview render, a review tick, a run verdict, an adjust tool), takes
the site's current status, and returns the next — or raises ``IllegalTransition``
with a sentence an endpoint can serve.

Three events are legal from EVERY rung, deliberately:

  - ``declare``: a declaration is the reset boundary. Re-declaring a different part
    invalidates every later-ladder fact about the old one, so the site drops back to
    DECLARED from wherever it stood (the caller clears the facts alongside — since 5b
    they exist: ``SiteSession.clear_preview_facts``).
  - ``regress_to_detected``: the case-level system switch (AM-8) resets every site;
    idempotent over sites still fresh.
  - ``invalidate_preview`` (5b): a case-level choices CHANGE — construction, jaw or
    relief; the demo's rule #1, they all describe the same shipped part — drops every
    rung past DECLARED back to DECLARED, leaving earlier rungs standing.

5b reaches ``preview`` (the live panes) and ``review_ready``/``withdraw_review`` (the
two-way tick); 5c/6 call ``flag`` and ``adjust``; ``reseat_preview`` (2026-07-28) is
``preview``'s changed-seat twin — same act, but READY falls because the review
attested a different seat. Written together so the WHOLE ladder has one home.
"""
from __future__ import annotations

from typing import Dict, Tuple

from .session import SiteStatus

_S = SiteStatus

_ANY = frozenset(_S)


class IllegalTransition(RuntimeError):
    """An act the ladder does not allow from where the site stands. The message is a
    servable sentence: the act, the site's actual rung, and the rungs it would need."""


# event name -> (rungs the act is legal from, the rung it lands on)
_EDGES: Dict[str, Tuple[frozenset, SiteStatus]] = {
    "declare": (_ANY, _S.DECLARED),
    "regress_to_detected": (_ANY, _S.DETECTED),
    "review_ready": (frozenset({_S.PREVIEWED, _S.ADJUSTED}), _S.READY),
    "withdraw_review": (frozenset({_S.READY}), _S.PREVIEWED),
    "flag": (frozenset({_S.PREVIEWED, _S.READY}), _S.FLAGGED),
    # slice 6 WIDENED the adjust edge, deliberately — see ``adjust``'s docstring:
    # a clean site may be reworked (the queue offers it, visibly optional), a
    # reworked one may be reworked again, and either way READY falls because the
    # pose the review attested has moved.
    "adjust": (frozenset({_S.FLAGGED, _S.READY, _S.ADJUSTED}), _S.ADJUSTED),
}

# ``preview`` needs per-rung landings a single-target edge cannot draw (see the
# function's doc): first render moves DECLARED->PREVIEWED, a re-render holds the rung.
_PREVIEW_LANDINGS: Dict[SiteStatus, SiteStatus] = {
    _S.DECLARED: _S.PREVIEWED,
    _S.PREVIEWED: _S.PREVIEWED,
    _S.READY: _S.READY,
}

# ``reseat_preview``: the same act over a DIFFERENT seat (see the function's doc) —
# identical landings except READY, whose attestation falls with the changed physics.
_RESEAT_LANDINGS: Dict[SiteStatus, SiteStatus] = {
    _S.DECLARED: _S.PREVIEWED,
    _S.PREVIEWED: _S.PREVIEWED,
    _S.READY: _S.PREVIEWED,
}


def _step(event: str, current: SiteStatus) -> SiteStatus:
    legal_from, target = _EDGES[event]
    if current not in legal_from:
        allowed = ", ".join(sorted(s.value for s in legal_from))
        raise IllegalTransition(
            f"cannot {event} a site that is {current.value!r} — the ladder allows "
            f"{event} only from: {allowed}")
    return target


def declare(current: SiteStatus) -> SiteStatus:
    """An operator declared a variant for the site — legal from any rung (the reset
    boundary; the caller clears later-ladder facts alongside)."""
    return _step("declare", current)


def regress_to_detected(current: SiteStatus) -> SiteStatus:
    """The case's system switched (AM-8): every site starts over."""
    return _step("regress_to_detected", current)


def preview(current: SiteStatus) -> SiteStatus:
    """A preview rendered for the declared part (5b's live panes), seating the SAME
    selection the site's facts already record.

    Legal from DECLARED (the first render), PREVIEWED (a re-render — the payload is
    response-only, so the UI's auto-fire re-asks after a page reload) and READY (the
    SAME re-render over a reviewed site). READY holds its rung deliberately: the
    derivation is deterministic over an unchanged seat, so a reload's re-render must
    never silently untick an operator's review (the re-click pair-integrity lesson:
    a re-render never destroys an operator act). "Unchanged" is JUDGED, not assumed
    (the 2026-07-28 effective-default drift finding): the preview route compares the
    landed selection against the site's recorded seat and routes a differing one
    through ``reseat_preview`` — the reset boundaries only guarantee the OPERATOR
    acts, while the effective fallbacks can drift outside them."""
    target = _PREVIEW_LANDINGS.get(current)
    if target is None:
        allowed = ", ".join(sorted(s.value for s in _PREVIEW_LANDINGS))
        raise IllegalTransition(
            f"cannot preview a site that is {current.value!r} — the ladder allows "
            f"preview only from: {allowed}")
    return target


def reseat_preview(current: SiteStatus) -> SiteStatus:
    """A preview rendered whose SEAT differs from the site's recorded one — or whose
    record is absent, which proves nothing and fails closed (the 2026-07-28
    effective-default drift finding). The effective fallbacks — the case's
    suggestions, the standing relief default — live outside the session, so they can
    drift while READY stands and no reset boundary fires; the UI then auto-refires
    the preview when its key changes. That render is NEW physics: READY falls to
    PREVIEWED because the review attested the OLD seat (AM-8: reviewed over the
    panes means THESE panes), and the drift costs the tick visibly instead of the
    panes repainting under it. Every other landing matches ``preview`` — the caller
    (the preview route) judges seat equality and picks between the two events."""
    target = _RESEAT_LANDINGS.get(current)
    if target is None:
        allowed = ", ".join(sorted(s.value for s in _RESEAT_LANDINGS))
        raise IllegalTransition(
            f"cannot reseat_preview a site that is {current.value!r} — the ladder "
            f"allows reseat_preview only from: {allowed}")
    return target


def review_ready(current: SiteStatus) -> SiteStatus:
    """The operator's review tick over the panes (5b), or re-verify after an adjust
    (6) — the only acts that ever set READY (AM-8: reviewed over panels, never a
    checkbox)."""
    return _step("review_ready", current)


def withdraw_review(current: SiteStatus) -> SiteStatus:
    """The tick un-ticked (5b): the demo's review checkbox was two-way, and an
    attestation the operator can take back is more honest than one that only latches.
    Lands on PREVIEWED — the panes are still rendered; only the attestation is gone.
    (A slice-6 adjusted-then-reviewed site also lands PREVIEWED: the ladder records
    where a site STANDS, not how it got there — revisit with 6 if adjust needs more.)"""
    return _step("withdraw_review", current)


def invalidate_preview(current: SiteStatus) -> SiteStatus:
    """A case-level choice changed — construction, jaw or relief (put_choices' stated
    boundary; the demo's rule #1, librarySelection.ts:10-16: they all describe the
    same shipped part). Every fact past DECLARED describes a part no longer being
    made, so later rungs drop back to DECLARED while declarations stand. Never
    refuses: the choices change sweeps every site, so fresh rungs pass through
    untouched (idempotent, like ``regress_to_detected``)."""
    if current in (_S.DETECTED, _S.DECLARED):
        return current
    return _S.DECLARED


def flag(current: SiteStatus) -> SiteStatus:
    """A verdict flagged the site (plan §2's fork; 5c's run evidence)."""
    return _step("flag", current)


def adjust(current: SiteStatus) -> SiteStatus:
    """An adjust tool reworked the site — the FIRST legitimate writer of this rung
    (slice 6). Legal from FLAGGED (the stage's reason for existing), from READY (the
    stage is a rework surface, not a penalty box: the plan's queue lists clean sites
    below the flagged ones, visibly optional, and the client asked for tools they can
    reach) and from ADJUSTED (a second tool on the same site — an operator refits,
    then nudges).

    READY FALLING IS THE POINT, not a side effect. A tool that lands moves the pose
    the review attested, so the attestation cannot stand: the site drops to ADJUSTED
    and the operator re-confirms over the NEW panes (``review_ready`` is legal from
    here — the ladder already drew that edge). Same doctrine as ``reseat_preview``:
    changed physics costs the tick visibly, and never repaints under it."""
    return _step("adjust", current)
