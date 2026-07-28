/**
 * Deliver's DISPLAY rules (plan §4 Deliver; AM-12), pure and pinned: the confirm
 * button's inertia derivation (each missing piece NAMED — flow's blockedReason
 * doctrine at the button), the acknowledgment-per-flag rule as the UI enforces it
 * locally (the BFF re-refuses it server-side either way), the wire body assembly,
 * and the 409 re-confirm detection.
 *
 * The operator-name store's tests are GONE with the store (client 2026-07-27: "WE
 * dont need operator name the checkmark is sufficient") — see the module's note.
 */
import { describe, expect, it } from "vitest";
import {
  ackRequired,
  confirmBlockers,
  confirmWireBody,
  isEvidenceDrift409,
  releaseBlockers,
} from "./deliver";
import {
  assuranceSite,
  assuranceView,
  caseSessionDetail,
  flaggedAssuranceSite,
} from "../testing/fixtures";

const TWO_SITES = assuranceView(); // flagged tooth 30 pinned first, ready tooth 19

describe("confirmBlockers — inert until complete, each missing piece named", () => {
  it("names every undispositioned site and nothing else — NO name is ever asked for", () => {
    const blockers = confirmBlockers(TWO_SITES, {}, []);
    expect(blockers).toEqual([
      "tooth 30 needs a disposition — release or withhold",
      "tooth 19 needs a disposition — release or withhold",
      "tooth 30 is flagged — releasing it needs its own acknowledgment",
    ]);
    // the removed blocker, pinned as an absence (client 2026-07-27)
    expect(blockers.join(" ")).not.toContain("name");
  });

  it("a flagged site dispositioned RELEASE needs its own acknowledgment", () => {
    const blockers = confirmBlockers(TWO_SITES, { 30: "release", 19: "release" }, []);
    expect(blockers).toEqual([
      "tooth 30 is flagged — releasing it needs its own acknowledgment",
    ]);
  });

  it("acknowledging the flag clears the last blocker", () => {
    expect(
      confirmBlockers(TWO_SITES, { 30: "release", 19: "release" }, [30]),
    ).toEqual([]);
  });

  it("a WITHHELD flagged site needs no acknowledgment — there is no release to acknowledge", () => {
    expect(
      confirmBlockers(TWO_SITES, { 30: "withhold", 19: "release" }, []),
    ).toEqual([]);
  });

  it("two flagged releases each demand their own acknowledgment (AM-12: row by row)", () => {
    const view = assuranceView({
      sites: [
        flaggedAssuranceSite({ tooth: 30 }),
        flaggedAssuranceSite({ tooth: 19 }),
      ],
    });
    const blockers = confirmBlockers(view, { 30: "release", 19: "release" }, [30]);
    expect(blockers).toEqual([
      "tooth 19 is flagged — releasing it needs its own acknowledgment",
    ]);
  });
});

describe("ackRequired — which rows render the acknowledgment tick", () => {
  it("only a flagged row dispositioned release", () => {
    const flagged = flaggedAssuranceSite();
    expect(ackRequired(flagged, "release")).toBe(true);
    expect(ackRequired(flagged, "withhold")).toBe(false);
    expect(ackRequired(flagged, undefined)).toBe(true); // undecided still shows it
    expect(ackRequired(assuranceSite(), "release")).toBe(false);
  });
});

describe("confirmWireBody — the acts, wire-shaped", () => {
  it("keys dispositions by tooth-as-string and lists acknowledged flags", () => {
    expect(confirmWireBody({ 30: "release", 19: "withhold" }, [30])).toEqual({
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
    });
  });
});

describe("releaseBlockers — the chain's remaining steps, named", () => {
  it("names confirmation then payment", () => {
    const detail = caseSessionDetail();
    expect(releaseBlockers(detail.session)).toEqual([
      "the confirmation — confirm over the evidence first",
      "the payment authorization (stub)",
    ]);
  });

  it("empties when the chain is complete", () => {
    const detail = caseSessionDetail();
    expect(
      releaseBlockers({
        ...detail.session,
        confirmed: true,
        payment_authorized: true,
      }),
    ).toEqual([]);
  });
});

describe("the 409 re-confirm detection", () => {
  it("recognizes the BFF's changed-since-confirmed words on a 409", () => {
    expect(
      isEvidenceDrift409({
        kind: "error",
        status: 409,
        detail: "HTTP 409 — the case changed since it was confirmed — re-confirm over the current evidence",
      }),
    ).toBe(true);
  });

  it("any other refusal is not the re-confirm flow", () => {
    expect(
      isEvidenceDrift409({ kind: "error", status: 409, detail: "HTTP 409 — a run is already in flight" }),
    ).toBe(false);
    expect(
      isEvidenceDrift409({ kind: "error", detail: "ECONNREFUSED" }),
    ).toBe(false);
    expect(isEvidenceDrift409({ kind: "ok", data: null })).toBe(false);
  });
});

describe("the operator name store, DELETED (client 2026-07-27)", () => {
  it("the module exports no name loader or saver at all", async () => {
    // an absence test, deliberately: the three round-trip tests that used to live
    // here proved a sessionStorage name survived a reload. Nothing reads a name
    // now, and a store nobody reads is a place for a stale one to hide
    const module = await import("./deliver");
    expect(Object.keys(module)).not.toContain("loadOperator");
    expect(Object.keys(module)).not.toContain("saveOperator");
  });
});
