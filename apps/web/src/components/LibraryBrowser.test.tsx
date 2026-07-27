/**
 * Static-markup tests for the LIBRARY BROWSER (renderToStaticMarkup — node environment, no
 * jsdom, per the repo convention): system tabs, the card grid (variant / dims / filename),
 * the honest badges (duplicate-with-named-counterpart, superseded, legacy, unloadable), the
 * 404 "restart make serve" fallback, and the pure badge/label helpers.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  LibraryBrowser,
  catalogEntryKey,
  duplicateBadgeText,
  groupTabLabel,
  supersededBadgeText,
} from "./LibraryBrowser";
import { catalogGroupLabels } from "../domain/librarySelection";
import type { LibraryCatalogEntry, LibraryCatalogGroup } from "../domain/types";

function makeEntry(overrides: Partial<LibraryCatalogEntry> = {}): LibraryCatalogEntry {
  return {
    id: "6020",
    variant: "6020",
    label: "neodent-gm-6020",
    rimDiameterMm: 6.16,
    heightMm: 3.38,
    filename: "neodent-gm-6020.stl",
    sha256: "abc123",
    flags: [],
    duplicateOf: [],
    meshUrl: "/api/library/neodent-gm/6020/mesh",
    ...overrides,
  };
}

function makeGroups(): LibraryCatalogGroup[] {
  return [
    {
      model: "neodent-gm",
      legacy: false,
      variants: [
        makeEntry(),
        makeEntry({
          id: "superseded-2026-07-13--6020",
          filename: "superseded-2026-07-13/neodent-gm-6020.stl",
          flags: ["superseded"],
        }),
      ],
    },
    {
      model: "zimmer-4.5",
      legacy: false,
      variants: [
        makeEntry({
          id: "6020",
          filename: "zimmer-4.5-6020.stl",
          label: "zimmer-4.5-6020",
          flags: ["duplicate"],
          duplicateOf: ["neodent-gm/6020"],
        }),
      ],
    },
    {
      model: "vendor-legacy-library",
      legacy: true,
      variants: [
        makeEntry({
          id: "legacy_master",
          variant: "legacy_master",
          filename: "legacy_master.stl",
          flags: ["legacy"],
        }),
        makeEntry({
          id: "broken",
          variant: "broken",
          filename: "broken.stl",
          rimDiameterMm: null,
          heightMm: null,
          flags: ["unloadable"],
        }),
      ],
    },
  ];
}

function render(overrides: Partial<Parameters<typeof LibraryBrowser>[0]> = {}): string {
  return renderToStaticMarkup(
    <LibraryBrowser
      state="ready"
      errorMessage={null}
      groups={makeGroups()}
      activeModel="neodent-gm"
      previewedKey={null}
      onSelectModel={() => undefined}
      onPreviewEntry={() => undefined}
      onRetry={() => undefined}
      onClose={() => undefined}
      {...overrides}
    />,
  );
}

describe("LibraryBrowser — tabs", () => {
  it("renders one system tab per group — the client's primary neodent-gm / zimmer-4.5 choice", () => {
    const html = render();
    expect(html).toContain("neodent-gm");
    expect(html).toContain("zimmer-4.5");
    expect(html).toContain("Legacy shelf (legacy)");
    expect(html).toContain('role="tablist"');
  });

  /* A legacy shelf's `model` is the raw name of a CLIENT-OWNED data folder we do not rename —
     it stays the wire key that addresses the files, and never reaches the screen. */
  it("never prints a legacy shelf's raw data-folder name — the neutral label stands in", () => {
    const tabs = render().split("library-cards")[0] ?? "";
    expect(tabs).not.toContain("vendor-legacy-library");
    expect(tabs).toContain("Legacy shelf");
  });

  it("marks the active tab selected and shows per-tab part counts", () => {
    const html = render();
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain("library-tab--active");
    expect(html).toContain('<span class="library-tab__count">2</span>');
  });
});

describe("LibraryBrowser — cards", () => {
  it("shows variant code large, diameter x height, and the filename small", () => {
    const html = render();
    expect(html).toContain('<span class="library-card__variant">6020</span>');
    expect(html).toContain("Ø6.16 × 3.38 mm");
    expect(html).toContain("neodent-gm-6020.stl");
  });

  it("badges the superseded archive under its own system tab (never hidden)", () => {
    const html = render();
    expect(html).toContain("superseded 2026-07-13");
    expect(html).toContain("superseded-2026-07-13/neodent-gm-6020.stl");
  });

  it("badges the byte-identical duplicate naming the counterpart", () => {
    const html = render({ activeModel: "zimmer-4.5" });
    expect(html).toContain("identical file to neodent-gm 6020");
    expect(html).toContain("library-badge--duplicate");
  });

  it("legacy group: loadable parts badge as legacy; unloadable parts are listed but disabled", () => {
    const html = render({ activeModel: "vendor-legacy-library" });
    expect(html).toContain("legacy library");
    expect(html).toContain("library-badge--unloadable");
    expect(html).toContain("disabled");
    expect(html).toContain("dimensions unavailable");
  });

  it("marks the currently previewed card", () => {
    const html = render({ previewedKey: "neodent-gm/6020" });
    expect(html).toContain("library-card--active");
    expect(html).toContain("viewing ✓");
  });
});

describe("LibraryBrowser — degraded states", () => {
  it("404 fallback: the restart hint, not a broken panel", () => {
    const html = render({ state: "unavailable", groups: [] });
    expect(html).toContain("restart");
    expect(html).toContain("make serve");
    expect(html).not.toContain("library-cards");
  });

  it("error state shows the message and a retry control", () => {
    const html = render({ state: "error", errorMessage: "boom", groups: [] });
    expect(html).toContain("boom");
    expect(html).toContain("Retry");
  });

  it("loading state shows the busy spinner", () => {
    const html = render({ state: "loading", groups: [] });
    expect(html).toContain("scanning the part library");
  });

  it("ready with an empty catalog says so instead of rendering nothing", () => {
    const html = render({ groups: [], activeModel: null });
    expect(html).toContain("No library parts found");
  });
});

describe("pure helpers", () => {
  it("catalogEntryKey is model-scoped so two 6020s (current vs superseded) stay distinct", () => {
    expect(catalogEntryKey("neodent-gm", { id: "6020" })).toBe("neodent-gm/6020");
    expect(catalogEntryKey("neodent-gm", { id: "superseded-2026-07-13--6020" })).toBe(
      "neodent-gm/superseded-2026-07-13--6020",
    );
  });

  /* The counterpart ref carries the group's WIRE model. When that group is a legacy shelf the
     model is a client-owned folder name, so the badge must name it by its display label. */
  it("duplicateBadgeText names a legacy counterpart by its label, not its folder", () => {
    const labels = catalogGroupLabels(makeGroups());
    const entry = makeEntry({
      flags: ["duplicate"],
      duplicateOf: ["vendor-legacy-library/legacy_master"],
    });
    expect(duplicateBadgeText(entry, labels)).toBe("identical file to Legacy shelf legacy_master");
    expect(duplicateBadgeText(entry, labels)).not.toContain("vendor-legacy-library");
  });

  it("duplicateBadgeText names every counterpart, null for non-duplicates", () => {
    expect(
      duplicateBadgeText(makeEntry({ flags: ["duplicate"], duplicateOf: ["neodent-gm/6020"] })),
    ).toBe("identical file to neodent-gm 6020");
    expect(
      duplicateBadgeText(
        makeEntry({ flags: ["duplicate"], duplicateOf: ["a/1", "b/2"] }),
      ),
    ).toBe("identical file to a 1, b 2");
    expect(duplicateBadgeText(makeEntry())).toBeNull();
  });

  it("supersededBadgeText extracts the archive date from the filename", () => {
    expect(
      supersededBadgeText(
        makeEntry({ flags: ["superseded"], filename: "superseded-2026-07-13/x.stl" }),
      ),
    ).toBe("superseded 2026-07-13");
    expect(
      supersededBadgeText(makeEntry({ flags: ["superseded"], filename: "archive/x.stl" })),
    ).toBe("superseded");
    expect(supersededBadgeText(makeEntry())).toBeNull();
  });

  it("groupTabLabel appends (legacy) only for legacy groups", () => {
    const labels = catalogGroupLabels(makeGroups());
    expect(groupTabLabel({ model: "neodent-gm", legacy: false }, labels)).toBe("neodent-gm");
    expect(groupTabLabel({ model: "vendor-legacy-library", legacy: true }, labels)).toBe(
      "Legacy shelf (legacy)",
    );
  });
});
