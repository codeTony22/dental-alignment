/**
 * Deliver's surface (plan §4 Deliver; AM-1/AM-11/AM-12), statically rendered per
 * the repo convention: the assurance table in the BFF's worst-first order (flags
 * pinned — the order is SERVED, never re-sorted here), row-expand QC images via
 * the ungated evidence endpoint, the disposition + per-flag acknowledgment
 * controls, the confirm button inert with each missing piece NAMED, the sealed
 * state, the payment button labelled AS a stub, release, the gated artifact list
 * with withheld sites shown open, and the 409 re-confirm flow. The pure rules
 * (blockers, ack-per-flag, wire body, drift detection) are domain/deliver.test.ts's;
 * the header/endpoint wiring is api/client.test.ts's.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { DeliverStageView } from "./DeliverStage";
import { assuranceView, caseSessionDetail, siteView } from "../testing/fixtures";
import type { CaseSessionDetail } from "../api/client";

/** A detail whose session stands where Deliver opens: a done run, sites resolved. */
function deliverableDetail(
  overrides: Partial<CaseSessionDetail["session"]> = {},
): CaseSessionDetail {
  const base = caseSessionDetail({
    sites: [
      siteView({ tooth: 30, status: "flagged", declared_variant: "5020" }),
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
    ],
  });
  return {
    ...base,
    session: { ...base.session, run_state: "done", ...overrides },
  };
}

const CONFIRMED = {
  confirmed: true,
  confirmation: {
    operator: "Ana Petrova",
    at: "2026-07-27T12:00:00+00:00",
    run_id: "20260727-120000-abc123",
    evidence_sha256: "c0ffee".padEnd(64, "0"),
    dispositions: { "30": "release", "19": "release" },
    acknowledged_flags: [30],
  },
};

const PAID = {
  payment_authorized: true,
  payment: { provider: "stub", operator: "Ana Petrova", at: "2026-07-27T12:01:00+00:00" },
};

function view(overrides: Partial<Parameters<typeof DeliverStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <StaticRouter location="/case/case-a/deliver">
      <DeliverStageView
        detail={deliverableDetail()}
        assurance={{ kind: "ok", data: assuranceView() }}
        operatorName="Ana Petrova"
        dispositions={{}}
        acknowledged={[]}
        expanded={[]}
        onOperatorName={() => undefined}
        onDisposition={() => undefined}
        onAcknowledge={() => undefined}
        onToggleExpand={() => undefined}
        onConfirm={() => undefined}
        onPay={() => undefined}
        onRelease={() => undefined}
        onReloadEvidence={() => undefined}
        onDownload={() => undefined}
        {...overrides}
      />
    </StaticRouter>,
  );
}

describe("the assurance table — worst-first as SERVED, flags pinned (AM-12)", () => {
  it("renders rows in the payload's order and marks the flagged one", () => {
    const html = view();
    const first = html.indexOf('data-tooth="30"');
    const second = html.indexOf('data-tooth="19"');
    expect(first).toBeGreaterThan(-1);
    expect(second).toBeGreaterThan(first); // the served order, verbatim
    expect(html).toContain('data-role="assurance-row" data-tooth="30" data-status="flagged"');
  });

  it("a row carries the evidence: numbers, gate words, clamp, rotation honesty", () => {
    const html = view();
    expect(html).toContain("0.07"); // rim agreement
    expect(html).toContain("0.43"); // deviation RMS
    expect(html).toContain("0.71"); // deviation p90
    expect(html).toContain("rim-seat");
    expect(html).toContain("ROTATION could not be verified"); // the gate's words
    expect(html).toContain("rotation unverified"); // the honesty badge
    expect(html).toContain("declared 5020"); // identity: declared vs identified
    expect(html).toContain("measured 5020");
  });

  it("each numeric's industry reference renders beside it, verbatim", () => {
    expect(view()).toContain("scan-body agreement literature");
  });

  it("row-expand shows the site's QC images lazily via the evidence endpoint", () => {
    const collapsed = view();
    expect(collapsed).not.toContain("case-a-30-clockview.png");
    const html = view({ expanded: [30] });
    expect(html).toContain(
      'src="/api/case-sessions/case-a/runs/current/qc/case-a-30-clockview.png"',
    );
    expect(html).toContain(
      'src="/api/case-sessions/case-a/runs/current/qc/case-a-30-deviation.png"',
    );
    expect(html).toContain('loading="lazy"');
  });

  it("an assurance fetch error states itself instead of an empty table", () => {
    const html = view({
      assurance: { kind: "error", detail: "HTTP 404 — no completed current run" },
    });
    expect(html).toContain('data-role="assurance-error"');
    expect(html).toContain("no completed current run");
  });
});

describe("dispositions and the per-flag acknowledgment (AM-12)", () => {
  it("every row carries release/withhold controls; only flagged rows the ack tick", () => {
    const html = view();
    expect(html.match(/data-role="disposition-release"/g)).toHaveLength(2);
    expect(html.match(/data-role="disposition-withhold"/g)).toHaveLength(2);
    expect(html.match(/data-role="acknowledge-flag"/g)).toHaveLength(1);
  });

  it("withholding the flagged row retires its acknowledgment tick", () => {
    const html = view({ dispositions: { 30: "withhold" } });
    expect(html).not.toContain('data-role="acknowledge-flag"');
  });
});

describe("the confirm button — inert until complete, each missing piece named", () => {
  it("disabled with the blockers listed under it", () => {
    const html = view({ operatorName: "" });
    expect(html).toContain('data-role="confirm"');
    expect(html).toContain("disabled");
    expect(html).toContain('data-role="confirm-blockers"');
    expect(html).toContain("your name — the record names its actor");
    expect(html).toContain("tooth 30 needs a disposition");
    expect(html).toContain("tooth 19 needs a disposition");
    expect(html).toContain("tooth 30 is flagged — releasing it needs its own acknowledgment");
  });

  it("armed once every piece is present — no blockers named", () => {
    const html = view({
      dispositions: { 30: "release", 19: "release" },
      acknowledged: [30],
    });
    expect(html).not.toContain('data-role="confirm-blockers"');
  });
});

describe("the sealed state after confirmation", () => {
  it("shows who confirmed, when, and the evidence hash", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="sealed-confirmation"');
    expect(html).toContain("Confirmed by Ana Petrova");
    expect(html).toContain("2026-07-27T12:00:00+00:00");
    expect(html).toContain("c0ffee".padEnd(64, "0"));
  });
});

describe("the payment stub — labelled AS a stub (AM-11)", () => {
  it("the button says stub and waits for the confirmation", () => {
    const html = view();
    expect(html).toContain('data-role="payment-stub"');
    expect(html).toContain("Authorize payment (stub)");
    expect(html).toContain("disabled"); // unconfirmed: the chain has an order
  });

  it("once paid, the stub's record renders — provider named", () => {
    const html = view({ detail: deliverableDetail({ ...CONFIRMED, ...PAID }) });
    expect(html).toContain('data-role="payment-done"');
    expect(html).toContain("stub");
    expect(html).toContain("Ana Petrova");
  });
});

describe("release — the disclosure act", () => {
  it("inert until the chain is complete, the remaining steps named", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="release"');
    expect(html).toContain("the payment authorization (stub)");
  });

  it("after release the record renders and the artifacts section takes over", () => {
    const html = view({
      detail: deliverableDetail({
        ...CONFIRMED,
        ...PAID,
        released: true,
        release: {
          operator: "Ana Petrova",
          at: "2026-07-27T12:02:00+00:00",
          run_id: "20260727-120000-abc123",
          evidence_sha256: "c0ffee".padEnd(64, "0"),
          released_teeth: [19],
        },
      }),
      artifacts: {
        kind: "ok",
        data: {
          run_id: "20260727-120000-abc123",
          files: ["case-a-19-healingcap-aligned.stl"],
          withheld_teeth: [30],
          withheld_case_files: ["case-a-upper-overlay.stl", "case-a-manifest.json"],
        },
      },
    });
    expect(html).toContain('data-role="released"');
    expect(html).toContain('data-role="artifact-download" data-file="case-a-19-healingcap-aligned.stl"');
    // the withheld site is SHOWN as withheld, with its open status beside it
    expect(html).toContain('data-role="withheld-site"');
    expect(html).toContain("Tooth 30");
    expect(html).toContain("withheld");
    expect(html).toContain("flagged"); // its open status, from the detail's sites
    // the case-wide files the BFF held back are SHOWN held back, by name — the
    // surface never pretends a partial release shipped the whole package
    expect(html).toContain('data-role="withheld-case-files"');
    expect(html).toContain("case-a-upper-overlay.stl");
    expect(html).toContain("case-a-manifest.json");
    // and nothing offers to download what was not released
    expect(html).not.toContain('data-file="case-a-upper-overlay.stl"');
  });

  it("a full release lists no held-back case files and says nothing about them", () => {
    const html = view({
      detail: deliverableDetail({
        ...CONFIRMED,
        ...PAID,
        released: true,
        release: {
          operator: "Ana Petrova",
          at: "2026-07-27T12:02:00+00:00",
          run_id: "20260727-120000-abc123",
          evidence_sha256: "c0ffee".padEnd(64, "0"),
          released_teeth: [19, 30],
        },
      }),
      artifacts: {
        kind: "ok",
        data: {
          run_id: "20260727-120000-abc123",
          files: ["case-a-19-healingcap-aligned.stl", "case-a-upper-overlay.stl"],
          withheld_teeth: [],
          withheld_case_files: [],
        },
      },
    });
    expect(html).toContain('data-file="case-a-upper-overlay.stl"');
    expect(html).not.toContain('data-role="withheld-case-files"');
  });
});

describe("the 409 re-confirm flow", () => {
  it("renders the BFF's words and the reload affordance", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      staleWords:
        "HTTP 409 — the case changed since it was confirmed — re-confirm over the current evidence",
      dispositions: { 30: "release", 19: "release" },
      acknowledged: [30],
    });
    expect(html).toContain('data-role="reconfirm"');
    expect(html).toContain("changed since it was confirmed");
    expect(html).toContain("Reload the evidence");
  });
});

describe("phases and errors state themselves", () => {
  it("a confirming phase names the work", () => {
    expect(
      view({
        phase: "confirming",
        dispositions: { 30: "release", 19: "release" },
        acknowledged: [30],
      }),
    ).toContain("Sealing the confirmation…");
  });

  it("an action refusal renders in the backend's words", () => {
    const html = view({ actionError: "HTTP 422 — releasing a flagged site requires its own acknowledgment" });
    expect(html).toContain('data-role="deliver-error"');
    expect(html).toContain("requires its own acknowledgment");
  });
});
