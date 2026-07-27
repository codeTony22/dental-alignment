variable "stage" { type = string }
variable "project" { type = string }
variable "region" { type = string }
variable "service_name" { type = string }
variable "account_id" { type = string }

variable "worker_cpu" { type = number }
variable "worker_memory" { type = number }
variable "worker_image" { type = string }

variable "scan_retention_days" { type = number }
variable "stuck_case_alarm_minutes" { type = number }
variable "alarm_email" { type = string }
