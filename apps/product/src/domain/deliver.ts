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
import type { ApiResult, AssuranceSite, AssuranceView, ConfirmBody, SessionView } from "../api/client";

export type Disposition = "release" | "withhold";

/** The operator's per-row acts so far — keyed by tooth (number, UI-side). */
export type DispositionMap = Readonly<Record<number, Disposition>>;

/**
 * Everything still standing between the operator and a confirmable table, in the
 * order the surface lists it: each row without a disposition (table order — worst
 * first, exactly as served), then each flagged row dispositioned release without
 * its own acknowledgment (AM-12: row by row, never in bulk).
 *
 * THE ACTOR'S NAME USED TO LEAD THIS LIST. It is gone (client 2026-07-27: "WE dont
 * need operator name the checkmark is sufficient") — an unauthenticated self-typed
 * name blocked the button while proving nothing. Deliberate; do not restore it.
 */
export function confirmBlockers(
  assurance: AssuranceView,
  dispositions: DispositionMap,
  acknowledged: readonly number[],
): readonly string[] {
  const blockers: string[] = [];
  for (const site of assurance.sites) {
    if (dispositions[site.tooth] === undefined) {
      blockers.push(`tooth ${site.tooth} needs a disposition — release or withhold`);
    }
  }
  const acked = new Set(acknowledged);
  for (const site of assurance.sites) {
    // an undecided flagged row is still headed for the acknowledgment unless the
    // operator withholds it — showing the demand early beats a surprise later
    if (ackRequired(site, dispositions[site.tooth]) && !acked.has(site.tooth)) {
      blockers.push(
        `tooth ${site.tooth} is flagged — releasing it needs its own acknowledgment`,
      );
    }
  }
  return blockers;
}

/** Whether a row renders (and demands) its acknowledgment tick: flagged, and not
 * explicitly withheld — withholding drops the release, so there is nothing to
 * acknowledge. */
export function ackRequired(
  site: AssuranceSite,
  disposition: Disposition | undefined,
): boolean {
  return site.status === "flagged" && disposition !== "withhold";
}

/** The acts, wire-shaped: dispositions keyed tooth-as-string (JSON object keys). */
export function confirmWireBody(
  dispositions: DispositionMap,
  acknowledged: readonly number[],
): ConfirmBody {
  const wire: Record<string, Disposition> = {};
  for (const [tooth, act] of Object.entries(dispositions)) {
    wire[tooth] = act;
  }
  return { dispositions: wire, acknowledged_flags: [...acknowledged] };
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
