/**
 * The LIBRARY-SIDE annotation domain (client ask 2026-07-24, half one): the draft-edit rules
 * behind "clicking the part adds or moves a feature", the state line the operator reads, and
 * the PUT body's exactly-one-placement-per-feature contract.
 */
import { describe, expect, it } from "vitest";
import type { DraftFeature, PartFeature } from "./partFeatures";
import {
  MAX_PART_FEATURES,
  annotationStateLine,
  draftCounts,
  draftDefinesRotation,
  draftKey,
  draftsAreDirty,
  draftsFrom,
  featureLabel,
  placeDraft,
  readClick,
  removeDraft,
  toFeatureInputs,
} from "./partFeatures";

function makeFeature(overrides: Partial<PartFeature> = {}): PartFeature {
  return {
    id: "trench-01",
    kind: "trench",
    azimuthDeg: -22.5,
    radiusMm: 1.47,
    zMm: 1.81,
    source: "auto",
    definesRotation: true,
    ...overrides,
  };
}

/** The 4030's real auto seed: three trenches plus the concentric channel. */
function seed(): PartFeature[] {
  return [
    makeFeature({ id: "trench-01", azimuthDeg: -22.5, radiusMm: 1.47 }),
    makeFeature({ id: "trench-02", azimuthDeg: 1.0, radiusMm: 1.43 }),
    makeFeature({ id: "trench-03", azimuthDeg: 72.2, radiusMm: 1.43 }),
    makeFeature({ id: "channel", kind: "channel", azimuthDeg: -170.5, radiusMm: 0.03, definesRotation: false }),
  ];
}

describe("draftsFrom", () => {
  it("adopts a server annotation unchanged, with local keys and no pending clicks", () => {
    const drafts = draftsFrom(seed());
    expect(drafts.map((d) => d.key)).toEqual(["draft-1", "draft-2", "draft-3", "draft-4"]);
    expect(drafts.map((d) => d.id)).toEqual(["trench-01", "trench-02", "trench-03", "channel"]);
    expect(drafts.every((d) => d.point === null)).toBe(true);
    expect(drafts[0]?.azimuthDeg).toBe(-22.5);
  });
});

describe("readClick", () => {
  it("reads azimuth/radius about the FITTED rim centre, not the frame origin", () => {
    // A click 2mm along +y from a rim centre at (0.4, -0.3) reads 90°, r 2 — measuring about
    // the origin instead would give a different angle AND a different lever arm.
    const read = readClick([0.4, 1.7, 1.8], [0.4, -0.3]);
    expect(read.azimuthDeg).toBeCloseTo(90, 10);
    expect(read.radiusMm).toBeCloseTo(2, 10);
    expect(read.zMm).toBe(1.8);
  });
});

describe("placeDraft", () => {
  const read = { azimuthDeg: 45, radiusMm: 1.9, zMm: 1.8 };

  it("APPENDS when nothing is selected", () => {
    const drafts = draftsFrom(seed());
    const next = placeDraft(
      drafts,
      { point: [1, 1, 1], kind: "trench", key: draftKey(9) },
      read,
      null,
    );
    expect(next).toHaveLength(5);
    expect(next[4]?.key).toBe("draft-9");
    expect(next[4]?.azimuthDeg).toBe(45);
    expect(next[4]?.point).toEqual([1, 1, 1]);
    expect(next[4]?.source).toBe("operator");
  });

  it("MOVES the selected mark in place — same slot, same key, same kind", () => {
    const drafts = draftsFrom(seed());
    const next = placeDraft(
      drafts,
      { point: [1, 1, 1], kind: "notch", key: draftKey(9) },
      read,
      "draft-2",
    );
    expect(next).toHaveLength(4);
    expect(next[1]?.key).toBe("draft-2");
    // the kind belongs to the mark being corrected, not to the "new mark" picker
    expect(next[1]?.kind).toBe("trench");
    expect(next[1]?.azimuthDeg).toBe(45);
    expect(next[1]?.point).toEqual([1, 1, 1]);
    // a moved mark is the operator's now, and its id is the SERVER's to re-derive
    expect(next[1]?.source).toBe("operator");
    expect(next[1]?.id).toBeNull();
    // every other mark is untouched
    expect(next[0]).toEqual(drafts[0]);
    expect(next[2]).toEqual(drafts[2]);
  });

  it("appends when the selected key no longer exists (it was removed under the armed click)", () => {
    const drafts = draftsFrom(seed());
    const next = placeDraft(drafts, { point: [1, 1, 1], kind: "trench", key: "draft-9" }, read, "gone");
    expect(next).toHaveLength(5);
  });

  it("refuses to append past the server's own cap, leaving the list unchanged", () => {
    const full: DraftFeature[] = Array.from({ length: MAX_PART_FEATURES }, (_, i) => ({
      key: draftKey(i + 1),
      kind: "trench",
      azimuthDeg: i * 10,
      radiusMm: 1.5,
      zMm: 1.8,
      source: "operator",
      id: null,
      point: null,
    }));
    const next = placeDraft(full, { point: [1, 1, 1], kind: "trench", key: "draft-99" }, read, null);
    expect(next).toHaveLength(MAX_PART_FEATURES);
    expect(next.map((d) => d.key)).toEqual(full.map((d) => d.key));
    // ...but a MOVE is still allowed at the cap: it does not grow the list
    const moved = placeDraft(full, { point: [1, 1, 1], kind: "trench", key: "draft-99" }, read, "draft-3");
    expect(moved).toHaveLength(MAX_PART_FEATURES);
    expect(moved[2]?.azimuthDeg).toBe(45);
  });
});

describe("removeDraft / draftCounts / annotationStateLine", () => {
  it("removes by local key only", () => {
    const drafts = draftsFrom(seed());
    expect(removeDraft(drafts, "draft-2").map((d) => d.id)).toEqual([
      "trench-01",
      "trench-03",
      "channel",
    ]);
  });

  it("counts machine vs human marks and states them with the variant", () => {
    const drafts = placeDraft(
      draftsFrom(seed()).slice(0, 2),
      { point: [1, 1, 1], kind: "trench", key: "draft-9" },
      { azimuthDeg: 120, radiusMm: 1.5, zMm: 1.8 },
      null,
    );
    expect(draftCounts(drafts)).toEqual({ auto: 2, operator: 1 });
    expect(annotationStateLine("6020", drafts)).toBe("6020 · 3 features (2 auto, 1 operator)");
  });

  it("uses the singular for a lone mark", () => {
    expect(annotationStateLine("4020", draftsFrom([makeFeature()]))).toBe(
      "4020 · 1 feature (1 auto, 0 operator)",
    );
  });
});

describe("featureLabel", () => {
  it("names the mark, its signed azimuth and its lever arm", () => {
    expect(featureLabel({ id: "trench-03", kind: "trench", azimuthDeg: 72.2, radiusMm: 1.43 })).toBe(
      "trench-03 · +72.2° · r 1.43mm",
    );
    expect(featureLabel({ id: null, kind: "notch", azimuthDeg: -12.34, radiusMm: 2 })).toBe(
      "notch · -12.3° · r 2.00mm",
    );
  });
});

describe("draftDefinesRotation", () => {
  it("refuses a concentric mark as a rotation anchor — it names the axis, not a clock angle", () => {
    const drafts = draftsFrom(seed());
    expect(draftDefinesRotation(drafts[0] as DraftFeature)).toBe(true);
    expect(draftDefinesRotation(drafts[3] as DraftFeature)).toBe(false); // channel, r 0.03mm
  });
});

describe("draftsAreDirty", () => {
  it("is false for an untouched load — reloading the same annotation is not an edit", () => {
    const features = seed();
    expect(draftsAreDirty(draftsFrom(features), features)).toBe(false);
  });

  it("is true once a mark is added, removed, or moved", () => {
    const features = seed();
    const drafts = draftsFrom(features);
    expect(draftsAreDirty(removeDraft(drafts, "draft-1"), features)).toBe(true);
    expect(
      draftsAreDirty(
        placeDraft(drafts, { point: [1, 1, 1], kind: "trench", key: "draft-9" }, { azimuthDeg: 45, radiusMm: 1.9, zMm: 1.8 }, "draft-1"),
        features,
      ),
    ).toBe(true);
  });

  it("is true for a fresh click even at an identical azimuth — the server may snap it", () => {
    const features = seed();
    const drafts = draftsFrom(features);
    const sameSpot = placeDraft(
      drafts,
      { point: [1, 1, 1], kind: "trench", key: "draft-9" },
      { azimuthDeg: -22.5, radiusMm: 1.47, zMm: 1.81 },
      "draft-1",
    );
    expect(draftsAreDirty(sameSpot, features)).toBe(true);
  });
});

describe("toFeatureInputs", () => {
  it("sends a fresh click as a POINT and an untouched mark as its azimuth — never both", () => {
    const drafts = placeDraft(
      draftsFrom(seed()),
      { point: [1.2, 0.4, 1.8], kind: "trench", key: "draft-9" },
      { azimuthDeg: 45, radiusMm: 1.9, zMm: 1.8 },
      null,
    );
    const inputs = toFeatureInputs(drafts);
    expect(inputs).toHaveLength(5);
    for (const input of inputs) {
      expect((input.point === null) !== (input.azimuthDeg === null)).toBe(true);
    }
    expect(inputs[0]).toEqual({ kind: "trench", azimuthDeg: -22.5, point: null });
    expect(inputs[3]).toEqual({ kind: "channel", azimuthDeg: -170.5, point: null });
    expect(inputs[4]).toEqual({ kind: "trench", azimuthDeg: null, point: [1.2, 0.4, 1.8] });
  });

  it("preserves list order — the stored marks read in the order the operator placed them", () => {
    const drafts = draftsFrom(seed());
    expect(toFeatureInputs(drafts).map((i) => i.azimuthDeg)).toEqual([-22.5, 1.0, 72.2, -170.5]);
  });
});
