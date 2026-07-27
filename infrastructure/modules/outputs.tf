output "cases_bucket" {
  value = module.storage.cases_bucket
}

output "previews_bucket" {
  value = module.storage.previews_bucket
}

output "kms_key_arn" {
  value = module.kms.key_arn
}

output "stage1_queue_url" {
  value = module.queue.stage1_url
}

output "stage2_queue_url" {
  value = module.queue.stage2_url
}

output "worker_ecr_repository_url" {
  value = module.worker.ecr_repository_url
}

output "worker_cluster_name" {
  value = module.worker.cluster_name
}

output "ops_sns_topic_arn" {
  value = module.observability.sns_topic_arn
}
