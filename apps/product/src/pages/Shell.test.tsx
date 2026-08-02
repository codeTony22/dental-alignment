/**
 * THE WAY HOME (client, 2026-07-27: "There is no option to go back to home and see all
 * cases"). A link did exist — in the case header's far corner, labelled "Next case — back to
 * the worklist" — but the first thing anyone tries is the wordmark, and it was inert, while
 * the label led with an action about a DIFFERENT case. These tests pin the affordance so it
 * can never quietly become a span again.
 *
 * IT MOVED ON 2026-08-02, and the tests moved with it rather than being deleted. The client
 * saw TWO nav bars on a case route — the brand bar and the case band beneath it — and asked
 * for one, with the way home in the same bar as the stages. A case route therefore no longer
 * renders this header at all, and `CaseShellView` carries "All cases" in the band beside the
 * rail; that the link EXISTS on a case route is pinned in CaseShell.test.tsx. What is pinned
 * here is the other half of the bargain: suppressing the header must not leave a route with
 * no way out.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { Shell } from "./Shell";

function render(location: string): string {
  return renderToStaticMarkup(
    <StaticRouter location={location}>
      <Shell />
    </StaticRouter>,
  );
}

describe("Shell — the way home", () => {
  it("carries the wordmark and All cases on the worklist — never a dead end", () => {
    const html = render("/");
    expect(html).toContain('data-role="home"');
    expect(html).toContain('data-role="all-cases"');
    expect(html).toContain("rTech");
  });

  it("makes the wordmark a link, not a span", () => {
    const html = render("/");
    expect(html).toMatch(
      /<a[^>]*href="\/"[^>]*data-role="home"|data-role="home"[^>]*href="\/"/,
    );
  });

  it("carries it on the other non-case routes too — /terms is reachable from Deliver", () => {
    expect(render("/terms")).toContain('data-role="all-cases"');
  });

  it("renders NO brand bar on a case route — the case band is the only nav there", () => {
    /* THE CLIENT'S ASK (2026-08-02): "There are two nav bars, take off the ArTech
       Software Labs". Two stacked dark bands read as two navigations for one page, and
       the second one already carried the case's own identity and its stages. The band
       takes the way home with it — see CaseShell.test.tsx. */
    const html = render("/case/case-a/declare");
    expect(html).not.toContain("app-header");
    expect(html).not.toContain('data-role="home"');
    expect(html).not.toContain('data-role="all-cases"');
  });
});
