/**
 * The three live panes + the review tick (plan §4 Declare / §7 slice 5b), statically
 * rendered per the repo convention (viewer slots are props, so WebGL never enters a
 * test). The pure rules — notices, the preview key/auto-fire, the tick's truth, the
 * wire-mesh flatteners — are pinned in domain/declare.test.ts; what belongs here is
 * the SURFACE: which words render where, the stats from the payload's OWN numbers,
 * the caption that says whose colouring is on screen, and the tick's wiring states.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DeclarePanesView } from "./DeclarePanes";
import { paneNotices, reviewTick } from "../domain/declare";
import { sitePreviewPayload, siteView } from "../testing/fixtures";
import type { SiteView } from "../api/client";

const previewedSite = siteView({
  tooth: 19,
  status: "previewed",
  declared_variant: "5020",
});

function noticesFor(
  site: SiteView | null,
  overrides: Partial<Parameters<typeof paneNotices>[0]> = {},
) {
  return paneNotices({
    site,
    choicesComplete: true,
    partMeshKnown: true,
    partError: null,
    scanError: null,
    scanEmpty: false,
    previewPhase: "ready",
    previewError: null,
    ...overrides,
  });
}

function view(overrides: Partial<Parameters<typeof DeclarePanesView>[0]> = {}) {
  return renderToStaticMarkup(
    <DeclarePanesView
      site={previewedSite}
      variantLabel="5020"
      notices={noticesFor(previewedSite)}
      partBusy={false}
      scanBusy={false}
      scanCaption="1,234 triangles within 9 mm of the site's centre"
      previewPhase="ready"
      payload={sitePreviewPayload()}
      tick={reviewTick(previewedSite)}
      reviewSaving="idle"
      reviewError={null}
      onToggleReview={() => undefined}
      onRetryPreview={() => undefined}
      libraryViewer={<div data-role="stub-library-viewer" />}
      scanViewer={<div data-role="stub-scan-viewer" />}
      unionViewer={<div data-role="stub-union-viewer" />}
      {...overrides}
    />,
  );
}

describe("the three panes render with their viewer slots and captions", () => {
  it("mounts all three panes, each with its slot", () => {
    const html = view();
    expect(html).toContain('data-role="pane-library"');
    expect(html).toContain('data-role="pane-scan"');
    expect(html).toContain('data-role="pane-union"');
    expect(html).toContain('data-role="stub-library-viewer"');
    expect(html).toContain('data-role="stub-scan-viewer"');
    expect(html).toContain('data-role="stub-union-viewer"');
  });

  it("the union caption says WHOSE colouring is on screen — a preview, with its seat", () => {
    const html = view();
    expect(html).toContain("preview — this selection seated now");
    expect(html).toContain("rim-seat seat");
    expect(html).toContain("rim 0.07 mm");
    expect(html).toContain("nothing processed yet");
  });

  it("RMS/p90 come from the payload's OWN stats", () => {
    const html = view();
    expect(html).toContain("RMS 0.430 mm");
    expect(html).toContain("p90 0.710 mm");
  });
});

describe("honest words over empty panes — never a blank canvas", () => {
  it("an undeclared site asks for the declaration; no stats, no caption", () => {
    const undeclared = siteView({ tooth: 19, status: "detected" });
    const html = view({
      site: undeclared,
      variantLabel: null,
      notices: noticesFor(undeclared, { partMeshKnown: false, previewPhase: "idle" }),
      previewPhase: "idle",
      payload: null,
      tick: reviewTick(undeclared),
    });
    expect(html).toContain("Declare this site&#x27;s cap variant");
    expect(html).not.toContain('data-role="union-stats"');
  });

  it("a preview error renders the backend's words with the explicit retry", () => {
    const html = view({
      notices: noticesFor(previewedSite, {
        previewPhase: "error",
        previewError: "HTTP 409 — no confirmed site could be aligned",
      }),
      previewPhase: "error",
      payload: null,
    });
    expect(html).toContain("no confirmed site could be aligned");
    expect(html).toContain('data-role="preview-retry"');
  });

  it("a computing preview is the busy state NAMING the work, not a notice", () => {
    const html = view({
      notices: noticesFor(previewedSite, { previewPhase: "computing" }),
      previewPhase: "computing",
      payload: null,
    });
    expect(html).toContain("seating this selection on the scan");
    expect(html).toContain("nothing is being processed");
  });
});

describe("the review tick — with the panes it attests (AM-8)", () => {
  it("previewed: enabled and unticked; ready: ticked", () => {
    expect(view()).toMatch(/data-role="review-tick"(?![^>]*disabled)[^>]*\/?>/);
    const ready = siteView({ tooth: 19, status: "ready", declared_variant: "5020" });
    const html = view({ site: ready, tick: reviewTick(ready) });
    expect(html).toMatch(/data-role="review-tick"[^>]*checked/);
  });

  it("anything short of a preview is inert WITH its reason", () => {
    const declared = siteView({ tooth: 19, status: "declared", declared_variant: "5020" });
    const html = view({
      site: declared,
      tick: reviewTick(declared),
      previewPhase: "computing",
      payload: null,
      notices: noticesFor(declared, { previewPhase: "computing" }),
    });
    expect(html).toMatch(/data-role="review-tick"[^>]*disabled/);
    expect(html).toContain("preview this site first");
  });

  it("in-flight and refused states are stated — optimism OFF", () => {
    expect(view({ reviewSaving: "ticking" })).toContain("Recording the review…");
    expect(view({ reviewSaving: "unticking" })).toContain("Withdrawing the review…");
    expect(
      view({ reviewError: "HTTP 422 — cannot review_ready a site that is 'declared'" }),
    ).toContain("cannot review_ready");
  });
});
