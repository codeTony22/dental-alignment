/**
 * A failed load gets a STATED banner, never a blank screen (slice 2 contract):
 * the operator's next move is in the words. The default copy diagnoses a DOWN
 * service; callers that know better (a 404 is a refusal, not an outage — see
 * pages/CaseShell.tsx) pass their own headline and next move so the banner
 * never misdiagnoses what actually happened.
 */
import type { ReactNode } from "react";

interface ErrorBannerProps {
  readonly detail: string;
  readonly headline?: string;
  /** The next-move sentence; defaults to the down-service instruction. */
  readonly children?: ReactNode;
}

export function ErrorBanner({ detail, headline, children }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      data-role="bff-error"
      style={{
        border: "1px solid #b3261e",
        borderRadius: "6px",
        padding: "0.75rem 1rem",
        maxWidth: "40rem",
      }}
    >
      <strong>{headline ?? "The case service is unreachable."}</strong>
      <p style={{ margin: "0.5rem 0 0" }}>{detail}</p>
      <p style={{ margin: "0.5rem 0 0" }}>
        {children ?? (
          <>Nothing was loaded. Start the BFF on :8001 (or check the dev proxy) and reload.</>
        )}
      </p>
    </div>
  );
}
