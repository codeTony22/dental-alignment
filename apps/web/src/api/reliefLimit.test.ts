/**
 * THE RELIEF-CEILING CONTRACT (client, 2026-07-25) — the wire half.
 *
 * Two things are pinned:
 *
 *  1. GET /api/relief-limit asks about a (construction part x model x cap variant) TRIPLE, and a
 *     404 carries its status so the caller can show the "restart make serve" hint instead of a
 *     failure toast — the same treatment /api/constructions and /api/library already get.
 *  2. The CLAMP fields on a run's per-site gingival reading are read conservatively: absent
 *     `clamped` is false and absent `applied_mm` is null. A backend that says nothing must never
 *     be read as "applied exactly what you asked for" — that is the silent substitution the whole
 *     feature exists to prevent.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchReliefLimit } from "./client";
import { mapReliefLimit, mapRunResult } from "./mappers";
import { clampedSites, describeClamp } from "../domain/reliefClamp";
import type { WireReliefLimit, WireRunResult } from "./wireTypes";

afterEach(() => {
  vi.unstubAllGlobals();
});

const WIRE_LIMIT: WireReliefLimit = {
  construction_path: "atlantis/neodent-gm-scanbody.stl",
  model: "neodent-gm",
  variant: "5030",
  max_safe_offset_mm: 0.06,
  limited_by: "channel wall",
  min_wall_mm: 0.5,
  measured: true,
  note: null,
};

function stubFetch(response: Response) {
  const spy = vi.fn(async (_input: string) => response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("mapReliefLimit", () => {
  it("maps the measured ceiling and what limits it", () => {
    expect(mapReliefLimit(WIRE_LIMIT)).toEqual({
      constructionPathId: "atlantis/neodent-gm-scanbody.stl",
      model: "neodent-gm",
      variant: "5030",
      maxSafeMm: 0.06,
      limitedBy: "channel wall",
      minWallMm: 0.5,
      measured: true,
      note: null,
    });
  });

  it("reads a null ceiling as 'not determined', never as 'no limit'", () => {
    expect(mapReliefLimit({ ...WIRE_LIMIT, max_safe_offset_mm: null }).maxSafeMm).toBeNull();
  });

  it("refuses a non-finite ceiling — an Infinity would render as a limit nobody can exceed", () => {
    const limit = mapReliefLimit({ ...WIRE_LIMIT, max_safe_offset_mm: Number.POSITIVE_INFINITY });
    expect(limit.maxSafeMm).toBeNull();
  });

  it("accepts the shorter `max_safe_mm` spelling as the same number", () => {
    const limit = mapReliefLimit({
      construction_path: "a",
      model: "m",
      variant: "v",
      max_safe_offset_mm: null,
      max_safe_mm: 0.12,
    });
    expect(limit.maxSafeMm).toBe(0.12);
  });

  it("names the only thing that limits it today when the backend did not say", () => {
    const limit = mapReliefLimit({
      construction_path: "a",
      model: "m",
      variant: "v",
      max_safe_offset_mm: 0.1,
    });
    expect(limit.limitedBy).toBe("channel wall");
    expect(limit.minWallMm).toBeNull();
    // absent `measured` means measured — only an explicit false marks a fallback
    expect(limit.measured).toBe(true);
  });
});

describe("fetchReliefLimit", () => {
  it("asks about the construction part, the system and the cap variant", async () => {
    const spy = stubFetch(new Response(JSON.stringify(WIRE_LIMIT), { status: 200 }));
    const limit = await fetchReliefLimit("atlantis/neodent-gm-scanbody.stl", "neodent-gm", "5030");
    expect(limit.maxSafeMm).toBe(0.06);
    const url = String(spy.mock.calls[0]?.[0]);
    expect(url.startsWith("/api/relief-limit?")).toBe(true);
    expect(url).toContain("construction_path=atlantis%2Fneodent-gm-scanbody.stl");
    expect(url).toContain("model=neodent-gm");
    expect(url).toContain("variant=5030");
  });

  it("surfaces a 404 with its status, so the column can say 'restart make serve'", async () => {
    stubFetch(new Response("not found", { status: 404 }));
    await expect(fetchReliefLimit("a", "m", "v")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("wraps an unreachable backend rather than throwing a raw TypeError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    await expect(fetchReliefLimit("a", "m", "v")).rejects.toBeInstanceOf(ApiError);
  });
});

/** A minimal run payload carrying one site, so the clamp fields can be read off it. */
function runWith(gingival: Record<string, unknown> | null): WireRunResult {
  return {
    summary: {
      sites: [
        {
          tooth: 3,
          spec: "neodent-gm-5030",
          vendor: "atlantis",
          coverage: 0.9,
          alignment_error_mm: 0.1,
          advisory: "",
          variant: {
            identified: "5030",
            declared: "5030",
            measured_rim_diameter_mm: 5.1,
            diameter_class_margin_mm: 0.2,
            flags: [],
          },
          site_measurement: {
            md_span_mm: 8,
            gap_mesial_mm: 1,
            gap_distal_mm: 1,
            classification: "bounded",
            terminal_site: false,
          },
          production: { screw_channel_radius_mm: 1.153 },
          seed_source: "marks",
          auto_delta_mm: 0.2,
          fit: { avg_mm: 0.08, max_mm: 0.4 },
          gingival_offset: gingival,
        },
      ],
      package_files: [],
    },
    files_base: "/files/",
    duration_s: 1,
    cached: false,
  } as unknown as WireRunResult;
}

describe("the clamp fields on a run's gingival reading", () => {
  it("carries both numbers, the ceiling and the reason when the run clamped", () => {
    const result = mapRunResult(
      runWith({
        requested_mm: 0.2,
        applied_mm: 0.06,
        clamped: true,
        limit_mm: 0.06,
        min_wall_mm: 0.5,
        clamp_reason: "the channel wall would drop under the rule",
      }),
    );
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.requestedMm).toBe(0.2);
    expect(reading?.appliedMm).toBe(0.06);
    expect(reading?.clamped).toBe(true);
    expect(reading?.limitMm).toBe(0.06);
    expect(reading?.minWallMm).toBe(0.5);
    expect(reading?.clampReason).toBe("the channel wall would drop under the rule");
  });

  it("reads a silent backend as NOT clamped and NOT reported — never as applied-in-full", () => {
    const result = mapRunResult(runWith({ requested_mm: 0.2, achieved_median_mm: 0.14 }));
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.clamped).toBe(false);
    expect(reading?.appliedMm).toBeNull();
    // the request itself is untouched, as always
    expect(reading?.requestedMm).toBe(0.2);
  });
});

/**
 * THE SHAPE THE WORKER ACTUALLY SENDS, captured verbatim from the live API on 2026-07-25:
 * case 276794487-zimmer-4.5, tooth 3, atlantis/zimmer-4.5-scanbody x zimmer-4.5/6020, run at
 * the client's 0.20 mm default and clamped to the pair's 0.08 mm ceiling.
 *
 * The clamp lives in `production`. `gingival_offset.requested_mm` is NOT the operator's ask —
 * it is the value the part was CUT with (0.08), because the achieved-clearance instrument
 * measures against the relief actually applied. Reading the clamp off `gingival_offset` alone
 * reported this run as unclamped and relabelled 0.08 as the request, which is exactly the
 * silent substitution the feature forbids. These tests pin the real bytes so that cannot
 * regress into a stub-only guarantee.
 */
const LIVE_PRODUCTION_CLAMP = {
  screw_channel_radius_mm: 1.0,
  gingival_offset_mm: 0.08,
  gingival_offset_requested_mm: 0.2,
  gingival_offset_applied_mm: 0.08,
  clamped: true,
  clamp_reason:
    "the 0.20mm gingival relief the lab asked for is NOT safe on atlantis/zimmer-4.5 6020: at " +
    "0.20mm it thins a channel wall that is already under the 0.50mm rule (0.294mm at zero " +
    "relief). The package was emitted at the maximum safe relief for this construction-part/cap " +
    "pair, 0.08mm — NOT at the 0.20mm requested.",
  limited_by: "wall",
  max_safe_mm: 0.08,
  wall_mm_at_zero: 0.2945,
  wall_mm_at_requested: 0.0296,
  wall_mm_at_applied: 0.3026,
};

const LIVE_GINGIVAL_BLOCK = {
  requested_mm: 0.08,
  achieved_median_mm: 0.0531,
  achieved_min_mm: 0.0001,
  achieved_max_mm: 0.2876,
  method: "surface-sample nearest-distance, relieved product vs the un-relieved reference product",
};

function liveRun(
  production: Record<string, unknown>,
  gingival: Record<string, unknown> | null,
): WireRunResult {
  const run = runWith(gingival) as unknown as {
    summary: { sites: Array<Record<string, unknown>> };
  };
  const site = run.summary.sites[0] as Record<string, unknown>;
  site.production = production;
  return run as unknown as WireRunResult;
}

describe("the clamp as the LIVE worker sends it (production block)", () => {
  it("reports the run as CLAMPED from production, not from the gingival block", () => {
    const result = mapRunResult(liveRun(LIVE_PRODUCTION_CLAMP, LIVE_GINGIVAL_BLOCK));
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.clamped).toBe(true);
    expect(reading?.appliedMm).toBe(0.08);
    expect(reading?.limitMm).toBe(0.08);
    expect(reading?.clampReason).toContain("NOT at the 0.20mm requested");
  });

  it("labels the OPERATOR'S ask as requested — never the 0.08 the part was cut with", () => {
    const result = mapRunResult(liveRun(LIVE_PRODUCTION_CLAMP, LIVE_GINGIVAL_BLOCK));
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.requestedMm).toBe(0.2);
    expect(reading?.requestedMm).not.toBe(LIVE_GINGIVAL_BLOCK.requested_mm);
    // achieved stays the measurement, untouched by the clamp read
    expect(reading?.achievedMedianMm).toBe(0.0531);
  });

  it("yields a clamp the notice layer can print, with applied strictly under the ask", () => {
    const result = mapRunResult(liveRun(LIVE_PRODUCTION_CLAMP, LIVE_GINGIVAL_BLOCK));
    const clamps = clampedSites(result.summary.sites);
    expect(clamps).toHaveLength(1);
    expect(clamps[0]).toMatchObject({ tooth: 3, requestedMm: 0.2, appliedMm: 0.08 });
    expect(describeClamp(clamps[0]!)).toContain("0.20 mm requested");
    expect(describeClamp(clamps[0]!)).toContain("0.08 mm applied");
  });

  it("an UNCLAMPED live row (the dess pairs at 0.20) reports no clamp", () => {
    const result = mapRunResult(
      liveRun(
        {
          screw_channel_radius_mm: 1.0,
          gingival_offset_mm: 0.2,
          gingival_offset_requested_mm: 0.2,
          gingival_offset_applied_mm: 0.2,
          clamped: false,
          clamp_reason: null,
          limited_by: "none",
          max_safe_mm: null,
        },
        { requested_mm: 0.2, achieved_median_mm: 0.1408 },
      ),
    );
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.clamped).toBe(false);
    expect(reading?.requestedMm).toBe(0.2);
    expect(clampedSites(result.summary.sites)).toHaveLength(0);
  });

  it("still reads a pre-clamp backend (production carrying only the radius)", () => {
    const result = mapRunResult(
      liveRun({ screw_channel_radius_mm: 1.153 }, { requested_mm: 0.2, achieved_median_mm: 0.14 }),
    );
    const reading = result.summary.sites[0]?.gingivalOffset;
    expect(reading?.clamped).toBe(false);
    expect(reading?.appliedMm).toBeNull();
    expect(reading?.requestedMm).toBe(0.2);
  });
});

describe("the ceiling endpoint's wall-rule spelling", () => {
  const base: WireReliefLimit = {
    construction_path: "atlantis/zimmer-4.5-scanbody.stl",
    model: "zimmer-4.5",
    variant: "6020",
    max_safe_offset_mm: null,
  };

  it("reads the worker's min_wall_rule_mm as the rule the ceiling protects", () => {
    // the live payload: max_safe_mm + min_wall_rule_mm, neither of them the canonical spelling
    const limit = mapReliefLimit({
      ...base,
      max_safe_mm: 0.08,
      min_wall_rule_mm: 0.5,
      limited_by: "wall",
    });
    expect(limit.maxSafeMm).toBe(0.08);
    expect(limit.minWallMm).toBe(0.5);
    expect(limit.limitedBy).toBe("wall");
  });

  it("prefers the canonical min_wall_mm when a backend sends both", () => {
    expect(mapReliefLimit({ ...base, min_wall_mm: 0.5, min_wall_rule_mm: 0.6 }).minWallMm).toBe(0.5);
  });

  it("stays null when neither spelling is sent — never an invented rule", () => {
    expect(mapReliefLimit(base).minWallMm).toBeNull();
  });
});
