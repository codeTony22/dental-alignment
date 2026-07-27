import type { ImportCompatibility, PoseTransferDocument } from "../domain/poseTransfer";
import { canImport, describeImportSite } from "../domain/poseTransfer";

/**
 * The IMPORT half's lifecycle, owned by App and rendered here.
 *
 * "unavailable" is the honest 404: the RUNNING backend has no import route yet (this build
 * proposes to `POST /api/cases/{id}/sites/{tooth}/import-pose`). It is a named state rather than
 * a generic failure for the same reason /api/constructions and /api/library have one — the
 * operator must read "that endpoint does not exist yet", not "something went wrong".
 */
export type PoseImportState =
  | { readonly kind: "idle" }
  | { readonly kind: "parse-error"; readonly filename: string; readonly message: string }
  | {
      readonly kind: "ready";
      readonly filename: string;
      readonly document: PoseTransferDocument;
      readonly compatibility: ImportCompatibility;
    }
  | { readonly kind: "submitting"; readonly filename: string; readonly tooth: number }
  | { readonly kind: "applied"; readonly lines: readonly string[] }
  | { readonly kind: "refused"; readonly message: string }
  | { readonly kind: "unavailable" };

export interface PoseTransferPanelProps {
  readonly caseId: string;
  /** Teeth whose seated pose is on hand and can be written to a file. */
  readonly exportableTeeth: readonly number[];
  /** Sites with no exportable pose (no run yet, or implant.json could not be read) — SAID, not
   *  silently omitted: an export missing a site is discovered on the importing machine. */
  readonly missingPoseTeeth: readonly number[];
  readonly importState: PoseImportState;
  /** null exports the whole case. */
  readonly onExport: (tooth: number | null) => void;
  readonly onChooseFile: (file: File) => void;
  readonly onApplyImport: () => void;
  readonly onClearImport: () => void;
}

/**
 * POSE IMPORT / EXPORT (RealGUIDE screenshot parity, 2026-07-25).
 *
 * EXPORT is pure client work: the pose matrices the viewer already fetched for its axis triads,
 * plus the selection that produced them and the provenance already on each row. Nothing is asked
 * of the backend, so it works on any build.
 *
 * IMPORT IS AN OPERATOR WRITE, and it obeys the house rule every other operator write obeys: the
 * client PROPOSES, the server's gates judge, the write is audited. This panel therefore never
 * applies a pose — it parses the file, states what the file holds, judges COMPATIBILITY against
 * the case in front of the operator (a different implant system or jaw BLOCKS: restoring a
 * matrix onto a different part is seating the wrong object precisely), and hands a proposal to
 * the endpoint. A backend without that endpoint yet lands on the "unavailable" state below,
 * naming the route it needs — the same graceful degradation the catalog panels use, never a
 * crash and never a silent local overwrite.
 */
export function PoseTransferPanel({
  caseId,
  exportableTeeth,
  missingPoseTeeth,
  importState,
  onExport,
  onChooseFile,
  onApplyImport,
  onClearImport,
}: PoseTransferPanelProps) {
  const canExport = exportableTeeth.length > 0;
  return (
    <section className="pose-transfer" aria-labelledby="pose-transfer-heading">
      <h3 id="pose-transfer-heading" className="pose-transfer__title">
        Pose transfer
      </h3>
      <p className="panel__copy">
        Export a portable pose file — the seated matrix for a site, the selection that produced it
        (system, cap, construction, jaw, relief) and which operator adjustments it already
        contains. Import proposes a prior alignment back onto this case; the server&apos;s gates
        judge it and record it, exactly like a rotation nudge. It is never a silent overwrite.
      </p>

      <div className="pose-transfer__row">
        <button
          type="button"
          className="button button--secondary button--small"
          disabled={!canExport}
          title={
            canExport
              ? `Write every seated site of ${caseId} to one file`
              : "No seated pose yet — run the automation first"
          }
          onClick={() => onExport(null)}
        >
          ⭳ Export case
        </button>
        {exportableTeeth.map((tooth) => (
          <button
            key={tooth}
            type="button"
            className="button button--ghost button--small"
            title={`Write tooth ${tooth}'s seated pose to a file`}
            onClick={() => onExport(tooth)}
          >
            ⭳ tooth {tooth}
          </button>
        ))}
      </div>

      {missingPoseTeeth.length > 0 && (
        <p className="panel__hint">
          No seated pose to export for tooth {missingPoseTeeth.join(", ")} — that site has not been
          aligned on this run.
        </p>
      )}

      <div className="pose-transfer__import">
        <label className="pose-transfer__file-label" htmlFor="pose-transfer-file">
          Import a pose file
        </label>
        <input
          id="pose-transfer-file"
          type="file"
          accept="application/json,.json"
          className="pose-transfer__file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            // the same file picked twice must re-parse — clear the input's value
            e.target.value = "";
            if (file) onChooseFile(file);
          }}
        />
      </div>

      {importState.kind === "parse-error" && (
        <p className="panel__error" role="alert">
          {importState.filename}: {importState.message}
        </p>
      )}

      {importState.kind === "unavailable" && (
        <p className="panel__error" role="alert">
          Pose import is not yet available — the running backend has no{" "}
          <code>POST /api/cases/&#123;case&#125;/sites/&#123;tooth&#125;/import-pose</code> route.
          Export works regardless; restart <code>make serve</code> once the worker ships the
          endpoint.
        </p>
      )}

      {importState.kind === "refused" && (
        <p className="panel__error" role="alert">
          {importState.message}
        </p>
      )}

      {importState.kind === "applied" && (
        <div className="pose-transfer__applied" role="status">
          <p className="panel__hint panel__hint--recompute">Imported as a proposal, and recorded:</p>
          <ul className="pose-transfer__list">
            {importState.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <button type="button" className="button button--ghost button--small" onClick={onClearImport}>
            Dismiss
          </button>
        </div>
      )}

      {importState.kind === "submitting" && (
        <p className="panel__hint" role="status" aria-live="polite">
          Proposing tooth {importState.tooth}&apos;s pose from {importState.filename}…
        </p>
      )}

      {importState.kind === "ready" && (
        <div className="pose-transfer__pending">
          <p className="pose-transfer__file-name">
            {importState.filename} — case {importState.document.caseId}, exported{" "}
            {importState.document.exportedAt || "at an unrecorded time"}
          </p>
          <ul className="pose-transfer__list">
            {importState.document.sites.map((site) => (
              <li key={site.tooth}>{describeImportSite(site)}</li>
            ))}
          </ul>
          {importState.compatibility.blockers.length > 0 && (
            <p className="panel__error" role="alert">
              This file cannot be imported into {caseId}: {importState.compatibility.blockers.join("; ")}.
            </p>
          )}
          {importState.compatibility.warnings.length > 0 && (
            <ul className="pose-transfer__warnings" role="status">
              {importState.compatibility.warnings.map((warning) => (
                <li key={warning}>⚠ {warning}</li>
              ))}
            </ul>
          )}
          <div className="pose-transfer__row">
            <button
              type="button"
              className="button button--primary button--small"
              disabled={!canImport(importState.compatibility)}
              title={
                canImport(importState.compatibility)
                  ? `Propose tooth ${importState.compatibility.teeth.join(", ")} — the server's gates judge it`
                  : `Cannot import: ${importState.compatibility.blockers.join("; ")}`
              }
              onClick={onApplyImport}
            >
              Propose import ({importState.compatibility.teeth.length} site
              {importState.compatibility.teeth.length === 1 ? "" : "s"})
            </button>
            <button type="button" className="button button--ghost button--small" onClick={onClearImport}>
              Discard file
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
