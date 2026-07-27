/**
 * The SITE STEPPER — '‹ n ›' across the case's marked sites plus the overview list ("1 — 6020").
 * Pinned: the position read-out, the ends being disabled rather than wrapping, the per-site
 * REVIEW state (the thing the Process gate counts, not the selection state), and the honest
 * empty state for a case with nothing marked yet.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SiteStepper, siteOverviewLabel } from "./SiteStepper";
import type { SiteSelection } from "../domain/librarySelection";

const SITES: SiteSelection[] = [
  { tooth: 3, variantId: "6020", reviewed: true },
  { tooth: 29, variantId: null, reviewed: false },
];

describe("siteOverviewLabel", () => {
  it("reads '1 — 6020', and says so when no cap is chosen", () => {
    expect(siteOverviewLabel(SITES[0] as SiteSelection, 0)).toBe("1 — 6020");
    expect(siteOverviewLabel(SITES[1] as SiteSelection, 1)).toBe("2 — no cap chosen");
  });

  it("keeps an archived id qualified, so two same-numbered caps cannot look identical", () => {
    expect(
      siteOverviewLabel({ tooth: 5, variantId: "superseded-2026-07-13--5020", reviewed: false }, 0),
    ).toBe("1 — superseded-2026-07-13--5020");
  });
});

describe("SiteStepper", () => {
  it("shows the position and the active site's tooth", () => {
    const html = renderToStaticMarkup(
      <SiteStepper sites={SITES} activeIndex={0} onStep={() => {}} onSelect={() => {}} />,
    );
    expect(html).toContain("1 / 2");
    expect(html).toContain("tooth 3");
  });

  it("disables the previous step at the first site and the next at the last", () => {
    const first = renderToStaticMarkup(
      <SiteStepper sites={SITES} activeIndex={0} onStep={() => {}} onSelect={() => {}} />,
    );
    expect(first).toMatch(/disabled[^>]*aria-label="Previous site"/);
    expect(first).not.toMatch(/disabled[^>]*aria-label="Next site"/);
    const last = renderToStaticMarkup(
      <SiteStepper sites={SITES} activeIndex={1} onStep={() => {}} onSelect={() => {}} />,
    );
    expect(last).toMatch(/disabled[^>]*aria-label="Next site"/);
    expect(last).not.toMatch(/disabled[^>]*aria-label="Previous site"/);
  });

  it("lists every site with its review state, marking the current one", () => {
    const html = renderToStaticMarkup(
      <SiteStepper sites={SITES} activeIndex={1} onStep={() => {}} onSelect={() => {}} />,
    );
    expect(html).toContain("1 — 6020");
    expect(html).toContain("2 — no cap chosen");
    expect(html).toContain("decode-stepper__item--reviewed");
    expect(html).toContain("decode-stepper__item--active");
    expect(html).toContain('aria-current="true"');
  });

  it("says a case has nothing marked instead of rendering an empty stepper", () => {
    const html = renderToStaticMarkup(
      <SiteStepper sites={[]} activeIndex={0} onStep={() => {}} onSelect={() => {}} />,
    );
    expect(html).toContain("No marked sites");
    expect(html).not.toContain("Previous site");
  });
});
