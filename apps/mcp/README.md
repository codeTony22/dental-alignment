# apps/mcp — alignment MCP server

Hand-rolled JSON-RPC 2.0 stdio MCP. Agent-shaped peer of the BFF and
`apps/api`. READ / DRY_RUN / COMMIT tools over `case_prep.application` /
`caseflow`.

Design: [`docs/engagement/alignment-mcp-server.md`](../../docs/engagement/alignment-mcp-server.md).

```bash
PYTHONPATH=apps/mcp/src apps/worker/.venv/bin/python -m alignment_mcp
```

Boundaries: `tests/test_boundaries.py` — no `bff` imports, no `case_prep.server`.
