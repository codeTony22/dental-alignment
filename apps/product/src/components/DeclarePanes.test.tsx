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
import { DeclarePanesView, seatedRunCaption } from "./DeclarePanes";
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
      scanCaption="1,234 triangles within 11 mm of the site's centre"
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

describe("the parity chrome (ledger row 9): HUDs on the glass, the demo's clothes", () => {
  const layers = {
    library: [
      { id: "part", label: "library part", swatch: "#2fa75f", visible: true, opacity: 1, available: true },
    ],
    scan: [
      { id: "scan", label: "scanned cap", swatch: "#f2e3a6", visible: true, opacity: 1, available: true },
    ],
    union: [
      { id: "scan", label: "scan", swatch: "#f2e3a6", visible: true, opacity: 0.45, available: true },
      { id: "deviation", label: "preview deviation", swatch: null, visible: false, opacity: 1, available: true },
    ],
  } as const;

  it("panes wear the verify-panel clothes and the words float as overlays", () => {
    const html = view();
    expect(html).toContain('class="verify-panels"');
    expect(html).toMatch(/data-role="pane-library"[^>]*class="verify-panel"/);
    expect(html).toContain("verify-panel__stage");
  });

  it("the layer HUD renders eyes + opacity per layer, on the glass", () => {
    const html = view({ layers });
    expect(html).toContain("verify-panel__hud--layers");
    expect(html).toContain("scanned cap");
    expect(html).toContain("preview deviation");
    expect(html).toContain("45%"); // the union scan's kept 0.45 default
    expect(html).toMatch(/aria-pressed="false"[^>]*aria-label="Show preview deviation"/);
  });

  it("the union colorbar HUD carries the signed ramp, its ticks and the stats line", () => {
    const html = view();
    expect(html).toContain("verify-panel__hud--scale");
    expect(html).toContain("linear-gradient"); // deviationGradientCss — the mesh's own ramp
    expect(html).toContain("−0.50"); // the signed scale's leftmost tick at clamp 0.5 (true minus)
    expect(html).toMatch(/data-role="union-stats"[^>]*class="verify-colorbar__stats"/);
  });

  it("the attestation wears the acknowledgment-bar language — text yields, the act does not", () => {
    // the demo's decode-ack shape (VerifyDialog's footer): the sentence side is the
    // flexible column, the act sits in the pinned actions block so no amount of
    // wording can push it off the bar
    const html = view();
    expect(html).toContain('class="decode-ack"');
    expect(html).toContain("decode-ack__disclaimer");
    expect(html).toContain("decode-ack__actions");
  });
});

describe("the pane chrome the demo's same surface carries (parity fix, ledger row 9)", () => {
  it("the toolbar offers the link-orbits toggle, honest about its state", () => {
    const off = view({ linked: false, onToggleLinked: () => undefined });
    expect(off).toContain("verify-panels__toolbar");
    expect(off).toMatch(/aria-pressed="false"[^>]*>[^<]*link views/);
    const on = view({ linked: true, onToggleLinked: () => undefined });
    expect(on).toMatch(/aria-pressed="true"[^>]*>[^<]*views linked/);
    expect(on).toContain("button--active");
  });

  it("every pane header carries the maximize control", () => {
    const html = view({ maximizedId: null, onToggleMaximized: () => undefined });
    expect(html).toContain("verify-panel__heading");
    expect((html.match(/verify-panel__maximize/g) ?? []).length).toBeGreaterThanOrEqual(3);
    expect(html).toContain('aria-label="Maximise 3 · Union — coloured by deviation"');
  });

  it("maximised: one pane fills the stage, the others UNMOUNT, the way back is stated", () => {
    const html = view({
      maximizedId: "union",
      onToggleMaximized: () => undefined,
      linked: false,
      onToggleLinked: () => undefined,
    });
    expect(html).toContain("verify-panels__grid--maximized");
    expect(html).toContain('data-role="pane-union"');
    expect(html).not.toContain('data-role="pane-library"');
    expect(html).not.toContain('data-role="pane-scan"');
    expect(html).toContain("show all three");
    // linking needs more than one panel on screen — the toggle goes down, not away
    expect(html).toMatch(/disabled[^>]*>[^<]*link views/);
  });

  it("the union pane offers both scales; signed is the default and says so", () => {
    const html = view({ scaleId: "signed", onSelectScale: () => undefined });
    expect(html).toContain('role="radiogroup"');
    expect(html).toMatch(/aria-checked="true"[^>]*>[^<]*Signed ±0\.50 mm/);
    expect(html).toMatch(/aria-checked="false"[^>]*>[^<]*Contacts 0\.00–0\.60 mm/);
  });

  it("the Contacts scale swaps bar, ticks and aria to the absolute rainbow", () => {
    const html = view({ scaleId: "contacts", onSelectScale: () => undefined });
    expect(html).toContain("absolute distance");
    expect(html).toContain("0.15"); // the contacts quartile ticks at 0.6 max
    expect(html).toContain("0.60");
    expect(html).not.toContain("−0.50"); // the signed ticks left with their scale
  });

  it("the legend-and-stats fold keeps the convention, the unmeasured swatch and the source", () => {
    const html = view();
    expect(html).toContain("verify-colorbar__detail");
    expect(html).toContain("legend &amp; stats");
    expect(html).toContain("+ = scan outside the cap surface"); // the payload's OWN convention
    expect(html).toContain("verify-colorbar__unmeasured");
    expect(html).toContain("not measured");
    expect(html).toContain("area-uniform surface samples"); // the stats' stated source
    // the tested promise survives the fold: the stats line keeps its data-role
    expect(html).toMatch(/data-role="union-stats"[^>]*class="verify-colorbar__stats"/);
  });
});

describe("the attestation — a button-weight act over the panes it attests (AM-8)", () => {
  it("an unattested site offers the act, with the sentence naming what it covers", () => {
    // client 2026-07-27 #2: "The reviewed over the panes check mark needs to be
    // better confirmed" — the bare checkbox is gone; the act states its subject
    const html = view();
    expect(html).toMatch(/data-role="review-tick"(?![^>]*disabled)/);
    expect(html).toContain("Confirm this site");
    expect(html).toContain('data-role="attestation-sentence"');
    expect(html).toContain("tooth 19");
    expect(html).toContain("the declared cap 5020");
    expect(html).toContain("the panes above");
    expect(html).not.toContain('type="checkbox" data-role="review-tick"');
  });

  it("an attested site shows what WAS attested, and withdrawing is equally explicit", () => {
    const ready = siteView({ tooth: 19, status: "ready", declared_variant: "5020" });
    const html = view({ site: ready, tick: reviewTick(ready) });
    expect(html).toMatch(/data-role="review-tick"[^>]*aria-pressed="true"/);
    expect(html).toContain("Undo this confirmation");
    expect(html).toContain("You confirmed tooth");
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
    expect(view({ reviewSaving: "ticking" })).toContain("Recording the attestation…");
    expect(view({ reviewSaving: "unticking" })).toContain(
      "Undoing…",
    );
    expect(
      view({ reviewError: "HTTP 422 — cannot review_ready a site that is 'declared'" }),
    ).toContain("cannot review_ready");
  });
});

describe("the panes' way home (client 2026-07-29: the pane camera vs the main stage)", () => {
  it("offers a reset control on EVERY pane, each naming the pane it restores", () => {
    const html = view({ onResetView: () => undefined });
    const controls = html.match(/data-role="pane-reset-view"/g) ?? [];
    expect(controls).toHaveLength(3);
    expect(html).toContain("Restore the framing of 1 · Library part");
    expect(html).toContain("Restore the framing of 2 · Scanned cap");
  });

  it("renders no reset control when the container supplies no handler", () => {
    // Static callers that predate the control must keep their markup — a dead button
    // that cannot restore anything is worse than none.
    expect(view()).not.toContain('data-role="pane-reset-view"');
  });
});

/**
 * THE SEATED FALLBACK (§10-AE, reproduced live on cap7020 t3): a flagged site's
 * panes wear the RUN's own fit, not preview words and not an eternal 422 retry.
 */
describe("the seated fallback's words and chrome", () => {
  it("seatedRunCaption names the shipped fit and where rework lives", () => {
    const words = seatedRunCaption({
      ...sitePreviewPayload(),
      seat: { seat_method: "rim-seat", rim_agreement_mm: 0.8 },
    });
    expect(words).toContain("the run's own fit");
    expect(words).toContain("rim-seat seat, rim 0.80 mm");
    expect(words).toContain("rework belongs to Adjustment");
    expect(words).not.toContain("preview");
    expect(seatedRunCaption(null)).toBeNull();
  });

  it("a seated payload wears the run caption, never the preview's", () => {
    const html = view({
      payload: sitePreviewPayload(),
      payloadSource: "seated",
    });
    expect(html).toContain("the run&#x27;s own fit");
    expect(html).not.toContain("nothing processed yet");
    expect(html).not.toContain('data-role="preview-retry"');
  });

  it("a failed seated read states itself instead of pretending an empty pane", () => {
    const html = view({
      payload: null,
      previewPhase: "idle",
      seatedPhase: "error",
      seatedError: "the case service is unreachable",
    });
    expect(html).toContain("the shipped fit could not be read");
    expect(html).toContain("the case service is unreachable");
  });
});
