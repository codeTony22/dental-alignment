interface BusyStateProps {
  readonly message: string;
  readonly elapsedS: number;
}

export function BusyState({ message, elapsedS }: BusyStateProps) {
  return (
    <div className="busy-state" role="status" aria-live="polite">
      <span className="busy-state__spinner" aria-hidden="true" />
      <span className="busy-state__message">{message}</span>
      <span className="busy-state__elapsed">{elapsedS.toFixed(0)}s elapsed</span>
    </div>
  );
}
