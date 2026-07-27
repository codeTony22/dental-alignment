variable "name_prefix" { type = string }
variable "account_id" { type = string }

# Customer-managed key for scan data at rest. Access is governed by IAM policies on the
# worker/api roles (which additionally pin a per-case kms:EncryptionContext) rather than a
# broad key policy — the key is a genuine second boundary, not just a co-located grant.
resource "aws_kms_key" "scans" {
  description             = "${var.name_prefix} scan data CMK"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      }
    ]
  })

  tags = { Name = "${var.name_prefix}-scans-cmk" }
}

resource "aws_kms_alias" "scans" {
  name          = "alias/${var.name_prefix}-scans"
  target_key_id = aws_kms_key.scans.key_id
}

output "key_arn" { value = aws_kms_key.scans.arn }
output "key_id" { value = aws_kms_key.scans.key_id }
