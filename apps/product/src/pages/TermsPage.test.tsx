/**
 * The terms page's contract: it renders the version it resolved and says PLACEHOLDER
 * when the server says so — the surface never decides for itself whether a document
 * it received is binding.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TermsView } from "./TermsPage";

const PLACEHOLDER = {
  version: "placeholder-v1",
  title: "Terms and Conditions",
  status: "placeholder",
  body: "PLACEHOLDER — pending the client's final Terms and Conditions text.",
};

describe("the terms page", () => {
  it("names the version it resolved, so a sealed record can be read back", () => {
    const html = renderToStaticMarkup(<TermsView document={PLACEHOLDER} />);
    expect(html).toContain('data-role="terms-version"');
    expect(html).toContain("placeholder-v1");
    expect(html).toContain('data-role="terms-body"');
  });

  it("says PLACEHOLDER because the SERVER said so, not because it guessed", () => {
    const html = renderToStaticMarkup(<TermsView document={PLACEHOLDER} />);
    expect(html).toContain('data-role="terms-status"');
    // the apostrophe arrives HTML-escaped from renderToStaticMarkup
    expect(html).toContain("this is not the client");
    expect(html).toContain("final Terms and Conditions text");
  });

  it("a real document carries no placeholder banner", () => {
    const real = { ...PLACEHOLDER, status: "current", body: "Real terms." };
    const html = renderToStaticMarkup(<TermsView document={real} />);
    expect(html).not.toContain('data-role="terms-status"');
    expect(html).toContain("Real terms.");
  });
});
