/**
 * THE CAP-CROP COLOR — one colour, one home. §10-AO (client 2026-08-06) made the
 * pane crop bone-white; §10-AS.5 (client 2026-08-10, over a Delivery screenshot:
 * "this should be the color of the scan panels in the middle") reversed it — the
 * crop wears PALETTE.arch itself, so a future retune of the scan tone follows
 * automatically. The separate CAP_SCAN_COLOR constant is retired; this pin
 * guards the binding's home and that the tan stays a shade Lambert can shade.
 */
import { describe, expect, it } from "vitest";
import { PALETTE, paletteHex } from "./palette";

describe("the scan tan — the panes' crop colour IS the arch colour", () => {
  it("is the pinned scan tan", () => {
    expect(PALETTE.arch).toBe(0xf2e3a6);
  });

  it("is not pure white — Lambert shading needs value headroom to shade into", () => {
    expect(PALETTE.arch).not.toBe(0xffffff);
  });

  it("serves the same hex through its CSS accessor, for legend swatches", () => {
    expect(paletteHex("arch")).toBe("#f2e3a6");
  });
});
