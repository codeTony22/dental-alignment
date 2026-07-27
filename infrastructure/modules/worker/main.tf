variable "name_prefix" { type = string }
variable "region" { type = string }
variable "worker_cpu" { type = number }
variable "worker_memory" { type = number }
variable "worker_image" { type = string }
variable "subnet_ids" { type = list(string) }
variable "security_group" { type = string }
variable "cases_bucket_arn" { type = string }
variable "previews_bucket_arn" { type = string }
variable "kms_key_arn" { type = string }
variable "stage1_queue_arn" { type = string }
variable "stage2_queue_arn" { type = string }
variable "stage1_queue_url" { type = string }
variable "stage1_queue_name" { type = string }

resource "aws_ecr_repository" "worker" {
  name                 = "${var.name_prefix}-case-prep"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name_prefix}-case-prep"
  retention_in_days = 30
}

# ---- roles --------------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-worker-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Least-privilege task permissions: prefix-scoped S3, consume-only on the stage queues,
# KMS usable ONLY via S3, CloudWatch limited to the quality namespace.
data "aws_iam_policy_document" "task" {
  statement {
    sid       = "ScanObjects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.cases_bucket_arn}/tenant/*", "${var.previews_bucket_arn}/*"]
  }
  statement {
    sid       = "ListCases"
    actions   = ["s3:ListBucket"]
    resources = [var.cases_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["tenant/*"]
    }
  }
  statement {
    sid       = "ConsumeQueues"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
    resources = [var.stage1_queue_arn, var.stage2_queue_arn]
  }
  statement {
    sid       = "UseKeyViaS3Only"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${var.region}.amazonaws.com"]
    }
  }
  statement {
    sid       = "EmitQualityMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["CasePrep/Quality"]
    }
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${var.name_prefix}-worker-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# ---- task definition ----------------------------------------------------------------
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-case-prep"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # x86_64, NOT arm64: Open3D 0.18 registration_icp and offscreen render both segfault on
  # the arm64 wheel (found during the 2A spike). Pin x86_64 in production.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name                   = "case-prep"
      image                  = var.worker_image
      essential              = true
      readonlyRootFilesystem = true
      user                   = "10001"
      linuxParameters        = { initProcessEnabled = true }
      environment = [
        { name = "STAGE1_QUEUE_URL", value = var.stage1_queue_url },
        { name = "METRIC_NAMESPACE", value = "CasePrep/Quality" },
        { name = "AWS_REGION", value = var.region },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# ---- scale-from-zero service --------------------------------------------------------
resource "aws_ecs_service" "worker" {
  name            = "${var.name_prefix}-case-prep"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.security_group]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count] # autoscaling owns it
  }
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 10
}

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.name_prefix}-scale-out"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  policy_type        = "StepScaling"
  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 20
      scaling_adjustment          = 2
    }
    step_adjustment {
      metric_interval_lower_bound = 20
      scaling_adjustment          = 6
    }
  }
}

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.name_prefix}-scale-in"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  policy_type        = "StepScaling"
  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 300
    metric_aggregation_type = "Maximum"
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "backlog" {
  alarm_name          = "${var.name_prefix}-stage1-backlog"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 1
  dimensions          = { QueueName = var.stage1_queue_name }
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]
  ok_actions          = [aws_appautoscaling_policy.scale_in.arn]
}

output "ecr_repository_url" { value = aws_ecr_repository.worker.repository_url }
output "cluster_name" { value = aws_ecs_cluster.main.name }
output "task_role_arn" { value = aws_iam_role.task.arn }
output "service_name" { value = aws_ecs_service.worker.name }
