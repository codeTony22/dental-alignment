import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiClient } from "./api/client";
import { App } from "./App";
import { SIGNAL_GROUP_ORDER } from "./domain/signals";
import { CASES, servedFetch, signalEnvelope, techniqueResult } from "./testing/fixtures";

describe("App bindings", () => {
  it("exposes the technique strip and adjust dock against served fixtures", () => {
    const client = new ApiClient(servedFetch({
      "GET /api/v1/cases": { cases: CASES },
      "GET /api/v1/cases/neodent-gm/sites/4/signals": signalEnvelope(),
    }));
    const html = renderToStaticMarkup(<App client={client} />);
    expect(html).toContain('data-role="technique-strip"');
    expect(html).toContain('data-role="alignment-strip"');
    expect(html).toContain('data-role="adjust-dock"');
    expect(html).toContain('data-mode="deterministic"');
    expect(html).toContain('data-mode="intelligence"');
    expect(html).toContain("Fit by points");
  });

  it("fixture technique results keep the full group set", () => {
    const result = techniqueResult("deterministic");
    expect(result.signal_groups).toEqual(SIGNAL_GROUP_ORDER);
    expect(result.signals_after.group_names).toEqual(SIGNAL_GROUP_ORDER);
  });
});
