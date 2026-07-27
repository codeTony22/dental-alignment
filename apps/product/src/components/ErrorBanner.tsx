/**
 * A BFF that is down gets a STATED banner, never a blank screen (slice 2 contract):
 * the operator's next move — start the service, check the proxy — is in the words.
 */
interface ErrorBannerProps {
  readonly detail: string;
}

export function ErrorBanner({ detail }: ErrorBannerProps) {
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
      <strong>The case service is unreachable.</strong>
      <p style={{ margin: "0.5rem 0 0" }}>{detail}</p>
      <p style={{ margin: "0.5rem 0 0" }}>
        Nothing was loaded. Start the BFF on :8001 (or check the dev proxy) and reload.
      </p>
    </div>
  );
}
