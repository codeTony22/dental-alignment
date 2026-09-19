# packages/shared — shared types (Phase 1, not yet built)

Shared TypeScript DTOs / zod schemas reused by `apps/web` and `apps/api`.
The Phase 2 worker's **case manifest** (`apps/worker` `case.json`, mirroring
[`schema.sql`](../../docs/schema.sql) `implant_sites` / `restorations`) is the contract
these types will align with, so a portal case serializes straight into the automation pipeline.

Until this package exists, the operator UI hand-mirrors BFF wire types in
[`apps/product/src/api/client.ts`](../../apps/product/src/api/client.ts). See
[`docs/migration/product-bff-to-frontend-api.md`](../../docs/migration/product-bff-to-frontend-api.md)
for how that contract should move.
