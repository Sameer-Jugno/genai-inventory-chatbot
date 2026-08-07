# Inventory Planner — Terraform `dev` environment

This folder is the **only place** you should run Terraform. Modules under
`../../modules` are libraries; this env wires them.

## One-command up / down (recommended)

From the **repo root** (not this folder):

```bash
# Create / refresh the full AWS stack (VPC → OpenSearch → Lambda → ECS chat)
./scripts/stack-up.sh

# Tear everything down when you are done (stops most ongoing cost)
./scripts/stack-down.sh
# or non-interactive:
./scripts/stack-down.sh --yes
```

`stack-up.sh` will:

1. Build `dist/ingestion.zip`
2. `terraform apply` foundation + Phase 2 (ECR, OpenSearch, Lambda)
3. Build & push the chat Docker image to ECR
4. `terraform apply` Phase 3 (ECS + ALB forward)
5. Load `.env` keys into Secrets Manager
6. Create the OpenSearch `inventory-items` index
7. Ensure Cognito user `demo@example.com` / `DemoPass123!`

**After a destroy + up, OpenSearch is empty** — re-upload catalog files to S3
`uploads/` (see `DATASET_ANALYTICS.txt`).

Useful flags:

| Flag | Meaning |
|------|---------|
| `--skip-image` | Do not rebuild/push; reuse `chat_container_image` in `terraform.tfvars` |
| `--skip-secrets` | Do not call `put_provider_secrets.sh` |
| `--skip-index` | Do not create the OpenSearch index |
| `--skip-demo-user` | Do not create the Cognito demo user |

## Files

| File | Purpose |
|------|---------|
| `versions.tf` | Terraform + AWS provider pin |
| `providers.tf` | AWS provider / region / default tags |
| `variables.tf` | Inputs (safe defaults + account placeholders + feature flags) |
| `main.tf` | Module composition and wiring |
| `outputs.tf` | Values useful for demos and scripts |
| `terraform.tfvars.example` | Template for real values |

## Feature flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `enable_iam` | `false` | Create ECS + Lambda IAM roles (needs `iam:CreateRole`) |
| `enable_phase2` | `false` | OpenSearch Serverless + ingestion Lambda (requires `enable_iam`) |
| `enable_phase3` | `false` | ECS chat service + ALB forward (requires `enable_phase2` + image URI) |

`stack-up.sh` turns all three **on** via `-var` so you do not need to flip them
manually for a full bring-up. Keep them `true` in `terraform.tfvars` for day-to-day
`terraform apply` after the stack exists.

## Account setup (once)

```bash
cp terraform.tfvars.example terraform.tfvars
# edit region / AZs / opensearch_bootstrap_principal_arns
```

Also create repo-root `.env` with at least:

```bash
GROQ_API_KEY=...
HF_TOKEN=...
# optional: GROQ_API_KEY_2=...
```

`terraform.tfvars` and `.env` are gitignored. Do not commit secrets.

## Manual Terraform (if you prefer)

```bash
cd terraform/envs/dev
aws sts get-caller-identity
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
terraform destroy -var-file=terraform.tfvars
```

Do **not** run `terraform init` inside `terraform/modules/*`.

## Cost notes

- **OpenSearch Serverless** and **ECS Fargate** (plus ALB/NAT if present) are the
  main ongoing costs while the stack is up.
- `stack-down.sh` destroys the Terraform-managed resources so you are not billed
  for idle POC infra overnight.
- S3 is configured with `force_destroy = true` (POC) so destroy succeeds even
  when uploads/images remain in the bucket.
