/**
 * THE PRE-RUN ALIGNMENT PREVIEW's wire contract (client, 2026-07-26: "verify must work on the
 * first pass, automatically").
 *
 * The union pane could only ever colour a SHIPPED pose, so before any run it said "no seated
 * result for this site" — verification that only works after the thing it gates. The preview
 * endpoint answers with the SAME payload shape as the shipped deviation, which is the point:
 * one instrument, one scale, one colouring. These pin the request the client sends (the run's own
 * body, so the preview is of exactly what Process would do), and the one field that tells the two
 * apart.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { previewSiteAlignment, ApiError } from "./client";
import { mapSiteDeviation } from "./mappers";
import type { WireSiteDeviation } from "./wireTypes";
import type { ConfirmedSite } from "../domain/types";

const SITES: ConfirmedSite[] = [
  { tooth: 29, center: [1, 2, 3], declaredVariant: "6020", centerMark: [1, 2, 3] },
  { tooth: 3, center: [4, 5, 6], declaredVariant: "6030" },
];

const SELECTION = {
  model: "neodent-gm",
  constructionPathId: "dess/neodent-gm-scanbody.stl",
  jaw: "lower",
  gingivalOffsetMm: 0.2,
};

function wirePayload(overrides: Partial<WireSiteDeviation> = {}): WireSiteDeviation {
  return {
    case_id: "cap6020-neodent-gm",
    tooth: 29,
    implant_model: "neodent-gm",
    variant: "6020",
    frame: "jaw-scan world frame",
    units: "mm",
    n_points: 2,
    points: [
      [0, 0, 0],
      [1, 1, 1],
    ],
    faces: [[0, 1, 1]],
    deviation_mm: [0.12, null],
    scale: {
      clamp_mm: 0.5,
      min_mm: -0.5,
      max_mm: 0.5,
      colormap: "RdBu_r",
      sign_convention: "+ = scan outside the cap surface",
      data_min_mm: -1.2,
      data_max_mm: 1.4,
      footprint_band_mm: 1.2,
    },
    stats: {
      rms_mm: 0.31,
      p90_mm: 0.52,
      n_footprint: 100,
      n_samples: 400,
      source: "area-uniform surface samples (the acceptance difference map)",
    },
    vertex_footprint_points: 1,
    reporting_only: true,
    ...overrides,
  };
}

function stubFetch(response: Response) {
  const spy = vi.fn(async () => response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("previewSiteAlignment", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs the RUN's own body to the site's preview endpoint", async () => {
    const spy = stubFetch(
      new Response(JSON.stringify(wirePayload({ preview: true })), { status: 200 }),
    );
    await previewSiteAlignment("cap6020-neodent-gm", 29, SITES, SELECTION);
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/cap6020-neodent-gm/sites/29/preview-alignment");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    // EVERY marked site travels, not just the previewed one: the preview must be produced from
    // exactly the inputs Process would use, and the endpoint picks the tooth out of them
    expect((body.sites as unknown[]).length).toBe(2);
    expect(body.model).toBe("neodent-gm");
    expect(body.construction_path).toBe("dess/neodent-gm-scanbody.stl");
    expect(body.jaw).toBe("lower");
    expect(body.gingival_offset_mm).toBe(0.2);
  });

  it("maps the preview into the very same shape the shipped deviation maps into", async () => {
    stubFetch(new Response(JSON.stringify(wirePayload({ preview: true })), { status: 200 }));
    const preview = await previewSiteAlignment("cap6020-neodent-gm", 29, SITES, SELECTION);
    const shipped = mapSiteDeviation(wirePayload());
    expect(preview.points).toEqual(shipped.points);
    expect(preview.faces).toEqual(shipped.faces);
    expect(preview.scale).toEqual(shipped.scale);
    expect(preview.stats).toEqual(shipped.stats);
    // …and exactly one field tells them apart
    expect(preview.preview).toBe(true);
    expect(shipped.preview).toBe(false);
  });

  it("carries the seat numbers the results table would print, when the server sent them", async () => {
    stubFetch(
      new Response(
        JSON.stringify(
          wirePayload({
            preview: true,
            seat: { seat_method: "rim", rim_agreement_mm: 0.41, fit: { avg_mm: 0.18, max_mm: 1.4 } },
          }),
        ),
        { status: 200 },
      ),
    );
    const preview = await previewSiteAlignment("cap6020-neodent-gm", 29, SITES, SELECTION);
    expect(preview.seat).toEqual({
      seatMethod: "rim",
      rimAgreementMm: 0.41,
      fit: { avgMm: 0.18, maxMm: 1.4 },
    });
  });

  it("surfaces the server's own refusal sentence rather than a status line", async () => {
    stubFetch(
      new Response(
        JSON.stringify({ detail: "tooth 29 has no declared cap variant — choose one before previewing the alignment" }),
        { status: 422 },
      ),
    );
    await expect(previewSiteAlignment("x", 29, SITES, SELECTION)).rejects.toThrowError(
      new ApiError(
        "tooth 29 has no declared cap variant — choose one before previewing the alignment",
        422,
      ),
    );
  });

  it("keeps a 404 distinguishable, so the pane can say 'restart make serve' instead of failing", async () => {
    stubFetch(new Response("Not Found", { status: 404 }));
    await expect(previewSiteAlignment("x", 29, SITES, SELECTION)).rejects.toMatchObject({
      status: 404,
    });
  });
});

describe("mapSiteDeviation — a build that predates the preview", () => {
  it("reads a payload with no preview flag as a SHIPPED read, never as an unlabelled preview", () => {
    const mapped = mapSiteDeviation(wirePayload());
    expect(mapped.preview).toBe(false);
    expect(mapped.seat).toBeNull();
  });
});
