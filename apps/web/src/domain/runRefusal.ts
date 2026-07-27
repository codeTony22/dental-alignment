/**
 * THE HARD-FAIL PATH, MADE READABLE.
 *
 * The client hit this exactly (2026-07-25): the export gate refused to ship a part whose screw
 * channel the relief had eaten, and the UI showed them the transport failure. The refusal itself
 * is CORRECT and stays — a lab must not receive a part with no wall around its channel. What was
 * wrong is that it read as an unexplained error at the end of a long run.
 *
 * This module turns whatever the transport produced into three things an operator can act on:
 *
 *   TITLE     — what happened, in one clause ("nothing was shippable").
 *   DETAIL    — the SERVER'S OWN SENTENCE, verbatim. It names the tooth, the part, the measured
 *               channel radius and the number that was asked for; nothing here paraphrases it.
 *   NEXT STEP — what to change, and where.
 *
 * `serverSentence` exists because a refusal can arrive two ways: unwrapped (the client's
 * `throwServerDetail` already pulled FastAPI's `detail` out) or still wrapped in the generic
 * "Running automation failed (409 Conflict): {json}" form when the body was not the `detail`
 * shape. The second is the "raw 409 blob" the client saw. Both end up as the same sentence here.
 */

/** Which refusal this is — chooses the next step, never the wording of the server's own sentence. */
export type RunRefusalKind = "relief" | "selection" | "other";

export interface RunRefusal {
  readonly kind: RunRefusalKind;
  readonly title: string;
  /** The server's own words, verbatim. */
  readonly detail: string;
  readonly nextStep: string;
  readonly status: number | null;
}

/** The generic wrapper `parseJsonOrThrow` builds when a body was not FastAPI's `{detail: ...}`. */
const WRAPPER = /^.*?\sfailed\s\(\d{3}[^)]*\):\s*/;

/**
 * The operator-readable sentence inside a transport message: FastAPI's `detail` when the body is
 * still JSON, otherwise the message with the "<action> failed (409 Conflict): " prefix stripped.
 * Falls back to the message unchanged — an unreadable refusal is still shown, never swallowed.
 */
export function serverSentence(message: string): string {
  const brace = message.indexOf("{");
  if (brace >= 0) {
    try {
      const parsed = JSON.parse(message.slice(brace)) as { detail?: unknown };
      if (typeof parsed.detail === "string" && parsed.detail.trim() !== "") {
        return parsed.detail.trim();
      }
    } catch {
      // not JSON after all — fall through to the prefix strip
    }
  }
  const stripped = message.replace(WRAPPER, "").trim();
  return stripped === "" ? message.trim() : stripped;
}

/** A refusal about the gingival relief — the one this feature exists for. The worker's own
 *  refusal names the relief and the channel, so those words are what we key on. */
function isReliefRefusal(sentence: string): boolean {
  return /gingival|screw channel|channel wall|relief/i.test(sentence);
}

/** A refusal about an incomplete library selection (the 422 the no-guessing contract raises). */
function isSelectionRefusal(sentence: string, status: number | null): boolean {
  if (status !== 422) return false;
  return /implant system|construction part|choose|declare|select/i.test(sentence);
}

const RELIEF_NEXT_STEP =
  "Lower the gingival profile offset to at most the ceiling shown beside the offset input " +
  "(“max safe for this part”) and process again — or choose a construction part with more wall " +
  "around its screw channel. The relief is the only thing that has to change; the marks, the " +
  "declared caps and the reviews are all still in place.";

const SELECTION_NEXT_STEP =
  "Open “⧉ Verify & process”, make the selection the message names, then process again.";

const GENERIC_NEXT_STEP =
  "The run did not complete, so nothing was emitted — a package is never shipped from a run that " +
  "stopped at a gate. Address the condition above and process again.";

/**
 * The refusal, or null when the failure is not one (a network drop, a client-side gate). Callers
 * pass whatever they caught; anything without a message is not a server refusal and is left to
 * the generic error toast.
 */
export function runRefusalFrom(err: unknown): RunRefusal | null {
  if (!(err instanceof Error) || err.message.trim() === "") return null;
  // ApiError carries the HTTP status; a plain Error does not. Read it structurally rather than
  // importing the class — this module is domain, and must not depend on the transport layer.
  const carried = (err as unknown as { status?: unknown }).status;
  const status = typeof carried === "number" ? carried : null;
  const detail = serverSentence(err.message);
  if (isReliefRefusal(detail)) {
    return {
      kind: "relief",
      title: "Not shippable at this gingival relief — nothing was emitted",
      detail,
      nextStep: RELIEF_NEXT_STEP,
      status,
    };
  }
  if (isSelectionRefusal(detail, status)) {
    return {
      kind: "selection",
      title: "The run was refused — the library selection is incomplete",
      detail,
      nextStep: SELECTION_NEXT_STEP,
      status,
    };
  }
  return {
    kind: "other",
    title: "The run was refused — no package was emitted",
    detail,
    nextStep: GENERIC_NEXT_STEP,
    status,
  };
}
