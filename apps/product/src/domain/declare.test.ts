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
  captureAssessment,
  caseSessionDetail,
  catalogEntry,
  catalogGroup,
  rescanAssessment,
  runnableDetail,
  sitePreviewPayload,
  siteView,
} from "../testing/fixtures";
import {
  activeSiteFrom,
  claimSlot,
  createPreviewFirer,
  declareQueueSummary,
  declaredLabel,
  declareCautionWords,
  siteStateSentence,
  dimsLabel,
  indicesFrom,
  paneNotices,
  partCameraFrame,
  unifiedPaneRadiusMm,
  poseHeldBy,
  positionsFrom,
  previewKeyFor,
  scanPaneRadiusMm,
  seatedReadWanted,
  siteFrameFor,
  resetCount,
  attestationAction,
  attestationSentence,
  attestationSummary,
  reviewTick,
  skipConsequenceWords,
  runKeyFor,
  settleSlot,
  shouldAutoPreview,
  shouldAutoRun,
  switchWords,
  systemCards,
  variantMeshUrl,
  variantShelves,
  alignmentStats,
  presetFrame,
  presetFraming,
  siteIdentity,
  VIEW_PRESETS,
  type PaneFrame,
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

  it("refuses the statuses the server's ladder refuses — no auto-fired 422 (§10-AE)", () => {
    /* Reproduced live on cap7020 t3: a FLAGGED site auto-fired a preview the BFF
       always refuses ("the ladder allows preview only from: declared, previewed,
       ready"), so the panes never got a pose and rested 45° off the cap. The key
       mirrors the server's own ladder rule — not a client verdict, just declining
       to fire a request whose refusal is already known. */
    for (const status of ["flagged", "adjusted"] as const) {
      const blocked = caseSessionDetail({
        ...previewable,
        sites: [siteView({ tooth: 19, status, declared_variant: "5020" })],
      });
      expect(previewKeyFor(blocked, 19)).toBeNull();
    }
    for (const status of ["declared", "previewed", "ready"] as const) {
      const open = caseSessionDetail({
        ...previewable,
        sites: [siteView({ tooth: 19, status, declared_variant: "5020" })],
      });
      expect(previewKeyFor(open, 19)).not.toBeNull();
    }
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

describe("siteFrameFor — panes 2/3 face the top of the cap (the demo's semantics)", () => {
  const pose = {
    axis: [0, 0.6, 0.8],
    x_axis: [1, 0, 0],
    origin: [1, 2, 3],
  };
  const occlusal = [0, 0, 1] as const;

  it("a preview pose frames down the EXACT seated axis with up = its x_axis", () => {
    expect(siteFrameFor([1, 2, 3], pose, [...occlusal], 11)).toEqual({
      center: [1, 2, 3],
      radiusMm: 11,
      viewDirection: [0, 0.6, 0.8],
      up: [1, 0, 0],
    });
  });

  it("without a pose the jaw's occlusal proxy aims the camera; up stays null", () => {
    expect(siteFrameFor([1, 2, 3], null, [...occlusal], 11)).toEqual({
      center: [1, 2, 3],
      radiusMm: 11,
      viewDirection: [0, 0, 1],
      up: null,
    });
  });

  it("a malformed pose axis falls back to the occlusal proxy — up falls with it", () => {
    const broken = { ...pose, axis: [0, 1] };
    expect(siteFrameFor([1, 2, 3], broken, [...occlusal], 11)).toEqual({
      center: [1, 2, 3],
      radiusMm: 11,
      viewDirection: [0, 0, 1],
      up: null,
    });
  });

  it("with neither, the frame centres the site and leaves the direction to the viewer", () => {
    expect(siteFrameFor([1, 2, 3], null, null, 11)).toEqual({
      center: [1, 2, 3],
      radiusMm: 11,
      viewDirection: null,
      up: null,
    });
  });

  it("no centre (or a malformed one) means no frame at all", () => {
    expect(siteFrameFor(null, pose, [...occlusal], 11)).toBeNull();
    expect(siteFrameFor([1, 2], pose, [...occlusal], 11)).toBeNull();
  });
});

describe("partCameraFrame — pane 1 top-down the part's file axis", () => {
  it("frames down [0,0,1] with up [1,0,0], at the part's own radius + a tight margin", () => {
    /* MARGIN 1.6 → 1.05 (client 2026-08-06: "the measurements in the 3 panels do
       not match" — measured 64 px/mm on pane 1 vs 84 on panes 2/3). The generous
       margin predates the tight §10-AE crops; the workspace now unifies every
       pane's field (unifiedPaneRadiusMm below), so the part frame only needs to
       not crop its own silhouette. */
    expect(
      partCameraFrame({
        rimCentre: [0.2, -0.1],
        centroid: [10, 20, 5],
        rmaxMm: 4.0,
      }),
    ).toEqual({
      center: [10.2, 19.9, 5],
      radiusMm: 4.2,
      viewDirection: [0, 0, 1],
      up: [1, 0, 0],
    });
  });

  it("a mesh that does not read as revolute yields no frame — default framing wins", () => {
    expect(partCameraFrame(null)).toBeNull();
  });
});

describe("unifiedPaneRadiusMm — one field of view, so one mm is one length everywhere", () => {
  it("takes the larger of the part's field and the scan region's — nothing crops", () => {
    expect(unifiedPaneRadiusMm(4.2, 5.6)).toBe(5.6);
    expect(unifiedPaneRadiusMm(8.4, 5.6)).toBe(8.4);
  });

  it("no part frame yet leaves the scan region's field standing", () => {
    expect(unifiedPaneRadiusMm(null, 5.6)).toBe(5.6);
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
    for (const status of ["detected", "declared"] as const) {
      const tick = reviewTick(siteView({ status }));
      expect(tick.enabled).toBe(false);
      expect(tick.reason).toContain("preview this site first");
    }
    expect(reviewTick(null).enabled).toBe(false);
  });

  /* A SITE THE RUN HAS ALREADY MEASURED IS NOT A SITE AWAITING A PREVIEW (design
     review 2026-07-31). Both of these used to read "preview this site first" beside a
     row that says "Flagged by the run — deviation RMS 0.214 mm": three sentences on
     one screen, one of them false about work that has demonstrably happened. */
  it("a flagged site is refused with the RUN's reason and pointed at Adjust", () => {
    const tick = reviewTick(siteView({ status: "flagged" }));
    expect(tick.enabled).toBe(false);
    expect(tick.reason).toContain("Adjust");
    expect(tick.reason).not.toContain("preview this site first");
  });

  it("a reworked site is sent back to the panes that show the fit that moved", () => {
    const tick = reviewTick(siteView({ status: "adjusted" }));
    expect(tick.enabled).toBe(false);
    expect(tick.reason).toContain("Adjust");
    expect(tick.reason).not.toContain("preview this site first");
  });
});

describe("the attestation's sentence — what is actually being attested", () => {
  it("names the tooth, the declared cap and the panes as the subject", () => {
    const words = attestationSentence(
      siteView({ tooth: 19, status: "previewed", declared_variant: "5020" }),
    );
    expect(words).toContain("tooth 19");
    expect(words).toContain("the declared cap 5020");
    expect(words).toContain("the panes above");
    expect(words).toContain("Confirm that"); // the demo ack bar's voice
  });

  it("an attested site states what WAS attested, in the past tense", () => {
    const words = attestationSentence(
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
    );
    expect(words).toContain("You confirmed tooth");
    expect(words).toContain("tooth 19");
    expect(words).toContain("5020");
  });

  it("an undeclared site is not asked to attest a cap it does not have", () => {
    expect(
      attestationSentence(siteView({ status: "previewed", declared_variant: null })),
    ).toContain("no cap declared yet");
    expect(attestationSentence(null)).toContain("No site selected");
  });

  it("the act's label says which way the act goes", () => {
    expect(attestationAction(siteView({ status: "ready" }))).toBe(
      "Undo this confirmation",
    );
  });

  it("the last confirm of a run-ready case NAMES THE RUN (client 2026-08-04)", () => {
    // "we should have Align or Run Alignment" — honest exactly where the
    // auto-fire makes it true: every other site ready, choices complete
    expect(
      attestationAction(siteView({ status: "previewed" }), {
        othersUnready: 0,
        choicesComplete: true,
      }),
    ).toBe("Confirm — run the alignment");
  });

  it("with sites still unconfirmed, the label counts them instead of promising a run", () => {
    expect(
      attestationAction(siteView({ status: "previewed" }), {
        othersUnready: 2,
        choicesComplete: true,
      }),
    ).toBe("Confirm — 2 sites left before the alignment runs");
    expect(
      attestationAction(siteView({ status: "previewed" }), {
        othersUnready: 1,
        choicesComplete: true,
      }),
    ).toBe("Confirm — 1 site left before the alignment runs");
  });

  it("incomplete choices keep the plain confirm — the run is not imminent", () => {
    expect(
      attestationAction(siteView({ status: "previewed" }), {
        othersUnready: 0,
        choicesComplete: false,
      }),
    ).toBe("Confirm this site");
  });
});

describe("attestationSummary — the set faced at the moment of moving forward", () => {
  it("an attested site's line carries its cap and the seat facts it stood on", () => {
    const [line] = attestationSummary([
      siteView({
        tooth: 19,
        status: "ready",
        declared_variant: "5020",
        seat_method: "rim-seat",
        rim_agreement_mm: 0.07,
      }),
    ]);
    expect(line).toEqual({
      tooth: 19,
      attested: true,
      words: "Tooth 19 · 5020 · rim-seat, rim 0.07 mm",
    });
  });

  it("an unattested site is NAMED with its rung instead (the blockedReason doctrine)", () => {
    const lines = attestationSummary([
      siteView({ tooth: 30, status: "previewed", declared_variant: "6020" }),
      siteView({ tooth: 19, status: "detected", declared_variant: null }),
    ]);
    expect(lines.map((l) => l.attested)).toEqual([false, false]);
    expect(lines[0]!.words).toBe("Tooth 30 · 6020 · not attested (previewed)");
    expect(lines[1]!.words).toBe(
      "Tooth 19 · no cap declared · not attested (detected)",
    );
  });

  it("a READY site whose seat facts are gone SAYS so — never a blank half-line", () => {
    const [line] = attestationSummary([
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
    ]);
    expect(line!.words).toContain("no seat facts recorded");
  });
});

describe("skipConsequenceWords — the skip states its cost truthfully", () => {
  it("with nothing flagged, it says exactly that", () => {
    expect(skipConsequenceWords(0)).toContain("Nothing is flagged");
  });

  it("with flags it names the count AND what Deliver will actually do", () => {
    const words = skipConsequenceWords(2);
    expect(words).toContain("2 flagged sites");
    expect(words).toContain("own acknowledgment");
    expect(words).toContain("withhold");
  });

  it("one flagged site reads as one, not as a plural with a stray s", () => {
    expect(skipConsequenceWords(1)).toContain("1 flagged site stays");
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

/* THE HELD POSE (client 2026-08-05: "touching the variant tooth buttons put the
 * middle panel camera to the back of the scan"). A variant click re-claims the
 * slot, the payload vanishes for the recompute, and the camera fell back to the
 * occlusal proxy — which on this case aims at the BACK. The proxy is the fallback
 * for a site NEVER measured, not one being RE-measured: the slot carries the last
 * measured pose across re-claims so the camera keeps the seated axis it earned. */
describe("poseHeldBy — the measured axis survives a re-preview", () => {
  it("a fresh slot holds nothing — before any measurement the proxy is the honest view", () => {
    expect(poseHeldBy(undefined)).toBeNull();
    expect(poseHeldBy(claimSlot({}, 19, "k1")[19])).toBeNull();
  });

  it("a ready slot answers with its own payload's pose", () => {
    const payload = sitePreviewPayload();
    let slots = claimSlot({}, 19, "k1");
    slots = settleSlot(slots, 19, "k1", { kind: "ok", data: payload });
    expect(poseHeldBy(slots[19])).toBe(payload.pose);
  });

  it("re-claiming over a ready slot carries its pose — the variant click keeps the camera", () => {
    const payload = sitePreviewPayload();
    let slots = claimSlot({}, 19, "k1");
    slots = settleSlot(slots, 19, "k1", { kind: "ok", data: payload });
    slots = claimSlot(slots, 19, "k2"); // the variant click re-asks
    expect(slots[19]).toMatchObject({ key: "k2", state: "computing" });
    expect(poseHeldBy(slots[19])).toEqual(payload.pose);
  });

  it("the hold survives chained re-claims and a failed settle alike", () => {
    const payload = sitePreviewPayload();
    let slots = claimSlot({}, 19, "k1");
    slots = settleSlot(slots, 19, "k1", { kind: "ok", data: payload });
    slots = claimSlot(slots, 19, "k2");
    slots = claimSlot(slots, 19, "k3");
    slots = settleSlot(slots, 19, "k3", { kind: "error", detail: "the seat refused" });
    expect(slots[19]!.state).toBe("error");
    expect(poseHeldBy(slots[19])).toEqual(payload.pose);
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

describe("the variant DETECTION proposed for this site (gap variant-suggested-badge)", () => {
  const detail = caseSessionDetail({
    catalog: {
      groups: [
        catalogGroup("conical-4x4", [
          catalogEntry({ id: "5020" }),
          catalogEntry({ id: "6030", variant: "6030" }),
        ]),
      ],
      constructions: [],
    },
  });

  it("marks the card whose id is the SERVER's suggested_variant for the site", () => {
    const site = siteView({ tooth: 19, suggested_variant: "6030" });
    const cards = variantShelves(detail, site).current;
    expect(cards.find((c) => c.id === "6030")?.suggested).toBe(true);
    expect(cards.find((c) => c.id === "5020")?.suggested).toBe(false);
  });

  it("the badge STAYS after the operator declares another part — the way back to the proposal (client 2026-08-05)", () => {
    // reversed from "vanishes on declaration": exploring the shelf lost the
    // recommendation ("we lost the suggested label"), and the SELECTED state
    // already attributes the operator's act — the two marks answer different
    // questions and may coexist.
    const site = siteView({
      tooth: 19,
      suggested_variant: "6030",
      declared_variant: "5020",
    });
    const cards = variantShelves(detail, site).current;
    expect(cards.find((c) => c.id === "6030")?.suggested).toBe(true);
    expect(cards.find((c) => c.id === "5020")?.suggested).toBe(false);
  });

  it("no site, or a site the detector proposed nothing for, marks nothing", () => {
    expect(variantShelves(detail).current.every((c) => !c.suggested)).toBe(true);
    const bare = siteView({ tooth: 19, suggested_variant: null });
    expect(variantShelves(detail, bare).current.every((c) => !c.suggested)).toBe(true);
  });

  it("a suggestion naming a part off this shelf marks nothing — it is not declarable here", () => {
    const site = siteView({ tooth: 19, suggested_variant: "not-in-this-catalog" });
    expect(variantShelves(detail, site).current.every((c) => !c.suggested)).toBe(true);
  });
});

describe("declareQueueSummary — how far through the declaration the operator is", () => {
  it("counts REVIEWED (the tick's `ready`) against the total, and names the shortfall", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "ready" }),
      siteView({ tooth: 30, status: "previewed" }),
      siteView({ tooth: 3, status: "detected" }),
    ]);
    expect(words).toContain("1 of 3 sites reviewed");
    expect(words).toContain("2");
  });

  it("says so plainly when every site is reviewed", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "ready" }),
      siteView({ tooth: 30, status: "ready" }),
    ]);
    expect(words).toContain("2 of 2 sites reviewed");
  });

  it("a flagged or adjusted site is NOT reviewed — the run moved it off the tick", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "flagged" }),
      siteView({ tooth: 30, status: "adjusted" }),
    ]);
    expect(words).toContain("0 of 2 sites reviewed");
  });

  it("an empty queue says there is nothing to review, never '0 of 0'", () => {
    expect(declareQueueSummary([])).not.toContain("0 of 0");
  });

  /* THREE POPULATIONS, THREE SENTENCES (design review 2026-07-31). Folding everything
     that is not `ready` into "still to confirm over the panes" told an operator whose
     run flagged one site that they had left work undone HERE — when the act that site
     needs is in Adjust, and every site had already been confirmed before the run
     fired. */
  it("names the flagged population as Adjust's work, not as unconfirmed panes", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "ready" }),
      siteView({ tooth: 30, status: "ready" }),
      siteView({ tooth: 3, status: "flagged" }),
    ]);
    expect(words).toContain("2 of 3 sites reviewed");
    expect(words).toContain("1 flagged");
    expect(words).toContain("Adjust");
    expect(words).not.toContain("still to confirm over the panes");
  });

  it("a reworked site is counted as needing re-confirmation, not as never confirmed", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "ready" }),
      siteView({ tooth: 30, status: "adjusted" }),
    ]);
    expect(words).toContain("1 reworked");
    expect(words).not.toContain("still to confirm over the panes");
  });

  it("keeps the pre-run sentence for sites that genuinely have no tick yet", () => {
    const words = declareQueueSummary([
      siteView({ tooth: 19, status: "ready" }),
      siteView({ tooth: 30, status: "previewed" }),
    ]);
    expect(words).toContain("1 still to confirm over the panes");
  });
});

describe("siteStateSentence — the row's state in words, and the RUN's own number", () => {
  const rows = [
    { tooth: 19, deviation_rms_mm: 0.041 },
    { tooth: 30, deviation_rms_mm: 0.184 },
    { tooth: 3 }, // a row the run wrote no deviation onto
  ];

  it("pre-run a confirmed site SAYS no run has measured it — never a dash reading as zero", () => {
    const words = siteStateSentence(siteView({ tooth: 19, status: "ready" }), []);
    expect(words).toContain("no run has measured");
    // no figure at all, and above all no "0.00" / bare placeholder a reader takes
    // for a measured zero (the design's `—` in the deviation slot)
    expect(words).not.toContain("mm");
    expect(words).not.toContain("0.00");
  });

  it("a confirmed site with a run row carries the run's deviation RMS verbatim", () => {
    const words = siteStateSentence(siteView({ tooth: 19, status: "ready" }), rows);
    expect(words).toContain("0.041 mm");
  });

  it("a flagged site names the flag AND the number the run measured", () => {
    const words = siteStateSentence(siteView({ tooth: 30, status: "flagged" }), rows);
    expect(words.toLowerCase()).toContain("flagged");
    expect(words).toContain("0.184 mm");
  });

  it("a run row with no deviation says so rather than inventing one", () => {
    const words = siteStateSentence(siteView({ tooth: 3, status: "ready" }), rows);
    expect(words).toContain("no deviation");
  });

  it("the pre-run rungs speak the operator's next act, not the wire's word", () => {
    const detected = siteStateSentence(siteView({ tooth: 19, status: "detected" }), []);
    const declared = siteStateSentence(siteView({ tooth: 19, status: "declared" }), []);
    const previewed = siteStateSentence(siteView({ tooth: 19, status: "previewed" }), []);
    expect(detected).not.toBe("detected");
    expect(detected.toLowerCase()).toContain("declar");
    expect(declared).not.toBe("declared");
    expect(previewed.toLowerCase()).toContain("confirm");
  });

  it("a reworked site asks for its confirmation again", () => {
    const words = siteStateSentence(siteView({ tooth: 19, status: "adjusted" }), rows);
    expect(words.toLowerCase()).toContain("confirm");
    expect(words).toContain("0.041 mm");
  });

  it("no sentence is a verdict of ours: 'in tolerance' is never claimed client-side", () => {
    for (const status of ["ready", "flagged", "adjusted"] as const) {
      const words = siteStateSentence(siteView({ tooth: 19, status }), rows);
      expect(words.toLowerCase()).not.toContain("in tolerance");
      expect(words.toLowerCase()).not.toContain("pass");
    }
  });
});

/**
 * §10-AN slice C: the caution CHIP's own list — "reworked since the run" (the SAME
 * sentence `siteStateSentence` already speaks) plus a rescan-grade capture verdict
 * (the SAME sentence the worker wrote, off `site.capture`). Collected, never
 * paraphrased, and empty wherever there is nothing to say.
 */
describe("declareCautionWords — the caution chip's list, off the SAME facts the row already reads", () => {
  const rows = [{ tooth: 19, deviation_rms_mm: 0.041 }];

  it("is empty with no site selected", () => {
    expect(declareCautionWords(null, rows)).toEqual([]);
  });

  it("is empty for a clean, unreworked site", () => {
    expect(declareCautionWords(siteView({ tooth: 19, status: "ready" }), rows)).toEqual([]);
  });

  it("carries the EXACT reworked-since-the-run sentence siteStateSentence speaks", () => {
    const site = siteView({ tooth: 19, status: "adjusted" });
    const words = declareCautionWords(site, rows);
    expect(words).toEqual([siteStateSentence(site, rows)]);
    expect(words[0]).toContain("Reworked since the run");
  });

  it("carries the worker's own rescan sentence, verbatim off site.capture", () => {
    const message = "Only 41% of the rim arc is captured — below the rescan threshold.";
    const site = siteView({ tooth: 19, status: "detected", capture: rescanAssessment(message) });
    expect(declareCautionWords(site, rows)).toEqual([message]);
  });

  it("carries BOTH when a site is reworked AND its capture is rescan-grade", () => {
    const message = "Only 41% of the rim arc is captured — below the rescan threshold.";
    const site = siteView({
      tooth: 19,
      status: "adjusted",
      capture: rescanAssessment(message),
    });
    expect(declareCautionWords(site, rows)).toEqual([
      siteStateSentence(site, rows),
      message,
    ]);
  });

  it("never speaks for a passing or marginal capture — only rescan-grade", () => {
    const pass = siteView({
      tooth: 19,
      status: "detected",
      capture: captureAssessment({ verdict: "marginal" }),
    });
    expect(declareCautionWords(pass, rows)).toEqual([]);
  });
});

// --- the workspace toolbar's rules (gaps `workspace-toolbar-site-chip`,
// --- `alignment-metrics-strip`, `named-view-presets`) --------------------------------

describe("siteIdentity — WHICH site the three panes are showing", () => {
  it("names the tooth and the effective system", () => {
    expect(siteIdentity(19, "conical-4x4")).toEqual({
      tooth: "Tooth 19",
      system: "conical-4x4",
    });
  });

  it("with no site selected it says so rather than printing a bare dash", () => {
    expect(siteIdentity(null, "conical-4x4").tooth).toBe("No site selected");
  });

  it("with no effective system it says so — a blank would read as 'no system needed'", () => {
    expect(siteIdentity(19, null).system).toBe("no system declared");
  });
});

describe("alignmentStats — the strip's facts, every one the SERVER's", () => {
  const rows = [
    {
      tooth: 19,
      deviation_rms_mm: 0.0412,
      deviation_p90_mm: 0.0871,
      clocking: { notch_shift_deg: -1.42 },
      correspondence: { pairs: 3, max_pairs: 8 },
    },
    { tooth: 30 },
  ];
  const statOf = (
    stats: readonly { readonly id: string; readonly value: string }[],
    id: string,
  ): string => stats.find((s) => s.id === id)!.value;

  it("reads the run row's deviation, clocking and pairs verbatim", () => {
    const stats = alignmentStats(rows, 19, "5020");
    expect(statOf(stats, "variant")).toBe("5020");
    expect(statOf(stats, "dev-rms")).toBe("0.041 mm");
    expect(statOf(stats, "dev-p90")).toBe("0.087 mm");
    expect(statOf(stats, "rotation")).toBe("-1.4°");
    expect(statOf(stats, "pairs")).toBe("3 / 8");
  });

  it("a positive clocking residual carries its sign — the direction IS the fact", () => {
    const stats = alignmentStats([{ tooth: 19, clocking: { notch_shift_deg: 2.5 } }], 19, null);
    expect(statOf(stats, "rotation")).toBe("+2.5°");
  });

  /* THE ROTATION STAT GETS THE PAIRS PILL'S OWN HONESTY (§10-H's "STILL OPEN" line,
     closed 2026-08-02): a run that could not verify this cap's rotation still printed
     a bare "+21.7°", a number the run itself refused to trust, indistinguishable from
     a verified reading. The suffix is the SAME server boolean the toolbar's notice
     and Deliver's inert "unverified" em both key on — never re-derived. */
  it("carries the server's unverified word beside the figure", () => {
    const stats = alignmentStats(
      [{ tooth: 19, clocking: { notch_shift_deg: 21.7, rotation_unverified: true } }],
      19,
      null,
    );
    expect(statOf(stats, "rotation")).toBe("+21.7° · unverified");
  });

  it("a verified rotation stays a bare figure", () => {
    const stats = alignmentStats(
      [{ tooth: 19, clocking: { notch_shift_deg: 3.2, rotation_unverified: false } }],
      19,
      null,
    );
    expect(statOf(stats, "rotation")).toBe("+3.2°");
  });

  it("PAIRS is '—' while the row carries no correspondence — never an invented 0 / 8", () => {
    const stats = alignmentStats(rows, 30, "5020");
    expect(statOf(stats, "pairs")).toBe("—");
    expect(statOf(stats, "pairs")).not.toContain("0");
  });

  it("a correspondence with no server cap renders the count alone, not a guessed bound", () => {
    const stats = alignmentStats([{ tooth: 19, correspondence: { pairs: 4 } }], 19, null);
    expect(statOf(stats, "pairs")).toBe("4");
  });

  /* THE VACUOUS RMS, IN THE STRIP (defect cap6020-neodent-gm, 2026-08-01). "1 / 8"
     reads exactly like "3 / 8" — a fit that happened — and says nothing about the one
     way the two differ: a single observation has nothing to cross-check it. The word
     is the SERVER's own `cross_checked`, never a `pairs === 1` test here. */
  it("a fit the server did not cross-check says so beside its count", () => {
    const stats = alignmentStats(
      [{ tooth: 19, correspondence: { pairs: 1, max_pairs: 8, cross_checked: false } }],
      19,
      null,
    );
    expect(statOf(stats, "pairs")).toBe("1 / 8 · unchecked");
  });

  it("a cross-checked fit carries no such word — and neither does a silent server", () => {
    const checked = alignmentStats(
      [{ tooth: 19, correspondence: { pairs: 3, max_pairs: 8, cross_checked: true } }],
      19,
      null,
    );
    expect(statOf(checked, "pairs")).toBe("3 / 8");
    const silent = alignmentStats(
      [{ tooth: 19, correspondence: { pairs: 1, max_pairs: 8 } }],
      19,
      null,
    );
    expect(statOf(silent, "pairs")).toBe("1 / 8");
  });

  /* NO RUN IS NOT A MEASUREMENT (design review 2026-07-31). The strip printed "—" in
     every numeric cell before a run — the same dash the queue rows deliberately refuse
     because "in a deviation column it reads as a measured zero". It says the absence
     out loud instead, exactly as `measuredWords` already does one panel away. */
  it("pre-run says NO RUN YET rather than a dash a reader takes for a zero", () => {
    const stats = alignmentStats([], 19, "5020");
    expect(statOf(stats, "variant")).toBe("5020");
    for (const id of ["dev-rms", "dev-p90", "rotation", "pairs"]) {
      expect(statOf(stats, id)).toBe("no run yet");
    }
  });

  it("keeps the dash where a run row EXISTS but carries no figure — a different fact", () => {
    const stats = alignmentStats(rows, 30, "5020");
    expect(statOf(stats, "dev-rms")).toBe("—");
    expect(statOf(stats, "pairs")).toBe("—");
  });

  /* THE PREVIEW'S OWN PUBLISHED FIGURES, WITH THEIR SOURCE NAMED. On Declare before
     the run, the union pane's legend prints "RMS 0.086 mm · p90 0.142 mm" from
     payload.stats while this strip said no figure existed. Both come from the server;
     what differs is WHICH act measured, so the label carries it. */
  it("falls back to the preview's server-published figures, naming them as the preview's", () => {
    const stats = alignmentStats([], 19, "5020", {
      poseAvailable: true,
      rmsMm: 0.0861,
      p90Mm: 0.1423,
      source: "preview",
    });
    expect(statOf(stats, "dev-rms")).toBe("0.086 mm");
    expect(statOf(stats, "dev-p90")).toBe("0.142 mm");
    const label = (id: string) => stats.find((s) => s.id === id)!.label;
    expect(label("dev-rms")).toContain("preview");
    // the preview seats a cap; it measures no clocking residual and no pairs
    expect(statOf(stats, "rotation")).toBe("no run yet");
    expect(statOf(stats, "pairs")).toBe("no run yet");
  });

  it("the RUN's own figures say so too — a strip cell never hides which act measured it", () => {
    const label = (id: string) =>
      alignmentStats(rows, 19, "5020").find((s) => s.id === id)!.label;
    expect(label("dev-rms")).toContain("run");
    expect(label("dev-p90")).toContain("run");
  });

  it("a run row always wins over a preview still held in the browser", () => {
    const stats = alignmentStats(rows, 19, "5020", {
      poseAvailable: true,
      rmsMm: 9.999,
      p90Mm: 9.999,
      source: "preview",
    });
    expect(statOf(stats, "dev-rms")).toBe("0.041 mm");
  });

  it("an undeclared site's VARIANT is a dash, never the suggestion", () => {
    expect(statOf(alignmentStats([], null, null), "variant")).toBe("—");
  });

  it("no stat is a verdict: nothing here says pass, fail or in tolerance", () => {
    const words = alignmentStats(rows, 19, "5020")
      .map((s) => `${s.label} ${s.value}`)
      .join(" ")
      .toLowerCase();
    for (const verdict of ["pass", "fail", "in tolerance", "ok", "within"]) {
      expect(words).not.toContain(verdict);
    }
  });
});

describe("presetFrame — the named viewpoints, in each pane's OWN basis", () => {
  /* The canonical part frame: look down +z with up +x (partCameraFrame's own
     directions), which is the same reference the seated pose's x_axis is. */
  const base: PaneFrame = {
    center: [1, 2, 3],
    radiusMm: 11,
    viewDirection: [0, 0, 1],
    up: [1, 0, 0],
  };

  it("offers three viewpoints, and NONE of the off-axis two wears an anatomical name", () => {
    expect(VIEW_PRESETS.map((p) => p.id)).toEqual(["occlusal", "side-a", "side-b"]);
    /* THE RENAME (design review 2026-07-31). The off-axis two were shipped as
       "buccal"/"mesial" but they are built from the seated pose's `x_axis`, which the
       worker publishes only "because it is what makes the three panes COMPARABLE"
       (application/preview.py:119-124) — a shared clock reference, never an arch
       direction. Nothing maps it to buccal/lingual or mesial/distal, so on tooth 29
       "buccal" could look at the lingual wall. A name the product cannot justify is a
       name the product does not use. */
    const words = VIEW_PRESETS.map((p) => `${p.label} ${p.title}`).join(" ").toLowerCase();
    for (const anatomy of ["buccal", "lingual", "mesial", "distal", "palatal"]) {
      expect(words).not.toContain(anatomy);
    }
  });

  it("occlusal IS the pane's own framing — down the seated axis, unchanged", () => {
    expect(presetFrame(base, "occlusal")).toEqual(base);
  });

  it("side A looks down the third basis vector with the axis standing up on screen", () => {
    const frame = presetFrame(base, "side-a")!;
    expect(frame.viewDirection).toEqual([0, 1, 0]); // z × x
    expect(frame.up).toEqual([0, 0, 1]); // the cap's own axis points up
    // the pane keeps its own subject: only the camera moved
    expect(frame.center).toEqual(base.center);
    expect(frame.radiusMm).toBe(base.radiusMm);
  });

  it("side B looks down the shared clock reference itself, the axis still up", () => {
    const frame = presetFrame(base, "side-b")!;
    expect(frame.viewDirection).toEqual([1, 0, 0]);
    expect(frame.up).toEqual([0, 0, 1]);
  });

  it("normalises whatever the pose supplied — a wire axis is not a unit vector", () => {
    const scaled: PaneFrame = { ...base, viewDirection: [0, 0, 4], up: [3, 0, 0] };
    const frame = presetFrame(scaled, "side-a")!;
    expect(frame.viewDirection![0]).toBeCloseTo(0, 12);
    expect(frame.viewDirection![1]).toBeCloseTo(1, 12);
    expect(frame.up![2]).toBeCloseTo(1, 12);
  });

  it("without a measured roll there is no off-axis view — null, never a guessed clock", () => {
    // pre-preview panes 2/3 frame down the jaw's occlusal PROXY with up = null
    // (siteFrameFor): an off-axis view would need a roll nothing has measured.
    const proxy: PaneFrame = { ...base, up: null };
    expect(presetFrame(proxy, "side-a")).toBeNull();
    expect(presetFrame(proxy, "side-b")).toBeNull();
    // occlusal still works: it is exactly the framing the pane already has
    expect(presetFrame(proxy, "occlusal")).toEqual(proxy);
  });

  it("a degenerate basis (axis parallel to its roll) yields no view rather than NaNs", () => {
    const degenerate: PaneFrame = { ...base, viewDirection: [0, 0, 1], up: [0, 0, 2] };
    expect(presetFrame(degenerate, "side-a")).toBeNull();
  });

  it("no frame in, no frame out", () => {
    expect(presetFrame(null, "occlusal")).toBeNull();
    expect(presetFrame(null, "side-a")).toBeNull();
  });
});

/**
 * REFERENCE AND LABEL MUST COME FROM ONE FRAME (design review 2026-07-31).
 *
 * The pane foot is the one on-screen sentence claiming to be a LIVE measurement of
 * orientation. Under a preset it measured the camera against the preset-ROTATED
 * direction while printing the label of the UN-rotated axis, so a side-on pane read
 * "down the seated pose axis" at exactly 90° off it — and "90° off the seated pose
 * axis" once the operator orbited back onto it. This pairs the two.
 */
describe("presetFraming — the frame a pane got, and the words for what it framed on", () => {
  const base: PaneFrame = {
    center: [1, 2, 3],
    radiusMm: 11,
    viewDirection: [0, 0, 1],
    up: [1, 0, 0],
  };

  it("occlusal is the pane's own framing, so the pane's own axis name stands", () => {
    const framing = presetFraming(base, "occlusal");
    expect(framing.frame).toEqual(base);
    expect(framing.presetLabel).toBeNull();
  });

  it("a rotated frame carries a label for the direction it ACTUALLY framed on", () => {
    const framing = presetFraming(base, "side-a");
    expect(framing.frame!.viewDirection).toEqual([0, 1, 0]);
    expect(framing.presetLabel).not.toBeNull();
    expect(framing.presetLabel).toContain("side A");
    expect(framing.presetLabel).not.toContain("seated pose axis");
  });

  it("a preset that could not apply falls back to the base frame AND its base label", () => {
    // pre-preview panes 2/3: the occlusal proxy carries no clock reference at all
    const proxy: PaneFrame = { ...base, up: null };
    const framing = presetFraming(proxy, "side-a");
    expect(framing.frame).toEqual(proxy);
    // no label of its own — the caller keeps naming the axis the pane is really on
    expect(framing.presetLabel).toBeNull();
  });

  it("no frame in: no frame, and no claim about one", () => {
    expect(presetFraming(null, "side-b")).toEqual({ frame: null, presetLabel: null });
  });
});

/**
 * THE SEATED FALLBACK (§10-AE): a site the ladder will not preview (flagged or
 * adjusted) with a DONE run still has a fit the server knows — the shipped one.
 * Declare's panes read it through GET .../seated (no rung moves) so pane 2 frames
 * down the cap's own axis instead of resting on the occlusal proxy.
 */
describe("seatedReadWanted — the panes' fallback to the shipped fit", () => {
  it("wants the seated read exactly when the preview lane is closed over a done run", () => {
    expect(seatedReadWanted({ tooth: 19, previewKey: null, runState: "done",
                              siteStatus: "flagged" })).toBe(true);
    expect(seatedReadWanted({ tooth: 19, previewKey: null, runState: "done",
                              siteStatus: "adjusted" })).toBe(true);
  });

  it("stays out of the preview lane's way, and never fires without a run", () => {
    expect(seatedReadWanted({ tooth: 19, previewKey: "k", runState: "done",
                              siteStatus: "ready" })).toBe(false);
    expect(seatedReadWanted({ tooth: 19, previewKey: null, runState: "none",
                              siteStatus: "flagged" })).toBe(false);
    expect(seatedReadWanted({ tooth: null, previewKey: null, runState: "done",
                              siteStatus: "flagged" })).toBe(false);
    // a detected/declared site with a null key is missing its declaration or
    // choices — the seated read answers a different question and stays quiet
    expect(seatedReadWanted({ tooth: 19, previewKey: null, runState: "done",
                              siteStatus: "declared" })).toBe(false);
  });
});

/**
 * PANE 2's DISPLAY RADIUS (§10-AE.2, tightened twice since — §10-AO,
 * 2026-08-06): the DECLARED cap's own rim when known, else the largest
 * SERVED catalog rim's radius + 0.6 mm of surrounding anatomy, never wider
 * than the standing 11 mm band and never below a workable 3.5 mm.
 * DISPLAY-ONLY — §10-I.3: no client bound ever reaches the aligner.
 */
describe("scanPaneRadiusMm — the cap-tight display band", () => {
  const twoVariants = caseSessionDetail({
    catalog: {
      groups: [{
        model: "conical-4x4",
        variants: [
          { id: "5020", variant: "5020", label: "5020",
            rim_diameter_mm: 6.2, height_mm: 3.4 },
          { id: "7030", variant: "7030", label: "7030",
            rim_diameter_mm: 8.2, height_mm: 5.4 },
        ],
      }],
      constructions: [],
    },
  });

  it("keys to the DECLARED cap's own rim (client 2026-08-06, third tightening)", () => {
    // 6.2/2 + 0.6 = 3.7 (above the 3.5 floor): the pane shows THIS cap, not
    // the largest cap the catalog could serve
    expect(scanPaneRadiusMm(twoVariants, "5020")).toBeCloseTo(3.7, 5);
    expect(scanPaneRadiusMm(twoVariants, "7030")).toBeCloseTo(4.7, 5);
  });

  it("bounds by the largest served rim while nothing is declared", () => {
    // 8.2/2 + 0.6 = 4.7 — an honest bound, never a guess at the declaration
    expect(scanPaneRadiusMm(twoVariants)).toBeCloseTo(4.7, 5);
    // a declared variant the catalog does not carry falls back the same way
    expect(scanPaneRadiusMm(twoVariants, "9999")).toBeCloseTo(4.7, 5);
  });

  it("falls back to the standing band when the catalog serves no dimensions", () => {
    expect(scanPaneRadiusMm(caseSessionDetail())).toBe(11);
  });

  it("never narrows below 3.5 mm and never widens past the standing band", () => {
    const tiny = caseSessionDetail({
      catalog: {
        groups: [{ model: "conical-4x4",
                   variants: [{ id: "x", variant: "x", label: "x",
                                rim_diameter_mm: 3.0, height_mm: 2.0 }] }],
        constructions: [],
      },
    });
    // 3.0/2 + 0.6 = 2.1 → floor 3.5
    expect(scanPaneRadiusMm(tiny)).toBe(3.5);
    const huge = caseSessionDetail({
      catalog: {
        groups: [{ model: "conical-4x4",
                   variants: [{ id: "x", variant: "x", label: "x",
                                rim_diameter_mm: 30.0, height_mm: 9.0 }] }],
        constructions: [],
      },
    });
    expect(scanPaneRadiusMm(huge)).toBe(11);
  });
});
