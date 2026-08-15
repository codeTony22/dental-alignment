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
  postCheckoutReturn,
  postConfirm,
  postDetect,
  postPayment,
  postPreview,
  postRelease,
  postRePreview,
  postReview,
  postAdjustDecision,
  postRun,
  putChoices,
  putDeclaration,
  putRimPoints,
  deleteRimPoints,
  putSystem,
  previewMeshUrl,
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
      // the raw `detail` rides along (slice 6): almost every refusal is a sentence and
      // this is that sentence again, but the ONE structured refusal — the best-fit's
      // already-optimal PASS — is only reachable through it
      refusal: "unknown case 'gone-case'",
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

  it("rim-points PUTs {points} to the tooth's own rim-points path (task #33)", async () => {
    const calls = capturingFetch();
    await putRimPoints("case-a", 19, [
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9],
    ]);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/rim-points");
    expect(calls[0]!.init?.method).toBe("PUT");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      points: [
        [1, 2, 3],
        [4, 5, 6],
        [7, 8, 9],
      ],
    });
  });

  it("rim-points DELETEs the same path, body-less — two-way like the review tick", async () => {
    const calls = capturingFetch();
    await deleteRimPoints("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/rim-points");
    expect(calls[0]!.init?.method).toBe("DELETE");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("preview POSTs with no body to the tooth's own path — everything derives from the session", async () => {
    const calls = capturingFetch();
    await postPreview("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/preview");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
  });

  it("re-preview POSTs with no body to the tooth's own path — everything it reads is the run directory's", async () => {
    // gap `re-preview-a-site-without-applying-a-tool` (2026-07-31): the route is
    // structurally body-less (it defines no request model), and `postRePreview`
    // shipped ahead of any UI caller with no pin of its own — this closes that.
    const calls = capturingFetch();
    await postRePreview("case-a", 19);
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/sites/19/re-preview");
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

  it("the fork POSTs exactly the decision — an act, with nothing else to claim", async () => {
    // client 2026-07-27 #3: "Delivery vs Skip Adjustments". The body carries one
    // word; the decision gates nothing, so there is no site list or reason to send
    const calls = capturingFetch();
    await postAdjustDecision("case-a", "skip");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/adjust-decision");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({ decision: "skip" });
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
      refusal: [
        {
          type: "value_error",
          loc: ["body", "jaw"],
          msg: "Value error, jaw must be one of upper, lower, got 'sideways'",
          input: "sideways",
        },
      ],
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

describe("the Deliver calls (slice 8) — no actor rides on any of them", () => {
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

  it("assurance GETs ungated — the EVIDENCE class is visible before anything (AM-1)", async () => {
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

  it("the preview-mesh URL addresses the ungated evidence endpoint, encoded", () => {
    expect(previewMeshUrl("case-a", "case-a-arch-with-healingcaps.stl")).toBe(
      "/api/case-sessions/case-a/runs/current/preview-mesh/case-a-arch-with-healingcaps.stl",
    );
    expect(previewMeshUrl("a/b", "x y.stl")).toBe(
      "/api/case-sessions/a%2Fb/runs/current/preview-mesh/x%20y.stl",
    );
  });

  it("confirm POSTs the acts and NOTHING about who sent them", async () => {
    // the X-Operator header is gone from this client entirely (client 2026-07-27:
    // "WE dont need operator name the checkmark is sufficient") — asserted as an
    // absence so nobody re-adds it as a "missing header" fix
    const calls = capturingFetch();
    await postConfirm("case-a", {
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
      terms_accepted: true,
    });
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/confirm");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
      terms_accepted: true,
    });
  });

  it("payment POSTs exactly {authorize: true} — the stub's one honest act", async () => {
    const calls = capturingFetch();
    await postPayment("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/payment");
    expect(calls[0]!.init?.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      authorize: true,
    });
  });

  it("names the invoice it read — a DIGEST, never an amount (audit 2026-07-31)", async () => {
    // nothing bound the price the operator READ to the price they were CHARGED: a
    // rival turnaround PUT moved the server price between the render and the click
    // and the charge landed 200 at a figure no surface displayed. The precondition
    // is the document's opaque identity; an amount on this wire would let a client
    // pay $0 for a released case.
    const calls = capturingFetch();
    await postPayment("case-a", "f".repeat(64));
    const body = JSON.parse(calls[0]!.init?.body as string);
    expect(body).toEqual({ authorize: true, invoice_fingerprint: "f".repeat(64) });
    expect(Object.keys(body)).not.toContain("amount_cents");
  });

  it("release POSTs body-less and header-less — everything it consumes is the session's", async () => {
    const calls = capturingFetch();
    await postRelease("case-a");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/release");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(calls[0]!.init?.body).toBeUndefined();
    expect(calls[0]!.init?.headers).toBeUndefined();
  });

  it("the checkout return POSTs only the reference — no field could claim success", async () => {
    const calls = capturingFetch();
    await postCheckoutReturn("case-a", "chk_abc123");
    expect(calls[0]!.url).toBe("/api/case-sessions/case-a/checkout/return");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(JSON.parse(calls[0]!.init?.body as string)).toEqual({
      reference: "chk_abc123",
    });
  });

  it("the artifact list GETs behind the release gate alone — even listing is disclosure", async () => {
    const calls = capturingFetch(200, {
      run_id: "r",
      files: [],
      withheld_teeth: [],
      withheld_case_files: [],
    });
    await fetchArtifacts("case-a");
    expect(calls[0]!.url).toBe(
      "/api/case-sessions/case-a/runs/current/artifacts",
    );
    expect(calls[0]!.init?.headers).toBeUndefined();
  });

  it("an artifact download fetches the bytes — a fetch, not a bare <a href>, because the endpoint is gated", async () => {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    stubFetch(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(
        new Response(new Blob([new Uint8Array([83, 84, 76])]), { status: 200 }),
      );
    }) as never);
    const result = await fetchArtifactBlob("case-a", "cap-19.stl");
    expect(calls[0]!.url).toBe(
      "/api/case-sessions/case-a/runs/current/artifacts/cap-19.stl",
    );
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
    const result = await fetchArtifactBlob("case-a", "cap-19.stl");
    expect(result).toEqual({
      kind: "error",
      status: 409,
      detail: "HTTP 409 — artifacts are not disclosed for case 'case-a'",
    });
  });
});
