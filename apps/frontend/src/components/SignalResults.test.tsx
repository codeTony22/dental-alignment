import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SIGNAL_GROUP_ORDER } from "../domain/signals";
import { techniqueResult } from "../testing/fixtures";
import { SignalResults } from "./SignalResults";

describe("SignalResults", () => {
  it("renders every taxonomy group from a served fixture", () => {
    const html = renderToStaticMarkup(
      <SignalResults result={techniqueResult("intelligence")} error={null} />,
    );
    expect(html).toContain('data-role="technique-results"');
    for (const name of SIGNAL_GROUP_ORDER) {
      expect(html).toContain(`data-signal-group="${name}"`);
    }
    expect(html).toContain("get_site_signals");
    expect(html).toContain("dry_run_best_fit");
    expect(html).toContain("Surface deviation map");
    expect(html).toContain("The cap&#x27;s ROTATION could not be verified.");
  });

  it("renders a refusal without dropping the empty-state copy", () => {
    const html = renderToStaticMarkup(
      <SignalResults result={null} error="the refinement left the trust region" />,
    );
    expect(html).toContain('data-role="technique-error"');
    expect(html).toContain("trust region");
    expect(html).not.toContain('data-role="technique-empty"');
  });
});
