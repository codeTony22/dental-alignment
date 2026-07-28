/**
 * THE WAY HOME (client, 2026-07-27: "There is no option to go back to home and see all
 * cases"). A link did exist — in the case header's far corner, labelled "Next case — back to
 * the worklist" — but the first thing anyone tries is the wordmark, and it was inert, while
 * the label led with an action about a DIFFERENT case. These tests pin both affordances on
 * every route so neither can quietly become a span again.
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
  it("makes the wordmark a link to the worklist", () => {
    const html = render("/case/case-a/deliver");
    expect(html).toContain('data-role="home"');
    expect(html).toMatch(/<a[^>]*href="\/"[^>]*data-role="home"|data-role="home"[^>]*href="\/"/);
    expect(html).toContain("rTech");
  });

  it("offers an explicit All cases link", () => {
    const html = render("/case/case-a/declare");
    expect(html).toContain('data-role="all-cases"');
    expect(html).toContain("All cases");
  });

  it("carries both on the worklist itself — never a dead end", () => {
    const html = render("/");
    expect(html).toContain('data-role="home"');
    expect(html).toContain('data-role="all-cases"');
  });
});
