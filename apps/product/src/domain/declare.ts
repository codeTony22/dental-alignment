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
