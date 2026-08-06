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
  value       = try(module.iam[0].ecs_task_execution_role_arn, null)
}

output "ecs_task_role_arn" {
  description = "IAM role ARN assumed by the chat application containers."
  value       = try(module.iam[0].ecs_task_role_arn, null)
}

output "lambda_execution_role_arn" {
  description = "IAM role ARN for the ingestion Lambda."
  value       = try(module.iam[0].lambda_execution_role_arn, null)
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint (null until enable_phase2)."
  value       = try(module.opensearch[0].collection_endpoint, null)
}

output "opensearch_collection_arn" {
  description = "OpenSearch Serverless collection ARN (null until enable_phase2)."
  value       = try(module.opensearch[0].collection_arn, null)
}

output "ingestion_function_name" {
  description = "Ingestion Lambda function name (null until enable_phase2)."
  value       = try(module.ingestion_lambda[0].function_name, null)
}

output "ingestion_dlq_url" {
  description = "Ingestion dead-letter queue URL (null until enable_phase2)."
  value       = try(module.ingestion_lambda[0].dlq_url, null)
}

output "chat_ecs_cluster_name" {
  description = "ECS cluster name for the chat service (null until enable_phase3)."
  value       = try(module.ecs_chat[0].cluster_name, null)
}

output "chat_ecs_service_name" {
  description = "ECS service name for the chat application (null until enable_phase3)."
  value       = try(module.ecs_chat[0].service_name, null)
}

output "chat_log_group_name" {
  description = "CloudWatch log group for the chat tasks (null until enable_phase3)."
  value       = try(module.ecs_chat[0].log_group_name, null)
}

output "provider_secrets_arn" {
  description = "Secrets Manager ARN for GROQ_API_KEY + HF_TOKEN (null until enable_iam)."
  value       = try(module.provider_secrets[0].secret_arn, null)
}
