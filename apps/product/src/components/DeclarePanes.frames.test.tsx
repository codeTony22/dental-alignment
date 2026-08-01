/**
 * THE DROPPED-PROP GUARD (client 2026-07-27: "the camera does not face the top of
 * the healing cap"): the frame computed in the DeclarePanes CONTAINER must actually
 * REACH the three VerifyViewer slots — the pane semantics themselves are pure and
 * unit-pinned (domain/declare.test.ts: siteFrameFor / partCameraFrame); what only a
 * component render can pin is the wiring. The viewer package's VerifyViewer is
 * mocked to stamp its `frame` prop into the markup (effects never run under
 * renderToStaticMarkup, so no WebGL enters the test), and the container renders in
 * its initial state: the SITE frame (centre + radius) must arrive on panes 2 and 3
 * whole, pane 1's frame stays honestly null until its part mesh has loaded.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("viewer", async (importOriginal) => {
  const real = await importOriginal<typeof import("viewer")>();
  const React = await import("react");
  return {
    ...real,
    VerifyViewer: (props: { frame: unknown; ariaLabel: string }) =>
      React.createElement("div", {
        "data-role": "viewer-stub",
        "aria-label": props.ariaLabel,
        // encodeURIComponent keeps the JSON free of quotes, so it survives as one
        // HTML attribute and the test can parse it back exactly
        "data-frame": encodeURIComponent(JSON.stringify(props.frame ?? null)),
      }),
  };
});

import { DeclarePanes } from "./DeclarePanes";
import { caseSessionDetail, siteView } from "../testing/fixtures";

function frameOf(html: string, ariaLabel: string): unknown {
  const match = html.match(
    new RegExp(`aria-label="${ariaLabel}"[^>]*data-frame="([^"]*)"`),
  );
  expect(match, `a viewer slot labelled "${ariaLabel}" with its frame`).not.toBeNull();
  return JSON.parse(decodeURIComponent(match![1]!));
}

describe("the container's frames reach the viewer slots", () => {
  const detail = caseSessionDetail({
    sites: [siteView({ tooth: 19, center: [1, 2, 3] })],
  });
  const html = renderToStaticMarkup(
    <DeclarePanes
      detail={detail}
      site={detail.sites[0]!}
      onDetail={() => undefined}
      postPreview={() =>
        Promise.resolve({ kind: "error" as const, detail: "unused statically" })
      }
    />,
  );

  it("panes 2 AND 3 both receive the whole site frame — centre, radius, direction, up", () => {
    const scan = frameOf(html, "The scanned cap region");
    const union = frameOf(
      html,
      "The scan and the previewed cap overlaid, coloured by deviation",
    );
    // initial state: no scan parsed yet (no occlusal), no preview (no pose) — the
    // frame still centres the site at the crop radius with the direction honestly
    // null; the POSE/occlusal directions themselves are siteFrameFor's unit pins
    const expected = {
      center: [1, 2, 3],
      radiusMm: 11,
      viewDirection: null,
      up: null,
    };
    expect(scan).toEqual(expected);
    expect(union).toEqual(expected);
  });

  it("pane 1's frame is null until its part mesh loads — default framing, no guess", () => {
    expect(frameOf(html, "The declared library part")).toBeNull();
  });
});
