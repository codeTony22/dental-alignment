variable "name_prefix" { type = string }
variable "region" { type = string }

data "aws_availability_zones" "available" {
  state = "available"
}

# Sandbox VPC: private only. No internet gateway, no NAT — the worker cannot reach the
# internet at all, so a hostile mesh-parser exploit has nowhere to exfiltrate to.
resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 4, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "${var.name_prefix}-private-${count.index}", Tier = "private" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  # intentionally NO default route (0.0.0.0/0) — there is no IGW/NAT to point it at
  tags = { Name = "${var.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Security groups: the worker may only reach the interface endpoints on 443.
resource "aws_security_group" "endpoints" {
  name_prefix = "${var.name_prefix}-endpoints-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.worker.id]
  }
  lifecycle { create_before_destroy = true }
  tags = { Name = "${var.name_prefix}-endpoints-sg" }
}

resource "aws_security_group" "worker" {
  name_prefix = "${var.name_prefix}-worker-"
  vpc_id      = aws_vpc.main.id
  # no ingress at all; egress only to AWS endpoints over 443
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
  lifecycle { create_before_destroy = true }
  tags = { Name = "${var.name_prefix}-worker-sg" }
}

# S3 reached via a (free) gateway endpoint on the route table.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${var.name_prefix}-s3-endpoint" }
}

# Everything else via interface endpoints — keeps all AWS-API traffic inside the VPC.
locals {
  interface_services = ["sqs", "kms", "ecr.api", "ecr.dkr", "logs", "secretsmanager", "monitoring"]
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(local.interface_services)
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "${var.name_prefix}-${replace(each.value, ".", "-")}-endpoint" }
}

output "vpc_id" { value = aws_vpc.main.id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "worker_security_group_id" { value = aws_security_group.worker.id }
