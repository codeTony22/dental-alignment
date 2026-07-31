/**
 * The case shell's promises (slice 2): the payload renders as header + rail + a stage
 * body that names its building slice; "next case" returns to the worklist (AM-7);
 * the container shows its honest pre-flight state; a down BFF is a stated banner.
 * (The redirect DECISION itself is pure and pinned in domain/flow.test.ts —
 * resolveStagePath — per the repo convention of testing logic outside the DOM.)
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes, StaticRouter } from "react-router-dom";
import { caseSessionDetail, siteView } from "../testing/fixtures";
import { ErrorBanner } from "../components/ErrorBanner";
import { CaseLoadError, CaseShell, CaseShellView } from "./CaseShell";

describe("the case shell view", () => {
  const detail = caseSessionDetail();

  it("names the case, its doctor and jaw", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <CaseShellView detail={detail} stage="intake" />
      </StaticRouter>,
    );
    expect(html).toContain("Case case-a — Dr. Rivera");
    expect(html).toContain("lower");
  });

  it("renders the rail and Adjust's built stage — no placeholder line remains", () => {
    // THE LAST PLACEHOLDER IS GONE (client 2026-07-28: "The adjust functionality is
    // not build at all"). Every stage now mounts a real surface, so this test's
    // subject flipped from "names its building slice" to "there is nothing left to
    // name" — the shell can no longer express a promise it cannot keep.
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/adjust">
        <CaseShellView detail={detail} stage="adjust" />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="stage-rail"');
    expect(html).toContain('data-role="adjust-stage"');
    expect(html).not.toContain("builds this");
  });

  it("Deliver mounts its built stage (slice 8) — no placeholder line remains", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/deliver">
        <CaseShellView detail={detail} stage="deliver" />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="deliver-stage"');
    expect(html).not.toContain("slice 8 builds this");
  });

  it("Declare mounts its built stage (slice 5a) — no placeholder line remains", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/declare">
        <CaseShellView detail={detail} stage="declare" />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="declare-stage"');
    expect(html).not.toContain("Slice 5a builds");
  });

  it("Intake mounts the main stage; Declare offers the arch as a dialog instead", () => {
    // Retargeted 2026-07-30: Declare's arch used to mount alongside the panes as an
    // always-open strip, and it cost them a third of the stage (client: "small
    // panels, the view is cut off"). On Declare the viewer now mounts only inside
    // the arch DIALOG, so a static render carries the button and no main-stage.
    const intake = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <CaseShellView detail={detail} stage="intake" />
      </StaticRouter>,
    );
    expect(intake).toContain('data-role="main-stage"');
    expect(intake).toContain("Loading scan.stl"); // effects do not run statically — honest pre-flight

    const declare = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/declare">
        <CaseShellView detail={detail} stage="declare" />
      </StaticRouter>,
    );
    expect(declare).toContain('data-role="arch-open"');
    expect(declare).not.toContain('data-role="main-stage"');
    const adjust = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/adjust">
        <CaseShellView
          detail={caseSessionDetail({
            session: {
              tenant_id: "local",
              adjust_visited: false,
              adjust_decision: null,
              run_state: "done",
              run_refusal: null,
              confirmed: false,
              payment_authorized: false,
              confirmation: null,
              payment: null,
              release: null,
              release_preview: null,
              released: false,
            },
          })}
          stage="adjust"
        />
      </StaticRouter>,
    );
    // Adjust mounts the THREE PANES, not the arch: the fit is the subject here, and
    // the whole-arch context strip belongs to Declare's framing decision.
    expect(adjust).not.toContain('data-role="main-stage"');
    expect(adjust).toContain('data-role="adjust-queue"');
    expect(adjust).toContain('data-role="adjust-toolbox"');
    expect(adjust).toContain('data-role="pane-union"');
  });

  /* The way back MOVED to the app header (client, 2026-07-27: "There is no option to go back
     to home and see all cases"). The corner link this test used to pin said "Next case" and
     went to the worklist — a label describing an action it did not perform. The affordance is
     now the header's brand + "All cases" on every route, pinned in Shell.test.tsx; the case
     header keeps only the case's own identity. */
  it("keeps the case header to the case's own identity", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <CaseShellView detail={detail} stage="intake" />
      </StaticRouter>,
    );
    expect(html).not.toContain('data-role="next-case"');
    expect(html).toContain("case-header__title");
  });

  it("the rail reflects the payload's facts, not click history", () => {
    const resolved = caseSessionDetail({
      sites: [siteView({ status: "ready" }), siteView({ tooth: 19, status: "flagged" })],
      session: {
        tenant_id: "local",
        adjust_visited: false,
        adjust_decision: null,
        run_state: "done",
        run_refusal: null,
        confirmed: false,
        payment_authorized: false,
        confirmation: null,
        payment: null,
        release: null,
        release_preview: null,
        released: false,
      },
    });
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/deliver">
        <CaseShellView detail={resolved} stage="deliver" />
      </StaticRouter>,
    );
    expect(html).toContain('href="/case/case-a/adjust"'); // a run exists
    expect(html).toContain('href="/case/case-a/deliver"'); // flagged-with-run delivers
  });
});

describe("the case shell container", () => {
  it("shows its pre-flight loading state (effects do not run statically)", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <Routes>
          <Route path="/case/:id/:stage" element={<CaseShell />} />
        </Routes>
      </StaticRouter>,
    );
    expect(html).toContain("Loading case case-a");
  });
});

describe("the error banner", () => {
  it("states the failure and the operator's next move — never a blank screen", () => {
    const html = renderToStaticMarkup(<ErrorBanner detail="HTTP 502 — bad gateway" />);
    expect(html).toContain("The case service is unreachable.");
    expect(html).toContain("HTTP 502 — bad gateway");
    expect(html).toContain("Start the BFF on :8001");
  });
});

describe("the case load error", () => {
  it("a 404 names the missing case and points home — the service is NOT down", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/gone-case/intake">
        <CaseLoadError
          id="gone-case"
          error={{ kind: "error", status: 404, detail: "HTTP 404 — unknown case 'gone-case'" }}
        />
      </StaticRouter>,
    );
    expect(html).toContain("no longer in the data root");
    expect(html).toContain("gone-case");
    expect(html).toContain("HTTP 404 — unknown case &#x27;gone-case&#x27;");
    expect(html).toContain('href="/"'); // the next move: back to the worklist
    expect(html).not.toContain("unreachable"); // a refusal must not read as an outage
    expect(html).not.toContain("Start the BFF");
  });

  it("any other failure keeps the unreachable-service banner and its next move", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <CaseLoadError
          id="case-a"
          error={{ kind: "error", detail: "ECONNREFUSED" }}
        />
      </StaticRouter>,
    );
    expect(html).toContain("The case service is unreachable.");
    expect(html).toContain("ECONNREFUSED");
    expect(html).toContain("Start the BFF on :8001");
  });
});
