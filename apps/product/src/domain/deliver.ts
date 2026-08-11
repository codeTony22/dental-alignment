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
    // the EFFECTIVE disposition, never the raw map lookup: a site dropped at
    // Adjust is headed for withhold, and demanding an acknowledgment for a
    // release that is not going to happen is a question about nothing
    if (
      ackRequired(site, effectiveDisposition(site, dispositions)) &&
      !acked.has(site.tooth)
    ) {
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
 * release/withhold pair was friction on single-site cases — 7 of 9). A row
 * ``needsAcknowledgment`` can plausibly be held back, so it renders the control; a
 * clean row that is going to release says so quietly instead of asking a question
 * with one sane answer.
 *
 * AND A ROW ALREADY HEADED FOR WITHHOLD OFFERS IT TOO (audit 2026-07-31), because
 * the alternative was a one-way door: a clean site dropped at Adjust rendered the
 * literal word "released" — the control being gated on ``needsAcknowledgment``
 * alone — while confirming from that screen withheld it and every case-wide file
 * with it, and there was no way back short of navigating to Adjust. The rule is
 * therefore stated over the EFFECTIVE disposition, not over the flag: any row this
 * screen is about to withhold must be reversible on this screen.
 */
export function withholdOffered(
  site: AssuranceSite,
  dispositions: DispositionMap = {},
): boolean {
  return (
    needsAcknowledgment(site) ||
    effectiveDisposition(site, dispositions) === "withhold"
  );
}

/**
 * WHAT A ROW'S DISPOSITION ACTUALLY IS — the one resolution this app makes, and it
 * mirrors ``confirm_case``'s own precedence line exactly: the operator's act on this
 * screen, else the DRAFT the server carries for the site (a cap dropped at Adjust —
 * ``AssuranceSite.withhold_intent``), else release.
 *
 * The draft link is the whole fix for the 2026-07-31 coherence finding. The server
 * resolved omissions against it — the invoice priced it, the attestation counted it,
 * the confirmation sealed it — while this function resolved them straight to
 * "release", so one screen said "released" about a site the very next click
 * withheld. Reading the server's own field here means the surface and the seal
 * resolve the same map from the same inputs. It is still not a client-side verdict:
 * a disposition says what the OPERATOR does with a site, never what the site IS, and
 * the server re-resolves and re-judges every one of these on confirm.
 */
export function effectiveDisposition(
  site: AssuranceSite,
  dispositions: DispositionMap,
): Disposition {
  return (
    dispositions[site.tooth] ?? (site.withhold_intent === true ? "withhold" : "release")
  );
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
/** WHAT A RECEIPT LOOKS LIKE, whichever record it came off. The invoice's `paid`
 *  block and the session's own `payment` carry the same five facts under the same
 *  names, and the paid step reads the session's directly — the invoice block it used
 *  to read vanishes with the "Paid" step the moment payment lands. Structural rather
 *  than a union so a third carrier needs no change here. */
export interface PaidRecordLike {
  readonly amount_cents?: number | null;
  readonly currency?: string | null;
  readonly rate_card_version?: string | null;
  readonly turnaround?: string | null;
  readonly at: string;
}

export function receiptWords(paid: PaidRecordLike | null): string | null {
  if (paid === null) return null;
  if (paid.amount_cents == null) {
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

/*
 * CORRECTED 2026-07-31. It read "against the dispositions actually confirmed", and
 * that is false the whole time it matters most: with NO confirmation standing,
 * ``_billing_dispositions`` takes its DRAFT branch and prices the caps dropped at
 * Adjust (bff/resources/deliver.py) — so the counts above already describe drops
 * nobody has signed. Naming only the confirmed half told a reader the sentence was
 * lagging when it was in fact current, which is the wrong direction to be wrong in
 * on the screen that signs.
 */
export const ATTESTATION_PENDING_CAVEAT =
  "Withholding a site removes it from this release. The statement above is " +
  "re-derived server-side — against the standing confirmation's dispositions once " +
  "there is one, and against the caps already dropped before that — so a withhold " +
  "ticked here and not yet confirmed is the one thing still only in this browser. " +
  "The checkout echoes the sealed wording.";

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
  /**
   * Whether this row is one the confirm gate makes the operator acknowledge —
   * ``needsAcknowledgment``, NOT ``status === "flagged"`` (audit 2026-07-31). The
   * two diverge on exactly the row that most needs the emphasis: a shared-part
   * conflict leaves the ladder rung at "ready" while the BFF pins the row first,
   * demands its acknowledgment and bills it at HALF rate, so the checkout rendered
   * "Site 19 · ready" with no emphasis over an Order line reading "1 acknowledged
   * exception, at half rate" that no row on screen could be attributed to.
   */
  readonly flagged: boolean;
  /**
   * THE THIRD FACT, and the missing one: the worker's shared-construction-part
   * sentence, verbatim (``AssuranceSite.production_note``). It is the whole reason
   * such a row is an exception; dropping it left the discount unattributable.
   */
  readonly productionNote: string | null;
  /** What this site's money actually does — the same resolution the stage, the
   *  confirm gate and the server's own invoice split stand on. */
  readonly disposition: Disposition;
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
export function signoffRows(
  assurance: AssuranceView,
  dispositions: DispositionMap = {},
): readonly SignoffRow[] {
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
    // the predicate the rest of this module, the BFF's confirm gate and
    // `derive_invoice` all stand on — see `SignoffRow.flagged`
    flagged: needsAcknowledgment(site),
    productionNote: site.production_note,
    disposition: effectiveDisposition(site, dispositions),
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

/**
 * THE THREE MAIN ARTIFACTS, PREVIEWED ON THE PAGE (client 2026-08-01: "we need to
 * show the 3 main artifacts as a preview in the Deliver Page, below the open full
 * report button").
 *
 * The run writes three QC images per site — the alignment proof, the clock view and
 * the deviation map — and until now they lived only inside the report modal, one
 * click and one scroll away from the surface that asks for a signature over them.
 * This projects the assurance's own `qc_images` list into labelled preview cards,
 * in the assurance's worst-first site order, verbatim.
 *
 * The FILENAME is always the server's — nothing here constructs one. Only the human
 * label is derived, from the suffix the worker's own writer uses; a name the
 * labeller does not recognise keeps the server's name whole rather than guessing a
 * prettier one.
 */
export interface QcPreview {
  readonly tooth: number;
  readonly filename: string;
  readonly label: string;
}

const QC_LABELS: readonly { readonly suffix: string; readonly label: string }[] = [
  { suffix: "-alignment-proof.png", label: "Alignment proof" },
  { suffix: "-clockview.png", label: "Clock view" },
  { suffix: "-deviation.png", label: "Deviation map" },
];

export function qcPreviews(assurance: AssuranceView): readonly QcPreview[] {
  return assurance.sites.flatMap((site) =>
    site.qc_images.map((filename) => ({
      tooth: site.tooth,
      filename,
      label:
        QC_LABELS.find((row) => filename.endsWith(row.suffix))?.label ?? filename,
    })),
  );
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
  /**
   * WHAT CONFIRMING DOES WITH THIS SITE (audit 2026-07-31). The stage's confirm
   * button sits on this same panel, and a site dropped at Adjust appeared in this
   * list as an unremarkable line — so the surface the operator actually reads before
   * signing named every fact about the site except the one the signature decides.
   * Resolved by ``effectiveDisposition``, like every other disposition on the two
   * Deliver surfaces.
   */
  readonly disposition: Disposition;
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
export function evidenceSummary(
  assurance: AssuranceView,
  dispositions: DispositionMap = {},
): readonly EvidenceLine[] {
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
      disposition: effectiveDisposition(site, dispositions),
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
 * THE SERVED TOLERANCE BANDS (§10-AB.2, client 2026-08-02: "Do this — a displayed
 * tolerance number … as a server-derived band"). The comp prints "tolerance 0.12 mm"
 * from a prop; this product's honest equivalent is the CATALOG bands every assurance
 * row already carries (`references[*].bands` — cited numbers, served per site). The
 * line reads the first row (the bands are the catalog's constants, identical across
 * rows), names pass and review edges per metric, and carries the one disclaimer that
 * keeps it honest: verdicts are the run's own guidance, not a band check made here —
 * a row can sit inside every band and still be flagged (an unverified rotation), or
 * outside one and read ready. Null when nothing served carries bands: the line is
 * absent rather than defaulted, like every other absent fact on this surface.
 */
const _BANDED_METRICS = ["rim_agreement_mm", "deviation_rms_mm"] as const;

export function toleranceBandsWords(
  sites: readonly AssuranceSite[],
): string | null {
  const references = sites[0]?.references;
  if (references === undefined) return null;
  const parts: string[] = [];
  for (const key of _BANDED_METRICS) {
    const ref = references[key];
    const bands = ref?.bands;
    if (ref === undefined || bands === null || bands === undefined) continue;
    parts.push(
      `${ref.label} pass ≤ ${bands.pass.toFixed(2)} ${ref.unit} · ` +
        `review ≤ ${bands.review.toFixed(2)} ${ref.unit}`,
    );
  }
  if (parts.length === 0) return null;
  return (
    `Tolerance bands (served): ${parts.join(" — ")}. ` +
    "Verdicts are the run's own guidance, not a band check made here."
  );
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
    ackRequired(site, effectiveDisposition(site, dispositions)),
  ).length;
  // EVERY withheld site, not only the flagged ones (audit 2026-07-31): a clean cap
  // dropped at Adjust does not release either, and a header reading "every row here
  // releases as it stands" over one is the same lie the row itself used to tell
  const held = assurance.sites.filter(
    (site) => effectiveDisposition(site, dispositions) === "withhold",
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
    // "since the automation's own fit", not "after the run" — since §10-AG the
    // rework can be the run's own evidence RE-APPLY, which happens inside the
    // run after automation; both lanes' stale numbers describe the automation's
    // fit, and "after the run" was false on one of them (review 2026-08-04)
    `Reworked since the automation's own fit — ${named} below still ` +
    `${one ? "describes" : "describe"} that fit, not the one standing on this ` +
    `site now. Confirming seals ${one ? "it" : "them"} as ` +
    `${one ? "it stands" : "they stand"}.`
  );
}

/**
 * WHETHER THIS ROW'S FIT HAD ANYTHING TO CHECK IT (defect cap6020-neodent-gm,
 * 2026-08-01), on the document the signature covers.
 *
 * A fit-by-points built from ONE observation is exactly determined for rotation: that
 * single delta IS the answer and its residual is zero by construction. A real case's
 * activity log reads "run completed — verdicts written for 1 site, none flagged" at
 * 14:32:30 and "fit by 1 point pair(s) → 1 observation(s): rotated −50.9° … marks agree
 * to 0.000mm RMS" at 14:32:52; the site left at 0.451mm RMS / 0.745mm p90. The 0.000mm
 * was arithmetic, and nothing on this table said so.
 *
 * THE SERVER'S OWN WORD, NOT A COUNT COMPARED HERE. `observations` is on the wire and
 * the shortcut would be `observations === 1` — but "is this number a measurement?" is a
 * judgment about evidence, and this app makes none of those (AM-4). `cross_checked` is
 * derived in `bff/resources/deliver._correspondence_view` from the count the same block
 * states, and sealed with it. `null` is a row that cannot say, and it says nothing.
 */
export function crossCheckWords(site: AssuranceSite): string | null {
  if (site.correspondence?.cross_checked !== false) return null;
  return (
    "This fit stands on a single observation — the rotation is fixed exactly by one " +
    "mark, so there is nothing to cross-check it against and the fit has no " +
    "agreement number. A legitimate fit where the automatic reader had no evidence, " +
    "and one no residual can vouch for. Confirming seals it as it stands."
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

// --- the construction step, moved into Deliver (client 2026-08-01: "we also forgot
// the selection of the construction, and we need to put the construction library
// after the Confirmation in the Delivery step") ----------------------------------------
//
// STRUCTURAL FACT (application/run.py ~155): ``construction_path`` is a REQUIRED run
// input — one run aligns, bores the CHOSEN construction and emits the whole package.
// Changing it after a run exists is truthfully a RE-PROCESS, never a same-evidence
// edit: the choices PUT fires the existing reset boundary (``clear_current_run``),
// and whatever this screen would otherwise be signing over stops describing anything
// once the run it was measured against is gone. The words below say so BEFORE the
// PUT — the visible-reset doctrine ``declare.switchWords``/``intake.remarkWords``
// already carry, applied a third time to the one choice Deliver itself can change.

/** One picker row — the same shape Intake's own catalog reader
 * (``domain/intake.constructionOptions``) now serves; this module reuses it rather
 * than reading ``detail.catalog.constructions`` a second way. */
export interface ConstructionOption {
  readonly path_id: string;
  readonly label: string;
  readonly vendor: string;
  /** The catalog row's own SERVED url (BFF `GET /api/constructions/{vendor}/
   *  {filename}/mesh`) — this app never assembles it (the same posture
   *  `declare.variantMeshUrl` states for cap variants). Optional/nullable: a row
   *  from an older BFF that predates the route (CLAUDE.md's stale-server trap)
   *  is still a valid option to PICK, just not one this app can preview alone. */
  readonly mesh_url?: string | null;
}

export interface ConstructionGroup {
  readonly vendor: string;
  readonly options: readonly ConstructionOption[];
}

/**
 * THE PICKER'S OPTIONS, GROUPED BY VENDOR — display grouping over Intake's own rows,
 * in the vendor order those rows already arrive in (the catalog's own directory
 * listing order; this module invents no ordering of its own).
 */
export function constructionGroups(
  options: readonly ConstructionOption[],
): readonly ConstructionGroup[] {
  const order: string[] = [];
  const buckets = new Map<string, ConstructionOption[]>();
  for (const option of options) {
    if (!buckets.has(option.vendor)) {
      buckets.set(option.vendor, []);
      order.push(option.vendor);
    }
    buckets.get(option.vendor)!.push(option);
  }
  return order.map((vendor) => ({ vendor, options: buckets.get(vendor) ?? [] }));
}

export interface ConstructionStepInfo {
  readonly pathId: string | null;
  readonly label: string;
  readonly vendor: string | null;
  /** The BFF's own attribution (``ChoicesView.effective_construction.source``) —
   *  "suggested" wears the tag exactly like every other effective-choice chip on
   *  Intake; this module never decides suggestedness by comparing values itself. */
  readonly suggested: boolean;
}

/**
 * THE EFFECTIVE CONSTRUCTION, for the step's summary line — the BFF's own value and
 * attribution (never re-derived), resolved against the SAME options list the picker
 * offers so the label and vendor read like the picker's own rows, never a bare
 * ``vendor/file.stl`` path id.
 */
export function constructionStepWords(
  choices: ChoicesView,
  options: readonly ConstructionOption[],
): ConstructionStepInfo {
  const effective = choices.effective_construction;
  if (effective.value === null) {
    return {
      pathId: null,
      label: "No construction part chosen yet",
      vendor: null,
      suggested: false,
    };
  }
  const match = options.find((o) => o.path_id === effective.value);
  const label = match?.label ?? effective.value;
  const vendor = match?.vendor ?? null;
  return {
    pathId: effective.value,
    label,
    // The catalog labels a part VENDOR-FIRST ("dess — neodent-gm-scanbody"), so
    // repeating the vendor beside it reads as a stutter rather than as provenance
    // ("dess — neodent-gm-scanbody · dess", seen on screen 2026-08-01). Kept where
    // the label does NOT name it, because there the vendor is the missing fact.
    vendor: vendor !== null && !label.includes(vendor) ? vendor : null,
    suggested: effective.source === "suggested",
  };
}

/**
 * WHETHER A CHANGE HERE WOULD RETIRE ANYTHING (the checkbox-over-nothing doctrine —
 * ``intake.remarkRetiresSomething``'s sibling, applied to this third door). A case
 * with no run at all yet has nothing beyond the ORDINARY choices-change reset every
 * case-level choice already causes — asking for extra consent over zero extra
 * consequence would be the same empty confirmation AM-8 already forbids for a system
 * switch declared before anything was declared.
 */
export function constructionChangeRetiresSomething(
  session: Pick<SessionView, "run_state">,
): boolean {
  return session.run_state !== "none";
}

/**
 * THE BLAST RADIUS, IN WORDS, BEFORE THE PUT (the visible-reset doctrine —
 * ``declare.switchWords``/``intake.remarkWords``, mirrored a third time). Names the
 * candidate's own label, the way ``switchWords`` names the target system, and states
 * the confirmation clause only when one is actually standing to fall — a case never
 * confirmed has nothing there to lose, and saying otherwise would be exactly the
 * false consequence this doctrine exists to keep out of a reset warning.
 */
export function constructionChangeWords(
  label: string,
  confirmed: boolean,
  runDone = false,
): string {
  /* THE RE-EMIT TRUTH (§10-AC): over a DONE run, a part change re-emits the
     package from the run's own poses — the pose is construction-independent
     (measured), so the fits the operator reviewed stand and nothing re-aligns.
     The disclosure-before-act rule is unchanged; the disclosed consequence
     SHRANK with the behaviour, and the one new consequence is stated: the
     design gate judges the new (part × cap) pairing and can refuse. Without a
     done run the old full-reset truth still applies, and the old words stay. */
  if (runDone) {
    const consequence = confirmed
      ? "the standing confirmation falls — you confirm again over the " +
        "re-emitted evidence"
      : "the design gate judges the new pairing and can refuse — a refusal " +
        "lands as a refused run, with its words";
    return (
      `Changing the construction part to ${label} re-emits the package from ` +
      `the run's own poses — the fits stand, nothing re-aligns, and ` +
      `${consequence}.`
    );
  }
  const consequence = confirmed
    ? "the standing confirmation falls — you confirm again over the new evidence"
    : "every site's preview and review resets — Declare confirms them again before " +
      "a new run can fire";
  return (
    `Changing the construction part to ${label} re-processes the case: a new run ` +
    `re-bores and re-renders everything, and ${consequence}.`
  );
}

// --- the four 3D preview tabs (client 2026-08-01: "we also have the previews of
// the artifacts" — the demo's three labelled tabs; a fourth added 2026-08-06,
// §10-AO) --------------------------------------------------------------------------
//
// The demo composited these client-side from raw scan + per-part STLs
// (apps/web/src/components/ViewerControls.tsx). This product's worker bakes merged
// meshes (auto_flow.py: `arch-with-healingcaps.stl`, `arch-with-constructions.stl`)
// AND the pieces they were merged from (`arch-capless.stl`, `{tooth}-healingcap-
// aligned.stl`, `{tooth}-scanbody-<vendor>.stl`). A merged mesh is ONE colour, which
// painted the whole scan green (client 2026-08-06) — so a tab's scene LAYERS the
// pieces when the package carries them, each tinted its own role, and falls back to
// the merged mesh in the arch material when it does not (an older run). Every layer
// is still a filename MATCH against the worker's own export names — nothing here
// invents geometry or re-parses a name for attribution.
//
// TAB 4, "Arch alone" (client 2026-08-06, §10-AO): the capless arch — the scan with
// the cap's seat cut, no healing cap, no construction — invents no new geometry
// either; `arch-capless.stl` is already tabs 1/2's own composite base and already
// in `package_files`. It is its own tab because "the arch with its seats cut and
// nothing sitting in them" is a fact worth seeing on its own, not just as scaffolding
// under the other two composites.

/** The tinting role a preview layer renders with — the viewer package's own
 *  PartRole values, carried by NAME rather than imported: this module stays
 *  framework-free (no dependency on the three.js-backed viewer package), and the
 *  caller indexes its own palette with the string. */
export type PreviewMeshRole = "arch" | "cap" | "construction" | "socket";

/** One mesh of a tab's scene, with the role that colours it. */
export interface PreviewLayer {
  readonly filename: string;
  readonly role: PreviewMeshRole;
}

export interface PreviewTab {
  readonly key: string;
  readonly label: string;
  /** The tab's PRIMARY file — its identity for keying and for single-mesh
   *  consumers; always layers[0]'s file for a merged tab. */
  readonly filename: string;
  readonly tooth: number | null;
  /** THE SCENE (client 2026-08-06: "why is the scan green? … only the healing cap
   *  is green"): the arch tabs compose the package's own pieces — the capless arch
   *  in the scan material with each posed part tinted its role — and fall back to
   *  the merged mesh painted as the arch it mostly is when the pieces are absent
   *  (an older run). */
  readonly layers: readonly PreviewLayer[];
}

const ALIGNMENT_SUFFIX = "-arch-with-healingcaps.stl";
const CONSTRUCTION_ARCH_SUFFIX = "-arch-with-constructions.stl";
const CONSTRUCTION_SUFFIX = "-prosthesis_cad.stl";
const CAPLESS_SUFFIX = "-arch-capless.stl";
// the full-depth socket variant (client 2026-08-09) — floor at the implant's top
const PLATFORM_SUFFIX = "-arch-platform.stl";

/**
 * THE FOUR TABS, MATCHED BY SUFFIX, NEVER CONSTRUCTED: each candidate is the
 * worker's own fixed tail (auto_flow.py/output_package.py's exact export names),
 * matched against the run's OWN ``package_files`` list — the same suffix-matching
 * discipline ``qcPreviews`` already applies to the QC images. A tab whose file the
 * package does not carry is simply ABSENT (an honest gap, never a disabled button):
 * an older run, or one with no constructions built yet, renders fewer tabs rather
 * than a broken one.
 *
 * ``teeth`` drives tab 3 ONLY — one per site that actually has its own construction
 * file, in the CALLER's order (the assurance's own worst-first order, so these tabs
 * read in the same order as the table above them). Nothing here parses a tooth
 * number back OUT of a filename (this app never re-parses a filename to attribute
 * it); the teeth are named by the caller and only checked for membership.
 *
 * TAB 4 ("Arch alone", §10-AO) is the same ``capless`` file tabs 1/2 already
 * resolved above, ordered LAST (after every per-tooth tab 3) per the client's own
 * 1-2-3-4 numbering — the scan with the cap's seat cut, no healing cap, no
 * construction: one layer, the arch role, nothing composed on top of it.
 */
export function previewTabs(
  packageFiles: readonly string[],
  teeth: readonly number[],
): readonly PreviewTab[] {
  const tabs: PreviewTab[] = [];
  // the composite base both arch tabs share — the scan with clean holes where the
  // parts sit, so the part layers never fight the triangles underneath them
  const capless = packageFiles.find((f) => f.endsWith(CAPLESS_SUFFIX));
  // THE TINTED SOCKET (client 2026-08-09 night: "can't see depth at all"):
  // when the run wrote the socket as its own layer beside the socketless
  // arch, tabs 4/5 compose them so the CUT surface reads against the gum —
  // the downloads keep the merged solids the lab expects. Old packages
  // (no layer files) keep the merged single-layer render.
  const socketless = packageFiles.find((f) =>
    f.endsWith("-arch-socketless.stl"),
  );
  const socketDish = packageFiles.find((f) => f.endsWith("-socket-dish.stl"));
  const socketPlatform = packageFiles.find((f) =>
    f.endsWith("-socket-platform.stl"),
  );
  const composed = (
    merged: string,
    parts: readonly string[],
    role: PreviewMeshRole,
  ): readonly PreviewLayer[] =>
    capless !== undefined && parts.length > 0
      ? [{ filename: capless, role: "arch" as const },
         ...parts.map((filename) => ({ filename, role }))]
      : [{ filename: merged, role: "arch" as const }];
  const alignment = packageFiles.find((f) => f.endsWith(ALIGNMENT_SUFFIX));
  if (alignment !== undefined) {
    const caps = teeth.flatMap((tooth) => {
      const file = packageFiles.find((f) =>
        f.endsWith(`-${tooth}-healingcap-aligned.stl`));
      return file === undefined ? [] : [file];
    });
    tabs.push({
      key: "alignment",
      label: "1 · Healing-cap alignment",
      filename: alignment,
      tooth: null,
      layers: composed(alignment, caps, "cap"),
    });
  }
  const archConstruction = packageFiles.find((f) => f.endsWith(CONSTRUCTION_ARCH_SUFFIX));
  if (archConstruction !== undefined) {
    // the posed construction's tail carries the vendor (`-{tooth}-scanbody-<vendor>
    // .stl`, emit.py's own naming), so the tooth anchors an INFIX here — the same
    // membership discipline, hyphen-bounded so 19 never speaks for 9
    const constructions = teeth.flatMap((tooth) => {
      const file = packageFiles.find((f) =>
        f.includes(`-${tooth}-scanbody-`) && f.endsWith(".stl"));
      return file === undefined ? [] : [file];
    });
    tabs.push({
      key: "construction-in-arch",
      label: "2 · Construction in arch",
      filename: archConstruction,
      tooth: null,
      layers: composed(archConstruction, constructions, "construction"),
    });
  }
  for (const tooth of teeth) {
    const file = packageFiles.find((f) => f.endsWith(`-${tooth}${CONSTRUCTION_SUFFIX}`));
    if (file === undefined) continue;
    tabs.push({
      key: `construction-tooth-${tooth}`,
      label: `3 · Construction alone — tooth ${tooth}`,
      filename: file,
      tooth,
      layers: [{ filename: file, role: "construction" }],
    });
  }
  // TAB 4, LAST (§10-AO): the scan with the cap's seat cut — no healing cap, no
  // construction. The same `capless` file resolved above; absent exactly when tabs
  // 1/2 already fell back to their merged mesh for the same reason.
  if (capless !== undefined) {
    tabs.push({
      key: "arch-alone",
      label: "4 · Arch alone",
      filename: capless,
      tooth: null,
      layers:
        socketless !== undefined && socketDish !== undefined
          ? [
              { filename: socketless, role: "arch" },
              { filename: socketDish, role: "socket" },
            ]
          : [{ filename: capless, role: "arch" }],
    });
  }
  // THE FIFTH TAB (client 2026-08-09: the platform-level floor, "do the
  // envelope walls"): the same socket at FULL depth — walls down to the cap's
  // offset base, the implant's top space. Served as its own package file; tab 4
  // stays the shallow visible dish. Absent on packages emitted before the
  // artifact existed — a tab must never point at a file the run did not write.
  const platform = packageFiles.find((f) => f.endsWith(PLATFORM_SUFFIX));
  if (platform !== undefined) {
    tabs.push({
      key: "arch-platform",
      label: "5 · Arch — platform",
      filename: platform,
      tooth: null,
      layers:
        socketless !== undefined && socketPlatform !== undefined
          ? [
              { filename: socketless, role: "arch" },
              { filename: socketPlatform, role: "socket" },
            ]
          : [{ filename: platform, role: "arch" }],
    });
  }
  // ARTIFACT 6 RETURNS (client 2026-08-11: "we lose the artifact 6 we had
  // before") — §10-AS.19's retirement reversed by the client's own ask; the
  // open-arch doctrine still governs tabs 1-5. Appears exactly when the run
  // built it.
  const modelClosed = packageFiles.find((f) => f.endsWith("-model-closed.stl"));
  if (modelClosed !== undefined) {
    tabs.push({
      key: "model-closed",
      label: "6 · Closed model",
      filename: modelClosed,
      tooth: null,
      layers: [{ filename: modelClosed, role: "arch" }],
    });
  }
  return tabs;
}

// --- the preview's per-layer visibility toggle (client 2026-08-09: "a tool like the
// panels to hide certain parts of the library, construction, or scan" — PRESENTATION
// ONLY. Read the caution twice: this is the same 3D preview the download bundle's own
// files are named after, and a toggle that fed anything back into what gets fetched,
// downloaded or listed would let the surface manufacture an artifact nobody ran. It
// changes what the operator SEES, never what shipped, so it lives entirely in the
// component's own view-local state; these two functions are its only domain logic,
// pure so the exclusion is pinned without a WebGL viewer. -----------------------------

/** ONE ROW PER DISTINCT ROLE a tab's layers carry, in first-appearance order — never
 * one row per FILE. A composite tab can carry several same-role files (one healing-cap
 * mesh per site on tab 1, one construction mesh per site on tab 2); grouping them under
 * one row is what makes "hide the caps" one click rather than one per tooth, and
 * matches the client's own words ("hide certain parts of the library, construction, or
 * scan" — three things, not N).
 */
export function previewLayerRows(tab: PreviewTab): readonly PreviewLayerRow[] {
  const order: PreviewMeshRole[] = [];
  const buckets = new Map<PreviewMeshRole, string[]>();
  for (const layer of tab.layers) {
    if (!buckets.has(layer.role)) {
      buckets.set(layer.role, []);
      order.push(layer.role);
    }
    buckets.get(layer.role)!.push(layer.filename);
  }
  return order.map((role) => ({ role, filenames: buckets.get(role) ?? [] }));
}

/** One toggle row — the role it stands for, and every file it groups (display need
 *  only ever asks "how many", but the filenames are kept rather than a count so a
 *  future caller never has to re-derive them from the tab). */
export interface PreviewLayerRow {
  readonly role: PreviewMeshRole;
  readonly filenames: readonly string[];
}

/**
 * THE SCENE'S OWN LAYER LIST, given what the operator hid — a hidden ROLE is dropped
 * entirely from the build, not merely dimmed: a layer excluded here never reaches
 * `VerifyViewer`, so there is nothing partial about "hidden" for this panel to get
 * wrong. Nothing else changes: the container still loads every file's bytes exactly as
 * it did before this existed (`meshes` stays keyed to `tab.layers`'s own order), so
 * re-showing a role is instant — the fetch already happened.
 */
export function visiblePreviewLayers(
  tab: PreviewTab,
  hiddenRoles: ReadonlySet<PreviewMeshRole>,
): readonly PreviewLayer[] {
  return tab.layers.filter((layer) => !hiddenRoles.has(layer.role));
}

/* --- THE CONSTRUCTION LIBRARY AS ITS OWN PAGE (client 2026-08-01) ------------------
 *
 * The client's flow makes the construction choice a page between Adjustment and
 * Delivery. The OPTIONS are the catalog's (`intake.constructionOptions`) and the
 * effective value is the BFF's (`constructionStepInfo`) — this adds only the page's
 * own words, so there is no fourth copy of the part list anywhere.
 */

export function libraryNote(chosen: boolean): string {
  return chosen
    ? "Delivery cuts this part for every site that ships."
    : "Pick the part Delivery should cut for this case.";
}

export function libraryForwardLabel(chosen: boolean): string {
  return chosen ? "Continue to Delivery" : "Pick a construction part first";
}

/**
 * WHY THE PREVIEW PANEL SAYS NOTHING YET.
 *
 * The client asked for "preview of the boolean with the construction and the scan
 * unified in a view". The design comp appears to answer it and does not: its preview
 * is a static CSS disc with no data bindings at all — it does not read the chosen
 * part, the scan, the run or any geometry, and it wears the SCAN CAP's own palette, so
 * it depicts the cap rather than a union. Porting it would ship a control that looks
 * like an answer and is not, which is the silent no-op this codebase forbids
 * everywhere else (the chordal-span note's precedent).
 *
 * The real thing needs a mesh the BFF does not serve today: `library.py` serves a
 * catalog part alone, and the only unified geometry that exists is the RUN's own baked
 * `-arch-with-constructions.stl`, which is emitted after this page rather than before
 * it. So the panel states the gap rather than dressing it.
 */
/**
 * THE UNIFIED VIEW THE CLIENT ASKED FOR, where one already exists.
 *
 * "Preview of the boolean with the construction and the scan unified in a view" — and
 * the run has already built exactly that: `-arch-with-constructions.stl` is the arch
 * with every site's construction part posed into it. The library page is only reachable
 * over a DONE run (`flow.isReachable`), so on this page that file is on disk and the
 * existing preview-mesh route already serves it. No new worker code, no new geometry.
 *
 * ONE TAB, not three. Deliver shows the cap arch, the construction arch and the
 * per-site parts because Deliver is reviewing everything that ships. This page is
 * asking one question — what does the construction look like ON the scan — so the cap
 * arch (the scan WITHOUT constructions) and the prosthesis (the part WITHOUT the scan)
 * are both off-topic here.
 *
 * ABSENT rather than broken when the run carried no such file, the same discipline
 * `previewTabs` already applies: an older run renders no preview rather than a dead one.
 */
export function libraryPreviewTab(
  packageFiles: readonly string[],
): PreviewTab | null {
  return previewTabs(packageFiles, []).find(
    (tab) => tab.key === "construction-in-arch",
  ) ?? null;
}

/**
 * WHOSE PART THE PREVIEW IS SHOWING. It is the RUN's — the part the emitted mesh was
 * built with — which is not necessarily the one the operator is hovering over. Saying
 * so is the difference between a preview and a promise: picking a different part
 * cannot change this image until the case re-runs, and a surface that let the operator
 * believe otherwise would be claiming geometry nobody computed.
 */
export function libraryPreviewCaption(label: string): string {
  return (
    `This is the run's own unified mesh, built with ${label}. Choosing a different ` +
    `part cannot change it until the case is re-run.`
  );
}

/** Deliver's acknowledgment checkboxes, PRE-FILLED from the drafts given on
 * Adjustment (client 2026-08-02). A union, never a replacement: a row the operator
 * already ticked HERE stays ticked, and a draft only ever adds. Withdrawal happens
 * where the operator is looking — untick here, or withdraw on Adjust before
 * arriving. The confirmation's own gate is untouched; this fills a form. */
export function prefillAcknowledged(
  sites: ReadonlyArray<{ readonly tooth: number; readonly exception_acknowledged?: boolean }>,
  current: readonly number[],
): readonly number[] {
  const drafted = sites
    .filter((s) => s.exception_acknowledged === true)
    .map((s) => s.tooth);
  return [...new Set([...current, ...drafted])].sort((a, b) => a - b);
}

export function libraryPreviewPending(): string {
  return (
    "The unified construction-and-scan preview is not built yet — the only unified " +
    "mesh that exists today is the one the run bakes after this step. What you pick " +
    "here is what Delivery cuts."
  );
}

/* --- THE UNRUN CANDIDATE'S OWN PREVIEW (§10-M2 "the natural next slice", client
 * ruling 2026-08-02) ------------------------------------------------------------
 *
 * §10-M2 answered "what does the construction look like ON the scan" for a run
 * that already exists. It named, and left open, the harder case: previewing a
 * part the case has NOT run at all — there is no baked union, and there will not
 * be one until a run fires with this part chosen. `library.py`'s construction
 * route serves the vendor's catalog mesh alone (unposed, in its own local frame),
 * which is real geometry and a real improvement over hunting blind through a
 * flat picklist — but it is not the union, and saying so is the whole point.
 */

/**
 * WHOSE MESH THE ARMED CANDIDATE'S PREVIEW IS SHOWING — the SAME caption doctrine
 * as `libraryPreviewCaption` above (§10-M2: a preview must never imply geometry
 * nobody computed), applied to a part that has not been run at all rather than
 * one a run already baked. This mesh is the VENDOR'S CATALOG PART ALONE: not
 * cut, not seated, not measured against any site in this case. A caption that
 * let the operator read this as the union, or as THIS site's own construction,
 * would be exactly the over-claim the run-mesh caption already refuses.
 */
export function libraryPartPreviewCaption(label: string): string {
  return (
    `This is ${label} — the vendor's catalog part alone, in its own frame. It is ` +
    `not yet cut, seated, or measured for any site in this case.`
  );
}

// --- THE ANALYSIS DIGEST (client 2026-08-09: "on the open-full-report, a tool that
// I can copy to the clipboard automatically and feed the case and the report to the
// LLM, to make the code better and to understand what happened with each case").
// Pure composition of SERVED facts — every sentence verbatim, every number the
// row's own; nothing here measures or judges. ---------------------------------------

function _num(v: number | null | undefined, unit = "mm"): string {
  return v === null || v === undefined ? "n/a" : `${v} ${unit}`;
}

function _siteBlock(site: AssuranceSite): string {
  const lines: string[] = [];
  lines.push(`### Tooth ${site.tooth} — ${site.status ?? "no status"}`);
  lines.push(
    `- cap: declared ${site.declared_variant ?? "n/a"} · identified ` +
      `${site.identified_variant ?? "n/a"} · agreement ` +
      `${site.variant_agreement ?? "n/a"}`,
  );
  lines.push(
    `- seat: ${site.seat_method ?? "n/a"} · rim agreement ` +
      `${_num(site.rim_agreement_mm)}`,
  );
  const rotBits = Object.entries(
    (site.rotation ?? {}) as unknown as Record<string, unknown>,
  )
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${String(v)}`);
  if (rotBits.length > 0) lines.push(`- rotation: ${rotBits.join(" · ")}`);
  lines.push(
    `- deviation: RMS ${_num(site.deviation_rms_mm)} · p90 ` +
      `${_num(site.deviation_p90_mm)}`,
  );
  lines.push(`- gate (${site.gate.level}${site.gate.stale ? ", STALE" : ""}):`);
  for (const action of site.gate.actions) lines.push(`  > ${action}`);
  if (site.clamp.clamped && site.clamp.reason !== null) {
    lines.push(`- relief clamp: ${site.clamp.reason}`);
  } else {
    lines.push(
      `- relief: requested ${_num(site.clamp.requested_mm)} · applied ` +
        `${_num(site.clamp.applied_mm)}`,
    );
  }
  if (site.production_note !== null) {
    lines.push(`- production note: ${site.production_note}`);
  }
  if (site.stale_metrics.length > 0) {
    lines.push(`- stale after rework: ${site.stale_metrics.join(", ")}`);
  }
  for (const ref of Object.values(site.references ?? {})) {
    lines.push(
      `- reference ${ref.label}: ${ref.display ?? String(ref.value)} ` +
        `(band ${ref.band}; vs ${ref.industry_ref.value} — ` +
        `${ref.industry_ref.source})`,
    );
  }
  return lines.join("\n");
}

/**
 * The paste-ready case digest for an outside reviewer (human or LLM): case and run
 * identity, the fork, then every site's served facts worst-first, all sentences
 * verbatim. Ends with the questions the client actually asks of it.
 */
export function analysisClipboardText(
  caseId: string,
  doctor: string,
  jaw: string | null,
  assurance: AssuranceView,
  extras?: {
    /** the package's artifact names, when the listing has loaded */
    readonly files?: readonly string[];
    /** the standing confirmation seal, when one exists */
    readonly confirmation?: {
      readonly at: string;
      readonly evidence_sha256: string;
      readonly terms_version?: string | null;
    } | null;
    /** the served detection record — the scan's own measured numbers (client
     *  2026-08-10: "enough data, math information for the LLM to make an
     *  opinion of what is wrong with that current alignment run") */
    readonly detection?: {
      readonly jaw_reading?: string | null;
      readonly site_measured_height_mm?: Record<string, number | null>;
      readonly site_proposed_variant?: Record<string, string | null>;
    } | null;
    /** the served case log — every act with its receipt, oldest first */
    readonly activity?: {
      readonly entries: readonly {
        readonly at: string;
        readonly event: string;
        readonly tooth: number | null;
        readonly detail: string;
      }[];
    } | null;
  },
): string {
  const head = [
    `# Case analysis digest — ${caseId}`,
    `run ${assurance.run_id} · doctor ${doctor}` +
      (jaw !== null ? ` · ${jaw} jaw` : ""),
    `adjust fork: ${assurance.adjustments ?? "never faced"}`,
    "",
    "## Sites (served worst-first)",
  ];
  const blocks = assurance.sites.map(_siteBlock);
  // THE RELIEF BLOCK, VERBATIM (client 2026-08-09: "expose all of these
  // information") — the served gingival_relief record carries the clamp story
  // and the by-tooth trail exactly as the run recorded them.
  const reliefLines: string[] = [];
  const relief = assurance.relief;
  if (relief !== null && Object.keys(relief).length > 0) {
    reliefLines.push("", "## Relief (served record, verbatim)");
    for (const [key, value] of Object.entries(relief)) {
      reliefLines.push(
        `- ${key}: ${
          typeof value === "object" && value !== null
            ? JSON.stringify(value)
            : String(value)
        }`,
      );
    }
  }
  const fileLines: string[] = [];
  if (extras?.files !== undefined && extras.files.length > 0) {
    fileLines.push("", "## Package files");
    for (const name of extras.files) fileLines.push(`- ${name}`);
  }
  const sealLines: string[] = [];
  if (extras?.confirmation != null) {
    sealLines.push(
      "",
      "## Confirmation seal",
      `sealed at ${extras.confirmation.at}`,
      `evidence ${extras.confirmation.evidence_sha256}` +
        (extras.confirmation.terms_version != null
          ? ` · terms ${extras.confirmation.terms_version}`
          : ""),
    );
  }
  // THE MATH FOR THE REVIEWER (client 2026-08-10): the detection record's own
  // measured numbers and the case log's receipts — the raw material an outside
  // reviewer diagnoses an alignment from, not just the verdicts.
  const detectionLines: string[] = [];
  const detection = extras?.detection;
  if (detection != null) {
    detectionLines.push("", "## Detection (served record)");
    if (detection.jaw_reading != null) {
      detectionLines.push(`- jaw reading: ${detection.jaw_reading}`);
    }
    const heights = detection.site_measured_height_mm ?? {};
    const proposals = detection.site_proposed_variant ?? {};
    for (const tooth of Object.keys(heights)) {
      const h = heights[tooth];
      const p = proposals[tooth];
      detectionLines.push(
        `- tooth ${tooth}: measured cap height ${
          h != null ? `${h} mm` : "not measured"
        } · measured-variant proposal ${p ?? "none"}`,
      );
    }
    if (detectionLines.length === 1) detectionLines.length = 0;
  }
  const logLines: string[] = [];
  const entries = extras?.activity?.entries ?? [];
  if (entries.length > 0) {
    logLines.push("", "## Case log (served acts, oldest first)");
    for (const e of entries) {
      logLines.push(
        `- ${e.at} ${e.event}${e.tooth !== null ? ` · tooth ${e.tooth}` : ""}: ${e.detail}`,
      );
    }
  }
  const tail = [
    "",
    "## For the reviewer",
    "Every sentence above is the system's own served wording; every number is",
    "the run's own measurement. Useful questions: which gate actions repeat",
    "across cases; whether rim/RMS/p90 sit near their band edges; whether a",
    "clamp or production note explains an operator complaint; what the rotation",
    "evidence kind was when a fit needed rework. Read the case log oldest-first",
    "for the causal chain — each tool act carries its own residual receipt.",
  ];
  return [
    ...head, ...blocks, ...reliefLines, ...detectionLines, ...logLines,
    ...fileLines, ...sealLines, ...tail,
  ].join("\n");
}

/**
 * THE LIBRARY PREVIEW'S FRAME (client 2026-08-10: "Construction page should do
 * the same — looking at the top of the construction site"). The run's unified
 * construction-in-arch mesh framed AT the sites rather than the whole arch: the
 * centroid of the served site centres, widened by their spread so every site
 * stays in frame, looking down the occlusal read. Frame-shaped exactly like the
 * workspace panes' (declare.PaneFrame), because it feeds the same viewer prop.
 * No valid centre → null → the viewer's whole-mesh fit stands, never a guess;
 * a missing occlusal read leaves the direction null the same way.
 */
export function constructionSiteFrame(
  centers: readonly (readonly number[] | null)[],
  occlusal: readonly [number, number, number] | null,
  bandMm: number,
): {
  readonly center: readonly [number, number, number];
  readonly radiusMm: number;
  readonly viewDirection: readonly [number, number, number] | null;
  readonly up: null;
} | null {
  const valid = centers.filter(
    (c): c is readonly [number, number, number] =>
      c !== null && c.length === 3 && c.every((v) => Number.isFinite(v)),
  );
  if (valid.length === 0) return null;
  const centre: [number, number, number] = [
    valid.reduce((s, c) => s + c[0], 0) / valid.length,
    valid.reduce((s, c) => s + c[1], 0) / valid.length,
    valid.reduce((s, c) => s + c[2], 0) / valid.length,
  ];
  const spread = Math.max(
    ...valid.map((c) =>
      Math.hypot(c[0] - centre[0], c[1] - centre[1], c[2] - centre[2]),
    ),
  );
  return {
    center: centre,
    radiusMm: bandMm + spread,
    viewDirection: occlusal,
    up: null,
  };
}
