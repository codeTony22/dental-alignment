"""THE RATE CARD AND THE INVOICE SHAPE (design flow.dc.html payLines/payTotal
1475-1480; gap ``per-site-pricing-model``, 2026-07-31).

WHY THIS MODULE EXISTS AT ALL, stated once because it is the sharpest doctrine point
on the Deliver surface: a client that could POST an amount could pay $0 for a released
case. An amount is a status-shaped claim wearing a currency symbol — the same class of
thing as a verdict — so it is DERIVED here, server-side, from the run's own assurance
and the case's turnaround choice. ``PaymentIn`` keeps its single ``authorize`` boolean;
the authorization route prices the case at the moment it authorizes and RECORDS what it
charged on ``PaymentRecord``, so a receipt is re-derivable afterwards even when the
lab's turnaround choice moves on.

THE NUMBERS BELOW ARE PLACEHOLDERS. The client has supplied no price list, and inventing
one and shipping it as fact would be the mistake ``TERMS_TEXT_PLACEHOLDER`` exists to
avoid, with money attached. The design prototype's own figures ($32 standard / $48 rush
per site, exceptions at half) are carried across as the placeholder so the surface has
believable shapes to render, and every invoice says ``status: "placeholder"`` in the
open. Swapping in the client's real rates is a change to ``_UNIT_CENTS`` plus a bump of
``RATE_CARD_VERSION`` — the version rides onto every payment record, so an amount
charged under the old card stays readable as having been charged under THAT card, never
silently reinterpreted (the ``TERMS_VERSION`` precedent, for the same reason).

MONEY IS INTEGER CENTS, never a float: a rate table in dollars-as-float would put
0.1 + 0.2 under a signature. The half-rate exception is integer division, and
``test_pricing`` pins that every unit in the card halves exactly.

This module deliberately knows nothing about sessions, runs or FastAPI — it owns the
card and the arithmetic. WHICH sites count as released, exceptional or withheld is the
Deliver resource's derivation (it is the same ``_needs_acknowledgment`` predicate the
confirmation gate stands on), passed in here as counts.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

CURRENCY = "USD"

# bump this beside ANY change to the card below — a payment record carries the version
# it was charged under, and an old amount must never be read as the new card's
RATE_CARD_VERSION = "placeholder-v1"

# the word the wire uses for "these rates are not the client's yet" (TermsDocumentView's
# own vocabulary, so a surface can render both the same way)
RATE_CARD_STATUS = "placeholder"

RATE_CARD_NOTE = (
    "PLACEHOLDER RATES — pending the client's price list. The figures are the design "
    "prototype's ($32 per site standard, $48 rush, exceptions at half rate) and are "
    "not a quotation."
)

# per released site, keyed by turnaround — the ONE thing the turnaround choice changes
_UNIT_CENTS: Dict[str, int] = {"standard": 3200, "rush": 4800}

# AN EXCEPTION BILLS AT HALF (the design's rule, kept): a site the operator had to
# acknowledge row by row is work the lab did not get to finish cleanly. Expressed as a
# fraction over integer cents rather than 0.5, so no float ever touches an amount.
EXCEPTION_NUMERATOR = 1
EXCEPTION_DENOMINATOR = 2

TURNAROUNDS = tuple(_UNIT_CENTS)


def unit_amount_cents(turnaround: str) -> int:
    """The per-site unit for a turnaround word. KeyError on a word the card does not
    carry — deliberately loud: a silent fallback to the standard rate would quietly
    undercharge a rush case, and the request models already refuse unknown words at
    the wire (``ChoicesIn.turnaround`` is a Literal)."""
    return _UNIT_CENTS[turnaround]


def exception_amount_cents(turnaround: str) -> int:
    return (unit_amount_cents(turnaround) * EXCEPTION_NUMERATOR
            // EXCEPTION_DENOMINATOR)


class InvoiceLine(BaseModel):
    """One line. ``key`` is the machine word a surface switches on; ``label`` is a
    noun phrase with NO money in it — currency formatting is presentation, and the
    amounts ride as cents so the UI formats them in the viewer's own locale.

    ``billed`` is not ``amount_cents == 0``: a rush turnaround is included at zero and
    IS billed (it repriced every site above), while a withheld site is not billed at
    all. Collapsing the two would have the surface tell an operator that withholding
    a site was free when what actually happened is that it was never charged for."""

    key: str
    label: str
    quantity: int
    # None on lines that have no per-unit price (the turnaround line, withheld sites)
    unit_amount_cents: Optional[int] = None
    amount_cents: int
    billed: bool


class InvoicePaymentView(BaseModel):
    """WHAT WAS ACTUALLY CHARGED, off the payment record — beside, never instead of,
    the current price. The two can legitimately differ (a turnaround change after
    payment reprices the case going forward), and collapsing them would either forge
    a receipt or deny the operator's newer choice. Fields are Optional because a
    payment record persisted before this module existed carries none of them, and
    under-claiming is the safe direction (the ``adjustments`` precedent)."""

    amount_cents: Optional[int]
    currency: Optional[str]
    rate_card_version: Optional[str]
    turnaround: Optional[str]
    at: str


class InvoiceView(BaseModel):
    """The priced case, read-only. Every field here is a server derivation; there is
    no route that accepts any of it."""

    case_id: str
    run_id: str
    currency: str
    rate_card_version: str
    status: str
    note: str
    turnaround: str
    # "chosen" | "default" — the EffectiveChoiceView vocabulary, so the surface renders
    # its "default" chip from a server fact instead of comparing fields itself
    turnaround_source: str
    lines: List[InvoiceLine] = Field(default_factory=list)
    total_cents: int
    paid: Optional[InvoicePaymentView] = None


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def price_invoice(*, case_id: str, run_id: str, turnaround: str,
                  turnaround_source: str, released: int, exceptions: int,
                  withheld: int,
                  paid: Optional[InvoicePaymentView] = None) -> InvoiceView:
    """The whole invoice from four counts. A line appears only when it has something
    in it — an invoice carrying "0 exceptions" would be inviting a reader to wonder
    what an exception is on a case that has none — except the TURNAROUND line, which
    is always stated because it is what every other line's rate keys on."""
    unit = unit_amount_cents(turnaround)
    exception_unit = exception_amount_cents(turnaround)
    lines: List[InvoiceLine] = []
    if released:
        lines.append(InvoiceLine(
            key="released_sites", label=_plural(released, "released site"),
            quantity=released, unit_amount_cents=unit,
            amount_cents=released * unit, billed=True))
    if exceptions:
        lines.append(InvoiceLine(
            key="exception_sites",
            label=_plural(exceptions, "acknowledged exception") + ", at half rate",
            quantity=exceptions, unit_amount_cents=exception_unit,
            amount_cents=exceptions * exception_unit, billed=True))
    lines.append(InvoiceLine(
        key="turnaround", label=f"{turnaround.capitalize()} turnaround",
        quantity=1, unit_amount_cents=None, amount_cents=0, billed=True))
    if withheld:
        lines.append(InvoiceLine(
            key="withheld_sites",
            label=_plural(withheld, "withheld site") + ", not released",
            quantity=withheld, unit_amount_cents=None, amount_cents=0,
            billed=False))
    return InvoiceView(
        case_id=case_id, run_id=run_id, currency=CURRENCY,
        rate_card_version=RATE_CARD_VERSION, status=RATE_CARD_STATUS,
        note=RATE_CARD_NOTE, turnaround=turnaround,
        turnaround_source=turnaround_source, lines=lines,
        total_cents=sum(line.amount_cents for line in lines), paid=paid)
