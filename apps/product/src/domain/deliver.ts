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
  AssuranceSite,
  AssuranceView,
  ConfirmBody,
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
  return assurance.sites.map((site) => ({
    tooth: site.tooth,
    gate: site.gate.level,
    flagged: site.status === "flagged",
    words:
      `${site.declared_variant ?? "no cap declared"} · ` +
      `${site.seat_method ?? "seat not recorded"}, rim ${mm(site.rim_agreement_mm)} · ` +
      `RMS ${mm(site.deviation_rms_mm)} / p90 ${mm(site.deviation_p90_mm)}`,
  }));
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
