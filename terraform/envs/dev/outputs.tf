output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer (returns 503 until ECS is wired)."
  value       = module.alb.alb_dns_name
}

output "alb_security_group_id" {
  description = "Security group ID of the ALB — used later by the ECS service ingress rule."
  value       = module.alb.alb_security_group_id
}

output "target_group_arn" {
  description = "ALB target group ARN — ECS will register here in a later phase."
  value       = module.alb.target_group_arn
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "private_subnet_id" {
  description = "Private subnet ID for Fargate / Lambda placement later."
  value       = module.vpc.private_subnet_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs used by the ALB."
  value       = module.vpc.public_subnet_ids
}

output "data_bucket_name" {
  description = "Shared S3 data bucket (uploads/ and images/ prefixes)."
  value       = module.s3.bucket_name
}

output "data_bucket_arn" {
  description = "ARN of the shared S3 data bucket."
  value       = module.s3.bucket_arn
}

output "uploads_prefix" {
  description = "Prefix where administrators place inventory files."
  value       = module.s3.uploads_prefix
}

output "images_prefix" {
  description = "Prefix where the ingestion Lambda writes image assets."
  value       = module.s3.images_prefix
}

output "ecr_repository_url" {
  description = "ECR repository URL for the chat-app image."
  value       = module.ecr.repository_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID for end-user authentication."
  value       = module.cognito.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito app client ID used by the chat UI."
  value       = module.cognito.user_pool_client_id
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for chat session history."
  value       = module.dynamodb.table_name
}

output "ecs_task_execution_role_arn" {
  description = "IAM role ARN used by ECS to pull images and write logs."
  value       = module.iam.ecs_task_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "IAM role ARN assumed by the chat application containers."
  value       = module.iam.ecs_task_role_arn
}

output "lambda_execution_role_arn" {
  description = "IAM role ARN for the future ingestion Lambda."
  value       = module.iam.lambda_execution_role_arn
}
