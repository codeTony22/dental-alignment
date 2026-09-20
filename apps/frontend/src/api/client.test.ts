import { describe, expect, it } from "vitest";
import { ApiClient } from "./client";
import { CASES, servedFetch, signalEnvelope, techniqueResult } from "../testing/fixtures";

describe("ApiClient", () => {
  it("lists cases from /api/v1/cases", async () => {
    const client = new ApiClient(servedFetch({
      "GET /api/v1/cases": { cases: CASES },
    }));
    await expect(client.listCases()).resolves.toEqual(CASES);
  });

  it("posts a technique run and returns the full envelope", async () => {
    const payload = techniqueResult("intelligence");
    const client = new ApiClient(servedFetch({
      "POST /api/v1/cases/neodent-gm/sites/4/technique": payload,
    }));
    const result = await client.postTechnique("neodent-gm", 4, {
      mode: "intelligence", apply: true,
    });
    expect(result.mode).toBe("intelligence");
    expect(result.signal_groups).toEqual(payload.signal_groups);
    expect(result.signals_after.group_names).toEqual(signalEnvelope().group_names);
  });

  it("surfaces a structured 409 as ApiError", async () => {
    const client = new ApiClient(servedFetch({
      "POST /api/v1/cases/neodent-gm/sites/4/best-fit": {
        status: 409,
        body: { detail: { kind: "already_optimal", message: "already the best fit" } },
      },
    }));
    await expect(client.postBestFit("neodent-gm", 4, { apply: true })).rejects.toMatchObject({
      status: 409,
      detail: { kind: "already_optimal" },
    });
  });
});
