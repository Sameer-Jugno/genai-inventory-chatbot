variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_id" {
  type = string
}

variable "alb_security_group_id" {
  type = string
}

variable "target_group_arn" {
  type = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "container_image" {
  description = "Full ECR image URI including tag."
  type        = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "opensearch_endpoint" {
  type = string
}

variable "opensearch_index" {
  type = string
}

variable "groq_model_id" {
  description = "Groq chat model ID."
  type        = string
  default     = "llama-3.3-70b-versatile"
}

variable "hf_embed_model_id" {
  description = "Hugging Face embedding model ID."
  type        = string
  default     = "BAAI/bge-large-en-v1.5"
}

variable "provider_secrets_arn" {
  description = "Secrets Manager ARN containing GROQ_API_KEY and HF_TOKEN."
  type        = string
}

variable "dynamodb_table_name" {
  type = string
}

variable "data_bucket_name" {
  type = string
}

variable "images_prefix" {
  type    = string
  default = "images/"
}

variable "cognito_user_pool_id" {
  type = string
}

variable "cognito_app_client_id" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
