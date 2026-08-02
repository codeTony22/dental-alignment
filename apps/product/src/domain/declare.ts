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
import type {
  ApiResult,
  CaseSessionDetail,
  PreviewPose,
  SitePreviewPayload,
  SiteView,
} from "../api/client";

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
  /**
   * The part DETECTION proposed for the site being declared — the BFF's
   * `SiteView.suggested_variant`, which is the case record's own curated variant
   * (bff/resources/case_sessions.py:491), never a comparison this module makes.
   * It is a per-SITE fact, so the same shelf marks a different card as the
   * operator moves down the queue.
   */
  readonly suggested: boolean;
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

/**
 * The active system's cards, for ONE site.
 *
 * `site` is optional only so a caller with no active site (an empty queue) still gets
 * a shelf; passing it is what lets the shelf mark the DETECTOR'S PROPOSAL (gap
 * `variant-suggested-badge`, design flow.dc.html:374-377 — the "sugg." pill). The
 * proposal is shown until the operator declares and not one render longer: once
 * `declared_variant` is set, their act is the answer and a second highlighted card
 * would only ask them to re-litigate a decision they already made. This is the same
 * attribution rule the SYSTEM card's "suggested" tag follows — a server fact, worn
 * only while the server is still the one supplying the value.
 */
export function variantShelves(
  detail: CaseSessionDetail,
  site: SiteView | null = null,
): VariantShelves {
  const effective = detail.system.effective_model;
  const group = declarableGroups(detail).find((g) => g.model === effective);
  const proposed =
    site !== null && site.declared_variant === null ? site.suggested_variant : null;
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
        suggested: proposed !== null && id === proposed,
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

/**
 * HOW FAR THROUGH THE DECLARATION THE OPERATOR IS (gap `declare-queue-header`;
 * design flow.dc.html:1173-1175, `queueNote`). Adjust's queue has carried its counts
 * since slice 6 (domain/adjust.queueSummary) while Declare's went straight from title
 * to rows, so the one stage with a per-site obligation was the one that never said how
 * many were left.
 *
 * REVIEWED means `ready` and nothing else: the tick over the live panes is what sets
 * it (bff/status.review_ready), and it is the same fact flow.isComplete("declare")
 * reads — two places must not count "done" differently. A flagged or adjusted site is
 * deliberately NOT reviewed here: the run or a rework moved the pose out from under
 * the attestation, and the ladder draws its way back through `previewed`.
 *
 * The design's second clause ("authorize the run in the left rail") does not port —
 * this product fires the run itself once every site is ready (shouldAutoRun), so
 * telling the operator to go press something would name a control that does not exist.
 */
export function declareQueueSummary(sites: readonly SiteView[]): string {
  const total = sites.length;
  if (total === 0) return "No sites on this case yet — nothing to review.";
  const count = (status: string) => sites.filter((s) => s.status === status).length;
  const reviewed = count("ready");
  const plural = total === 1 ? "site" : "sites";
  const head = `${reviewed} of ${total} ${plural} reviewed`;
  if (reviewed === total) {
    return `${head} — every one confirmed over its panes.`;
  }
  /* THREE POPULATIONS, NOT ONE (design review 2026-07-31). Everything short of `ready`
     used to be folded into "still to confirm over the panes" — so a run that flagged
     one of three sites printed "1 still to confirm over the panes" over a row reading
     "Flagged by the run — deviation RMS 0.214 mm. Adjust reworks it.", and over a tick
     that refuses to be clicked. The operator was required to confirm all three sites
     before the run fired, so that sentence also implied work had been undone that had
     not. Each population gets the act that is actually open to it. */
  const flagged = count("flagged");
  const reworked = count("adjusted");
  const pending = total - reviewed - flagged - reworked;
  const clauses: string[] = [];
  if (pending > 0) clauses.push(`${pending} still to confirm over the panes`);
  if (flagged > 0) {
    clauses.push(`${flagged} flagged by the run — Adjust reworks ${flagged === 1 ? "it" : "them"}`);
  }
  if (reworked > 0) {
    clauses.push(
      `${reworked} reworked since the run — confirm ${reworked === 1 ? "it" : "them"} again in Adjust`,
    );
  }
  return `${head} — ${clauses.join(" · ")}.`;
}

/**
 * THE MEASURED FIGURE A QUEUE ROW MAY CARRY — the RUN's own `deviation_rms_mm`, read
 * off its verdict row verbatim (the same key deliver.py:353 reads; the worker rounds
 * it at auto_flow.py:2408). Nothing here computes a deviation, a tolerance comparison
 * or a verdict: those are server-derived, and a browser that re-derived them would be
 * a second, quieter source of truth.
 *
 * The three absences are three different sentences, on purpose. Pre-run there IS no
 * row, and the design's dash (`"—"`) reads as a measured zero to anyone scanning a
 * column of numbers — the very confusion this surface exists to prevent.
 */
function measuredWords(row: Record<string, unknown> | undefined): string {
  if (row === undefined) return "no run has measured this fit yet";
  const rms = row["deviation_rms_mm"];
  if (typeof rms !== "number") return "the run's row carries no deviation figure";
  return `deviation RMS ${rms.toFixed(3)} mm`;
}

/**
 * THE ROW'S STATE AS A SENTENCE (gap `queue-row-state-sentence`; design
 * flow.dc.html:1180-1187). The queue printed `site.status` — "previewed",
 * "review_ready", "adjusted" — wire vocabulary from bff/status.py that names a rung
 * on a ladder the operator never saw, and no row carried a number at all.
 *
 * Each sentence names the operator's NEXT ACT where there is one, and the run's own
 * measurement where there is one. The words map the ladder; they never re-decide it.
 *
 * `rows` is the current run's verdict rows (GET /{id}/run), empty before a run exists.
 */
export function siteStateSentence(
  site: SiteView,
  rows: ReadonlyArray<Record<string, unknown>> = [],
): string {
  const measured = measuredWords(rows.find((r) => r["tooth"] === site.tooth));
  switch (site.status) {
    case "detected":
      return "Awaiting your declaration — no cap variant chosen for this site yet.";
    case "declared":
      return "Variant declared — the panes have not previewed this seat yet.";
    case "previewed":
      return "Previewed — confirm it over the panes to release it to the run.";
    case "ready":
      return `Confirmed over the panes — ${measured}.`;
    case "flagged":
      // "flagged" is the RUN's verdict, landed server-side; restating it is not
      // deciding it. What this must never say is whether the number is acceptable.
      return `Flagged by the run — ${measured}. Adjust reworks it.`;
    case "adjusted":
      return `Reworked since the run — ${measured}; confirm it again over the panes.`;
    default:
      // a rung this app has not met yet is still a fact the operator must see
      return site.status;
  }
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
 * FROM (case, tooth, system, variant, the three EFFECTIVE case-level choices — the
 * values the BFF actually seats with since the 2026-07-27 automation ask, so a
 * fresh case with suggestions previews with no Intake visit, and pinning a
 * suggestion mints the SAME key instead of refiring identical physics). null = the
 * session cannot preview yet (nothing declared, or an effective value absent),
 * which is also the auto-fire's off switch. Keyed on server FACTS only (the demo's
 * previewKey lesson: an effect that re-derives its trigger from render state
 * re-fires forever; one that compares a stable key fires once per distinct
 * preview).
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
    detail.choices.effective_construction.value,
    detail.choices.effective_jaw.value,
    detail.choices.effective_relief.value,
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

// --- the preview firer: the panes' async guards, framework-free (5b review M1) -------

/** One site's preview slot: which key it answers for, and how far it got. The payload
 * lives in CLIENT memory only — the BFF stores facts, not meshes — so a reload
 * honestly re-asks (the auto-fire) rather than pretending to remember. */
export interface PreviewSlot {
  readonly key: string;
  readonly state: "computing" | "ready" | "error";
  readonly payload?: SitePreviewPayload;
  readonly error?: string;
}

export type PreviewSlots = Readonly<Record<number, PreviewSlot>>;

/** Claiming is SYNCHRONOUS: the slot takes the key before any response can exist,
 * so ownership is decided at fire time, never at settle time. */
export function claimSlot(
  prev: PreviewSlots,
  tooth: number,
  key: string,
): PreviewSlots {
  return { ...prev, [tooth]: { key, state: "computing" } };
}

/**
 * THE STALE-RESPONSE GUARD: a settling response writes its slot ONLY while the slot
 * still holds ITS key — a newer ask (a re-declaration, a choices change) re-claimed
 * the slot, and the older physics answering late must not overwrite the newer truth
 * (the demo's previewKey lesson, made a pure rule so it is testable off-React).
 */
export function settleSlot(
  prev: PreviewSlots,
  tooth: number,
  key: string,
  result: ApiResult<SitePreviewPayload>,
): PreviewSlots {
  const current = prev[tooth];
  if (current === undefined || current.key !== key) return prev; // a newer ask owns it
  if (result.kind === "ok") {
    return { ...prev, [tooth]: { key, state: "ready", payload: result.data } };
  }
  return { ...prev, [tooth]: { key, state: "error", error: result.detail } };
}

export type PostPreviewFn = (
  caseId: string,
  tooth: number,
) => Promise<ApiResult<SitePreviewPayload>>;

export interface PreviewFirer {
  /** The auto-fire path: POST unless this (tooth, key) already fired — THE
   * DOUBLE-POST GUARD, synchronous, because the slot state a React effect reads
   * lags a render behind (Intake's shouldAutoDetect lesson: a doubled effect run
   * must find the claim already recorded). Returns whether a POST was issued. */
  maybeFire(tooth: number, key: string): boolean;
  /** The operator's explicit retry: always fires, re-claiming the slot. */
  fire(tooth: number, key: string): void;
}

/**
 * The panes' preview wiring with its ASYNC GUARDS, framework-free so both are
 * testable without a renderer (5b review M1): `post` is injectable (the component
 * passes the real client fn; tests pass a controlled fake), `update` is
 * setState-shaped, `isLive` is the container's mounted ref, and `onSettled` fires
 * on success so the container can re-read the detail (the site moved
 * declared→previewed SERVER-side — trust direction, AM-4).
 */
export function createPreviewFirer(args: {
  readonly caseId: string;
  readonly post: PostPreviewFn;
  readonly update: (fn: (prev: PreviewSlots) => PreviewSlots) => void;
  readonly isLive?: () => boolean;
  readonly onSettled?: (result: ApiResult<SitePreviewPayload>) => void;
}): PreviewFirer {
  const fired: Record<number, string> = {};

  function fire(tooth: number, key: string): void {
    fired[tooth] = key;
    args.update((prev) => claimSlot(prev, tooth, key));
    void args.post(args.caseId, tooth).then((result) => {
      if (args.isLive !== undefined && !args.isLive()) return;
      args.update((prev) => settleSlot(prev, tooth, key, result));
      args.onSettled?.(result);
    });
  }

  return {
    fire,
    maybeFire(tooth: number, key: string): boolean {
      if (fired[tooth] === key) return false; // already in flight for THIS key
      fire(tooth, key);
      return true;
    },
  };
}

// --- the run's auto-fire (plan §7 slice 5c; §1.2 compute-early) ----------------------

/**
 * THE RUN'S IDENTITY — one string naming exactly what an authorized run would be
 * computed FROM (case, system, every site's declared variant, the three case-level
 * choices). null = the session cannot run yet OR a current run already exists:
 * choices incomplete, any site short of READY, or run_state past "none" all switch
 * the auto-fire off (a refused run deliberately does NOT re-fire — the retry is the
 * operator's explicit act, exactly like an errored preview slot). Keyed on server
 * FACTS only, like previewKeyFor: after a reset boundary clears the run pointer,
 * the changed declaration/choices yield a NEW key and the auto-fire re-arms.
 */
export function runKeyFor(detail: CaseSessionDetail): string | null {
  if (detail.session.run_state !== "none") return null;
  if (!detail.choices.complete) return null;
  if (detail.system.effective_model === null) return null;
  if (detail.sites.length === 0) return null;
  if (detail.sites.some((s) => s.status !== "ready")) return null;
  return [
    detail.case.id,
    detail.system.effective_model,
    ...detail.sites.map((s) => `${s.tooth}:${s.declared_variant}`),
    // the EFFECTIVE choices — the same document the run's authorized gate reads
    detail.choices.effective_construction.value,
    detail.choices.effective_jaw.value,
    detail.choices.effective_relief.value,
  ].join("|");
}

/** The run's auto-fire decision — the same shape as shouldAutoPreview: fire exactly
 * when a run is possible and this key has not fired (the fired key is the
 * container's ref, so a doubled effect run cannot double-POST a 30–60 s job). */
export function shouldAutoRun(args: {
  readonly key: string | null;
  readonly firedKey: string | null;
}): boolean {
  return args.key !== null && args.key !== args.firedKey;
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

// --- the panes' camera frames (the demo's top-of-cap directive, 2026-07-26, restored
// --- for the product 2026-07-27: the camera faces the top of the healing cap) --------

/** A pane camera frame — exactly the viewer package's VerifyViewer `frame` prop
 * shape, so the container passes it through whole (a dropped field here is the
 * bug the frames component test exists to keep dead). */
export interface PaneFrame {
  readonly center: readonly [number, number, number];
  readonly radiusMm: number;
  readonly viewDirection: readonly [number, number, number] | null;
  readonly up: readonly [number, number, number] | null;
}

/** The wire carries number[]; a malformed triple must never aim a camera. */
const tripleOf = (
  v: readonly number[] | null | undefined,
): readonly [number, number, number] | null =>
  v != null && v.length === 3 ? [v[0]!, v[1]!, v[2]!] : null;

/**
 * PANES 2/3's FRAME — the demo's exact semantics (VerifyStage.tsx 451-482, the
 * seatedFrame/occlusal story), restored as one pure rule:
 *
 *  - a preview payload's POSE frames down its EXACT seated axis with up = the
 *    pose's own x_axis (the 2026-07-26 lesson: verified 0.000°-0.054° against the
 *    packaged implant.json; x_axis is what makes the three panes comparable — a
 *    coded cutout reads at the same clock angle everywhere);
 *  - BEFORE a preview exists, the jaw's OCCLUSAL direction aims the camera — the
 *    honest proxy, named as one (6.2°-42.0° off the cap's real axis across the
 *    fleet); up stays null, because only the measured pose earns a roll;
 *  - with NEITHER, the frame still centres the site at its radius and leaves the
 *    direction null — the viewer's default angle, never a guess dressed as a
 *    measurement; and with no centre at all there is no frame (null).
 *
 * A pose whose axis triple is malformed falls back to the occlusal proxy AND
 * drops the up-roll with it — up belongs to the axis it rolls around.
 */
export function siteFrameFor(
  center: readonly number[] | null | undefined,
  pose: PreviewPose | null,
  occlusal: readonly number[] | null,
  radiusMm: number,
): PaneFrame | null {
  const c = tripleOf(center);
  if (c === null) return null;
  const axis = pose !== null ? tripleOf(pose.axis) : null;
  return {
    center: c,
    radiusMm,
    viewDirection: axis ?? tripleOf(occlusal),
    up: axis !== null ? tripleOf(pose!.x_axis) : null,
  };
}

/** What pane 1's frame is computed FROM — the viewer's computePartFrame result,
 * structurally (the fitted rim centre in canonical xy, the vertex centroid, the
 * part's own p97 radius). */
export interface PartFrameFit {
  readonly rimCentre: readonly [number, number];
  readonly centroid: readonly [number, number, number];
  readonly rmaxMm: number;
}

/**
 * PANE 1's FRAME: down the part's own FILE axis (+z) with up +x — the canonical
 * frame's reference direction, the same one the seated pose's x_axis is, so pane 1
 * and panes 2/3 agree where "zero degrees" sits. The target is the fitted rim
 * centre (canonical xy + centroid) through the part's mid-height, at the part's
 * OWN radius (a 6mm cap framed at the scan's 9mm region radius would sit in the
 * pane as a small disc). null in = null out: a mesh that does not read as a
 * revolute part falls back to the viewer's default framing rather than aiming the
 * camera off noise.
 */
export function partCameraFrame(fit: PartFrameFit | null): PaneFrame | null {
  if (fit === null) return null;
  return {
    center: [
      fit.rimCentre[0] + fit.centroid[0],
      fit.rimCentre[1] + fit.centroid[1],
      fit.centroid[2],
    ],
    radiusMm: fit.rmaxMm * 1.6,
    viewDirection: [0, 0, 1],
    up: [1, 0, 0],
  };
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
      // effective-incomplete (client 2026-07-27): suggestions and the standing
      // default normally cover the choices, so this only shows when a piece has
      // NO fallback (a case whose folder matched no construction part)
      return (
        "Complete the case-level choices at Intake (construction part, jaw, " +
        "relief) — no suggestion covers them all yet, and the preview seats " +
        "the cap with them."
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
  /* A SITE THE RUN HAS MEASURED IS NOT A SITE AWAITING A PREVIEW (design review
     2026-07-31). Both of these rungs got "preview this site first" — a statement that
     is false about a fit the run has already measured and printed a deviation for two
     lines above. The refusal itself stands: the panes HERE seat a fresh preview, while
     what a flagged or reworked site needs confirming over is the pose that shipped,
     which only Adjust's panes show. The BFF would accept `review_ready` from ADJUSTED
     (status.py:50) — this surface declines to offer it against the wrong evidence, and
     now says which evidence and where. */
  if (site.status === "flagged") {
    return {
      enabled: false,
      ticked: false,
      reason: "The run flagged this fit — Adjust reworks it, and the confirmation is taken there.",
    };
  }
  if (site.status === "adjusted") {
    return {
      enabled: false,
      ticked: false,
      reason:
        "This site was reworked after the run — confirm it in Adjust, over the panes " +
        "showing the fit that moved.",
    };
  }
  return {
    enabled: false,
    ticked: false,
    reason: "The tick attests the live panes — preview this site first.",
  };
}

/**
 * THE ATTESTATION'S SENTENCE (client 2026-07-27 #2: "The reviewed over the panes
 * check mark needs to be better confirmed"). A bare "Reviewed over the panes"
 * checkbox never said WHAT was being attested; this names it for THIS site — the
 * tooth, the declared cap, and that the panes on screen are the subject — in the
 * demo acknowledgment bar's own voice (VerifyDialog's REVIEW_DISCLAIMER: "I
 * acknowledge that the library part selected matches the corresponding scan data").
 *
 * Two sentences, because attesting and having-attested are different statements: the
 * first is what the act will mean, the second is what the record now says. Both name
 * the same three things, so withdrawing is as explicit as giving.
 */
export function attestationSentence(site: SiteView | null): string {
  if (site === null) return "No site selected — pick a site in the queue.";
  const cap =
    site.declared_variant !== null
      ? `the declared cap ${site.declared_variant}`
      : "no cap declared yet";
  // PLAIN WORDS (client, 2026-07-28: "What is withdraw attestation?"). "Attestation" is
  // the audit term, not the operator's — they confirmed a site, and they can undo it.
  if (site.status === "ready") {
    return (
      `You confirmed tooth ${site.tooth}: the panes showed its scan with ` +
      `${cap} seated on it, and they matched.`
    );
  }
  return (
    `Confirm that the panes above show tooth ${site.tooth}'s scan with ` +
    `${cap} seated on it, and that they match.`
  );
}

/** The attestation button's label — an act's weight, not a checkbox's. */
export function attestationAction(site: SiteView | null): string {
  return site !== null && site.status === "ready"
    ? "Undo this confirmation"
    : "Confirm this site";
}

/** One line of Declare's move-forward summary: a site and what its tick stands on. */
export interface AttestationLine {
  readonly tooth: number;
  readonly attested: boolean;
  /** The whole line, ready to render — facts only, never a verdict of our own. */
  readonly words: string;
}

/** The seat facts as one phrase, or the honest absence (a READY site whose facts
 * were cleared by a boundary is a state worth SEEING, never one to paper over). */
function seatWords(site: SiteView): string {
  if (site.seat_method === null && site.rim_agreement_mm === null) {
    return "no seat facts recorded";
  }
  const rim =
    site.rim_agreement_mm !== null
      ? `rim ${site.rim_agreement_mm.toFixed(2)} mm`
      : "rim not measured";
  return `${site.seat_method ?? "seat method not recorded"}, ${rim}`;
}

/**
 * THE SET, FACED AT THE MOMENT OF MOVING FORWARD (client 2026-07-27 #2: "maybe at
 * the time to move forward to the next step"). One line per site — tooth, declared
 * cap, and the seat facts that preview produced — so the operator confirms the whole
 * set before advancing rather than trusting a count of ticks.
 *
 * A site that is NOT attested is named as such instead (the blockedReason doctrine:
 * a surface that cannot advance says exactly which site is holding it, never a bare
 * "incomplete"). Facts only — every value here is the BFF's.
 */
export function attestationSummary(
  sites: readonly SiteView[],
): readonly AttestationLine[] {
  return sites.map((site) => {
    const cap = site.declared_variant ?? "no cap declared";
    if (site.status !== "ready") {
      return {
        tooth: site.tooth,
        attested: false,
        words: `Tooth ${site.tooth} · ${cap} · not attested (${site.status})`,
      };
    }
    return {
      tooth: site.tooth,
      attested: true,
      words: `Tooth ${site.tooth} · ${cap} · ${seatWords(site)}`,
    };
  });
}

/**
 * WHAT SKIPPING ACTUALLY COSTS, said truthfully against what Deliver does (client
 * 2026-07-27 #3: two options, and the skip must not pretend the flags evaporate).
 * With nothing flagged, skipping forfeits nothing. With flags, Deliver still refuses
 * to release one without its own row acknowledgment — so the sentence names the
 * count and the two honest ways through it.
 */
export function skipConsequenceWords(flaggedCount: number): string {
  if (flaggedCount === 0) {
    // One clause (client 2026-07-30: the footer must condense) — "no fits waiting to
    // be reworked" restated what the flag count already says.
    return "Nothing is flagged — adjusting is optional.";
  }
  const sites = `${flaggedCount} flagged site${flaggedCount === 1 ? "" : "s"}`;
  return (
    `${sites} stay${flaggedCount === 1 ? "s" : ""} exactly as the run left ` +
    `${flaggedCount === 1 ? "it" : "them"}. Deliver will not release a flagged ` +
    `site without its own acknowledgment on the row — acknowledge it there, or ` +
    `withhold it and leave the site open.`
  );
}

/**
 * A recorded instant, for humans (client 2026-07-30). The wire's
 * "2026-07-31T01:17:18.636748+00:00" was rendered verbatim into the fork's recorded
 * note — microseconds and all — which is machine text on an operator surface.
 *
 * Deliberately a SLICE of the ISO string, not a Date round trip: the store writes
 * UTC, and formatting through the browser's locale would show a different wall time
 * per machine while the evidence bundle carries the original — two clocks for one
 * act. Minute precision, labelled UTC, deterministic in tests.
 */
export function recordedAtWords(iso: string): string {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]} UTC` : iso;
}

// --- the workspace toolbar (gaps `workspace-toolbar-site-chip`, ----------------------
// --- `alignment-metrics-strip`, `named-view-presets`; design flow.dc.html 206-266) ---
//
// WHY THESE RULES ARE HERE AND NOT IN THE COMPONENTS: Declare and Adjust show one
// operator the same three panes of the same site, and the client made those panes
// dominate the stage (2026-07-27, styles.css --split). What that cost was the site's
// own identity — the tooth number lives in the work column's headings and the queue
// rows, and all of those SCROLL. So both stages grow one toolbar, and it must say the
// same thing in both: one rule module, two callers.

/** The identity chip's two halves — WHICH site, under WHICH implant system. */
export interface SiteIdentity {
  readonly tooth: string;
  readonly system: string;
}

/** Both halves say what is missing rather than going blank: an empty slot beside a
 * live 3D pane reads as "nothing to say here", which is the opposite of the truth. */
export function siteIdentity(
  tooth: number | null,
  systemModel: string | null,
): SiteIdentity {
  return {
    tooth: tooth === null ? "No site selected" : `Tooth ${tooth}`,
    system: systemModel ?? "no system declared",
  };
}

/** One cell of the ALIGNMENT strip: a stable id for the markup, the operator's label,
 * and the value already formatted (formatting is presentation; the NUMBER is the
 * server's). */
export interface WorkspaceStat {
  readonly id: string;
  readonly label: string;
  readonly value: string;
}

/** The absence, once — and deliberately a dash rather than a zero or a blank: the
 * strip is a row of numbers, and a blank cell in a row of numbers reads as zero. */
const NO_FIGURE = "—";

/** THE OTHER ABSENCE, and it is a different one (design review 2026-07-31). A dash
 *  belongs where a run row EXISTS and carries no figure; before any run there is no
 *  measurement to be absent from, and a dash in a deviation column reads as a measured
 *  zero — the same reason `measuredWords` refuses one on the queue rows. */
const NO_RUN = "no run yet";

/**
 * WHAT A PREVIEW HAS ALREADY PUBLISHED about this site, held in the browser between
 * the pane that renders it and the strip above it.
 *
 * Every field is the SERVER's: `rms_mm`/`p90_mm` off the preview payload's own
 * `stats` block (the very numbers the union pane's folded legend prints), and
 * `poseAvailable` is whether that payload carried a seated pose at all — which is what
 * decides whether the off-axis viewpoints have a clock reference to rotate about.
 * Nothing here is derived in the browser.
 */
export interface PreviewFigures {
  readonly poseAvailable: boolean;
  readonly rmsMm: number | null;
  readonly p90Mm: number | null;
  /** The payload's own `stats.source` — named on the label so a preview figure is
   *  never mistaken for the run's. */
  readonly source: string;
}

function blockOf(row: Record<string, unknown> | undefined, key: string) {
  const block = row?.[key];
  return typeof block === "object" && block !== null
    ? (block as Record<string, unknown>)
    : undefined;
}

/**
 * THE ALWAYS-VISIBLE ALIGNMENT READOUT (gap `alignment-metrics-strip`; design's
 * selStats, flow.dc.html:1356-1363).
 *
 * Every one of these facts already existed and every one was somewhere else: the
 * deviation only inside the union pane's FOLDED legend, the clocking residual only
 * inside Adjust's rotation TAB, the pairs only inside the fit-by-points TAB. An
 * operator on the mark-trench tab could not see how many pairs were placed; one on
 * the rotation tab could not see the deviation. This re-sites them; it fetches
 * nothing new and derives nothing new.
 *
 * WHAT DOES NOT PORT: the design computes MAX DEV from its own client-side
 * `deviation()` and colours it against a client-side `tolerance`. This product
 * derives deviations, tolerances and verdicts SERVER-side, so the strip carries the
 * two figures the run actually published — `deviation_rms_mm` and `deviation_p90_mm`
 * — under the labels they truly are. Naming p90 "MAX DEV" would be a client-side
 * claim about a number the server never made.
 *
 * `rows` is the current run's verdict rows (GET /{id}/run), read defensively: they
 * arrive wire-untyped, exactly like the catalog's.
 */
export function alignmentStats(
  rows: ReadonlyArray<Record<string, unknown>>,
  tooth: number | null,
  declaredVariant: string | null,
  preview: PreviewFigures | null = null,
): readonly WorkspaceStat[] {
  const row = tooth === null ? undefined : rows.find((r) => r["tooth"] === tooth);
  /* NO ROWS AT ALL = NO RUN. On Declare the container fetches them only once
     `run_state === "done"`, so pre-run this list is empty while the union pane below is
     already printing "Deviation over the footprint: RMS 0.086 mm · p90 0.142 mm" for
     the same site. The strip stated that no figure existed for figures that were on the
     screen. A row that exists and lacks a number keeps its dash: that is a different
     fact, and the run made it. */
  const noRun = rows.length === 0;
  const absent = noRun ? NO_RUN : NO_FIGURE;
  const clocking = blockOf(row, "clocking");
  const shift = clocking?.["notch_shift_deg"];
  /* THE SAME HONESTY THE PAIRS PILL ALREADY CARRIES (§10-H's "STILL OPEN" line,
     closed 2026-08-02). `rotation_unverified` is the SERVER's own boolean — set when
     the automatic reader's evidence (correlation, prominence or occupancy) failed its
     gate, or a confirm re-read itself failed — and no tool ever clears it: an applied
     tool's re-read returns only the three instrument numbers, never this flag, so a
     bare "+21.7°" here was indistinguishable from a reading the run actually trusted.
     `unverifiedClockNotice` (domain/adjust.ts) reads the identical block for Adjust's
     workspace notice; this is the same fact, on the number it qualifies. */
  const rotationUnverified = clocking?.["rotation_unverified"] === true;
  // The MEASURED notch residual at the shipped pose (adjust._fold_outcome writes it),
  // not the operator's cumulative nudge — they answer different questions, and this
  // strip asks "is it clocked right?".
  const rotation =
    typeof shift === "number"
      ? `${shift > 0 ? "+" : ""}${shift.toFixed(1)}°${rotationUnverified ? " · unverified" : ""}`
      : absent;
  const correspondence = blockOf(row, "correspondence");
  const pairs = correspondence?.["pairs"];
  const maxPairs = correspondence?.["max_pairs"];
  // "3 / 8" only where the SERVER supplied the cap. A hard-coded 8 here would be a
  // second copy of a bound the wire already carries (deliver.AssuranceCorrespondence),
  // and "0 / 8" on a site nobody has fit by points would be an invented fact.
  /* AND WHETHER THAT FIT HAD ANYTHING TO CHECK IT (defect cap6020-neodent-gm,
     2026-08-01). "1 / 8" renders exactly like "3 / 8" — a fit that happened — and hides
     the one way they differ: a single observation is exactly determined, its residual
     is zero by construction, and the fit reports no agreement number at all. The word
     is the SERVER's `cross_checked` (bff/resources/deliver._correspondence_view), never
     a `pairs === 1` test here: the count of PAIRS cannot answer it — one radial span is
     two observations and IS cross-checked. A server that says nothing gets no word. */
  const counted =
    typeof pairs !== "number"
      ? absent
      : typeof maxPairs === "number"
        ? `${pairs} / ${maxPairs}`
        : `${pairs}`;
  const pairsWords =
    typeof pairs === "number" && correspondence?.["cross_checked"] === false
      ? `${counted} · unchecked`
      : counted;
  /* THE SOURCE IS PART OF THE FIGURE. Two acts measure this site's deviation — the run,
     and the pre-run preview seat — on the same instrument at different moments, and a
     cell that showed one under the other's name would be the quietest possible lie. So
     the label carries whose number it is, and the preview's is used ONLY where the run
     has published none. Clocking and pairs have no preview analogue: the preview seats
     a cap, it does not read a notch residual or place a correspondence. */
  const usePreview = row === undefined && preview !== null;
  /* One short word, not the payload's provenance sentence. The strip inlined
     `preview.source` verbatim — "area-uniform surface samples (the acceptance
     difference map)" — which made the toolbar read as nested parentheses (client
     screenshot, 2026-08-01). Run-vs-preview is the distinction the operator needs
     here; the instrument's full name stays on the union pane's stats line, which is
     the surface that owns it. */
  const devSource = usePreview ? "preview" : "run";
  const devRms = usePreview ? mmWordsOr(preview.rmsMm, absent) : mmWordsOr(row?.["deviation_rms_mm"], absent);
  const devP90 = usePreview ? mmWordsOr(preview.p90Mm, absent) : mmWordsOr(row?.["deviation_p90_mm"], absent);
  const devLabel = (key: string) =>
    devRms === NO_RUN && devP90 === NO_RUN ? key : `${key} (${devSource})`;
  return [
    { id: "variant", label: "VARIANT", value: declaredVariant ?? NO_FIGURE },
    { id: "dev-rms", label: devLabel("DEV RMS"), value: devRms },
    { id: "dev-p90", label: devLabel("DEV P90"), value: devP90 },
    { id: "rotation", label: "ROTATION", value: rotation },
    { id: "pairs", label: "PAIRS", value: pairsWords },
  ];
}

/** mmWords with the caller's own word for "there is no figure here". */
function mmWordsOr(value: unknown, absent: string): string {
  return typeof value === "number" ? `${value.toFixed(3)} mm` : absent;
}

/**
 * The three named viewpoints (design viewTabs, flow.dc.html:1224-1226).
 *
 * THE DESIGN'S ANATOMICAL NAMES DO NOT PORT (design review 2026-07-31). It calls the
 * off-axis two "buccal" and "mesial", and this app shipped them that way — but they are
 * built from the seated pose's `x_axis`, which the worker publishes only "because it is
 * what makes the three panes COMPARABLE" (application/preview.py:119-124): a shared
 * CLOCK reference, per site, with no anatomical meaning and no fixed relation to the
 * arch. Nothing maps it to buccal/lingual or mesial/distal, so on tooth 29 "buccal"
 * could be looking at the lingual wall and on tooth 13 at the distal one — and an
 * operator asked "does the cap sit proud on the buccal?" would judge the wrong wall.
 *
 * It is the same claim this app already refused for the occlusal proxy ("an
 * anatomically-named view built on it would be a guessed angle"), and the buttons' own
 * tooltips already told the truth the labels contradicted. The viewer does compute a
 * real anatomical frame (computeAnatomyFrame().anterior, "toward the incisors"), so an
 * honestly-named buccal view is buildable — from that basis plus the site's quadrant,
 * which is a measurement this surface has not made. Until it does, the names say what
 * the geometry is: two sides of one clock reference.
 */
export type ViewPresetId = "occlusal" | "side-a" | "side-b";

/* THE LABELS ARE ABBREVIATED (comp, read directly 2026-08-02: its own strip reads
   "occ · buc · mes"). Ours keep the honest names — "side A/B" rather than the comp's
   anatomical buccal/mesial, because those need a measured roll and naming them where
   there is none is the lie this app already refused — so only the visible text
   shortens. The full sentence stays in `title`, which is the only place the operator
   learns what the direction means. */
export const VIEW_PRESETS: readonly {
  readonly id: ViewPresetId;
  readonly label: string;
  /** What the direction MEANS — the only place the operator learns that "side A" is
   *  measured off this site's own clock reference and not off the arch. */
  readonly title: string;
}[] = [
  {
    id: "occlusal",
    label: "occ",
    title: "Straight down the seated axis — the top of the cap, each pane's own framing.",
  },
  {
    id: "side-a",
    label: "A",
    title:
      "Side on, a quarter turn off this site's clock reference — the cap's axis stands " +
      "up on screen. The clock reference is the seated pose's own, shared by all three " +
      "panes; it is not an arch direction.",
  },
  {
    id: "side-b",
    label: "B",
    title:
      "Side on, down this site's clock reference itself — the cap's axis stands up on " +
      "screen. A quarter turn from side A, and like it not an arch direction.",
  },
];

const norm = (
  v: readonly [number, number, number],
): readonly [number, number, number] | null => {
  const len = Math.hypot(v[0], v[1], v[2]);
  // 1e-9 is "the wire sent us noise", not a tolerance on anything physical
  return len < 1e-9 ? null : [v[0] / len, v[1] / len, v[2] / len];
};

const cross = (
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): readonly [number, number, number] => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

/**
 * A NAMED VIEWPOINT, IN THE PANE'S OWN BASIS (gap `named-view-presets`).
 *
 * The panes had per-pane ⌖ home and free orbit and nothing else, so "look at this
 * from the buccal" was a freehand drag repeated three times — and the memory note
 * `verify-ui-directives` is explicit that the panes ARE the product and rotation IS a
 * verdict, which makes a viewpoint the operator can RETURN to worth having.
 *
 * The rule is one rotation, applied to whatever frame the pane already computed, so
 * each pane keeps its own centre and its own radius (the library part is framed in
 * its file frame at its own p97 radius; panes 2/3 at the site's centre). The basis is
 * the frame's own: z' = the direction it looks down (the seated axis, or the part's
 * +z), x' = its up-vector (the pose's x_axis, or the part's +x — the SAME reference,
 * which is exactly why a coded cutout reads at one clock angle in all three panes).
 * y' = z' × x' completes it.
 *
 *   occlusal — z' (the framing the pane already has, returned unchanged)
 *   side A   — look down y', axis up
 *   side B   — look down x', axis up
 *
 * NULL WHERE THE ROLL IS NOT MEASURED. Before a preview exists panes 2/3 frame down
 * the jaw's occlusal PROXY with `up: null` (siteFrameFor) — the proxy sat 6.2°-42.0°
 * off the real axis across the fleet, and it carries no clock reference at all. An
 * off-axis view built on it would be a made-up angle, so there is none: the caller
 * offers occlusal and says the rest need the seated pose.
 */
export function presetFrame(
  base: PaneFrame | null,
  preset: ViewPresetId,
): PaneFrame | null {
  if (base === null) return null;
  if (preset === "occlusal") return base;
  const axis = base.viewDirection === null ? null : norm(base.viewDirection);
  const clock = base.up === null ? null : norm(base.up);
  if (axis === null || clock === null) return null;
  const third = norm(cross(axis, clock));
  if (third === null) return null; // the roll is parallel to the axis: no basis
  return {
    center: base.center,
    radiusMm: base.radiusMm,
    viewDirection: preset === "side-a" ? third : clock,
    up: axis,
  };
}

/** What the pane foot may call the direction a preset actually framed on. null for
 *  occlusal, which IS the pane's own framing — the caller keeps naming its own axis
 *  ("the seated pose axis", "the occlusal proxy", "the part's own axis"). */
export function presetViewLabel(preset: ViewPresetId): string | null {
  if (preset === "occlusal") return null;
  return preset === "side-a" ? "the side A viewpoint" : "the side B viewpoint";
}

/** A frame, and the words for what that frame is pointed down. */
export interface PresetFraming {
  readonly frame: PaneFrame | null;
  /** null = the preset did not move this pane, so its own axis label still stands. */
  readonly presetLabel: string | null;
}

/**
 * THE FRAME AND ITS NAME, TOGETHER (design review 2026-07-31).
 *
 * The pane foot is the one sentence on screen claiming to be a LIVE measurement of
 * orientation, and it was reading the camera against the preset-ROTATED direction while
 * printing the label of the UN-rotated one: under an off-axis preset all three panes
 * said "down the seated pose axis" while sitting exactly 90° off it, and said "90° off
 * the seated pose axis" once the operator orbited back onto it. The band exists
 * precisely because the design's static "OCCLUSAL" caption "starts lying on the first
 * drag"; under a preset it lied with no drag at all.
 *
 * A reference and a label may never come from different frames, so they are produced
 * here in one call. `?? base` on a preset that cannot apply is deliberate — the pane
 * keeps its own framing rather than dropping to nothing — and it yields a null label
 * for exactly the same reason: the pane is still on the axis it was already naming.
 */
export function presetFraming(
  base: PaneFrame | null,
  preset: ViewPresetId,
): PresetFraming {
  const rotated = presetFrame(base, preset);
  if (rotated === null) return { frame: base, presetLabel: null };
  return {
    frame: rotated,
    presetLabel: rotated === base ? null : presetViewLabel(preset),
  };
}
