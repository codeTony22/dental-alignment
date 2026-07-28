/**
 * DECLARE'S DISPLAY RULES (plan §4 Declare / AM-8, slice 5a), pinned framework-free:
 * which system cards render (non-legacy groups; the effective one attributed to the
 * server's `source`, never a local comparison), how variant cards split current from
 * superseded, the dims line, the visible-reset confirmation WORDS with the count in
 * them, and the active-site defaulting the queue and stage share.
 */
import { describe, expect, it, vi } from "vitest";
import type { ApiResult, SitePreviewPayload } from "../api/client";
import {
  caseSessionDetail,
  catalogEntry,
  catalogGroup,
  runnableDetail,
  sitePreviewPayload,
  siteView,
} from "../testing/fixtures";
import {
  activeSiteFrom,
  claimSlot,
  createPreviewFirer,
  declaredLabel,
  dimsLabel,
  indicesFrom,
  paneNotices,
  positionsFrom,
  previewKeyFor,
  resetCount,
  reviewTick,
  runKeyFor,
  settleSlot,
  shouldAutoPreview,
  shouldAutoRun,
  switchWords,
  systemCards,
  variantMeshUrl,
  variantShelves,
  type PostPreviewFn,
  type PreviewSlots,
} from "./declare";

const twoSystems = caseSessionDetail({
  catalog: {
    groups: [
      catalogGroup("conical-4x4"),
      catalogGroup("astra-ev", [catalogEntry({ id: "3010", variant: "3010" })]),
      catalogGroup("old-parts-library", [catalogEntry({ id: "4040" })], true),
    ],
    constructions: [],
  },
});

describe("systemCards", () => {
  it("lists non-legacy groups only — a legacy shelf is not a declarable system", () => {
    expect(systemCards(twoSystems).map((c) => c.model)).toEqual([
      "conical-4x4",
      "astra-ev",
    ]);
  });

  it("attributes the effective card from the server's source, with the suggested tag", () => {
    const cards = systemCards(twoSystems);
    expect(cards[0]).toMatchObject({
      model: "conical-4x4",
      effective: true,
      suggested: true, // system.source === "suggested" — the server said WHICH
    });
    expect(cards[1]).toMatchObject({ effective: false, suggested: false });
  });

  it("a declared system carries no suggested tag — it is the operator's act", () => {
    const declared = caseSessionDetail({
      ...twoSystems,
      system: { effective_model: "astra-ev", source: "declared" },
    });
    const cards = systemCards(declared);
    expect(cards.find((c) => c.model === "astra-ev")).toMatchObject({
      effective: true,
      suggested: false,
    });
  });

  it("drops a group whose model is not a string instead of rendering a lie", () => {
    const noisy = caseSessionDetail({
      catalog: { groups: [{ legacy: false }, catalogGroup()], constructions: [] },
    });
    expect(systemCards(noisy).map((c) => c.model)).toEqual(["conical-4x4"]);
  });
});

describe("variantShelves — the active system's cards", () => {
  const detail = caseSessionDetail({
    catalog: {
      groups: [
        catalogGroup("conical-4x4", [
          catalogEntry({ id: "5020", rim_diameter_mm: 5.0, height_mm: 2.0 }),
          catalogEntry({
            id: "superseded-2025-01-01--4010",
            variant: "4010",
            flags: ["superseded"],
            rim_diameter_mm: 4.0,
            height_mm: 1.0,
          }),
          { flags: [] }, // no id — undeclarable, dropped
        ]),
      ],
      constructions: [],
    },
  });

  it("splits current from superseded by the catalog's own flag", () => {
    const shelves = variantShelves(detail);
    expect(shelves.current.map((c) => c.id)).toEqual(["5020"]);
    expect(shelves.superseded.map((c) => c.id)).toEqual([
      "superseded-2025-01-01--4010",
    ]);
  });

  it("cards carry the catalog's Ø × height line", () => {
    const [card] = variantShelves(detail).current;
    expect(card?.dims).toBe("Ø 5.0 × 2.0 mm");
  });

  it("an effective system with no group yields empty shelves, never a throw", () => {
    const empty = caseSessionDetail({
      system: { effective_model: null, source: "none" },
    });
    expect(variantShelves(empty)).toEqual({ current: [], superseded: [] });
  });
});

describe("dimsLabel", () => {
  it("formats both numbers, and is honest when the catalog could not measure", () => {
    expect(dimsLabel(4.5, 3.1)).toBe("Ø 4.5 × 3.1 mm");
    expect(dimsLabel(null, 3.1)).toBe("dimensions unavailable");
    expect(dimsLabel(4.5, null)).toBe("dimensions unavailable");
  });
});

describe("the visible-reset confirmation (AM-8)", () => {
  it("counts sites that would lose their declaration", () => {
    const detail = caseSessionDetail({
      sites: [
        siteView({ tooth: 19, status: "declared", declared_variant: "5020" }),
        siteView({ tooth: 30 }),
        siteView({ tooth: 31, status: "declared", declared_variant: "6030" }),
      ],
    });
    expect(resetCount(detail)).toBe(2);
  });

  it("the words name the target system and the reset count", () => {
    const words = switchWords("astra-ev", 2);
    expect(words).toContain("astra-ev");
    expect(words).toContain("resets 2 declared sites");
  });

  it("one site reads singular — pedantry the operator will notice", () => {
    expect(switchWords("astra-ev", 1)).toContain("resets 1 declared site —");
  });
});

describe("activeSiteFrom — the queue and the stage share one active site", () => {
  const sites = [siteView({ tooth: 19 }), siteView({ tooth: 30 })];

  it("picks the clicked tooth", () => {
    expect(activeSiteFrom(sites, 30)?.tooth).toBe(30);
  });

  it("defaults to the first site when nothing was clicked yet", () => {
    expect(activeSiteFrom(sites, null)?.tooth).toBe(19);
  });

  it("a stale tooth (re-detected case) falls back to the first site", () => {
    expect(activeSiteFrom(sites, 42)?.tooth).toBe(19);
  });

  it("no sites at all is an honest null", () => {
    expect(activeSiteFrom([], null)).toBeNull();
  });
});

describe("declaredLabel", () => {
  it("names the declared variant, or an honest dash", () => {
    expect(declaredLabel(siteView({ declared_variant: "5020" }))).toBe("5020");
    expect(declaredLabel(siteView())).toBe("—");
  });
});

// --- the panes' rules (slice 5b) ------------------------------------------------------

const previewable = caseSessionDetail({
  sites: [siteView({ tooth: 19, status: "declared", declared_variant: "5020" })],
  catalog: {
    groups: [catalogGroup("conical-4x4", [catalogEntry({ id: "5020" })])],
    constructions: [],
  },
  choices: {
    construction_path: "dess/a.stl",
    jaw: "lower",
    gingival_offset_mm: 0.2,
    gingival_offset_default_mm: 0.2,
    effective_construction: { value: "dess/a.stl", source: "chosen" },
    effective_jaw: { value: "lower", source: "chosen" },
    effective_relief: { value: 0.2, source: "chosen" },
    complete: true,
  },
});

describe("variantMeshUrl — pane 1 follows the SERVED url, never assembles one", () => {
  it("finds the declared variant's mesh_url on the effective system's rows", () => {
    expect(variantMeshUrl(previewable, "5020")).toBe(
      "/api/library/conical-4x4/5020/mesh",
    );
  });

  it("no variant, unknown variant, or a row without a url are all an honest null", () => {
    expect(variantMeshUrl(previewable, null)).toBeNull();
    expect(variantMeshUrl(previewable, "9999")).toBeNull();
    const urlless = caseSessionDetail({
      ...previewable,
      catalog: {
        groups: [
          catalogGroup("conical-4x4", [
            catalogEntry({ id: "5020", mesh_url: undefined }),
          ]),
        ],
        constructions: [],
      },
    });
    expect(variantMeshUrl(urlless, "5020")).toBeNull();
  });
});

describe("previewKeyFor — the preview's identity, from server facts only", () => {
  it("names case, tooth, system, variant and all three choices", () => {
    expect(previewKeyFor(previewable, 19)).toBe(
      "case-a|19|conical-4x4|5020|dess/a.stl|lower|0.2",
    );
  });

  it("is null while the session cannot preview — no tooth, no declaration, or incomplete choices", () => {
    expect(previewKeyFor(previewable, null)).toBeNull();
    expect(previewKeyFor(previewable, 42)).toBeNull();
    const undeclared = caseSessionDetail({
      ...previewable,
      sites: [siteView({ tooth: 19, status: "detected" })],
    });
    expect(previewKeyFor(undeclared, 19)).toBeNull();
    const incomplete = caseSessionDetail({
      ...previewable,
      choices: { ...previewable.choices, jaw: null, complete: false },
    });
    expect(previewKeyFor(incomplete, 19)).toBeNull();
  });

  it("a different variant or choice is a different key — the re-fire trigger", () => {
    const other = caseSessionDetail({
      ...previewable,
      choices: {
        ...previewable.choices,
        gingival_offset_mm: 0.1,
        effective_relief: { value: 0.1, source: "chosen" },
      },
    });
    expect(previewKeyFor(other, 19)).not.toBe(previewKeyFor(previewable, 19));
  });

  it("a fresh case previews on its suggestions — no Intake visit needed (client 2026-07-27)", () => {
    // the client's complaint, client-side: declaration only, raw choices all None —
    // the EFFECTIVE values mint the key, and it EQUALS the explicitly-pinned key,
    // so pinning a prefill later refires no identical physics
    const fresh = caseSessionDetail({
      ...previewable,
      choices: {
        construction_path: null,
        jaw: null,
        gingival_offset_mm: null,
        gingival_offset_default_mm: 0.2,
        effective_construction: { value: "dess/a.stl", source: "suggested" },
        effective_jaw: { value: "lower", source: "suggested" },
        effective_relief: { value: 0.2, source: "default" },
        complete: true,
      },
    });
    expect(previewKeyFor(fresh, 19)).toBe(previewKeyFor(previewable, 19));
  });
});

describe("shouldAutoPreview — keyed on facts, no render-loop refiring", () => {
  it("fires when a preview is possible and the slot answers for another key or none", () => {
    expect(shouldAutoPreview({ key: "k1", slotKey: null })).toBe(true);
    expect(shouldAutoPreview({ key: "k2", slotKey: "k1" })).toBe(true);
  });

  it("never fires without a key, and never re-fires over a slot holding this key", () => {
    expect(shouldAutoPreview({ key: null, slotKey: null })).toBe(false);
    // computing, ready AND error slots all hold the key — an errored preview waits
    // for the operator's explicit retry, not a render loop
    expect(shouldAutoPreview({ key: "k1", slotKey: "k1" })).toBe(false);
  });
});

describe("the wire mesh flatteners", () => {
  it("points flatten to xyz triples, faces to index triples", () => {
    expect(
      Array.from(positionsFrom([[1, 2, 3], [4, 5, 6]])),
    ).toEqual([1, 2, 3, 4, 5, 6]);
    const indices = indicesFrom([[0, 1, 2]]);
    expect(indices).toBeInstanceOf(Uint32Array);
    expect(Array.from(indices)).toEqual([0, 1, 2]);
  });
});

describe("paneNotices — honest words, never a blank canvas", () => {
  const base = {
    site: siteView({ tooth: 19, status: "declared", declared_variant: "5020" }),
    choicesComplete: true,
    partMeshKnown: true,
    partError: null,
    scanError: null,
    scanEmpty: false,
    previewPhase: "ready" as const,
    previewError: null,
  };

  it("all three panes are quiet when everything answers", () => {
    expect(paneNotices(base)).toEqual({ part: null, scan: null, union: null });
  });

  it("no site selected states it on every pane", () => {
    const notices = paneNotices({ ...base, site: null });
    expect(notices.part).toContain("No site selected");
    expect(notices.scan).toContain("No site selected");
    expect(notices.union).toContain("No site selected");
  });

  it("an undeclared site asks for the declaration on part and union", () => {
    const notices = paneNotices({
      ...base,
      site: siteView({ tooth: 19, status: "detected" }),
    });
    expect(notices.part).toContain("Declare this site's cap variant");
    expect(notices.union).toContain("Declare this site's cap variant");
  });

  it("incomplete choices point back at Intake on the union pane", () => {
    const notices = paneNotices({
      ...base,
      choicesComplete: false,
      previewPhase: "idle",
    });
    expect(notices.union).toContain("case-level choices at Intake");
  });

  it("a preview error surfaces in the backend's words; computing is NOT a notice", () => {
    expect(
      paneNotices({
        ...base,
        previewPhase: "error",
        previewError: "HTTP 409 — no confirmed site could be aligned",
      }).union,
    ).toContain("no confirmed site could be aligned");
    expect(paneNotices({ ...base, previewPhase: "computing" }).union).toBeNull();
  });

  it("the scan pane states its own trouble — a missing centre or an empty crop", () => {
    expect(
      paneNotices({
        ...base,
        site: siteView({ tooth: 19, declared_variant: "5020", center: null }),
      }).scan,
    ).toContain("no centre to frame");
    expect(paneNotices({ ...base, scanEmpty: true }).scan).toContain(
      "No scan surface",
    );
  });
});

describe("reviewTick — enabled only over a preview (AM-8)", () => {
  it("previewed = an untitcked, enabled tick; ready = ticked", () => {
    expect(
      reviewTick(siteView({ status: "previewed", declared_variant: "5020" })),
    ).toEqual({ enabled: true, ticked: false, reason: null });
    expect(
      reviewTick(siteView({ status: "ready", declared_variant: "5020" })),
    ).toEqual({ enabled: true, ticked: true, reason: null });
  });

  it("anything short of a preview is inert WITH its reason — a tick over nothing", () => {
    for (const status of ["detected", "declared", "flagged", "adjusted"] as const) {
      const tick = reviewTick(siteView({ status }));
      expect(tick.enabled).toBe(false);
      expect(tick.reason).toContain("preview this site first");
    }
    expect(reviewTick(null).enabled).toBe(false);
  });
});

// --- the preview firer's async guards (5b review M1, landed 5c) ----------------------

/** A slots holder shaped like setState, so the firer runs exactly as wired. */
function slotHarness() {
  let slots: PreviewSlots = {};
  return {
    get: () => slots,
    update: (fn: (prev: PreviewSlots) => PreviewSlots) => {
      slots = fn(slots);
    },
  };
}

/** An injectable postPreview whose settlement the TEST controls — the seam the 5b
 * review asked for: the guards get exercised against real async ordering. */
function deferredPost() {
  const pending: Array<{
    tooth: number;
    resolve: (result: ApiResult<SitePreviewPayload>) => void;
  }> = [];
  const post: PostPreviewFn = (_caseId, tooth) =>
    new Promise((resolve) => {
      pending.push({ tooth, resolve });
    });
  return { post, pending };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("the preview firer — the DOUBLE-POST guard", () => {
  it("a doubled effect run for the same (tooth, key) POSTs exactly once", () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const firer = createPreviewFirer({ caseId: "case-a", post, update: slots.update });
    expect(firer.maybeFire(19, "k1")).toBe(true);
    // React strict/re-render double-invocation: the slot state lags a render
    // behind, so the guard must be synchronous — the second ask finds the claim
    expect(firer.maybeFire(19, "k1")).toBe(false);
    expect(pending.length).toBe(1);
    // a NEW key (re-declaration, choices change) is a new ask
    expect(firer.maybeFire(19, "k2")).toBe(true);
    expect(pending.length).toBe(2);
    // an errored slot does not auto-refire either — the retry is fire(), explicit
    expect(firer.maybeFire(19, "k2")).toBe(false);
  });

  it("sites fire independently — per-site non-blocking", () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const firer = createPreviewFirer({ caseId: "case-a", post, update: slots.update });
    expect(firer.maybeFire(19, "k19")).toBe(true);
    expect(firer.maybeFire(30, "k30")).toBe(true);
    expect(pending.map((p) => p.tooth)).toEqual([19, 30]);
    expect(slots.get()[19]?.state).toBe("computing");
    expect(slots.get()[30]?.state).toBe("computing");
  });
});

describe("the preview firer — STALE-RESPONSE rejection", () => {
  it("an older ask settling late never overwrites the newer claim", async () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const firer = createPreviewFirer({ caseId: "case-a", post, update: slots.update });
    firer.fire(19, "old-key");
    firer.fire(19, "new-key"); // a re-declaration re-claims the slot synchronously
    expect(slots.get()[19]).toEqual({ key: "new-key", state: "computing" });
    // the OLD physics answers late — its payload must be discarded
    pending[0]!.resolve({ kind: "ok", data: sitePreviewPayload() });
    await flush();
    expect(slots.get()[19]).toEqual({ key: "new-key", state: "computing" });
    // the CURRENT ask settles normally
    const payload = sitePreviewPayload({ tooth: 19 });
    pending[1]!.resolve({ kind: "ok", data: payload });
    await flush();
    expect(slots.get()[19]).toEqual({ key: "new-key", state: "ready", payload });
  });

  it("an error settles with the backend's words; a stale error is discarded too", async () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const firer = createPreviewFirer({ caseId: "case-a", post, update: slots.update });
    firer.fire(19, "k1");
    pending[0]!.resolve({ kind: "error", detail: "HTTP 409 — no seat" });
    await flush();
    expect(slots.get()[19]).toEqual({
      key: "k1",
      state: "error",
      error: "HTTP 409 — no seat",
    });
    firer.fire(19, "k2");
    firer.fire(19, "k3");
    pending[1]!.resolve({ kind: "error", detail: "stale trouble" });
    await flush();
    expect(slots.get()[19]).toEqual({ key: "k3", state: "computing" });
  });

  it("an unmounted container writes nothing and settles nobody", async () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const onSettled = vi.fn();
    let live = true;
    const firer = createPreviewFirer({
      caseId: "case-a",
      post,
      update: slots.update,
      isLive: () => live,
      onSettled,
    });
    firer.fire(19, "k1");
    live = false; // the container unmounted mid-flight
    pending[0]!.resolve({ kind: "ok", data: sitePreviewPayload() });
    await flush();
    expect(slots.get()[19]).toEqual({ key: "k1", state: "computing" });
    expect(onSettled).not.toHaveBeenCalled();
  });

  it("onSettled fires with the result — the container's detail re-read hook", async () => {
    const { post, pending } = deferredPost();
    const slots = slotHarness();
    const onSettled = vi.fn();
    const firer = createPreviewFirer({
      caseId: "case-a",
      post,
      update: slots.update,
      onSettled,
    });
    firer.fire(19, "k1");
    const payload = sitePreviewPayload();
    pending[0]!.resolve({ kind: "ok", data: payload });
    await flush();
    expect(onSettled).toHaveBeenCalledWith({ kind: "ok", data: payload });
  });

  it("the pure rules underneath: settleSlot returns prev untouched for a stale key", () => {
    const claimed = claimSlot({}, 19, "new-key");
    const settled = settleSlot(claimed, 19, "old-key", {
      kind: "ok",
      data: sitePreviewPayload(),
    });
    expect(settled).toBe(claimed); // the SAME reference — provably no write
  });
});

// --- the run's auto-fire (5c) --------------------------------------------------------

describe("runKeyFor — the run's identity, from server facts only", () => {
  it("names the authorized content: case, system, variants, choices", () => {
    const key = runKeyFor(runnableDetail());
    expect(key).toContain("case-a");
    expect(key).toContain("conical-4x4");
    expect(key).toContain("19:5020");
    expect(key).toContain("30:6020");
    expect(key).toContain("dess/conical-scanbody.stl");
  });

  it("is null until every site is READY — the gate's own precondition", () => {
    const detail = runnableDetail({
      sites: [
        siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
        siteView({ tooth: 30, status: "previewed", declared_variant: "6020" }),
      ],
    });
    expect(runKeyFor(detail)).toBeNull();
  });

  it("is null while choices are incomplete, with no sites, or no system", () => {
    expect(
      runKeyFor(
        runnableDetail({
          // effective-incomplete: no act AND no fallback for the construction
          choices: {
            construction_path: null,
            jaw: null,
            gingival_offset_mm: null,
            gingival_offset_default_mm: 0.2,
            effective_construction: { value: null, source: "none" },
            effective_jaw: { value: "lower", source: "suggested" },
            effective_relief: { value: 0.2, source: "default" },
            complete: false,
          },
        }),
      ),
    ).toBeNull();
    expect(runKeyFor(runnableDetail({ sites: [] }))).toBeNull();
    expect(
      runKeyFor(
        runnableDetail({ system: { effective_model: null, source: "none" } }),
      ),
    ).toBeNull();
  });

  it("is null whenever a current run exists — refused does NOT auto-refire", () => {
    for (const run_state of ["queued", "running", "done", "refused"] as const) {
      const detail = runnableDetail();
      expect(
        runKeyFor({
          ...detail,
          session: { ...detail.session, run_state },
        }),
      ).toBeNull();
    }
  });

  it("re-arms with a NEW key after a reset boundary changes the content", () => {
    const before = runKeyFor(runnableDetail());
    const after = runKeyFor(
      runnableDetail({
        sites: [
          siteView({ tooth: 19, status: "ready", declared_variant: "5030" }),
          siteView({ tooth: 30, status: "ready", declared_variant: "6020" }),
        ],
      }),
    );
    expect(after).not.toBeNull();
    expect(after).not.toEqual(before);
  });
});

describe("shouldAutoRun — fire once per authorized content", () => {
  it("fires when runnable and this key has not fired", () => {
    expect(shouldAutoRun({ key: "k1", firedKey: null })).toBe(true);
    expect(shouldAutoRun({ key: "k2", firedKey: "k1" })).toBe(true);
  });

  it("never fires without a key, nor twice for the same key", () => {
    expect(shouldAutoRun({ key: null, firedKey: null })).toBe(false);
    expect(shouldAutoRun({ key: "k1", firedKey: "k1" })).toBe(false);
  });
});
