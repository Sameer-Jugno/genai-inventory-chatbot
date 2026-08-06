# Phase 1 foundation modules.
# Phase 2 (OpenSearch + ingestion Lambda) is gated by enable_phase2.
# Phase 3 (ECS chat) is gated by enable_phase3.
# IAM is gated by enable_iam (sameer_user currently lacks iam:CreateRole).

data "aws_caller_identity" "current" {}

module "vpc" {
  source = "../../modules/vpc"

  project_name        = var.project_name
  environment         = var.environment
  vpc_cidr            = var.vpc_cidr
  availability_zones  = var.availability_zones
  public_subnet_cidrs = var.public_subnet_cidrs
  private_subnet_cidr = var.private_subnet_cidr
  common_tags         = var.common_tags
}

module "s3" {
  source = "../../modules/s3"

  project_name = var.project_name
  environment  = var.environment
  common_tags  = var.common_tags
}

module "ecr" {
  source = "../../modules/ecr"

  project_name = var.project_name
  environment  = var.environment
  common_tags  = var.common_tags
}

module "cognito" {
  source = "../../modules/cognito"

  project_name = var.project_name
  environment  = var.environment
  common_tags  = var.common_tags
}

module "dynamodb" {
  source = "../../modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
  common_tags  = var.common_tags
}

module "alb" {
  source = "../../modules/alb"

  project_name      = var.project_name
  environment       = var.environment
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  enable_forward    = var.enable_phase3
  common_tags       = var.common_tags
}

# ---------------------------------------------------------------------------
# IAM — default off until lead grants iam:CreateRole / iam:GetRole.
# Set enable_iam = true in terraform.tfvars, then plan/apply.
# ---------------------------------------------------------------------------
module "provider_secrets" {
  count  = var.enable_iam ? 1 : 0
  source = "../../modules/provider_secrets"

  project_name = var.project_name
  environment  = var.environment
  common_tags  = var.common_tags
}

module "iam" {
  count  = var.enable_iam ? 1 : 0
  source = "../../modules/iam"

  project_name = var.project_name
  environment  = var.environment

  dynamodb_table_arn   = module.dynamodb.table_arn
  data_bucket_arn      = module.s3.bucket_arn
  provider_secrets_arn = module.provider_secrets[0].secret_arn

  common_tags = var.common_tags
}

# ---------------------------------------------------------------------------
# Phase 2 — OpenSearch Serverless + ingestion Lambda.
# Requires enable_iam = true. Default enable_phase2 = false (do not apply yet).
# Build the zip before enabling: scripts/build_ingestion_package.sh
# ---------------------------------------------------------------------------
locals {
  ingestion_package_path = "${path.module}/../../../dist/ingestion.zip"
  ingestion_dlq_arn      = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${var.project_name}-${var.environment}-ingestion-dlq"
}

module "opensearch" {
  count  = var.enable_phase2 ? 1 : 0
  source = "../../modules/opensearch"

  project_name = var.project_name
  environment  = var.environment

  data_access_principal_arns = concat(
    module.iam[*].lambda_execution_role_arn,
    module.iam[*].ecs_task_role_arn,
    var.opensearch_bootstrap_principal_arns,
  )

  common_tags = var.common_tags
}

resource "aws_iam_role_policy" "ecs_task_opensearch" {
  count = var.enable_phase2 ? 1 : 0

  name = "${var.project_name}-${var.environment}-ecs-task-opensearch"
  role = module.iam[0].ecs_task_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "OpenSearchServerlessAPI"
      Effect   = "Allow"
      Action   = ["aoss:APIAccessAll"]
      Resource = module.opensearch[0].collection_arn
    }]
  })
}

resource "aws_iam_role_policy" "lambda_execution_opensearch" {
  count = var.enable_phase2 ? 1 : 0

  name = "${var.project_name}-${var.environment}-lambda-opensearch"
  role = module.iam[0].lambda_execution_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "OpenSearchServerlessAPI"
      Effect   = "Allow"
      Action   = ["aoss:APIAccessAll"]
      Resource = module.opensearch[0].collection_arn
    }]
  })
}

resource "aws_iam_role_policy" "lambda_execution_dlq" {
  count = var.enable_phase2 ? 1 : 0

  name = "${var.project_name}-${var.environment}-lambda-dlq"
  role = module.iam[0].lambda_execution_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SendToIngestionDLQ"
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = local.ingestion_dlq_arn
    }]
  })
}

module "ingestion_lambda" {
  count  = var.enable_phase2 ? 1 : 0
  source = "../../modules/ingestion_lambda"

  project_name    = var.project_name
  environment     = var.environment
  aws_region      = var.aws_region
  lambda_role_arn = try(module.iam[0].lambda_execution_role_arn, "")

  package_path     = local.ingestion_package_path
  source_code_hash = var.enable_phase2 ? filebase64sha256(local.ingestion_package_path) : ""

  data_bucket_id   = module.s3.bucket_name
  data_bucket_arn  = module.s3.bucket_arn
  data_bucket_name = module.s3.bucket_name
  uploads_prefix   = module.s3.uploads_prefix
  images_prefix    = module.s3.images_prefix

  opensearch_endpoint = try(module.opensearch[0].collection_endpoint, "")
  opensearch_index    = var.opensearch_index

  groq_model_id         = var.groq_model_id
  hf_embed_model_id     = var.hf_embed_model_id
  provider_secrets_arn  = module.provider_secrets[0].secret_arn

  common_tags = var.common_tags

  depends_on = [
    aws_iam_role_policy.lambda_execution_opensearch,
    aws_iam_role_policy.lambda_execution_dlq,
  ]
}

# ---------------------------------------------------------------------------
# Phase 3 — ECS Fargate chat service (Chainlit + Groq agent).
# Requires enable_phase2 (OpenSearch) and a pushed ECR image URI.
# ---------------------------------------------------------------------------
module "ecs_chat" {
  count  = var.enable_phase3 ? 1 : 0
  source = "../../modules/ecs_chat"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  vpc_id                = module.vpc.vpc_id
  private_subnet_id     = module.vpc.private_subnet_id
  alb_security_group_id = module.alb.alb_security_group_id
  target_group_arn      = module.alb.target_group_arn

  execution_role_arn = module.iam[0].ecs_task_execution_role_arn
  task_role_arn      = module.iam[0].ecs_task_role_arn

  container_image = var.chat_container_image

  opensearch_endpoint    = module.opensearch[0].collection_endpoint
  opensearch_index       = var.opensearch_index
  groq_model_id          = var.groq_model_id
  hf_embed_model_id      = var.hf_embed_model_id
  provider_secrets_arn   = module.provider_secrets[0].secret_arn
  dynamodb_table_name    = module.dynamodb.table_name
  data_bucket_name       = module.s3.bucket_name
  images_prefix          = module.s3.images_prefix
  cognito_user_pool_id   = module.cognito.user_pool_id
  cognito_app_client_id  = module.cognito.user_pool_client_id

  common_tags = var.common_tags

  depends_on = [
    aws_iam_role_policy.ecs_task_opensearch,
    module.ingestion_lambda,
  ]
}
