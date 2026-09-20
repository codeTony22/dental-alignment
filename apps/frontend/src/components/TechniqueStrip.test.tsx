import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TechniqueStrip } from "./TechniqueStrip";

describe("TechniqueStrip", () => {
  it("renders both modes and marks the active one", () => {
    const html = renderToStaticMarkup(
      <TechniqueStrip
        mode="intelligence"
        onChangeMode={() => undefined}
        onRun={() => undefined}
        busy={false}
        disabled={false}
      />,
    );
    expect(html).toContain('data-role="technique-mode"');
    expect(html).toContain('data-mode="deterministic"');
    expect(html).toContain('data-mode="intelligence"');
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("Intelligence");
    expect(html).toContain("Try technique");
    expect(html).toContain("MCP tool surface");
  });
});
