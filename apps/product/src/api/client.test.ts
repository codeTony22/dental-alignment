/**
 * The client's error posture (slice 2 contract: stated words, never a rejected
 * promise) must let pages tell a REFUSING service from a DOWN one — a 404 for a
 * stale bookmark is not an outage, and the banner copy branches on that status
 * (see pages/CaseShell.tsx). These tests pin that the status survives the seam.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchCaseSession,
  postDetect,
  putChoices,
  refusalDetail,
  scanUrlFor,
} from "./client";

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

describe("the action requests (slice 4) — detect and choices", () => {
  function capturingFetch(status = 200, body: unknown = {}) {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    stubFetch(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        }),
      );
    }) as never);
    return calls;
  }

  it("detect POSTs with no body — a compute trigger, nothing to claim with", async () => {
    const calls = capturingFetch();
    await postDetect("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/detect");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("fresh is the explicit re-ask", async () => {
    const calls = capturingFetch();
    await postDetect("case-a", true);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/detect?fresh=1");
  });

  it("choices PUTs the whole document as JSON", async () => {
    const calls = capturingFetch();
    await putChoices("case-a", {
      construction_path: "dess/a.stl",
      jaw: "upper",
      gingival_offset_mm: 0.15,
    });
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/choices");
    expect(calls[0]!.init?.method).toBe("PUT");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      construction_path: "dess/a.stl",
      jaw: "upper",
      gingival_offset_mm: 0.15,
    });
  });

  it("a pydantic-shaped 422 surfaces the backend's sentences, not machinery", async () => {
    capturingFetch(422, {
      detail: [
        {
          type: "value_error",
          loc: ["body", "jaw"],
          msg: "Value error, jaw must be one of upper, lower, got 'sideways'",
          input: "sideways",
        },
      ],
    });
    const result = await putChoices("case-a", {
      construction_path: null,
      jaw: "sideways",
      gingival_offset_mm: null,
    });
    expect(result).toEqual({
      kind: "error",
      status: 422,
      detail: "HTTP 422 — jaw must be one of upper, lower, got 'sideways'",
    });
  });
});

describe("refusalDetail — the two FastAPI refusal shapes", () => {
  it("a plain sentence passes through", () => {
    expect(refusalDetail("unknown case 'x'")).toBe("unknown case 'x'");
  });

  it("pydantic rows join their sentences, prefix stripped", () => {
    expect(
      refusalDetail([
        { msg: "Value error, first refusal" },
        { msg: "second refusal" },
      ]),
    ).toBe("first refusal; second refusal");
  });

  it("anything else is honestly unreadable — null, so the status line stands", () => {
    expect(refusalDetail(undefined)).toBeNull();
    expect(refusalDetail([{ nonsense: true }])).toBeNull();
  });
});

describe("the scan-stream URL (slice 3)", () => {
  it("addresses the case's scan under its session resource", () => {
    expect(scanUrlFor("neodent-gm")).toBe("/api/case-sessions/neodent-gm/scan");
  });

  it("URL-encodes the case id — an id is data, never path syntax", () => {
    expect(scanUrlFor("a/b c")).toBe("/api/case-sessions/a%2Fb%20c/scan");
  });
});
