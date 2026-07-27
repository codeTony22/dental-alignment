/**
 * THE CLAMP NOTICE (client, 2026-07-25): "it must be impossible to miss — this is a change to
 * what the lab asked for."
 *
 * Pinned here: both numbers are always printed together (a lone "0.06 applied" would read as the
 * request), the reason rides along when the backend gave one, an unclamped run renders NOTHING
 * (a standing "no clamp" line trains the eye to skip the spot the real one appears in), and the
 * notice is an alert rather than a status so a screen reader announces it.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReliefClampNotice } from "./ReliefClampNotice";
import type { SiteReliefClamp } from "../domain/reliefClamp";

const CLAMP: SiteReliefClamp = {
  tooth: 3,
  requestedMm: 0.2,
  appliedMm: 0.06,
  limitMm: 0.06,
  minWallMm: 0.5,
  reason: null,
};

describe("ReliefClampNotice", () => {
  it("renders nothing when nothing was clamped", () => {
    expect(renderToStaticMarkup(<ReliefClampNotice clamps={[]} />)).toBe("");
  });

  it("prints BOTH numbers and the reason the ceiling exists", () => {
    const html = renderToStaticMarkup(<ReliefClampNotice clamps={[CLAMP]} />);
    expect(html).toContain("0.20 mm requested");
    expect(html).toContain("0.06 mm applied");
    expect(html).toContain("without thinning the channel wall below 0.50 mm");
    expect(html).toContain("Tooth 3");
  });

  it("announces itself as an alert, not a quiet status", () => {
    const html = renderToStaticMarkup(<ReliefClampNotice clamps={[CLAMP]} />);
    expect(html).toContain('role="alert"');
  });

  it("names every clamped tooth in the headline", () => {
    const html = renderToStaticMarkup(
      <ReliefClampNotice clamps={[CLAMP, { ...CLAMP, tooth: 14, appliedMm: 0.1 }]} />,
    );
    expect(html).toContain("reduced on teeth 3 and 14");
    expect(html).toContain("0.10 mm applied");
  });

  it("shows the backend's own reason verbatim when it gave one", () => {
    const html = renderToStaticMarkup(
      <ReliefClampNotice clamps={[{ ...CLAMP, reason: "channel wall would fall to 0.10mm" }]} />,
    );
    expect(html).toContain("channel wall would fall to 0.10mm");
  });

  it("keeps the numbers in the compact tone, and drops only the explanatory tail", () => {
    const html = renderToStaticMarkup(<ReliefClampNotice clamps={[CLAMP]} tone="compact" />);
    expect(html).toContain("0.20 mm requested");
    expect(html).toContain("0.06 mm applied");
    expect(html).not.toContain("Lower the requested relief");
  });

  it("explains, in the banner tone, that nothing was silently substituted", () => {
    const html = renderToStaticMarkup(<ReliefClampNotice clamps={[CLAMP]} />);
    expect(html).toContain("Nothing was silently substituted");
  });
});
