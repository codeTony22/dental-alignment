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
