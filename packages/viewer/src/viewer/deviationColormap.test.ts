/**
 * THE DEVIATION RAMP — one colour language for the union mesh and its colorbar.
 *
 * What is pinned here is what a doctor reads off the picture: blue is negative (scan inside the
 * cap), red is positive (scan outside it), the middle is near-white, everything past the clamp
 * saturates rather than wrapping, and an UNMEASURED vertex is grey — never a colour that would
 * read as "perfect fit" where the instrument had no scan surface to measure against.
 */
import { describe, expect, it } from "vitest";
import {
  CONTACTS_MAX_MM,
  UNMEASURED_COLOR_HEX,
  buildDeviationColors,
  buildScaleColors,
  clampNoteFor,
  contactsColorSrgb,
  contactsFraction,
  contactsGradientCss,
  contactsTickLabels,
  deviationColorSrgb,
  deviationFraction,
  deviationGradientCss,
  deviationTickLabels,
  rampSrgb255,
  srgbToLinear,
} from "./deviationColormap";

/** Rough channel dominance test — the ramp's ends are unmistakably blue and red. */
function channels(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

describe("deviationFraction", () => {
  it("maps -clamp..+clamp onto 0..1 with 0 in the middle", () => {
    expect(deviationFraction(-0.5, 0.5)).toBe(0);
    expect(deviationFraction(0, 0.5)).toBe(0.5);
    expect(deviationFraction(0.5, 0.5)).toBe(1);
  });

  it("saturates past the clamp instead of wrapping (real sites span ±4mm)", () => {
    expect(deviationFraction(-4.61, 0.5)).toBe(0);
    expect(deviationFraction(4.25, 0.5)).toBe(1);
  });
});

describe("deviationColorSrgb", () => {
  it("reads blue negative, red positive, near-white at agreement", () => {
    const [nr, , nb] = channels(deviationColorSrgb(-0.5, 0.5));
    expect(nb).toBeGreaterThan(nr); // blue end
    const [pr, , pb] = channels(deviationColorSrgb(0.5, 0.5));
    expect(pr).toBeGreaterThan(pb); // red end
    const [zr, zg, zb] = channels(deviationColorSrgb(0, 0.5));
    expect(Math.min(zr, zg, zb)).toBeGreaterThan(230); // near-white middle
  });

  it("paints an unmeasured vertex grey — never a ramp colour", () => {
    expect(deviationColorSrgb(null, 0.5)).toBe(UNMEASURED_COLOR_HEX);
    expect(deviationColorSrgb(Number.NaN, 0.5)).toBe(UNMEASURED_COLOR_HEX);
    expect(deviationColorSrgb(0, 0.5)).not.toBe(UNMEASURED_COLOR_HEX);
  });

  it("emits well-formed hex at every sampled point", () => {
    for (let i = 0; i <= 20; i += 1) {
      const mm = -0.5 + (i / 20) * 1.0;
      expect(deviationColorSrgb(mm, 0.5)).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it("interpolates between stops rather than stepping", () => {
    const a = rampSrgb255(0.05);
    const lower = rampSrgb255(0);
    const upper = rampSrgb255(0.1);
    expect(a[0]).toBeGreaterThan(Math.min(lower[0], upper[0]) - 1e-9);
    expect(a[0]).toBeLessThan(Math.max(lower[0], upper[0]) + 1e-9);
    expect(a).not.toEqual(lower);
  });
});

describe("buildDeviationColors", () => {
  it("emits three LINEAR floats per point, in point order", () => {
    const colors = buildDeviationColors([-0.5, 0, 0.5], 0.5);
    expect(colors).toHaveLength(9);
    for (const v of colors) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
    // the middle point is the near-white stop, brighter than either end in every channel
    expect(colors[3]).toBeGreaterThan(colors[0] as number);
    expect(colors[5]).toBeGreaterThan(colors[8] as number);
  });

  it("converts sRGB to linear (a mid-grey must NOT stay 0.5)", () => {
    expect(srgbToLinear(0)).toBe(0);
    expect(srgbToLinear(255)).toBeCloseTo(1, 6);
    expect(srgbToLinear(128)).toBeLessThan(0.25);
  });

  it("greys the null readings and leaves the measured ones ramped", () => {
    const colors = buildDeviationColors([null, 0.5], 0.5);
    const grey = srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(1, 3), 16));
    expect(colors[0]).toBeCloseTo(grey, 6);
    expect(colors[3]).not.toBeCloseTo(grey, 3);
  });
});

describe("the colorbar", () => {
  it("builds a left-to-right gradient from the same ramp", () => {
    const css = deviationGradientCss();
    expect(css.startsWith("linear-gradient(to right, ")).toBe(true);
    expect(css).toContain("0%");
    expect(css).toContain("100%");
    // the bar's ends must be the ramp's ends, so bar and mesh cannot drift apart
    expect(css).toContain(deviationColorSrgb(-1, 1));
    expect(css).toContain(deviationColorSrgb(1, 1));
  });

  it("labels the ticks with explicit signs — the sign IS the clinical meaning", () => {
    expect(deviationTickLabels(0.5)).toEqual(["−0.50", "−0.25", "0", "+0.25", "+0.50"]);
  });

  it("says so when the data runs past the clamp, and stays quiet when it does not", () => {
    expect(clampNoteFor(-4.6093, 4.2481, 0.5)).toBe("clamped — this site spans -4.61 to +4.25 mm");
    expect(clampNoteFor(-0.3, 0.4, 0.5)).toBeNull();
    expect(clampNoteFor(null, null, 0.5)).toBeNull();
  });
});

/**
 * THE "CONTACTS" SCALE (the client's own, offered alongside ours). The behaviour that matters:
 * it is ABSOLUTE — +0.3 and −0.3 paint identically, which is precisely why the signed scale
 * stays on offer and the selector says which is which.
 */
describe("the Contacts scale", () => {
  it("is absolute: equal magnitudes of either sign paint the same", () => {
    expect(contactsColorSrgb(0.3, CONTACTS_MAX_MM)).toBe(contactsColorSrgb(-0.3, CONTACTS_MAX_MM));
    expect(contactsFraction(-0.3, 0.6)).toBeCloseTo(0.5, 6);
  });

  it("puts agreement at the bottom of the bar and saturates past the top", () => {
    expect(contactsFraction(0, 0.6)).toBe(0);
    expect(contactsFraction(0.6, 0.6)).toBe(1);
    expect(contactsFraction(4.2, 0.6)).toBe(1);
    expect(contactsColorSrgb(4.2, 0.6)).toBe(contactsColorSrgb(0.6, 0.6));
  });

  it("still refuses to paint an unread vertex as agreement", () => {
    expect(contactsColorSrgb(null, CONTACTS_MAX_MM)).toBe(UNMEASURED_COLOR_HEX);
    const colors = buildScaleColors("contacts", [null, 0.3], CONTACTS_MAX_MM);
    const grey = srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(1, 3), 16));
    expect(colors[0]).toBeCloseTo(grey, 6);
    expect(colors[3]).not.toBeCloseTo(grey, 3);
  });

  it("labels its ticks WITHOUT signs — this scale has none", () => {
    expect(contactsTickLabels(CONTACTS_MAX_MM)).toEqual(["0.00", "0.15", "0.30", "0.45", "0.60"]);
  });

  it("builds its bar from the same ramp the mesh uses", () => {
    const css = contactsGradientCss();
    expect(css.startsWith("linear-gradient(to right, ")).toBe(true);
    expect(css).toContain(contactsColorSrgb(0, 1));
    expect(css).toContain(contactsColorSrgb(1, 1));
  });

  it("routes each scale id to its own ramp — one entry point, no drift", () => {
    const signed = buildScaleColors("signed", [0.3], 0.5);
    const contacts = buildScaleColors("contacts", [0.3], 0.5);
    expect(Array.from(signed)).not.toEqual(Array.from(contacts));
    expect(Array.from(signed)).toEqual(Array.from(buildDeviationColors([0.3], 0.5)));
  });
});
