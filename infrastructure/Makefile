# Terraform for the Phase 2 case-prep platform. S3 backend with native state locking.
# Usage:  make init STAGE=dev   |   make plan STAGE=dev   |   make apply STAGE=prod
STAGE ?= dev

.PHONY: bootstrap init plan apply fmt validate destroy

# One-time, out-of-band: create the state bucket the S3 backend locks against.
# (Chicken-and-egg — the backend can't create its own bucket.)
bootstrap:
	aws s3api create-bucket --bucket artech-implantcad-tfstate --region us-east-1
	aws s3api put-bucket-versioning --bucket artech-implantcad-tfstate \
	  --versioning-configuration Status=Enabled
	aws s3api put-public-access-block --bucket artech-implantcad-tfstate \
	  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

init:
	terraform init -reconfigure -backend-config=backend.$(STAGE).hcl

plan:
	terraform plan -var-file=environments/$(STAGE).tfvars

apply:
	terraform apply -var-file=environments/$(STAGE).tfvars

destroy:
	terraform destroy -var-file=environments/$(STAGE).tfvars

fmt:
	terraform fmt -recursive

validate:
	terraform validate
