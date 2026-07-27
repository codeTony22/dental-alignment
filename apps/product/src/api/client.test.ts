/**
 * The client's error posture (slice 2 contract: stated words, never a rejected
 * promise) must let pages tell a REFUSING service from a DOWN one — a 404 for a
 * stale bookmark is not an outage, and the banner copy branches on that status
 * (see pages/CaseShell.tsx). These tests pin that the status survives the seam.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCaseSession } from "./client";

function stubFetch(impl: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the BFF client's error results", () => {
  it("carries the HTTP status and the BFF's stated refusal on a 404", async () => {
    stubFetch(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "unknown case 'gone-case'" }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const result = await fetchCaseSession("gone-case");
    expect(result).toEqual({
      kind: "error",
      status: 404,
      detail: "HTTP 404 — unknown case 'gone-case'",
    });
  });

  it("carries no status when the network itself failed — nothing answered", async () => {
    stubFetch(() => Promise.reject(new Error("ECONNREFUSED")));
    const result = await fetchCaseSession("case-a");
    expect(result).toEqual({ kind: "error", detail: "ECONNREFUSED" });
  });
});
