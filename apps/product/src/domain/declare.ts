/**
 * DECLARE'S DISPLAY RULES (plan §4 Declare / AM-8, slice 5a), framework-free: how the
 * worker-shaped catalog payload becomes system cards and variant shelves, the
 * visible-reset confirmation words, and the active-site defaulting shared by the
 * queue and the 3D stage.
 *
 * Direction of trust (AM-4): the EFFECTIVE system and its attribution come from the
 * BFF's `system` view (`source: "declared" | "suggested" | "none"`) — this module
 * never decides which system is in effect by comparing fields, and the reset a
 * switch causes happens SERVER-side; the only thing computed here is the sentence
 * that warns about it (with the count in words, per the visible-reset doctrine) and
 * the shapes the cards render from. Catalog rows arrive untyped from the worker;
 * rows without a usable id are dropped rather than rendered as undeclarable lies —
 * the same defensive posture as domain/intake's construction options.
 */
import type { CaseSessionDetail, SiteView } from "../api/client";

export interface SystemCard {
  readonly model: string;
  /** The number of catalog entries — a card hint, not a physics claim. */
  readonly variantCount: number;
  /** This is the system the case works against (the server's effective_model). */
  readonly effective: boolean;
  /** The effective system is still the SUGGESTION (server's `source`), so the UI
   * shows its "suggested" tag — an operator's declared system never carries it. */
  readonly suggested: boolean;
}

interface RawGroup {
  readonly model: string;
  readonly legacy: boolean;
  readonly variants: readonly Record<string, unknown>[];
}

/** The catalog groups that are real, declarable systems (non-legacy, well-shaped). */
function declarableGroups(detail: CaseSessionDetail): readonly RawGroup[] {
  return detail.catalog.groups.flatMap((row) => {
    const model = row["model"];
    if (typeof model !== "string") return [];
    if (row["legacy"] === true) return []; // a legacy shelf is not a system
    const variants = Array.isArray(row["variants"])
      ? (row["variants"] as Record<string, unknown>[])
      : [];
    return [{ model, legacy: false, variants }];
  });
}

export function systemCards(detail: CaseSessionDetail): readonly SystemCard[] {
  const effective = detail.system.effective_model;
  return declarableGroups(detail).map((group) => ({
    model: group.model,
    variantCount: group.variants.length,
    effective: group.model === effective,
    suggested: group.model === effective && detail.system.source === "suggested",
  }));
}

export interface VariantCard {
  /** The catalog's own entry id — exactly what the declaration PUT sends. */
  readonly id: string;
  readonly label: string;
  readonly dims: string;
  readonly superseded: boolean;
}

/** "Ø 5.0 × 2.0 mm", or honesty when the catalog could not measure the file. */
export function dimsLabel(
  rimDiameterMm: number | null,
  heightMm: number | null,
): string {
  if (rimDiameterMm === null || heightMm === null) return "dimensions unavailable";
  return `Ø ${rimDiameterMm.toFixed(1)} × ${heightMm.toFixed(1)} mm`;
}

export interface VariantShelves {
  readonly current: readonly VariantCard[];
  /** Behind the labelled fold — visible, never hidden (the catalog's own posture). */
  readonly superseded: readonly VariantCard[];
}

export function variantShelves(detail: CaseSessionDetail): VariantShelves {
  const effective = detail.system.effective_model;
  const group = declarableGroups(detail).find((g) => g.model === effective);
  const cards = (group?.variants ?? []).flatMap((row): VariantCard[] => {
    const id = row["id"];
    if (typeof id !== "string") return []; // no id = not declarable; drop, not lie
    const label = row["label"];
    const flags = Array.isArray(row["flags"]) ? row["flags"] : [];
    const dia = row["rim_diameter_mm"];
    const height = row["height_mm"];
    return [
      {
        id,
        label: typeof label === "string" ? label : id,
        dims: dimsLabel(
          typeof dia === "number" ? dia : null,
          typeof height === "number" ? height : null,
        ),
        superseded: flags.includes("superseded"),
      },
    ];
  });
  return {
    current: cards.filter((c) => !c.superseded),
    superseded: cards.filter((c) => c.superseded),
  };
}

/** How many sites a system switch would visibly reset (their declarations drop). */
export function resetCount(detail: CaseSessionDetail): number {
  return detail.sites.filter((s) => s.declared_variant !== null).length;
}

/**
 * THE VISIBLE-RESET WORDS (AM-8: "switching is an explicit case-level act that
 * visibly resets all variants"): the confirmation names the target system AND the
 * count, so the operator confirms the actual consequence, not a vague "are you
 * sure". The reset itself is the BFF's — these are only its honest words.
 */
export function switchWords(model: string, count: number): string {
  const sites = count === 1 ? "1 declared site" : `${count} declared sites`;
  return (
    `Switching to ${model} resets ${sites} — a variant belongs to one system's ` +
    `catalog, so every declaration on this case starts over.`
  );
}

/** The queue's and the stage's shared active site: the clicked tooth when it still
 * exists (a re-detect can remove one), else the first site, else null. */
export function activeSiteFrom(
  sites: readonly SiteView[],
  activeTooth: number | null,
): SiteView | null {
  if (activeTooth !== null) {
    const hit = sites.find((s) => s.tooth === activeTooth);
    if (hit !== undefined) return hit;
  }
  return sites[0] ?? null;
}

/** The queue's declared-variant column: the id, or an honest dash. */
export function declaredLabel(site: SiteView): string {
  return site.declared_variant ?? "—";
}

// --- the three panes' rules (plan §7 slice 5b; reference semantics: the demo's -------
// --- VerifyStage, REBUILT against BFF shapes per the ledger rule) --------------------

/** Pane 1's mesh URL for a declared variant: the SERVED `mesh_url` on the effective
 * system's catalog row — this app never assembles a library path itself (the BFF's
 * membership rules own resolution). null = no variant, or the catalog carries none. */
export function variantMeshUrl(
  detail: CaseSessionDetail,
  variantId: string | null,
): string | null {
  if (variantId === null) return null;
  const group = declarableGroups(detail).find(
    (g) => g.model === detail.system.effective_model,
  );
  const row = (group?.variants ?? []).find((v) => v["id"] === variantId);
  const url = row?.["mesh_url"];
  return typeof url === "string" ? url : null;
}

/**
 * THE PREVIEW'S IDENTITY — one string naming exactly what a preview would be computed
 * FROM (case, tooth, system, variant, the three case-level choices). null = the
 * session cannot preview yet (nothing declared, or choices incomplete), which is also
 * the auto-fire's off switch. Keyed on server FACTS only (the demo's previewKey
 * lesson: an effect that re-derives its trigger from render state re-fires forever;
 * one that compares a stable key fires once per distinct preview).
 */
export function previewKeyFor(
  detail: CaseSessionDetail,
  tooth: number | null,
): string | null {
  if (tooth === null) return null;
  const site = detail.sites.find((s) => s.tooth === tooth);
  if (site === undefined || site.declared_variant === null) return null;
  if (!detail.choices.complete) return null;
  if (detail.system.effective_model === null) return null;
  return [
    detail.case.id,
    tooth,
    detail.system.effective_model,
    site.declared_variant,
    detail.choices.construction_path,
    detail.choices.jaw,
    detail.choices.gingival_offset_mm,
  ].join("|");
}

/**
 * THE AUTO-FIRE DECISION (the panes' analogue of Intake's shouldAutoDetect): fire
 * exactly when a preview is possible (`key` non-null) and the site's slot does not
 * already answer for THIS key — a slot holding another key is a stale part/choices
 * combination, a slot holding this key (computing, ready OR error) is fresh. An
 * errored slot deliberately does NOT re-fire: the retry is the operator's explicit
 * act, not a render loop's.
 */
export function shouldAutoPreview(args: {
  readonly key: string | null;
  readonly slotKey: string | null;
}): boolean {
  return args.key !== null && args.key !== args.slotKey;
}

/** The payload's number[][] wire mesh, flattened for the viewer package's typed-array
 * geometry (VerifyLayerGeometry) — pure so the conversion is testable off-WebGL. */
export function positionsFrom(points: readonly (readonly number[])[]): Float32Array {
  const out = new Float32Array(points.length * 3);
  points.forEach((p, i) => {
    out[i * 3] = p[0] ?? 0;
    out[i * 3 + 1] = p[1] ?? 0;
    out[i * 3 + 2] = p[2] ?? 0;
  });
  return out;
}

export function indicesFrom(faces: readonly (readonly number[])[]): Uint32Array {
  const out = new Uint32Array(faces.length * 3);
  faces.forEach((f, i) => {
    out[i * 3] = f[0] ?? 0;
    out[i * 3 + 1] = f[1] ?? 0;
    out[i * 3 + 2] = f[2] ?? 0;
  });
  return out;
}

/** The preview fetch's lifecycle as the union pane sees it — "idle" covers both "not
 * fired yet" and "cannot fire yet" (the notice words distinguish them from facts). */
export type PreviewPhase = "idle" | "computing" | "ready" | "error";

export interface PaneNoticeInputs {
  readonly site: SiteView | null;
  readonly choicesComplete: boolean;
  readonly partMeshKnown: boolean;
  readonly partError: string | null;
  readonly scanError: string | null;
  /** true once the crop ran and found nothing within the region radius. */
  readonly scanEmpty: boolean;
  readonly previewPhase: PreviewPhase;
  readonly previewError: string | null;
}

export interface PaneNotices {
  readonly part: string | null;
  readonly scan: string | null;
  readonly union: string | null;
}

/**
 * THE HONEST WORDS over an empty pane (verify-UI doctrine: the panes are the product,
 * so a pane with nothing to show states WHY — never a blank canvas). Order matters:
 * the first true reason is the actionable one. A computing preview is NOT a notice —
 * it is the pane's busy state, which names the work instead.
 */
export function paneNotices(inputs: PaneNoticeInputs): PaneNotices {
  const {
    site,
    choicesComplete,
    partMeshKnown,
    partError,
    scanError,
    scanEmpty,
    previewPhase,
    previewError,
  } = inputs;
  const noSite = site === null ? "No site selected — pick a site in the queue." : null;
  const undeclared =
    site !== null && site.declared_variant === null
      ? "Declare this site's cap variant — the panes show the declared part."
      : null;

  const part = (() => {
    if (noSite) return noSite;
    if (undeclared) return undeclared;
    if (partError) return partError;
    if (!partMeshKnown) return "The catalog carries no mesh for this variant.";
    return null;
  })();

  const scan = (() => {
    if (scanError) return scanError;
    if (noSite) return noSite;
    if (site !== null && (site.center === null || site.center.length !== 3)) {
      return "This site has no centre to frame — detection placed none.";
    }
    if (scanEmpty) return "No scan surface near this site's centre.";
    return null;
  })();

  const union = (() => {
    if (noSite) return noSite;
    if (undeclared) return undeclared;
    if (!choicesComplete) {
      return (
        "Complete the case-level choices at Intake (construction part, jaw, " +
        "relief) — the preview seats the cap with them."
      );
    }
    if (previewPhase === "error") {
      return previewError ?? "The alignment preview failed.";
    }
    if (previewPhase === "idle") {
      return "The preview has not run for this declaration yet.";
    }
    return null; // computing = busy state; ready = the colouring itself
  })();

  return { part, scan, union };
}

export interface ReviewTickState {
  readonly enabled: boolean;
  readonly ticked: boolean;
  /** Present exactly when disabled — the honest reason beside the inert control. */
  readonly reason: string | null;
}

/**
 * THE REVIEW TICK'S TRUTH (AM-8: "reviewed over panels, not a checkbox"): enabled
 * only when the site stands on a preview — previewed (tick = attest) or ready
 * (untick = withdraw). Anywhere else the control is inert WITH its reason; the BFF
 * refuses regardless (the machine's review_ready), this only keeps the surface from
 * offering an act the server would refuse.
 */
export function reviewTick(site: SiteView | null): ReviewTickState {
  if (site === null) {
    return { enabled: false, ticked: false, reason: "No site selected." };
  }
  if (site.status === "previewed") return { enabled: true, ticked: false, reason: null };
  if (site.status === "ready") return { enabled: true, ticked: true, reason: null };
  return {
    enabled: false,
    ticked: false,
    reason: "The tick attests the live panes — preview this site first.",
  };
}
