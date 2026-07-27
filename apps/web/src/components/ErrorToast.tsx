interface ErrorToastProps {
  readonly message: string;
  readonly onDismiss: () => void;
}

export function ErrorToast({ message, onDismiss }: ErrorToastProps) {
  return (
    <div className="toast toast--error" role="alert">
      <span className="toast__message">{message}</span>
      <button type="button" className="toast__dismiss" onClick={onDismiss} aria-label="Dismiss error">
        &times;
      </button>
    </div>
  );
}
