/**
 * POSE IMPORT / EXPORT's domain rules. The three things this file exists to pin:
 *  1. an exported matrix is BIT-FOR-BIT the one the pipeline wrote (round-trip against
 *     api/mappers' own implant.json reader — the two must never drift apart);
 *  2. a file that is not a rigid placement, or is from a newer build, is REFUSED with a
 *     sentence rather than half-parsed;
 *  3. the compatibility judgment: a different implant system or jaw BLOCKS (a restored matrix
 *     would seat the wrong object precisely), everything else warns.
 */
import { describe, expect, it } from "vitest";
import {
  buildPoseTransfer,
  canImport,
  describeImportSite,
  importCompatibility,
  parsePoseMatrix,
  parsePoseTransfer,
  poseMatrixFrom,
  poseTransferFilename,
  POSE_TRANSFER_FORMAT,
  POSE_TRANSFER_VERSION,
  provenanceFrom,
  serializePoseTransfer,
} from "./poseTransfer";
import type { PoseMatrix, PoseSourceRow, PoseTransferSelection, SeatedPose } from "./poseTransfer";
import { mapImplantPose } from "../api/mappers";

const SELECTION: PoseTransferSelection = {
  model: "neodent-gm",
  constructionPathId: "zimmer/ti-base.stl",
  jaw: "upper",
  gingivalOffsetMm: 0.2,
};

/** A 90° rotation about Z, translated — a genuinely rigid, non-identity pose. */
const POSE: SeatedPose = {
  position: [10, -4, 2.5],
  axisX: [0, 1, 0],
  axisY: [-1, 0, 0],
  axisZ: [0, 0, 1],
};

const ROW: PoseSourceRow = {
  tooth: 3,
  seedSource: "marks",
  seatMethod: "rim",
  clocking: { rotationUnverified: false, evidence: "codes" },
  nudge: { cumulativeDeg: 12.5 },
  doctorConfirmation: { confirmed: true, note: "seat looks right", ts: "2026-07-25T09:00:00Z" },
  variant: { declared: "6020", identified: "6020" },
};

function build(over: Partial<Parameters<typeof buildPoseTransfer>[0]> = {}) {
  return buildPoseTransfer({
    caseId: "276794487-zimmer-4.5",
    exportedAt: new Date("2026-07-25T12:00:00Z"),
    selection: SELECTION,
    rows: [ROW],
    poses: new Map([[3, POSE]]),
    declaredByTooth: new Map([[3, "6020"]]),
    ...over,
  });
}

describe("poseMatrixFrom", () => {
  it("round-trips the pipeline's own implant.json matrix, unchanged", () => {
    const wire = {
      case_id: "c",
      tooth: 3,
      pose_matrix: [
        [0, -1, 0, 10],
        [1, 0, 0, -4],
        [0, 0, 1, 2.5],
        [0, 0, 0, 1],
      ] as const,
      position: [10, -4, 2.5] as const,
      axis: [0, 0, 1] as const,
    };
    const pose = mapImplantPose(wire);
    expect(poseMatrixFrom(pose)).toEqual(wire.pose_matrix);
  });

  it("writes [0,0,0,1] as the bottom row — the transform is rigid by construction", () => {
    expect(poseMatrixFrom(POSE)[3]).toEqual([0, 0, 0, 1]);
  });
});

/**
 * THE ROUND TRIP AGAINST A REAL SEAT, not a hand-written 90° one.
 *
 * A synthetic matrix of exact halves and units proves the index arithmetic; it cannot prove that
 * a genuine pipeline pose survives the trip. This one is copied verbatim out of the delivered
 * package `reports/final-export/neodent-gm/neodent-gm-4-implant.json` — full-precision doubles
 * off an actual seat — and it exercises the two things only real numbers can:
 *  - the RIGIDITY CHECK must ACCEPT it (a tolerance tight enough to reject honest float noise
 *    would refuse every real export, which is a far worse failure than accepting a sloppy one);
 *  - JSON.stringify -> JSON.parse must return the SAME doubles, so a file written on one
 *    workstation seats identically on another rather than "almost".
 * Inlined rather than read off disk on purpose: the test stays hermetic, and the fixture is the
 * evidence — if the emitter's format ever moves, this literal is what has to be re-copied.
 */
describe("a REAL delivered pose survives export and re-import unchanged", () => {
  const REAL_RECORD = {
    case_id: "neodent-gm",
    tooth: 4,
    pose_matrix: [
      [0.17456181107491966, 0.7474663621544867, 0.6409541415435177, 7.44068897275737],
      [-0.08594767288364122, 0.6600309148966093, -0.7463056940065734, -22.733247235929255],
      [-0.9808879506040074, 0.07518795667051581, 0.179459186255766, 15.191105732102368],
      [0, 0, 0, 1],
    ],
    position: [7.44068897275737, -22.733247235929255, 15.191105732102368],
    axis: [0.6409541415435177, -0.7463056940065734, 0.179459186255766],
  } as const;

  it("re-derives the delivered matrix exactly from the viewer's own reading of it", () => {
    // the pipeline writes `position` AS pose_matrix[:3,3] (SitePackageSpec.position is that
    // slice), which is why reading the two apart and writing them back together is lossless
    expect(poseMatrixFrom(mapImplantPose(REAL_RECORD as never))).toEqual(REAL_RECORD.pose_matrix);
  });

  it("serializes and parses back to the identical doubles, rigidity accepted", () => {
    const pose = mapImplantPose(REAL_RECORD as never);
    const { document, skippedTeeth } = buildPoseTransfer({
      caseId: "neodent-gm",
      exportedAt: new Date("2026-07-25T12:00:00Z"),
      selection: SELECTION,
      rows: [{ ...ROW, tooth: 4 }],
      poses: new Map([[4, pose]]),
      declaredByTooth: new Map([[4, "6020"]]),
    });
    expect(skippedTeeth).toEqual([]);
    const reparsed = parsePoseTransfer(serializePoseTransfer(document));
    // a refusal here would mean the rigidity check rejects the pipeline's own output
    expect(reparsed).toMatchObject({ kind: "ok" });
    if (reparsed.kind !== "ok") return;
    expect(reparsed.document.sites[0]?.poseMatrix).toEqual(REAL_RECORD.pose_matrix);
    expect(reparsed.document.sites[0]?.provenance.seatMethod).toBe("rim");
    expect(reparsed.document.sites[0]?.provenance.nudgeCumulativeDeg).toBe(12.5);
  });
});

describe("buildPoseTransfer", () => {
  it("carries the pose, the selection that produced it and the operator's adjustments", () => {
    const { document, skippedTeeth } = build();
    expect(skippedTeeth).toEqual([]);
    expect(document.format).toBe(POSE_TRANSFER_FORMAT);
    expect(document.version).toBe(POSE_TRANSFER_VERSION);
    expect(document.caseId).toBe("276794487-zimmer-4.5");
    expect(document.exportedAt).toBe("2026-07-25T12:00:00.000Z");
    expect(document.selection).toEqual(SELECTION);
    expect(document.sites).toHaveLength(1);
    expect(document.sites[0]?.tooth).toBe(3);
    expect(document.sites[0]?.variantId).toBe("6020");
    expect(document.sites[0]?.provenance).toEqual({
      seedSource: "marks",
      seatMethod: "rim",
      nudgeCumulativeDeg: 12.5,
      rotationUnverified: false,
      clockEvidence: "codes",
      identifiedVariant: "6020",
      doctorConfirmed: true,
      doctorNote: "seat looks right",
      doctorConfirmedAt: "2026-07-25T09:00:00Z",
    });
  });

  it("reports the teeth it could not export instead of silently shipping a partial file", () => {
    const { document, skippedTeeth } = build({
      rows: [ROW, { ...ROW, tooth: 14 }],
      poses: new Map([[3, POSE]]),
    });
    expect(document.sites.map((s) => s.tooth)).toEqual([3]);
    expect(skippedTeeth).toEqual([14]);
  });

  it("exports one site when asked for one, the whole case when asked for none", () => {
    const poses = new Map([
      [3, POSE],
      [14, POSE],
    ]);
    const rows = [ROW, { ...ROW, tooth: 14 }];
    expect(build({ rows, poses }).document.sites).toHaveLength(2);
    expect(build({ rows, poses, onlyTeeth: [14] }).document.sites.map((s) => s.tooth)).toEqual([14]);
  });

  it("keeps null provenance honest when a site has no run row behind it", () => {
    expect(provenanceFrom(null).seatMethod).toBeNull();
    expect(provenanceFrom(null).identifiedVariant).toBeNull();
  });

  it("serializes deterministically — two exports of one state differ only by the timestamp", () => {
    const a = serializePoseTransfer(build().document);
    const b = serializePoseTransfer(build().document);
    expect(a).toBe(b);
    expect(a.endsWith("\n")).toBe(true);
  });

  it("names the file after the case, and the tooth when there is one", () => {
    expect(poseTransferFilename("case-1", 3)).toBe("case-1-3-pose.json");
    expect(poseTransferFilename("case-1", null)).toBe("case-1-pose.json");
    expect(poseTransferFilename("a/b", null)).toBe("a-b-pose.json");
  });
});

describe("parsePoseTransfer", () => {
  const text = () => serializePoseTransfer(build().document);

  it("reads back exactly what it wrote", () => {
    const parsed = parsePoseTransfer(text());
    expect(parsed.kind).toBe("ok");
    if (parsed.kind !== "ok") return;
    expect(parsed.document).toEqual(build().document);
  });

  it("refuses a file that is not one of ours, with a sentence", () => {
    expect(parsePoseTransfer("not json")).toMatchObject({
      kind: "error",
      message: expect.stringContaining("not JSON"),
    });
    expect(parsePoseTransfer(JSON.stringify({ format: "other", version: 1 }))).toMatchObject({
      kind: "error",
      message: expect.stringContaining("not an ArTech pose transfer"),
    });
  });

  it("refuses a file from a newer build rather than guessing at its fields", () => {
    const doc = { ...build().document, version: POSE_TRANSFER_VERSION + 1 };
    expect(parsePoseTransfer(JSON.stringify(doc))).toMatchObject({
      kind: "error",
      message: expect.stringContaining("newer build"),
    });
  });

  it("refuses a pose that is not a rigid placement", () => {
    const scaled: PoseMatrix = [
      [2, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 0, 1],
    ];
    expect(parsePoseMatrix(scaled, "Tooth 3")).toContain("scales or shears");
    const sheared: PoseMatrix = [
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, 1, 0],
      [0, 0, 1, 1],
    ];
    expect(parsePoseMatrix(sheared, "Tooth 3")).toContain("rigid placement");
    // a mirror is orthonormal but left-handed — it would flip the part, so it is refused too
    const mirrored: PoseMatrix = [
      [1, 0, 0, 0],
      [0, 1, 0, 0],
      [0, 0, -1, 0],
      [0, 0, 0, 1],
    ];
    expect(parsePoseMatrix(mirrored, "Tooth 3")).toContain("scales or shears");
  });

  it("accepts a genuine rotation", () => {
    expect(parsePoseMatrix(poseMatrixFrom(POSE), "Tooth 3")).toEqual(poseMatrixFrom(POSE));
  });

  it("refuses a matrix of the wrong shape or with non-numbers", () => {
    expect(parsePoseMatrix([[1, 0, 0, 0]], "Tooth 3")).toContain("4 rows");
    expect(parsePoseMatrix([[1, 0, 0], [0], [0], [0]], "Tooth 3")).toContain("4 numbers");
    expect(
      parsePoseMatrix(
        [
          ["x", 0, 0, 0],
          [0, 1, 0, 0],
          [0, 0, 1, 0],
          [0, 0, 0, 1],
        ],
        "Tooth 3",
      ),
    ).toContain("not a number");
  });

  it("refuses a file with no selection, no jaw, no case or no sites", () => {
    const doc = build().document;
    const without = (key: string) => {
      const copy = { ...doc } as Record<string, unknown>;
      delete copy[key];
      return JSON.stringify(copy);
    };
    expect(parsePoseTransfer(without("caseId"))).toMatchObject({ kind: "error" });
    expect(parsePoseTransfer(without("selection"))).toMatchObject({
      kind: "error",
      message: expect.stringContaining("without its part"),
    });
    expect(
      parsePoseTransfer(JSON.stringify({ ...doc, selection: { ...doc.selection, jaw: "sideways" } })),
    ).toMatchObject({ kind: "error", message: expect.stringContaining("which jaw") });
    expect(parsePoseTransfer(JSON.stringify({ ...doc, sites: [] }))).toMatchObject({
      kind: "error",
      message: expect.stringContaining("no sites"),
    });
  });

  it("drops an unrecognised closed-set value instead of casting it into the union", () => {
    const doc = build().document;
    const tampered = JSON.parse(JSON.stringify(doc)) as Record<string, unknown>;
    (tampered.sites as Record<string, unknown>[])[0]!.provenance = { seatMethod: "telepathy" };
    const parsed = parsePoseTransfer(JSON.stringify(tampered));
    expect(parsed.kind).toBe("ok");
    if (parsed.kind !== "ok") return;
    expect(parsed.document.sites[0]?.provenance.seatMethod).toBeNull();
  });
});

describe("importCompatibility", () => {
  const doc = build().document;
  const target = {
    caseId: "276794487-zimmer-4.5",
    selection: SELECTION,
    siteTeeth: [3, 14],
    declaredByTooth: new Map([
      [3, "6020"],
      [14, "5020"],
    ]),
  };

  it("passes a file that matches the case in front of the operator", () => {
    const verdict = importCompatibility(doc, target);
    expect(verdict.blockers).toEqual([]);
    expect(verdict.warnings).toEqual([]);
    expect(verdict.teeth).toEqual([3]);
    expect(canImport(verdict)).toBe(true);
  });

  it("BLOCKS a different implant system — the pose would seat the wrong part precisely", () => {
    const other = { ...doc, selection: { ...SELECTION, model: "zimmer-tsv" } };
    const verdict = importCompatibility(other, target);
    expect(verdict.blockers.join(" ")).toContain("implant system");
    expect(canImport(verdict)).toBe(false);
  });

  it("BLOCKS a different jaw — the matrix is expressed in that jaw's world frame", () => {
    const other = { ...doc, selection: { ...SELECTION, jaw: "lower" as const } };
    expect(importCompatibility(other, target).blockers.join(" ")).toContain("lower jaw");
  });

  it("BLOCKS a file whose teeth have no site here", () => {
    const other = { ...doc, sites: [{ ...doc.sites[0]!, tooth: 30 }] };
    const verdict = importCompatibility(other, target);
    expect(verdict.blockers.join(" ")).toContain("none of the file's teeth (30)");
    expect(verdict.teeth).toEqual([]);
  });

  it("WARNS about a different case, construction, relief, declared cap, or extra teeth", () => {
    const other = {
      ...doc,
      caseId: "other-case",
      selection: { ...SELECTION, constructionPathId: "x/y.stl", gingivalOffsetMm: 0.35 },
      sites: [{ ...doc.sites[0]!, variantId: "7030" }, { ...doc.sites[0]!, tooth: 30 }],
    };
    const verdict = importCompatibility(other, target);
    expect(verdict.blockers).toEqual([]);
    const text = verdict.warnings.join(" | ");
    expect(text).toContain("exported from case other-case");
    expect(text).toContain("construction part differs");
    expect(text).toContain("gingival relief differs");
    expect(text).toContain("tooth 30 has no site");
    expect(text).toContain("“7030” in the file");
    expect(verdict.teeth).toEqual([3]);
  });
});

describe("describeImportSite", () => {
  it("states the adjustments the pose already contains", () => {
    const site = build().document.sites[0]!;
    expect(describeImportSite(site)).toBe(
      "tooth 3 · 6020 · rim seat · operator rotation +12.5° · doctor-confirmed",
    );
  });

  it("says when a cap was never declared and when the rotation was never verified", () => {
    const site = build().document.sites[0]!;
    expect(
      describeImportSite({
        ...site,
        variantId: null,
        provenance: { ...site.provenance, nudgeCumulativeDeg: 0, rotationUnverified: true, doctorConfirmed: null },
      }),
    ).toBe("tooth 3 · no cap declared · rim seat · rotation unverified");
  });
});
