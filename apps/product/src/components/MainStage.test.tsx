/**
 * THE MAIN STAGE's chrome (plan §7 slice 3), statically rendered — the repo convention:
 * renderToStaticMarkup in node asserts the CONTROL SURFACE (the subject toggle, the
 * honest load states, the framed-on line), never WebGL. The camera moves themselves are
 * the viewer package's browser-only surface (see its sceneController characterization
 * test header); the routing DECISION is pure and pinned in the package's siteRouting
 * tests, so what belongs here is only what this app puts around them.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MainStage, MainStageView, scanErrorHeadline } from "./MainStage";
import { siteView } from "../testing/fixtures";

const stubViewer = <div data-role="viewer-stub" />;

function view(overrides: Partial<Parameters<typeof MainStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <MainStageView
      scanState={{ kind: "ready" }}
      scanFilename="upper_jaw.stl"
      subject="site"
      siteAvailable={true}
      activeTooth={19}
      onSelectSubject={() => undefined}
      viewerSlot={stubViewer}
      {...overrides}
    />,
  );
}

describe("the subject toggle — the demo stage's two-button control, reimplemented", () => {
  it("offers this-site and whole-arch, with the current subject pressed", () => {
    const html = view({ subject: "site" });
    expect(html).toContain("This site");
    expect(html).toContain("Whole arch");
    expect(html).toMatch(/aria-pressed="true"[^>]*>[^<]*This site/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>[^<]*Whole arch/);
  });

  it("whole-arch pressed when the operator backed out", () => {
    expect(view({ subject: "arch" })).toMatch(/aria-pressed="true"[^>]*>[^<]*Whole arch/);
  });

  it("this-site goes down (with the reason) when no site has a usable centre", () => {
    const html = view({ siteAvailable: false });
    expect(html).toMatch(/disabled[^>]*>[^<]*This site/);
    expect(html).toContain("nothing to frame");
  });
});

describe("the stage's honest load states", () => {
  it("loading names the scan file", () => {
    expect(view({ scanState: { kind: "loading" } })).toContain("Loading upper_jaw.stl");
  });

  it("ready on a site states what the stage is framed on — front view", () => {
    const html = view({ scanState: { kind: "ready" }, activeTooth: 19 });
    expect(html).toContain("Framed on tooth 19");
    expect(html).toContain("front view");
  });

  it("a scan 404 reads as a refusal — the service answered, the scan is missing", () => {
    const detail = "fetch for \"/api/case-sessions/case-a/scan\" responded with 404: Not Found";
    const html = view({ scanState: { kind: "error", detail } });
    expect(html).toContain("The case service answered");
    expect(html).toContain("404");
    expect(html).not.toContain("did not load"); // a refusal must not read as an outage
  });

  it("any other load failure keeps the plain did-not-load words with the stated detail", () => {
    const html = view({ scanState: { kind: "error", detail: "NetworkError: ECONNREFUSED" } });
    expect(html).toContain("The scan did not load.");
    expect(html).toContain("ECONNREFUSED");
  });

  it("scanErrorHeadline branches on the loader's own words", () => {
    expect(scanErrorHeadline("responded with 404")).toContain("answered");
    expect(scanErrorHeadline("timeout")).toBe("The scan did not load.");
  });
});

describe("the MainStage container, statically (effects do not run)", () => {
  it("mounts the real viewer surface and opens in the loading state on a site subject", () => {
    const html = renderToStaticMarkup(
      <MainStage
        caseId="case-a"
        scanFilename="upper_jaw.stl"
        sites={[siteView({ tooth: 19 })]}
      />,
    );
    expect(html).toContain("3D viewer of the doctor&#x27;s scan"); // the package's Viewer3D div
    expect(html).toContain("Loading upper_jaw.stl");
    expect(html).toMatch(/aria-pressed="true"[^>]*>[^<]*This site/); // site is the opening subject
  });

  it("with no usable site centre the site subject is honestly unavailable", () => {
    const html = renderToStaticMarkup(
      <MainStage
        caseId="case-a"
        scanFilename="upper_jaw.stl"
        sites={[siteView({ center: null })]}
      />,
    );
    expect(html).toMatch(/disabled[^>]*>[^<]*This site/);
  });
});
