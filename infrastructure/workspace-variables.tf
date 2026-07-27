variable "stage" {
  description = "Deployment stage (dev, prod)"
  type        = string
}

variable "project" {
  description = "Project identifier used in the artech-{project}-{stage} name prefix"
  type        = string
  default     = "implantcad"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "service_name" {
  description = "Service name for tagging"
  type        = string
  default     = "case-prep"
}

variable "worker_cpu" {
  description = "Fargate worker vCPU units (1024 = 1 vCPU). Dense-mesh jobs need memory; CPU follows."
  type        = number
  default     = 2048
}

variable "worker_memory" {
  description = "Fargate worker memory (MiB). Dense intraoral meshes need 4-8 GB."
  type        = number
  default     = 8192
}

variable "worker_image" {
  description = "Container image URI for the case-prep worker (ECR). CI sets this per deploy."
  type        = string
  default     = ""
}

variable "scan_retention_days" {
  description = "Days to keep delivered case inputs before lifecycle expiry. Confirm with the client (clinical/legal retention)."
  type        = number
  default     = 365
}

variable "stuck_case_alarm_minutes" {
  description = "Age of an awaiting_seed case before the stuck-case alarm fires (human-in-the-loop SLA)."
  type        = number
  default     = 1440
}

variable "alarm_email" {
  description = "Email subscribed to the operations SNS topic (DLQ depth, stuck cases). Empty disables the subscription."
  type        = string
  default     = ""
}
