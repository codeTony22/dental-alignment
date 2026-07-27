variable "name_prefix" { type = string }
variable "alarm_email" { type = string }
variable "stuck_case_alarm_minutes" { type = number }
variable "stage1_dlq_name" { type = string }
variable "stage2_dlq_name" { type = string }
variable "stage1_queue_name" { type = string }
variable "stage2_queue_name" { type = string }

resource "aws_sns_topic" "ops" {
  name = "${var.name_prefix}-ops"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.ops.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# A case landing in a DLQ means it fell out of automation and must be picked up manually —
# never let one sit silently.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = { stage1 = var.stage1_dlq_name, stage2 = var.stage2_dlq_name }
  alarm_name          = "${var.name_prefix}-${each.key}-dlq-nonempty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  dimensions          = { QueueName = each.value }
  alarm_actions       = [aws_sns_topic.ops.arn]
  treat_missing_data  = "notBreaching"
}

# Processing backlog ageing past the SLA (work not getting picked up / failing slowly).
resource "aws_cloudwatch_metric_alarm" "stuck_processing" {
  for_each            = { stage1 = var.stage1_queue_name, stage2 = var.stage2_queue_name }
  alarm_name          = "${var.name_prefix}-${each.key}-oldest-message-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.stuck_case_alarm_minutes * 60
  dimensions          = { QueueName = each.value }
  alarm_actions       = [aws_sns_topic.ops.arn]
  treat_missing_data  = "notBreaching"
}

# Human-in-the-loop SLA: a case sitting in awaiting_seed too long. The worker/API emits
# CasePrep/Quality AwaitingSeedAgeMinutes; alarm when the operator hasn't seeded in time.
resource "aws_cloudwatch_metric_alarm" "stuck_awaiting_seed" {
  alarm_name          = "${var.name_prefix}-stuck-awaiting-seed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AwaitingSeedAgeMinutes"
  namespace           = "CasePrep/Quality"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.stuck_case_alarm_minutes
  alarm_actions       = [aws_sns_topic.ops.arn]
  treat_missing_data  = "notBreaching"
}

# The safety-critical metric: confident-but-wrong must stay near zero. Alarm on any
# meaningful false-confidence so a clinical regression is caught immediately.
resource "aws_cloudwatch_metric_alarm" "false_confidence" {
  alarm_name          = "${var.name_prefix}-false-confidence-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FalseConfidenceRate"
  namespace           = "CasePrep/Quality"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 0.01
  alarm_actions       = [aws_sns_topic.ops.arn]
  treat_missing_data  = "notBreaching"
}

output "sns_topic_arn" { value = aws_sns_topic.ops.arn }
