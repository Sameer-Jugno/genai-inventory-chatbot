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
  common_tags       = var.common_tags
}

module "iam" {
  source = "../../modules/iam"

  project_name = var.project_name
  environment  = var.environment

  dynamodb_table_arn = module.dynamodb.table_arn
  data_bucket_arn    = module.s3.bucket_arn

  # PLACEHOLDERS until Bedrock model access is confirmed in the AWS account
  bedrock_claude_inference_profile_id = var.bedrock_claude_inference_profile_id
  bedrock_claude_foundation_model_id  = var.bedrock_claude_foundation_model_id
  bedrock_titan_embedding_model_id    = var.bedrock_titan_embedding_model_id

  common_tags = var.common_tags
}
