/**
 * THE TERMS, AS A PAGE (client 2026-07-30: "shouldn't term and condition be a link
 * and if clicked route to the proper pages").
 *
 * They should, and the reason outlives the layout: every confirmation already records
 * WHICH terms it accepted (`terms_version`, sealed into the evidence hash), and until
 * this route existed that string pointed at nothing an auditor could obtain. A
 * versioned page makes the recorded version RESOLVABLE — /terms/placeholder-v1 serves
 * exactly the text that signature covered, even after the client's real terms land as
 * a new version.
 *
 * It is a ROUTE rather than a modal on purpose, unlike the report and the checkout: a
 * legal document is something you print, save, or send to someone else, and all three
 * want a URL. Deliver opens it in a NEW TAB so reading the terms never costs the
 * operator the confirmation they were part-way through.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchTerms, type TermsDocumentView } from "../api/client";

export interface TermsViewProps {
  readonly document: TermsDocumentView;
}

/** Pure markup — statically testable. */
export function TermsView({ document }: TermsViewProps) {
  return (
    <article data-role="terms-page" className="terms-page">
      <h1 className="terms-page__title">{document.title}</h1>
      <p data-role="terms-version" className="terms-page__version">
        Version <strong>{document.version}</strong>
      </p>
      {document.status === "placeholder" && (
        /* the document says so ITSELF — the surface never decides whether what it
           received is binding, it renders the status the server gave it */
        <p data-role="terms-status" className="terms-block__placeholder">
          PLACEHOLDER — this is not the client's final Terms and Conditions text. A
          confirmation accepted against this version records exactly that.
        </p>
      )}
      <div data-role="terms-body" className="terms-page__body">
        {document.body}
      </div>
    </article>
  );
}

/** The container: resolves the version in the path, or the current one. */
export function TermsPage() {
  const { version } = useParams<{ version?: string }>();
  const [document, setDocument] = useState<TermsDocumentView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchTerms(version).then((result) => {
      if (result.kind === "ok") setDocument(result.data);
      else setError(result.detail);
    });
  }, [version]);

  if (error !== null) {
    return (
      <div data-role="terms-error" className="page">
        <p className="panel__error">{error}</p>
        <Link className="button button--secondary" to="/">
          ← All cases
        </Link>
      </div>
    );
  }
  if (document === null) {
    return (
      <div data-role="terms-loading" className="page">
        <p className="panel__hint">Loading the terms…</p>
      </div>
    );
  }
  return <TermsView document={document} />;
}
