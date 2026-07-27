locals {
  name_prefix = "artech-${var.project}-${var.stage}"
}

# Network: a sandboxed VPC with NO internet egress (no IGW/NAT) — the worker reaches
# AWS only through VPC endpoints. Untrusted scan meshes therefore cannot phone home.
module "network" {
  source      = "./network"
  name_prefix = local.name_prefix
  region      = var.region
}

# Customer-managed KMS key bound to a per-tenant/per-case encryption context.
module "kms" {
  source      = "./kms"
  name_prefix = local.name_prefix
  account_id  = var.account_id
}

# Private, versioned, SSE-KMS S3 buckets: scan cases, watermarked previews, access logs.
module "storage" {
  source              = "./storage"
  name_prefix         = local.name_prefix
  kms_key_arn         = module.kms.key_arn
  scan_retention_days = var.scan_retention_days
}

# SQS stage-1 -> awaiting_seed -> stage-2 split, each with a dead-letter queue.
module "queue" {
  source      = "./queue"
  name_prefix = local.name_prefix
  kms_key_arn = module.kms.key_arn
}

# The sandboxed Fargate worker: ECR, cluster, least-privilege roles, task def, and a
# scale-from-zero service driven by queue depth.
module "worker" {
  source = "./worker"

  name_prefix    = local.name_prefix
  region         = var.region
  worker_cpu     = var.worker_cpu
  worker_memory  = var.worker_memory
  worker_image   = var.worker_image
  subnet_ids     = module.network.private_subnet_ids
  security_group = module.network.worker_security_group_id

  cases_bucket_arn    = module.storage.cases_bucket_arn
  previews_bucket_arn = module.storage.previews_bucket_arn
  kms_key_arn         = module.kms.key_arn
  stage1_queue_arn    = module.queue.stage1_arn
  stage2_queue_arn    = module.queue.stage2_arn
  stage1_queue_url    = module.queue.stage1_url
  stage1_queue_name   = module.queue.stage1_name
}

# Alarms: DLQ depth, oldest-message age (stuck processing), the human-in-the-loop
# stuck-awaiting-seed SLA, and a false-confidence-rate regression alarm (the safety metric).
module "observability" {
  source = "./observability"

  name_prefix              = local.name_prefix
  alarm_email              = var.alarm_email
  stuck_case_alarm_minutes = var.stuck_case_alarm_minutes
  stage1_dlq_name          = module.queue.stage1_dlq_name
  stage2_dlq_name          = module.queue.stage2_dlq_name
  stage1_queue_name        = module.queue.stage1_name
  stage2_queue_name        = module.queue.stage2_name
}
