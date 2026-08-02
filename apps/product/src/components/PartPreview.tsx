/**
 * THE UNRUN CONSTRUCTION PART, PREVIEWED ALONE (§10-M2's "natural next slice",
 * 2026-08-02 — "previewing a part the case has NOT run" was the one thing M2 left
 * open once the run's own baked union was wired up).
 *
 * WHAT THIS IS NOT: the union `DeliverPreview`'s "2 · Construction in arch" tab
 * shows, and `libraryPreviewCaption` names — that mesh is the RUN's own, built
 * from the part the run actually used, posed against this case's own scan. THIS
 * mesh is the vendor's catalog part ALONE, in its OWN local frame: nothing here
 * has been cut, seated, or measured against any site in this case. Letting the
 * operator read the two as the same thing is exactly the over-claim §10-M2's
 * caption doctrine forbids — `libraryPartPreviewCaption` is the whole difference
 * between a preview and a promise.
 *
 * `meshUrl` is followed VERBATIM from the catalog row's own SERVED `mesh_url`
 * (BFF `GET /api/constructions/{vendor}/{filename}/mesh`, landed da698b5) — this
 * app never assembles the path itself, the same posture `domain/declare.ts`'s
 * `variantMeshUrl` already states for cap variants. `null` (a row from a BFF that
 * predates the route, or one the catalog otherwise cannot resolve) degrades to
 * the stated gap below, never a client-guessed URL or a viewer with nothing to
 * show — CLAUDE.md's stale-server trap, the same discipline `libraryPreviewTab`
 * already applies to the run-mesh side of this page.
 *
 * Container mirrors DeliverPreview.tsx's shape exactly: `loadStlPositions(url)`
 * with a stale-response guard, `frame={null}` so `VerifyScene.frameAll()` frames
 * the isolated part (the pane doctrine: "a cap rendering 14px tall in a viewport
 * is a bug — frame so the subject fills its pane" applies just as hard to a lone
 * scanbody, which would otherwise be a speck in the scanner's own world frame).
 */
import { useEffect, useState, type ReactNode } from "react";
import { PALETTE, VerifyViewer, loadStlPositions, type VerifyLayerGeometry } from "viewer";
import { libraryPartPreviewCaption } from "../domain/deliver";

export interface PartPreviewViewProps {
  readonly label: string;
  /** The row's own served url, or null — see the module doc's stale-server note. */
  readonly meshUrl: string | null;
  readonly busy: boolean;
  readonly error: string | null;
  /** The 3D surface itself — the container passes the real viewer; tests pass a stub. */
  readonly viewerSlot: ReactNode;
}

/** The pane's chrome, pure payload -> markup — statically testable without WebGL. */
export function PartPreviewView({
  label,
  meshUrl,
  busy,
  error,
  viewerSlot,
}: PartPreviewViewProps) {
  return (
    <section
      data-role="library-part-preview"
      aria-label={`Catalog part preview: ${label}`}
      className="panel deliver-mesh-preview library-part-preview"
    >
      <h3 className="panel__title">
        Catalog part<span className="panel__title-case"> · {label}</span>
      </h3>
      {meshUrl === null ? (
        // NO INVENTED URL, NO DEAD VIEWER (repo-wide doctrine, restated by
        // CLAUDE.md's stale-server trap): a row that cannot be previewed states
        // the gap rather than mounting a viewer with nothing to load.
        <p data-role="library-part-preview-pending" className="panel__hint">
          This catalog part carries no preview mesh yet — it is still a valid pick,
          it just cannot be shown alone until the BFF serves one.
        </p>
      ) : (
        <>
          <div
            data-role="library-part-preview-canvas"
            className="deliver-mesh-preview__canvas"
          >
            {viewerSlot}
            {busy && (
              <p
                data-role="library-part-preview-busy"
                className="deliver-mesh-preview__notice"
              >
                Loading {label}…
              </p>
            )}
            {error !== null && (
              <div
                data-role="library-part-preview-error"
                role="alert"
                className="deliver-mesh-preview__notice"
              >
                {error}
              </div>
            )}
          </div>
          <p data-role="library-part-preview-caption" className="panel__hint">
            {libraryPartPreviewCaption(label)}
          </p>
        </>
      )}
    </section>
  );
}

export interface PartPreviewProps {
  readonly label: string;
  readonly meshUrl: string | null;
}

/** The container: the armed candidate's mesh bytes, loaded and framed alone. */
export function PartPreview({ label, meshUrl }: PartPreviewProps) {
  const [positions, setPositions] = useState<Float32Array | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (meshUrl === null) {
      setPositions(null);
      setError(null);
      setBusy(false);
      return undefined;
    }
    let cancelled = false;
    setPositions(null);
    setError(null);
    setBusy(true);
    loadStlPositions(meshUrl)
      .then((loaded) => {
        if (!cancelled) setPositions(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          // NAMES THE PART, NEVER A GENERIC FAILURE (task doctrine): loadStlPositions'
          // own message is three.js's fetch-status text, which never carries the
          // BFF's own JSON `detail` (STLLoader reads bytes, not the error body), so
          // this is what keeps the refusal honestly attributable rather than a bare
          // "something went wrong".
          const detail = err instanceof Error ? err.message : "the request failed";
          setError(`"${label}" did not load: ${detail}`);
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [meshUrl, label]);

  const geometry: VerifyLayerGeometry | null =
    positions !== null ? { positions, color: PALETTE.construction } : null;

  return (
    <PartPreviewView
      label={label}
      meshUrl={meshUrl}
      busy={busy}
      error={error}
      viewerSlot={
        <VerifyViewer
          layers={[{ id: "part", geometry, visible: true, opacity: 1 }]}
          frame={null}
          ariaLabel={`Preview: ${label}`}
        />
      }
    />
  );
}
