/**
 * THE TOOTH CHART's domain rules. Pinned here because they are clinical facts, not styling:
 * which arch a Universal number belongs to, what it is called, how the familiar diagram lines
 * the two arches up, which conditions a tooth must report, and how the auto-increment picks a
 * number without ever colliding with the duplicate-tooth guard.
 */
import { describe, expect, it } from "vitest";
import {
  addSiteBlockedReason,
  ARCH_ROWS,
  AUTO_TOOTH_NUMBER_DEFAULT,
  archRowTeeth,
  buildToothCells,
  cellsByTooth,
  chartSitesFrom,
  isUniversalTooth,
  jawOfTooth,
  LOWER_TEETH,
  nextToothNumber,
  parseToothEntry,
  rowIsMarked,
  toothLabel,
  toothName,
  UPPER_TEETH,
} from "./toothChart";
import type { ChartRunRow, ToothChartSite } from "./toothChart";
import {
  initialSelection,
  stepSite,
  withActiveSite,
  withReviewed,
  withSites,
  withVariant,
} from "./librarySelection";
import type { LibrarySelection } from "./librarySelection";
import { authorizeRun, canRun, runBlockers } from "./runGate";

describe("Universal numbering", () => {
  it("splits the arches at 16/17 and refuses anything that is not a tooth", () => {
    expect(jawOfTooth(1)).toBe("upper");
    expect(jawOfTooth(16)).toBe("upper");
    expect(jawOfTooth(17)).toBe("lower");
    expect(jawOfTooth(32)).toBe("lower");
    expect(jawOfTooth(0)).toBeNull();
    expect(jawOfTooth(33)).toBeNull();
    expect(jawOfTooth(3.5)).toBeNull();
    expect(isUniversalTooth(8)).toBe(true);
    expect(isUniversalTooth(-1)).toBe(false);
  });

  it("names each tooth anatomically — the accessible label, not a bare number", () => {
    expect(toothName(1)).toBe("upper right third molar");
    expect(toothName(3)).toBe("upper right first molar");
    expect(toothName(8)).toBe("upper right central incisor");
    expect(toothName(9)).toBe("upper left central incisor");
    expect(toothName(14)).toBe("upper left first molar");
    expect(toothName(17)).toBe("lower left third molar");
    expect(toothName(24)).toBe("lower left central incisor");
    expect(toothName(25)).toBe("lower right central incisor");
    expect(toothName(30)).toBe("lower right first molar");
    expect(toothName(32)).toBe("lower right third molar");
    expect(toothLabel(3)).toBe("Tooth 3 — upper right first molar");
  });

  it("lists 16 teeth per arch, each exactly once", () => {
    expect(UPPER_TEETH).toHaveLength(16);
    expect(LOWER_TEETH).toHaveLength(16);
    expect(new Set([...UPPER_TEETH, ...LOWER_TEETH]).size).toBe(32);
  });
});

describe("the arch diagram's layout", () => {
  it("puts the same side of the mouth in the same column, top and bottom", () => {
    const upper = archRowTeeth(ARCH_ROWS[0]);
    const lower = archRowTeeth(ARCH_ROWS[1]);
    expect(upper).toHaveLength(16);
    expect(lower).toHaveLength(16);
    // 1 above 32, 2 above 31, … — the invariant that makes a dental chart readable
    upper.forEach((tooth, i) => {
      expect(tooth + (lower[i] as number)).toBe(33);
    });
  });

  it("reads upper left-to-right 1…16 and lower left-to-right 32…17", () => {
    expect(archRowTeeth(ARCH_ROWS[0])[0]).toBe(1);
    expect(archRowTeeth(ARCH_ROWS[0])[15]).toBe(16);
    expect(archRowTeeth(ARCH_ROWS[1])[0]).toBe(32);
    expect(archRowTeeth(ARCH_ROWS[1])[15]).toBe(17);
  });

  it("splits each arch into two quadrants at the midline", () => {
    for (const row of ARCH_ROWS) {
      expect(row.quadrants[0].teeth).toHaveLength(8);
      expect(row.quadrants[1].teeth).toHaveLength(8);
    }
    expect(ARCH_ROWS[1].quadrants[0].label).toBe("Lower right");
  });
});

describe("buildToothCells", () => {
  const SITES: ToothChartSite[] = [
    { tooth: 3, marked: true, reviewed: true, flags: [] },
    { tooth: 14, marked: false, reviewed: false, flags: ["capture-rescan"] },
  ];

  it("covers all 32 teeth, carrying each site's state onto its own tooth", () => {
    const cells = buildToothCells({ jaw: "upper", sites: SITES, activeTooth: 14 });
    expect(cells).toHaveLength(32);
    const byTooth = cellsByTooth(cells);
    expect(byTooth.get(3)?.siteIndex).toBe(0);
    expect(byTooth.get(3)?.marked).toBe(true);
    expect(byTooth.get(3)?.reviewed).toBe(true);
    expect(byTooth.get(3)?.active).toBe(false);
    expect(byTooth.get(14)?.active).toBe(true);
    expect(byTooth.get(14)?.flags).toEqual(["capture-rescan"]);
    expect(byTooth.get(5)?.siteIndex).toBeNull();
  });

  it("marks the case's jaw and leaves the other arch out of it", () => {
    const byTooth = cellsByTooth(buildToothCells({ jaw: "upper", sites: SITES, activeTooth: null }));
    expect(byTooth.get(3)?.inCaseJaw).toBe(true);
    expect(byTooth.get(30)?.inCaseJaw).toBe(false);
    const lower = cellsByTooth(buildToothCells({ jaw: "lower", sites: SITES, activeTooth: null }));
    expect(lower.get(3)?.inCaseJaw).toBe(false);
    expect(lower.get(30)?.inCaseJaw).toBe(true);
  });

  it("never activates a tooth that has no site (a stale cursor cannot light an empty tooth)", () => {
    const byTooth = cellsByTooth(buildToothCells({ jaw: "upper", sites: SITES, activeTooth: 7 }));
    expect(byTooth.get(7)?.active).toBe(false);
  });

  it("keeps the FIRST row when two sites claim one tooth — it does not pick a winner", () => {
    const cells = buildToothCells({
      jaw: "upper",
      sites: [
        { tooth: 3, marked: true, reviewed: false, flags: ["duplicate-tooth"] },
        { tooth: 3, marked: false, reviewed: true, flags: ["duplicate-tooth"] },
      ],
      activeTooth: null,
    });
    expect(cellsByTooth(cells).get(3)?.siteIndex).toBe(0);
    expect(cellsByTooth(cells).get(3)?.marked).toBe(true);
  });
});

describe("chartSitesFrom", () => {
  const runRow = (over: Partial<ChartRunRow> = {}): ChartRunRow => ({
    tooth: 3,
    clocking: { rotationUnverified: false },
    variant: { declared: "6020", flags: [] },
    ...over,
  });

  it("reads marks from any of the four kinds the doctor can place", () => {
    expect(rowIsMarked({ tooth: 3 })).toBe(false);
    expect(rowIsMarked({ tooth: 3, centerMark: [0, 0, 0] })).toBe(true);
    expect(rowIsMarked({ tooth: 3, rimMark: [0, 0, 0] })).toBe(true);
    expect(rowIsMarked({ tooth: 3, rimPoints: [[0, 0, 0]] })).toBe(true);
    expect(rowIsMarked({ tooth: 3, markedPoints: [[0, 0, 0]] })).toBe(true);
    expect(rowIsMarked({ tooth: 3, rimPoints: [] })).toBe(false);
  });

  it("raises each flag from the source that actually measured it", () => {
    const sites = chartSitesFrom({
      rows: [{ tooth: 3, centerMark: [0, 0, 0] }, { tooth: 14 }, { tooth: 30 }],
      reviewedTeeth: [3],
      captures: ["rescan", "marginal", null],
      runRows: [
        runRow({ tooth: 3, clocking: { rotationUnverified: true } }),
        runRow({ tooth: 14, variant: { declared: "6020", flags: ["declared 6020 disputed"] } }),
      ],
      duplicateTeeth: [],
      jaw: "upper",
    });
    expect(sites[0]).toEqual({
      tooth: 3,
      marked: true,
      reviewed: true,
      flags: ["capture-rescan", "rotation-unverified"],
    });
    expect(sites[1]?.flags).toEqual(["capture-marginal", "variant-mismatch"]);
    expect(sites[1]?.reviewed).toBe(false);
    // tooth 30 is on the lower arch while the run is selected upper — a reportable inconsistency
    expect(sites[2]?.flags).toEqual(["off-jaw"]);
  });

  it("raises no run-derived flag before a run has measured anything", () => {
    const sites = chartSitesFrom({
      rows: [{ tooth: 3 }],
      reviewedTeeth: [],
      captures: [null],
      runRows: [],
      duplicateTeeth: [],
      jaw: "upper",
    });
    expect(sites[0]?.flags).toEqual([]);
  });

  it("does not dispute a cap nobody declared", () => {
    const sites = chartSitesFrom({
      rows: [{ tooth: 3 }],
      reviewedTeeth: [],
      captures: [null],
      runRows: [runRow({ variant: { declared: null, flags: ["declared variant missing"] } })],
      duplicateTeeth: [],
      jaw: "upper",
    });
    expect(sites[0]?.flags).toEqual([]);
  });

  it("flags both rows of a duplicated tooth number", () => {
    const sites = chartSitesFrom({
      rows: [{ tooth: 3 }, { tooth: 3 }],
      reviewedTeeth: [],
      captures: [null, null],
      runRows: [],
      duplicateTeeth: [3],
      jaw: "upper",
    });
    expect(sites[0]?.flags).toEqual(["duplicate-tooth"]);
    expect(sites[1]?.flags).toEqual(["duplicate-tooth"]);
  });
});

describe("automated tooth number increasing", () => {
  it("is on by default, matching the client's own toggle", () => {
    expect(AUTO_TOOTH_NUMBER_DEFAULT).toBe(true);
  });

  it("starts at the arch's first tooth when nothing has been added yet", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [], lastTooth: null })).toBe(1);
    expect(nextToothNumber({ jaw: "lower", usedTeeth: [], lastTooth: null })).toBe(17);
  });

  it("increments from the last site's tooth", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [3], lastTooth: 3 })).toBe(4);
    expect(nextToothNumber({ jaw: "lower", usedTeeth: [19], lastTooth: 19 })).toBe(20);
  });

  it("skips numbers already taken, so it can never create a duplicate", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [3, 4, 5], lastTooth: 3 })).toBe(6);
  });

  it("wraps once round the arch rather than running out at the last molar", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [16], lastTooth: 16 })).toBe(1);
    expect(nextToothNumber({ jaw: "lower", usedTeeth: [32], lastTooth: 32 })).toBe(17);
  });

  it("returns null when the arch is full — the caller must refuse, not invent a number", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [...UPPER_TEETH], lastTooth: 16 })).toBeNull();
  });

  it("ignores a last tooth from the other arch and starts at this arch's first free one", () => {
    expect(nextToothNumber({ jaw: "upper", usedTeeth: [30, 1], lastTooth: 30 })).toBe(2);
  });
});

describe("parseToothEntry (manual entry, auto-numbering off)", () => {
  const context = { jaw: "upper" as const, usedTeeth: [3, 14] };

  it("accepts a free tooth on the selected arch", () => {
    expect(parseToothEntry("5", context)).toEqual({ kind: "ok", tooth: 5 });
    expect(parseToothEntry("  5 ", context)).toEqual({ kind: "ok", tooth: 5 });
  });

  it("names the rule each refusal broke", () => {
    expect(parseToothEntry("", context).kind).toBe("error");
    expect(parseToothEntry("abc", context)).toMatchObject({ kind: "error" });
    expect(parseToothEntry("3.5", context)).toMatchObject({
      kind: "error",
      message: expect.stringContaining("whole tooth number"),
    });
    expect(parseToothEntry("33", context)).toMatchObject({
      kind: "error",
      message: expect.stringContaining("1–32"),
    });
    expect(parseToothEntry("3", context)).toMatchObject({
      kind: "error",
      message: expect.stringContaining("already has a site"),
    });
    expect(parseToothEntry("30", context)).toMatchObject({
      kind: "error",
      message: expect.stringContaining("lower arch"),
    });
  });
});

/**
 * WHO OWNS THE NEXT CLICK. The viewer holds ONE one-shot pick and `enterPointPick` supersedes
 * whatever was waiting, so the chart must refuse to arm while any other tool holds it. The
 * verifier found the original list naming four of the six owners — these cases exist so the
 * next owner added to the viewer cannot quietly go unnamed again.
 */
describe("adding a site refuses while another tool owns the scan click", () => {
  const FREE = {
    brushing: false,
    placingMark: false,
    rimPoints: false,
    trenchMark: false,
    correspondencePoint: false,
    libraryMark: false,
    runInFlight: false,
  };

  it("permits the add when nothing else is armed", () => {
    expect(addSiteBlockedReason(FREE)).toBeNull();
  });

  it("names EVERY tool that can hold the pick — none may be silently omitted", () => {
    const owners = Object.keys(FREE) as (keyof typeof FREE)[];
    for (const owner of owners) {
      const reason = addSiteBlockedReason({ ...FREE, [owner]: true });
      expect(reason, `${owner} must block adding a site`).not.toBeNull();
      expect(reason).toMatch(/\.$/); // a sentence, not a flag
    }
  });

  it("blocks on the correspondence point and the library mark (the two that were missing)", () => {
    expect(addSiteBlockedReason({ ...FREE, correspondencePoint: true })).toContain(
      "correspondence point",
    );
    expect(addSiteBlockedReason({ ...FREE, libraryMark: true })).toContain("library mark");
  });

  it("reports the tool nearest the operator's hand when several are somehow set", () => {
    expect(addSiteBlockedReason({ ...FREE, brushing: true, runInFlight: true })).toContain(
      "brush stroke",
    );
  });
});

/**
 * THE SHARED CURSOR, end to end — App's own wiring, replicated.
 *
 * The chart's central claim is that it and the verify dialog's '‹ n ›' stepper move ONE cursor.
 * That claim lives in App (three expressions: what the chart is given, what a chart click does,
 * and what the stepper writes), so it was provable only by driving the app by hand. The three
 * expressions are reproduced verbatim below and pinned from BOTH directions — otherwise a later
 * edit to any one of them re-opens two competing cursors, which is precisely the failure the
 * chart's shape exists to rule out and precisely the failure a static-markup test cannot see.
 */
type WiredRow = { readonly tooth: number; readonly declaredVariant?: string | null };

/** App: `chartSites` (the ToothChart's `sites` prop). */
const wiredChartSites = (state: LibrarySelection, rows: readonly WiredRow[]) =>
  chartSitesFrom({
    rows,
    reviewedTeeth: state.sites.filter((s) => s.reviewed).map((s) => s.tooth),
    captures: rows.map(() => null),
    runRows: [],
    duplicateTeeth: [],
    jaw: state.jaw,
  });

/** App: `activeChartTooth` (the ToothChart's `activeTooth` prop). */
const wiredActiveTooth = (state: LibrarySelection) =>
  state.sites[state.activeSiteIndex]?.tooth ?? null;

/** App: `handleSelectToothSite` — what the chart reports a click as. */
const wiredClick = (state: LibrarySelection, tooth: number) => {
  const index = state.sites.findIndex((s) => s.tooth === tooth);
  return index < 0 ? state : withActiveSite(state, index);
};

/** Which teeth the chart actually lights, for a given selection. */
const litTeeth = (state: LibrarySelection, rows: readonly WiredRow[]) =>
  buildToothCells({
    jaw: state.jaw,
    sites: wiredChartSites(state, rows),
    activeTooth: wiredActiveTooth(state),
  })
    .filter((cell) => cell.active)
    .map((cell) => cell.tooth);

function wiredSelection(rows: readonly WiredRow[], jaw: "upper" | "lower" = "upper") {
  return withSites(
    initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "zimmer/ti-base.stl",
      jaw,
      sites: [],
    }),
    rows,
  );
}

describe("the chart and the stepper cannot disagree about which site is being worked on", () => {
  const ROWS: WiredRow[] = [{ tooth: 4 }, { tooth: 13 }, { tooth: 5 }];

  it("a chart click puts the stepper on that site — for every site", () => {
    const start = wiredSelection(ROWS);
    for (const row of ROWS) {
      const moved = wiredClick(start, row.tooth);
      expect(wiredActiveTooth(moved)).toBe(row.tooth);
      expect(litTeeth(moved, ROWS)).toEqual([row.tooth]);
    }
  });

  it("a stepper move lights exactly that tooth on the chart", () => {
    let state = wiredSelection(ROWS);
    const walked: (number | null)[] = [];
    for (let i = 0; i < ROWS.length; i += 1) {
      walked.push(wiredActiveTooth(state));
      expect(litTeeth(state, ROWS)).toEqual([wiredActiveTooth(state)]);
      state = stepSite(state, 1);
    }
    expect(walked).toEqual([4, 13, 5]);
  });

  it("no sites: no cursor and no lit tooth (the chart cannot invent one)", () => {
    const empty = wiredSelection([]);
    expect(wiredActiveTooth(empty)).toBeNull();
    expect(litTeeth(empty, [])).toEqual([]);
  });

  it("a full arch: the cursor reaches all 16, and the auto-increment refuses a 17th", () => {
    const all: WiredRow[] = Array.from({ length: 16 }, (_, i) => ({ tooth: i + 1 }));
    let state = wiredSelection(all);
    for (let i = 0; i < all.length; i += 1) {
      expect(litTeeth(state, all)).toEqual([i + 1]);
      state = stepSite(state, 1);
    }
    expect(
      nextToothNumber({ jaw: "upper", usedTeeth: all.map((r) => r.tooth), lastTooth: 16 }),
    ).toBeNull();
  });

  it("a site on the OTHER jaw stays reachable, and is still the one shared cursor", () => {
    const mixed: WiredRow[] = [{ tooth: 4 }, { tooth: 30 }];
    const moved = wiredClick(wiredSelection(mixed), 30);
    expect(wiredActiveTooth(moved)).toBe(30);
    expect(litTeeth(moved, mixed)).toEqual([30]);
    const cell = cellsByTooth(
      buildToothCells({ jaw: moved.jaw, sites: wiredChartSites(moved, mixed), activeTooth: 30 }),
    ).get(30);
    expect(cell?.inCaseJaw).toBe(false);
    expect(cell?.flags).toContain("off-jaw");
  });

  it("deleting the site under the cursor never leaves the chart lighting a stranger", () => {
    const onLast = wiredClick(wiredSelection(ROWS), 5);
    expect(onLast.activeSiteIndex).toBe(2);
    const shorter: WiredRow[] = [{ tooth: 4 }];
    const after = withSites(onLast, shorter);
    expect(wiredActiveTooth(after)).toBe(4);
    expect(litTeeth(after, shorter)).toEqual([4]);
  });

  it("never lights two teeth at once, even when two rows claim one number", () => {
    const duplicated: WiredRow[] = [{ tooth: 4 }, { tooth: 4 }];
    expect(litTeeth(wiredSelection(duplicated), duplicated)).toHaveLength(1);
  });
});

/**
 * THE RUN GATE, reached through the chart's own controls. The chart introduced two new ways to
 * change what a run would submit (click-to-add and the auto-increment), and one new way to move
 * the cursor. None of them may put a run within reach of an UNREVIEWED site — the disclaimer's
 * gate ("enabled only after all sites have been reviewed") is the whole reason
 * `authorizeRun` exists, and a new control is exactly how such a gate quietly re-opens.
 */
describe("no chart control can reach a run without the reviews", () => {
  const fullyReviewed = (state: LibrarySelection): LibrarySelection => {
    let out = state;
    state.sites.forEach((_, index) => {
      out = withVariant(out, index, "6020");
      out = withReviewed(out, index, true);
    });
    return out;
  };

  it("(control) a fully declared and reviewed case authorizes", () => {
    const ready = fullyReviewed(wiredSelection([{ tooth: 4 }, { tooth: 13 }]));
    expect(canRun({ selection: ready, duplicateTeeth: [] })).toBe(true);
    expect(authorizeRun({ selection: ready, duplicateTeeth: [] }).ok).toBe(true);
  });

  it("a site added FROM THE CHART re-closes a gate that was open", () => {
    const ready = fullyReviewed(wiredSelection([{ tooth: 4 }, { tooth: 13 }]));
    // App: setConfirmedSites([...prev, { tooth, center }]) -> the sync effect -> withSites
    const withNewSite = withSites(ready, [{ tooth: 4 }, { tooth: 13 }, { tooth: 5 }]);
    const blockers = runBlockers({ selection: withNewSite, duplicateTeeth: [] }).join(" | ");
    expect(authorizeRun({ selection: withNewSite, duplicateTeeth: [] }).ok).toBe(false);
    expect(blockers).toContain("cap variant for site 3");
    expect(blockers).toContain("review of site 3");
  });

  it("the auto-incremented number is an ordinary unreviewed site, not a shortcut", () => {
    const ready = fullyReviewed(wiredSelection([{ tooth: 4 }]));
    const next = nextToothNumber({ jaw: "upper", usedTeeth: [4], lastTooth: 4 });
    expect(next).toBe(5);
    const after = withSites(ready, [{ tooth: 4 }, { tooth: next as number }]);
    expect(authorizeRun({ selection: after, duplicateTeeth: [] }).ok).toBe(false);
  });

  it("moving the cursor authorizes nothing at all", () => {
    const unreviewed = wiredSelection([{ tooth: 4 }, { tooth: 13 }]);
    expect(authorizeRun({ selection: wiredClick(unreviewed, 13), duplicateTeeth: [] }).ok).toBe(
      false,
    );
  });
});
