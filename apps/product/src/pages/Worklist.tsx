/**
 * "/" — the worklist, the 20-scan morning's home screen (plan §4 "Worklist first",
 * AM-7). Slice 2 lands the route; slice 2b builds the rows.
 */
export function WorklistPage() {
  return (
    <section data-role="worklist">
      <h2>Worklist</h2>
      <p>Worklist — slice 2b builds this (one row per case, blocked-first).</p>
    </section>
  );
}
