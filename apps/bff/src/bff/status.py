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
two-way tick); 5c/6 call ``flag`` and ``adjust``. Written together so the WHOLE ladder
has one home.
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
    "adjust": (frozenset({_S.FLAGGED}), _S.ADJUSTED),
}

# ``preview`` needs per-rung landings a single-target edge cannot draw (see the
# function's doc): first render moves DECLARED->PREVIEWED, a re-render holds the rung.
_PREVIEW_LANDINGS: Dict[SiteStatus, SiteStatus] = {
    _S.DECLARED: _S.PREVIEWED,
    _S.PREVIEWED: _S.PREVIEWED,
    _S.READY: _S.READY,
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
    """A preview rendered for the declared part (5b's live panes).

    Legal from DECLARED (the first render), PREVIEWED (a re-render — the payload is
    response-only, so the UI's auto-fire re-asks after a page reload) and READY (the
    SAME re-render over a reviewed site). READY holds its rung deliberately: the
    derivation is deterministic over an unchanged declaration+choices — and the reset
    boundaries guarantee they are unchanged wherever READY still stands — so a reload's
    re-render must never silently untick an operator's review (the re-click
    pair-integrity lesson: a re-render never destroys an operator act)."""
    target = _PREVIEW_LANDINGS.get(current)
    if target is None:
        allowed = ", ".join(sorted(s.value for s in _PREVIEW_LANDINGS))
        raise IllegalTransition(
            f"cannot preview a site that is {current.value!r} — the ladder allows "
            f"preview only from: {allowed}")
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
    """An adjust tool reworked the flagged site (slice 6)."""
    return _step("adjust", current)
