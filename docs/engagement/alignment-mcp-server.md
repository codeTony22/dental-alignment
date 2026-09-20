# Alignment MCP server

The agent-shaped peer of the BFF and the REST case API. It speaks JSON-RPC 2.0
over stdio and calls **the same** `case_prep.application` / `caseflow` seam the
operator UI uses. It owns no physics.

- Code: [`apps/mcp`](../../apps/mcp)
- Boundaries (AST): [`apps/mcp/tests/test_boundaries.py`](../../apps/mcp/tests/test_boundaries.py) — no `bff` imports, no `case_prep.server`
- Technique contract: [`alignment-technique-modes.md`](alignment-technique-modes.md)
- REST sibling: [`frontend-rest-api.md`](frontend-rest-api.md)

## Tool classes

Every tool is one of `READ` / `DRY_RUN` / `COMMIT`.

| class | tools |
|---|---|
| READ | `list_cases`, `get_case`, `get_site_signals`, `get_seated`, `get_landmarks`, `get_acceptance` |
| DRY_RUN | `dry_run_best_fit` (`best_fit_site(..., apply=False)`), `dry_run_repreview` |
| COMMIT | `commit_best_fit`, `commit_rotation`, `commit_mark_trench`, `commit_fit_by_points`, `run_alignment_technique` |

`get_site_signals` serves the **full** taxonomy (not a subset): capture,
measurement honesty, seat, fit, correspondence, certification, residue,
acceptance (every catalog key), landmarks, clocking, stability, guidance.

## Run

```bash
# from the repo root, using the worker venv (the one environment)
PYTHONPATH=apps/mcp/src apps/worker/.venv/bin/python -m alignment_mcp
```

Point an MCP client at that command. `initialize` / `tools/list` / `tools/call`
are implemented; notifications are acknowledged by silence.
