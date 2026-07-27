/**
 * THE CLIENT'S FOURTH ASK, PINNED (2026-07-26): "'Fit by points' must be present after
 * processing … it must be discoverable without hunting."
 *
 * The correspondence endpoints shipped on 2026-07-24 and the client reported the feature
 * missing, because reaching it meant expanding a rotation widget (which only auto-expands on
 * flagged rows) inside a cell of a fifteen-column table that scrolls sideways. These tests pin
 * the replacement: the corrections are a BLOCK, one strip per seated site, with Fit by points as
 * a first-class control beside Best fit — no expansion, no scrolling, no flagged-row condition.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AlignmentActions, type AlignmentActionsContext } from "./AlignmentActions";
import { makeRunSite } from "./RotationVerdict.test";

function makeContext(overrides: Partial<AlignmentActionsContext> = {}): AlignmentActionsContext {
  return {
    busyTooth: null,
    armedTrenchTooth: null,
    bestFit: {
      matchingDiameterMm: 0.3,
      apply: true,
      unavailable: false,
      busyTooth: null,
      notice: null,
      confirmation: null,
      onChangeDiameter: () => undefined,
      onToggleApply: () => undefined,
      onRun: () => undefined,
      onSearchWider: () => undefined,
    },
    correspondenceNotice: null,
    markTrenchNotice: null,
    onOpenFitByPoints: () => undefined,
    onStartMarkTrench: () => undefined,
    onCancelMarkTrench: () => undefined,
    onReverify: () => undefined,
    ...overrides,
  };
}

describe("AlignmentActions — the corrections, findable", () => {
  it("offers Fit by points beside Best fit on EVERY seated site, with no expansion", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions
        sites={[makeRunSite({ tooth: 29 }), makeRunSite({ tooth: 30 })]}
        context={makeContext()}
      />,
    );
    expect(html.split("⇔ Fit by points").length - 1).toBe(2);
    expect(html.split("⊚ Best fit").length - 1).toBe(2);
    expect(html.split("⌖ Mark trench").length - 1).toBe(2);
    expect(html.split("◱ Re-verify").length - 1).toBe(2);
    expect(html).toContain("tooth 29");
    expect(html).toContain("tooth 30");
  });

  it("is present on a HEALTHY row too — the old control only auto-expanded on flagged ones", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions sites={[makeRunSite()]} context={makeContext()} />,
    );
    expect(html).toContain("⇔ Fit by points");
  });

  it("names the loop the client described", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions sites={[makeRunSite()]} context={makeContext()} />,
    );
    expect(html).toContain("If the alignment is not right");
    expect(html).toContain("re-verify");
  });

  it("keeps the best-fit controls folded away until that site's Best fit is opened", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions sites={[makeRunSite()]} context={makeContext()} />,
    );
    expect(html).not.toContain("Matching diameter");
    expect(html).toContain('aria-expanded="false"');
  });

  it("renders nothing at all when no site has been seated", () => {
    expect(renderToStaticMarkup(<AlignmentActions sites={[]} context={makeContext()} />)).toBe("");
  });
});

describe("AlignmentActions — per-tooth slicing", () => {
  const sites = [makeRunSite({ tooth: 29 }), makeRunSite({ tooth: 30 })];

  it("arms the trench click on one tooth only, and instructs that click once", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions sites={sites} context={makeContext({ armedTrenchTooth: 29 })} />,
    );
    expect(html.split("✕ cancel mark").length - 1).toBe(1);
    expect(html.split("⌖ Mark trench").length - 1).toBe(1);
    expect(html.split("click the coded trench on the scan — Esc cancels").length - 1).toBe(1);
  });

  it("prints each outcome line under the tooth it belongs to", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions
        sites={sites}
        context={makeContext({
          markTrenchNotice: { tooth: 29, text: "rotated +38.2° — code feature on your mark" },
          correspondenceNotice: { tooth: 30, text: "your marks agree to 0.07mm" },
        })}
      />,
    );
    expect(html.split("rotated +38.2°").length - 1).toBe(1);
    expect(html.split("your marks agree to 0.07mm").length - 1).toBe(1);
    expect(html.indexOf("rotated +38.2°")).toBeLessThan(html.indexOf("your marks agree"));
  });

  it("takes one tooth's buttons down while ITS request is in flight, leaving the other live", () => {
    const html = renderToStaticMarkup(
      <AlignmentActions sites={sites} context={makeContext({ busyTooth: 29 })} />,
    );
    const disabledFits = html.match(/<button[^>]*disabled[^>]*>⇔ Fit by points/g) ?? [];
    expect(disabledFits).toHaveLength(1);
  });
});
