/**
 * The product shell's one promise for slice 0b (plan §7 slice 0): the app EXISTS, names
 * itself, and is wired at the BFF — nothing else. renderToStaticMarkup in a node
 * environment, the repo's component-test convention (apps/web precedent): effects do not
 * run, so the /health fetch never fires in tests and the markup shows the pre-flight
 * "checking" state honestly.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { App, healthLabel } from "./App";

describe("the product shell", () => {
  it("names the product app", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("ArTech — Case Flow");
  });

  it("shows the BFF probe in its pre-flight state (effects do not run statically)", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("checking BFF");
  });
});

describe("healthLabel — the pure mapping the shell renders from", () => {
  it("maps every probe state to operator words", () => {
    expect(healthLabel({ kind: "checking" })).toBe("checking BFF…");
    expect(healthLabel({ kind: "up", service: "bff" })).toBe("BFF up (bff)");
    expect(healthLabel({ kind: "down", detail: "fetch failed" })).toBe(
      "BFF unreachable — fetch failed",
    );
  });
});
