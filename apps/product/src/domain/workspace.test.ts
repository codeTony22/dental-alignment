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
    expect(paneLinkLabel(true)).toBe("⛓ rotating together");
    expect(paneLinkLabel(false)).toBe("⛓ link panes");
  });
});
