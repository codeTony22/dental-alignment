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

Two events are legal from EVERY rung, deliberately:

  - ``declare``: a declaration is the reset boundary. Re-declaring a different part
    invalidates every later-ladder fact about the old one, so the site drops back to
    DECLARED from wherever it stood (the caller clears the facts themselves — none
    exist yet; previews and review ticks arrive in 5b, and they clear HERE, at this
    stated rule, instead of being rediscovered).
  - ``regress_to_detected``: the case-level system switch (AM-8) resets every site;
    idempotent over sites still fresh.

Later slices call the rest: ``preview`` (5b's live panes), ``review_ready`` (5b's
tick, 6's re-verify), ``flag`` (5c's run verdicts), ``adjust`` (6's tools). Written
now so the WHOLE ladder has one home before anyone needs a second.
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
    "preview": (frozenset({_S.DECLARED}), _S.PREVIEWED),
    "review_ready": (frozenset({_S.PREVIEWED, _S.ADJUSTED}), _S.READY),
    "flag": (frozenset({_S.PREVIEWED, _S.READY}), _S.FLAGGED),
    "adjust": (frozenset({_S.FLAGGED}), _S.ADJUSTED),
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
    """A preview rendered for the declared part (5b's live panes)."""
    return _step("preview", current)


def review_ready(current: SiteStatus) -> SiteStatus:
    """The operator's review tick over the panes (5b), or re-verify after an adjust
    (6) — the only acts that ever set READY (AM-8: reviewed over panels, never a
    checkbox)."""
    return _step("review_ready", current)


def flag(current: SiteStatus) -> SiteStatus:
    """A verdict flagged the site (plan §2's fork; 5c's run evidence)."""
    return _step("flag", current)


def adjust(current: SiteStatus) -> SiteStatus:
    """An adjust tool reworked the flagged site (slice 6)."""
    return _step("adjust", current)
