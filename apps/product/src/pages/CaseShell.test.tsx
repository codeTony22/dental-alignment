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

  it("renders the rail and, on an unbuilt stage, a body naming its building slice", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/deliver">
        <CaseShellView detail={detail} stage="deliver" />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="stage-rail"');
    expect(html).toContain("slice 8 builds this");
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

  it("Intake and Declare mount the main stage (slice 3); Adjust and Deliver stay placeholders", () => {
    for (const stage of ["intake", "declare"] as const) {
      const html = renderToStaticMarkup(
        <StaticRouter location={`/case/case-a/${stage}`}>
          <CaseShellView detail={detail} stage={stage} />
        </StaticRouter>,
      );
      expect(html).toContain('data-role="main-stage"');
      expect(html).toContain("Loading scan.stl"); // effects do not run statically — honest pre-flight
    }
    const adjust = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/adjust">
        <CaseShellView
          detail={caseSessionDetail({
            session: {
              tenant_id: "local",
              adjust_visited: false,
              run_state: "done",
              confirmed: false,
              payment_authorized: false,
            },
          })}
          stage="adjust"
        />
      </StaticRouter>,
    );
    expect(adjust).not.toContain('data-role="main-stage"');
    expect(adjust).toContain("slice 6 builds this");
  });

  it("offers the next-case affordance back to the worklist (AM-7)", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <CaseShellView detail={detail} stage="intake" />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="next-case"');
    expect(html).toContain('href="/"');
  });

  it("the rail reflects the payload's facts, not click history", () => {
    const resolved = caseSessionDetail({
      sites: [siteView({ status: "ready" }), siteView({ tooth: 19, status: "flagged" })],
      session: {
        tenant_id: "local",
        adjust_visited: false,
        run_state: "done",
        confirmed: false,
        payment_authorized: false,
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
