/**
 * DELIVER'S DISPLAY RULES (plan §4 Deliver; grill AM-11/AM-12) — pure, framework-free.
 *
 * Direction of trust (AM-4): every VERDICT here is the BFF's — the table order
 * (served worst-first, rendered verbatim), the flag statuses, the confirmation and
 * release records. What this module derives is display logic only: which pieces are
 * still missing before the confirm button may fire (each one NAMED under the inert
 * button — flow.ts's blockedReason doctrine applied to a button), how the operator's
 * acts assemble into the wire body, and how a 409 that means "the evidence moved"
 * is told apart from any other refusal. The BFF re-judges every one of these rules
 * server-side; a UI that skipped them would merely see its POST refused in words.
 */
import type {
  ApiResult,
  ArtifactFile,
  ArtifactsView,
  AssuranceSite,
  AssuranceView,
  ChoicesView,
  ConfirmBody,
  ConfirmationView,
  InvoicePaymentView,
  InvoiceView,
  SessionView,
} from "../api/client";
// the rework's vocabulary lives where the rework happens; Deliver is where it is read
import { staleMetricsPhrase } from "./adjust";

export type Disposition = "release" | "withhold";

/** The operator's per-row acts so far — keyed by tooth (number, UI-side). */
export type DispositionMap = Readonly<Record<number, Disposition>>;

/**
 * AM-12's acknowledgment gate applies whenever EITHER of two things is true:
 * the session ladder flagged the site, or the PRODUCTION block disclosed a
 * shared-construction-part conflict (``production_note`` — plan §10-E, finding
 * 2026-07-28). Mirrors the BFF's own predicate (deliver.py's
 * ``_needs_acknowledgment``) exactly, so a row can never look pinned-first (the
 * BFF's own worst-first order already reflects this) without the UI also
 * offering — and demanding — the same acknowledgment.
 */
export function needsAcknowledgment(site: AssuranceSite): boolean {
  return site.status === "flagged" || site.production_note !== null;
}

/** Why a row needs its own acknowledgment, in the reader's words — flagged
 * sites read as they always did; a production-noted "ready" row says the
 * true reason rather than claiming a flag that never fired. */
function acknowledgmentReason(site: AssuranceSite): string {
  return site.status === "flagged"
    ? "is flagged"
    : "shares a construction part with a differently-declared variant";
}

/**
 * Everything still standing between the operator and a confirmable table, in table
 * order (worst first, exactly as served): the terms acceptance (plan §10-A), then
 * each row needing acknowledgment (``needsAcknowledgment``) headed for release
 * without one (AM-12: row by row, never in bulk).
 *
 * TWO BLOCKERS WERE DELETED FROM THIS LIST, both deliberately:
 *
 *  - the ACTOR'S NAME (client 2026-07-27 #1: "WE dont need operator name the
 *    checkmark is sufficient") — an unauthenticated self-typed name blocked the
 *    button while proving nothing.
 *  - the PER-ROW DISPOSITION (client 2026-07-27 #4: "What is disposition release vs
 *    withhold") — every site now defaults to release, matching the server, so a row
 *    the operator never touched is not an outstanding question. Withholding is the
 *    exceptional act and the only one that must be said.
 *
 * What survives is the client's own assurance rule: a row ``needsAcknowledgment``
 * being released still needs its row tick. This one derivation feeds both places
 * the surface offers to confirm from (the stage and the report modal's footer) —
 * never two lists.
 *
 * ``termsAccepted`` defaults ``true`` so every EXISTING caller (this module's own
 * tests, written before the terms step existed) keeps its prior behavior; the
 * container passes the real checkbox state.
 */
export function confirmBlockers(
  assurance: AssuranceView,
  dispositions: DispositionMap,
  acknowledged: readonly number[],
  termsAccepted = true,
): readonly string[] {
  const blockers: string[] = [];
  if (!termsAccepted) {
    blockers.push("the terms — read and accept them before confirming");
  }
  const acked = new Set(acknowledged);
  for (const site of assurance.sites) {
    // an untouched row needing acknowledgment is headed for release (the
    // default), so the demand shows immediately — withholding it is what
    // makes the demand go away
    if (ackRequired(site, dispositions[site.tooth]) && !acked.has(site.tooth)) {
      blockers.push(
        `tooth ${site.tooth} ${acknowledgmentReason(site)} — releasing it ` +
          `needs its own acknowledgment`,
      );
    }
  }
  return blockers;
}

/**
 * WHETHER A ROW OFFERS THE WITHHOLD CONTROL AT ALL (client 2026-07-27 #4: the
 * release/withhold pair was friction on single-site cases — 7 of 9). Only a row
 * ``needsAcknowledgment`` can plausibly be held back, so only such a row renders
 * the control; a clean row is released, and says so quietly instead of asking a
 * question with one sane answer. The server agrees by construction: an omitted
 * disposition IS release.
 */
export function withholdOffered(site: AssuranceSite): boolean {
  return needsAcknowledgment(site);
}

/** What a row's disposition actually IS: the operator's act, else release — the
 * server's own default, resolved here too so the surface never shows "undecided"
 * for a state that is not undecided. */
export function effectiveDisposition(
  site: AssuranceSite,
  dispositions: DispositionMap,
): Disposition {
  return dispositions[site.tooth] ?? "release";
}

/** Whether a row renders (and demands) its acknowledgment tick: it
 * ``needsAcknowledgment``, and is not explicitly withheld — withholding drops
 * the release, so there is nothing to acknowledge. */
export function ackRequired(
  site: AssuranceSite,
  disposition: Disposition | undefined,
): boolean {
  return needsAcknowledgment(site) && disposition !== "withhold";
}

/** The acts, wire-shaped: dispositions keyed tooth-as-string (JSON object keys),
 * plus the terms acceptance (plan §10-A) — required, like the payment stub's
 * ``authorize``. */
export function confirmWireBody(
  dispositions: DispositionMap,
  acknowledged: readonly number[],
  termsAccepted: boolean,
): ConfirmBody {
  const wire: Record<string, Disposition> = {};
  for (const [tooth, act] of Object.entries(dispositions)) {
    wire[tooth] = act;
  }
  return {
    dispositions: wire,
    acknowledged_flags: [...acknowledged],
    terms_accepted: termsAccepted,
  };
}

// --- the terms (plan §10-A) -------------------------------------------------------------
//
// Client, verbatim: "Delivery should be confirm and accept alginment and term and
// conditions, payment, and released artifacts." The agreement moves OFF Declare's
// per-site ticks onto this one commercial signature.
//
// THE TEXT BELOW IS A PLACEHOLDER, matching bff/resources/deliver.py's
// ``TERMS_TEXT_PLACEHOLDER`` in spirit (not byte-for-byte — this copy owns its own
// rendering; the server never inspects the text, only a boolean). It is NOT
// contractual language this codebase is entitled to invent: the real terms are the
// client's to supply. DeliverStage.tsx renders this inside an unmissable
// "PLACEHOLDER" banner so nobody mistakes it for the real thing on screen either.
// Swapping it for the client's real text is a ONE-STRING change.

/** The terms text, naming the case's own site count the way the plan's own
 * placeholder sentence does ("I have reviewed the alignment for all N sites"). */
export function termsText(siteCount: number): string {
  return (
    `I have reviewed the alignment for all ${siteCount} site` +
    `${siteCount === 1 ? "" : "s"} in this case, including the assurance report ` +
    `and its QC images. I accept the alignment as shown and authorize release ` +
    `of the deliverables.`
  );
}

// --- the invoice, FORMATTED (gap ``invoice-on-the-surfaces``, 2026-07-31) -------------
//
// TWO RULES HOLD THIS SECTION HONEST, and they are the money-shaped twins of AM-4's
// "every verdict is the BFF's":
//
//  1. FORMAT, NEVER COMPUTE. `orderTotal` renders `total_cents`; nothing here sums a
//     line, compares an amount, or applies a rate. An amount the browser arrived at is
//     the money-shaped cousin of a client-asserted verdict — and `postPayment` still
//     carries `{authorize: true}` and nothing else, so a number invented here could
//     only ever mislead the reader, which is worse, not better.
//  2. THE PLACEHOLDER STAYS. `status` is the SERVER's word for "these rates are not
//     the client's yet"; the surface badges it and prints `note` verbatim. A total
//     that looks like a quotation when it is not is worse than no total at all.

/**
 * A server amount SPLIT into the parts it is printed with — integer arithmetic over
 * cents the BFF sent, never arithmetic that produces a new amount.
 *
 * Deliberately not `Intl.NumberFormat`: it is locale-dependent, and a figure that
 * reads $48.00 for one operator and 48,00 $ for another is a receipt two people
 * cannot compare. An unknown currency prints its ISO code rather than borrowing a
 * symbol it has no right to.
 */
export function formatMoney(cents: number, currency: string): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const whole = Math.trunc(abs / 100);
  const part = String(abs % 100).padStart(2, "0");
  return currency === "USD"
    ? `${sign}$${whole}.${part}`
    : `${sign}${whole}.${part} ${currency}`;
}

/** One order row, ready to render. */
export interface OrderLine {
  readonly key: string;
  readonly label: string;
  /** The line's own amount, or "not billed" — see `InvoiceLine.billed`. */
  readonly amount: string;
  /** The per-unit rate where the server priced one; null otherwise. */
  readonly unit: string | null;
  readonly billed: boolean;
}

/**
 * The served lines, in the SERVED order, each carrying the server's own amount.
 *
 * An unbilled line reads "not billed" rather than "$0.00": `billed` is not
 * `amount_cents === 0` (a rush turnaround is included at zero and IS billed — it
 * repriced every site above), and collapsing the two would tell an operator that
 * withholding a site was free when what happened is that it was never charged for.
 */
export function orderLines(invoice: InvoiceView): readonly OrderLine[] {
  return invoice.lines.map((line) => ({
    key: line.key,
    label: line.label,
    amount: line.billed
      ? formatMoney(line.amount_cents, invoice.currency)
      : "not billed",
    unit:
      line.unit_amount_cents !== null
        ? `${formatMoney(line.unit_amount_cents, invoice.currency)} each`
        : null,
    billed: line.billed,
  }));
}

/** The total — `total_cents` rendered, NEVER the sum of the lines above it. */
export function orderTotal(invoice: InvoiceView): string {
  return formatMoney(invoice.total_cents, invoice.currency);
}

/** Whether the rates are still the prototype's — the SERVER's own word, not a guess
 *  from whether the figures look round. */
export function invoiceIsPlaceholder(invoice: InvoiceView): boolean {
  return invoice.status === "placeholder";
}

/** The turnaround line, with WHERE the word came from — the `EffectiveChoiceView`
 *  vocabulary the Intake chips already use, so "default" reads the same everywhere. */
export function turnaroundWords(invoice: InvoiceView): string {
  const word = invoice.turnaround;
  const head = `${word.charAt(0).toUpperCase()}${word.slice(1)} turnaround`;
  return invoice.turnaround_source === "chosen"
    ? `${head} — chosen for this case.`
    : `${head} — the standing default.`;
}

/**
 * WHAT WAS ACTUALLY CHARGED, once a payment record exists — beside, never instead of,
 * the current price. The two can legitimately differ: a turnaround change after
 * payment reprices the case going forward, and rewriting the receipt to match would
 * forge it. A record persisted before amounts were kept says so rather than printing
 * a $0.00 nobody was charged.
 */
export function receiptWords(paid: InvoicePaymentView | null): string | null {
  if (paid === null) return null;
  if (paid.amount_cents === null) {
    return `Authorized at ${paid.at} — no amount was recorded with this payment.`;
  }
  const amount = formatMoney(paid.amount_cents, paid.currency ?? "USD");
  const how = [
    paid.turnaround !== null ? `${paid.turnaround} turnaround` : null,
    paid.rate_card_version !== null ? `rate card ${paid.rate_card_version}` : null,
  ].filter((piece): piece is string => piece !== null);
  const under = how.length > 0 ? ` under ${how.join(", ")}` : "";
  return `Charged ${amount} at ${paid.at}${under}.`;
}

/** The pay button, priced (design payLabel, flow.dc.html:1481-1482). With no invoice
 *  it says nothing about money — a button that names a price it does not have is the
 *  one thing worse than an unpriced button. */
export function payButtonLabel(invoice: InvoiceView | null, busy: boolean): string {
  if (busy) return "Authorizing (demo)…";
  return invoice !== null ? `Pay ${orderTotal(invoice)} (demo)` : "Pay (demo)";
}

// --- the attestation's enumeration (gap ``clinical-responsibility-attestation``) ------
//
// The signed sentence named a SITE COUNT and nothing else — never the sites released
// under acknowledgment, never the withheld. The three counts below are the BFF's:
// `derive_invoice` classifies every site with `_needs_acknowledgment`, the very
// predicate the confirm gate stands on, against the STANDING confirmation's own
// dispositions. So once a confirmation exists this sentence enumerates exactly what
// was sealed, and the checkout can echo it read-only.
//
// WHAT IS DONE HERE IS A LOOKUP, NOT ARITHMETIC: each count is one server-sent
// `quantity`, keyed by the line the server itself keyed. A line the server omitted is
// zero because the server's own rule is that a line appears only when it has
// something in it (bff/pricing.price_invoice) — that convention is read, not inferred.

export interface AttestationCounts {
  readonly released: number;
  readonly exceptions: number;
  readonly withheld: number;
}

function lineQuantity(invoice: InvoiceView, key: string): number {
  return invoice.lines.find((line) => line.key === key)?.quantity ?? 0;
}

export function attestationCounts(invoice: InvoiceView): AttestationCounts {
  return {
    released: lineQuantity(invoice, "released_sites"),
    exceptions: lineQuantity(invoice, "exception_sites"),
    withheld: lineQuantity(invoice, "withheld_sites"),
  };
}

/**
 * THE SENTENCE THE OPERATOR SIGNS, enumerated (design clinicalLabel,
 * flow.dc.html:1409-1414).
 *
 * The design puts this checkbox INSIDE the pay modal; the product does not, and the
 * product wins: here the acceptance is bound to CONFIRM, where it rides into the
 * evidence hash with its `terms_version` — strictly stronger than a tick beside a
 * card. The checkout echoes the sealed sentence read-only instead.
 *
 * The wording's constant clauses live in the BFF's Clinical Responsibility Statement
 * (`CLINICAL_VERSION` — a resolvable document, incorporated by the terms); this is
 * the case-specific enumeration of it, and every number in it is a server-derived
 * count. Where the invoice has not arrived, the sentence falls back to the site-count
 * text rather than claiming "0 constructions".
 */
export function attestationText(
  invoice: InvoiceView | null,
  siteCount: number,
): string {
  if (invoice === null) return termsText(siteCount);
  const { released, exceptions, withheld } = attestationCounts(invoice);
  const shipped = released + exceptions;
  const head =
    `I confirm the alignment metrics shown for this case are the ones I reviewed, ` +
    `and I accept clinical responsibility for releasing ${shipped} ` +
    `construction${shipped === 1 ? "" : "s"}`;
  const exceptionClause =
    exceptions > 0
      ? `, including ${exceptions} as ` +
        `${exceptions === 1 ? "an acknowledged exception" : "acknowledged exceptions"}`
      : "";
  const withheldClause =
    withheld > 0
      ? ` ${withheld} withheld site${withheld === 1 ? "" : "s"} ` +
        `${withheld === 1 ? "stays" : "stay"} open: nothing is disclosed for ` +
        `${withheld === 1 ? "it" : "them"} and ` +
        `${withheld === 1 ? "it remains" : "they remain"} mine to resolve.`
      : "";
  return `${head}${exceptionClause}.${withheldClause}`;
}

/**
 * WHY THE SENTENCE ABOVE CAN LAG THE OPERATOR'S PENDING ACTS, said out loud.
 *
 * The counts come from the server, and the server knows only the dispositions it has
 * been given — the standing confirmation's, or the all-release default. A withhold
 * ticked in the report but not yet confirmed is still only in this browser. Rather
 * than let the browser adjust the counts (that arithmetic is exactly what must stay
 * server-side), the surface states the fact: the sentence is re-derived against what
 * is actually confirmed, and the checkout echoes THAT.
 */
/**
 * THE CLINICAL STATEMENT'S VERSION, for the link only.
 *
 * It mirrors ``bff/resources/deliver.CLINICAL_VERSION``, and that duplication is
 * bounded on purpose: nothing here is ever SEALED with it. What a confirmation
 * records is the TERMS version the server chose, read back off the record
 * (`sealedTermsHref`); this constant only points a reader at the document the current
 * terms incorporate. A stale copy would 404 on a real document, which is loud —
 * unlike a stale copy that silently claimed a signature covered something it did not.
 */
export const CLINICAL_TERMS_VERSION = "clinical-responsibility-placeholder-v1";

export const ATTESTATION_PENDING_CAVEAT =
  "Withholding a site in the report removes it from this release. The statement " +
  "above is re-derived server-side against the dispositions actually confirmed, " +
  "and the checkout echoes the sealed wording.";

// --- the metrics the checkout restates (gap ``pay-modal-metric-signoff``) -------------

/** One site's line in the checkout's sign-off strip. */
export interface SignoffRow {
  readonly tooth: number;
  readonly variant: string;
  readonly deviation: string;
  /** The SESSION LADDER's rung, verbatim — the chip's word. */
  readonly status: string;
  /** The run's guidance level, verbatim — the second chip's word. */
  /** null when it would only repeat `status` — see `signoffRows`. */
  readonly gate: string | null;
  readonly flagged: boolean;
}

/**
 * THE NUMBERS THE MONEY IS BEING ASKED FOR (design payMetricRows,
 * flow.dc.html:1401-1408). The checkout asked for payment over a case id and a site
 * count; the deviations sat on the stage BEHIND the dialog, where a reader about to
 * pay could not see them.
 *
 * The design's chip word came from a client-side `deviation() <= tolerance`
 * comparison — "in tolerance" — and that is exactly what this product must never
 * render: every band comparison belongs to the acceptance catalog and is made
 * server-side, per metric. Both chips here are server WORDS carried verbatim (the
 * session ladder's rung, the run's guidance level), and the order is the BFF's served
 * order — this app never re-sorts evidence.
 */
export function signoffRows(assurance: AssuranceView): readonly SignoffRow[] {
  return assurance.sites.map((site) => ({
    tooth: site.tooth,
    variant: site.declared_variant ?? "no cap declared",
    deviation: mm(site.deviation_rms_mm),
    status: site.status ?? "unknown",
    // The gate level is a SECOND server word, not a restatement of the first: the
    // status is where the site stands in the ladder, the gate level is what the
    // run's acceptance catalog said about it. They usually agree — and when they
    // do, rendering both put a bare "ready ready" in front of someone about to
    // pay, which reads as a bug rather than as two facts (seen on screen
    // 2026-07-31). Null here means "the same word twice", and the surface drops
    // it. It survives only where it DIVERGES, which is the case worth the room.
    gate: site.gate.level === (site.status ?? "unknown") ? null : site.gate.level,
    flagged: site.status === "flagged",
  }));
}

/**
 * THE CASE-POLICY LINE (design toleranceLine, flow.dc.html:1415) — MINUS THE
 * TOLERANCE, for the reason `assuranceCountsWords` already states: there is no single
 * case tolerance in this product, and printing one would invent a case-wide threshold
 * nothing in the pipeline applies. What IS case-wide and server-derived is the relief
 * and the turnaround, each with the source the BFF attributed it to.
 */
export function casePolicyWords(choices: ChoicesView): string {
  const relief = choices.effective_relief.value;
  const reliefWords =
    relief !== null ? `relief ${relief.toFixed(2)} mm` : "relief not set";
  const turnaround = choices.effective_turnaround?.value ?? "standard";
  return `Case policy: ${reliefWords} · ${turnaround} turnaround.`;
}

/** The release button's named blockers — the chain's remaining steps, in order. */
export function releaseBlockers(
  session: Pick<SessionView, "confirmed" | "payment_authorized">,
): readonly string[] {
  const blockers: string[] = [];
  if (!session.confirmed) {
    blockers.push("the confirmation — confirm over the evidence first");
  }
  if (!session.payment_authorized) {
    blockers.push("the payment authorization (stub)");
  }
  return blockers;
}

/**
 * The BFF's evidence-drift 409 ("the case changed since it was confirmed —
 * re-confirm over the current evidence", and release's post-drift cousin): the one
 * refusal the surface answers with the RE-CONFIRM flow — reload the evidence and
 * ask the operator again — instead of a plain error banner.
 */
export function isEvidenceDrift409(result: ApiResult<unknown>): boolean {
  return (
    result.kind === "error" &&
    result.status === 409 &&
    (result.detail.includes("changed since it was confirmed") ||
      result.detail.includes("evidence changed after release"))
  );
}

// THE OPERATOR NAME STORE IS GONE (client 2026-07-27: "WE dont need operator name
// the checkmark is sufficient"). `loadOperator`/`saveOperator` kept a self-typed
// name in sessionStorage and rode it on every gating call as `X-Operator`. Behind
// no authentication that was never identity — the acts are the record now, and a
// real name arrives with real auth (plan §8 / phase-2).

// --- the stage's compact evidence (client 2026-07-27 #5) ------------------------------

/** One site's evidence as a single line — what the STAGE shows now that the full
 * table lives in a modal. */
export interface EvidenceLine {
  readonly tooth: number;
  readonly gate: string;
  readonly flagged: boolean;
  /** The facts, in the served order's own words — no verdict of ours. */
  readonly words: string;
  /**
   * THE ROW'S ONE SENTENCE OF WHY (design ref: assuranceRows[].note,
   * flow.dc.html:1385-1389). The gate's FIRST action, verbatim from the run
   * (``AssuranceGate.actions``) — never a phrase of ours, and never the design's
   * client-side reasonFor(), which built its sentence from a tolerance comparison
   * done in the browser. Where the run raised no action, the fallback states the
   * gate's own word and nothing more.
   */
  readonly note: string;
  /** True while ``note`` is the run's own sentence; false for the fallback. Rendered
   * as a data attribute so the distinction survives into the markup a reviewer reads. */
  readonly noteFromRun: boolean;
}

/** The gate's own sentence where it raised one; otherwise a statement about the
 * gate, carrying its level and asserting nothing the run did not. */
function evidenceNote(site: AssuranceSite): { note: string; fromRun: boolean } {
  const stated = site.gate.actions[0];
  if (stated !== undefined && stated.trim() !== "") {
    return { note: stated, fromRun: true };
  }
  return { note: `No action was raised — this gate reads ${site.gate.level}.`, fromRun: false };
}

function mm(value: number | null): string {
  return value !== null ? `${value.toFixed(2)} mm` : "—";
}

/**
 * THE STAGE'S SUMMARY (client 2026-07-27 #5: "The reports can be shown in a modal").
 * With the table behind a modal, the stage must still say enough that opening it is
 * a decision rather than a hunt: one line per site, worst-first in the BFF's SERVED
 * order (this app never re-sorts evidence), carrying the identity, the seat and the
 * deviation — the three numbers a reader scans for — beside the gate's own word.
 */
export function evidenceSummary(assurance: AssuranceView): readonly EvidenceLine[] {
  return assurance.sites.map((site) => {
    const why = evidenceNote(site);
    return {
      tooth: site.tooth,
      gate: site.gate.level,
      flagged: site.status === "flagged",
      words:
        `${site.declared_variant ?? "no cap declared"} · ` +
        `${site.seat_method ?? "seat not recorded"}, rim ${mm(site.rim_agreement_mm)} · ` +
        `RMS ${mm(site.deviation_rms_mm)} / p90 ${mm(site.deviation_p90_mm)}`,
      note: why.note,
      noteFromRun: why.fromRun,
    };
  });
}

// --- the assurance panel's own header (design assuranceNote, flow.dc.html:1376-1378) ---

/** One status word and how many SERVED rows carry it. */
export interface AssuranceCount {
  readonly status: string;
  readonly count: number;
}

/**
 * THE TABLE, TALLIED. Display arithmetic over statuses the BFF derived — this counts
 * rows, it never decides what a row is (AM-4). The order is the served order's own
 * first-appearance order, so a worst-first table reads "1 flagged / 1 ready" rather
 * than some alphabet of ours, and an unrecognised status word is counted BY ITS OWN
 * NAME: this app is not entitled to bucket a server word it has no phrasing for.
 */
export function assuranceCounts(assurance: AssuranceView): readonly AssuranceCount[] {
  const order: string[] = [];
  const tally = new Map<string, number>();
  for (const site of assurance.sites) {
    const word = site.status ?? "unknown";
    if (!tally.has(word)) order.push(word);
    tally.set(word, (tally.get(word) ?? 0) + 1);
  }
  return order.map((status) => ({ status, count: tally.get(status) ?? 0 }));
}

/**
 * The counts line the panel header carries. The phrasing is the WORKLIST'S
 * (worklist.rollupLabel: count, word, " / ") rather than a third vocabulary for the
 * same idea — an operator crossing from the worklist to Deliver reads one language.
 *
 * THE DESIGN'S TOLERANCE CLAUSE IS DELIBERATELY ABSENT (design 1376-1378 ends
 * "· tolerance 0.40 mm"). There is no single case tolerance in this product: every
 * band comparison belongs to the acceptance catalog and is made server-side, per
 * metric. Printing one number here would invent a case-wide threshold that nothing
 * in the pipeline actually applies.
 */
export function assuranceCountsWords(assurance: AssuranceView): string {
  const total = assurance.sites.length;
  const head = `${total} site${total === 1 ? "" : "s"}`;
  const counts = assuranceCounts(assurance);
  if (counts.length === 0) return head;
  return `${head} · ${counts.map((c) => `${c.count} ${c.status}`).join(" / ")}`;
}

/**
 * THE "EXCEPTIONS" LINE, AS THE PRODUCT'S OWN ACT. The design counts sites
 * "accepted as exceptions" as though acceptance were a status; here it is not — it is
 * the operator's per-row acknowledgment (AM-12), and the rows that need one are
 * ``needsAcknowledgment``'s, flagged or production-noted alike (plan §10-E). So the
 * header names the OBLIGATION rather than minting a fourth status word.
 *
 * IT READS THE DISPOSITIONS (audit 2026-07-31). Counting ``needsAcknowledgment``
 * alone made this header assert that sites the operator had explicitly WITHHELD
 * "release only as acknowledged exceptions" — contradicting, on the same screen, the
 * rows (which render no tick, ``ackRequired`` being false once withheld), the confirm
 * gate (which demands nothing for them), and the server's own ``derive_invoice``
 * (bff/resources/deliver.py:492-500 counts them ``withheld``, explicitly NOT
 * ``exceptions``). The whole content of withholding is that the site does not
 * release. So the count is ``ackRequired`` — the very predicate the rows and
 * ``confirmBlockers`` stand on — and the withheld are named as what they are.
 *
 * ``dispositions`` defaults to empty, which is the SERVER's default too (an omitted
 * disposition IS release), so a caller with none in hand reads exactly as before.
 */
export function acknowledgmentPolicyWords(
  assurance: AssuranceView,
  dispositions: DispositionMap = {},
): string {
  const owed = assurance.sites.filter((site) =>
    ackRequired(site, dispositions[site.tooth]),
  ).length;
  const held = assurance.sites.filter(
    (site) => needsAcknowledgment(site) && dispositions[site.tooth] === "withhold",
  ).length;
  const heldClause =
    held === 0
      ? ""
      : ` ${held} site${held === 1 ? " is" : "s are"} withheld — ` +
        `${held === 1 ? "it does" : "they do"} not release at all.`;
  if (owed === 0) {
    return held > 0
      ? `No site releases as an acknowledged exception.${heldClause}`
      : "No site needs an acknowledgment — every row here releases as it stands.";
  }
  const one = owed === 1;
  return (
    `${owed} site${one ? "" : "s"} release${one ? "s" : ""} only as ` +
    `${one ? "an acknowledged exception" : "acknowledged exceptions"} — the tick sits ` +
    `on the row in the report, and the acknowledgment rides in the confirmation.` +
    heldClause
  );
}

// --- what a reworked row's numbers still describe (review 2026-07-28, finding E) -------

/**
 * WHICH OF THIS ROW'S NUMBERS PREDATE THE OPERATOR'S REWORK, or null when none do.
 *
 * Adjust re-derives what it can over the new pose — the deviation scalars come off the
 * very payload the operator's panes are rendering — but the rim agreement was anchored
 * on the scan's own fitted rim circle and the guidance on a dozen run-time inputs, and
 * neither survives in the shipped record. Recomputing them on a different anchor would
 * put a different number under the same name; leaving them unlabelled let a re-derived
 * hash imply the whole table was current.
 *
 * So the row SAYS SO, and says what confirming does with them. The list is the BFF's
 * and the vocabulary is Adjust's (`staleMetricsPhrase`, where the rework happens); this
 * sentence is Deliver's own voice, because here the subject is a signature.
 */
export function staleMetricsWords(site: AssuranceSite): string | null {
  const named = staleMetricsPhrase(site.stale_metrics);
  if (named === null) return null;
  const one = site.stale_metrics.length === 1;
  return (
    `Reworked after the run — ${named} below still ${one ? "describes" : "describe"} ` +
    `the fit the run produced, not the one on this site now. Confirming seals ` +
    `${one ? "it" : "them"} as ${one ? "it stands" : "they stand"}.`
  );
}

/**
 * THE FORK, IN WORDS, WHERE THE CONFIRM IS (review 2026-07-28). The BFF folds the
 * Delivery-vs-Skip decision into the evidence hash, so a confirmation already covers
 * whether the fits were reworked or waved through — but a hash shows nobody
 * anything, and Deliver rendered the word nowhere. An operator opening the report to
 * decide whether to sign could not see the very fact their signature was about to
 * seal.
 *
 * The word is the BFF's (assurance.adjustments); the sentence is display. Declare's
 * own vocabulary is kept — "adjustments skipped" / "adjustments taken up" — so the
 * stage that recorded the act and the stage that seals it read the same. An unfaced
 * fork says exactly that: null is an answer, never a decision to be implied.
 */
export function adjustmentsWords(assurance: AssuranceView): string {
  const seal = "This is part of what confirming seals.";
  if (assurance.adjustments === "skip") {
    return `Adjustments skipped — the fits stand as the run produced them. ${seal}`;
  }
  if (assurance.adjustments === "adjust") {
    return `Adjustments taken up in Adjust. ${seal}`;
  }
  return `The Delivery-vs-Skip fork was never faced. ${seal}`;
}

// --- the delivery progression (client 2026-07-27 #6) ----------------------------------

export type StepState = "done" | "current" | "waiting";

/** One step of the visible Confirmed → Paid → Released progression. */
export interface ReleaseStep {
  readonly id: "confirmed" | "paid" | "released";
  readonly title: string;
  readonly state: StepState;
  /** done → its timestamp; current → what the act does; waiting → what it needs. */
  readonly detail: string;
}

/**
 * THE THREE STEPS, EACH SHOWING ITS OWN STATE (client 2026-07-27 #6: "Make sure we
 * have good UI for payment and release of information / artifacts"). Payment and
 * release used to be two stacked panels with no shared shape, so the operator could
 * not see where they were in the one progression that actually matters.
 *
 * Exactly one step is "current" — the first unfinished one — because a progression
 * with two live steps is a list, not a progression. Everything after it WAITS and
 * says what it is waiting for, so no step is ever inert without a reason.
 */
export function releaseSteps(
  session: Pick<SessionView, "confirmed" | "confirmation" | "payment_authorized" |
    "payment" | "released" | "release">,
): readonly ReleaseStep[] {
  const confirmed = session.confirmed && session.confirmation !== null;
  const paid = session.payment_authorized && session.payment !== null;
  const released = session.released && session.release !== null;
  return [
    {
      id: "confirmed",
      title: "Confirmed",
      state: confirmed ? "done" : "current",
      detail: confirmed
        ? `Sealed at ${session.confirmation!.at}`
        : "Read the report and confirm over the evidence as it stands.",
    },
    {
      id: "paid",
      title: "Paid",
      state: paid ? "done" : confirmed ? "current" : "waiting",
      detail: paid
        ? `Authorized at ${session.payment!.at} (${session.payment!.provider})`
        : confirmed
          ? "Authorize the (stub) payment for this case."
          : "Waiting for the confirmation.",
    },
    {
      id: "released",
      title: "Released",
      state: released ? "done" : paid ? "current" : "waiting",
      detail: released
        ? `Disclosed at ${session.release!.at}`
        : paid
          ? "Release the deliverables — the evidence is re-derived first."
          : confirmed
            ? "Waiting for the payment authorization."
            : "Waiting for the confirmation and the payment authorization.",
    },
  ];
}

/**
 * WHAT RELEASING WILL DISCLOSE, in sentences, BEFORE the act (client 2026-07-27 #6).
 * Every number here is the BFF's `release_preview` — derived through the artifact
 * gate's own file split, so this promise and that disclosure cannot diverge. A
 * withheld site is named with the fact that it STAYS OPEN: withholding is not a
 * deferral, it is a site left unfinished on purpose.
 */
export function releaseDisclosureWords(
  preview: SessionView["release_preview"],
): readonly string[] {
  if (preview === null) return [];
  const files = `${preview.file_count} file${preview.file_count === 1 ? "" : "s"}`;
  const teeth =
    preview.teeth.length > 0
      ? preview.teeth.map((t) => `tooth ${t}`).join(", ")
      : "no sites";
  const words = [`Releasing discloses ${files} for ${teeth}.`];
  for (const tooth of preview.withheld_teeth) {
    words.push(
      `Tooth ${tooth} is withheld — its files stay back and the site stays open.`,
    );
  }
  if (preview.withheld_case_file_count > 0) {
    words.push(
      `${preview.withheld_case_file_count} case-wide files stay back too: they ` +
        `aggregate every site, so they release only when every site does.`,
    );
  }
  return words;
}

// --- the closing statement, after the release (design releasedNote, :1510-1511) -------

/**
 * WHAT ACTUALLY SHIPPED, once it has. The progression's Released step states the
 * TIME; nothing on the surface stated the AMOUNT, so a case that finished never said
 * it had.
 *
 * Every number is counted off the ARTIFACTS RESPONSE — the gated list the release
 * actually served — and never off ``release_preview`` or any client-side expectation
 * of what should have shipped. Those two can legitimately differ: a withheld site's
 * files stay back, and the sentence has to describe the disclosure that happened.
 * Which is also why a withheld case is never called closed: it says which sites stay
 * open, because withholding is a site left unfinished on purpose, not a deferral.
 *
 * SERVED, NOT LISTED (audit 2026-07-31). The BFF deliberately lists a file it could
 * not find on disk with ``size_bytes: None`` — "a file the package claims but the run
 * directory no longer holds: an honest gap the operator can see, never a 0"
 * (bff/resources/deliver.py:1158-1170). Counting the LISTED rows folded that
 * disclosed gap straight back into a total and then called the run closed, from the
 * very page on which clicking that row 404s (``fetch_artifact``, :1230). So the count
 * is the served files, the gap is said out loud, and "closed" is refused whenever
 * anything is missing or nothing shipped at all — under-claiming here is the entire
 * reason this sentence exists.
 */
export function releasedClosingWords(artifacts: ArtifactsView): string {
  const served = artifacts.files.filter((f) => f.size_bytes !== null);
  const absent = artifacts.files.length - served.length;
  const withheld = artifacts.withheld_teeth;
  const closed = served.length > 0 && absent === 0;
  const openSites =
    withheld.length > 0
      ? `${withheld.length === 1 ? "Tooth" : "Teeth"} ${withheld.join(", ")} ` +
        `${withheld.length === 1 ? "stays" : "stay"} open and ` +
        `${withheld.length === 1 ? "its" : "their"} files stayed back`
      : null;
  const closing =
    openSites !== null
      ? closed
        ? `${openSites} — this run is closed for the sites that shipped.`
        : `${openSites}.`
      : closed
        ? "Nothing was withheld — this run is closed."
        : "Nothing was withheld.";
  const gap =
    absent > 0
      ? ` ${absent} listed file${absent === 1 ? "" : "s"} ` +
        `${absent === 1 ? "is" : "are"} no longer in the run directory — ` +
        `${absent === 1 ? "it" : "they"} cannot be downloaded from here.`
      : "";
  if (served.length === 0) return `No files were disclosed.${gap} ${closing}`;
  const teeth = new Set(served.filter((f) => f.tooth !== null).map((f) => f.tooth))
    .size;
  const caseWide = served.filter((f) => f.tooth === null).length;
  const aggregate =
    caseWide > 0
      ? `, including ${caseWide} case-wide file${caseWide === 1 ? "" : "s"}`
      : "";
  return (
    `Released ${served.length} file${served.length === 1 ? "" : "s"} for ${teeth} ` +
    `site${teeth === 1 ? "" : "s"}${aggregate}.${gap} ${closing}`
  );
}

// --- what paying is, said where paying starts (design payment modal; plan §10-A) ------

/**
 * THE FOOTNOTE UNDER THE CHECKOUT. A payment surface that names no agreement leaves
 * the operator to infer what the money does; this states the two facts that are
 * easiest to get wrong — the authorization is bound to THIS run, and it discloses
 * nothing by itself.
 *
 * It claims no NEW acceptance: the terms were accepted at the confirmation and are
 * sealed there with their version. Paying does not re-accept them, and this sentence
 * must never be read as a second signature.
 */
export const CHECKOUT_SEAL_WORDS =
  "Paying authorizes the (stub) payment for this run, under the terms already " +
  "accepted and sealed in this case's confirmation. It discloses nothing on its " +
  "own: releasing the artifacts is a separate act, back on this page.";

/**
 * WHERE THAT FOOTNOTE'S LINK POINTS: the version the standing confirmation SEALED,
 * so the document read beside the payment is the one this case is actually bound by
 * — not whatever /terms happens to serve after newer terms land. With nothing sealed
 * yet the current document is the only honest answer.
 */
export function sealedTermsHref(
  confirmation: Pick<ConfirmationView, "terms_version"> | null,
): string {
  const version = confirmation?.terms_version;
  return version != null && version !== ""
    ? `/terms/${encodeURIComponent(version)}`
    : "/terms";
}

// --- the artifacts, grouped by site (client 2026-07-27 #6) ----------------------------

/** One site's deliverables (or the case-wide set, tooth null). */
export interface ArtifactGroup {
  readonly tooth: number | null;
  readonly title: string;
  readonly files: readonly ArtifactFile[];
  readonly totalBytes: number;
}

/** Sizes a person reads. A missing size stays honestly unknown — never a "0 B". */
export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "size unknown — the file is missing from the run";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * GROUPED BY SITE, not one flat list (client 2026-07-27 #6). A six-site package is
 * thirty near-identical filenames differing by a number in the middle; grouped, the
 * operator reads "tooth 19: 3 files" and can check that against the case. The
 * server attributes each file (the artifact gate's anchored rule) — this only
 * buckets what it was told, in the package's own order, with case-wide files LAST
 * because they belong to no site and would otherwise head the list.
 */
export function groupArtifacts(
  files: readonly ArtifactFile[],
): readonly ArtifactGroup[] {
  const order: (number | null)[] = [];
  const buckets = new Map<number | null, ArtifactFile[]>();
  for (const file of files) {
    if (!buckets.has(file.tooth)) {
      buckets.set(file.tooth, []);
      order.push(file.tooth);
    }
    buckets.get(file.tooth)!.push(file);
  }
  const sites = order.filter((t): t is number => t !== null);
  const caseWide = order.includes(null) ? [null] : [];
  return [...sites, ...caseWide].map((tooth) => {
    const group = buckets.get(tooth) ?? [];
    return {
      tooth,
      title: tooth === null ? "Case-wide files" : `Tooth ${tooth}`,
      files: group,
      totalBytes: group.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0),
    };
  });
}
