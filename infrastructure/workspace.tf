provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Environment = var.stage
      Project     = var.project
      Service     = var.service_name
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# The Phase 2 case-prep platform: a sandboxed Fargate worker that processes untrusted
# scan meshes, fed by an SQS stage-1 -> awaiting_seed -> stage-2 split, with private
# SSE-KMS storage and stuck-case/DLQ alarms. Self-contained per stage.
module "case_prep" {
  source = "./modules"

  stage        = var.stage
  project      = var.project
  region       = var.region
  service_name = var.service_name
  account_id   = data.aws_caller_identity.current.account_id

  worker_cpu    = var.worker_cpu
  worker_memory = var.worker_memory
  worker_image  = var.worker_image

  scan_retention_days      = var.scan_retention_days
  stuck_case_alarm_minutes = var.stuck_case_alarm_minutes
  alarm_email              = var.alarm_email
}
