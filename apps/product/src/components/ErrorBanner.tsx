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
  // The demo's refusal language (.run-refusal): red, persistent, laid out as what
  // happened / the words verbatim / what to do next.
  return (
    <div role="alert" data-role="bff-error" className="run-refusal">
      <strong className="run-refusal__title">
        {headline ?? "The case service is unreachable."}
      </strong>
      <p className="run-refusal__detail">{detail}</p>
      <p className="run-refusal__next">
        {children ?? (
          <>Nothing was loaded. Start the BFF on :8001 (or check the dev proxy) and reload.</>
        )}
      </p>
    </div>
  );
}
