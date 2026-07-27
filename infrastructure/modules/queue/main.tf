variable "name_prefix" { type = string }
variable "kms_key_arn" { type = string }

locals {
  # geometry jobs run for minutes; visibility must exceed the longest job (heartbeat
  # extension handles the tail). 30 min is comfortable for 2A/2B.
  visibility_seconds = 1800
  retention_seconds  = 1209600 # 14 days
}

resource "aws_sqs_queue" "stage1_dlq" {
  name                      = "${var.name_prefix}-stage1-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = local.retention_seconds
}

resource "aws_sqs_queue" "stage1" {
  name                       = "${var.name_prefix}-stage1"
  visibility_timeout_seconds = local.visibility_seconds
  message_retention_seconds  = local.retention_seconds
  kms_master_key_id          = var.kms_key_arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage1_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "stage2_dlq" {
  name                      = "${var.name_prefix}-stage2-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = local.retention_seconds
}

resource "aws_sqs_queue" "stage2" {
  name                       = "${var.name_prefix}-stage2"
  visibility_timeout_seconds = local.visibility_seconds
  message_retention_seconds  = local.retention_seconds
  kms_master_key_id          = var.kms_key_arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.stage2_dlq.arn
    maxReceiveCount     = 3
  })
}

# Worker -> API status writeback (case state transitions). Drained by the NestJS API.
resource "aws_sqs_queue" "status" {
  name                      = "${var.name_prefix}-status-writeback"
  message_retention_seconds = local.retention_seconds
  kms_master_key_id         = var.kms_key_arn
}

output "stage1_arn" { value = aws_sqs_queue.stage1.arn }
output "stage1_url" { value = aws_sqs_queue.stage1.url }
output "stage1_name" { value = aws_sqs_queue.stage1.name }
output "stage1_dlq_name" { value = aws_sqs_queue.stage1_dlq.name }
output "stage2_arn" { value = aws_sqs_queue.stage2.arn }
output "stage2_url" { value = aws_sqs_queue.stage2.url }
output "stage2_name" { value = aws_sqs_queue.stage2.name }
output "stage2_dlq_name" { value = aws_sqs_queue.stage2_dlq.name }
output "status_url" { value = aws_sqs_queue.status.url }
