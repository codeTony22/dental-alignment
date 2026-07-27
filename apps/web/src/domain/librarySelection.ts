/**
 * THE LIBRARY SELECTION (cap decoding) — the operator's explicit choices, as a pure state machine.
 *
 * Client directive 2026-07-25 (their library-selection screenshots): "THE LAB CHOOSES, THE
 * SOFTWARE NEVER GUESSES." The backend now refuses a run that does not NAME the implant system
 * and the construction part; this module is the client half of that contract — what the operator
 * has chosen so far, what is still missing, and (the part the disclaimer turns on) which sites
 * they have actually REVIEWED.
 *
 * Two rules earn this a state machine rather than four loose useStates:
 *
 *  1. A REVIEW IS ABOUT A SPECIFIC PART. The acknowledgment says "the library part selected
 *     matches the corresponding scan data" — so changing what is selected must invalidate the
 *     review that was made against the old selection. Changing a site's cap variant clears THAT
 *     site's review; changing the implant system, the construction part, the jaw or the relief
 *     clears EVERY site's (they all describe the same shipped part).
 *  2. A CAP VARIANT BELONGS TO ONE SYSTEM. Switching the system drops every chosen variant —
 *     carrying a zimmer id into a neodent run is exactly the silent mismatch the gate exists to
 *     prevent (the backend would 422, but the operator should never get that far).
 *
 * Framework-free (no React, no fetch): every transition is a pure function returning a new state.
 */
import type { ConstructionPart, Jaw, LibraryCatalogEntry, LibraryCatalogGroup } from "./types";

/** The client's default tissue clearance for the emitted construction part (mirrors the
 *  worker's pipeline/final_product.DEFAULT_GINGIVAL_OFFSET_MM — one number, two languages). */
export const GINGIVAL_OFFSET_DEFAULT_MM = 0.2;

/** The backend's own bounds (server.py `_MAX_GINGIVAL_OFFSET_MM`): a relief is a fraction of a
 *  millimetre, so anything past 1mm is a typo, not a clinical intent. Rejected here too, with
 *  the same reasoning, so the operator sees it before the round trip. */
export const GINGIVAL_OFFSET_MIN_MM = 0;
export const GINGIVAL_OFFSET_MAX_MM = 1.0;

/** The input's step: the relief is chosen in 0.05mm increments (0.20 is the client's default). */
export const GINGIVAL_OFFSET_STEP_MM = 0.05;

/** One site's half of the selection: which cap the operator declared for it, and whether they
 *  have reviewed the three panels for it. `variantId` is a CATALOG id — the plain variant for a
 *  current part ("6020"), the archive-qualified id for a superseded one
 *  ("superseded-2026-07-13--6020"), which is exactly what the run accepts as `declared_variant`. */
export interface SiteSelection {
  readonly tooth: number;
  readonly variantId: string | null;
  readonly reviewed: boolean;
}

export interface LibrarySelection {
  /** The implant system (a non-legacy catalog group's model). null = nothing chosen yet. */
  readonly model: string | null;
  /** The construction part's catalog `path_id`. null = nothing chosen yet. */
  readonly constructionPathId: string | null;
  readonly jaw: Jaw;
  /** The RAW text in the offset input — kept verbatim so a half-typed "0." is not rewritten
   *  under the operator's cursor; `gingivalOffsetMm` is the last value that actually parsed. */
  readonly gingivalOffsetInput: string;
  readonly gingivalOffsetMm: number;
  readonly sites: readonly SiteSelection[];
  /** Which site the stepper is on (clamped into range by every transition that can shrink the list). */
  readonly activeSiteIndex: number;
}

/** "0.20" — the offset's display form (2dp), used for the initial input text and read-outs. */
export function formatOffsetMm(valueMm: number): string {
  return valueMm.toFixed(2);
}

/** A fresh selection for a case: the case's name-matched SUGGESTIONS are preselected — a
 *  suggestion the operator can see and change is not a guess, and the backend still requires it
 *  to be sent back explicitly. A case that matched nothing starts empty and simply cannot run
 *  until the operator picks (which is the point). */
export function initialSelection(input: {
  readonly suggestedModel: string | null;
  readonly suggestedConstruction: string | null;
  readonly jaw: Jaw;
  readonly sites: readonly { readonly tooth: number; readonly declaredVariant?: string | null }[];
}): LibrarySelection {
  return {
    model: input.suggestedModel,
    constructionPathId: input.suggestedConstruction,
    jaw: input.jaw,
    gingivalOffsetInput: formatOffsetMm(GINGIVAL_OFFSET_DEFAULT_MM),
    gingivalOffsetMm: GINGIVAL_OFFSET_DEFAULT_MM,
    sites: input.sites.map((s) => ({
      tooth: s.tooth,
      variantId: s.declaredVariant && s.declaredVariant.trim() !== "" ? s.declaredVariant : null,
      reviewed: false,
    })),
    activeSiteIndex: 0,
  };
}

/** Every site's review dropped — what any selection change that describes the SHIPPED PART does
 *  (system, construction, jaw, relief): the operator reviewed a different part than the one that
 *  would now be processed. */
function clearAllReviews(sites: readonly SiteSelection[]): SiteSelection[] {
  return sites.map((s) => (s.reviewed ? { ...s, reviewed: false } : s));
}

/** Switching the implant SYSTEM drops every chosen cap variant (a variant id belongs to one
 *  system's catalog) and therefore every review. */
export function withModel(state: LibrarySelection, model: string | null): LibrarySelection {
  if (state.model === model) return state;
  return {
    ...state,
    model,
    sites: state.sites.map((s) => ({ ...s, variantId: null, reviewed: false })),
  };
}

export function withConstruction(state: LibrarySelection, pathId: string | null): LibrarySelection {
  if (state.constructionPathId === pathId) return state;
  return { ...state, constructionPathId: pathId, sites: clearAllReviews(state.sites) };
}

export function withJaw(state: LibrarySelection, jaw: Jaw): LibrarySelection {
  if (state.jaw === jaw) return state;
  return { ...state, jaw, sites: clearAllReviews(state.sites) };
}

/**
 * The offset input, as typed. The raw text is always kept (so the field never fights the
 * operator mid-keystroke); the numeric value only moves when the text parses INSIDE the bounds —
 * an out-of-range or unparseable entry leaves the last good number in place and is reported by
 * `offsetError`, which blocks Process. Every accepted change clears the reviews: the relief
 * changes the emitted part's surface, so an earlier review described a different part.
 */
export function withOffsetInput(state: LibrarySelection, raw: string): LibrarySelection {
  const parsed = parseGingivalOffset(raw);
  if (parsed.kind === "error") return { ...state, gingivalOffsetInput: raw };
  if (parsed.valueMm === state.gingivalOffsetMm) return { ...state, gingivalOffsetInput: raw };
  return {
    ...state,
    gingivalOffsetInput: raw,
    gingivalOffsetMm: parsed.valueMm,
    sites: clearAllReviews(state.sites),
  };
}

/** One site's declared cap. Only THAT site's review is dropped — the other sites' parts did not
 *  change, and re-reviewing them would be busywork the disclaimer does not ask for. */
export function withVariant(
  state: LibrarySelection,
  siteIndex: number,
  variantId: string | null,
): LibrarySelection {
  const site = state.sites[siteIndex];
  if (site === undefined || site.variantId === variantId) return state;
  return {
    ...state,
    sites: state.sites.map((s, i) => (i === siteIndex ? { ...s, variantId, reviewed: false } : s)),
  };
}

/** The acknowledgment checkbox for one site ("reviewed"). */
export function withReviewed(
  state: LibrarySelection,
  siteIndex: number,
  reviewed: boolean,
): LibrarySelection {
  const site = state.sites[siteIndex];
  if (site === undefined || site.reviewed === reviewed) return state;
  return { ...state, sites: state.sites.map((s, i) => (i === siteIndex ? { ...s, reviewed } : s)) };
}

export function withActiveSite(state: LibrarySelection, index: number): LibrarySelection {
  if (state.sites.length === 0) return { ...state, activeSiteIndex: 0 };
  const clamped = Math.min(Math.max(index, 0), state.sites.length - 1);
  if (clamped === state.activeSiteIndex) return state;
  return { ...state, activeSiteIndex: clamped };
}

/** The '‹ n ›' stepper: a signed step, clamped at both ends (no wrap — an operator stepping past
 *  the last site should land on the last site, not silently back at the first). */
export function stepSite(state: LibrarySelection, delta: number): LibrarySelection {
  return withActiveSite(state, state.activeSiteIndex + delta);
}

/**
 * Re-key the selection against the step-3 rows: the operator can add/remove sites or edit a
 * tooth number while the dialog is closed. Choices are carried by TOOTH (the only stable key
 * both halves share); a tooth that vanished takes its choice with it, and a new tooth arrives
 * unchosen and unreviewed. A row whose declared variant was set outside the dialog is adopted.
 *
 * SPEAKING vs SILENT (verifier finding, 2026-07-25 — this was a live acknowledgment bypass).
 * A row that CARRIES a `declaredVariant` field is speaking about the declaration, including
 * when it says "" / null ("auto" in step 3's picker); a row without the field is silent and
 * leaves the dialog's choice alone. The distinction matters because the two halves must not
 * diverge: an operator who reviewed 6020 and then put that row back on "auto" used to leave
 * the selection claiming a REVIEWED 6020 while the run submitted no declaration at all — the
 * backend then auto-identified a part nobody reviewed, with the acknowledgment reading as
 * satisfied. Clearing the row therefore clears that site's variant AND its review, exactly as
 * changing it to another variant does: un-declaring a part is a selection change too.
 */
export function withSites(
  state: LibrarySelection,
  sites: readonly { readonly tooth: number; readonly declaredVariant?: string | null }[],
): LibrarySelection {
  const byTooth = new Map(state.sites.map((s) => [s.tooth, s] as const));
  const next = sites.map((row) => {
    const prior = byTooth.get(row.tooth);
    const states = row.declaredVariant !== undefined;
    const declared =
      typeof row.declaredVariant === "string" && row.declaredVariant.trim() !== ""
        ? row.declaredVariant
        : null;
    if (prior === undefined) return { tooth: row.tooth, variantId: declared, reviewed: false };
    // a variant changed elsewhere (step 3's picker) is a selection change like any other —
    // it invalidates this site's review; so is CLEARING it back to "auto"
    if (states && declared !== prior.variantId) {
      return { tooth: row.tooth, variantId: declared, reviewed: false };
    }
    return prior;
  });
  return withActiveSite({ ...state, sites: next }, state.activeSiteIndex);
}

/** The offset input's verdict: a value, or the sentence the field shows (and Process refuses on). */
export type OffsetParse =
  | { readonly kind: "ok"; readonly valueMm: number }
  | { readonly kind: "error"; readonly message: string };

export function parseGingivalOffset(raw: string): OffsetParse {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { kind: "error", message: "Enter a gingival profile offset (0 turns the relief off)." };
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value)) {
    return { kind: "error", message: `“${trimmed}” is not a number of millimetres.` };
  }
  if (value < GINGIVAL_OFFSET_MIN_MM || value > GINGIVAL_OFFSET_MAX_MM) {
    return {
      kind: "error",
      message:
        `The gingival profile offset must be between ${GINGIVAL_OFFSET_MIN_MM} and ` +
        `${formatOffsetMm(GINGIVAL_OFFSET_MAX_MM)} mm — past that the relief eats the part.`,
    };
  }
  return { kind: "ok", valueMm: value };
}

/** The offset field's error sentence, or null when the text in the box is a usable value. */
export function offsetError(state: LibrarySelection): string | null {
  const parsed = parseGingivalOffset(state.gingivalOffsetInput);
  return parsed.kind === "error" ? parsed.message : null;
}

/**
 * What is still missing, in the operator's own language — the list the Process button's
 * disabled-reason shows. Ordered the way the column is: system, then construction, then the
 * per-site cap, then the offset. Empty = every REQUIRED SELECTION is made (the acknowledgment
 * is judged separately by `unreviewedSiteNumbers`, since it is a different kind of gate).
 */
export function missingSelections(state: LibrarySelection): string[] {
  const missing: string[] = [];
  if (!state.model) missing.push("the implant system");
  if (!state.constructionPathId) missing.push("the construction part");
  state.sites.forEach((site, i) => {
    if (site.variantId === null) missing.push(`the cap variant for site ${i + 1} (tooth ${site.tooth})`);
  });
  const offset = offsetError(state);
  if (offset !== null) missing.push("a valid gingival profile offset");
  return missing;
}

/** 1-based numbers of the sites whose "reviewed" box is still unticked — the disclaimer's own
 *  gate ("enabled only after all sites have been reviewed"). */
export function unreviewedSiteNumbers(state: LibrarySelection): number[] {
  const out: number[] = [];
  state.sites.forEach((site, i) => {
    if (!site.reviewed) out.push(i + 1);
  });
  return out;
}

/** Every reason Process is refused, missing selections first. Empty = the run may go. */
export function processBlockers(state: LibrarySelection): string[] {
  const blockers = [...missingSelections(state)];
  if (state.sites.length === 0) {
    blockers.push("at least one marked site");
    return blockers;
  }
  const unreviewed = unreviewedSiteNumbers(state);
  if (unreviewed.length > 0) {
    blockers.push(
      `a review of site${unreviewed.length > 1 ? "s" : ""} ${unreviewed.join(", ")}`,
    );
  }
  return blockers;
}

export function canProcess(state: LibrarySelection): boolean {
  return processBlockers(state).length === 0;
}

/** The active site, or null when the case has no marked sites at all. */
export function activeSite(state: LibrarySelection): SiteSelection | null {
  return state.sites[state.activeSiteIndex] ?? null;
}

// ---- CATALOG SHAPING -----------------------------------------------------------------------

/** What the interface calls a legacy shelf. A legacy group's `model` is the raw name of a
 *  CLIENT-OWNED data folder that we do not rename (it addresses the files on the wire), so it
 *  stays the key and never becomes the caption. */
export const LEGACY_SHELF_LABEL = "Legacy shelf";

/**
 * model -> the name the interface prints for that catalog group. A real implant system is named
 * by its own model dir; a legacy shelf gets `LEGACY_SHELF_LABEL` instead of its folder name, so
 * a vendor-specific directory name never reaches the screen. Several legacy shelves are numbered
 * in catalog order (which is sorted server-side) so their tabs stay distinguishable.
 */
export function catalogGroupLabels(
  groups: readonly Pick<LibraryCatalogGroup, "model" | "legacy">[],
): ReadonlyMap<string, string> {
  const legacyModels = groups.filter((g) => g.legacy).map((g) => g.model);
  const labels = new Map<string, string>();
  for (const group of groups) {
    if (!group.legacy) {
      labels.set(group.model, group.model);
      continue;
    }
    const ordinal = legacyModels.indexOf(group.model) + 1;
    labels.set(
      group.model,
      legacyModels.length > 1 ? `${LEGACY_SHELF_LABEL} ${ordinal}` : LEGACY_SHELF_LABEL,
    );
  }
  return labels;
}

/** An implant SYSTEM the run can actually be sent: a `library/caps/<model>/` group. Legacy
 *  shelves (`*-library` dirs) are listed by the catalog but are NOT systems — the backend has no
 *  cap library for them and would refuse ("unknown implant system"), so they are offered as
 *  disabled entries with the reason instead of being silently hidden. */
export interface SystemChoice {
  /** The wire key (the catalog group's model dir) — what a run and a mesh URL are sent. */
  readonly model: string;
  /** What the operator reads. Same as `model` for a real system; the neutral shelf name for a
   *  legacy group, whose model is a client data-folder name the interface does not print. */
  readonly label: string;
  readonly selectable: boolean;
  readonly variantCount: number;
  /** Why it cannot be chosen (null when it can). */
  readonly unavailableReason: string | null;
}

export function systemChoices(groups: readonly LibraryCatalogGroup[]): SystemChoice[] {
  const labels = catalogGroupLabels(groups);
  return groups.map((group) => ({
    model: group.model,
    label: labels.get(group.model) ?? group.model,
    selectable: !group.legacy,
    variantCount: group.variants.length,
    unavailableReason: group.legacy
      ? "a legacy shelf, not an implant system — no cap library the run can load"
      : null,
  }));
}

/** "Superseded 2026-07-13" — the archive heading the superseded parts are grouped under, read
 *  from the entry's own filename ("superseded-2026-07-13/neodent-gm-6020.stl"); null when the
 *  entry is current. Same parse as LibraryBrowser's per-card badge (pinned by a test) — the
 *  heading is Sentence case because it labels a GROUP, the badge lowercase because it labels a
 *  card. */
export function supersededArchiveLabel(entry: LibraryCatalogEntry): string | null {
  if (!entry.flags.includes("superseded")) return null;
  const dir = entry.filename.split("/")[0] ?? "";
  const date = dir.startsWith("superseded-") ? dir.slice("superseded-".length) : null;
  return date ? `Superseded ${date}` : "Superseded";
}

export interface VariantGroup {
  readonly label: string;
  readonly entries: readonly LibraryCatalogEntry[];
}

/**
 * The cap-variant list for one system, split the way the client's dialog splits it: the CURRENT
 * parts first, then each superseded archive as its own clearly separated group (one per archive
 * date — a shelf archived twice reads as two groups, not one blurred pile). Order within a group
 * is the catalog's own (deterministic, sorted server-side); archive groups are ordered by label
 * so the display never depends on directory iteration order.
 */
export function partitionVariants(entries: readonly LibraryCatalogEntry[]): {
  readonly current: readonly LibraryCatalogEntry[];
  readonly archives: readonly VariantGroup[];
} {
  const current: LibraryCatalogEntry[] = [];
  const archives = new Map<string, LibraryCatalogEntry[]>();
  for (const entry of entries) {
    const label = supersededArchiveLabel(entry);
    if (label === null) {
      current.push(entry);
      continue;
    }
    const bucket = archives.get(label);
    if (bucket) bucket.push(entry);
    else archives.set(label, [entry]);
  }
  return {
    current,
    archives: [...archives.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([label, group]) => ({ label, entries: group })),
  };
}

/** The construction dropdown's option groups: one per vendor, vendors and files in the
 *  catalog's own sorted order (the listing is already deterministic server-side). */
export function groupConstructionsByVendor(
  parts: readonly ConstructionPart[],
): { readonly vendor: string; readonly parts: readonly ConstructionPart[] }[] {
  const byVendor = new Map<string, ConstructionPart[]>();
  for (const part of parts) {
    const bucket = byVendor.get(part.vendor);
    if (bucket) bucket.push(part);
    else byVendor.set(part.vendor, [part]);
  }
  return [...byVendor.entries()].map(([vendor, vendorParts]) => ({ vendor, parts: vendorParts }));
}

/** The catalog entry a site's chosen variant id refers to, within the chosen system — null when
 *  nothing is chosen, the system is not loaded, or (defensively) the id is not in the catalog. */
export function findVariantEntry(
  groups: readonly LibraryCatalogGroup[],
  model: string | null,
  variantId: string | null,
): LibraryCatalogEntry | null {
  if (model === null || variantId === null) return null;
  const group = groups.find((g) => g.model === model);
  return group?.variants.find((v) => v.id === variantId) ?? null;
}
