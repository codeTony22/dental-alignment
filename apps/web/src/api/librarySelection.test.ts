/**
 * THE NO-INFERENCE API CONTRACT (client directive 2026-07-25) — mappers + client flows:
 *
 *  - a case is listed with its SUGGESTIONS, all of which may be null (and are absent entirely on
 *    a backend predating the change) — the client must read that as "the operator must choose",
 *    never as a reason to hide the case or invent a model;
 *  - the run request CARRIES the selection, and a 422 refusal surfaces the server's own sentence;
 *  - the deviation payload is packed into the typed arrays the union pane renders, with its
 *    per-point nulls intact.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  fetchConstructions,
  fetchLibrary,
  fetchSiteDeviation,
  runAutomation,
} from "./client";
import { mapCase, mapConstructionParts, mapRunResult, mapSiteDeviation } from "./mappers";
import { authorizeRun, type AuthorizedRunSelection } from "../domain/runGate";
import { initialSelection, withReviewed, withVariant } from "../domain/librarySelection";
import type {
  WireCase,
  WireConstructionPart,
  WireRunResult,
  WireSiteDeviation,
} from "./wireTypes";

/**
 * The ONLY way to build a run selection: the gate mints it (domain/runGate). Even a test has to
 * pass the client's acknowledgment — every required selection made AND every site
 * reviewed — before `runAutomation` will accept an argument at all. That is the compile-time half
 * of the bypass fix; see domain/runGate.test.ts for the behavioural half.
 */
function authorizedSelection(): AuthorizedRunSelection {
  let selection = initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "upper",
    sites: [{ tooth: 3 }],
  });
  selection = withReviewed(withVariant(selection, 0, "6020"), 0, true);
  const auth = authorizeRun({ selection, duplicateTeeth: [] });
  if (!auth.ok) throw new Error(`the gate refused a complete selection: ${auth.reason}`);
  return auth.selection;
}

const WIRE_CASE: WireCase = {
  id: "patient-4471",
  doctor: "Doctor Patient 4471",
  jaw: "lower",
  vendor: null,
  scan_url: "/api/cases/patient-4471/scan",
  scan_filename: "lower_jaw.stl",
  suggested_model: null,
  suggested_construction: null,
  suggested_sites: [],
};

const WIRE_CONSTRUCTIONS: WireConstructionPart[] = [
  {
    vendor: "atlantis",
    filename: "zimmer-4.5-scanbody.stl",
    path_id: "atlantis/zimmer-4.5-scanbody.stl",
    label: "atlantis — zimmer-4.5-scanbody",
  },
  {
    vendor: "dess",
    filename: "neodent-gm-scanbody.stl",
    path_id: "dess/neodent-gm-scanbody.stl",
    label: "dess — neodent-gm-scanbody",
  },
];

const WIRE_DEVIATION: WireSiteDeviation = {
  case_id: "cap7030-zimmer-4.5",
  tooth: 29,
  implant_model: "zimmer-4.5",
  variant: "7030",
  frame: "jaw-scan world frame",
  units: "mm",
  n_points: 3,
  points: [
    [11.2516, 5.9287, 17.6166],
    [11.3, 6.0, 17.7],
    [11.4, 6.1, 17.8],
  ],
  faces: [[0, 1, 2]],
  deviation_mm: [0.2439, null, -0.3171],
  scale: {
    clamp_mm: 0.5,
    min_mm: -0.5,
    max_mm: 0.5,
    colormap: "RdBu_r",
    sign_convention: "+ = scan outside the cap surface",
    data_min_mm: -4.6093,
    data_max_mm: 4.2481,
    footprint_band_mm: 1.2,
  },
  stats: {
    rms_mm: 0.427,
    p90_mm: 0.732,
    n_footprint: 4910,
    n_samples: 12000,
    source: "area-uniform surface samples (the acceptance difference map)",
  },
  vertex_footprint_points: 5574,
  reporting_only: true,
};

describe("mapCase — the no-inference listing", () => {
  it("carries a case that matched NO implant system, with every suggestion null", () => {
    const mapped = mapCase(WIRE_CASE);
    expect(mapped.id).toBe("patient-4471");
    expect(mapped.suggestedModel).toBeNull();
    expect(mapped.suggestedConstruction).toBeNull();
    expect(mapped.vendor).toBeNull();
    expect(mapped.scanFilename).toBe("lower_jaw.stl");
    expect(mapped.jaw).toBe("lower");
  });

  it("keeps the suggestions when the folder name did match", () => {
    const mapped = mapCase({
      ...WIRE_CASE,
      vendor: "dess",
      suggested_model: "neodent-gm",
      suggested_construction: "dess/neodent-gm-scanbody.stl",
    });
    expect(mapped.suggestedModel).toBe("neodent-gm");
    expect(mapped.suggestedConstruction).toBe("dess/neodent-gm-scanbody.stl");
    expect(mapped.vendor).toBe("dess");
  });

  it("collapses absent fields (a backend predating the change) to null, not to a guess", () => {
    const legacy: WireCase = {
      id: "neodent-gm",
      doctor: "Doctor Neodent GM",
      jaw: "upper",
      vendor: "dess",
      scan_url: "/api/cases/neodent-gm/scan",
      suggested_sites: [],
    };
    const mapped = mapCase(legacy);
    expect(mapped.suggestedModel).toBeNull();
    expect(mapped.suggestedConstruction).toBeNull();
    expect(mapped.scanFilename).toBeNull();
  });

  it("narrows an unknown jaw string to a jaw rather than widening the domain type", () => {
    expect(mapCase({ ...WIRE_CASE, jaw: "sideways" }).jaw).toBe("upper");
  });
});

describe("mapConstructionParts", () => {
  it("maps the vendor/filename/path_id rows the picker groups by", () => {
    expect(mapConstructionParts(WIRE_CONSTRUCTIONS)).toEqual([
      {
        vendor: "atlantis",
        filename: "zimmer-4.5-scanbody.stl",
        pathId: "atlantis/zimmer-4.5-scanbody.stl",
        label: "atlantis — zimmer-4.5-scanbody",
      },
      {
        vendor: "dess",
        filename: "neodent-gm-scanbody.stl",
        pathId: "dess/neodent-gm-scanbody.stl",
        label: "dess — neodent-gm-scanbody",
      },
    ]);
  });
});

describe("mapRunResult — the selection echo", () => {
  const base: WireRunResult = {
    summary: { sites: [], package_files: [] },
    files_base: "/api/cases/x/files/",
    duration_s: 1.2,
    cached: false,
  };

  it("maps what the run was AUTHORIZED with, tooth keys parsed back to numbers", () => {
    const mapped = mapRunResult({
      ...base,
      selection: {
        model: "zimmer-4.5",
        construction_path: "atlantis/zimmer-4.5-scanbody.stl",
        vendor: "atlantis",
        jaw: "lower",
        gingival_offset_mm: 0.2,
        variants: { "29": "7030", "3": null },
      },
    });
    expect(mapped.selection?.model).toBe("zimmer-4.5");
    expect(mapped.selection?.vendor).toBe("atlantis");
    expect(mapped.selection?.gingivalOffsetMm).toBe(0.2);
    expect(mapped.selection?.variantByTooth.get(29)).toBe("7030");
    expect(mapped.selection?.variantByTooth.get(3)).toBeNull();
  });

  it("says nothing rather than echoing the client's own belief when the backend sent none", () => {
    expect(mapRunResult(base).selection).toBeNull();
  });
});

describe("mapSiteDeviation", () => {
  it("packs points and faces into the typed arrays the union mesh needs", () => {
    const mapped = mapSiteDeviation(WIRE_DEVIATION);
    expect(mapped.points).toBeInstanceOf(Float32Array);
    expect([...mapped.points.slice(0, 3)].map((v) => Number(v.toFixed(3)))).toEqual([11.252, 5.929, 17.617]);
    expect([...mapped.faces]).toEqual([0, 1, 2]);
    expect(mapped.scale.clampMm).toBe(0.5);
    expect(mapped.scale.dataMinMm).toBe(-4.6093);
    expect(mapped.stats.rmsMm).toBe(0.427);
    expect(mapped.vertexFootprintPoints).toBe(5574);
  });

  it("keeps an unreadable vertex as null — a hole must never render as a perfect fit", () => {
    expect(mapSiteDeviation(WIRE_DEVIATION).deviationMm).toEqual([0.2439, null, -0.3171]);
  });
});

describe("client flows", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Response) {
    const spy = vi.fn(async () => response);
    vi.stubGlobal("fetch", spy);
    return spy;
  }

  it("fetchConstructions reads GET /api/constructions", async () => {
    const spy = stubFetch(new Response(JSON.stringify(WIRE_CONSTRUCTIONS), { status: 200 }));
    const parts = await fetchConstructions();
    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/constructions");
    expect(parts.map((p) => p.pathId)).toEqual([
      "atlantis/zimmer-4.5-scanbody.stl",
      "dess/neodent-gm-scanbody.stl",
    ]);
  });

  it("surfaces a 404 with its status so the column can show the restart hint", async () => {
    stubFetch(new Response("not found", { status: 404, statusText: "Not Found" }));
    await expect(fetchConstructions()).rejects.toMatchObject({ status: 404 });
  });

  it("fetchLibrary names the implant system EXPLICITLY when one is chosen", async () => {
    const spy = stubFetch(new Response("[]", { status: 200 }));
    await fetchLibrary("cap7030-zimmer-4.5", "zimmer-4.5");
    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/cases/cap7030-zimmer-4.5/library?model=zimmer-4.5");
  });

  it("fetchSiteDeviation reads the site's deviation endpoint", async () => {
    const spy = stubFetch(new Response(JSON.stringify(WIRE_DEVIATION), { status: 200 }));
    const payload = await fetchSiteDeviation("cap7030-zimmer-4.5", 29);
    const [url] = spy.mock.calls[0] as unknown as [string];
    expect(url).toBe("/api/cases/cap7030-zimmer-4.5/sites/29/deviation");
    expect(payload.tooth).toBe(29);
  });

  it("a site with no run yet answers 404 — the union pane's own graceful state", async () => {
    stubFetch(new Response(JSON.stringify({ detail: "no run yet" }), { status: 404 }));
    await expect(fetchSiteDeviation("neodent-gm", 3)).rejects.toBeInstanceOf(ApiError);
  });

  it("runAutomation POSTs the operator's decoding selection alongside the sites", async () => {
    const spy = stubFetch(
      new Response(
        JSON.stringify({
          summary: { sites: [], package_files: [] },
          files_base: "/api/cases/x/files/",
          duration_s: 1,
          cached: false,
        }),
        { status: 200 },
      ),
    );
    await runAutomation(
      "neodent-gm",
      [{ tooth: 3, center: [1, 2, 3], declaredVariant: "6020" }],
      false,
      authorizedSelection(),
    );
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/neodent-gm/run");
    expect(JSON.parse(init.body as string)).toEqual({
      sites: [{ tooth: 3, center: [1, 2, 3], declared_variant: "6020" }],
      fresh: false,
      model: "neodent-gm",
      construction_path: "dess/neodent-gm-scanbody.stl",
      jaw: "upper",
      gingival_offset_mm: 0.2,
    });
  });

  it("surfaces the backend's own refusal sentence when the selection is incomplete", async () => {
    stubFetch(
      new Response(
        JSON.stringify({
          detail:
            "the library selection is incomplete: choose the construction part. The software will not pick one for you.",
        }),
        { status: 422 },
      ),
    );
    // The CLIENT-side gate is clear here — this is the backend refusing for its own reasons
    // (a construction it cannot resolve, say), and the operator must read the server's sentence.
    await expect(
      runAutomation("neodent-gm", [], false, authorizedSelection()),
    ).rejects.toThrow(/The software will not pick one for you/);
  });
});
