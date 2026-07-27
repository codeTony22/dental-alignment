/**
 * THE PRODUCT SHELL — deliberately minimal (plan §7 slice 0: "skeletons; ports 8001/5174").
 *
 * Presentational only (plan §1.3): this app renders payloads and collects choices; every
 * millimetre, verdict and clamp comes from the worker via the BFF. The only network the
 * shell does is a liveness probe of the BFF on :8001, reached through the vite proxy so
 * no backend host is ever hard-coded here. The four-stage flow (Intake → Declare →
 * Adjust → Deliver) lands on this shell in slices 2+.
 */
import { useEffect, useState } from "react";

export type HealthProbe =
  | { kind: "checking" }
  | { kind: "up"; service: string }
  | { kind: "down"; detail: string };

/** Pure state → words, so the render path is testable without a browser or a fetch. */
export function healthLabel(probe: HealthProbe): string {
  switch (probe.kind) {
    case "checking":
      return "checking BFF…";
    case "up":
      return `BFF up (${probe.service})`;
    case "down":
      return `BFF unreachable — ${probe.detail}`;
  }
}

export function App() {
  const [probe, setProbe] = useState<HealthProbe>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    fetch("/health")
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { ok?: boolean; service?: string };
        if (!cancelled) {
          setProbe(
            body.ok
              ? { kind: "up", service: body.service ?? "unknown" }
              : { kind: "down", detail: "service reports not ok" },
          );
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setProbe({ kind: "down", detail: err instanceof Error ? err.message : String(err) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>ArTech — Case Flow</h1>
      <p>The product app shell. The four-stage case flow builds on top of this.</p>
      <p data-role="bff-health">{healthLabel(probe)}</p>
    </main>
  );
}

export default App;
