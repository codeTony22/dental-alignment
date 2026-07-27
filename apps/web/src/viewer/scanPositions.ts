/**
 * THE DOCTOR'S SCAN, PARSED ONCE PER CASE — shared by every comparison pane that needs the
 * arch's raw geometry (the three-panel verify, and the fit-by-points stage's scan half).
 *
 * The arch is 11-25 MB. Re-downloading and re-parsing it each time a pane mounts cost seconds of
 * blank canvas, and two panes that parse it separately hold two copies of the same 20 MB array —
 * so the cache lives here, at module scope, rather than inside whichever component happened to
 * need it first (it did: this was private to VerifyStage until the fit-by-points stage needed
 * the same bytes).
 *
 * ONE ENTRY ONLY: a second case's scan evicts the first rather than accumulating tens of
 * megabytes for cases nobody is looking at.
 */
import { scanUrlFor } from "../api/client";
import { loadStlPositions } from "./verifyScene";

let scanCache: { caseId: string; positions: Float32Array } | null = null;

export async function scanPositionsFor(caseId: string): Promise<Float32Array> {
  if (scanCache?.caseId === caseId) return scanCache.positions;
  const positions = await loadStlPositions(scanUrlFor(caseId));
  scanCache = { caseId, positions };
  return positions;
}

/** Drop the cached scan — for tests, and for any caller that needs the next read to be a fetch. */
export function clearScanPositionsCache(): void {
  scanCache = null;
}
