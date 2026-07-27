import { useEffect } from "react";

/**
 * Everything the viewer-overlay chip needs to say WHAT part is on screen instead of the scan:
 * the library variant id, its catalog dimensions (null when the catalog has none), which tooth's
 * row the preview belongs to (null only if that row vanished mid-preview), and whether the part's
 * mesh is still loading (live variant switching swaps the part while the chip stays up).
 */
export interface PartPreviewInfo {
  readonly variant: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly tooth: number | null;
  readonly loading: boolean;
}

/** "Ø6.16 × 3.38 mm", or null when the catalog carries no dimensions for the variant. */
export function formatVariantDims(rimDiameterMm: number | null, heightMm: number | null): string | null {
  return rimDiameterMm !== null && heightMm !== null ? `Ø${rimDiameterMm} × ${heightMm} mm` : null;
}

/** "6020 · Ø6.16 × 3.38 mm (tooth 3)" — dims/tooth segments dropped when unknown. */
export function partPreviewLabel(preview: PartPreviewInfo): string {
  const dims = formatVariantDims(preview.rimDiameterMm, preview.heightMm);
  const tooth = preview.tooth !== null ? ` (tooth ${preview.tooth})` : "";
  return `${preview.variant}${dims ? ` · ${dims}` : ""}${tooth}`;
}

/**
 * Keydown handler factory — a pure function (Escape → exit, everything else ignored) so the
 * wiring is unit-testable in the node test env, per the repo's static-markup convention
 * (interaction logic lives in pure functions/handlers with their own tests).
 */
export function makePreviewKeyHandler(onBackToScan: () => void): (event: { key: string }) => void {
  return (event) => {
    if (event.key === "Escape") onBackToScan();
  };
}

interface PartPreviewChipProps {
  /** null renders nothing — the chip exists ONLY while a library-part preview is on screen. */
  readonly preview: PartPreviewInfo | null;
  /** False when NO case is selected (library-browser preview on the empty stage): there is no
   *  scan to go back to, so the Back button and its Escape twin are omitted — the chip still
   *  names the part, it just cannot offer a way "back" that does not exist. */
  readonly canReturnToScan: boolean;
  readonly onBackToScan: () => void;
}

/**
 * Viewer overlay shown while a LIBRARY PART (not the doctor's scan) is on screen (client ask
 * 2026-07-23: "visibility of the parts, and when we choose a part we can go back to the actual
 * scan"). The preview state was previously invisible — nothing said "this is not your scan" and
 * there was no way back short of arming a marking tool. The chip names the part + its catalog
 * dimensions + the row's tooth, and carries the explicit way back. Escape is the keyboard
 * equivalent of the Back button, registered only while the chip is mounted — mirroring how the
 * mark/rim banners' Cancel buttons pair with App's own Escape listener.
 */
export function PartPreviewChip({ preview, canReturnToScan, onBackToScan }: PartPreviewChipProps) {
  const active = preview !== null && canReturnToScan;
  useEffect(() => {
    if (!active) return undefined;
    const handler = makePreviewKeyHandler(onBackToScan);
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active, onBackToScan]);

  if (preview === null) return null;

  return (
    <div className="part-preview-chip" role="status" aria-live="polite">
      {preview.loading && <span className="part-preview-chip__spinner" aria-hidden="true" />}
      <span className="part-preview-chip__text">
        {preview.loading ? "Loading library part — " : "Viewing library part — "}
        {partPreviewLabel(preview)}
      </span>
      {canReturnToScan && (
        <button
          type="button"
          className="part-preview-chip__back"
          onClick={onBackToScan}
          title="Restore the clean input scan (Esc)"
        >
          ← Back to scan
        </button>
      )}
    </div>
  );
}
