import { describe, expect, it } from "vitest";
import { buildStagedViews, groupPartsByRole } from "./caseData";
import type { CaseMeta, CasePart } from "./caseData";

function part(name: string, role: CasePart["role"]): CasePart {
  return { name, role, b64: "" };
}

describe("groupPartsByRole", () => {
  it("buckets parts by their declared role, preserving order within each bucket", () => {
    const parts = [
      part("case-arch.stl", "arch"),
      part("case-4-cap.stl", "cap"),
      part("case-13-cap.stl", "cap"),
      part("case-4-construction.stl", "construction"),
    ];
    const groups = groupPartsByRole(parts);
    expect(groups.arch).toEqual([parts[0]]);
    expect(groups.cap).toEqual([parts[1], parts[2]]);
    expect(groups.construction).toEqual([parts[3]]);
  });

  it("returns empty arrays for roles with no parts", () => {
    const groups = groupPartsByRole([part("case-arch.stl", "arch")]);
    expect(groups.cap).toEqual([]);
    expect(groups.construction).toEqual([]);
  });

  it("returns all-empty groups for an empty parts list", () => {
    const groups = groupPartsByRole([]);
    expect(groups).toEqual({ arch: [], cap: [], construction: [] });
  });
});

describe("buildStagedViews", () => {
  const emptyMeta: CaseMeta = { sites: [] };

  it("builds the healing-cap-alignment view from arch + cap parts", () => {
    const parts = [part("case-arch.stl", "arch"), part("case-4-healingcap-aligned.stl", "cap")];
    const views = buildStagedViews(parts, emptyMeta);
    const stage1 = views[0];
    expect(stage1?.label).toBe("Healing-cap alignment");
    expect(stage1?.parts).toEqual(parts);
  });

  it("builds the construction-in-arch view from arch + construction parts", () => {
    const parts = [
      part("case-arch-capless.stl", "arch"),
      part("case-4-prosthesis_cad.stl", "construction"),
    ];
    const views = buildStagedViews(parts, emptyMeta);
    const stage2 = views[1];
    expect(stage2?.label).toBe("Construction in arch");
    expect(stage2?.parts).toEqual(parts);
  });

  it("adds one construction-alone view per site in meta, matched by tooth number in the filename", () => {
    const parts = [
      part("case-arch.stl", "arch"),
      part("case-4-prosthesis_cad.stl", "construction"),
      part("case-13-prosthesis_cad.stl", "construction"),
    ];
    const meta: CaseMeta = {
      sites: [
        { tooth: 4, variant: "5020", fitAvgMm: 0.3, fitMaxMm: 1.1, seatMethod: "rim", guidanceLevel: "ready" },
        { tooth: 13, variant: "6030", fitAvgMm: 0.5, fitMaxMm: 2.0, seatMethod: "icp", guidanceLevel: "attention" },
      ],
    };
    const views = buildStagedViews(parts, meta);
    expect(views).toHaveLength(4); // stage1 + stage2 + 2 per-tooth
    expect(views[2]?.label).toBe("Construction alone — tooth 4");
    expect(views[2]?.parts).toEqual([parts[1]]);
    expect(views[3]?.label).toBe("Construction alone — tooth 13");
    expect(views[3]?.parts).toEqual([parts[2]]);
  });

  it("falls back to all construction parts when no filename matches a site's tooth number", () => {
    const parts = [part("case-arch.stl", "arch"), part("case-construction-bundle.stl", "construction")];
    const meta: CaseMeta = {
      sites: [{ tooth: 9, variant: "5020", fitAvgMm: null, fitMaxMm: null, seatMethod: null, guidanceLevel: null }],
    };
    const views = buildStagedViews(parts, meta);
    const perTooth = views[2];
    expect(perTooth?.label).toBe("Construction alone — tooth 9");
    expect(perTooth?.parts).toEqual([parts[1]]);
  });

  it("always returns at least the two arch-level views even with no sites", () => {
    const parts = [part("case-arch.stl", "arch")];
    const views = buildStagedViews(parts, emptyMeta);
    expect(views.map((v) => v.label)).toEqual(["Healing-cap alignment", "Construction in arch"]);
  });
});
