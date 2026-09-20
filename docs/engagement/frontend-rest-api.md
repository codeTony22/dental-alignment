# Frontend REST API (`apps/api`)

UI-shaped FastAPI peer of the BFF and the alignment MCP. Prefix `/api/v1`.
Port **8002**. Owns no physics — every millimetre comes from
`case_prep.application`.

This is **not** the NestJS privileged-ops placeholder the Phase-1 portal
sketched (S3 / Stripe / service-role). That work is still unbuilt. The live
operator product remains `apps/product` → `apps/bff` → the same seam.

- Code: [`apps/api`](../../apps/api)
- Frontend: [`apps/frontend`](../../apps/frontend) (Vite, :5175, proxies `/api` here)
- MCP sibling: [`alignment-mcp-server.md`](alignment-mcp-server.md)
- Technique contract: [`alignment-technique-modes.md`](alignment-technique-modes.md)

## Routes the technique UI uses

| method | path | seam |
|---|---|---|
| GET | `/api/v1/cases` | `discover_cases` |
| GET | `/api/v1/cases/{id}` | `case_by_id` |
| GET | `/api/v1/cases/{id}/sites/{tooth}/signals` | `assemble_site_signals` (full taxonomy) |
| GET | `.../seated` · `.../landmarks` · `.../acceptance` | same reads as BFF adjust / deliver |
| POST | `.../re-preview` | measure-only re-read |
| POST | `.../rotation` · `.../mark-trench` · `.../fit-by-points` · `.../best-fit` | `application.adjust` tools |
| POST | `.../technique` | `{mode: deterministic\|intelligence, apply, ...}` → `run_technique` |

Refusals match the BFF split: 422 malformed, 409 gate, structured
`already_optimal`. Extra body fields are `extra=forbid`. Statuses are never
accepted from the client.

Session landing (status ladder, confirmation retirement) stays the BFF's. This
peer reports outcomes and the signal envelope so an operator can try the
technique without a second physics path.
