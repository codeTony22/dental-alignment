/**
 * The SCAN-SIDE correspondence domain (client ask 2026-07-24, half two): which part a run row
 * names, which features may anchor a rotation, the one-feature-one-place pair rules, and the
 * outcome copy — including the tautology guard on a single pair ("your marks agree to 0.00mm"
 * would dress a construction up as a measurement).
 */
import { describe, expect, it } from "vitest";
import type { AlignToCorrespondenceResult, CorrespondencePair } from "./correspondence";
import {
  MAX_CORRESPONDENCE_PAIRS,
  anchorableFeatures,
  canAddFreePoint,
  canAddPair,
  describeCorrespondence,
  featurePair,
  freePair,
  freePointNumber,
  pairKey,
  pairLabel,
  residualLabel,
  sitePartKey,
  unpairedFeatures,
  withPair,
  withoutPair,
} from "./correspondence";
import type { PartFeature } from "./partFeatures";

function feature(id: string, azimuthDeg: number, radiusMm = 2.0): PartFeature {
  return {
    id,
    kind: "trench",
    azimuthDeg,
    radiusMm,
    zMm: 1.8,
    source: "auto",
    definesRotation: radiusMm >= 0.5,
  };
}

/** The 7030's real seed: three trenches plus the concentric channel. */
const FEATURES: PartFeature[] = [
  feature("trench-01", -177.0, 2.06),
  feature("trench-02", -136.0, 2.08),
  feature("trench-03", -0.1, 2.0),
  { ...feature("channel", -173.1, 0.03), kind: "channel", definesRotation: false },
];

describe("sitePartKey", () => {
  it("splits a run row's spec on the IDENTIFIED variant, keeping hyphenated model names whole", () => {
    expect(sitePartKey("zimmer-4.5-7030", "7030")).toEqual({ model: "zimmer-4.5", variant: "7030" });
    expect(sitePartKey("neodent-gm-5020", "5020")).toEqual({ model: "neodent-gm", variant: "5020" });
  });

  it("falls back to the last hyphen when the spec does not end with the identified variant", () => {
    // legacy cached row: the row's identified variant disagrees with the shipped spec label
    expect(sitePartKey("neodent-gm-4030", "")).toEqual({ model: "neodent-gm", variant: "4030" });
    expect(sitePartKey("neodent-gm-4030", "6020")).toEqual({ model: "neodent-gm", variant: "4030" });
  });

  it("returns null rather than naming a part it cannot read", () => {
    expect(sitePartKey("mystery", "")).toBeNull();
    expect(sitePartKey("-7030", "")).toBeNull();
    expect(sitePartKey("zimmer-", "")).toBeNull();
    expect(sitePartKey("", "")).toBeNull();
  });
});

describe("anchorableFeatures / unpairedFeatures / canAddPair", () => {
  it("drops the concentric bore — it names the axis, not a clock angle", () => {
    expect(anchorableFeatures(FEATURES).map((f) => f.id)).toEqual([
      "trench-01",
      "trench-02",
      "trench-03",
    ]);
  });

  it("offers only features not already paired", () => {
    const pairs: CorrespondencePair[] = [featurePair("trench-02", "trench", [1, 2, 3])];
    expect(unpairedFeatures(FEATURES, pairs).map((f) => f.id)).toEqual(["trench-01", "trench-03"]);
    expect(canAddPair(FEATURES, pairs)).toBe(true);
  });

  it("cannot add when every anchorable feature is paired", () => {
    const pairs: CorrespondencePair[] = anchorableFeatures(FEATURES).map((f) =>
      featurePair(f.id, f.kind, [0, 0, 0]),
    );
    expect(unpairedFeatures(FEATURES, pairs)).toEqual([]);
    expect(canAddPair(FEATURES, pairs)).toBe(false);
  });

  it("cannot add past the server's own pair cap", () => {
    const many = Array.from({ length: MAX_CORRESPONDENCE_PAIRS }, (_, i) => feature(`t-${i}`, i * 20));
    const pairs: CorrespondencePair[] = many.map((f) => featurePair(f.id, f.kind, [0, 0, 0]));
    expect(canAddPair([...many, feature("t-extra", 200)], pairs)).toBe(false);
  });

  it("a free point never takes a feature off the board, and only the cap gates free points", () => {
    // client ask 2026-07-26: free points are their own spots on the part
    const pairs: CorrespondencePair[] = [freePair([1, 0, 2], [10, 20, 30])];
    expect(unpairedFeatures(FEATURES, pairs).map((f) => f.id)).toEqual([
      "trench-01",
      "trench-02",
      "trench-03",
    ]);
    expect(canAddFreePoint(pairs)).toBe(true);
    const full = Array.from({ length: MAX_CORRESPONDENCE_PAIRS }, (_, i) =>
      freePair([i, 0, 0], [i, 0, 0]),
    );
    expect(canAddFreePoint(full)).toBe(false);
  });
});

describe("withPair / withoutPair", () => {
  it("re-marking a feature MOVES its point rather than adding a second pair for the same id", () => {
    const first = withPair([], featurePair("trench-02", "trench", [1, 1, 1]));
    const second = withPair(first, featurePair("trench-02", "trench", [9, 9, 9]));
    expect(second).toHaveLength(1);
    expect(second[0]?.scanPoint).toEqual([9, 9, 9]);
  });

  it("keeps the order features were named in", () => {
    const pairs = withPair(
      withPair([], featurePair("trench-03", "trench", [1, 1, 1])),
      featurePair("trench-01", "trench", [2, 2, 2]),
    );
    expect(pairs.map((p) => p.featureId)).toEqual(["trench-03", "trench-01"]);
    expect(withoutPair(pairs, "trench-03").map((p) => p.featureId)).toEqual(["trench-01"]);
  });

  it("labels a recorded pair", () => {
    const pairs = [featurePair("trench-02", "trench", [0, 0, 0])];
    expect(pairLabel(pairs, 0)).toBe("trench-02 ↔ marked");
  });

  it("every free click APPENDS a new numbered point — free points are never deduplicated", () => {
    const pairs = withPair(
      withPair([], freePair([1, 0, 2], [10, 20, 30])),
      freePair([1, 0, 2], [11, 21, 31]),
    );
    expect(pairs).toHaveLength(2);
    expect(pairs.map((p) => p.featureId)).toEqual([null, null]);
  });

  it("numbers free points positionally in click order, past any feature pairs", () => {
    const pairs = [
      freePair([1, 0, 2], [10, 20, 30]),
      featurePair("trench-01", "trench", [0, 0, 0]),
      freePair([0, 1, 2], [12, 22, 32]),
    ];
    // the SAME positional numbering the server audits as "point-1"/"point-2"
    expect(freePointNumber(pairs, 0)).toBe(1);
    expect(freePointNumber(pairs, 1)).toBeNull();
    expect(freePointNumber(pairs, 2)).toBe(2);
    expect(pairKey(pairs, 0)).toBe("point-1");
    expect(pairKey(pairs, 1)).toBe("trench-01");
    expect(pairKey(pairs, 2)).toBe("point-2");
    expect(pairLabel(pairs, 0)).toBe("point 1 ↔ marked");
    expect(pairLabel(pairs, 2)).toBe("point 2 ↔ marked");
  });

  it("removes a free point by its positional key, and the survivors renumber", () => {
    const pairs = [freePair([1, 0, 2], [1, 1, 1]), freePair([0, 1, 2], [2, 2, 2])];
    const remaining = withoutPair(pairs, "point-1");
    expect(remaining).toHaveLength(1);
    expect(remaining[0]?.scanPoint).toEqual([2, 2, 2]);
    // the surviving point is now point 1 — exactly what the server would label it
    expect(pairKey(remaining, 0)).toBe("point-1");
    expect(pairLabel(remaining, 0)).toBe("point 1 ↔ marked");
  });
});

function result(overrides: Partial<AlignToCorrespondenceResult> = {}): AlignToCorrespondenceResult {
  return {
    tooth: 29,
    appliedDeltaDeg: 8.0,
    cumulativeDeg: 8.0,
    stabilityExcessMm: 0.006,
    clocking: {
      notchShiftDeg: -1.4,
      notchCorr: 0.62,
      notchProminence: 0.21,
      evidence: "codes",
      consistencyDeg: null,
      rotationUnverified: false,
    },
    nudge: { cumulativeDeg: 8.0 },
    pairs: [
      {
        featureId: "trench-01",
        featureAzimuthDeg: -177,
        clickAzimuthDeg: -167,
        deltaDeg: 10,
        residualDeg: 2,
        residualMm: 0.072,
      },
      {
        featureId: "trench-02",
        featureAzimuthDeg: -136,
        clickAzimuthDeg: -130,
        deltaDeg: 6,
        residualDeg: -2,
        residualMm: 0.073,
      },
    ],
    residualRmsMm: 0.072,
    ...overrides,
  };
}

describe("describeCorrespondence", () => {
  it("states the rotation, how well the marks agree, and the RE-READ code residual", () => {
    expect(describeCorrespondence(result())).toBe(
      "rotated +8.0° from 2 marks; your marks agree to 0.07mm; codes now read -1.4°",
    );
  });

  it("omits the agreement clause on a SINGLE pair — there is nothing to disagree with", () => {
    const single = result({
      pairs: [result().pairs[0]!],
      residualRmsMm: 0,
      appliedDeltaDeg: -38.2,
    });
    expect(describeCorrespondence(single)).toBe("rotated -38.2° from 1 mark; codes now read -1.4°");
  });

  it("says so honestly when the code reader has no signal at the new pose", () => {
    const blind = result({
      clocking: { ...result().clocking, notchShiftDeg: null, evidence: "none" },
    });
    expect(describeCorrespondence(blind)).toContain("no code signal at this pose");
  });
});

describe("residualLabel", () => {
  it("reports the miss in degrees AND in millimetres at that feature's own radius", () => {
    expect(residualLabel(result().pairs[0]!)).toBe("trench-01 · +2.0° · 0.07mm off");
    expect(residualLabel(result().pairs[1]!)).toBe("trench-02 · -2.0° · 0.07mm off");
  });
});
