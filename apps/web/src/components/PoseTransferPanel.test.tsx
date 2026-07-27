/**
 * POSE TRANSFER's rendered contract. Pinned: export is offered per site and for the case and
 * SAYS which sites have no pose; a parsed file states what it holds; an incompatible file
 * refuses with the reason on the button; and the missing-endpoint case is a NAMED, clearly
 * labelled state that names the route the worker must add — never a crash and never a silent
 * local pose overwrite.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PoseTransferPanel, type PoseImportState } from "./PoseTransferPanel";
import type { PoseTransferDocument } from "../domain/poseTransfer";

const DOC: PoseTransferDocument = {
  format: "artech.pose-transfer",
  version: 1,
  caseId: "276794487-zimmer-4.5",
  exportedAt: "2026-07-25T12:00:00.000Z",
  selection: {
    model: "neodent-gm",
    constructionPathId: "zimmer/ti-base.stl",
    jaw: "upper",
    gingivalOffsetMm: 0.2,
  },
  sites: [
    {
      tooth: 3,
      variantId: "6020",
      poseMatrix: [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
      ],
      provenance: {
        seedSource: "marks",
        seatMethod: "rim",
        nudgeCumulativeDeg: 12.5,
        rotationUnverified: false,
        clockEvidence: "codes",
        identifiedVariant: "6020",
        doctorConfirmed: null,
        doctorNote: null,
        doctorConfirmedAt: null,
      },
    },
  ],
};

function render(over: Partial<Parameters<typeof PoseTransferPanel>[0]> = {}) {
  return renderToStaticMarkup(
    <PoseTransferPanel
      caseId="276794487-zimmer-4.5"
      exportableTeeth={[3, 14]}
      missingPoseTeeth={[]}
      importState={{ kind: "idle" }}
      onExport={() => {}}
      onChooseFile={() => {}}
      onApplyImport={() => {}}
      onClearImport={() => {}}
      {...over}
    />,
  );
}

describe("PoseTransferPanel — export", () => {
  it("offers the whole case and each seated site", () => {
    const html = render();
    expect(html).toContain("⭳ Export case");
    expect(html).toContain("⭳ tooth 3");
    expect(html).toContain("⭳ tooth 14");
  });

  it("refuses to offer an export before anything is seated, and says why", () => {
    const html = render({ exportableTeeth: [] });
    expect(html).toContain('disabled="" title="No seated pose yet — run the automation first"');
  });

  it("names the sites it has no pose for instead of shipping a quietly partial file", () => {
    expect(render({ missingPoseTeeth: [29] })).toContain("No seated pose to export for tooth 29");
  });
});

describe("PoseTransferPanel — import", () => {
  const ready: PoseImportState = {
    kind: "ready",
    filename: "case-3-pose.json",
    document: DOC,
    compatibility: { blockers: [], warnings: [], teeth: [3] },
  };

  it("states that an import is a judged, recorded proposal — not an overwrite", () => {
    const html = render();
    expect(html).toContain("gates");
    expect(html).toContain("never a silent overwrite");
  });

  it("shows what a parsed file holds, adjustments included", () => {
    const html = render({ importState: ready });
    expect(html).toContain("case-3-pose.json");
    expect(html).toContain("tooth 3 · 6020 · rim seat · operator rotation +12.5°");
    expect(html).toContain("Propose import (1 site)");
  });

  it("blocks an incompatible file and puts the reason on the button", () => {
    const html = render({
      importState: {
        ...ready,
        compatibility: {
          blockers: ["the file was produced for the lower jaw, this case is selected for the upper jaw"],
          warnings: [],
          teeth: [],
        },
      },
    });
    expect(html).toContain("This file cannot be imported into 276794487-zimmer-4.5");
    expect(html).toContain(
      'disabled="" title="Cannot import: the file was produced for the lower jaw',
    );
  });

  it("shows differences that do not block as warnings the operator decides on", () => {
    const html = render({
      importState: {
        ...ready,
        compatibility: { blockers: [], warnings: ["the file was exported from case other"], teeth: [3] },
      },
    });
    expect(html).toContain("the file was exported from case other");
    expect(html).toContain("Propose import (1 site)");
  });

  it("reports a parse refusal with the file's name and the reason", () => {
    const html = render({
      importState: { kind: "parse-error", filename: "notes.json", message: "That file is not JSON…" },
    });
    expect(html).toContain("notes.json: That file is not JSON…");
  });

  it("labels the missing endpoint as NOT YET AVAILABLE and names the route it needs", () => {
    const html = render({ importState: { kind: "unavailable" } });
    expect(html).toContain("Pose import is not yet available");
    expect(html).toContain("/import-pose");
    expect(html).toContain("Export works regardless");
  });

  it("shows the server's own refusal sentence verbatim", () => {
    const html = render({
      importState: { kind: "refused", message: "Rotation refused: stability excess 0.42 mm." },
    });
    expect(html).toContain("Rotation refused: stability excess 0.42 mm.");
  });

  it("reports what was actually applied", () => {
    const html = render({
      importState: { kind: "applied", lines: ["tooth 3 — pose proposed, codes now read −1.4°"] },
    });
    expect(html).toContain("Imported as a proposal, and recorded:");
    expect(html).toContain("tooth 3 — pose proposed, codes now read −1.4°");
  });
});
