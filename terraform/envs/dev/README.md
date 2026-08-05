# CandyWagon — Terraform `dev` environment

This folder is the **only place** you should run Terraform for the Phase 1
platform stack. Modules under `../../modules` are libraries; this env wires them.

## Files

| File | Purpose |
|------|---------|
| `versions.tf` | Terraform + AWS provider pin |
| `providers.tf` | AWS provider / region / default tags |
| `variables.tf` | Inputs (safe defaults + account placeholders) |
| `main.tf` | Module composition and wiring |
| `outputs.tf` | Values useful for later phases and demos |
| `terraform.tfvars.example` | Template for real values |

## Account placeholders (fill after access)

Copy the example, then edit:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Update in `terraform.tfvars`:

1. `aws_region`
2. `aws_profile` (or leave empty and use env credentials)
3. `availability_zones` (must match that region)
4. Bedrock Claude + Titan model / inference-profile IDs

`terraform.tfvars` is gitignored. Do not commit real account values.

## After account access — run order

```bash
cd terraform/envs/dev
aws sts get-caller-identity          # prove credentials work
terraform init
terraform plan -var-file=terraform.tfvars
# terraform apply -var-file=terraform.tfvars   # only when ready to create resources
```

Do **not** run `init`/`plan`/`apply` until placeholders are confirmed and AWS credentials work.
