import type { RunSiteResult } from "../domain/types";
import type { PartRole } from "../viewer/palette";

/** One part of a staged composite view: a file *name* (App.tsx resolves it to a URL) plus its color role. */
export interface StagedPart {
  readonly name: string;
  readonly role: PartRole;
}

/** A staged view request: either the raw scan endpoint (kind "scan") or a files_base-relative part name. */
export type StagedPartSource = { readonly kind: "scan" } | { readonly kind: "file"; readonly name: string };

export interface StagedComposite {
  readonly parts: ReadonlyArray<{ readonly source: StagedPartSource; readonly role: PartRole }>;
  /** If every part fails to resolve (e.g. an older cached run missing arch-capless.stl), show this single merged file instead. */
  readonly fallbackFile?: string;
}

interface ViewerControlsProps {
  readonly sites: readonly RunSiteResult[];
  readonly onShowComposite: (composite: StagedComposite, label: string) => void;
  readonly caseId: string;
  readonly activeLabel: string | null;
}

/** Label for stage 1, exported so App.tsx's post-run auto-reveal can set activeViewLabel
 *  to the exact string this button compares against (so it lights up as active). */
export const STAGE1_LABEL = "1 · Healing-cap alignment";

/** Stage 1 · the healing-cap ALIGNMENT on the whole arch: the doctor's scan (ivory) plus
 *  every site's aligned healing cap (green). Exported so App.tsx can reuse the EXACT same
 *  composition for the post-run auto-reveal instead of re-deriving it. */
export function buildStage1Composite(sites: readonly RunSiteResult[], caseId: string): StagedComposite {
  return {
    parts: [
      { source: { kind: "scan" }, role: "arch" },
      ...sites.map((site) => ({
        source: { kind: "file" as const, name: `${caseId}-${site.tooth}-healingcap-aligned.stl` },
        role: "cap" as const,
      })),
    ],
  };
}

/** The client's staged reveal: 1 · the healing-cap ALIGNMENT on the whole arch;
 *  2 · the arch with the scanned cap replaced by the CONSTRUCTION; 3 · each aligned
 *  construction part alone. Each stage is rendered as a colored composite — the doctor's
 *  scan in ivory, healing caps in green, constructions in steel blue — since STL itself
 *  carries no color. */
export function ViewerControls({ sites, onShowComposite, caseId, activeLabel }: ViewerControlsProps) {
  const btn = (composite: StagedComposite, label: string) => {
    // activeLabel may carry a " (legacy view)" suffix (stage-2 fallback to the pre-merged
    // file) — match by prefix so the button still highlights as active in that case.
    const isActive = activeLabel === label || activeLabel === `${label} (legacy view)`;
    return (
      <button
        key={label}
        type="button"
        className={`button button--secondary${isActive ? " button--active" : ""}`}
        onClick={() => onShowComposite(composite, label)}
      >
        {label}
      </button>
    );
  };

  const stage1 = buildStage1Composite(sites, caseId);

  const stage2: StagedComposite = {
    parts: [
      { source: { kind: "file", name: `${caseId}-arch-capless.stl` }, role: "arch" },
      ...sites.map((site) => ({
        source: { kind: "file" as const, name: `${caseId}-${site.tooth}-prosthesis_cad.stl` },
        role: "construction" as const,
      })),
    ],
    fallbackFile: `${caseId}-arch-with-constructions.stl`,
  };

  return (
    <div className="viewer-controls">
      {btn(stage1, STAGE1_LABEL)}
      {btn(stage2, "2 · Construction in arch")}
      {sites.map((site) =>
        btn(
          {
            parts: [
              {
                source: { kind: "file", name: `${caseId}-${site.tooth}-prosthesis_cad.stl` },
                role: "construction",
              },
            ],
          },
          `3 · Construction alone — tooth ${site.tooth}`,
        ),
      )}
    </div>
  );
}
