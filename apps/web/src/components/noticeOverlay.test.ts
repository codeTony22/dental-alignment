/**
 * THE NOTICE OVERLAY'S POINTER CONTRACT (review 2026-07-26): the fit-by-points part pane
 * invites "click the part itself to place a free numbered point" — and the full-pane notice
 * overlay it was printed on intercepted exactly that click (and the orbit), leaving the pane
 * inert on any part whose detector anchors nothing.
 *
 * renderToStaticMarkup cannot see pointer interception and this suite has no jsdom, so the
 * stylesheet is pinned as text — crude, but the one instrument here that catches the
 * regression. Read with node:fs (typed by src/test-node.d.ts): vitest stubs `.css?raw`
 * imports to "" in this node-env suite. Selector blocks are matched structurally
 * (declaration block per selector), not by whole-file substring.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

/** Every declaration block for a selector written exactly as `selector {` in this sheet. */
function blocks(selector: string): string[] {
  const out: string[] = [];
  let from = 0;
  for (;;) {
    const start = css.indexOf(`${selector} {`, from);
    if (start === -1) break;
    const end = css.indexOf("}", start);
    out.push(css.slice(start, end));
    from = end;
  }
  return out;
}

describe("verify-panel notice overlays — messages, never controls", () => {
  it("a notice never intercepts the pane's clicks — the invitation must stay clickable", () => {
    const notice = blocks(".verify-panel__overlay--notice");
    expect(notice.length).toBeGreaterThan(0);
    expect(notice.some((b) => b.includes("pointer-events: none"))).toBe(true);
  });

  it("the invite tone is a strip, not a full-pane veil over the mesh it asks to click", () => {
    const invite = blocks(".verify-panel__overlay--invite");
    expect(invite.length).toBeGreaterThan(0);
    // `inset: auto …` pins it to an edge instead of the base class's `inset: 0` cover
    expect(invite.some((b) => b.includes("inset: auto"))).toBe(true);
  });

  it("the busy overlay keeps blocking — a pane mid-request has nothing safe to click", () => {
    for (const block of blocks(".verify-panel__overlay")) {
      expect(block).not.toContain("pointer-events");
    }
  });
});
