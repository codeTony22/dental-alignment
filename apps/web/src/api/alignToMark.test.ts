/**
 * ALIGN-TO-MARKED-TRENCH — client + mapper contract (client ask 2026-07-24): the wire
 * response is the nudge response plus the click/feature geometry; the client POSTs the
 * picked world point and surfaces the server's own 409/422 sentence as the ApiError
 * message (the toast shows the gate's reason, not a generic status line) — the exact
 * pattern of the nudgeRotation/confirmAlignment client flows.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { alignToMark, ApiError } from "./client";
import { mapAlignToMarkResult } from "./mappers";
import type { WireAlignToMarkResult } from "./wireTypes";

const WIRE: WireAlignToMarkResult = {
  tooth: 29,
  applied_delta_deg: 38.2,
  cumulative_deg: 38.2,
  stability_excess_mm: 0.031,
  clocking: { notch_shift_deg: -1.4, notch_corr: 0.62, notch_prominence: 0.21 },
  nudge: { operator_delta_deg: 38.2, cumulative_deg: 38.2 },
  matched_feature_azimuth_deg: -136.0,
  click_azimuth_deg: -97.8,
  files: ["cap7030-zimmer-4.5-29-healingcap-aligned.stl", "cap7030-zimmer-4.5-29-implant.json"],
};

describe("mapAlignToMarkResult", () => {
  it("maps the nudge fields plus the click/feature geometry", () => {
    const result = mapAlignToMarkResult(WIRE);
    expect(result).toEqual({
      tooth: 29,
      appliedDeltaDeg: 38.2,
      cumulativeDeg: 38.2,
      stabilityExcessMm: 0.031,
      // absent wire evidence/consistency/unverified collapse to the honest defaults,
      // same as every other clocking payload (see mapClocking)
      clocking: {
        notchShiftDeg: -1.4,
        notchCorr: 0.62,
        notchProminence: 0.21,
        evidence: "none",
        consistencyDeg: null,
        rotationUnverified: false,
      },
      nudge: { cumulativeDeg: 38.2 },
      matchedFeatureAzimuthDeg: -136.0,
      clickAzimuthDeg: -97.8,
    });
  });
});

describe("alignToMark client flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Response) {
    const spy = vi.fn(async () => response);
    vi.stubGlobal("fetch", spy);
    return spy;
  }

  it("POSTs the picked world point to the site's align-to-mark endpoint and maps the result", async () => {
    const spy = stubFetch(new Response(JSON.stringify(WIRE), { status: 200 }));
    const result = await alignToMark("cap7030-zimmer-4.5", 29, [12.5, 8.2, 17.0]);
    expect(spy).toHaveBeenCalledOnce();
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/cap7030-zimmer-4.5/sites/29/align-to-mark");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ point: [12.5, 8.2, 17.0] });
    expect(result.appliedDeltaDeg).toBe(38.2);
    expect(result.matchedFeatureAzimuthDeg).toBe(-136.0);
    expect(result.clickAzimuthDeg).toBe(-97.8);
  });

  it("surfaces the server's own 409 refusal sentence as the error message", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail: "align-to-mark rotation +38.2° refused: ring-fixed stability excess 0.90mm exceeds the 0.35mm certification bound — the rim cannot hold this rotation still",
        }),
        { status: 409 },
      ),
    );
    await expect(alignToMark("cap7030-zimmer-4.5", 29, [0, 0, 0])).rejects.toThrowError(
      new ApiError(
        "align-to-mark rotation +38.2° refused: ring-fixed stability excess 0.90mm exceeds the 0.35mm certification bound — the rim cannot hold this rotation still",
        409,
      ),
    );
  });

  it("surfaces the out-of-range-mark 422 sentence too", async () => {
    stubFetch(
      new Response(
        JSON.stringify({ detail: "the mark is 48.3mm from tooth 29's seated cap — click the coded trench on the cap itself (within 15mm)" }),
        { status: 422 },
      ),
    );
    await expect(alignToMark("cap7030-zimmer-4.5", 29, [0, 0, 0])).rejects.toThrowError(
      new ApiError("the mark is 48.3mm from tooth 29's seated cap — click the coded trench on the cap itself (within 15mm)", 422),
    );
  });
});
