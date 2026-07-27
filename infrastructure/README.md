# Infrastructure — Phase 2 case-prep platform (Terraform)

Provisions the sandboxed automation platform from
[`docs/engagement/phase2-aws-infrastructure-plan.md`](../docs/engagement/phase2-aws-infrastructure-plan.md):
a no-egress Fargate worker fed by an SQS stage-1 → awaiting_seed → stage-2 split, with
private SSE-KMS storage and the alarms that make the human-in-the-loop and the safety gate
operable.

Conventions follow `wl-gateway-service` (`workspace*.tf` root, `modules/`,
`environments/`, `artech-{project}-{stage}-*` naming, the `{Environment,Project,Service,ManagedBy}`
tag block) — **except the backend: S3 with native locking** (`use_lockfile`, TF ≥ 1.10), not
TF Cloud `remote`.

## Layout

```
workspace-versions.tf   terraform block + S3 backend + provider pin
workspace.tf            provider, account/region data, root module call
workspace-variables.tf  root variables
backend.{dev,prod}.hcl  per-stage S3 backend config (bucket/key/region/use_lockfile)
environments/*.tfvars   per-stage inputs
modules/                network · kms · storage · queue · worker · observability
```

| Module | Creates |
|---|---|
| `network` | VPC with **no IGW/NAT**, 2 private subnets, S3 gateway + interface endpoints (sqs/kms/ecr/logs/secretsmanager/monitoring), worker SG (no ingress, egress 443 to endpoints only) |
| `kms` | customer-managed key, rotation on |
| `storage` | `cases` (versioned, SSE-KMS, TLS-only + KMS-enforced policy, lifecycle + incomplete-multipart cleanup, access logging), `previews`, `logs` buckets |
| `queue` | `stage1`/`stage2` queues + DLQs (redrive maxReceiveCount 3), `status-writeback`, all SSE-KMS |
| `worker` | ECR (immutable, scan-on-push), ECS cluster, least-privilege task/exec roles, **x86_64** sandboxed task def (read-only rootfs, non-root), scale-from-zero service on queue depth |
| `observability` | SNS ops topic, DLQ-nonempty / oldest-message-age / **stuck-awaiting-seed** / **false-confidence-rate** alarms |

## Run it

```bash
# 0. one-time: create the state bucket the S3 backend locks against (chicken-and-egg)
make bootstrap

# 1. init against a stage's backend, then plan/apply
make init  STAGE=dev
make plan  STAGE=dev
make apply STAGE=dev
```

State locking is S3-native (`use_lockfile = true` in `backend.*.hcl`) — concurrent applies
contend on a lock object in the state bucket; no DynamoDB table required.

> `terraform validate` passes offline. A real `plan`/`apply` needs AWS credentials and
> globally-unique bucket names (`artech-implantcad-{stage}-cases` etc. — adjust `project` if taken).

## Known limitations & next steps (from the plan grilling — [`../docs/engagement/phase2-plan-grilling.md`](../docs/engagement/phase2-plan-grilling.md))

This IaC already addresses several grill items: **DLQ + redrive + alarms**, **prefix-scoped
least-privilege IAM**, **no-egress sandbox**, **stuck-case / DLQ / false-confidence alarms**,
and **x86_64** (the arm64 Open3D segfault). Open, by design, until the data model lands:

- **KMS is via-S3-scoped, not yet per-case-context-pinned.** The task role restricts the key to
  `kms:ViaService = s3` — a real boundary, but not the per-case encryption-context match the plan
  markets. That needs a per-case scoped `sts:AssumeRole` session (2B) and is intentionally deferred.
- **Tenancy/`tenant_id` is assumed, not resolved.** The `tenant/*` S3 prefix scoping presumes the
  schema migration (`tenant_id`, `case_status` with `awaiting_seed`/`queued`/`assigned`,
  `processing_jobs.stage`) is applied first. Resolve tenancy → migrate → then these ARNs are stable.
- **No per-tenant in-flight cap.** `worker` caps total tasks at `max_capacity = 10`; a single
  bulk-submitting shop can still consume it. Add a per-tenant cap before high-volume onboarding.
- **Single region, no CRR/DR** wired yet — decide against the client's real RPO/RTO.
- The **stuck-awaiting-seed** and **false-confidence-rate** alarms watch `CasePrep/Quality` custom
  metrics the worker/API must emit; the alarms are inert until that telemetry (and the audit loop
  behind false-confidence) ships.
