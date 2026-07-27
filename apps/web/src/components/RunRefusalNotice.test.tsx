/**
 * THE HARD-FAIL PANEL (client, 2026-07-25): "render the server's sentence in the UI as an
 * actionable message with the suggested next step, not a raw 409 blob."
 *
 * The fixture is the client's own refusal, routed through the domain exactly as App routes it —
 * so this test fails if either half stops carrying the server's words through to the screen.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RunRefusalNotice } from "./RunRefusalNotice";
import { runRefusalFrom } from "../domain/runRefusal";
import { ApiError } from "../api/client";

const CLIENT_SENTENCE =
  "the 0.20mm gingival relief ate the screw channel of tooth 3 (atlantis/neodent-gm 5030): the " +
  "as-built channel measured r=1.153mm before the relief and is UNMEASURABLE after it, so no " +
  "instrument can accept the delivered part — re-run with a smaller gingival offset (asked " +
  "0.20mm) or use a construction part with more wall";

function refusalHtml(message: string, status: number): string {
  const refusal = runRefusalFrom(new ApiError(message, status));
  if (refusal === null) throw new Error("the domain did not recognise this as a refusal");
  return renderToStaticMarkup(<RunRefusalNotice refusal={refusal} onDismiss={() => {}} />);
}

describe("RunRefusalNotice — the client's own refusal, on screen", () => {
  it("shows the server's sentence verbatim: the tooth, the part and the measured radius", () => {
    const html = refusalHtml(CLIENT_SENTENCE, 409);
    expect(html).toContain("ate the screw channel of tooth 3 (atlantis/neodent-gm 5030)");
    expect(html).toContain("r=1.153mm");
  });

  it("says what happened, and that nothing was emitted", () => {
    const html = refusalHtml(CLIENT_SENTENCE, 409);
    expect(html).toContain("nothing was emitted");
    expect(html).toContain("emitted no package");
  });

  it("gives the next step, naming the control that fixes it", () => {
    const html = refusalHtml(CLIENT_SENTENCE, 409);
    expect(html).toContain("Next step:");
    expect(html).toContain("max safe for this part");
  });

  it("shows no raw JSON or status line when the refusal arrived as a wrapped 409 blob", () => {
    const blob = `Running automation failed (409 Conflict): ${JSON.stringify({ detail: CLIENT_SENTENCE })}`;
    const html = refusalHtml(blob, 409);
    expect(html).toContain("ate the screw channel of tooth 3");
    expect(html).not.toContain("409 Conflict");
    expect(html).not.toContain('{"detail"');
  });

  it("announces itself as an alert and offers a dismiss control", () => {
    const html = refusalHtml(CLIENT_SENTENCE, 409);
    expect(html).toContain('role="alert"');
    expect(html).toContain('aria-label="Dismiss the refusal"');
  });

  it("routes an incomplete selection to the dialog instead of the offset field", () => {
    const html = refusalHtml("choose the construction part for this case", 422);
    expect(html).toContain("library selection is incomplete");
    expect(html).toContain("Verify &amp; process");
  });
});
