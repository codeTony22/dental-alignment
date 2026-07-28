/**
 * The routed layout: one header, one outlet. What used to be the slice-0b App (a
 * health-probe placeholder) retires here — liveness is now surfaced where it matters,
 * as the stated error state of whichever page actually needed the BFF (slice 2
 * contract: a down BFF is a banner, not a blank screen).
 *
 * Parity slice: the shell wears the demo's app frame — the dark header with the
 * ArTech wordmark, and the viewport-height app-shell so the workbench's regions own
 * their own scroll (the page itself never grows past the viewport on wide screens).
 */
import { Link, Outlet } from "react-router-dom";

export function Shell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        {/* THE WORDMARK IS THE WAY HOME (client, 2026-07-27: "There is no option to go back
            to home and see all cases"). A back-link did exist — in the far corner of the case
            header, labelled "Next case — back to the worklist" — but the FIRST thing anyone
            tries is the logo, and it was inert. It is a Link now on every route; the worklist
            renders it too (harmlessly self-referential there, and never a dead-end). */}
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
      <Outlet />
    </div>
  );
}
