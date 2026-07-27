/**
 * Static-markup tests for the header (node env, repo convention): the Library button is
 * ALWAYS rendered — never gated on a case — and reads as a toggle while the browser is open.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Header } from "./Header";

describe("Header — Library button", () => {
  it("renders the always-visible Library toggle alongside the brand", () => {
    const html = renderToStaticMarkup(
      <Header libraryOpen={false} onToggleLibrary={() => undefined} />,
    );
    expect(html).toContain(">Library</button>");
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain("rTech");
  });

  it("reads pressed/active while the browser panel is open", () => {
    const html = renderToStaticMarkup(
      <Header libraryOpen={true} onToggleLibrary={() => undefined} />,
    );
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("app-header__library-button--active");
  });
});
