terraform {
  required_version = ">= 1.10"

  # S3 backend with NATIVE state locking (use_lockfile, GA in TF 1.10+) — no DynamoDB
  # lock table needed. Concrete bucket/key/region are supplied per stage via
  #   terraform init -backend-config=backend.<stage>.hcl
  # so the same root targets dev or prod (mirrors the wl-gateway-service convention of
  # keeping the workspace out of the backend block).
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}
