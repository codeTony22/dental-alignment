/**
 * THE BEST-FIT "ALREADY OPTIMAL" OUTCOME on the wire (client ask 2026-07-26): the one 409
 * whose `detail` is an OBJECT — a machine-readable confirmation (kind "already_optimal")
 * that the certified pose already is the best fit at the dialled diameter, with the
 * suggested wider diameter for the one-click follow-up.
 *
 * What is pinned: ApiError tolerates BOTH detail shapes (the object's `message` becomes the
 * error message, so every consumer that reads `.message` keeps working; the object rides on
 * `.detail` for typed readers), `bestFitAlreadyOptimal` recognises the outcome by its KIND —
 * never by matching prose — and every plain-string 409 still renders exactly as before.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, bestFitAlreadyOptimal, bestFitSite } from "./client";

const OPTIMAL_DETAIL = {
  kind: "already_optimal",
  message:
    "the certified pose is already the best fit within this matching diameter — nothing to correct at Ø0.30mm; widen to search further",
  matching_diameter_mm: 0.3,
  suggested_diameter_mm: 0.6,
};

function stubFetch(response: Response) {
  const spy = vi.fn(async () => response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("bestFitSite — the object-detail 409", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces the object's message as the ApiError message and the object as .detail", async () => {
    stubFetch(new Response(JSON.stringify({ detail: OPTIMAL_DETAIL }), { status: 409 }));
    let caught: unknown = null;
    try {
      await bestFitSite("cap7030-zimmer-4.5", 29, { matchingDiameterMm: 0.3, apply: true });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.status).toBe(409);
    expect(err.message).toBe(OPTIMAL_DETAIL.message);
    expect(err.detail).toEqual(OPTIMAL_DETAIL);

    const optimal = bestFitAlreadyOptimal(err);
    expect(optimal).toEqual({
      message: OPTIMAL_DETAIL.message,
      matchingDiameterMm: 0.3,
      suggestedDiameterMm: 0.6,
    });
  });

  it("keeps a plain-string 409 exactly as before — a refusal sentence, not a confirmation", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail:
            "best-fit at a 0.30mm matching diameter refused: the top face would pull off the scan (0.12 → 0.61mm mean, bound +0.15mm)",
        }),
        { status: 409 },
      ),
    );
    let caught: unknown = null;
    try {
      await bestFitSite("cap7030-zimmer-4.5", 29, { matchingDiameterMm: 0.3, apply: true });
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.message).toContain("refused: the top face would pull off the scan");
    expect(err.detail).toBeUndefined();
    expect(bestFitAlreadyOptimal(err)).toBeNull();
  });
});

describe("bestFitAlreadyOptimal — the kind is the discriminator, never the prose", () => {
  it("rejects anything that is not a 409 ApiError carrying the exact kind and numbers", () => {
    expect(bestFitAlreadyOptimal(new Error("boom"))).toBeNull();
    expect(bestFitAlreadyOptimal(new ApiError("nope", 404))).toBeNull();
    expect(bestFitAlreadyOptimal(new ApiError("plain 409", 409))).toBeNull();
    expect(
      bestFitAlreadyOptimal(new ApiError("m", 409, { ...OPTIMAL_DETAIL, kind: "other" })),
    ).toBeNull();
    expect(
      bestFitAlreadyOptimal(
        new ApiError("m", 409, { ...OPTIMAL_DETAIL, suggested_diameter_mm: "0.6" }),
      ),
    ).toBeNull();
  });

  it("accepts the real shape even when the message wording changes", () => {
    // no string-matching on prose anywhere: reword the sentence and the parse still holds
    const reworded = { ...OPTIMAL_DETAIL, message: "different words, same verdict" };
    expect(bestFitAlreadyOptimal(new ApiError(reworded.message, 409, reworded))).toEqual({
      message: "different words, same verdict",
      matchingDiameterMm: 0.3,
      suggestedDiameterMm: 0.6,
    });
  });
});
