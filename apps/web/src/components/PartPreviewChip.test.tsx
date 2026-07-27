/**
 * Static-markup tests for the library-part preview overlay chip (renderToStaticMarkup — node
 * environment, no jsdom, per the repo convention): chip text incl. dims/tooth, the Back-to-scan
 * control, the loading state, and the pure Escape-key handler factory the chip's window
 * listener uses (effects don't run under static rendering, so the wiring logic is tested as a
 * pure function — the convention's "interaction logic lives in pure functions/handlers").
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  PartPreviewChip,
  formatVariantDims,
  makePreviewKeyHandler,
  partPreviewLabel,
  type PartPreviewInfo,
} from "./PartPreviewChip";

function makePreview(overrides: Partial<PartPreviewInfo> = {}): PartPreviewInfo {
  return {
    variant: "6020",
    rimDiameterMm: 6.16,
    heightMm: 3.38,
    tooth: 3,
    loading: false,
    ...overrides,
  };
}

describe("PartPreviewChip — markup", () => {
  it("renders the full 'viewing' statement: variant · Ø × height (tooth N) plus the way back", () => {
    const html = renderToStaticMarkup(
      <PartPreviewChip preview={makePreview()} canReturnToScan onBackToScan={() => undefined} />,
    );
    expect(html).toContain("Viewing library part — 6020 · Ø6.16 × 3.38 mm (tooth 3)");
    expect(html).toContain("← Back to scan");
    expect(html).toContain("part-preview-chip");
    // a status region — screen readers announce the mode change
    expect(html).toContain('role="status"');
  });

  it("loading state: says loading (not viewing) and shows the spinner", () => {
    const html = renderToStaticMarkup(
      <PartPreviewChip
        preview={makePreview({ loading: true })}
        canReturnToScan
        onBackToScan={() => undefined}
      />,
    );
    expect(html).toContain("Loading library part — 6020");
    expect(html).toContain("part-preview-chip__spinner");
    expect(html).not.toContain("Viewing library part");
  });

  it("omits the dims segment when the catalog has none, and the tooth segment when unknown", () => {
    const html = renderToStaticMarkup(
      <PartPreviewChip
        preview={makePreview({ rimDiameterMm: null, heightMm: null, tooth: null })}
        canReturnToScan
        onBackToScan={() => undefined}
      />,
    );
    expect(html).toContain("Viewing library part — 6020</span>");
    expect(html).not.toContain("Ø");
    expect(html).not.toContain("tooth");
  });

  it("renders NOTHING when no preview is active — the chip exists only during a preview", () => {
    const html = renderToStaticMarkup(
      <PartPreviewChip preview={null} canReturnToScan onBackToScan={() => undefined} />,
    );
    expect(html).toBe("");
  });

  it("no case selected (library-browser preview on the empty stage): still names the part, but offers no Back — there is no scan to go back to", () => {
    const html = renderToStaticMarkup(
      <PartPreviewChip
        preview={makePreview({ tooth: null })}
        canReturnToScan={false}
        onBackToScan={() => undefined}
      />,
    );
    expect(html).toContain("Viewing library part — 6020");
    expect(html).not.toContain("Back to scan");
  });
});

describe("partPreviewLabel / formatVariantDims — pure formatting", () => {
  it("formats dims and drops them when either dimension is missing", () => {
    expect(formatVariantDims(6.16, 3.38)).toBe("Ø6.16 × 3.38 mm");
    expect(formatVariantDims(null, 3.38)).toBeNull();
    expect(formatVariantDims(6.16, null)).toBeNull();
  });

  it("composes the label with every known segment, degrading gracefully", () => {
    expect(partPreviewLabel(makePreview())).toBe("6020 · Ø6.16 × 3.38 mm (tooth 3)");
    expect(partPreviewLabel(makePreview({ rimDiameterMm: null, heightMm: null }))).toBe("6020 (tooth 3)");
    expect(partPreviewLabel(makePreview({ tooth: null }))).toBe("6020 · Ø6.16 × 3.38 mm");
  });
});

describe("makePreviewKeyHandler — Escape exits, nothing else does", () => {
  it("calls onBackToScan for Escape only", () => {
    let calls = 0;
    const handler = makePreviewKeyHandler(() => {
      calls += 1;
    });
    handler({ key: "Escape" });
    expect(calls).toBe(1);
    handler({ key: "Enter" });
    handler({ key: "a" });
    handler({ key: " " });
    expect(calls).toBe(1);
  });
});
