/**
 * THE PANE WORKSPACE'S SHARED POLICY. The link mechanism is the viewer package's;
 * what this app decides is the OPENING state and the words on the toggle.
 */
import { describe, expect, it } from "vitest";
import { PANES_OPEN_LINKED, paneLinkLabel } from "./workspace";

describe("the pane link", () => {
  it("opens LINKED — the built toggle was reported missing because it opened off", () => {
    // client 2026-08-04; both stages import this one constant, so they cannot
    // open in different moods
    expect(PANES_OPEN_LINKED).toBe(true);
  });

  it("the toggle says the state it is in and the act it offers", () => {
    // Condensed 2026-08-05 (client, live-testing: "condense this buttons in
    // adjustments tab it takes a lot of space") — "rotating together" was the
    // longest word on the toolbar's control row. The button's own `title` still
    // carries the full sentence ("Rotate all three panels together (same angles
    // and zoom, each around its own content)"), so the word dropped from the
    // label is not lost, only moved off the row.
    expect(paneLinkLabel(true)).toBe("⛓ linked");
    expect(paneLinkLabel(false)).toBe("⛓ link panes");
  });
});
