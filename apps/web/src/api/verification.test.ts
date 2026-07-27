/**
 * The doctor-verification wire contract: acceptance + confirmation mapping, and the
 * confirm-alignment client flow (URL/body/response mapping, server-detail surfacing).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { confirmAlignment, ApiError } from "./client";
import { mapConfirmAlignmentResult, mapRunResult } from "./mappers";
import type { WireAcceptance, WireRunResult, WireRunSiteResult } from "./wireTypes";
import { qcImagesFor } from "../domain/types";

function makeWireAcceptance(): WireAcceptance {
  return {
    metrics: [
      {
        key: "fit_avg_mm",
        label: "Registration error — average",
        unit: "mm",
        audience: "doctor",
        industry_ref: { value: "RealGUIDE ships 0.28 mm avg", source: "docs/RUN-DEMO.md step 4" },
        bands: { pass: 0.8, review: 1.5 },
        note: null,
        value: 0.42,
        display: "0.42 mm",
        band: "pass",
      },
      {
        key: "delivered_channel_vs_recess_mm",
        label: "Delivered screw channel vs recess",
        unit: "mm",
        audience: "lab",
        industry_ref: { value: "vendor interface spec awaited", source: "master plan" },
        bands: null,
        note: "not yet measured",
        value: null,
        display: "not yet measured",
        band: "missing",
      },
    ],
    overall: {
      band: "pass",
      counts: { pass: 1, review: 0, fail: 0, missing: 1 },
      missing: ["delivered_channel_vs_recess_mm"],
    },
    context: {
      label: "Operator click precision (context)",
      text: "click scatter xy p90 = 0.61 mm",
      industry_ref: { value: "FLE p90 0.61 mm", source: "docs/research/fle-calibration.md" },
    },
  };
}

function makeWireRunSiteResult(overrides: Partial<WireRunSiteResult> = {}): WireRunSiteResult {
  return {
    tooth: 29,
    spec: "zimmer-4.5-7030",
    vendor: "atlantis",
    coverage: 0.45,
    alignment_error_mm: 1.38,
    advisory: "",
    variant: {
      identified: "7030",
      declared: "7030",
      measured_rim_diameter_mm: 5.09,
      diameter_class_margin_mm: 1.0,
      flags: [],
    },
    site_measurement: {
      md_span_mm: 11.2,
      gap_mesial_mm: 0.5,
      gap_distal_mm: 0.9,
      classification: "ample (>=7mm)",
      terminal_site: false,
    },
    production: { screw_channel_radius_mm: 1.0 },
    seed_source: "marks",
    auto_delta_mm: 0.39,
    fit: { avg_mm: 0.42, max_mm: 1.24 },
    ...overrides,
  };
}

function makeWireRunResult(sites: WireRunSiteResult[]): WireRunResult {
  return {
    summary: { sites, package_files: [] },
    files_base: "/api/cases/x/files/",
    duration_s: 1.0,
    cached: true,
  };
}

describe("mapRunResult — acceptance", () => {
  it("maps the acceptance evaluation to camelCase domain shapes", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ acceptance: makeWireAcceptance() })]);
    const acceptance = mapRunResult(wire).summary.sites[0]?.acceptance;
    expect(acceptance?.overall.band).toBe("pass");
    expect(acceptance?.overall.missing).toEqual(["delivered_channel_vs_recess_mm"]);
    const fit = acceptance?.metrics.find((m) => m.key === "fit_avg_mm");
    expect(fit?.band).toBe("pass");
    expect(fit?.display).toBe("0.42 mm");
    expect(fit?.audience).toBe("doctor");
    expect(fit?.bands).toEqual({ passMax: 0.8, reviewMax: 1.5 });
    expect(fit?.industryRef).toEqual({
      value: "RealGUIDE ships 0.28 mm avg",
      source: "docs/RUN-DEMO.md step 4",
    });
    expect(acceptance?.context.industryRef.source).toBe("docs/research/fle-calibration.md");
  });

  it("keeps a missing metric honest: band 'missing', null value, listed in overall", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ acceptance: makeWireAcceptance() })]);
    const metric = mapRunResult(wire)
      .summary.sites[0]?.acceptance?.metrics.find((m) => m.key === "delivered_channel_vs_recess_mm");
    expect(metric?.band).toBe("missing");
    expect(metric?.value).toBeNull();
  });

  it("routes an unknown audience string into the lab group, never dropping the metric", () => {
    const acceptance = makeWireAcceptance();
    acceptance.metrics[0]!.audience = "future-audience";
    const wire = makeWireRunResult([makeWireRunSiteResult({ acceptance })]);
    expect(mapRunResult(wire).summary.sites[0]?.acceptance?.metrics[0]?.audience).toBe("lab");
  });

  it("collapses an absent acceptance (backend predating the panel) to null", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    expect(mapRunResult(wire).summary.sites[0]?.acceptance).toBeNull();
  });
});

describe("mapRunResult — doctorConfirmation", () => {
  it("maps a persisted confirmation through (the reload path)", () => {
    const wire = makeWireRunResult([
      makeWireRunSiteResult({
        doctor_confirmation: { confirmed: true, note: "codes visually aligned", ts: "2026-07-23T10:00:00" },
      }),
    ]);
    expect(mapRunResult(wire).summary.sites[0]?.doctorConfirmation).toEqual({
      confirmed: true,
      note: "codes visually aligned",
      ts: "2026-07-23T10:00:00",
    });
  });

  it("collapses an absent confirmation to null (not yet signed off)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    expect(mapRunResult(wire).summary.sites[0]?.doctorConfirmation).toBeNull();
  });
});

describe("mapConfirmAlignmentResult", () => {
  it("maps the endpoint response to the domain shape", () => {
    const result = mapConfirmAlignmentResult({
      tooth: 29,
      doctor_confirmation: { confirmed: false, note: null, ts: "2026-07-23T10:05:00" },
      acceptance_overall: "review",
    });
    expect(result).toEqual({
      tooth: 29,
      confirmation: { confirmed: false, note: null, ts: "2026-07-23T10:05:00" },
      acceptanceOverall: "review",
    });
  });
});

describe("confirmAlignment client flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Response) {
    const spy = vi.fn(async () => response);
    vi.stubGlobal("fetch", spy);
    return spy;
  }

  it("POSTs the sign-off to the site's confirm-alignment endpoint and maps the result", async () => {
    const spy = stubFetch(
      new Response(
        JSON.stringify({
          tooth: 29,
          doctor_confirmation: { confirmed: true, note: "ok", ts: "2026-07-23T10:00:00" },
          acceptance_overall: "pass",
        }),
        { status: 200 },
      ),
    );
    const result = await confirmAlignment("cap7030-zimmer-4.5", 29, true, "  ok  ");
    expect(spy).toHaveBeenCalledOnce();
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/cap7030-zimmer-4.5/sites/29/confirm-alignment");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ confirmed: true, note: "ok" });
    expect(result.confirmation.confirmed).toBe(true);
    expect(result.acceptanceOverall).toBe("pass");
  });

  it("omits the note entirely on a retract (and on a blank note)", async () => {
    const spy = stubFetch(
      new Response(
        JSON.stringify({
          tooth: 29,
          doctor_confirmation: { confirmed: false, note: null, ts: "2026-07-23T10:05:00" },
          acceptance_overall: "pass",
        }),
        { status: 200 },
      ),
    );
    await confirmAlignment("cap7030-zimmer-4.5", 29, false, "   ");
    const [, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ confirmed: false });
  });

  it("surfaces the server's own 404 sentence as the error message", async () => {
    stubFetch(
      new Response(JSON.stringify({ detail: "tooth 99 has no aligned site in case 'x' — run the automation first" }), {
        status: 404,
      }),
    );
    await expect(confirmAlignment("x", 99, true)).rejects.toThrowError(
      new ApiError("tooth 99 has no aligned site in case 'x' — run the automation first", 404),
    );
  });
});

describe("qcImagesFor", () => {
  it("returns only the QC images the package actually emitted, labeled", () => {
    const files = [
      "cap7030-zimmer-4.5-29-clockview.png",
      "cap7030-zimmer-4.5-29-deviation.png",
      "cap7030-zimmer-4.5-lower.stl",
    ];
    const images = qcImagesFor("cap7030-zimmer-4.5", 29, files);
    expect(images.map((i) => i.name)).toEqual([
      "cap7030-zimmer-4.5-29-clockview.png",
      "cap7030-zimmer-4.5-29-deviation.png",
    ]);
  });

  it("returns an empty list when the package has no QC renders (legacy run)", () => {
    expect(qcImagesFor("case", 29, ["case-lower.stl"])).toEqual([]);
  });
});
