import { describe, expect, it } from "vitest";
import { existsSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Cheap wiring guard: confirms `pnpm build:standalone` actually produced the one self-contained
// file the Python emitter reads at case-emit time, and that it still contains the window.__CASE__
// wiring this whole bundle depends on. Run `pnpm build:standalone` before `pnpm test` for this
// to pass — see apps/web/package.json.
const DIST_PATH = fileURLToPath(new URL("../dist/standalone-viewer.iife.js", import.meta.url));

describe("standalone-viewer.iife.js build output", () => {
  it("exists at the path the emitter will read (viewer-standalone/dist/standalone-viewer.iife.js)", () => {
    expect(existsSync(DIST_PATH), `Expected ${DIST_PATH} to exist — run 'pnpm build:standalone' first.`).toBe(
      true,
    );
  });

  it("is a non-trivial single file (not an empty or stub build)", () => {
    const stats = statSync(DIST_PATH);
    expect(stats.size).toBeGreaterThan(10_000);
  });

  it("references window.__CASE__ (the emitter's wiring contract)", () => {
    const content = readFileSync(DIST_PATH, "utf-8");
    expect(content).toContain("__CASE__");
  });

  it("is a self-executing IIFE with no import/export statements (fully inlined, no externals)", () => {
    const content = readFileSync(DIST_PATH, "utf-8");
    expect(content.startsWith("(function(")).toBe(true);
    // A leftover bare `import `/`export ` statement would mean something wasn't inlined and the
    // file would fail to run standalone via file://.
    expect(content).not.toMatch(/^import /m);
    expect(content).not.toMatch(/^export /m);
  });
});
