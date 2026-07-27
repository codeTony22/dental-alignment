# apps/api — NestJS backend (Phase 1, not yet built)

Privileged operations only: presigned S3 multipart URLs, job-state writes, Stripe webhooks,
operator cross-tenant actions (service role). **Staged placeholder** — see Phase 1 docs.

[`docs/technical-design-build-guide.md`](../../docs/technical-design-build-guide.md) D4–D6, D8–D11.

> **Looking for the live-demo API?** It is NOT here — the demo's pipeline API is the
> Python FastAPI app in [`apps/worker/src/case_prep/server.py`](../worker/src/case_prep/server.py)
> (`cd apps/worker && make serve`, or `./scripts/run-demo.sh` from the repo root to start
> API + UI together).
