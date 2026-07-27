/**
 * The client's error posture (slice 2 contract: stated words, never a rejected
 * promise) must let pages tell a REFUSING service from a DOWN one — a 404 for a
 * stale bookmark is not an outage, and the banner copy branches on that status
 * (see pages/CaseShell.tsx). These tests pin that the status survives the seam.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteReview,
  fetchArtifactBlob,
  fetchArtifacts,
  fetchAssurance,
  fetchCaseSession,
  fetchRun,
  postConfirm,
  postDetect,
  postPayment,
  postPreview,
  postRelease,
  postReview,
  postRun,
  putChoices,
  putDeclaration,
  putSystem,
  qcImageUrl,
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

  it("system PUTs exactly {model} — the reset it causes is the BFF's, not a field", async () => {
    const calls = capturingFetch();
    await putSystem("case-a", "astra-ev");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/system");
    expect(calls[0]!.init?.method).toBe("PUT");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      model: "astra-ev",
    });
  });

  it("declaration PUTs exactly {variant} to the tooth's own path", async () => {
    const calls = capturingFetch();
    await putDeclaration("case-a", 19, "5020");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/declaration");
    expect(calls[0]!.init?.method).toBe("PUT");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      variant: "5020",
    });
  });

  it("preview POSTs with no body to the tooth's own path — everything derives from the session", async () => {
    const calls = capturingFetch();
    await postPreview("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/preview");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("the review tick POSTs with no body — the act IS the request (AM-8)", async () => {
    const calls = capturingFetch();
    await postReview("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/review");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("the untick DELETEs the same path, also body-less — two-way, never a field", async () => {
    const calls = capturingFetch();
    await deleteReview("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/review");
    expect(calls[0]!.init?.method).toBe("DELETE");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("the run POSTs with no body — the gate is server-minted (AM-8), nothing to claim with", async () => {
    const calls = capturingFetch();
    await postRun("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/run");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("the run facts read GETs the run subresource", async () => {
    const calls = capturingFetch();
    await fetchRun("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/run");
    expect(calls[0]!.init?.method ?? "GET").toBe("GET");
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

describe("the Deliver calls (slice 8) — every gating request names its actor (AM-11)", () => {
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

  it("assurance GETs ungated — the EVIDENCE class needs no operator (AM-1)", async () => {
    const calls = capturingFetch();
    await fetchAssurance("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/assurance");
    expect(calls[0]!.init?.headers).toBeUndefined();
  });

  it("the QC image URL addresses the ungated evidence endpoint, encoded", () => {
    expect(qcImageUrl("case-a", "case-a-19-clockview.png")).toBe(
      "/api/case-sessions/case-a/runs/current/qc/case-a-19-clockview.png",
    );
    expect(qcImageUrl("a/b", "x y.png")).toBe(
      "/api/case-sessions/a%2Fb/runs/current/qc/x%20y.png",
    );
  });

  it("confirm POSTs the acts with the X-Operator header", async () => {
    const calls = capturingFetch();
    await postConfirm("case-a", "Ana Petrova", {
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
    });
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/confirm");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(
      (calls[0]!.init?.headers as Record<string, string>)["X-Operator"],
    ).toBe("Ana Petrova");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
    });
  });

  it("payment POSTs exactly {authorize: true} — the stub's one honest act", async () => {
    const calls = capturingFetch();
    await postPayment("case-a", "Ana Petrova");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/payment");
    expect(
      (calls[0]!.init?.headers as Record<string, string>)["X-Operator"],
    ).toBe("Ana Petrova");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      authorize: true,
    });
  });

  it("release POSTs body-less with the operator — everything else is the session's", async () => {
    const calls = capturingFetch();
    await postRelease("case-a", "Ana Petrova");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/release");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
    expect(
      (calls[0]!.init?.headers as Record<string, string>)["X-Operator"],
    ).toBe("Ana Petrova");
  });

  it("the artifact list GETs with the operator — even listing is disclosure", async () => {
    const calls = capturingFetch(200, {
      run_id: "r",
      files: [],
      withheld_teeth: [],
      withheld_case_files: [],
    });
    await fetchArtifacts("case-a", "Ana Petrova");
    expect(calls[0]!.url).toBe(
      "/api/case-sessions/case-a/runs/current/artifacts",
    );
    expect(
      (calls[0]!.init?.headers as Record<string, string>)["X-Operator"],
    ).toBe("Ana Petrova");
  });

  it("an artifact download fetches with the header and yields the bytes — a bare <a href> could not carry the actor", async () => {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    stubFetch(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(
        new Response(new Blob([new Uint8Array([83, 84, 76])]), { status: 200 }),
      );
    }) as never);
    const result = await fetchArtifactBlob("case-a", "cap-19.stl", "Ana Petrova");
    expect(calls[0]!.url).toBe(
      "/api/case-sessions/case-a/runs/current/artifacts/cap-19.stl",
    );
    expect(
      (calls[0]!.init?.headers as Record<string, string>)["X-Operator"],
    ).toBe("Ana Petrova");
    expect(result.kind).toBe("ok");
  });

  it("an artifact refusal carries the BFF's stated words and status", async () => {
    stubFetch(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ detail: "artifacts are not disclosed for case 'case-a'" }),
          { status: 409, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    const result = await fetchArtifactBlob("case-a", "cap-19.stl", "Ana");
    expect(result).toEqual({
      kind: "error",
      status: 409,
      detail: "HTTP 409 — artifacts are not disclosed for case 'case-a'",
    });
  });
});
