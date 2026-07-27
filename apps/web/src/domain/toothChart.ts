/**
 * THE DENTAL TOOTH CHART — Universal numbering (1-32) as a SITE PICKER.
 *
 * Client gap (RealGUIDE screenshot parity, 2026-07-25): their left rail is an arch diagram, and
 * it is how the operator navigates a case — "tooth 3" is the language the lab, the doctor and
 * the prescription all speak, while "site 2 of 3" is language this app invented. The stepper
 * stays (it is the dialog's own control); the chart is the same cursor drawn anatomically.
 *
 * TWO RULES EARN THIS A DOMAIN MODULE rather than JSX with numbers in it:
 *
 *  1. THE CHART AND THE STEPPER SHARE ONE CURSOR. The chart does not own a selection — it
 *     renders `activeTooth` and reports clicks. App maps that onto the SAME
 *     `LibrarySelection.activeSiteIndex` the stepper moves, so the two can never disagree about
 *     which site is being worked on (they would otherwise compete, and the operator would have
 *     no way to tell which one the dialog believed).
 *  2. A TOOTH NUMBER IS A CLINICAL FACT, not a label. Universal numbering fixes which jaw a
 *     number belongs to (1-16 upper, 17-32 lower) and which anatomical tooth it names. A site
 *     placed on a number outside the case's jaw is therefore a REPORTABLE inconsistency, not a
 *     styling question — hence the `off-jaw` flag rather than silently hiding the row.
 *
 * Framework-free (no React, no fetch), like every other domain module here.
 */
import type { CaptureVerdict, Jaw } from "./types";

/** Universal numbering's range. Every helper here refuses anything outside it. */
export const UNIVERSAL_FIRST_TOOTH = 1;
export const UNIVERSAL_LAST_TOOTH = 32;

/** Upper arch, patient's RIGHT third molar (1) round to the LEFT third molar (16). */
export const UPPER_TEETH: readonly number[] = Array.from({ length: 16 }, (_, i) => i + 1);
/** Lower arch, patient's LEFT third molar (17) round to the RIGHT third molar (32). */
export const LOWER_TEETH: readonly number[] = Array.from({ length: 16 }, (_, i) => i + 17);

export function isUniversalTooth(tooth: number): boolean {
  return Number.isInteger(tooth) && tooth >= UNIVERSAL_FIRST_TOOTH && tooth <= UNIVERSAL_LAST_TOOTH;
}

/** Which arch a Universal number belongs to; null when the number is not a tooth at all. */
export function jawOfTooth(tooth: number): Jaw | null {
  if (!isUniversalTooth(tooth)) return null;
  return tooth <= 16 ? "upper" : "lower";
}

export function teethOfJaw(jaw: Jaw): readonly number[] {
  return jaw === "upper" ? UPPER_TEETH : LOWER_TEETH;
}

/** The eight positions of a quadrant, from the third molar inwards to the central incisor. */
const QUADRANT_POSITIONS: readonly string[] = [
  "third molar",
  "second molar",
  "first molar",
  "second premolar",
  "first premolar",
  "canine",
  "lateral incisor",
  "central incisor",
];

/**
 * The anatomical name of a Universal number ("upper right first molar"). Written out rather
 * than left as a bare number because it is the ACCESSIBLE label: a screen reader announcing
 * "3" tells an operator nothing, "tooth 3, upper right first molar" tells them everything.
 * Universal walks 1→16 across the upper arch (right→left) and 17→32 across the lower
 * (left→right), so the quadrant and the position within it are both derivable.
 */
export function toothName(tooth: number): string {
  const jaw = jawOfTooth(tooth);
  if (jaw === null) return "unknown tooth";
  // index 0-15 across the arch, in the direction Universal numbers run for that arch
  const acrossArch = jaw === "upper" ? tooth - 1 : tooth - 17;
  const side = jaw === "upper" ? (acrossArch < 8 ? "right" : "left") : acrossArch < 8 ? "left" : "right";
  const intoQuadrant = acrossArch < 8 ? acrossArch : 15 - acrossArch;
  return `${jaw} ${side} ${QUADRANT_POSITIONS[intoQuadrant] ?? "tooth"}`;
}

/** "Tooth 3 — upper right first molar", the chart button's accessible name. */
export function toothLabel(tooth: number): string {
  return `Tooth ${tooth} — ${toothName(tooth)}`;
}

export interface ArchQuadrant {
  readonly label: string;
  readonly teeth: readonly number[];
}

export interface ArchRow {
  readonly jaw: Jaw;
  readonly label: string;
  readonly quadrants: readonly [ArchQuadrant, ArchQuadrant];
}

/**
 * THE ARCH DIAGRAM'S LAYOUT — the familiar chart, not the numeric order.
 *
 * Upper reads left-to-right 1…16; lower reads left-to-right 32…17. That reversal is the whole
 * point of the diagram: column i then holds the SAME SIDE of the mouth top and bottom (1 sits
 * above 32, both third molars on the patient's right), which is what makes a chart readable at
 * a glance. Pinned by a test — every column pairs to 33.
 */
export const ARCH_ROWS: readonly [ArchRow, ArchRow] = [
  {
    jaw: "upper",
    label: "Upper arch · 1–16",
    quadrants: [
      { label: "Upper right", teeth: UPPER_TEETH.slice(0, 8) },
      { label: "Upper left", teeth: UPPER_TEETH.slice(8) },
    ],
  },
  {
    jaw: "lower",
    label: "Lower arch · 17–32",
    quadrants: [
      { label: "Lower right", teeth: [...LOWER_TEETH].slice(8).reverse() },
      { label: "Lower left", teeth: [...LOWER_TEETH].slice(0, 8).reverse() },
    ],
  },
];

/** Every tooth of a row in display order — the two quadrants, midline in the middle. */
export function archRowTeeth(row: ArchRow): number[] {
  return [...row.quadrants[0].teeth, ...row.quadrants[1].teeth];
}

/**
 * What the chart says about ONE tooth that carries a site, beyond "it exists". Each flag is a
 * condition the operator would otherwise have to go and find in another panel:
 *  - `capture-rescan` / `capture-marginal`: the intake gate's verdict for this site.
 *  - `rotation-unverified`: the shipped rotation could not be verified against the coded
 *    cutouts (the run row's own `clocking.rotationUnverified`).
 *  - `variant-mismatch`: the independent measurement DISPUTES the declared cap.
 *  - `duplicate-tooth`: two rows claim this number (the run gate refuses it).
 *  - `off-jaw`: the site's number belongs to the other arch than the one selected for the run.
 */
export type ToothFlag =
  | "capture-rescan"
  | "capture-marginal"
  | "rotation-unverified"
  | "variant-mismatch"
  | "duplicate-tooth"
  | "off-jaw";

/** The operator-facing sentence for each flag — one place, so the chip and the tooltip agree. */
export const TOOTH_FLAG_TEXT: Readonly<Record<ToothFlag, string>> = {
  "capture-rescan": "capture needs a rescan",
  "capture-marginal": "capture is marginal",
  "rotation-unverified": "rotation unverified",
  "variant-mismatch": "declared cap disputed by the measurement",
  "duplicate-tooth": "tooth number used by more than one site",
  "off-jaw": "site is on the other arch than the selected jaw",
};

/** One site, as the chart needs to see it. Deliberately narrow: the chart depends on facts, not
 *  on the shape of the run payload (see `chartSitesFrom` for the adapter). */
export interface ToothChartSite {
  readonly tooth: number;
  /** Any registration mark or painted patch placed for this site. */
  readonly marked: boolean;
  /** The review acknowledgment for this site (the state the Process gate counts). */
  readonly reviewed: boolean;
  readonly flags: readonly ToothFlag[];
}

/** One rendered tooth. `siteIndex` is the confirm-row index — the chart's click target. */
export interface ToothCell {
  readonly tooth: number;
  readonly jaw: Jaw;
  readonly label: string;
  readonly siteIndex: number | null;
  readonly marked: boolean;
  readonly reviewed: boolean;
  readonly active: boolean;
  /** Whether this tooth belongs to the arch the run is selected for (the other is dimmed). */
  readonly inCaseJaw: boolean;
  readonly flags: readonly ToothFlag[];
}

export interface ToothChartInput {
  /** The jaw the RUN is selected for (LibrarySelection.jaw) — highlighted; the other is dimmed. */
  readonly jaw: Jaw;
  readonly sites: readonly ToothChartSite[];
  /** The shared cursor, as a tooth number (null when no site is selected). */
  readonly activeTooth: number | null;
}

/**
 * Every tooth of the chart with its state. A tooth carrying MORE THAN ONE site keeps the FIRST
 * row's index (the duplicate is already flagged, and the gate refuses the run until it is
 * fixed — the chart must not invent a rule about which of the two wins).
 */
export function buildToothCells({ jaw, sites, activeTooth }: ToothChartInput): ToothCell[] {
  const firstByTooth = new Map<number, { site: ToothChartSite; index: number }>();
  sites.forEach((site, index) => {
    if (!firstByTooth.has(site.tooth)) firstByTooth.set(site.tooth, { site, index });
  });
  const cells: ToothCell[] = [];
  for (const row of ARCH_ROWS) {
    for (const tooth of archRowTeeth(row)) {
      const hit = firstByTooth.get(tooth);
      cells.push({
        tooth,
        jaw: row.jaw,
        label: toothLabel(tooth),
        siteIndex: hit?.index ?? null,
        marked: hit?.site.marked ?? false,
        reviewed: hit?.site.reviewed ?? false,
        active: activeTooth === tooth && hit !== undefined,
        inCaseJaw: row.jaw === jaw,
        flags: hit?.site.flags ?? [],
      });
    }
  }
  return cells;
}

/** Index the cells by tooth number, for the renderer's per-button lookup. */
export function cellsByTooth(cells: readonly ToothCell[]): ReadonlyMap<number, ToothCell> {
  return new Map(cells.map((c) => [c.tooth, c] as const));
}

// ---- ADAPTER FROM THE APP'S OWN SHAPES ------------------------------------------------------

/** The confirm row, as far as the chart cares: its tooth and whether anything is marked on it. */
export interface ChartConfirmRow {
  readonly tooth: number;
  readonly markedPoints?: readonly unknown[];
  readonly centerMark?: unknown;
  readonly rimMark?: unknown;
  readonly rimPoints?: readonly unknown[];
}

/** The run row, as far as the chart cares (structurally satisfied by RunSiteResult). */
export interface ChartRunRow {
  readonly tooth: number;
  readonly clocking: { readonly rotationUnverified: boolean } | null;
  readonly variant: { readonly declared: string | null; readonly flags: readonly string[] };
}

/** A row carries marks when the doctor has placed ANY of the four kinds. */
export function rowIsMarked(row: ChartConfirmRow): boolean {
  if ((row.markedPoints?.length ?? 0) > 0) return true;
  if ((row.rimPoints?.length ?? 0) > 0) return true;
  return row.centerMark !== undefined || row.rimMark !== undefined;
}

/**
 * Fold the app's four sources — the confirm rows, the library selection's per-site review, the
 * capture verdicts and the last run's rows — into the chart's own narrow site shape. Index-
 * aligned with `rows` (the same alignment `siteCaptures` already uses in App).
 *
 * A flag is only ever raised from data that EXISTS: no run, no rotation/variant flags; no
 * capture assessment, no capture flag. The chart never implies a verdict nobody measured.
 */
export function chartSitesFrom(input: {
  readonly rows: readonly ChartConfirmRow[];
  readonly reviewedTeeth: readonly number[];
  readonly captures: ReadonlyArray<CaptureVerdict | null>;
  readonly runRows: readonly ChartRunRow[];
  readonly duplicateTeeth: readonly number[];
  readonly jaw: Jaw;
}): ToothChartSite[] {
  const reviewed = new Set(input.reviewedTeeth);
  const runByTooth = new Map(input.runRows.map((r) => [r.tooth, r] as const));
  return input.rows.map((row, index) => {
    const flags: ToothFlag[] = [];
    const capture = input.captures[index] ?? null;
    if (capture === "rescan") flags.push("capture-rescan");
    else if (capture === "marginal") flags.push("capture-marginal");
    const run = runByTooth.get(row.tooth);
    if (run?.clocking?.rotationUnverified === true) flags.push("rotation-unverified");
    if (run !== undefined && variantIsDisputed(run.variant)) flags.push("variant-mismatch");
    if (input.duplicateTeeth.includes(row.tooth)) flags.push("duplicate-tooth");
    if (jawOfTooth(row.tooth) !== input.jaw) flags.push("off-jaw");
    return {
      tooth: row.tooth,
      marked: rowIsMarked(row),
      reviewed: reviewed.has(row.tooth),
      flags,
    };
  });
}

/** The declared cap is DISPUTED when a safety flag specifically names the declaration — the
 *  same read `agreementState` makes for the results table's Agreement column. */
function variantIsDisputed(variant: ChartRunRow["variant"]): boolean {
  if (variant.declared === null) return false;
  return variant.flags.some((f) => f.toLowerCase().includes("declared"));
}

// ---- AUTOMATED TOOTH NUMBER INCREASING ------------------------------------------------------

/**
 * Their toggle's default (RealGUIDE screenshot: checked). Auto-numbering is a convenience for
 * the common case — sites added along an arch in order — and is always overridable, both by
 * turning it off and by clicking the tooth you actually mean on the chart.
 */
export const AUTO_TOOTH_NUMBER_DEFAULT = true;

/**
 * THE NEXT TOOTH NUMBER for a new site: the first FREE number after the last site's, within the
 * selected jaw, wrapping once round the arch. Returns null when the jaw is full (all 16 taken)
 * or when the jaw has no free number at all — the caller must then refuse to add rather than
 * inventing a number outside the arch or colliding with an existing row.
 *
 * The wrap matters: an operator who starts at 14 and works distally reaches 16 and then wants
 * 1, not "no more sites". Skipping used numbers is how the existing duplicate-tooth guard
 * (findDuplicateTeeth, which BLOCKS the run) is respected at the source instead of after
 * the fact.
 */
export function nextToothNumber(input: {
  readonly jaw: Jaw;
  readonly usedTeeth: readonly number[];
  /** The tooth the previous site was added on; null starts from the arch's first number. */
  readonly lastTooth: number | null;
}): number | null {
  const arch = teethOfJaw(input.jaw);
  const used = new Set(input.usedTeeth);
  const startIndex =
    input.lastTooth !== null && jawOfTooth(input.lastTooth) === input.jaw
      ? arch.indexOf(input.lastTooth) + 1
      : 0;
  for (let step = 0; step < arch.length; step += 1) {
    const tooth = arch[(startIndex + step) % arch.length];
    if (tooth !== undefined && !used.has(tooth)) return tooth;
  }
  return null;
}

// ---- WHO OWNS THE NEXT CLICK ON THE SCAN ----------------------------------------------------

/**
 * Every tool that can hold the viewer's ONE-SHOT PICK, as a flag. Adding a site from the chart
 * arms that same pick, and the controller's `enterPointPick` silently SUPERSEDES whatever was
 * waiting — so two armed tools do not "share" the click, the second one steals it and the first
 * is left showing a banner for a click that will never come back to it.
 *
 * VERIFIER FINDING (2026-07-25): this list lived as an inline ternary in App and named only four
 * of the six owners. With a correspondence feature armed, clicking an empty tooth stole the
 * click: the operator's next click on the scan created a SITE while the correspondence panel
 * still said it was waiting for a feature point. Lifted here as a total record so the compiler
 * requires every owner to be answered for, and so the rule is pinned by tests rather than by
 * reading a ternary.
 */
export interface ScanClickOwners {
  readonly brushing: boolean;
  readonly placingMark: boolean;
  readonly rimPoints: boolean;
  readonly trenchMark: boolean;
  readonly correspondencePoint: boolean;
  readonly libraryMark: boolean;
  readonly runInFlight: boolean;
}

/**
 * Why a site cannot be added right now — one sentence naming the tool that holds the click, or
 * null when the chart may arm. Order is the operator's: the tool nearest their hand first.
 * A REASON rather than a boolean, per the house rule that a disabled control says why.
 */
export function addSiteBlockedReason(owners: ScanClickOwners): string | null {
  if (owners.brushing) return "Finish or cancel the brush stroke first — it owns clicks on the scan.";
  if (owners.placingMark) {
    return "Finish or cancel the mark you are placing first — it owns clicks on the scan.";
  }
  if (owners.rimPoints) {
    return "Finish or cancel the rim-border points first — they own clicks on the scan.";
  }
  if (owners.trenchMark) return "Finish or cancel the trench mark first — it owns clicks on the scan.";
  if (owners.correspondencePoint) {
    return "Finish or cancel the correspondence point first — it owns clicks on the scan.";
  }
  if (owners.libraryMark) {
    return "Finish or cancel the library mark you are placing first — it owns the next click.";
  }
  if (owners.runInFlight) return "The automation is running — add sites once it finishes.";
  return null;
}

/** The verdict for a MANUALLY typed tooth number (auto-numbering off) — a value, or the
 *  sentence the field shows. Every refusal names the actual rule it broke. */
export type ToothEntryParse =
  | { readonly kind: "ok"; readonly tooth: number }
  | { readonly kind: "error"; readonly message: string };

export function parseToothEntry(
  raw: string,
  context: { readonly jaw: Jaw; readonly usedTeeth: readonly number[] },
): ToothEntryParse {
  const trimmed = raw.trim();
  if (trimmed === "") return { kind: "error", message: "Enter a tooth number (Universal, 1–32)." };
  const value = Number(trimmed);
  if (!Number.isInteger(value)) {
    return { kind: "error", message: `“${trimmed}” is not a whole tooth number.` };
  }
  if (!isUniversalTooth(value)) {
    return {
      kind: "error",
      message: `Universal numbering runs ${UNIVERSAL_FIRST_TOOTH}–${UNIVERSAL_LAST_TOOTH} — ${value} is not a tooth.`,
    };
  }
  if (context.usedTeeth.includes(value)) {
    return { kind: "error", message: `Tooth ${value} already has a site — pick a free tooth.` };
  }
  if (jawOfTooth(value) !== context.jaw) {
    return {
      kind: "error",
      message: `Tooth ${value} is on the ${jawOfTooth(value)} arch, but the run is selected for the ${context.jaw} jaw.`,
    };
  }
  return { kind: "ok", tooth: value };
}
