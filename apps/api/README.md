# apps/api — case REST API (FastAPI)

UI-shaped peer of the BFF and the alignment MCP. Prefix `/api/v1`, port **8002**.
Owns no physics: every millimetre comes from `case_prep.application`.

Design: [`docs/engagement/frontend-rest-api.md`](../../docs/engagement/frontend-rest-api.md).
Technique modes: [`docs/engagement/alignment-technique-modes.md`](../../docs/engagement/alignment-technique-modes.md).

```bash
# shares the worker venv
cd apps/worker && .venv/bin/pip install -e ../api
.venv/bin/uvicorn case_api.main:app --reload --port 8002 --app-dir ../api/src
```

Tests: `../worker/.venv/bin/pytest -q` from `apps/api` (same convention as the BFF).

The Phase-1 NestJS privileged-ops backend (presigned S3, Stripe webhooks,
operator service-role) is still unbuilt. This package is the case-prep REST
adapter the operator frontend talks to — not that portal.
