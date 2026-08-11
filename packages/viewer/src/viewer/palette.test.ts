/**
 * THE CAP-CROP COLOR (§10-AO, client 2026-08-06: "the scanned healing cap renders white").
 * Panes 2/3's tight cap crop must read bone-white — never pure white (kills Lambert
 * shading) and never the whole-arch tan (PALETTE.arch), which those surfaces keep.
 */
import { describe, expect, it } from "vitest";
import { CAP_SCAN_COLOR, PALETTE, capScanHex } from "./palette";

describe("CAP_SCAN_COLOR — bone-white, not pure white", () => {
  it("is the pinned bone-white hex", () => {
    // brightened one step 2026-08-10 ("we need more glossy white here")
    expect(CAP_SCAN_COLOR).toBe(0xf7f6f2);
  });

  it("is not pure white — Lambert shading needs value headroom to shade into", () => {
    expect(CAP_SCAN_COLOR).not.toBe(0xffffff);
  });

  it("is distinct from the whole-arch tan the arch surfaces keep", () => {
    expect(CAP_SCAN_COLOR).not.toBe(PALETTE.arch);
  });

  it("serves the same hex through its CSS accessor, for legend swatches", () => {
    expect(capScanHex()).toBe("#f7f6f2");
  });
});
