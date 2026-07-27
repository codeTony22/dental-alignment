import { useEffect, useMemo, useRef, useState } from "react";
import { cachedMeshUrl } from "../api/meshCache";
import type { Vec3 } from "../domain/types";
import { PALETTE } from "../viewer/palette";
import { computePartFrame } from "../viewer/partFrame";
import { loadStlPositions } from "../viewer/verifyScene";
import { VerifyViewer, type VerifyViewerLayer } from "../viewer/VerifyViewer";
import { partPreviewLabel } from "./PartPreviewChip";

/** The pane's width floor: below this the variant cards' Ø×height caption and the 3D itself
 *  stop being readable, so the pane auto-collapses instead of rendering a sliver. */
export const COMPARE_PANE_MIN_WIDTH_PX = 280;

/** What the MAIN stage must keep beside an open pane — the scan is the primary subject
 *  (client, 2026-07-26: the docked pane never hijacks the main stage). */
export const COMPARE_MAIN_STAGE_MIN_WIDTH_PX = 300;

/** The split's own flex gap (`.stage-split { gap: 10px }` in styles.css) — part of the floor
 *  arithmetic. Review 2026-07-26: omitting it collapsed nothing in the 580–589px window while
 *  the main stage got only 290–299px, under its declared floor. */
export const COMPARE_SPLIT_GAP_PX = 10;

/** True when the split container cannot give the pane its floor AND leave the scan a usable
 *  main stage — the pane then auto-collapses to its strip. Pure, so the floor is pinned by test
 *  rather than discovered in a browser. The container's width pays for pane + gap + scan. */
export function compareAutoCollapsed(splitWidthPx: number): boolean {
  return (
    splitWidthPx <
    COMPARE_PANE_MIN_WIDTH_PX + COMPARE_SPLIT_GAP_PX + COMPARE_MAIN_STAGE_MIN_WIDTH_PX
  );
}

/** What the pane needs to know about the part it is asked to show — the active site's declared
 *  variant, resolved from the catalog (findVariantEntry) by App. */
export interface CompareVariantInfo {
  readonly variant: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly meshUrl: string;
}

export type CompareLoad =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "ready" }
  | { readonly kind: "error"; readonly message: string };

/**
 * WHY the pane has no part to show. One sentence per cause — review 2026-07-26 caught the
 * pane asking "Choose a cap variant" while the variant WAS declared (catalog still loading /
 * endpoint down) and while no site existed to receive a declaration at all; the true blocker
 * must be the one named.
 */
export type CompareEmptyReason =
  | "no-sites"
  | "no-declaration"
  | "catalog-pending"
  | "catalog-unavailable"
  | "not-in-catalog";

/** The cause of an unresolved part, from what App already knows. Only consulted when the
 *  catalog lookup (findVariantEntry) came back empty, so catalog "ready" here means the
 *  declared id genuinely is not in the catalog — not a race. */
export function compareEmptyReason(args: {
  readonly sitesMarked: boolean;
  readonly declared: boolean;
  readonly catalog: "idle" | "loading" | "ready" | "unavailable" | "error";
}): CompareEmptyReason {
  if (!args.sitesMarked) return "no-sites";
  if (!args.declared) return "no-declaration";
  if (args.catalog === "ready") return "not-in-catalog";
  if (args.catalog === "unavailable" || args.catalog === "error") return "catalog-unavailable";
  return "catalog-pending"; // idle | loading — the fetch simply has not resolved yet
}

/** The honest sentence for each empty cause — same vocabulary as SelectionColumn's own hints
 *  ("mark a cap in step 2") so the pane and the panel never disagree about what to do next. */
const EMPTY_SENTENCES: Record<CompareEmptyReason, string> = {
  "no-sites": "No marked sites on this case yet — mark a cap in step 2, then declare a variant to compare.",
  "no-declaration": "Choose a cap variant to compare — the pane follows the active site's declaration.",
  "catalog-pending": "Variant declared — waiting for the cap catalog to load before the part can be shown.",
  "catalog-unavailable": "Variant declared, but the cap catalog is unavailable — the part cannot be shown.",
  "not-in-catalog": "The declared variant is not in the cap catalog — declare one of the catalog's variants to compare.",
};

/**
 * The pane's one honest sentence, or null when the 3D itself is the answer. Precedence is
 * deliberate: the empty reason outranks any stale load error — an error about a part the
 * operator has since un-declared must never keep the empty state from stating the real
 * blocker.
 */
export function comparePaneNotice(empty: CompareEmptyReason | null, load: CompareLoad): string | null {
  if (empty !== null) return EMPTY_SENTENCES[empty];
  if (load.kind === "error") return load.message;
  return null;
}

export interface ComparePartPaneProps {
  /** The ACTIVE site's declared variant, or null when the catalog resolved nothing. */
  readonly variant: CompareVariantInfo | null;
  /** WHY `variant` is null — consulted only then; App computes it via compareEmptyReason. */
  readonly emptyReason: CompareEmptyReason;
  readonly tooth: number | null;
  readonly collapsed: boolean;
  readonly onToggleCollapsed: () => void;
}

/**
 * THE DOCKED PART PANE — scan | part, SIDE BY SIDE (client, 2026-07-26: "if we're doing this
 * selection, I think we should still see side by side the scan and the model that we're
 * selecting so we can compare").
 *
 * It replaces the step-2 rows' "view part" button, which SWAPPED the part into the main stage —
 * the exact opposite of comparing. The main stage keeps the scan and its site routing; this
 * pane shows the active site's declared variant beside it, reusing the verify dialog's own
 * pieces so a part reads identically in both places: VerifyViewer over loadStlPositions (bytes
 * through the session blob cache), framed by computePartFrame exactly as the dialog's pane 1
 * frames — top of the cap, viewDirection [0,0,1], up [1,0,0] (the canonical +x, the same "zero
 * degrees" the seated pose's x-axis means). A mesh whose frame is refused falls back to
 * frame-all rather than aiming the camera off noise.
 *
 * BUDGET: one extra live WebGL context while comparing, ZERO while collapsed — the VerifyViewer
 * (and its VerifyScene) unmounts with the pane body, and VerifyViewer disposes its scene on
 * unmount, so collapsing or leaving Mark & declare always releases the context.
 */
export function ComparePartPane({ variant, emptyReason, tooth, collapsed, onToggleCollapsed }: ComparePartPaneProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [autoCollapsed, setAutoCollapsed] = useState(false);
  const [positions, setPositions] = useState<Float32Array | null>(null);
  const [load, setLoad] = useState<CompareLoad>({ kind: "idle" });

  // The auto-collapse floor, measured on the SPLIT container (the pane's parent): the pane must
  // never squeeze the scan out of its own stage, and never render a sliver of 3D.
  useEffect(() => {
    const parent = rootRef.current?.parentElement;
    if (!parent) return undefined;
    const apply = () => setAutoCollapsed(compareAutoCollapsed(parent.clientWidth));
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  const isCollapsed = collapsed || autoCollapsed;
  const meshUrl = variant?.meshUrl ?? null;

  // The part's mesh: one fetch per part per session (cachedMeshUrl), skipped entirely while
  // collapsed — a closed pane must cost nothing, and reopening hits the cache.
  useEffect(() => {
    if (meshUrl === null || isCollapsed) {
      setPositions(null);
      setLoad({ kind: "idle" });
      return undefined;
    }
    let cancelled = false;
    setPositions(null);
    setLoad({ kind: "loading" });
    cachedMeshUrl(meshUrl)
      .then((url) => loadStlPositions(url))
      .then((loaded) => {
        if (cancelled) return;
        setPositions(loaded);
        setLoad({ kind: "ready" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoad({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load the library part.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [meshUrl, isCollapsed]);

  /** Top-of-cap framing — the SAME code path as VerifyStage's pane 1 (copied, not reinvented):
   *  rim centre back in mesh coordinates, the part's own radius, camera down the file's +z with
   *  the canonical +x up. */
  const frame = useMemo(() => {
    if (positions === null) return null;
    const pf = computePartFrame(positions);
    if (!pf) return null;
    const center: Vec3 = [
      pf.rimCentre[0] + pf.centroid[0],
      pf.rimCentre[1] + pf.centroid[1],
      pf.centroid[2],
    ];
    return {
      center,
      radiusMm: pf.rmaxMm * 1.6,
      viewDirection: [0, 0, 1] as Vec3,
      up: [1, 0, 0] as Vec3,
    };
  }, [positions]);

  const layers: VerifyViewerLayer[] = useMemo(
    () => [
      {
        id: "part",
        geometry: positions ? { positions, color: PALETTE.cap } : null,
        visible: true,
        opacity: 1,
      },
    ],
    [positions],
  );

  if (isCollapsed) {
    return (
      <div ref={rootRef} className="compare-pane compare-pane--collapsed">
        <button
          type="button"
          className="compare-pane__toggle"
          aria-expanded="false"
          disabled={autoCollapsed}
          onClick={onToggleCollapsed}
          title={
            autoCollapsed
              ? "Not enough width to show the part beside the scan — widen the window to compare"
              : "Show the declared part beside the scan"
          }
        >
          ⇤
        </button>
        <span className="compare-pane__collapsed-label">compare</span>
      </div>
    );
  }

  const notice = comparePaneNotice(variant === null ? emptyReason : null, load);

  return (
    <div ref={rootRef} className="compare-pane">
      <header className="compare-pane__header">
        <div className="compare-pane__titles">
          <span className="compare-pane__title">Compare — library part</span>
          <span className="compare-pane__caption">
            {variant
              ? partPreviewLabel({
                  variant: variant.variant,
                  rimDiameterMm: variant.rimDiameterMm,
                  heightMm: variant.heightMm,
                  tooth,
                  loading: load.kind === "loading",
                })
              : "the active site's declared variant appears here"}
          </span>
        </div>
        <button
          type="button"
          className="compare-pane__toggle"
          aria-expanded="true"
          onClick={onToggleCollapsed}
          title="Collapse the compare pane and give the width back to the scan"
        >
          ⇥
        </button>
      </header>
      <div className="compare-pane__stage">
        {variant !== null && (
          <VerifyViewer
            layers={layers}
            frame={frame}
            ariaLabel="The declared library part, shown beside the scan for comparison"
          />
        )}
        {notice && (
          <p className="compare-pane__notice" role="status">
            {notice}
          </p>
        )}
        {variant !== null && load.kind === "loading" && (
          <p className="compare-pane__busy" role="status">
            loading the library part…
          </p>
        )}
      </div>
    </div>
  );
}
