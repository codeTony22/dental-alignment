/**
 * The routed layout: one header, one outlet. What used to be the slice-0b App (a
 * health-probe placeholder) retires here — liveness is now surfaced where it matters,
 * as the stated error state of whichever page actually needed the BFF (slice 2
 * contract: a down BFF is a banner, not a blank screen).
 *
 * Parity slice: the shell wears the demo's app frame — the dark header with the
 * ArTech wordmark, and the viewport-height app-shell so the workbench's regions own
 * their own scroll (the page itself never grows past the viewport on wide screens).
 *
 * ONE BAR ON A CASE ROUTE (client 2026-08-02: "There are two nav bars, take off the
 * ArTech Software Labs, and All cases should be navigable in the same nav bar").
 * `CaseShellView` renders its own `#0e1613` band carrying the case, the stage rail and
 * the acts, and slice A stacked this one directly above it to read as a single header.
 * It did not: two dark bands, each with a link out, read as two navigations for one
 * page. So the brand bar now renders only where it is the ONLY bar, and the case band
 * takes the way home with it.
 */
import { Link, Outlet, useLocation } from "react-router-dom";

/** Does this route render its own nav band? Only the case shell does. Matched on the
 *  path rather than passed down, because `Outlet` gives a parent no way to ask its
 *  child what chrome it brought — and the alternative, a context, is a data-flow change
 *  for a question the URL already answers. */
export function rendersOwnNav(pathname: string): boolean {
  return pathname === "/case" || pathname.startsWith("/case/");
}

export function Shell() {
  const { pathname } = useLocation();
  return (
    <div className="app-shell">
      {!rendersOwnNav(pathname) && (
        <header className="app-header">
          {/* THE WORDMARK IS THE WAY HOME (client, 2026-07-27: "There is no option to go
              back to home and see all cases"). A back-link did exist — in the far corner
              of the case header, labelled "Next case — back to the worklist" — but the
              FIRST thing anyone tries is the logo, and it was inert. It is a Link on every
              route that renders this header; the worklist renders it too (harmlessly
              self-referential there, and never a dead-end). On a case route the same
              promise is kept by the band's own "All cases". */}
          <Link to="/" className="app-header__brand" data-role="home">
            <span className="app-header__wordmark">
              <span className="app-header__wordmark-a">A</span>rTech
            </span>
            <span className="app-header__sublabel">SOFTWARE LABS</span>
          </Link>
          <div className="app-header__right">
            <Link to="/" className="app-header__worklist" data-role="all-cases">
              ← All cases
            </Link>
            <div className="app-header__context">Case-Prep Automation — Case Flow</div>
          </div>
        </header>
      )}
      <Outlet />
    </div>
  );
}
