/**
 * THE RUN GATE — the ONE place a process route is allowed to start from.
 *
 * Client requirement (their own review disclaimer, quoted in VerifyDialog):
 * "The OK button will be enabled only after all sites have been reviewed."
 *
 * The verifier found three ways to reach Process with ZERO sites reviewed — step 4's primary
 * "Run automation", the "⟳ rerun live" button, and Confirm All's recompute — because each route
 * carried its own hand-rolled enabled-expression and only the DIALOG's button consulted
 * `processBlockers`. Copies of a gate drift; this module removes the copies.
 *
 * HOW THE BYPASS IS CLOSED, structurally rather than by discipline:
 *
 *   `runAutomation()` (api/client) no longer accepts a plain selection object. It accepts an
 *   `AuthorizedRunSelection`, whose brand is a module-private `unique symbol` — the ONLY value
 *   of that type in the app is the one `authorizeRun()` mints, and `authorizeRun` mints one only
 *   when every blocker is clear. A new route that tries to POST a run without passing the gate
 *   does not "silently regress": it fails `pnpm typecheck`.
 *
 * WHY REVIEW-EVERYWHERE (design decision, option (a) of the brief) rather than a compact inline
 * acknowledgment on the quick path (option (b)): the sentence the operator signs is "the library
 * part selected MATCHES THE CORRESPONDING SCAN DATA". That is a comparison, and the only place
 * this app puts that comparison in front of a human is the three-panel verify (library part /
 * scanned cap / deviation union). A checkbox on step 4 with no panels behind it would satisfy the
 * words and defeat the purpose — a rubber stamp is not a review. So every route requires the
 * per-site reviewed state, the dialog is where reviewing happens, and step 4's job is to say so
 * out loud ("3 sites not yet reviewed") with the review route one obvious click away.
 *
 * The reviews are NOT re-demanded for a re-run: `LibrarySelection` already drops a site's review
 * when the part under it changes (system, construction, jaw, relief, that site's cap). Editing
 * MARKS re-seats the same reviewed product, so a recompute after re-marking still passes — the
 * gate blocks unreviewed PRODUCT choices, not honest re-computation.
 *
 * Framework-free and pure, like every other domain module here.
 */
import type { Jaw } from "./types";
import type { LibrarySelection } from "./librarySelection";
import { processBlockers, unreviewedSiteNumbers } from "./librarySelection";

/** Module-private brand. Not exported, and never constructed anywhere but `authorizeRun`. */
declare const RUN_AUTHORIZED: unique symbol;

/**
 * A run selection that HAS PASSED THE GATE. Structurally identical to what the wire needs, plus a
 * brand no other module can produce — so "did this route check the acknowledgment?" is answered
 * by the type checker rather than by reading every call site.
 */
export interface AuthorizedRunSelection {
  readonly model: string;
  readonly constructionPathId: string;
  readonly jaw: Jaw;
  readonly gingivalOffsetMm: number;
  readonly [RUN_AUTHORIZED]: true;
}

/** Everything the gate judges: the operator's library selection, plus the step-3 row problem the
 *  selection itself cannot see (two rows claiming the same tooth). */
export interface RunGateInput {
  readonly selection: LibrarySelection;
  readonly duplicateTeeth: readonly number[];
}

export type RunAuthorization =
  | { readonly ok: true; readonly selection: AuthorizedRunSelection }
  | { readonly ok: false; readonly blockers: readonly string[]; readonly reason: string };

/** Where reviewing actually happens — named identically in the toast, the step-4 line and the
 *  disabled-button tooltip, so the operator is always pointed at the same door. */
export const REVIEW_ROUTE_LABEL = "Verify & process";

export const REVIEW_ROUTE_HINT =
  `Open “${REVIEW_ROUTE_LABEL}” to compare each site's library part against the scan and tick its review.`;

/**
 * Every reason a run is refused, in the operator's own language: duplicate teeth first (a step-3
 * problem that makes the rest meaningless), then the selection's own blockers — missing system,
 * missing construction, missing per-site cap, invalid relief, and finally the unreviewed sites.
 * Empty = the run may go.
 */
export function runBlockers({ selection, duplicateTeeth }: RunGateInput): string[] {
  const blockers: string[] = [];
  if (duplicateTeeth.length > 0) {
    blockers.push(
      `one tooth number per site (tooth ${duplicateTeeth.join(", ")} used more than once)`,
    );
  }
  blockers.push(...processBlockers(selection));
  return blockers;
}

export function canRun(input: RunGateInput): boolean {
  return runBlockers(input).length === 0;
}

/** "3 sites not yet reviewed" / "1 site not yet reviewed" — the disabled reason the brief asks
 *  to be VISIBLE rather than a silently dead button. null once every site is reviewed. */
export function unreviewedNotice(selection: LibrarySelection): string | null {
  const unreviewed = unreviewedSiteNumbers(selection);
  if (unreviewed.length === 0) return null;
  return `${unreviewed.length} site${unreviewed.length > 1 ? "s" : ""} not yet reviewed`;
}

/** "2 of 3 sites reviewed" — the running acknowledgment state, shown whether or not
 *  it currently blocks, so the operator can see the gate move as they work through the sites. */
export function reviewProgressText(selection: LibrarySelection): string | null {
  const total = selection.sites.length;
  if (total === 0) return null;
  const reviewed = total - unreviewedSiteNumbers(selection).length;
  return `${reviewed} of ${total} site${total > 1 ? "s" : ""} reviewed`;
}

/** The one sentence a refused route shows (toast on the quick path). Names every blocker, and
 *  points at the review route whenever an unticked acknowledgment is one of them. */
export function refusalSentence(input: RunGateInput): string {
  const blockers = runBlockers(input);
  if (blockers.length === 0) return "";
  const needsReview = unreviewedSiteNumbers(input.selection).length > 0;
  return (
    `Cannot process yet — still needed: ${blockers.join("; ")}.` + (needsReview ? ` ${REVIEW_ROUTE_HINT}` : "")
  );
}

/**
 * THE GATE. Returns the branded selection a run request can be built from, or the refusal with
 * its reasons. Every process route — step 4's Run automation, ⟳ rerun live, Confirm All's
 * recompute, and the dialog's OK · Process — goes through this one function.
 */
export function authorizeRun(input: RunGateInput): RunAuthorization {
  const blockers = runBlockers(input);
  if (blockers.length > 0) {
    return { ok: false, blockers, reason: refusalSentence(input) };
  }
  const { selection } = input;
  // Non-null by construction: `runBlockers` lists "the implant system"/"the construction part"
  // whenever either is null, so a clear blocker list means both are chosen. The cast is the ONE
  // place the brand is minted — deliberately visible, and unreachable without the check above.
  return {
    ok: true,
    selection: {
      model: selection.model as string,
      constructionPathId: selection.constructionPathId as string,
      jaw: selection.jaw,
      gingivalOffsetMm: selection.gingivalOffsetMm,
    } as AuthorizedRunSelection,
  };
}
