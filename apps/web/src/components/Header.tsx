interface HeaderProps {
  /** Whether the library browser panel is currently open — the button reads as a toggle. */
  readonly libraryOpen: boolean;
  readonly onToggleLibrary: () => void;
}

export function Header({ libraryOpen, onToggleLibrary }: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__brand">
        <span className="app-header__wordmark">
          <span className="app-header__wordmark-a">A</span>rTech
        </span>
        <span className="app-header__sublabel">SOFTWARE LABS</span>
      </div>
      <div className="app-header__right">
        {/* Always visible, never gated on a case (client ask 2026-07-23): the full part
            catalog is browsable before — or without — selecting a doctor scan. */}
        <button
          type="button"
          className={`app-header__library-button${libraryOpen ? " app-header__library-button--active" : ""}`}
          aria-pressed={libraryOpen}
          onClick={onToggleLibrary}
          title="Browse the full healing-cap part library"
        >
          Library
        </button>
        <div className="app-header__context">Case-Prep Automation — Live Demo</div>
      </div>
    </header>
  );
}
