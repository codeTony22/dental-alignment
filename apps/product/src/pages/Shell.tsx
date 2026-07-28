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
import { Outlet } from "react-router-dom";

export function Shell() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__wordmark">
            <span className="app-header__wordmark-a">A</span>rTech
          </span>
          <span className="app-header__sublabel">SOFTWARE LABS</span>
        </div>
        <div className="app-header__right">
          <div className="app-header__context">Case-Prep Automation — Case Flow</div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
