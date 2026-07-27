<!-- Authored by a multi-agent workflow: 6 design lenses -> synthesis -> 2 adversarial reviews -> finalize. -->

# Dental-Implant CAD Lab — AWS Infrastructure & Automation Plan

## Executive Summary

This document specifies the AWS infrastructure and automation that runs the `case-prep` worker (`apps/worker`, Python, hexagonal, 63 tests) around a closed third-party CAD app (RealGUIDE), which we never script — we only pre-process the inputs it imports. The system is a thin, durable control plane (Supabase + a small always-on NestJS API on Fargate) that signs presigned multipart uploads, persists case state, and enqueues work; and a sandboxed, on-demand geometry worker on **ECS Fargate (x86_64/Linux)** that ingests untrusted scan meshes, localizes scan bodies, registers them against a known library mesh via a custom numpy/scipy ICP (Open3D's `registration_icp` segfaults on arm64; Open3D is used for DBSCAN only), derives 6-DoF implant pose, and runs a retention-aware confidence gate (PASS=auto-seed / FLAG=manual). The pipeline contains a **mandatory human seed step**, so it is split at `awaiting_seed` into two automated stages with a structurally un-bypassable human boundary between them. At MVP this boundary is two FIFO SQS queues + DLQs, each draining via an **event-source-mapped trigger that launches a Fargate task per message** (true scale-from-zero — there is no always-on poller); once localization is automatic the longer chain graduates to an **AWS Step Functions** Standard workflow with `waitForTaskToken` for the human seed, per-state Retry/Catch, and `Map` for per-implant parallelism. All scan data lives in a private, versioned S3 bucket encrypted with a customer-managed KMS key (rotation on) **bound to a per-tenant/per-case encryption context**, so the CMK is a genuine second access boundary, not just a co-located permission; the worker runs in a VPC with **no NAT/IGW** so generic internet exfiltration is impossible by routing, and the remaining AWS-API egress is constrained by **account-pinned endpoint policies** so a compromised task cannot reach other accounts' buckets or queues. Infrastructure is Terraform (chosen over CDK because Supabase/Stripe/Sentry are first-class non-AWS resources in one plan). Observability emits the program's two go/no-go numbers — **clear-rate** (measured live per case) and **false-confidence-rate** (estimated from a sampled ground-truth audit loop, since real cases have no held-out truth at inference time) — segmented by scan-body-type and case-type (retention), computed by a **trusted out-of-band Lambda** (not from inside the untrusted sandbox), to CloudWatch as dimensioned custom metrics with regression alarms. At ~300 cases/month the orchestration and worker compute are single-to-low-double-digit dollars; **the two dominant lines are the per-AZ interface VPC endpoints and the always-on HA API**, which put the honest HA bill at **~$160–230/mo** (see §4).

### Architecture diagram

```
                         ┌─────────────────────────────────────────────────────────────────┐
                         │  Browser (clinic / operator console)                              │
                         └───────┬───────────────────────────────────────┬──────────────────┘
                                 │ 1. presigned UploadPart URLs           │ operator: seed click,
                                 │    (parallel parts, direct PUT)        │ deliverable download
                                 ▼                                        ▼
              ┌────────────────────────────────┐           ┌───────────────────────────────┐
              │ S3  dac-cases  (SSE-KMS, CMK,  │◀──────────│ NestJS API (always-on Fargate,│
              │  per-case enc-context)         │  presign   │  min 2 / 2 AZ)                 │
              │  inputs/ outputs/ report/      │  Create/   │  - signs multipart presigns   │
              │  + dac-previews  + dac-logs    │  Complete  │  - writes case state (outbox) │
              └───────┬────────────────────────┘            │  - SendMessage → SQS          │
                      │ s3:ObjectCreated                     │  - Stripe webhooks            │
                      ▼                                      │  - SendTaskSuccess (server-   │
            ┌───────────────────────┐                        │    side token, 2B)           │
            │ validation Lambda     │                        │  - drains status-writeback q  │
            │ (in-VPC, no egress;   │                        └───┬───────────────┬───────────┘
            │  on-failure → DLQ):   │                            │ enqueue       │ status read
            │ magic/size/SHA gate   │            ┌──────────────────────┐   ┌──────────────┐
            │ → tag + enqueue;      │───enqueue─▶│ SQS stage1.fifo +DLQ │   │  Supabase    │
            │ reject → tag+delete   │            │ SQS stage2.fifo +DLQ │   │ Postgres+RLS │
            └───────────────────────┘            │ status-writeback q   │◀──│  (PITR)      │
                                                 └─────┬──────────┬─────┘   └──────────────┘
                                                       │ ESM →    │ ESM →         ▲ status
                                                       │ RunTask  │ RunTask       │
                                  ┌────────────────────▼──┐   ┌───▼───────────────┴────┐
                                  │ Fargate worker STAGE-1│   │ Fargate worker STAGE-2 │
                                  │ 1 vCPU/4GB, sandboxed │   │ 2 vCPU/8GB, sandboxed  │
                                  │ ingest→clean→localize │   │ register→gate→package  │
                                  │ → case=awaiting_seed  │   │ → case=ready/needs_rev │
                                  │ writes signed report  │   │ writes signed report   │
                                  │ to S3 (write-only)    │   │ to S3 (write-only)     │
                                  └───────────┬───────────┘   └───────────┬────────────┘
                                              │ VPC endpoints (no NAT/IGW), each with an
                                              │ account-pinned policy: S3(gw, bucket-Deny),
                                              │ SQS, KMS, ECR api/dkr, CW Logs, STS(off for
                                              │ MVP worker), Secrets
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────┐
   │  Step Functions (Standard) — Phase 2B, gated by enable_step_functions; replaces the    │
   │  stage-2 consumer: runTask.sync steps · waitForTaskToken seed (server-side token) ·    │
   │  Map per-implant · Retry/Catch → ManualFallback. SQS stays as ingress; a starter       │
   │  Lambda StartExecution(name={case_id}:{submission_uuid}).                               │
   └──────────────────────────────────────────────────────────────────────────────────────┘

   Observability: worker → signed accuracy-report.json to S3 (write-only). A TRUSTED
   out-of-band metrics Lambda (gateway S3 endpoint) parses the report and emits
   PutMetricData → CasePrep/Quality (ClearRate live; FalseConfidenceRate over the audited
   sample) per ScanBodyType×Retention; alarms → SNS → Slack / PagerDuty; Sentry
   (web/api/worker, PII-scrubbed); CloudTrail data events.
```

---

## 1. Compute — the Fargate worker

### 1.1 First-principles framing

Four irreducible requirements drive every choice in this layer:

1. **Run one untrusted, memory-heavy, CPU-bound geometry job to completion**, on demand, at ~300 cases/month (~10–15/day, bursty), with no GPU.
2. **Contain a hostile mesh.** STL/PLY parsers (trimesh, Open3D) have had memory-safety CVEs; the only identifier is a non-PII case label. The blast radius of a malicious upload must be: no network pivot, no exfiltration to the internet *or to another account's AWS resources*, bounded CPU/memory/time, no host persistence, **and no ability to forge the safety metric**.
3. **Survive redelivery.** SQS is at-least-once; Fargate tasks can be reclaimed or die mid-run. The same logical unit of work must be safe to run twice and converge to one correct output — including the localization step, whose tooth↔cluster mapping must be made deterministic (§1.8, §1.10).
4. **Cost sub-linearly *in the variable lines*.** The worker is *not* always-on; we pay only while a case processes (minutes/case). The bill is dominated by a fixed floor (endpoints + HA API), so the design goal is to keep that floor minimal, not to pretend compute is the driver.

Anything not justified by these (always-on workers, GPU at 2A/2B, oversized tasks, broad IAM, metric emission from inside the sandbox) is cut.

### 1.2 Fargate vs Lambda vs Batch

| Option | Verdict | Reasoning against the four requirements |
|---|---|---|
| **Lambda** | **Rejected for the geometry stage** | 10 GB memory is borderline, but the 15-min wall-clock limit and `/tmp` ephemeral cap are fatal for 20–100 MB STLs that tessellate into multi-GB working sets and multi-start ICP that runs minutes. The Open3D + native-BLAS layer story is painful (large, finicky wheels — we already hit an arm64 segfault). Lambda is right only for the *thin* control plane (the S3-event "validate + enqueue" hop, the per-message `RunTask` trigger, and the trusted metrics Lambda), never the dense pipeline. |
| **AWS Batch** | **Deferred to 2C** | Batch is the correct home for 2C GPU inference (array jobs, GPU EC2 compute environments, spot bidding). For 2A/2B it adds a scheduler we don't need — our orchestration is a per-message `RunTask` trigger then Step Functions, both of which invoke Fargate tasks directly. Adopting Batch now would duplicate that. |
| **ECS Fargate (Linux)** | **Chosen for 2A/2B** | No server management; per-second billing (pay only while a case runs); `awsvpc` gives each task its own ENI/SG for true no-egress isolation; native read-only-rootfs / dropped-caps / non-root / ulimit support; ephemeral storage to 200 GB; and a clean upgrade path — the *same* task definition is invoked by a per-message `RunTask` trigger today and by a Step Functions `ecs:runTask.waitForTaskToken`/`.sync` state later with **zero image changes**. |

**Net:** Fargate runs the heavy worker. Tiny Lambdas front the S3 `ObjectCreated` validation/enqueue hop, the per-message `RunTask` launch, and the trusted post-hoc metric emission — none of which touch the dense pipeline.

### 1.3 Container image

One image, two runtime modes selected by container `command`/env (`stage1` / `stage2`) — not two images — so the registry, scanning, and provenance surface stays single. The same image carries the `case-prep` CLI for local repro.

```dockerfile
# ---- builder ----
FROM python:3.11-slim-bookworm@sha256:... AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libgl1 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml requirements.lock ./
RUN pip install --prefix=/install --require-hashes -r requirements.lock

# ---- runtime ----
FROM python:3.11-slim-bookworm@sha256:... AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -u 10001 app
COPY --from=builder /install /usr/local
COPY src/ /app/src/
ENV PYTHONPATH=/app/src \
    OPEN3D_CPU_RENDERING=true MPLBACKEND=Agg HOME=/tmp
# NOTE: thread caps (OMP/OPENBLAS/MKL_NUM_THREADS) are NOT baked here — they are
# set per task-def (§1.5) so stage1=1 and stage2=2 stay coupled to the actual vCPU.
USER 10001:10001
ENTRYPOINT ["python", "-m", "case_prep.worker"]
```

Decisions:

- **`python:3.11-slim-bookworm`, digest-pinned.** 3.11 is the production interpreter (the spike's 3.9 was only the local Open3D-0.18 arm64 wheel; `apps/worker/.venv` is 3.9 for exactly this reason). Slim shrinks attack surface; digest-pinning defeats tag mutation.
- **Multi-stage** so `build-essential` (compilers — prime exploit primitives) never ships in runtime. Runtime carries only `libgl1`/`libgomp1`/`libglib2.0-0`, which Open3D/trimesh genuinely `dlopen`.
- **Fully pinned, hashed lockfile.** `pyproject.toml` uses floors (`numpy>=1.24`, `open3d>=0.18`). For the container we generate `requirements.lock` with exact `==` and `--hash=sha256:...` per wheel (`uv pip compile --generate-hashes`), installed `--require-hashes`. This is the single most important supply-chain control for a sandbox parsing untrusted input: a poisoned transitive dep cannot slip in on rebuild.
- **Thread pinning lives in the task def, not the image** (fix for L1). Baking `OMP_NUM_THREADS=2` would oversubscribe a 1-vCPU stage-1 task (2 BLAS threads on 1 vCPU → context-thrash, unpredictable wall-clock that distorts cost/timeout estimates). The task def sets `OMP_NUM_THREADS` / `OPENBLAS_NUM_THREADS` / `MKL_NUM_THREADS` = `1` for stage1 and `2` for stage2, so threading tracks vCPU.
- **Non-root `uid 10001`, `HOME=/tmp`** so the read-only rootfs doesn't break libraries that scribble caches.
- **ECR:** private repo `dental/case-prep-worker`, immutable tags (`git-<sha>`), scan-on-push (ECR enhanced scanning), KMS-encrypted at rest, lifecycle keeping the last ~10–20 tagged and expiring untagged after 7 days. CI builds with `docker buildx`, signs (cosign); the task def references the image **by digest**, not tag, so a deploy is an explicit, auditable pin.

### 1.4 ARM64 vs X86_64 — the load-bearing call

**Build and run the production worker on `X86_64` (Fargate, Linux) for 2A/2B**, while keeping the image arm64-buildable for local dev.

- The dev host is Apple Silicon and the spike hit a **hard arm64 failure**: Open3D 0.18's `registration_icp` *segfaults* on the macOS-arm64 wheel (exit 139) — which is why registration was rewritten as an in-house numpy/scipy ICP. We still depend on Open3D for DBSCAN (`cluster_dbscan`) in `localize()`, so the wheel must still load and run correctly in production. **Open3D's arm64 wheels are the fragile axis of this stack — the load-bearing reason to stay x86.**
- Graviton/ARM64 Fargate is ~20% cheaper per vCPU-hour, but at ~300 cases/month of on-demand minutes the worker spend is single-to-low-double-digit dollars (see §4). A 20% saving on a ~$5 line is noise. (This cost point is *secondary, decorative* confirmation — it is **not** the reason; the wheel risk is. We do not lean on the cost number.)
- Linux-x86_64 is Open3D's best-tested wheel target; it removes the variable that already bit us and keeps prod parity with manylinux wheels.

Therefore `runtimePlatform = { cpuArchitecture: X86_64, operatingSystem: LINUX }`. Pin the linux-x86_64 Open3D wheel hash; CI builds on x86 (or `buildx --platform linux/amd64`). **Revisit ARM64 at 2B**: if the linux-arm64 Open3D wheel passes the golden-case regression set **executed inside the actual sandboxed task def** (read-only rootfs, dropped caps, no GPU — see L3 below) on Graviton, flip the platform via a one-line task-def change gated by a CI matrix — not a rewrite.

> **Sandbox-load smoke test (L3).** Add a CI step that imports Open3D and runs `cluster_dbscan` **inside the real sandboxed task definition** (read-only rootfs, `cap_drop ALL`, no `/dev/dri`, no GPU) before 2A sign-off, on both x86 today and arm64 at the 2B revisit. `OPEN3D_CPU_RENDERING=true`/`MPLBACKEND=Agg` plus the locked-down rootfs can break Open3D's GL `dlopen` at import on some wheels; the arm64 segfault history shows this stack fails in exactly these ways, so we prove it in the sandbox, not on a permissive runner.

### 1.5 Task sizing

The job is **single-case, CPU-bound** (KD-tree ICP, 12-start clocking search, SVD/PCA, DBSCAN), working set 4–8 GB on dense meshes, not parallel across cases inside one task — concurrency comes from *more tasks*.

| Stage | vCPU | Memory | Ephemeral | Thread caps (task-def env) | Justification |
|---|---|---|---|---|---|
| **stage1** (ingest → clean → localization-prep → `awaiting_seed`) | **1** | **4 GB** (`4096`) | 21 GB (default) | `*_NUM_THREADS=1` | Mostly IO + parse + DBSCAN/PCA. 4 GB covers a 100 MB STL's working set with headroom. |
| **stage2** (register → gate → package → `ready`) | **2** | **8 GB** (`8192`) | 30 GB | `*_NUM_THREADS=2` | Multi-start trimmed ICP is the compute peak; 2 vCPU parallelizes BLAS/KD-tree (matched by the thread caps). 8 GB is the stated ceiling, chosen high so an adversarial dense mesh OOM-*flags* rather than OOM-kills silently. |

- **Fargate vCPU↔memory are not free-form.** 1 vCPU allows 2–8 GB; 2 vCPU allows 4–16 GB. Both rows are valid grid points. If stage2 profiles above 8 GB on worst real cases, the next legal step is **2 vCPU / 16 GB** — do that before adding vCPUs.
- **Ephemeral storage** is encrypted by default on Fargate (AES-256), satisfying "encryption at rest" for scratch; the stage2 bump to 30 GB is defense-in-depth against a decompression-bomb STL (the SHA-verified, size-capped upload is the first line — see §3.4 for the multipart-specific size enforcement).
- **Right-sizing is a tuning task.** Ship stage2 at 2 vCPU / 8 GB, emit peak-RSS and wall-time (§5), tighten after ~50 real cases. Starting *high* is the correct bias for untrusted input: an under-provisioned task that OOM-kills mid-ICP looks like a flaky pipeline; an over-provisioned one costs cents.
- **Cost sanity:** 2 vCPU / 8 GB on-demand x86 ≈ $0.04048/vCPU-hr + $0.004445/GB-hr ⇒ ~$0.1165/hr. At ~5 min/case × 300 (≈2 implant sites avg) ⇒ ~27.5 task-hours/mo ⇒ **~$3–6/mo of worker compute** (verified floor ~$2.77 at 1 implant). This is *not* the bill driver (§4).

> **Note on shared vs separate task definitions.** The compute and orchestration lenses agreed on **two separate task definitions** (stage1 1 vCPU/4 GB, stage2 2 vCPU/8 GB) sharing **one image**. Two task defs let each half be sized independently for cost; one image keeps provenance single. This supersedes any "one task def parameterized by `STAGE`" reading.

### 1.6 Sandbox (untrusted-mesh containment)

Every control expressed as concrete task-def / SG / endpoint settings:

- **`networkMode: awsvpc`**, task ENI in **private subnets, no NAT, no IGW.** The task SG has **zero outbound rules** except `tcp/443` to the VPC-endpoint SG (and the S3 prefix list). No egress to the internet exists by routing.
- **VPC endpoints only, each with an account-pinned endpoint policy (fix for H2):** **Gateway endpoint for S3** (free) with an explicit **`Deny` on every bucket except `dac-cases-*`/`dac-previews-*`**; **Interface endpoints for SQS, ECR-api, ECR-dkr, CloudWatch Logs, KMS** (and Secrets Manager where the API/execution role needs it). **STS interface reachability is OFF for the MVP worker** (it has no `AssumeRole` need until the Step Functions per-case session). Every interface endpoint policy carries `"Condition": {"StringEquals": {"aws:PrincipalAccount": "111122223333"}}` and resource ARNs limited to this account's queues/key/log-groups — so a compromised worker cannot write to another account's SQS/S3 or assume a foreign role through the endpoint.
- **`readonlyRootFilesystem: true`.** All writes go to a mounted `tmpfs`/ephemeral scratch at `/tmp` (`HOME=/tmp`), wiped when the task ends.
- **`user: "10001:10001"`** (non-root, set in image and re-asserted in task def).
- **`linuxParameters`:** `capabilities.drop: ["ALL"]`; `initProcessEnabled: true` (PID-1 reaping so zombie geometry subprocesses don't pile up); a **custom seccomp profile** to block exotic syscalls (`ptrace`, `mount`, etc.).
- **`ulimits`:** `nofile` capped; **wall-clock bounded by SQS visibility + a hard in-process watchdog** that aborts a case after N minutes → FLAG/DLQ (defeats a complexity-bomb that spins ICP forever). Memory bounded by the task's hard limit (OOM-kill → DLQ → manual, never a host effect).
- **No metric emission from inside the sandbox** (fix for M5/H2 metric-channel). The worker writes only the **signed `accuracy-report.json` to S3 (write-only)**; a trusted out-of-band Lambda emits CloudWatch metrics (§3.7, §5.4). The sandbox therefore has no `cloudwatch:PutMetricData` grant and no `monitoring` endpoint, removing both the covert channel and the alarm-poisoning surface.
- **Fargate platform version `1.4.0+`** (encrypted ephemeral storage, runtime-monitoring hooks).
- **Recommended: GuardDuty ECS Runtime Monitoring** on the cluster, so a sandbox-escape attempt is detected and alarmed, feeding the audit requirement.

### 1.7 IAM — two distinct roles per task

Conflating the execution role and the task role is the most common Fargate IAM mistake; they are deliberately separate.

**Task execution role** (used by the ECS agent to launch the container — never your code):
- `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` on the one worker repo.
- `logs:CreateLogStream`, `logs:PutLogEvents` on the worker log group.
- `kms:Decrypt` on the ECR/logs CMK if CMK-encrypted.
- `secretsmanager:GetSecretValue` only where a task injects a secret as an env var at start.
- **No S3, no SQS, no `RunTask`.**

**Task role** (assumed by the worker process):
- **S3:** `s3:GetObject` on `inputs/tenant/*/case/*/*`; `s3:PutObject` on `outputs/*`, `report/*`, and the previews bucket. **No `s3:DeleteObject`** (lifecycle handles retention); **no `s3:ListBucket`** (it always knows the exact key); **no `GetObject` on `outputs/`** (write-only deliverables).
- **SQS:** `sqs:ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes` on the two stage queues; `sqs:SendMessage` on the **status-writeback queue only** (§3.6). **No `SendMessage`** on the stage queues (the API is their only producer).
- **KMS (the data CMK):** `kms:Decrypt`, `kms:GenerateDataKey`, conditioned both `kms:ViaService = s3.us-east-1.amazonaws.com` **and** an **encryption-context match** so the key is usable only for the case the task is processing (§3.2 — fix for C1).
- **Observability:** **none.** Metrics are emitted by the trusted Lambda, not the worker (§3.7).
- Trust policy: assumable only by `ecs-tasks.amazonaws.com`, `aws:SourceArn` scoped to the worker cluster (anti confused-deputy).

All actions are resource-scoped by ARN with prefix conditions; no `Resource: "*"` except the unavoidable VPC-Lambda ENI block (§3.5). **Per-case tightening (Step Functions era):** the state machine hands the worker a scoped-down session via `sts:AssumeRole` with an inline session policy pinning `s3:prefix` and the **KMS encryption context** to `tenant/${tenant_id}/case/${case_id}`, so a compromised task cannot name *or decrypt* another case's object. Full IAM policy documents are in §3.5.

### 1.8 Job lifecycle — trigger, heartbeat, idempotency

This runtime contract is identical whether the trigger is the MVP per-message `RunTask` launch or a later Step Functions `runTask` — only "what starts the task and where the input comes from" changes. **Build the heartbeat abstraction pluggable from day one** (SQS `ChangeMessageVisibility` vs `SendTaskHeartbeat`) so 2B is not a retrofit.

- **Trigger (MVP):** there is **no always-on poller** (fix for H2). An **event-source mapping / EventBridge Pipe on each FIFO queue invokes a small launcher Lambda that calls `ecs:RunTask`** for the message — true scale-from-zero, min capacity 0, no scaling policy. The message carries `{ tenant_id, case_id, stage }` (no `attempt` — see below); bytes stay in S3. The launched task reads the one message body passed to it. (If a future profiling shows per-message `RunTask` launch latency is unacceptable, the documented alternative is an ECS service with a **backlog-per-task** target-tracking policy = `ApproximateNumberOfMessagesVisible / RunningTaskCount`, *not* raw queue depth — but that re-introduces always-on cost and is not the MVP default.)
- **Heartbeat:** a background thread calls `ChangeMessageVisibility` on an interval well under the timeout (every ~60 s, extending to +15 min) while the case makes progress. If the worker dies, heartbeats stop, the message reappears, another task retries — bounded by `maxReceiveCount=3` → DLQ. Under Step Functions the equivalent is `SendTaskHeartbeat`.
- **Idempotency:** the logical unit of work is keyed on **`case_id:stage`** (the producer-stable key). The redelivery counter (`attempt`) is **observability-only** and never participates in dedup or output-key identity (fix for H5/M2). Mechanisms:
  1. **Deterministic output keys** under `tenant/{t}/case/{c}/{kind}/{content_hash}` — a redelivered message overwrites the same objects harmlessly. The key includes the **localization-result hash** so that a re-run which detects a *different* cluster count writes to a *different* prefix rather than silently overwriting a prior committed result (fix for H4).
  2. **Deterministic tooth↔cluster mapping** (fix for H4). DBSCAN label ids are not stable run-to-run, so the worker sorts/seeds clusters by a **stable geometric key** (centroid lexicographic order), never by raw DBSCAN label, before the `zip(resolved_sites, order)` assignment. The `_DONE` completion marker is written **only on the `declared == detected` clean path**; when `detected != declared` the case **FLAGs to manual** (surfacing `unresolved_sites`) and commits no auto pose. This closes the "attempt 1 detects 3, attempt 2 detects 4 → tooth 23's pose lands under tooth 24's key" hole.
  3. **Write-to-temp-then-atomic-finalize.** Outputs land under a per-attempt scratch prefix; only on success does the worker write the single completion marker (`.../stage1/_DONE` or a status row) that flips case state. On the next delivery, if `_DONE` exists for `(case_id, stage)`, the worker acks and returns — no recompute.
  Because the pipeline is otherwise pure-deterministic (fixed-seed numpy/scipy ICP, no wall-clock/RNG in the committed math) **and** the cluster ordering is now stabilized, re-running yields byte-identical poses — "overwrite the same key" is genuinely safe.

### 1.9 GPU / Batch (2C, out of 2A/2B scope)

2A/2B have no GPU and stay on CPU Fargate. **2C ML inference** (learned localizer / scan-body classifier) is the only GPU workload, and Fargate has no GPU. Introduce **AWS Batch on a GPU EC2 compute environment** (`g5`/`g4dn`, spot-biased, scale-to-zero) running a *separate* GPU image, invoked as an additional Step Functions branch — different image, sizing, IAM, and cost line. The CPU compute layer here does not change.

### 1.10 Localization determinism contract (new — H4 root cause)

Because §1.8's idempotency rests on it, the determinism contract for `localize()` / `orchestrator.run_case` is stated explicitly as a 2A acceptance criterion:

- Cluster ordering is derived from a **stable geometric sort** (centroid lexicographic), not DBSCAN label ids.
- `usable = locs[:declared]` and the `zip(resolved_sites, order)` mapping are computed over that stable order.
- The localization-result hash (count + ordered centroids, quantized) is part of the output key and the `_DONE` gate.
- `detected != declared` ⇒ **FLAG to manual**, never an auto commit; `unresolved_sites` is surfaced.

This is a small, testable change to `apps/worker/src/case_prep/pipeline/orchestrator.py` and `engine.localize`, and is gated by a redelivery-determinism unit test (run the same borderline mesh twice; assert identical tooth↔pose assignment or identical FLAG). Tracked in open-question form against the worker repo, not assumed.

---

## 2. Orchestration — SQS-split MVP and Step Functions graduation

The irreducible requirement: **run an automated chain, pause for a human one-click seed, run a second automated chain, never lose or double-process a case, and fall back to a human on any failure.** The orchestration wraps the existing `case_prep.pipeline.orchestrator.run_case(case_dir) -> CaseResult`, which already produces a per-implant `gated: List[(RegisteredImplant, GateDecision)]` where `GateDecision.passed` is the PASS=auto-seed / FLAG=manual signal — it does not reach inside it.

**DB contract — requires a migration that is a hard gate on 2B (fix for M1).** The orchestration depends on columns that **do not yet exist** in `docs/schema.sql`. Today the schema has `processing_jobs(id, case_id, status, assigned_worker, attempts, result_key, error, queued_at, started_at, finished_at)` — note **no `stage`** — and `case_status` enum `draft|submitted|in_design|ready|delivered|rejected` — note **no `awaiting_seed|queued|assigned`** — and `cases` has **`owner_id`, not `tenant_id`**. The entire two-stage claim-lock, the per-stage DLQ-drain, the `(case_id, stage)` idempotency upsert, and the `tenant/{tenant_id}/...` S3/IAM scoping are **impossible until a migration lands**. 2B is gated on a migration that:
1. adds `stage` to `processing_jobs` with a `UNIQUE(case_id, stage)`;
2. extends `case_status` with `awaiting_seed`, `queued`, `assigned`;
3. resolves tenancy (open-question #11: `tenant_id == owner_id` for one-shop-one-tenant, or an org id above logins) and adds the `tenant_id` column used by the key layout and IAM.

Until that migration is merged and applied in staging, the claim-lock and idempotency designs below are **specified-but-not-buildable**; this is called out at the relevant steps rather than presented as settled.

**Why split-then-graduate:** at 300 cases/mo the cost delta between SQS and Step Functions is rounding error; the real axis is complexity vs resumability. While localization is still a manual one-click seed, the automated tail (really just stage-2) is short and coarse whole-stage redrive is adequate — the SQS split is cheaper to build and reason about. Once localization is automatic, the stage-2 chain lengthens (registration → abutment interface → manufacturability/QC → packaging), per-step checkpointing earns its keep, and we graduate.

### Part 1 — MVP: SQS jobs queues + DLQ across the human boundary

#### 2.1 Topology

```
NestJS API ──(submit)──▶ stage1.fifo ──(ESM → RunTask)──▶ [Fargate stage-1] ──▶ case = awaiting_seed
                                              │ (poison/exhausted)
                                              ▼
                                         stage1-dlq.fifo ──▶ EventBridge ──▶ operator "needs triage"

Operator console ──(seed click)──▶ NestJS API ──▶ stage2.fifo ──(ESM → RunTask)──▶ [Fargate stage-2] ──▶ ready / needs_review
                                                                       │ (poison/exhausted)
                                                                       ▼
                                                                  stage2-dlq.fifo ──▶ EventBridge ──▶ operator
```

Two **separate queues, each with its own event-source-mapped launcher**, not one queue with a branch. There is no automated path from stage-1 completion to a stage-2 message — only the operator's authenticated `POST` enqueues stage-2. This is what makes the human step structurally un-bypassable. **There is no long-running "SQS-poller" service** (fix for H2); the launcher is event-driven and the worker is min=0.

#### 2.2 FIFO vs Standard — use FIFO

Both queues are **FIFO** (`*.fifo`), `ContentBasedDeduplication=false` with an explicit `MessageDeduplicationId`.

- **Exactly-once enqueue** is the property we want. The API may retry `POST /submit` after a blip; the operator may double-click "seed". FIFO's 5-minute dedup window collapses both, keyed on **`MessageDeduplicationId = "{case_id}:{stage}"`** — the producer-stable key, **with no `attempt` component** (fix for H5/M2). There is exactly one legitimate stage-1 enqueue and one stage-2 enqueue per case, so dropping `attempt` is what makes dedup actually collapse the duplicates it is meant to. Worker-side redelivery (SQS `maxReceiveCount`) is a *different* mechanism and must not share a key component with producer dedup.
- **`MessageGroupId = case_id`** serializes a case's messages so stage-1 and a stage-1 retry never race on the same S3 prefix.
- **Throughput is a non-issue:** ~300 cases/mo (≈1.6 msg/hr) against FIFO's 300 msg/s ceiling — orders of magnitude of headroom. Standard queues would force a custom dedup table for a worse guarantee.

> This **resolves the contradiction** between the orchestration lens (FIFO) and the cicd lens (which suggested Standard). FIFO wins: it gives exactly-once enqueue at zero throughput cost. The earlier draft's `:{attempt}` in the dedup id was itself a defect (it made every retry a new key, defeating dedup); the corrected key is `{case_id}:{stage}` everywhere a *dedup or output identity* is needed, and `attempt` is reserved strictly for log/metric tags.

#### 2.3 Queue settings

| Setting | stage1.fifo / stage2.fifo | Rationale |
|---|---|---|
| `VisibilityTimeout` | **900 s (15 min)** | Must exceed worst-case processing or SQS redelivers a still-running job; combined with heartbeat extension. |
| Heartbeat extension | `ChangeMessageVisibility` ~every 60 s while processing | Worker extends its own lease for long cases instead of one huge static VT (which would delay redrive of a *crashed* worker). |
| `maxReceiveCount` | **3** → DLQ | Two transient retries (OOM on a pathological mesh, S3 5xx, spot reclaim) then dead-letter. A 4th rarely succeeds and just delays the human fallback. |
| `RedrivePolicy.deadLetterTargetArn` | `stage{N}-dlq.fifo` | Per-stage DLQ so triage knows which half failed (a FIFO main queue must DLQ to a FIFO DLQ). |
| DLQ → pipeline redrive | **None — terminal to manual** (fix for H3-cost/H3-ops) | We do **not** auto-redrive DLQ→source. A dead-lettered clinical case is a terminal "human handles it in RealGUIDE" outcome (§2.5). The earlier `redrive_allow_policy: DLQ→main` line was wrong on two counts: `RedriveAllowPolicy` is a DLQ-side attribute declaring permitted *sources*, not a redrive-back mechanism (redrive-back is a separate `StartMessageMoveTask`), and FIFO source→DLQ move does not preserve `MessageGroupId` ordering. The line is removed. |
| `MessageRetentionPeriod` | 4 days main / **14 days DLQ** | DLQ retention long enough to triage over a weekend/holiday. (`awaiting_seed` durability comes from Postgres+PITR, **not** queue retention — see note below.) |
| `ReceiveMessageWaitTimeSeconds` | 20 (long polling) | Avoid empty-receive churn on the ESM. |
| KMS | SSE-SQS with the project CMK | Bodies carry opaque `case_id` + S3 keys (no PII); encryption-at-rest is mandated project-wide. |

> **`awaiting_seed` durability is Postgres, not SQS.** Between stage-1 completion and the operator's seed click, the case sits in `cases.status='awaiting_seed'` in the DB (PITR-backed), **not** in any queue. Nobody should "fix" a perceived expiry by lengthening queue retention; there is no queued message during the human wait.

#### 2.4 Retry / backoff layering

Two deliberate layers: **in-process** bounded exponential backoff with jitter (3 tries, 0.5→2 s) around idempotent IO (S3 `Get`/`Put`, DB update) absorbs blips without burning an SQS receive; **queue-level** redelivery (up to `maxReceiveCount=3`) handles crashes/poison, with the visibility timeout as the backoff between redeliveries. The in-process retry counter is local and **never** propagated into a dedup or output key.

The worker **fails closed**: the first action on receive is a conditional DB claim `status='running', attempts=attempts+1, assigned_worker=<task-arn>` guarded by `WHERE status in ('queued','running') AND (assigned_worker IS NULL OR started_at < now()-interval '15 min')` — the same claim-lock pattern the portal already uses for technician assignment. **This claim, not the SQS dedup or the Step Functions execution name, is the authoritative single-active-run guard** (see §2.10, L2). *Requires the `stage` column from the §2 migration.*

#### 2.5 Dead-letter → manual fallback (the safety net)

A DLQ message is **not** a silent retry; it is a case the automation has given up on, which a human must now handle in RealGUIDE — a **normal terminal outcome, not a 3am page**. A small **DLQ-drain Lambda** (event-source-mapped to each DLQ; not Fargate — it does no geometry) idempotently:

1. `UPDATE processing_jobs SET status='failed', error=<last cause> WHERE case_id=… AND stage=…`.
2. Transitions `cases.status` to the manual lane (`in_design`) and emits a domain event to the portal outbox so the operator console shows the case with the failure reason attached.
3. Publishes a `PipelineFallback{stage, case_type, scan_body_type}` signal (via the trusted-Lambda metric path, not from inside any sandbox) and an actionable Slack alert.

We alarm on the *rate* (§5), not each occurrence.

> **Both control-plane Lambdas have on-failure destinations (fix for M3).** The validation Lambda and the DLQ-drain Lambda are the spine of the safety net; an unhandled exception in either (KMS throttle, an unanticipated parse, a transient DB error) must not let a case **vanish**. Each is configured with an **on-failure destination → a dedicated `lambda-dlq` SQS queue**, alarmed on depth ≥ 1. An upload that never validates, or a dead-letter that never drains, surfaces to an operator rather than being silently dropped after Lambda's 2 async retries.

#### 2.6 How the NestJS API enqueues — transactional outbox

The API is the **only** writer to the stage queues. Both enqueue points use a transactional outbox to avoid the dual-write problem (DB row "queued" but the SQS send failed, or vice-versa):

```ts
// inside one Postgres transaction
await tx.processingJobs.insert({ caseId, stage: 'stage1', status: 'queued', attempts: 0 });
await tx.cases.update(caseId, { status: 'queued' });
await tx.outbox.insert({
  topic: 'enqueue.stage1',
  dedupId: `${caseId}:stage1`,          // producer-stable, NO attempt component
  body: { caseId, tenantId, stage: 'stage1', inputKeys, libraryVersion },
});
// a relay drains `outbox` → sqs.sendMessage({ MessageGroupId: caseId,
//   MessageDeduplicationId: `${caseId}:stage1` }); marks the row sent.
```

The relay makes enqueue at-least-once; FIFO dedup on `{case_id}:{stage}` makes the *effect* exactly-once across producer retries. **Stage-2** is the operator seed action `POST /operator/cases/:id/seed` (service-role, role-checked, audited), `dedupId = ${caseId}:stage2`, flipping `cases.status` from `awaiting_seed` to `queued`. The seed payload (per-implant ROI centroids / picked points) is **bounds-checked server-side** (untrusted human input, see M3-security note in §2.8) and persisted to S3 under the case prefix so the stage-2 worker reads it deterministically.

#### 2.7 Idempotency end-to-end

The single producer-stable key `case_id:stage` is enforced at **four** layers; `attempt` is observability-only and appears in **none** of them:

| Layer | Mechanism |
|---|---|
| Queue | FIFO `MessageDeduplicationId = {case_id}:{stage}` (5-min window) |
| DB claim | conditional `UPDATE … WHERE status in ('queued','running') …` (second consumer no-ops) — **authoritative** single-active guard |
| Compute | deterministic S3 keys `tenant/{t}/case/{c}/{kind}/{content_hash}` incl. localization-result hash — a re-run overwrites in place, a *different-count* re-run writes a new prefix (H4) |
| Result write | `processing_jobs` upsert keyed on `(case_id, stage)` (*requires `stage` column*) |

#### 2.8 (Stage-2 seed input is untrusted)

The operator seed payload — per-implant ROI centroids / picked points — is **untrusted input from a human** and steers the clinical registration pose. Before it is persisted to S3 and consumed by stage-2, the API **bounds-checks** it (point count ≤ declared sites, coordinates within the scan's bounding box, finite values). This is the MVP analogue of the Step Functions `SendTaskSuccess` payload validation (§2.11 / M3-security).

### Part 2 — Graduation: AWS Step Functions

**Trigger to migrate:** when localization graduates from operator one-click to automatic FPFH/ML, the stage-2 chain grows and coarse whole-stage redrive wastes minutes of mesh compute re-doing passed steps. At that point **SQS stays as the ingress buffer** and now triggers a **Standard** state machine instead of a Fargate task directly. The `stepfn` Terraform module ships from day one gated behind `var.enable_step_functions = false`, so 2B is a one-flag flip, not a new build.

**Why Standard, not Express:** `waitForTaskToken` and long waits (the human seed can take hours) are only supported on Standard; Express caps at 5 min with no callbacks. Standard's exactly-once execution semantics match a non-idempotent clinical workflow. Cost: ~25–35 transitions/case × 300/mo × $0.025/1k ≈ **$0.225/mo** — negligible. (This Standard-vs-Express call is correct and not a defect.)

#### 2.9 State machine shape

```
Start
 └─ IngestAndScaleGate        (Fargate runTask.sync; Retry transient; Catch → ManualFallback)
 └─ MeshHygiene               (Fargate .sync; Catch → ManualFallback)
 └─ LocalizeScanBodies        (Fargate .sync; Catch BelowQualityThreshold → AwaitOperatorSeed)
 └─ Choice: localization confident?
       ├─ yes ─▶ RegisterAllImplants (Map)
       └─ no  ─▶ AwaitOperatorSeed   (sqs:sendMessage.waitForTaskToken; token stays SERVER-SIDE;
                    │                  heartbeat+timeout; Catch Timeout → EscalateSeed)
                    └─▶ RegisterAllImplants (Map)
 └─ RegisterAllImplants  (Map over implant_sites, MaxConcurrency=4)
       └─ per item: RegisterImplant (Fargate .sync) → DerivePose → ConfidenceGate (Choice PASS/FLAG)
 └─ Choice: all implants PASS?
       ├─ yes ─▶ AbutmentInterface ─▶ Manufacturability ─▶ Package ─▶ MarkReady (Succeed)
       └─ any FLAG ─▶ RouteToManual (Lambda: case → in_design, FLAG reasons attached) ─▶ Succeed
```

Key decisions:

- **The human seed is `waitForTaskToken`**, not a poll loop. The task token is a **bearer credential and must never leave the server** (fix for M3-security). The state machine writes the token to an SQS message that the **NestJS API drains server-side**; the API stores the token keyed by `case_id`. The **operator console only ever references the case_id**, never the token. When the operator clicks seed and is authorized, the API looks up the token, validates/bounds-checks the seed payload, and calls `SendTaskSuccess(taskToken, seedResult)`. `HeartbeatSeconds` + `TimeoutSeconds` (e.g. 24 h placeholder) catch an un-actioned seed and **escalate**, then fall back to manual — it never hangs forever.
- **`Map` for per-implant parallelism**, mirroring `run_case`'s per-site loop. `MaxConcurrency: 4` bounds memory (each implant registration is its own 4–8 GB working set; we will not run 6 at once).
- **`ToleratedFailurePercentage: 0`:** an *errored* implant fails the case to manual; a *FLAGged* implant is a normal `Choice` outcome, not an error.
- **Routing-to-manual is `Succeed`, not `Fail`.** A FLAGged or dead-lettered case is a *correct, expected* outcome of a safety gate. `Fail` is reserved for genuine infrastructure exhaustion. **`RouteToManual` is implemented as a `Task` invoking a Lambda, then `Succeed`** — *not* a misused `sfn:sendTaskSuccess` (fix for H3): there is no waiting task to resume here, so a `SendTaskSuccess` call with no token would throw `InvalidToken` and, being the most common non-happy path, would fail the execution and misclassify the gate's normal output as infra failure. The Lambda flips `cases.status='in_design'` with FLAG reasons and notifies the operator. It also carries a `Catch → ManualFallback`.

#### 2.10 Retry / Catch policy per state

| State | Retry | Catch |
|---|---|---|
| Ingest / Hygiene / Register (Fargate) | `States.TaskFailed`, ECS throttles: 3×, 2 s, ×2, FULL jitter. `States.QueryEvaluationError`: 0 (never retry a logic bug) | `States.ALL` → `ManualFallback` (assign `$err`) |
| LocalizeScanBodies | transient 3× | custom `BelowQualityThreshold` → `AwaitOperatorSeed`; `States.ALL` → `ManualFallback` |
| AwaitOperatorSeed | — (token wait) | `States.Timeout`/`HeartbeatTimeout` → `EscalateSeed` → (re-timeout) → `ManualFallback` |
| Map / RegisterAllImplants | per-item already retried | `States.ExceedToleratedFailureThreshold` / `States.ALL` → `ManualFallback` |
| RouteToManual (Lambda) | transient 3× | `States.ALL` → `ManualFallback` |
| Package | transient 5× (idempotent S3 write) | `States.ALL` → `ManualFallback` |

#### 2.11 Idempotency under Step Functions

Standard gives exactly-once *execution*, but each Task can still be retried, so the four-layer idempotency from §2.7 holds, keyed on `case_id:stage` (the per-task `attempt`/`RetryCount` is observability-only and is **not** part of the S3 output key — same correction as MVP). **Execution `name = {case_id}:{submission_uuid}`, not `case_id` alone** (fix for L2): Standard retains execution history only 90 days, and `ExecutionAlreadyExists` is keyed on name within that window, so `name=case_id` would (a) fail to dedup a legitimate re-submit after 90 days and (b) make a failed/manual case un-re-drivable forever under the same name. The **DB claim (§2.4) is the authoritative single-active-run guard**; `name=…:{submission_uuid}` is best-effort dedup within the window.

#### 2.12 ASL sketch (core flow, JSONata)

```json
{
  "Comment": "Implant case-prep pipeline (post-localization-automation). Standard workflow.",
  "QueryLanguage": "JSONata",
  "StartAt": "IngestAndScaleGate",
  "States": {
    "IngestAndScaleGate": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": {
        "Cluster": "casePrepCluster",
        "TaskDefinition": "casePrepWorker:stage-ingest",
        "LaunchType": "FARGATE",
        "Overrides": { "ContainerOverrides": [{
          "Name": "worker",
          "Environment": [
            { "Name": "CASE_ID", "Value": "{% $states.context.Execution.Input.caseId %}" },
            { "Name": "TENANT_ID", "Value": "{% $states.context.Execution.Input.tenantId %}" },
            { "Name": "STEP", "Value": "ingest" }
          ]
        }]}
      },
      "Retry": [
        { "ErrorEquals": ["ECS.AmazonECSException", "States.TaskFailed"],
          "IntervalSeconds": 2, "MaxAttempts": 3, "BackoffRate": 2.0, "JitterStrategy": "FULL" }
      ],
      "Catch": [
        { "ErrorEquals": ["States.ALL"],
          "Assign": { "failedStep": "ingest", "err": "{% $states.errorOutput %}" },
          "Next": "ManualFallback" }
      ],
      "Assign": { "caseId": "{% $states.context.Execution.Input.caseId %}" },
      "Next": "LocalizeScanBodies"
    },

    "LocalizeScanBodies": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": {
        "Cluster": "casePrepCluster",
        "TaskDefinition": "casePrepWorker:stage-localize",
        "LaunchType": "FARGATE",
        "Overrides": { "ContainerOverrides": [{ "Name": "worker",
          "Environment": [{ "Name": "CASE_ID", "Value": "{% $caseId %}" },
                          { "Name": "STEP", "Value": "localize" }] }] }
      },
      "Retry": [
        { "ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 2, "MaxAttempts": 3, "BackoffRate": 2.0 },
        { "ErrorEquals": ["States.QueryEvaluationError"], "MaxAttempts": 0 }
      ],
      "Catch": [
        { "ErrorEquals": ["BelowQualityThreshold"], "Next": "AwaitOperatorSeed" },
        { "ErrorEquals": ["States.ALL"],
          "Assign": { "failedStep": "localize", "err": "{% $states.errorOutput %}" },
          "Next": "ManualFallback" }
      ],
      "Output": "{% $states.result %}",
      "Next": "LocalizationConfident"
    },

    "LocalizationConfident": {
      "Type": "Choice",
      "Choices": [
        { "Condition": "{% $states.input.localizationConfident = true %}", "Next": "RegisterAllImplants" }
      ],
      "Default": "AwaitOperatorSeed"
    },

    "AwaitOperatorSeed": {
      "Type": "Task",
      "Comment": "Pause for the operator one-click seed. Token drained server-side by NestJS; NEVER sent to the browser. Resumed by NestJS SendTaskSuccess after authz + payload bounds-check.",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Arguments": {
        "QueueUrl": "${OperatorSeedQueueUrl}",
        "MessageGroupId": "{% $caseId %}",
        "MessageDeduplicationId": "{% $caseId & ':seed' %}",
        "MessageBody": "{% $string({ 'taskToken': $states.context.Task.Token, 'caseId': $caseId, 'reason': 'localization_low_confidence' }) %}"
      },
      "HeartbeatSeconds": 3600,
      "TimeoutSeconds": 86400,
      "Catch": [
        { "ErrorEquals": ["States.Timeout", "States.HeartbeatTimeout"],
          "Assign": { "failedStep": "seed", "err": { "Error": "SeedTimeout" } },
          "Next": "EscalateSeed" }
      ],
      "Next": "RegisterAllImplants"
    },

    "EscalateSeed": {
      "Type": "Task",
      "Comment": "SLA-breach escalation; second timeout falls back to manual. Token also server-side only.",
      "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
      "Arguments": {
        "QueueUrl": "${OperatorEscalationQueueUrl}",
        "MessageGroupId": "{% $caseId %}",
        "MessageBody": "{% $string({ 'taskToken': $states.context.Task.Token, 'caseId': $caseId, 'escalated': true }) %}"
      },
      "TimeoutSeconds": 86400,
      "Catch": [ { "ErrorEquals": ["States.Timeout"], "Next": "ManualFallback" } ],
      "Next": "RegisterAllImplants"
    },

    "RegisterAllImplants": {
      "Type": "Map",
      "Comment": "Per-implant ICP register -> derive pose -> confidence gate, in parallel.",
      "Items": "{% $states.input.implantSites %}",
      "MaxConcurrency": 4,
      "ToleratedFailurePercentage": 0,
      "ItemProcessor": {
        "ProcessorConfig": { "Mode": "INLINE" },
        "StartAt": "RegisterImplant",
        "States": {
          "RegisterImplant": {
            "Type": "Task",
            "Resource": "arn:aws:states:::ecs:runTask.sync",
            "Arguments": {
              "Cluster": "casePrepCluster",
              "TaskDefinition": "casePrepWorker:stage-register",
              "LaunchType": "FARGATE",
              "Overrides": { "ContainerOverrides": [{ "Name": "worker",
                "Environment": [
                  { "Name": "CASE_ID", "Value": "{% $states.context.Execution.Input.caseId %}" },
                  { "Name": "TOOTH", "Value": "{% $string($states.input.tooth) %}" },
                  { "Name": "STEP", "Value": "register" }] }] }
            },
            "Retry": [ { "ErrorEquals": ["States.TaskFailed"],
                        "IntervalSeconds": 2, "MaxAttempts": 3, "BackoffRate": 2.0, "JitterStrategy": "FULL" } ],
            "Output": "{% $states.result %}",
            "Next": "ConfidenceGate"
          },
          "ConfidenceGate": {
            "Type": "Choice",
            "Comment": "PASS=auto-seed, FLAG=manual. Mirrors domain/confidence.evaluate_gate.",
            "Choices": [ { "Condition": "{% $states.input.gatePassed = true %}", "Next": "ImplantPass" } ],
            "Default": "ImplantFlag"
          },
          "ImplantPass": { "Type": "Pass",
            "Output": "{% { 'tooth': $states.input.tooth, 'decision': 'PASS' } %}", "End": true },
          "ImplantFlag": { "Type": "Pass",
            "Output": "{% { 'tooth': $states.input.tooth, 'decision': 'FLAG', 'reasons': $states.input.reasons } %}", "End": true }
        }
      },
      "Catch": [
        { "ErrorEquals": ["States.ExceedToleratedFailureThreshold", "States.ALL"],
          "Assign": { "failedStep": "register", "err": "{% $states.errorOutput %}" },
          "Next": "ManualFallback" }
      ],
      "Assign": { "implantDecisions": "{% $states.result %}" },
      "Next": "AllImplantsPass"
    },

    "AllImplantsPass": {
      "Type": "Choice",
      "Choices": [
        { "Condition": "{% $count($implantDecisions[decision = 'FLAG']) = 0 %}", "Next": "AbutmentInterface" }
      ],
      "Default": "RouteToManual"
    },

    "AbutmentInterface": { "Type": "Pass", "Next": "Package" },
    "Package": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Arguments": { "Cluster": "casePrepCluster", "TaskDefinition": "casePrepWorker:stage-package", "LaunchType": "FARGATE" },
      "Retry": [ { "ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 3, "MaxAttempts": 5, "BackoffRate": 2.0 } ],
      "Catch": [ { "ErrorEquals": ["States.ALL"], "Assign": { "failedStep": "package" }, "Next": "ManualFallback" } ],
      "Next": "MarkReady"
    },

    "MarkReady": { "Type": "Succeed" },

    "RouteToManual": {
      "Type": "Task",
      "Comment": "Some implant FLAGged -> case to in_design with reasons. A SUCCESS, not a failure. Implemented as a Lambda, NOT sfn:sendTaskSuccess (there is no waiting task to resume here).",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Arguments": {
        "FunctionName": "${RouteToManualFn}",
        "Payload": "{% { 'caseId': $caseId, 'outcome': 'flagged_to_manual', 'flags': $implantDecisions[decision = 'FLAG'] } %}"
      },
      "Retry": [ { "ErrorEquals": ["States.TaskFailed", "Lambda.ServiceException"],
                   "IntervalSeconds": 2, "MaxAttempts": 3, "BackoffRate": 2.0 } ],
      "Catch": [ { "ErrorEquals": ["States.ALL"], "Assign": { "failedStep": "route_to_manual" }, "Next": "ManualFallback" } ],
      "End": true
    },

    "ManualFallback": {
      "Type": "Task",
      "Comment": "Infra/algorithm failure -> case to in_design, alert operator. The DLQ-equivalent.",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Arguments": {
        "FunctionName": "${ManualFallbackFn}",
        "Payload": "{% { 'caseId': $caseId, 'failedStep': $exists($failedStep) ? $failedStep : 'unknown', 'error': $exists($err) ? $err : null } %}"
      },
      "End": true
    }
  }
}
```

> Correctness notes: JSONata mode at top level; `waitForTaskToken` only on Standard; `$states.context.Task.Token` is handed to the **API server-side via SQS and never to the browser** (M3-security); `HeartbeatSeconds`+`TimeoutSeconds` on the seed wait; `Catch` on `States.Timeout` for escalation; `Map` with `ToleratedFailurePercentage: 0` so an *errored* implant fails the case while a *FLAGged* implant is a normal `Choice` branch; **`RouteToManual` is a Lambda `Task` + `Succeed`, with its own Retry/Catch — not a tokenless `sfn:sendTaskSuccess`** (H3); `$exists()` guards on `$failedStep`/`$err` in the fallback. Replace `${...}` substitutions with real ARNs via Terraform `DefinitionSubstitutions`.

#### 2.13 Trigger: SQS → Step Functions (kept as ingress)

We do **not** let the API `StartExecution` directly. SQS stays as the durable ingress buffer (absorbs bursts, gives the API a fast fire-and-forget enqueue, decouples API availability from Step Functions). A tiny **starter Lambda** (event-source-mapped to `stage1.fifo`) calls `StartExecution(name={case_id}:{submission_uuid}, input={caseId,...})`. The DB claim (§2.4) — not the execution name — is the authoritative single-active guard (L2). If `StartExecution` throws, the SQS message is not deleted and redrives via the existing DLQ → manual fallback — the MVP safety net is preserved verbatim. The migration swaps the *consumer* (per-message `RunTask` launcher → state machine) without touching the API enqueue contract or DB lifecycle.

---

## 3. Storage, security & IAM

Region pinned to **`us-east-1`** (single-region MVP; cross-region DR in §6). Account-level **S3 Block Public Access** is ON account-wide; bucket settings below are belt-and-suspenders.

### 3.1 Buckets

Three buckets, all private, versioned, default-encrypted with the customer-managed key (CMK) `alias/cad-data`. **The data bucket's default-encryption configuration is pinned to the CMK** so an `aws:kms` PUT that omits the key-id header cannot silently land under the AWS-managed key (belt for C3, paired with the bucket-policy `Null` guard below).

| Bucket (logical) | Name pattern | Holds | Versioning | Default SSE | Lifecycle |
|---|---|---|---|---|---|
| **Inputs/outputs** | `dac-cases-{env}-{acct-short}` | Uploaded STLs (`inputs/`), deliverables (`outputs/`), reports (`report/`) | On | `aws:kms` CMK (pinned default) | §3.3 |
| **Previews** | `dac-previews-{env}-{acct-short}` | Downscaled GLB/PNG thumbnails for the console & portal | On | `aws:kms` CMK (pinned default) | Expire 90d |
| **Access logs** | `dac-logs-{env}-{acct-short}` | S3 server access logs + CloudTrail data-event logs | On + **Object Lock (compliance)** on the audit trail | **SSE-S3** (see §3.7/§3.9) | Expire 400d |

A **separate previews bucket** (not a prefix) because previews are the only objects rendered to a browser via short-TTL signed URLs and are derived, non-sensitive, downscaled artifacts. Isolating them means the browser-GET CORS/policy never touches the raw biometric-adjacent meshes; the inputs/outputs bucket has **no** browser-GET path (uploads are PUT-only via presign; deliverable downloads go through the API after the payment gate). Blast radius of a previews misconfiguration is a thumbnail, not a scan.

**Key layout** (PII-free — only opaque tenant/case UUIDs and a `kind`):

```
inputs/  tenant/{tenant_id}/case/{case_id}/{kind}/{content_hash}.stl
outputs/ tenant/{tenant_id}/case/{case_id}/deliverable/{content_hash}.zip
report/  tenant/{tenant_id}/case/{case_id}/report/{content_hash}.json
```

`{kind}` ∈ the existing `scan_file_kind` enum (`lower_arch | upper_arch | scan_bodies | bite | waxup | other`). The `tenant/.../case/...` prefix is load-bearing for IAM and for the **KMS encryption context** (§3.2): it lets a worker role be scoped to one tenant+case via both an IAM prefix condition and an encryption-context condition, so a compromised task can neither enumerate nor *decrypt* another tenant's meshes. *(`tenant_id` depends on the §2 tenancy migration.)*

**Per-bucket settings:** `BlockPublicAcls`/`IgnorePublicAcls`/`BlockPublicPolicy`/`RestrictPublicBuckets = true`; `ObjectOwnership = BucketOwnerEnforced` (ACLs disabled — policy is the only access path); versioning **Enabled** (recover from malicious/buggy overwrite or delete) with lifecycle expiry of noncurrent versions so versioning doesn't balloon cost.

**Bucket policy — deny-by-default hardening** (inputs/outputs and previews), now closing the `IfExists`/absent-header gap (fix for C3):

```json
{
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny", "Principal": "*", "Action": "s3:*",
      "Resource": ["arn:aws:s3:::dac-cases-prod-ab12",
                   "arn:aws:s3:::dac-cases-prod-ab12/*"],
      "Condition": { "Bool": { "aws:SecureTransport": "false" } }
    },
    {
      "Sid": "DenyUnencryptedPuts",
      "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/*",
      "Condition": { "StringNotEquals": { "s3:x-amz-server-side-encryption": "aws:kms" } }
    },
    {
      "Sid": "DenyMissingKmsKeyHeader",
      "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/*",
      "Condition": { "Null": { "s3:x-amz-server-side-encryption-aws-kms-key-id": "true" } }
    },
    {
      "Sid": "DenyWrongKmsKey",
      "Effect": "Deny", "Principal": "*", "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption-aws-kms-key-id":
            "arn:aws:kms:us-east-1:111122223333:key/CMK-UUID"
        }
      }
    }
  ]
}
```

`DenyInsecureTransport` enforces TLS. The three `Deny…Puts` statements together guarantee every object lands encrypted under *our* CMK: `DenyUnencryptedPuts` forces `aws:kms`; **`DenyMissingKmsKeyHeader` (the new `Null` guard) rejects an `aws:kms` PUT that omits the key-id header** — which the old `StringNotEqualsIfExists` would have *allowed*, letting the object fall to the bucket-default/AWS-managed key; `DenyWrongKmsKey` rejects a present-but-wrong key. Combined with the pinned bucket default, "every object is under our CMK" is now actually enforced. The presign (§3.4) sets these headers, so legitimate uploads are unaffected.

### 3.2 Encryption — customer-managed KMS key with per-case encryption context (fix for C1)

One symmetric CMK, `alias/cad-data`, `SYMMETRIC_DEFAULT`, **automatic annual rotation enabled**. **Enable S3 Bucket Keys** on each bucket to collapse per-object `GenerateDataKey` calls into roughly one per bucket-key-refresh window — at ~600 objects/mo this cuts KMS request cost by >99%.

The earlier draft called the CMK "the real access boundary," but the `DataPlaneUsers` statement granted `kms:Decrypt`/`GenerateDataKey` on `Resource: "*"` with **only** `kms:ViaService` — which asserts the call came *via S3* but does **not** bind it to a bucket, prefix, or tenant. That made the KMS layer add nothing beyond the S3 IAM. The corrected design **binds decryption to a per-tenant/per-case encryption context**:

- **On PUT**, S3 objects are written with an encryption context `{ "tenant_id": "...", "case_id": "..." }` (the presign and the worker set `x-amz-server-side-encryption-context` accordingly).
- **The key policy and the per-role IAM both require a matching encryption context** for `kms:Decrypt`. For the worker, the MVP floor uses the principal's session/path scoping; the **Step Functions per-case session** pins `kms:EncryptionContext:case_id` to the case the task is processing, so a compromised task cannot decrypt any object outside its own case even though it routes via S3.
- **`dac-validation-lambda` loses `kms:Decrypt` on anything but the `inputs/` context** (it never needs `outputs/`).

Key policy:

```json
{
  "Statement": [
    {
      "Sid": "RootAccountKeyAdminOnly",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:root" },
      "Action": ["kms:Create*","kms:Describe*","kms:Enable*","kms:List*",
                 "kms:Put*","kms:Update*","kms:Revoke*","kms:Disable*",
                 "kms:Get*","kms:Delete*","kms:TagResource","kms:UntagResource",
                 "kms:ScheduleKeyDeletion","kms:CancelKeyDeletion"],
      "Resource": "*"
    },
    {
      "Sid": "DataPlaneUsersViaServiceWithContext",
      "Effect": "Allow",
      "Principal": { "AWS": [
        "arn:aws:iam::111122223333:role/dac-worker-task",
        "arn:aws:iam::111122223333:role/dac-api-task"
      ]},
      "Action": ["kms:Decrypt","kms:GenerateDataKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" },
        "StringLike": { "kms:EncryptionContext:case_id": "*" },
        "Null": { "kms:EncryptionContext:case_id": "false", "kms:EncryptionContext:tenant_id": "false" }
      }
    },
    {
      "Sid": "ValidationLambdaInputsOnly",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:role/dac-validation-lambda" },
      "Action": ["kms:Decrypt"],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" },
        "Null": { "kms:EncryptionContext:case_id": "false" }
      }
    }
  ]
}
```

The data-plane statement now requires *that an encryption context be present and carry tenant/case*; the Step-Functions session policy (§3.5) narrows `case_id` to the exact value, making the CMK a genuine second boundary. (1) The root statement still grants **key administration only** — *not* `kms:Decrypt` — so an admin/CI identity can rotate/tag but cannot read a scan mesh (the replication role for §6 is added here too, also context-scoped). (2) `kms:ViaService` remains, constraining data-plane roles to use the key only through S3.

> **Residual risk (accepted, low):** at MVP — before the Step Functions per-case session — the worker can decrypt any object whose context carries *some* tenant/case, i.e. the per-case pin is only enforced from 2B onward. The MVP compensating control is the S3 IAM prefix scoping plus the single-message-per-task launch (a task only ever receives one case_id). This is documented in the remediations section, not silently left as "the CMK is the boundary."

### 3.3 Lifecycle (inputs/outputs bucket)

Storage grows ~linearly with volume (~200 MB/case × 300/mo ≈ 60 GB/mo new) until the retention-expiry steady state (~year 1). The client-confirmed retention window is enforced as expiry (a Terraform **variable**, not hardcoded).

| Rule (filter) | Transition / action | Rationale |
|---|---|---|
| `inputs/` current | → S3 **Standard-IA** at 30d, → **Glacier Flexible Retrieval** at 90d | Inputs are cold once a deliverable ships. |
| `outputs/` current | → Standard-IA at 30d (no Glacier) | Deliverables may be re-downloaded; keep ms access. |
| All prefixes, **noncurrent** versions | expire at 30d | Versioning safety net without unbounded cost. |
| `inputs/` + `outputs/` current | **Expiration at retention window** (default 365d, parameterized) | Mandated deletion; client-set without a code change. |
| All | `AbortIncompleteMultipartUpload` at 7d | Reclaim orphaned parts from failed clinic uploads. |

Previews: expire 90d (regenerable from source).

### 3.4 Presigned multipart upload + validation Lambda

The browser never holds AWS credentials; the **API role** signs every step, and **server-side size/part caps are set at presign time** so an authenticated tenant cannot assemble a multi-GB object that slips past the post-hoc validation (fix for M2-cost).

1. Browser asks the API to start an upload for `case_id`/`kind`. The API computes the key (it owns the content hash / UUID; the client never picks the key — prevents path traversal / cross-tenant injection).
2. API calls `CreateMultipartUpload` with `ServerSideEncryption=aws:kms`, `SSEKMSKeyId=<CMK arn>`, **and `SSEKMSEncryptionContext={tenant_id,case_id}`**, persists `upload_id` + key in an `uploads` row (resumability).
3. API returns presigned `UploadPart` URLs. **Each presigned part URL pins a `Content-Length` range** and the **server caps total part count** (e.g. ≤ 30 parts × 5 MB ⇒ hard ceiling well under 150 MB), so the *aggregate* object size is bounded **before** the bytes are durable — not merely checked on the completed object after multi-GB already landed. Browser uploads parts in parallel (3–5 concurrent) with per-part retry, tracking ETags.
4. Browser sends ETag list → API calls `CompleteMultipartUpload`. On reload, the API reconciles persisted ETags against `ListParts`.

Because the bucket policy denies a non-`aws:kms` PUT and a missing-key-header PUT, the presign **must** carry those headers (it does in step 2) — that is what makes "encryption at rest under our CMK" enforced, not aspirational.

**Validation Lambda** (`dac-validation-lambda`, triggered on `s3:ObjectCreated:*` under `inputs/`) — the security checkpoint for untrusted input, runs *before* a case is queued:

- Range-GET the header + parse: valid STL/PLY magic, vertex/face counts within sane bounds (reject 0-face and multi-GB-blowup meshes).
- Confirm the object size is within the ceiling (defense-in-depth behind the presign cap).
- Recompute SHA-256 → `case_files.checksum` (integrity + dedupe).
- **On pass:** tag `validation=passed` and emit the case-submitted signal (enqueue stage-1).
- **On fail:** tag `validation=failed`, write the reason to the portal DB, **and `DeleteObject` the rejected upload** (fix for M2-cost). The Lambda holds a **narrowly-scoped `s3:DeleteObject` on `inputs/*` conditioned on the `validation=failed` tag** — the *only* delete grant in the system — so oversized/malicious blobs are cleaned up immediately instead of sitting until lifecycle expiry. Failures route to the Lambda's on-failure DLQ (§2.5), never silently proceed.

The Lambda runs **in-VPC** (private subnets) so it reaches S3/KMS via endpoints and has no internet route — same untrusted bytes, same network sandbox as the worker, **with its own on-failure destination** so a Lambda crash surfaces rather than dropping the case.

### 3.5 IAM — least-privilege roles, deny-by-default

Separate task roles per compute identity; none can assume another; each scoped to the minimum prefix and action set. (ECS also needs the distinct *execution* role per §1.7.)

**`dac-api-task`** (always-on NestJS API). Per H1, the API **no longer holds `ecs:RunTask`/`iam:PassRole`** (the per-message `RunTask` launcher Lambda owns task launch; the API only enqueues to SQS), and the Supabase **service-role** key is replaced by a **scoped Postgres role exercised through an RPC/function surface**, not the RLS-bypass god-key:

```json
{
  "Statement": [
    { "Sid": "SignUploadsAndReadDeliverables", "Effect": "Allow",
      "Action": ["s3:PutObject","s3:GetObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/*" },
    { "Sid": "Previews", "Effect": "Allow",
      "Action": ["s3:GetObject","s3:PutObject"],
      "Resource": "arn:aws:s3:::dac-previews-prod-ab12/*" },
    { "Sid": "KmsForS3", "Effect": "Allow",
      "Action": ["kms:Decrypt","kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:us-east-1:111122223333:key/CMK-UUID",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" },
        "Null": { "kms:EncryptionContext:case_id": "false" } } },
    { "Sid": "EnqueueWork", "Effect": "Allow",
      "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:us-east-1:111122223333:dac-stage*" },
    { "Sid": "ResumeSeed", "Effect": "Allow",
      "Action": ["states:SendTaskSuccess","states:SendTaskFailure"],
      "Resource": "arn:aws:states:us-east-1:111122223333:stateMachine:casePrep*" },
    { "Sid": "ReadSecrets", "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": ["arn:aws:secretsmanager:us-east-1:111122223333:secret:dac/stripe-*",
                   "arn:aws:secretsmanager:us-east-1:111122223333:secret:dac/supabase-app-role-*",
                   "arn:aws:secretsmanager:us-east-1:111122223333:secret:dac/slack-*"] }
  ]
}
```

Removed vs. the draft: **`ecs:RunTask` and `iam:PassRole` are gone** (H1) — the API has no path to launch arbitrary container overrides under the worker role; task launch is the launcher Lambda's job, scoped to exact task-definition revisions with `iam:PassedToService = ecs-tasks.amazonaws.com`. The Supabase secret referenced is the **app-scoped role** (`dac/supabase-app-role-*`), used via RPC; the RLS-bypass service-role key is held *only* by a narrow status-writeback drain context (§3.6), so an API compromise is not instantly all-tenants. The API still has **no `s3:DeleteObject`** and **no `ListBucket`**.

> **Launcher Lambda role (`dac-runtask-launcher`)** — owns `ecs:RunTask` + `iam:PassRole` (H1 moves these here, tightly scoped):
> ```json
> { "Statement": [
>   { "Sid": "RunWorkerExactTaskDefs", "Effect": "Allow", "Action": ["ecs:RunTask"],
>     "Resource": "arn:aws:ecs:us-east-1:111122223333:task-definition/casePrepWorker:*",
>     "Condition": { "ArnEquals": { "ecs:cluster": "arn:aws:ecs:us-east-1:111122223333:cluster/casePrepCluster" } } },
>   { "Sid": "PassOnlyWorkerRolesToEcs", "Effect": "Allow", "Action": ["iam:PassRole"],
>     "Resource": ["arn:aws:iam::111122223333:role/dac-worker-task",
>                  "arn:aws:iam::111122223333:role/dac-worker-exec"],
>     "Condition": { "StringEquals": { "iam:PassedToService": "ecs-tasks.amazonaws.com" } } },
>   { "Sid": "ConsumeStageQueues", "Effect": "Allow",
>     "Action": ["sqs:ReceiveMessage","sqs:DeleteMessage","sqs:GetQueueAttributes"],
>     "Resource": "arn:aws:sqs:us-east-1:111122223333:dac-stage*" }
> ]}
> ```
> The launcher passes only fixed, allow-listed env keys (`CASE_ID`, `TENANT_ID`, `STEP`) — it does **not** allow a `command` override — so even a compromised launcher cannot choose what binary runs as the worker role.

**`dac-worker-task`** (on-demand geometry worker) — **most-sandboxed identity:**

```json
{
  "Statement": [
    { "Sid": "ReadInputs", "Effect": "Allow", "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/inputs/*" },
    { "Sid": "WriteOutputs", "Effect": "Allow", "Action": ["s3:PutObject"],
      "Resource": ["arn:aws:s3:::dac-cases-prod-ab12/outputs/*",
                   "arn:aws:s3:::dac-cases-prod-ab12/report/*"] },
    { "Sid": "WritePreview", "Effect": "Allow", "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::dac-previews-prod-ab12/*" },
    { "Sid": "KmsForS3WithContext", "Effect": "Allow", "Action": ["kms:Decrypt","kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:us-east-1:111122223333:key/CMK-UUID",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" },
        "Null": { "kms:EncryptionContext:case_id": "false" } } },
    { "Sid": "ConsumeQueue", "Effect": "Allow",
      "Action": ["sqs:ReceiveMessage","sqs:DeleteMessage","sqs:GetQueueAttributes","sqs:ChangeMessageVisibility"],
      "Resource": "arn:aws:sqs:us-east-1:111122223333:dac-stage*" },
    { "Sid": "StatusWritebackOnly", "Effect": "Allow",
      "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:us-east-1:111122223333:dac-status-writeback*" }
  ]
}
```

Worker has **no `cloudwatch:PutMetricData`** (metrics come from the trusted Lambda — fix for H2/M5), **no `GetObject` on `outputs/`**, **no `DeleteObject`**, **no `ListBucket`**, **no Secrets**, **no `RunTask`**, **no STS** (MVP). Status write-back is `SendMessage` to the one `status-writeback` queue only (§3.6).

**Per-case tightening (Step Functions era):** the state machine passes a scoped-down session via `sts:AssumeRole` with an inline session policy pinning *both* prefix and encryption context:

```json
"Condition": {
  "StringLike": { "s3:prefix": ["inputs/tenant/${tenant_id}/case/${case_id}/*"] },
  "StringEquals": { "kms:EncryptionContext:case_id": "${case_id}",
                    "kms:EncryptionContext:tenant_id": "${tenant_id}" }
}
```

so a compromised task can neither name nor *decrypt* another case's key. This is the era in which the CMK boundary becomes per-case-tight; the MVP residual (§3.2) is the gap until then.

**`dac-validation-lambda`** — gains the narrow tagged-delete (M2-cost), keeps inputs-only KMS:

```json
{
  "Statement": [
    { "Sid": "ReadAndTagInputs", "Effect": "Allow",
      "Action": ["s3:GetObject","s3:GetObjectTagging","s3:PutObjectTagging"],
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/inputs/*" },
    { "Sid": "DeleteRejectedOnly", "Effect": "Allow",
      "Action": ["s3:DeleteObject"],
      "Resource": "arn:aws:s3:::dac-cases-prod-ab12/inputs/*",
      "Condition": { "StringEquals": { "s3:ExistingObjectTag/validation": "failed" } } },
    { "Sid": "KmsDecryptInputs", "Effect": "Allow", "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:us-east-1:111122223333:key/CMK-UUID",
      "Condition": {
        "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" },
        "Null": { "kms:EncryptionContext:case_id": "false" } } },
    { "Sid": "EnqueueOnPass", "Effect": "Allow", "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:us-east-1:111122223333:dac-stage1*" },
    { "Sid": "VpcLambdaENIs", "Effect": "Allow",
      "Action": ["ec2:CreateNetworkInterface","ec2:DescribeNetworkInterfaces","ec2:DeleteNetworkInterface"],
      "Resource": "*" }
  ]
}
```

The `ec2:*NetworkInterface` block is the standard VPC-Lambda ENI requirement and the one unavoidable `Resource: "*"` (harmless — it can't read traffic).

**`dac-metrics-emitter`** (new — trusted, non-sandboxed; fix for H2/M5/C2): reads `report/*` and the audited-sample store from S3, computes/aggregates, and emits `CasePrep/Quality`:
```json
{ "Statement": [
  { "Sid": "ReadReports", "Effect": "Allow", "Action": ["s3:GetObject"],
    "Resource": "arn:aws:s3:::dac-cases-prod-ab12/report/*" },
  { "Sid": "KmsDecryptReports", "Effect": "Allow", "Action": ["kms:Decrypt"],
    "Resource": "arn:aws:kms:us-east-1:111122223333:key/CMK-UUID",
    "Condition": { "StringEquals": { "kms:ViaService": "s3.us-east-1.amazonaws.com" } } },
  { "Sid": "EmitQualityMetrics", "Effect": "Allow", "Action": ["cloudwatch:PutMetricData"],
    "Resource": "*", "Condition": { "StringEquals": { "cloudwatch:namespace": "CasePrep/Quality" } } }
]}
```
Because this identity is **outside** the untrusted-mesh sandbox, an exploited mesh parser cannot forge or suppress the safety metric (M5), and the metric dimensions are derived by trusted code from the signed report rather than from attacker-controlled free text.

**CI deploy roles** (assumed via GitHub OIDC, §5.3): a **plan role** (read-only + state read) and an **apply role** (broader provisioning), usable only from the protected `prod`/`staging` GitHub Environments via the `sub` condition. Separating plan from apply means a PR from a fork can never apply. **Account guardrail:** an SCP / permissions boundary denies `s3:*` and `kms:Decrypt` on these resources to any principal outside this role set, so deny-by-default holds even if someone hand-crafts a new role.

### 3.6 Status write-back path (resolved)

**The worker holds no DB credentials.** Keeping Supabase keys out of the untrusted-mesh sandbox is the point — a mesh exploit that lands code execution must not reach the database. Status flows via a **scoped `status-writeback` SQS queue** that the NestJS API drains (the worker task role's only `SendMessage` grant is to this one queue). The API then performs the privileged Postgres write **through the scoped app role / RPC surface**, not the RLS-bypass service-role key (H1) — the service-role key is confined to the narrow drain context and never reaches the general API request path or the sandbox. This supersedes the storage lens's earlier "inject the Supabase service-role key as an env var into the worker" option. (If a future profiling shows the SQS hop is too slow, the alternative is one narrow authenticated API endpoint — not DB creds in the sandbox.)

### 3.7 Network — VPC so the sandbox needs no internet (claim restated honestly)

The worker and validation Lambda process untrusted meshes. **No NAT and no IGW on the compute subnets** means there is physically no route to the *internet* — so generic internet exfiltration is impossible even if mesh-parsing code is exploited. But "exfiltration is impossible by routing" was **overstated** (fix for H2): interface VPC endpoints are themselves an AWS-API egress channel. The honest claim and the controls that back it:

> **No internet egress; AWS-API egress is constrained by per-endpoint policy to this account's resources only.**

| Endpoint | Type | Used by | Endpoint-policy constraint |
|---|---|---|---|
| `…s3` | **Gateway** | worker, Lambda | **explicit `Deny` on all buckets except `dac-cases-*`/`dac-previews-*`** (not merely a positive Allow) |
| `…sqs` | Interface | worker, API, Lambda | `aws:PrincipalAccount = 111122223333`; resource = this account's `dac-*` queues |
| `…kms` | Interface | worker, API, Lambda | `aws:PrincipalAccount`; resource = the data/secrets CMKs |
| `…secretsmanager` | Interface | API, execution roles | `aws:PrincipalAccount`; resource = `dac/*` secrets |
| `…ecr.api` / `…ecr.dkr` / logs / sts | Interface | execution role / worker | `aws:PrincipalAccount`; **STS reachability is OFF for the MVP worker** (no AssumeRole need until 2B) |

There is **no `monitoring` (CloudWatch) endpoint in the sandbox path** — metric emission was moved to the trusted out-of-band Lambda over the free gateway S3 endpoint (fix for H2 metric-channel and L4: it removes an entire per-AZ interface-endpoint line). Worker/Lambda SG egress allows **only 443 to the endpoint SGs** (and the S3 prefix list); no `0.0.0.0/0`. Bucket policies add `Deny … unless aws:sourceVpce = vpce-xxxx` to forbid access not originating inside the VPC. The **API** task, which legitimately needs Supabase/Stripe/Sentry/Slack egress, runs on a **separate network path** — see §3.7a — so the worker stays egress-locked.

#### 3.7a API egress (fix for M1 self-contradiction + M5 HA)

The draft simultaneously praised "skipping NAT saves ~$32/mo" and then booked a $32 NAT for the API. Resolution: **the API runs in public subnets behind the ALB and reaches Supabase/Stripe/Sentry/Slack directly — no NAT** (these are public SaaS endpoints; the API needs egress, not a stable source IP). A NAT is introduced **only if** Supabase network-restrictions require a stable egress IP, and if so the justification is *that*, not cost. Either way the "$32 NAT for the API" line is removed from the default bill. The API is a **Fargate service min 2 across 2 AZs** (fix for M5) — min-1 behind an ALB is a single-task SPOF for a tier the plan elsewhere wants paged on 5xx — which also forces the honest 2-AZ endpoint cost in §4.

### 3.8 Secrets

All third-party credentials in **AWS Secrets Manager**, encrypted with a **dedicated `alias/cad-secrets` CMK** (recommended, ~$1/mo, so secret-admins and data-admins are separable). One secret per credential, namespaced `dac/`:

| Secret | Consumer | Rotation |
|---|---|---|
| `dac/stripe-secret-key`, `dac/stripe-webhook-signing-secret` | API | manual/quarterly (Stripe-issued) |
| `dac/supabase-app-role-key` | API request path (scoped role via RPC) | manual on Supabase rotation |
| `dac/supabase-service-role-key` | **status-writeback drain context only** (RLS-bypass, never on the general API path or the sandbox) | manual on Supabase rotation |
| `dac/slack-webhook-url` | API, alarms Lambda | manual |

ECS task definitions inject secrets via the `secrets` block (`valueFrom` = secret ARN) resolved by the **execution role** at task start — never in the task definition, image, or CloudTrail args. `GetSecretValue` is scoped by ARN prefix. **No secrets in env files, images, plaintext Terraform state, or SSM plaintext params.** The Stripe webhook signing secret is what makes the `paid` transition trustworthy; it lives only here. The Supabase **service-role** key bypasses RLS, which is exactly why it is restricted to the narrow drain context and never shipped to the browser, the general API path, or the worker sandbox (§3.6, H1).

### 3.9 Audit & access logging

Three independent trails so a single tampered source doesn't blind us:

1. **CloudTrail with S3 data events** on inputs/outputs and previews — every `Get/Put/DeleteObject` with caller identity, source IP/VPCE, and key. Management events (KMS key changes, IAM edits) on by default. **CloudTrail is delivered to a separate logging/security account** (and a second region) so the workload account's admin/CI identities have **no delete path** to the trail.
2. **KMS** `Decrypt`/`GenerateDataKey` in CloudTrail management events — every scan-mesh decrypt is attributable to a role + request context (now including the encryption context, so cross-case decrypt attempts are visible).
3. **S3 server access logs** → `dac-logs` as a secondary request-level trail (usefully catches denied requests).

The audit trail uses **Object Lock in compliance mode, not governance** (fix for M4): governance mode is bypassable by any principal with `s3:BypassGovernanceRetention`, and the key/root admin in the workload account would otherwise be able to delete the audit trail — undermining clinical traceability for exactly the admin-pivot an attacker would aim for. Compliance mode is irreversible-by-design for the immutable audit trail; combined with the **separate logging account**, neither a workload-account admin nor a compromised CI identity can erase it. (Governance mode remains fine on the *data* bucket's versioning, where break-glass restore is occasionally legitimate.) **Encrypt logs with SSE-S3 (AES-256), not the data CMK** — same-CMK logging creates a decrypt dependency and KMS-call amplification on the log path, and logs aren't biometric data. CloudTrail log-file integrity validation (SHA-256 digest files) is on. This audit data also feeds the security-side alarms (cross-tenant access anomalies, `AccessDenied` spikes), complementary to the pipeline go/no-go metrics in §5.

---

## 4. Autoscaling & cost

### 4.1 Scaling model (fix for H2)

- **Worker is on-demand, min capacity 0, with an explicit per-message trigger.** There is **no always-on poller**. Each FIFO queue has an **event-source mapping / EventBridge Pipe → launcher Lambda → `ecs:RunTask`** (§1.8, §2.1): one message launches one task, the task processes one case, exits, and bills only for its runtime. This is true scale-from-zero and needs **no autoscaling policy**. (The earlier "SQS-poller … min 0" was internally contradictory — a poller is always-on. That language is removed.) If a long-running consumer service is ever chosen instead, its scaling signal **must** be **backlog-per-task** = `ApproximateNumberOfMessagesVisible / RunningTaskCount` (AWS's documented queue-driven pattern), *not* raw queue depth, which pages on transient bursts that running tasks are already clearing. The §5 queue-depth/age alarms are **operability alarms, not the scaling signal**.
- **API is always-on HA**: a Fargate **service desired/min 2 across 2 AZs** (fix for M5), target-tracking autoscale **min 2 / max 4 on CPU 60%**, **0.5 vCPU / 1 GB** each, behind an ALB with an ACM TLS cert. Min-2/2-AZ removes the single-task SPOF and is consistent with the "page on 5xx" posture.
- **Cold-start tradeoff:** keeping worker min capacity at 0 incurs a ~60–120 s Fargate task-launch on the first case. The Slack "needs seeding" alert path tolerates this; we keep min=0 for cost. If sub-minute stage-1 latency is later required, pay for one warm task (open question #4).

### 4.2 Cost table (us-east-1, ~300 cases/mo, ~200 MB/case) — HA done honestly

The dominant lines are the **per-AZ interface endpoints** and the **always-on HA API**, exactly the two the draft flagged as biggest but then under-booked. Interface endpoints bill **per-endpoint per-AZ-hour** ($0.01/hr ≈ $7.30/endpoint/AZ/mo); HA demands ≥2 AZs.

| Line item | Driver | Est. monthly |
|---|---|---|
| **Worker Fargate (on-demand)** | ~27.5 task-hours/mo (stage1 1vCPU/4GB ~90 s + stage2 2vCPU/8GB ~240 s per case, ~2 implant sites avg) | **$3–6** (verified floor ~$2.77) |
| **API Fargate (always-on, min 2 / 2 AZ)** | 2× 0.5 vCPU / 1 GB 24×7, +ALB | **$30–45** |
| **S3 storage** | ~60 GB/mo new, tiering to IA/Glacier, 365d retention | **$5–20** (grows linearly with retention until yr-1 steady state) |
| **KMS** | 1–2 CMKs + requests (Bucket Keys cut request cost >99%) | **$2–4** |
| **SQS** | ~600–1k messages/mo + DLQ + status-writeback + lambda-dlq | **$1–3** |
| **Step Functions** (2B) | ~30 transitions/case × 300 × $0.025/1k | **<$1** ($0.225) |
| **VPC interface endpoints** | **7 interface endpoints × 2 AZ × $7.30** (no `monitoring` endpoint — metrics via gateway S3 Lambda) | **~$102** (2 AZ); ~$153 at 3 AZ |
| **CloudTrail data events + CloudWatch** | thousands of events/mo, logs, custom metrics, dashboards | **$5–15** |
| **Sentry** | 3 projects, team tier | **$0–26** |
| **NAT** | **none by default** (API egress via public-subnet ALB path, §3.7a); add ~$32 only if Supabase needs a stable egress IP | **$0** (or ~$32 if required) |
| **DR / CRR** (optional, §6) | replica bucket + replica CMK + 2nd-region endpoints | **$5–15** |
| **Total (MVP HA, before DR)** | | **~$160–230** |

Notes (fix for H1, L1, L4): the **interface-endpoint line and the HA API are the bill** at this scale. Removing the `monitoring` endpoint (metrics via the free gateway S3 + trusted Lambda) saves a full per-AZ interface-endpoint line (~$15/mo at 2 AZ) *and* closes the H2 metric-channel — a rare case where the cheaper option is also the more secure one. The worker compute, Step Functions, SQS, and KMS numbers are sound and small. The bill is **~85% fixed floor / ~15% variable** at 300/mo: it is "sub-linear" only because the fixed floor dominates (low utilization), so we describe it as **"dominated by a fixed floor at this volume,"** not as an efficiency achievement. Storage grows linearly with retention. If the worker is acceptably **single-AZ** (it is on-demand, redrivable, min=0), pinning worker/validation-Lambda subnets to one AZ would roughly halve the endpoint line to ~$51 — an explicit, documented trade (single-AZ worker), not a silent assumption.

---

## 5. CI/CD, IaC & observability

### 5.1 IaC choice: Terraform

**Terraform (OpenTofu-compatible HCL), not CDK.** This is a close call and the reasoning is load-bearing:

| Factor | Terraform | CDK | Decides for *this* system because |
|---|---|---|---|
| **Supabase is first-class** | `supabase/supabase` provider manages projects/branches/PITR/network restrictions declaratively | No native construct; custom-resource shim | The portal's primary datastore is **not AWS**. Terraform treats Supabase, Stripe, Sentry, AWS as peers under one `plan`. Biggest differentiator. |
| **Multi-provider blast radius** | Stripe, Cloudflare/CDN, Sentry (`jianyuan/sentry`) all in one graph | Each non-AWS provider is a bespoke escape hatch | A KMS+S3 change and a Sentry alert-rule change land in the **same reviewed plan**. |
| **State as a reviewable artifact** | `terraform plan` posted to the PR is the gate | CloudFormation changesets; noisier diffs | The CI gate (§5.3) hinges on a human reading a plan. |
| **Language** | HCL | TypeScript (shared with `apps/api`/`apps/web`) | The one real point *for* CDK; does not outweigh Supabase + multi-cloud. |

Pin AWS provider `~> 5.x`, Terraform `~> 1.9` (or OpenTofu `~> 1.8`), and every module version. **Remote state & locking:** S3 backend with **native S3 state locking** (`use_lockfile = true`, GA in AWS provider 5.x — no DynamoDB table) on a dedicated `tf-state` bucket (versioning, SSE-KMS with its own key, BPA, `prevent_destroy`). One state file **per environment per stack**. Bootstrap the state bucket with a tiny local-state `0-bootstrap` module applied once, then committed.

### 5.2 Module / stack layout

The monorepo reserves `infra/`. Use root-modules-call-shared-modules (composition root):

```
infra/
  modules/                      # reusable, env-agnostic, no provider/backend blocks
    network/                    # VPC, private subnets, S3/SQS/ECR/CW/KMS endpoints (account-pinned policies),
                                #   public-subnet API path, no NAT on compute, no monitoring endpoint
    storage/                    # cases bucket, previews bucket, data CMK (+enc-context) + secrets CMK, lifecycle, CRR
    queue/                      # stage1/stage2 FIFO + DLQs, status-writeback q, lambda-dlq, alarms (NO redrive-back)
    worker/                     # ECR repo, 2 ECS task defs (sandboxed, per-def thread caps), exec+task roles, log groups
    launcher/                   # ESM/Pipe + RunTask launcher Lambda (owns ecs:RunTask + scoped PassRole)
    api/                        # always-on Fargate service min 2/2 AZ, ALB, autoscaling, task role (no RunTask/PassRole)
    metrics/                    # trusted out-of-band metrics Lambda (reads report/*, emits CasePrep/Quality)
    stepfn/                     # Step Functions state machine (gated enable_step_functions=false at MVP)
    observability/              # dashboards, log-metric-filters, alarms, SNS topics, Sentry projects
    iam/                        # GitHub OIDC provider, CI plan/apply roles, SCP guardrails
    audit/                      # CloudTrail (+ data events) to separate logging account, logs bucket, Object Lock compliance
    secrets/                    # Secrets Manager containers (values injected out-of-band, not in state)
  envs/
    staging/                    # root: backend{}, providers{}, calls modules/* with staging vars
    prod/                       # root: backend{}, providers{}, calls modules/* with prod vars
  0-bootstrap/                  # one-time: tf-state bucket, GitHub OIDC provider (local→committed)
```

`modules/*` never declare a `provider`/`backend`; `envs/*` are the only places that do, so staging and prod call the *same* module versions with different `tfvars`. Every resource tagged `Project`, `Environment`, `ManagedBy=terraform`, `CostCenter` (so §4.2 is verifiable per-environment in Cost Explorer). Cross-stack references flow through `terraform_remote_state`/SSM outputs, never hard-coded ARNs. Keep secret *values* out of state by creating empty secret containers in TF and populating via a separate privileged path.

### 5.3 CI/CD — GitHub Actions

Five workflows. **OIDC, never long-lived AWS keys** — the GitHub OIDC provider lets each workflow assume a scoped role with `sub` conditioned on `repo:ORG/REPO:environment:staging|prod`.

- **A — `worker-ci.yml` (PR gate, worker).** Triggers on `apps/worker/**`. Python **3.11** matrix. `pip install -e ".[dev]"` → `ruff`/`mypy` → `pytest -q` (the **63 tests** are the regression wall) **plus the new redelivery-determinism test** (§1.10: same borderline mesh twice ⇒ identical tooth↔pose or identical FLAG). Open3D is import-lazy, so pure domain + metrics tests run even on a runner lacking the wheel; mark Open3D-touching tests to degrade gracefully. Green required to merge.
- **B — `portal-ci.yml` (PR gate, web+api).** `pnpm install` → `turbo run typecheck lint test` across `apps/api`, `apps/web`, `packages/shared`, including the **RLS cross-tenant denial tests, the state-machine transition tests, and seed-payload bounds-check tests** (security-critical, block merge).
- **C — `worker-image.yml` (build → scan → push).** On merge to `main`/tags: multi-stage build → **Trivy scan (fail on fixable HIGH/CRITICAL)** → **sandboxed Open3D smoke test inside the real task def (L3)** → push to ECR tagged with the **git SHA** (immutable — never `latest`). ECR scan-on-push is the second scan. `syft` SBOM attached for clinical traceability.
- **D — `infra-plan.yml` (PR gate, infra).** On `infra/**`: `terraform fmt -check`, `validate`, `tflint`, **`tfsec`/`checkov`** (catch a public bucket / over-broad IAM / missing endpoint policy before merge), then `terraform plan` for staging and prod posted as a PR comment. No apply.
- **E — `deploy.yml` (staged apply, manual approval).** On merge to `main`, gated by GitHub Environments: **staging** auto-applies the new image SHA → smoke tests (enqueue a synthetic case stage-1 → seed-stub → stage-2, assert `ready` + a report artifact in S3); **prod** requires a named-reviewer approval and promotes the *exact SHA* validated in staging — build once, promote, never rebuild for prod.

Dependency-ordered path: **typecheck+pytest (A/B) → build+scan+sandbox-smoke+push (C) → plan with approval (D/E) → staging → prod**, prod behind a human gate.

### 5.4 Observability

Three correlated layers, all keyed by **`case_id`** so one case traces from API enqueue → stage-1 → operator seed → stage-2 → delivered.

**Structured logs.** Worker logs **JSON to stdout** (a `structlog`/`python-json-logger` adapter at the composition root — it does not touch the pure domain), every line carrying `{ case_id, tenant_id, stage, attempt, pipeline_version, event }` (`attempt` is the observability-only counter from §1.8). FireLens/awslogs ships to a CloudWatch Log Group per service (`/ecs/worker`, `/ecs/api`), retention 30d (staging) / 90d (prod). The NestJS API stamps the same envelope via a Nest interceptor, so **CloudWatch Logs Insights** answers "everything that happened to case X" in one query.

**Infra metrics + alarms** (operability — *not* the scaling signal, §4.1):

| Metric (source) | Alarm | Why |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` (stage1/2) | > backlog for 15 min | cases piling up — task launch stuck |
| `ApproximateAgeOfOldestMessage` | > 30 min | a case is starving |
| **DLQ depth ≥ 1** (stage1/2-dlq) | immediate (page) | **a case fell back to manual; an operator must be paged** |
| **`lambda-dlq` depth ≥ 1** | immediate (page) | a validation/DLQ-drain Lambda failed — a case could vanish (M3) |
| ECS worker `MemoryUtilization` | > 90% | 8 GB too tight for a dense scan — OOM / decompression-bomb signal |
| ECS task non-zero exit | > 0 | crash, possibly a malicious-mesh parser fault |
| API ALB 5xx / unhealthy targets | > 1% / < 2 healthy (page) | portal enqueue/presign path degraded (min-2 means one task can fail without outage) |
| Step Functions `ExecutionsFailed`/`TimedOut` (2B) | > 0 | a step's retry/catch exhausted |

Alarms fan out to **SNS → Slack** (warnings) and **PagerDuty/email** (page-worthy: DLQ depth, lambda-dlq depth, API degraded).

**The custom business metrics — the go/no-go numbers (major correctness fix: C2).** The program's funding decision rests on two numbers, *segmented* by scan-body-type and case-type (retention): **clear-rate** and **false-confidence-rate**. They are emitted by the **trusted `dac-metrics-emitter` Lambda** (not the sandbox — H2/M5), and they are **not the same kind of number**:

- **`ClearRate` — measured live, per case.** The worker knows what its gate auto-passed, so clear-rate is a true per-case measurement aggregated over a trailing window.
- **`FalseConfidenceRate` — an ESTIMATE from a sampled ground-truth audit loop, NOT a per-case measurement.** This is the critical correction. `domain/metrics.py:false_confidence_rate` operates on `ImplantOutcome(passed, within_tolerance)`, and `within_tolerance` requires comparing the recovered pose to **held-out ground-truth** (`position_error_mm(recovered, truth)`, …). **On a real client scan there is no `truth`** — recovering it *is* the job. So in the golden/demo harness (§7) the number is real, but **in production it cannot be measured per case.** Emitting a hard-coded 0 (or anything derived without truth) would make the system's #1 clinical-safety tripwire **structurally blind**.

  Production therefore defines `FalseConfidenceRate` over an **audited subset**: a sampled fraction of PASS cases is routed (async) to a human/RealGUIDE ground-truth check; the verified pose is written back to an audit store; the trusted Lambda computes false-confidence-rate over that audited sample on a trailing window, **with a sample-size floor** (a 2% rate on n=5 is noise — the alarm requires a minimum audited n per segment before it can fire). The dashboard and alarm are explicitly labelled "over audited sample (n=…)". **Until the audit loop exists, the alarm is decorative and is documented as such — it is not presented as a live safety control.**

The worker still computes and serializes the report (`domain/metrics.py` + `adapters/report_writer.py` → `accuracy-report.json`); the observability work is to (a) emit the live `ClearRate` from it and (b) feed PASS cases into the audit loop and emit the sampled `FalseConfidenceRate` from the audit store — both via the trusted Lambda. Metrics in namespace `CasePrep/Quality`:

| Metric | Dimensions | Semantics |
|---|---|---|
| `ClearRate` | `ScanBodyType`, `Retention`, `Environment` | percent auto-passed by the gate (live, per-case aggregate) |
| `FalseConfidenceRate` | `ScanBodyType`, `Retention`, `Environment`, `AuditedN` | **safety number — auto-passed yet out of tolerance, over the audited sample; target ≈ 0; requires AuditedN ≥ floor to alarm** |
| `ImplantsAutoPassed` / `ImplantsFlagged` | `ScanBodyType`, `Retention` | counts |
| `CountReconciled` (0/1) | `Environment` | scan-body count-gate over/under-detection |
| `RegistrationRMSE`, `ClockingGap` | `ScanBodyType`, `Retention` | raw confidence distribution feeding the auto-clock allow-list |

> **Cardinality caution (L4).** `ScanBodyType` is a free-text `text` column in `implant_sites` (effectively unbounded), and custom metrics bill ~$0.30/metric/mo per unique dimension combination. Before treating CloudWatch at "$5–15," **constrain `ScanBodyType` to a bounded enum/allow-list** (or hash-bucket unknowns into `other`) so `ScanBodyType × Retention × metric` cardinality is bounded. This is also a defense against a dimension-cardinality cost blow-up.

Per-case rates are noisy, so **alarms run on aggregated math expressions** over a trailing window (7-day or last-50-cases / last-N-audited) per `ScanBodyType`×`Retention`:

- **`FalseConfidenceRegression` (critical, clinical-safety):** windowed false-confidence-rate **over the audited sample** for any segment with `AuditedN ≥ floor` rises above a near-zero floor (e.g. > 1%). This pages *and* (in 2B) writes the allow-list flag that **drops a scan-body-type off the auto-clock allow-list**. A confident-but-wrong implant reaching a patient is the worst outcome in the system — which is exactly why the metric must be honestly grounded in audited truth, not fabricated.
- **`ClearRateRegression` (warning, economic):** windowed clear-rate for a segment falls materially below baseline. Clear-rate is the ROI number; a regression means a model/library/threshold change quietly broke the economics.

A **CloudWatch dashboard** renders `ClearRate` (live) and `FalseConfidenceRate` (audited-sample, with `AuditedN`) as time series broken out by scan-body-type and retention — the "automation-monitor page."

**Sentry.** Three projects (web, api, worker) provisioned by the Sentry Terraform provider; the worker SDK tags every event with `case_id`, `tenant_id`, `pipeline_version`, `stage`. **Scrub aggressively**: `before_send` strips any file path / vertex data, keeping only opaque case labels. Sentry releases tagged with the git SHA = the deployed image, so a regression is attributable to a deploy.

---

## 6. Backup & DR

The irreplaceable assets are **(a) Supabase Postgres** (case state, ownership, orders, audit/traceability) and **(b) the S3 scan + deliverable objects**. DR is specified per asset with a *tested* restore, and — critically — **with a referential-consistency assertion across the two** (fix for H4-ops).

| Asset | Mechanism | RPO | RTO |
|---|---|---|---|
| **Supabase Postgres** | Pro-tier **PITR** (continuous WAL) + daily logical backups | ≈ minutes | ≤ 1–2 h, runbooked |
| **S3 scans/deliverables** | **Cross-region replication** to a DR-region bucket (SSE-KMS, replica CMK, replicated enc-context) + versioning | ≈ minutes (CRR async, < 15 min typ.) | minutes — repoint API to replica |
| **App/infra** | Terraform state + git; redeploy from a SHA into the DR region | n/a (declarative) | ≤ 1 h |
| **KMS** | Replica CMK in the DR region; replication role re-encrypts | n/a | included — the DR-region key must exist *before* an incident |

**The two RPOs are different clocks, so the system RPO is the MAX of the two** (fix for H4-ops). Postgres PITR and S3 CRR can land at different recovery points, so after failover you can get a DB row marked `ready` referencing an `outputs/...zip` that **CRR had not yet replicated** (or an object with no row). DR for this system must prove the *join*, not each asset in isolation. **Targets for the funder: RPO = max(DB, S3) ≈ minutes; documented RTO ≤ 2 hours.**

The restore is **tested, not assumed**: a **quarterly DR game-day** PITR-restores Supabase to a scratch project and asserts row counts + a known case's state; fails a read path over to the S3 replica and re-runs a signed download; `terraform apply`s the stack into the DR region from a SHA; **and asserts referential consistency — every `result_key` in the restored DB resolves to an object in the replica bucket, and flags orphans in both directions**; then records achieved RPO/RTO against target. Consider gating the user-visible `ready`/deliverable-download transition behind a **replication-confirmed check** so the portal never offers a deliverable that hasn't replicated. **Versioning + deny-delete on the scans prefix except a break-glass role** defends the *more common* disaster — accidental/malicious delete — which CRR alone does **not** protect against (CRR replicates deletes unless configured otherwise; versioning is what saves you). CRR is optional at MVP (open questions / cost table); versioning + PITR + the referential-consistency game-day assertion are not.

---

## 7. Demo → production validation automation

The validation harness proves the pipeline's go/no-go numbers on a golden set and publishes a stakeholder-facing dashboard, mapping the demo deliverable onto the same metric machinery that runs in prod (§5.4) — **with the honest caveat that `FalseConfidenceRate` is fully measurable here (ground truth exists) but only audited-sample-estimable in prod (C2).**

- **Golden set, two tiers.** **Synthetic goldens committed in-repo** drive the fast PR gate (deterministic, no biometric data in git). **Real-case goldens** (client scans + libraries + ground-truth poses — biometric-adjacent) are **pulled from a KMS-encrypted S3 prefix** in a nightly/manual gated job only, never committed.
- **CI accuracy gate.** Assert **loose hard-fail bounds** (the existing integration bounds: position < 0.5 mm, axis < 3.0°, clocking < 10°) so the gate is stable across BLAS/arch differences, plus a **separate non-blocking "drift" warning band** near the measured actuals (0.067–0.074 mm, 0.28–0.66°) that catches silent regressions without failing the build on numerical drift. Because the spike runs 3.9/arm64 with the custom ICP while prod runs 3.11/linux-amd64, the loose bound is wide enough to cover both; if per-platform divergence proves material, pin expected values per-platform in a CI matrix.
- **Dashboard.** Renders, per scan-body-type and retention, the same `ClearRate` / `FalseConfidenceRate` / RMSE / clocking-gap that `accuracy-report.json` emits. **The demo dashboard and the prod automation-monitor share the *report schema and clear-rate*, but the prod `FalseConfidenceRate` is an audited-sample estimate, not the demo's full-truth number** — the dashboard labels which is which so stakeholders are not told an unmeasurable prod number is "the same" as the demo's. The **overlay-render column** (library mesh superimposed on scan per implant) is **net-new ~80 LOC** (matplotlib/trimesh, headless Agg) and does not yet exist — ship with a placeholder column if overlays are descoped for the first demo (open question #21).
- **Where the dashboard lives.** Either a CI build artifact, or pushed to the existing **previews bucket** behind auth (Cognito / signed URL), pending the access-control decision.

This closes the loop: clear-rate is computed once in the worker, asserted in CI against golden cases, rendered for the demo, and emitted/trended/alarmed live in prod; false-confidence-rate is fully proven on goldens and *estimated from the audit loop* in prod — one report schema, two honest readings.

---

## 8. Phased rollout (tied to the engagement gates)

| Phase | Scope | Compute | Orchestration | What ships | Gate to advance |
|---|---|---|---|---|---|
| **Foundation** | IaC + data plane + **DB migration** | — | — | `infra/` Terraform: network (no-NAT compute VPC + account-pinned endpoints, no monitoring endpoint), storage (3 buckets, data CMK with enc-context + secrets CMK, pinned default encryption, lifecycle), IAM roles + SCP, audit (CloudTrail to separate account, Object Lock compliance), secrets containers, ECR. **Schema migration (`stage`, enriched `case_status`, `tenant_id`) merged + applied in staging.** CI workflows A–E wired. | `terraform apply` clean in staging; smoke test green; security scans pass; **migration applied**. |
| **2A — pipeline hardening** | Worker containerized + sandboxed + **localization determinism** | One x86_64 image, two task defs (per-def thread caps), full sandbox (§1.6), pinned/hashed lockfile | Manual `RunTask` / CLI; no queues yet | The 63 tests + **redelivery-determinism test** in CI on 3.11; **sandboxed Open3D smoke test green**; worker runs a synthetic case end-to-end in-cluster; peak-RSS + wall-time emitted via the trusted report path. | First ~50 **real** client scans profiled; stage2 peak RSS ≤ 8 GB (else 2vCPU/16GB); cluster-ordering determinism verified. |
| **2B — MVP automation** | **SQS + per-message RunTask launch at the human boundary** | Same two task defs, on-demand min=0 | **2× FIFO SQS + DLQ**, ESM→launcher→`RunTask`, validation Lambda (+on-failure DLQ, tagged-delete), outbox enqueue, operator seed → stage-2, DLQ-drain → manual fallback (+on-failure DLQ), trusted metrics Lambda, **audit loop scaffolding for FCR**. Heartbeat abstraction pluggable. `stepfn` present but `enable_step_functions=false`. | `ClearRate` emitted live + segmented; `FalseConfidenceRate` emitted over audited sample with `AuditedN` floor; regression alarms live (FCR alarm armed only once audit loop produces n≥floor). | **Go/no-go on the metrics:** clear-rate at/above baseline; audited false-confidence-rate ≈ 0 per segment; cost table re-validated against measured wall-clock and **honest HA endpoint/API bill**. |
| **2B+ — Step Functions graduation** | Once **localization is automatic** | Same image; tasks via `ecs:runTask.sync` | **Flip `enable_step_functions=true`.** Standard workflow, server-side-token `waitForTaskToken` seed, `Map` per-implant, per-state Retry/Catch → `ManualFallback`, `RouteToManual` as Lambda+Succeed. Starter Lambda `StartExecution(name={case_id}:{submission_uuid})`; SQS stays ingress. **Per-case `sts:AssumeRole` session-policy + KMS enc-context tightening turned on** (closes §3.2 MVP residual). ARM64 revisit gate (sandboxed CI matrix on Graviton). | Stage-2 chain lengthens; per-step checkpointing earns its keep; per-case CMK boundary enforced. | Localizer/classifier clears allow-list bar; execution history demonstrates per-step resumability. |
| **2C — ML / GPU** | Learned localizer / classifier | **AWS Batch on GPU EC2** (`g5`/`g4dn`, spot-biased, scale-to-zero), *separate* GPU image, separate IAM/cost line | Additional Step Functions branch invoking the Batch job | GPU inference plugged in as a branch; CPU worker unchanged. | Cost-per-case and accuracy beat the manual-seed baseline. |

The phasing is **incremental and reversible**: SQS remains the ingress in both 2B epochs, so graduation swaps the *consumer* without touching the API enqueue contract or DB lifecycle; the `stepfn` module ships dormant-but-tested; and the worker image/task defs are unchanged from 2A through 2B+.

---

## 9. Consolidated open questions

**Sizing & performance**
1. **Worst-case real-mesh memory.** Profile the first ~50 real scans for peak RSS before locking stage2 sizing; if any exceed 8 GB, next legal step is 2 vCPU / 16 GB.
2. **Real per-case wall-clock.** Re-measure ~90 s (stage1) + ~240 s (stage2) on real ~1–5M-vertex scans — also the 2B go/no-go input and the cost-table input.
3. **Average implant sites/case.** ICP cost scales ~linearly with implant count; 300/mo assumes ~2 sites/case.
4. **Stage-1 cold-start tolerance.** Is the Slack "needs seeding" alert tolerant of a 60–120 s scale-from-zero, or is sub-minute latency required (pay for one warm task)?
5. **Launcher pattern confirmation.** Confirm the per-message `ESM/Pipe → RunTask launcher Lambda` is preferred over an always-on backlog-per-task ECS service at this volume (recommended: yes — true min=0).

**Orchestration & domain contracts**
6. **Schema migration (BLOCKING for 2B).** `docs/schema.sql` lacks `processing_jobs.stage`, the enriched `case_status` (`awaiting_seed|queued|assigned`), and `cases.tenant_id`. Confirm and sequence the migration; the entire claim-lock/idempotency/IAM-scoping layer depends on it.
7. **Tenancy model.** `tenant_id == owner_id` (one shop = one tenant) or an org id above logins? Determines the S3 key layout, IAM prefix, and **KMS encryption context** keys.
8. **Localization determinism (BLOCKING for 2A correctness).** Confirm the stable-geometric cluster ordering + localization-result-hash output key + FLAG-on-`detected!=declared` change to `orchestrator.py`/`engine.localize`, gated by the redelivery-determinism test.
9. **Seed-artifact contract.** Define `seed.json` (per-implant ROI / picked points) under the case S3 prefix and the `run_case` entry point that accepts it; include the server-side bounds-check contract.
10. **Operator-seed SLA window.** Drives `waitForTaskToken` `TimeoutSeconds` + escalation tier (24 h placeholders).
11. **Stage-1 Open3D dependency.** Does stage-1 need Open3D/DBSCAN, or only stage-2? If parse+clean only, a thinner stage-1 image is possible (at the cost of single-image provenance).
12. **Per-tenant fairness.** With `MessageGroupId=case_id` there's no cross-tenant head-of-line blocking, but one tenant could monopolize on-demand Fargate concurrency. Out of scope at 300/mo; flag if a per-tenant cap is required.

**Storage, security & DR**
13. **Retention window** (contractual). Parameterized, default 365d; confirm value and whether outputs differ from inputs.
14. **KMS encryption-context rollout.** Confirm S3 PUTs (presign + worker) set per-case `tenant_id`/`case_id` context, and that the MVP residual (full per-case KMS pin only from 2B) is acceptable with the compensating S3-prefix + one-message-per-task controls (§3.2 residual).
15. **Cross-region DR posture.** Single-region us-east-1 / no CRR is the MVP default. Confirm full active CRR (+~$5–15/mo, replica CMK) vs cheaper snapshot posture, and the contractual RPO/RTO. **System RPO = max(DB, S3).**
16. **Audit account separation + Object Lock compliance.** Confirm CloudTrail ships to a **separate logging account** and the audit trail uses **compliance** (irreversible) Object Lock — recommended for medical traceability (M4).
17. **Multipart size enforcement.** Confirm presign-time `Content-Length` range + server-side part-count cap (M2-cost) and the validation Lambda's tagged-delete of rejected uploads.
18. **Secrets CMK separation.** Recommend a dedicated `alias/cad-secrets`; confirm or collapse.
19. **Region / data residency.** Cost model assumes us-east-1; a residency requirement for biometric-adjacent data re-prices Fargate/KMS/egress.

**Observability & CI/CD**
20. **Production false-confidence-rate audit loop (BLOCKING for the safety alarm — C2).** Confirm the sampled ground-truth audit loop (route a fraction of PASS cases to human/RealGUIDE verification, write truth back, compute FCR over the audited subset with a sample-size floor). Until it exists, the `FalseConfidenceRegression` alarm is decorative — confirm acceptance of that interim state and the target audit sampling rate.
21. **Metric emission is out-of-band.** Confirm metrics are emitted by the trusted `dac-metrics-emitter` Lambda from the signed `accuracy-report.json` (sandbox is metric-blind by design — H2/M5), not from inside the worker.
22. **`ScanBodyType` cardinality.** Confirm `ScanBodyType` is constrained to a bounded enum/allow-list before relying on the CloudWatch cost estimate (L4).
23. **Status write-back path.** Confirm the scoped `status-writeback` SQS queue drained by the API (worker holds no DB creds), and that the RLS-bypass Supabase key is confined to the drain context (H1), over the one-endpoint alternative.
24. **Endpoint AZ count / worker single-AZ.** The cost line hinges on AZ count. Confirm 2-AZ endpoints (~$102/mo) for HA, or accept a documented **single-AZ worker** (~$51/mo) given it is on-demand/redrivable/min=0 (H1-cost).
25. **API HA.** Confirm API min 2 / 2 AZ (M5) and no NAT (public-subnet ALB egress) unless Supabase network-restrictions demand a stable egress IP (M1).
26. **Alarm routing.** DLQ-depth, lambda-dlq-depth, and API-degraded page (PagerDuty/email); quality/backlog regressions go to Slack. Confirm there is an on-call rotation, or everything routes to Slack at MVP.
27. **Sentry tier.** Three projects + Terraform-provider alert-rule management assume the paid team tier; confirm.
28. **Step Functions migration trigger.** Tied to "localization is automatic." Confirm `stepfn` ships dormant-but-tested and the heartbeat abstraction is pluggable from day one; confirm `RouteToManual` is the Lambda+Succeed implementation (H3).

**Demo validation**
29. **Overlay renders** (~80 LOC, not yet in code) in-scope for the demo, or placeholder column first?
30. **Golden expected values across platforms.** Pin per-platform (matrix), or one tolerance band wide enough for 3.9/arm64 and 3.11/linux-amd64? (Recommend loose hard-fail bounds + non-blocking drift band.)
31. **Real-case golden storage.** Synthetic goldens in-repo for the fast gate; real (biometric-adjacent) goldens pulled from a KMS-encrypted S3 prefix in a gated job. Confirm.
32. **ARM64 revisit gate (2B).** Needs the sandboxed golden-case CI matrix against the linux-arm64 Open3D wheel on Graviton (L3). Is the golden-case set already available to gate on?

---

## 10. Review remediations

This section records what changed in response to the two adversarial reviews (Security & Correctness; Cost & Operability) and any accepted residual risk.

**Critical (security) — all fixed:**
- **C1 — KMS not a real boundary.** Added a **per-tenant/per-case encryption-context** binding on `kms:Decrypt`/`GenerateDataKey` (§3.2, §3.5), required on every data-plane statement; the Step Functions per-case session pins `kms:EncryptionContext:case_id` to the exact case (§3.5). Dropped `dac-validation-lambda` to inputs-context only. *Residual (accepted, low):* before 2B the per-case KMS pin is not yet active; the MVP compensating controls are S3-prefix IAM + one-message-per-task launch (a task only ever sees one case_id). Documented in §3.2.
- **C2 — `FalseConfidenceRate` unmeasurable in prod.** Reframed (§5.4, §7) as an **audited-sample estimate** from a sampled ground-truth loop with a minimum-`AuditedN` alarm floor, *not* a per-case measurement (real cases have no held-out truth). The `FalseConfidenceRegression` alarm is explicitly **decorative until the audit loop exists** and is documented as such; the demo (full-truth) and prod (audited-sample) numbers are no longer claimed identical. Blocking open question #20.
- **C3 — `IfExists` lets unkeyed `aws:kms` PUTs fall to the default key.** Added a `Null` deny (`DenyMissingKmsKeyHeader`) and pinned the bucket default encryption to the CMK (§3.1).

**High — all fixed:**
- **H1 (sec) — API role over-powered.** Removed `ecs:RunTask`/`iam:PassRole` from `dac-api-task` (moved to a dedicated launcher Lambda scoped to exact task-def revisions, fixed env allow-list, `iam:PassedToService`); replaced the API's RLS-bypass service-role key with a scoped app role via RPC, confining the service-role key to the status-writeback drain context (§3.5, §3.6, §3.8).
- **H2 (sec/ops) — "exfiltration impossible by routing" overstated + no scaling trigger.** Restated the claim honestly ("no internet egress; AWS-API egress constrained by account-pinned endpoint policy"); added account-pinned policies to every interface endpoint, an explicit bucket-`Deny` on the S3 gateway endpoint, turned off STS reachability for the MVP worker, and **removed the `monitoring` endpoint** by moving metric emission to a trusted out-of-band Lambda (§1.6, §3.7). Specified the actual **scale-from-zero trigger** (ESM/Pipe → launcher Lambda → `RunTask`) and replaced "queue depth" with **backlog-per-task** for any future service variant (§1.8, §4.1).
- **H3 (sec) — broken `RouteToManual` ASL.** Reimplemented `RouteToManual` as a Lambda `Task` + `Succeed` with its own Retry/Catch; removed the tokenless `sfn:sendTaskSuccess` misuse (§2.9, §2.12).
- **H4 (sec) — non-deterministic tooth↔cluster remap on redelivery.** Added a stable-geometric cluster ordering, a localization-result-hash output key, and FLAG-on-`detected!=declared`; gated by a redelivery-determinism test (§1.8, §1.10). **H4 (ops) — DR consistency.** Defined system RPO = max(DB, S3) and added a referential-consistency game-day assertion (§6).
- **H5 (sec) / M2 (ops) — dedup-id contradiction.** Dedup and output-identity keys are now **`{case_id}:{stage}`** with no `attempt`; `attempt` is observability-only (§1.8, §2.2, §2.6, §2.7).

**Medium — addressed:**
- **M1 (sec) — schema missing columns.** Made the migration a **blocking Foundation gate** and flagged every dependent section as not-buildable until it lands (§2 intro, §8, open #6).
- **M2 (sec/ops) — multipart size bypass + no cleanup role.** Presign-time `Content-Length` range + server part-count cap; validation Lambda gains a tagged-`validation=failed` `s3:DeleteObject` to remove rejected blobs (§3.4, §3.5).
- **M3 (sec) — seed token confidentiality.** Task token stays server-side, keyed by `case_id`; console references the case only; seed payload bounds-checked (§2.9, §2.12). **M3 (ops) — Lambda failure paths.** Validation and DLQ-drain Lambdas get on-failure SQS DLQs, alarmed (§2.5, §5.4).
- **M4 (sec) — audit tamper.** Audit trail → **separate logging account** + **compliance-mode** Object Lock + second region (§3.9).
- **M5 (sec) — metric channel/poisoning.** Business metrics emitted by the trusted out-of-band Lambda, never the sandbox (§1.6, §3.5, §3.7, §5.4). **M5 (ops) — API SPOF.** API min 2 / 2 AZ (§3.7a, §4.1).

**Low — addressed where cheap:**
- **L1 — thread pinning moved from image to per-task-def env** (stage1=1, stage2=2) so a 1-vCPU task isn't oversubscribed (§1.3, §1.5).
- **L2 — execution name** changed to `{case_id}:{submission_uuid}`; DB claim is the authoritative single-active guard (§2.11, §2.13).
- **L3 — sandboxed Open3D smoke test** in CI inside the real task def before 2A/ARM revisit (§1.4, §5.3).
- **L4 — CloudWatch cardinality:** constrain `ScanBodyType` to a bounded enum; removed the `monitoring` endpoint cost line (§4.2, §5.4).
- **L5 — untrusted `declared_count`:** flagged to cap the manifest `declared_count` (e.g. ≤ 32) before it reaches `localize`/`Map` fan-out (folded into the seed-contract/validation work, open #9; manifest cap noted as a validation requirement).

**Cost narrative corrected:** the headline moved from "~$120–200, worker is single-digit so ARM is immaterial" to an **HA-honest ~$160–230/mo dominated by per-AZ interface endpoints + the always-on min-2 API** (§4.2). The NAT self-contradiction was removed (no NAT by default). The "sub-linear" framing was relabelled "dominated by a fixed floor at this volume."

**Accepted residual risks (explicit):**
1. **MVP KMS per-case scoping** is prefix/launch-based, not encryption-context-pinned, until 2B (§3.2). Low, time-boxed, compensated.
2. **`FalseConfidenceRegression` alarm is decorative until the audit loop ships** (§5.4, open #20). The mitigation is that clear-rate and per-case gate FLAGs remain live, and the gate itself fails closed (verified in `domain/confidence.py`).
3. **Single-AZ worker** is offered as a documented ~$51/mo option vs ~$102/mo for 2-AZ HA endpoints (§4.2, open #24); acceptable because the worker is on-demand, redrivable, and min=0.

**Confirmed-correct (not changed):** dual execution/task-role separation; worker has no Delete/List/stage-SendMessage; `evaluate_gate` fails closed on non-finite signals and missing screw-retained clocking evidence (`domain/confidence.py`); `DenyInsecureTransport` + `BucketOwnerEnforced`/BPA; separate previews bucket; Standard (not Express) Step Functions for `waitForTaskToken` + long human waits; Step Functions cost (~$0.225/mo); worker compute / SQS / KMS arithmetic.
