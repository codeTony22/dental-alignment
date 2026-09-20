# Deterministic vs Intelligence

The repo did not previously name these modes. They are two **execution
strategies** over one seam (`case_prep.application.adjust` +
`assemble_site_signals`). Neither invents a metric.

| mode | UI label | what it does |
|---|---|---|
| `deterministic` | **Deterministic** | One-shot pipeline refinement (`best_fit_site`). No agent loop. Operator-supplied pairs / marks are ignored so they cannot silently become a fit. |
| `intelligence` | **Intelligence** | Walk the MCP tool surface: READ `get_landmarks`, `get_seated`, `get_site_signals`, `get_acceptance`; DRY_RUN `dry_run_best_fit`; COMMIT `commit_best_fit` if the dry-run is adoptable. Operator-supplied rotation / mark / pairs are committed through the matching tools. Landmarks stay **proposals** — the scan half of a pair is never invented. |

Both return the same envelope: `signals_before`, `signals_after` (every
taxonomy group), `outcome`, `refusals`, `trace` (each step classified
READ / DRY_RUN / COMMIT), `proposals`.

`AlreadyOptimal` is a pass (green, with the widen diameter). A gate refusal is
a 409 / `status: refused` and does not mint substitute numbers.

Implementation: [`apps/worker/src/case_prep/application/technique.py`](../../apps/worker/src/case_prep/application/technique.py).
The REST API and the MCP `run_alignment_technique` tool both call that
function.
