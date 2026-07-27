/**
 * THE HARD-FAIL PATH, pinned (client, 2026-07-25 — "it read as an unexplained error").
 *
 * The refusal the client actually hit is the fixture here, in both shapes it can arrive in: the
 * unwrapped `detail` sentence, and the raw "(409 Conflict): {json}" blob the generic transport
 * wrapper builds when the body was not FastAPI's `detail` shape. Both must come out as the
 * server's own sentence — verbatim, never paraphrased — with a next step the operator can take.
 */
import { describe, expect, it } from "vitest";
import { runRefusalFrom, serverSentence } from "./runRefusal";
import { ApiError } from "../api/client";

/** The client's own refusal, verbatim from apps/worker output_package._relief_block_reason. */
const CLIENT_SENTENCE =
  "the 0.20mm gingival relief ate the screw channel of tooth 3 (atlantis/neodent-gm 5030): the " +
  "as-built channel measured r=1.153mm before the relief and is UNMEASURABLE after it, so no " +
  "instrument can accept the delivered part — re-run with a smaller gingival offset (asked " +
  "0.20mm) or use a construction part with more wall";

describe("serverSentence — the operator-readable sentence, however it arrived", () => {
  it("passes an already-unwrapped detail through untouched", () => {
    expect(serverSentence(CLIENT_SENTENCE)).toBe(CLIENT_SENTENCE);
  });

  it("digs the detail out of the raw blob the generic wrapper builds", () => {
    const blob = `Running automation failed (409 Conflict): ${JSON.stringify({ detail: CLIENT_SENTENCE })}`;
    expect(serverSentence(blob)).toBe(CLIENT_SENTENCE);
  });

  it("strips the transport prefix when the body was not JSON at all", () => {
    expect(serverSentence("Running automation failed (500 Internal Server Error): boom")).toBe("boom");
  });

  it("never swallows a message it cannot parse", () => {
    expect(serverSentence("something odd happened")).toBe("something odd happened");
  });
});

describe("runRefusalFrom", () => {
  it("recognises the relief refusal and points at the ceiling read-out", () => {
    const refusal = runRefusalFrom(new ApiError(CLIENT_SENTENCE, 409));
    expect(refusal?.kind).toBe("relief");
    expect(refusal?.status).toBe(409);
    // the server's own sentence, verbatim — the tooth, the part and the measured radius survive
    expect(refusal?.detail).toBe(CLIENT_SENTENCE);
    expect(refusal?.title).toContain("nothing was emitted");
    expect(refusal?.nextStep).toContain("max safe for this part");
    expect(refusal?.nextStep).toContain("construction part with more wall");
  });

  it("reads the raw 409 blob into the same actionable refusal", () => {
    const blob = `Running automation failed (409 Conflict): ${JSON.stringify({ detail: CLIENT_SENTENCE })}`;
    const refusal = runRefusalFrom(new ApiError(blob, 409));
    expect(refusal?.kind).toBe("relief");
    expect(refusal?.detail).toBe(CLIENT_SENTENCE);
    // and nothing of the transport wrapper leaks into what the operator reads
    expect(refusal?.detail).not.toContain("409 Conflict");
  });

  it("routes an incomplete-selection 422 to the dialog instead", () => {
    const refusal = runRefusalFrom(
      new ApiError("choose the construction part before processing this case", 422),
    );
    expect(refusal?.kind).toBe("selection");
    expect(refusal?.nextStep).toContain("Verify & process");
  });

  it("still explains a refusal it cannot classify, rather than showing a status line", () => {
    const refusal = runRefusalFrom(new ApiError("the seat for tooth 14 failed certification", 409));
    expect(refusal?.kind).toBe("other");
    expect(refusal?.detail).toBe("the seat for tooth 14 failed certification");
    expect(refusal?.nextStep).toContain("nothing was emitted");
  });

  it("is null for a non-error, so a client-side gate is left to its own route", () => {
    expect(runRefusalFrom(null)).toBeNull();
    expect(runRefusalFrom(new Error("   "))).toBeNull();
  });
});
