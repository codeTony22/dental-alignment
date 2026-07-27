/**
 * MANUAL CORRESPONDENCE — client + mapper contracts for the four new endpoints (client ask
 * 2026-07-24): the library part's marks (GET/PUT/DELETE
 * /api/library/{model}/{variant}/features) and the named-correspondence rotation
 * (POST /api/cases/{id}/sites/{tooth}/align-to-correspondence).
 *
 * The two behaviours that matter beyond field names: a PUT sends EXACTLY ONE placement per
 * feature (a click travels as a canonical point so the SERVER performs the authoritative snap;
 * an untouched mark travels as its azimuth), and every refusal surfaces the server's OWN
 * sentence as the ApiError message — the gates' reasons are written for the operator.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  alignToCorrespondence,
  fetchPartFeatures,
  resetPartFeatures,
  savePartFeatures,
} from "./client";
import {
  mapAlignToCorrespondenceResult,
  mapPartAnnotation,
  toWireCorrespondencePairs,
  toWirePartFeatures,
} from "./mappers";
import type { WireAlignToCorrespondenceResult, WirePartAnnotation } from "./wireTypes";
import { featurePair, freePair } from "../domain/correspondence";

const ANNOTATION: WirePartAnnotation = {
  model: "zimmer-4.5",
  variant: "7030",
  auto_seeded: true,
  revised_at: null,
  features: [
    {
      id: "trench-01",
      kind: "trench",
      azimuth_deg: -177.0,
      radius_mm: 2.061,
      z_mm: 1.808,
      source: "auto",
      defines_rotation: true,
    },
    {
      id: "channel",
      kind: "channel",
      azimuth_deg: -173.12,
      radius_mm: 0.03,
      z_mm: 1.806,
      source: "auto",
      defines_rotation: false,
    },
  ],
};

const CORRESPONDENCE: WireAlignToCorrespondenceResult = {
  tooth: 29,
  applied_delta_deg: 8.0,
  cumulative_deg: 8.0,
  stability_excess_mm: 0.006,
  clocking: { notch_shift_deg: -1.4, notch_corr: 0.62, notch_prominence: 0.21 },
  nudge: { operator_delta_deg: 8.0, cumulative_deg: 8.0 },
  pairs: [
    {
      feature_id: "trench-01",
      feature_azimuth_deg: -177,
      click_azimuth_deg: -167,
      delta_deg: 10,
      residual_deg: 2,
      residual_mm: 0.072,
    },
  ],
  residual_rms_mm: 0.072,
  files: ["cap7030-zimmer-4.5-29-healingcap-aligned.stl", "cap7030-zimmer-4.5-29-implant.json"],
};

function stubFetch(response: Response) {
  const spy = vi.fn(async () => response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("mapPartAnnotation", () => {
  it("maps the marks, keeping the server's own defines_rotation verdict", () => {
    const annotation = mapPartAnnotation(ANNOTATION);
    expect(annotation.model).toBe("zimmer-4.5");
    expect(annotation.variant).toBe("7030");
    expect(annotation.autoSeeded).toBe(true);
    expect(annotation.revisedAt).toBeNull();
    expect(annotation.features[0]).toEqual({
      id: "trench-01",
      kind: "trench",
      azimuthDeg: -177.0,
      radiusMm: 2.061,
      zMm: 1.808,
      source: "auto",
      definesRotation: true,
    });
    // the lever-arm rule is the BACKEND's to own — never re-derived here
    expect(annotation.features[1]?.definesRotation).toBe(false);
  });

  it("lists an unrecognized kind/source rather than dropping a mark the doctor placed", () => {
    const annotation = mapPartAnnotation({
      ...ANNOTATION,
      features: [{ ...ANNOTATION.features[0]!, kind: "dimple", source: "somebody" }],
    });
    expect(annotation.features[0]?.kind).toBe("trench");
    expect(annotation.features[0]?.source).toBe("operator");
  });
});

describe("toWirePartFeatures", () => {
  it("sends exactly one placement per feature — a click as a point, otherwise the azimuth", () => {
    expect(
      toWirePartFeatures([
        { kind: "trench", azimuthDeg: -177, point: null },
        { kind: "trench", azimuthDeg: null, point: [1.2, 0.4, 1.8] },
      ]),
    ).toEqual([
      { kind: "trench", azimuth_deg: -177 },
      { kind: "trench", point: [1.2, 0.4, 1.8] },
    ]);
  });
});

describe("part-features client flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs the part's marks from the catalog-keyed features endpoint", async () => {
    const spy = stubFetch(new Response(JSON.stringify(ANNOTATION), { status: 200 }));
    const annotation = await fetchPartFeatures("zimmer-4.5", "7030");
    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/library/zimmer-4.5/7030/features");
    expect(annotation.features).toHaveLength(2);
  });

  it("surfaces a 404 with its status, so the panel can show the restart hint", async () => {
    stubFetch(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }));
    await expect(fetchPartFeatures("zimmer-4.5", "7030")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("PUTs the operator's marks and adopts the persisted answer", async () => {
    const saved: WirePartAnnotation = {
      ...ANNOTATION,
      auto_seeded: false,
      revised_at: "2026-07-25T10:00:00",
      features: ANNOTATION.features.map((f) => ({ ...f, source: "operator" })),
    };
    const spy = stubFetch(new Response(JSON.stringify(saved), { status: 200 }));
    const out = await savePartFeatures("zimmer-4.5", "7030", [
      { kind: "trench", azimuthDeg: -177, point: null },
      { kind: "trench", azimuthDeg: null, point: [1.2, 0.4, 1.8] },
    ]);
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/library/zimmer-4.5/7030/features");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      features: [
        { kind: "trench", azimuth_deg: -177 },
        { kind: "trench", point: [1.2, 0.4, 1.8] },
      ],
    });
    expect(out.autoSeeded).toBe(false);
    expect(out.revisedAt).toBe("2026-07-25T10:00:00");
    expect(out.features.every((f) => f.source === "operator")).toBe(true);
  });

  it("surfaces the server's own 422 sentence when a click cannot be a mark", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail:
            "the click is 0.21mm from the part's rim centre — inside 0.5mm there is no azimuth to mark (a concentric landmark names the axis, not a clock angle)",
        }),
        { status: 422 },
      ),
    );
    await expect(
      savePartFeatures("zimmer-4.5", "7030", [{ kind: "trench", azimuthDeg: null, point: [0, 0, 1] }]),
    ).rejects.toThrowError(
      new ApiError(
        "the click is 0.21mm from the part's rim centre — inside 0.5mm there is no azimuth to mark (a concentric landmark names the axis, not a clock angle)",
        422,
      ),
    );
  });

  it("DELETEs back to the machine's own reading", async () => {
    const spy = stubFetch(
      new Response(JSON.stringify({ ...ANNOTATION, reverted: true }), { status: 200 }),
    );
    const out = await resetPartFeatures("zimmer-4.5", "7030");
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/library/zimmer-4.5/7030/features");
    expect(init.method).toBe("DELETE");
    expect(out.autoSeeded).toBe(true);
  });

  it("percent-escapes the catalog id — superseded entries carry separators", async () => {
    const spy = stubFetch(new Response(JSON.stringify(ANNOTATION), { status: 200 }));
    await fetchPartFeatures("neodent-gm", "superseded-2026-07-13--6020");
    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/library/neodent-gm/superseded-2026-07-13--6020/features");
  });
});

describe("mapAlignToCorrespondenceResult", () => {
  it("maps the nudge fields plus the per-pair residuals and their RMS", () => {
    const out = mapAlignToCorrespondenceResult(CORRESPONDENCE);
    expect(out.appliedDeltaDeg).toBe(8.0);
    expect(out.residualRmsMm).toBe(0.072);
    expect(out.pairs[0]).toEqual({
      featureId: "trench-01",
      featureAzimuthDeg: -177,
      clickAzimuthDeg: -167,
      deltaDeg: 10,
      residualDeg: 2,
      residualMm: 0.072,
    });
    // absent wire evidence/consistency/unverified collapse to the honest defaults (mapClocking)
    expect(out.clocking.evidence).toBe("none");
    expect(out.clocking.rotationUnverified).toBe(false);
  });
});

describe("alignToCorrespondence client flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs every named pair to the site's align-to-correspondence endpoint", async () => {
    const spy = stubFetch(new Response(JSON.stringify(CORRESPONDENCE), { status: 200 }));
    const out = await alignToCorrespondence("cap7030-zimmer-4.5", 29, [
      featurePair("trench-01", "trench", [12.5, 8.2, 17.0]),
      featurePair("trench-02", "trench", [13.1, 9.4, 17.2]),
    ]);
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/cap7030-zimmer-4.5/sites/29/align-to-correspondence");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      pairs: [
        { feature_id: "trench-01", scan_point: [12.5, 8.2, 17.0] },
        { feature_id: "trench-02", scan_point: [13.1, 9.4, 17.2] },
      ],
    });
    expect(out.pairs).toHaveLength(1);
  });

  it("a FREE pair travels as part_point and carries NO feature_id (client ask 2026-07-26)", async () => {
    const spy = stubFetch(new Response(JSON.stringify(CORRESPONDENCE), { status: 200 }));
    await alignToCorrespondence("cap7030-zimmer-4.5", 29, [
      freePair([0.52, -1.13, 1.81], [12.5, 8.2, 17.0]),
    ]);
    const [, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(init.body as string) as { pairs: Record<string, unknown>[] };
    expect(body.pairs).toEqual([
      { part_point: [0.52, -1.13, 1.81], scan_point: [12.5, 8.2, 17.0] },
    ]);
    expect(body.pairs[0]).not.toHaveProperty("feature_id");
  });

  it("toWireCorrespondencePairs keeps the two shapes mutually exclusive", () => {
    expect(
      toWireCorrespondencePairs([
        featurePair("trench-01", "trench", [1, 2, 3]),
        freePair([4, 5, 6], [7, 8, 9]),
      ]),
    ).toEqual([
      { feature_id: "trench-01", scan_point: [1, 2, 3] },
      { part_point: [4, 5, 6], scan_point: [7, 8, 9] },
    ]);
  });

  it("surfaces the server's own 409 refusal sentence as the error message", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail:
            "align-to-correspondence rotation +38.2° refused: ring-fixed stability excess 0.90mm exceeds the 0.35mm certification bound — the rim cannot hold this rotation still",
        }),
        { status: 409 },
      ),
    );
    await expect(
      alignToCorrespondence("cap7030-zimmer-4.5", 29, [
        featurePair("trench-01", "trench", [0, 0, 0]),
      ]),
    ).rejects.toThrowError(
      new ApiError(
        "align-to-correspondence rotation +38.2° refused: ring-fixed stability excess 0.90mm exceeds the 0.35mm certification bound — the rim cannot hold this rotation still",
        409,
      ),
    );
  });

  it("surfaces the unknown-feature 422 sentence, which names the marks that DO exist", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail:
            "'trench-09' is not a marked feature of zimmer-4.5/7030 (known: trench-01, trench-02, trench-03, channel)",
        }),
        { status: 422 },
      ),
    );
    await expect(
      alignToCorrespondence("cap7030-zimmer-4.5", 29, [
        featurePair("trench-09", "trench", [0, 0, 0]),
      ]),
    ).rejects.toThrowError(
      new ApiError(
        "'trench-09' is not a marked feature of zimmer-4.5/7030 (known: trench-01, trench-02, trench-03, channel)",
        422,
      ),
    );
  });
});
