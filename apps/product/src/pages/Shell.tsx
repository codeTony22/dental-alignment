/**
 * The routed layout: one header, one outlet. What used to be the slice-0b App (a
 * health-probe placeholder) retires here — liveness is now surfaced where it matters,
 * as the stated error state of whichever page actually needed the BFF (slice 2
 * contract: a down BFF is a banner, not a blank screen).
 */
import { Outlet } from "react-router-dom";

export function Shell() {
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <header>
        <h1 style={{ marginTop: 0 }}>ArTech — Case Flow</h1>
      </header>
      <Outlet />
    </main>
  );
}
