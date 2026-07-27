variable "name_prefix" { type = string }
variable "kms_key_arn" { type = string }
variable "scan_retention_days" { type = number }

# ---- access-log bucket --------------------------------------------------------------
resource "aws_s3_bucket" "logs" {
  bucket = "${var.name_prefix}-logs"
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    id     = "expire-logs"
    status = "Enabled"
    filter {}
    expiration { days = 90 }
  }
}

# ---- cases bucket (scan inputs + deliverables) --------------------------------------
resource "aws_s3_bucket" "cases" {
  bucket = "${var.name_prefix}-cases"
}

resource "aws_s3_bucket_versioning" "cases" {
  bucket = aws_s3_bucket.cases.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cases" {
  bucket = aws_s3_bucket.cases.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "cases" {
  bucket                  = aws_s3_bucket.cases.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "cases" {
  bucket        = aws_s3_bucket.cases.id
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "cases/"
}

# Deny non-TLS access and any upload not encrypted with OUR CMK.
resource "aws_s3_bucket_policy" "cases" {
  bucket = aws_s3_bucket.cases.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.cases.arn, "${aws_s3_bucket.cases.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyWrongKmsKey"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.cases.arn}/*"
        Condition = {
          StringNotEquals = { "s3:x-amz-server-side-encryption-aws-kms-key-id" = var.kms_key_arn }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "cases" {
  bucket = aws_s3_bucket.cases.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }

  rule {
    id     = "tier-and-expire-inputs"
    status = "Enabled"
    filter { prefix = "tenant/" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration { days = var.scan_retention_days }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

# ---- previews bucket (watermarked render images, pre-payment) -----------------------
resource "aws_s3_bucket" "previews" {
  bucket = "${var.name_prefix}-previews"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "previews" {
  bucket = aws_s3_bucket.previews.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "previews" {
  bucket                  = aws_s3_bucket.previews.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "previews" {
  bucket = aws_s3_bucket.previews.id
  rule {
    id     = "expire-previews"
    status = "Enabled"
    filter {}
    expiration { days = 30 }
  }
}

output "cases_bucket" { value = aws_s3_bucket.cases.id }
output "cases_bucket_arn" { value = aws_s3_bucket.cases.arn }
output "previews_bucket" { value = aws_s3_bucket.previews.id }
output "previews_bucket_arn" { value = aws_s3_bucket.previews.arn }
output "logs_bucket" { value = aws_s3_bucket.logs.id }
